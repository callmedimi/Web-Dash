"""Tests for Step 9.5: Alarm Center Screen Backend APIs and Planning."""
import pytest
import uuid
from backend.app import create_app
from backend.app.models.device import Device
from backend.app.extensions import get_db_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"test_alarms_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, role="admin"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": "noc_operator",
            "role": role,
            "permissions": {"alarms": True, "changes": True, "admin": True},
            "display_name": "NOC Operator",
            "must_change_password": False,
        }
        sess["user_id"] = "noc_operator"
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_alarms_unauthenticated(client):
    res = client.get("/api/v1/alarms/active")
    assert res.status_code == 401


def test_alarm_filters_crud(client):
    _login(client)

    # 1. Create Filter Preset
    filter_payload = {
        "name": "Tehran_Critical_Only",
        "description": "Critical alarms filter preset",
        "criteria": {
            "province": "TEH",
            "level": "Critical",
            "source": "both",
        },
    }
    res = client.post(
        "/api/v1/alarms/filters",
        json=filter_payload,
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 201
    created = res.get_json()
    assert created["name"] == "Tehran_Critical_Only"
    filter_id = created["id"]

    # 2. List Filter Presets
    res = client.get("/api/v1/alarms/filters")
    assert res.status_code == 200
    filters = res.get_json()
    assert any(f["id"] == filter_id for f in filters)

    # 3. Delete Filter Preset
    res = client.delete(
        f"/api/v1/alarms/filters/{filter_id}",
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "deleted"


def test_alarm_statistics_endpoint(client):
    _login(client)

    mock_alarms = [
        {"device_name": "R1", "level_name": "Critical", "age_minutes": 10},
        {"device_name": "R1", "level_name": "Major", "age_minutes": 100},
    ]

    res = client.post(
        "/api/v1/alarms/statistics",
        json={"alarms": mock_alarms},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["total_alarms"] == 2
    assert stats["level_breakdown"]["Critical"] == 1


def test_plan_alarm_clear_endpoint(client):
    _login(client, role="admin")

    with get_db_session() as db:
        d = Device(name="DEV-ALARM-PLAN-01", mgmt_ip="10.150.1.1", province="TEH", role="PE", enabled=True)
        db.add(d)
        db.commit()
        dev_id = d.id

    alarm_items = [
        {
            "device_id": dev_id,
            "sequence": 101,
            "description": "Interface GigabitEthernet0/1/0 physical status is Down",
        }
    ]

    res = client.post(
        "/api/v1/alarms/clear-plan",
        json={"alarms": alarm_items, "noconf_shutdown": False},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 201
    plan_data = res.get_json()
    assert plan_data["status"] == "planned"
    assert plan_data["count"] >= 1
