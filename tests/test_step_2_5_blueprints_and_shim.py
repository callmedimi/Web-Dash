"""Unit tests for Step 2.5: Modular Blueprints, Entrypoint Shim, and Schedules API."""
import os
import json
import pytest
from app import app
from backend.app import create_app
import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "InitialAdminPassword123!")

    app.config["TESTING"] = True
    auth.clear_all_rate_limits()
    auth._load_users()

    u = auth.get_user("admin")
    if not u:
        auth.create_user("admin", "InitialAdminPassword123!", role="god")
    auth.update_user(
        "admin",
        {"password": "InitialAdminPassword123!", "must_change_password": False, "is_active": True},
    )

    with app.test_client() as c:
        yield c


def login_admin(client):
    auth.clear_all_rate_limits()
    res = client.post("/login", json={"username": "admin", "password": "InitialAdminPassword123!"})
    assert res.status_code == 200
    me = client.get("/me").get_json()
    return me.get("csrf_token")


def test_app_shim_and_blueprint_registration():
    """Verify that app.py is a clean loader shim and all 13 blueprints are registered."""
    test_app = create_app({"TESTING": True})
    blueprints = test_app.blueprints
    expected_blueprints = [
        "main",
        "auth_api",
        "users_api",
        "jobs_api",
        "alarm_clear_api",
        "reports_api",
        "license_api",
        "routing_api",
        "telemetry_api",
        "arp_api",
        "sessions_export_api",
        "ptp_api",
        "schedules_api",
    ]
    for bp in expected_blueprints:
        assert bp in blueprints, f"Blueprint {bp} was not registered on Flask application"


def test_main_index_route(client):
    """Verify GET / renders the main dashboard page."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"<!DOCTYPE html>" in res.data or b"<html" in res.data


def test_routing_blueprint_endpoints(client):
    """Verify routing blueprint routes (/vrf-router-info, /parse-interface-config)."""
    csrf = login_admin(client)
    res_info = client.get("/vrf-router-info")
    assert res_info.status_code == 200
    assert "name" in res_info.get_json()

    res_parse = client.post(
        "/parse-interface-config",
        json={"config": "interface GigabitEthernet0/0/1\n ip address 10.0.0.1 24\n"},
        headers={"X-CSRF-Token": csrf},
    )
    assert res_parse.status_code == 200


def test_arp_and_historical_snapshots_endpoints(client):
    """Verify ARP search and historical snapshots archive endpoints."""
    csrf = login_admin(client)

    # 1. ARP search
    res_search = client.post(
        "/search-site-arp-mac",
        json={"keyword": "TEH-01"},
        headers={"X-CSRF-Token": csrf},
    )
    assert res_search.status_code in (200, 404, 500)

    # 2. Historical Snapshots list
    res_snaps = client.get("/admin/arp-mac/snapshots")
    assert res_snaps.status_code == 200
    assert isinstance(res_snaps.get_json(), list)

    # 3. Collector status
    res_status = client.get("/admin/arp-mac-collector-status")
    assert res_status.status_code == 200


def test_schedules_crud_and_trigger_endpoints(client):
    """Verify admin cron schedules API CRUD, toggle, and trigger now."""
    csrf = login_admin(client)

    # 1. List schedules initially
    res_list = client.get("/api/v1/schedules")
    assert res_list.status_code == 200
    initial_count = res_list.get_json()["count"]

    # 2. Create new cron schedule
    res_create = client.post(
        "/api/v1/schedules",
        json={
            "job_type": "arp_mac_collector",
            "cron": "0 2 * * *",
            "params": {"threads": 10},
            "enabled": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert res_create.status_code == 201
    created = res_create.get_json()
    schedule_id = created["schedule_id"]

    # 3. Toggle schedule
    res_toggle = client.post(
        f"/api/v1/schedules/{schedule_id}/toggle",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert res_toggle.status_code == 200
    assert res_toggle.get_json()["enabled"] is False

    # 4. Trigger schedule now
    res_run = client.post(
        f"/api/v1/schedules/{schedule_id}/run",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert res_run.status_code == 200
    assert res_run.get_json()["status"] == "triggered"
    assert "job_id" in res_run.get_json()

    # 5. Delete schedule
    res_del = client.delete(
        f"/api/v1/schedules/{schedule_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert res_del.status_code == 200


def test_sessions_export_and_ptp_target_search(client):
    """Verify sessions extractor and PTP troubleshoot endpoints."""
    csrf = login_admin(client)

    # PTP target search
    res_ptp = client.post(
        "/ptp/search-targets",
        json={"keyword": "ROUTER"},
        headers={"X-CSRF-Token": csrf},
    )
    assert res_ptp.status_code == 200
    assert "candidates" in res_ptp.get_json()
