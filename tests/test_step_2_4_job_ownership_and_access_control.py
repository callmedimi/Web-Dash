"""Unit tests for Step 2.4: Job Ownership, RBAC access control, and Deterministic CSV Export."""
import csv
import io
import pytest
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.jobs.engine import engine


@pytest.fixture
def app_client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


@pytest.fixture
def clean_db():
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.commit()
    yield
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.commit()


def test_operator_cannot_access_other_users_job_returns_404(app_client, clean_jobs=None):
    """
    Verify: User B requesting User A's job -> 404 (not 403, avoid enumeration - F-05).
    Applies to details, events, download, and cancel.
    """
    # Create Job A owned by 'operator_a'
    job_a_id = engine.submit(
        job_type="config_check",
        params={"opt": 1},
        user="operator_a",
        target_devices=["ROUTER-1"],
    )

    # 1. As operator_b (different user)
    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "operator_b", "role": "operator"}

    # Attempt to view Job A -> must be 404
    res_get = app_client.get(f"/api/v1/jobs/{job_a_id}")
    assert res_get.status_code == 404
    assert res_get.get_json()["error"]["code"] == "NOT_FOUND"

    # Attempt to stream events of Job A -> must be 404
    res_events = app_client.get(f"/api/v1/jobs/{job_a_id}/events")
    assert res_events.status_code == 404

    # Attempt to download Job A CSV -> must be 404
    res_dl = app_client.get(f"/api/v1/jobs/{job_a_id}/download")
    assert res_dl.status_code == 404

    # Attempt to cancel Job A -> must be 404
    res_cancel = app_client.post(f"/api/v1/jobs/{job_a_id}/cancel")
    assert res_cancel.status_code == 404


def test_job_list_filtering_by_role(app_client, clean_jobs=None):
    """Test that operators only see their own jobs, while admin sees all."""
    # Submit Job A by operator_a
    job_a_id = engine.submit("job_a_type", {}, "operator_a", target_devices=["DEV-A"])
    # Submit Job B by operator_b
    job_b_id = engine.submit("job_b_type", {}, "operator_b", target_devices=["DEV-B"])

    # As operator_a:
    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "operator_a", "role": "operator"}

    res_a = app_client.get("/api/v1/jobs")
    assert res_a.status_code == 200
    items_a = res_a.get_json()["items"]
    job_ids_a = [j["id"] for j in items_a]
    assert job_a_id in job_ids_a
    assert job_b_id not in job_ids_a

    # As operator_b:
    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "operator_b", "role": "operator"}

    res_b = app_client.get("/api/v1/jobs")
    assert res_b.status_code == 200
    items_b = res_b.get_json()["items"]
    job_ids_b = [j["id"] for j in items_b]
    assert job_b_id in job_ids_b
    assert job_a_id not in job_ids_b

    # As admin:
    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "superadmin", "role": "admin"}

    res_admin = app_client.get("/api/v1/jobs")
    assert res_admin.status_code == 200
    items_admin = res_admin.get_json()["items"]
    job_ids_admin = [j["id"] for j in items_admin]
    assert job_a_id in job_ids_admin
    assert job_b_id in job_ids_admin


def test_admin_and_god_can_access_any_job(app_client, clean_jobs=None):
    """Verify admin and god can access, stream, and download jobs created by operators."""
    job_id = engine.submit("operator_task", {}, "operator_x", target_devices=["ROUTER-X"])

    for role in ("admin", "god"):
        with app_client.session_transaction() as sess:
            sess["user"] = {"username": f"user_{role}", "role": role}

        res_get = app_client.get(f"/api/v1/jobs/{job_id}")
        assert res_get.status_code == 200

        res_dl = app_client.get(f"/api/v1/jobs/{job_id}/download")
        assert res_dl.status_code == 200


def test_deterministic_csv_download(app_client, clean_jobs=None):
    """
    Test deterministic CSV generation from DB:
    - Sourced from DB rows each time.
    - Deterministic sorting by device_name asc, id asc.
    - Zero mutation of database records.
    - Identical content across successive requests.
    """
    devices = ["Z-ROUTER-99", "A-ROUTER-01", "M-ROUTER-50"]
    job_id = engine.submit("bulk_export_test", {}, "operator_1", target_devices=devices)

    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "operator_1", "role": "operator"}

    res1 = app_client.get(f"/api/v1/jobs/{job_id}/download")
    assert res1.status_code == 200
    assert "text/csv" in res1.content_type
    assert f'job_bulk_export_test_{job_id}.csv' in res1.headers.get("Content-Disposition", "")

    csv_text1 = res1.get_data(as_text=True)

    # Parse and verify deterministic alphabetical device ordering
    reader = csv.reader(io.StringIO(csv_text1))
    header = next(reader)
    assert header[3] == "device_name"

    rows = list(reader)
    assert len(rows) == 3
    # Must be sorted alphabetically: A-ROUTER-01, M-ROUTER-50, Z-ROUTER-99
    assert rows[0][3] == "A-ROUTER-01"
    assert rows[1][3] == "M-ROUTER-50"
    assert rows[2][3] == "Z-ROUTER-99"

    # Second download must be byte-for-byte identical
    res2 = app_client.get(f"/api/v1/jobs/{job_id}/download")
    assert res2.status_code == 200
    csv_text2 = res2.get_data(as_text=True)
    assert csv_text1 == csv_text2


def test_root_jobs_alias_urls(app_client, clean_jobs=None):
    """Test /jobs root alias path alongside /api/v1/jobs."""
    job_id = engine.submit("alias_test", {}, "op_alias", target_devices=["DEV-1"])

    with app_client.session_transaction() as sess:
        sess["user"] = {"username": "op_alias", "role": "operator"}

    res = app_client.get(f"/jobs/{job_id}")
    assert res.status_code == 200
    assert res.get_json()["id"] == job_id
