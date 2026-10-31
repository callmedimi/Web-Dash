"""Integration and Acceptance tests for Step 9.8: Reports & Analytics Screen.
Tests Down-Links reports, run-to-run comparison, CSV/XLSX export, daily NOC digest, and schedules.
"""
import pytest
import uuid
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.down_link import DownLinkReport


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"webdash_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WEBDASH_DB_URL", db_url)
    monkeypatch.setenv("WEBDASH_SECRET_KEY", "test-secret-phase7-step8")
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="report_operator", role="operator"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {"reporting": True, "admin": True, "admin_schedule_manage": True},
            "display_name": username.title(),
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_down_links_report_lifecycle_and_comparison(client):
    _login(client)

    # 1. Seed two down link reports in DB for comparison
    with get_db_session() as db:
        rep1 = DownLinkReport(
            province="TEH",
            report_data=[
                {"NE NAME": "PE-TEH-01", "interface name": "GigabitEthernet0/1/0", "Description": "Uplink to Node A"},
                {"NE NAME": "PE-TEH-01", "interface name": "GigabitEthernet0/1/1", "Description": "Trunk Link B"},
            ],
            noconf_data=[],
            trunk_data=[],
            analytics={"total_down": 2, "total_routers": 1, "noconf_count": 0, "trunk_count": 0},
        )
        db.add(rep1)
        db.commit()
        rep1_id = rep1.id

        rep2 = DownLinkReport(
            province="TEH",
            report_data=[
                # GigabitEthernet0/1/0 recovered!
                {"NE NAME": "PE-TEH-01", "interface name": "GigabitEthernet0/1/1", "Description": "Trunk Link B"},
                # New down link!
                {"NE NAME": "PE-TEH-02", "interface name": "GigabitEthernet0/2/0", "Description": "New Customer Link"},
            ],
            noconf_data=[],
            trunk_data=[],
            analytics={"total_down": 2, "total_routers": 2, "noconf_count": 0, "trunk_count": 0},
        )
        db.add(rep2)
        db.commit()
        rep2_id = rep2.id

    # 2. Get latest report
    res_latest = client.get("/api/v1/reports/down-links/latest?province=TEH")
    assert res_latest.status_code == 200
    latest_data = res_latest.get_json()
    assert latest_data["id"] == rep2_id
    assert len(latest_data["report_data"]) == 2

    # 3. Compare rep2 against rep1
    res_compare = client.get(f"/api/v1/reports/down-links/{rep2_id}/compare?compare_with_id={rep1_id}")
    assert res_compare.status_code == 200
    comp = res_compare.get_json()
    new_down = comp.get("new_down_links", [])
    recovered = comp.get("recovered_links", [])
    assert len(new_down) == 1
    assert new_down[0]["interface name"] == "GigabitEthernet0/2/0"
    assert len(recovered) == 1
    assert recovered[0]["interface name"] == "GigabitEthernet0/1/0"

    # 4. Export CSV & XLSX
    res_csv = client.get(f"/api/v1/reports/down-links/{rep2_id}/export?format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.content_type

    res_xlsx = client.get(f"/api/v1/reports/down-links/{rep2_id}/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert "spreadsheetml" in res_xlsx.content_type


def test_daily_noc_digest_and_schedules(client):
    _login(client)

    # 1. Fetch Daily NOC Digest
    res_digest = client.get("/api/v1/reports/digest?hours=24")
    assert res_digest.status_code == 200
    digest_data = res_digest.get_json()
    assert "metrics" in digest_data
    assert digest_data["period"]["window_hours"] == 24

    # 2. Export Daily NOC Digest
    res_export = client.get("/api/v1/reports/digest/export?hours=24&format=xlsx")
    assert res_export.status_code == 200
    assert "spreadsheetml" in res_export.content_type

    # 3. Create Recurring Report Schedule
    schedule_payload = {
        "job_type": "down_links_report",
        "cron": "0 6 * * *",
        "params": {"province": "TEH", "age_value": 2, "age_unit": "days"},
    }
    res_sched = client.post("/api/v1/schedules", json=schedule_payload, headers={"X-CSRF-Token": "valid_csrf"})
    assert res_sched.status_code == 201
    sched_data = res_sched.get_json()
    assert sched_data["status"] == "created"
    assert "schedule_id" in sched_data
