"""Integration and Acceptance tests for Step 9.7: Automation Jobs Screen.
Tests job submission, list filtering, detail query, cancellation, and CSV export.
"""
import pytest
import uuid
from backend.app import create_app
from backend.app.db.session import init_db, get_db_session
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.models.job import Job, JobTask


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"webdash_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WEBDASH_DB_URL", db_url)
    monkeypatch.setenv("WEBDASH_SECRET_KEY", "test-secret-phase7-step7")
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="ops_lead", role="operator"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {"jobs": True, "admin": role in ("admin", "god")},
            "display_name": username.title(),
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_jobs_submission_and_lifecycle(client):
    # 1. Login as operator
    _login(client, username="ops_lead", role="operator")

    # 2. Submit new automation job
    payload = {
        "type": "alarm_clear",
        "mode": "dry_run",
        "params": {"timeout": 30},
        "devices": ["PE-TEH-01", "PE-TEH-02"],
    }
    res = client.post("/api/v1/jobs", json=payload, headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 202
    data = res.get_json()
    job_id = data["job_id"]
    assert data["status"] == "queued"

    # 3. List jobs - verify job appears in list
    res_list = client.get("/api/v1/jobs")
    assert res_list.status_code == 200
    list_data = res_list.get_json()
    assert list_data["total"] >= 1
    matched = [j for j in list_data["items"] if j["id"] == job_id]
    assert len(matched) == 1
    assert matched[0]["type"] == "alarm_clear"
    assert matched[0]["created_by"] == "ops_lead"

    # 4. Filter jobs by type
    res_filt = client.get("/api/v1/jobs?type=alarm_clear")
    assert res_filt.status_code == 200
    assert any(j["id"] == job_id for j in res_filt.get_json()["items"])

    res_filt_none = client.get("/api/v1/jobs?type=non_existent_type")
    assert res_filt_none.status_code == 200
    assert not any(j["id"] == job_id for j in res_filt_none.get_json()["items"])

    # 5. Get Single Job Detail
    res_detail = client.get(f"/api/v1/jobs/{job_id}")
    assert res_detail.status_code == 200
    detail_data = res_detail.get_json()
    assert detail_data["id"] == job_id
    assert detail_data["created_by"] == "ops_lead"
    assert "tasks" in detail_data
    assert len(detail_data["tasks"]) == 2

    # 6. Cancel Job
    res_cancel = client.post(f"/api/v1/jobs/{job_id}/cancel", headers={"X-CSRF-Token": "valid_csrf"})
    assert res_cancel.status_code in (200, 400)  # 200 if queued/running, 400 if already terminated

    # 7. Download CSV export
    res_csv = client.get(f"/api/v1/jobs/{job_id}/download")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.content_type
    csv_text = res_csv.get_data(as_text=True)
    assert "job_id,job_type,task_id,device_name" in csv_text
    assert "PE-TEH-01" in csv_text
    assert "PE-TEH-02" in csv_text


def test_jobs_rbac_isolation(client):
    # Operator 1 submits a job
    _login(client, username="user_one", role="operator")
    res = client.post(
        "/api/v1/jobs",
        json={"type": "license_check", "mode": "dry_run", "devices": ["PE-MHD-01"]},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 202
    job_id_1 = res.get_json()["job_id"]

    # Operator 2 logs in - must NOT see Operator 1's job (F-05, F-30)
    _login(client, username="user_two", role="operator")
    res_list = client.get("/api/v1/jobs")
    assert res_list.status_code == 200
    items = res_list.get_json()["items"]
    assert not any(j["id"] == job_id_1 for j in items)

    # Operator 2 direct access returns 404 (not 403, preventing enumeration)
    res_direct = client.get(f"/api/v1/jobs/{job_id_1}")
    assert res_direct.status_code == 404

    # Admin logs in - CAN see all jobs
    _login(client, username="admin_boss", role="admin")
    res_admin_list = client.get("/api/v1/jobs")
    assert res_admin_list.status_code == 200
    assert any(j["id"] == job_id_1 for j in res_admin_list.get_json()["items"])

    res_admin_get = client.get(f"/api/v1/jobs/{job_id_1}")
    assert res_admin_get.status_code == 200
    assert res_admin_get.get_json()["id"] == job_id_1
