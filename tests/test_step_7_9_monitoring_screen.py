"""Integration and Acceptance tests for Step 9.9: Monitoring Hub Screen.
Tests fleet health, device telemetry, interface search, telemetry doctor, and webhook ingestion.
"""
import pytest
import uuid
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.device import Device


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"webdash_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WEBDASH_DB_URL", db_url)
    monkeypatch.setenv("WEBDASH_SECRET_KEY", "test-secret-phase7-step9")
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="telemetry_operator", role="operator"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {"monitoring": True, "admin": True},
            "display_name": username.title(),
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_fleet_health_endpoint(client):
    _login(client)

    dev_teh = f"PE-TEH-{uuid.uuid4().hex[:6].upper()}"
    dev_shr = f"PE-SHR-{uuid.uuid4().hex[:6].upper()}"

    # 1. Seed two test devices with unique names
    with get_db_session() as db:
        dev1 = Device(
            name=dev_teh,
            mgmt_ip="10.10.1.1",
            vendor="huawei",
            province="TEH",
            role="PE",
            enabled=True,
        )
        dev2 = Device(
            name=dev_shr,
            mgmt_ip="10.20.1.1",
            vendor="huawei",
            province="FRS",
            role="PE",
            enabled=True,
        )
        db.add_all([dev1, dev2])
        db.commit()

    # 2. Query fleet health
    resp = client.get("/api/v1/telemetry/fleet-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "devices" in data
    assert "summary" in data

    device_names = [d["name"] for d in data["devices"]]
    assert dev_teh in device_names
    assert dev_shr in device_names

    # Test filtering by province
    resp_teh = client.get("/api/v1/telemetry/fleet-health?province=TEH")
    assert resp_teh.status_code == 200
    teh_data = resp_teh.get_json()
    teh_names = [d["name"] for d in teh_data["devices"]]
    assert dev_teh in teh_names
    assert dev_shr not in teh_names


def test_device_monitoring_and_doctor(client):
    _login(client)

    dev_isf = f"PE-ISF-{uuid.uuid4().hex[:6].upper()}"

    with get_db_session() as db:
        dev = Device(
            name=dev_isf,
            mgmt_ip="10.30.1.1",
            vendor="huawei",
            province="ISF",
            role="PE",
            enabled=True,
        )
        db.add(dev)
        db.commit()

    # Query device monitoring
    resp = client.get(f"/api/v1/telemetry/device/{dev_isf}")
    assert resp.status_code == 200
    mon_data = resp.get_json()
    assert mon_data["device"]["name"] == dev_isf
    assert "interfaces" in mon_data
    assert "grafana" in mon_data

    # Query telemetry doctor
    doctor_resp = client.get("/api/v1/telemetry/doctor")
    assert doctor_resp.status_code == 200
    doc_data = doctor_resp.get_json()
    assert "zabbix" in doc_data
    assert "grafana" in doc_data
    assert "coverage" in doc_data


def test_webhook_ingestion(client):
    # Webhook endpoint does not require session authentication
    payload = {
        "event_id": "EVT-1001",
        "severity": "high",
        "title": "BGP Session Down on Core Router",
        "host": "PE-TEST-01",
    }
    resp = client.post("/api/v1/telemetry/webhook", json=payload)
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data.get("status") in ("received", "accepted")
