"""Tests for Step 9.3: Devices Screen Backend APIs and Integration."""
import pytest
import uuid
from backend.app import create_app
from backend.app.models.device import Device
from backend.app.extensions import get_db_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"test_devices_{uuid.uuid4().hex[:8]}.db"
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
            "username": "noc_admin",
            "role": role,
            "permissions": {"devices": True, "admin": True},
            "display_name": "NOC Administrator",
            "must_change_password": False,
        }
        sess["user_id"] = "noc_admin"
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_devices_list_unauthenticated(client):
    res = client.get("/api/v1/devices")
    assert res.status_code == 401


def test_devices_crud_and_filters(client):
    _login(client)

    dev_name = f"NE40E-TEH-{uuid.uuid4().hex[:6]}"
    payload = {
        "name": dev_name,
        "mgmt_ip": "10.200.1.10",
        "vendor": "huawei",
        "os_family": "vrp8",
        "model": "NetEngine 40E-X8",
        "role": "PE",
        "province": "TEH",
        "site": "TEH-CENTRAL",
        "tags": ["core", "mpls"],
    }
    res = client.post(
        "/api/v1/devices",
        json=payload,
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 201
    created = res.get_json()
    assert created["name"] == dev_name
    dev_id = created["id"]

    # 2. List with province filter
    res = client.get("/api/v1/devices?province=TEH")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total"] >= 1
    assert any(d["id"] == dev_id for d in data["devices"])

    # 3. Update device
    res = client.put(
        f"/api/v1/devices/{dev_id}",
        json={"site": "TEH-NORTH"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 200
    assert res.get_json()["site"] == "TEH-NORTH"

    # 4. Filter by role
    res = client.get("/api/v1/devices?role=PE")
    assert res.status_code == 200
    assert any(d["id"] == dev_id for d in res.get_json()["devices"])


def test_target_sets_creation_and_membership(client):
    _login(client)

    d1_name = f"DEV-TS-1-{uuid.uuid4().hex[:6]}"
    d2_name = f"DEV-TS-2-{uuid.uuid4().hex[:6]}"
    with get_db_session() as db:
        d1 = Device(name=d1_name, mgmt_ip="10.210.1.1", province="ISF", role="PE", enabled=True)
        d2 = Device(name=d2_name, mgmt_ip="10.210.1.2", province="ISF", role="P", enabled=True)
        db.add_all([d1, d2])
        db.commit()
        id1, id2 = d1.id, d2.id

    ts_name = f"Isfahan_Set_{uuid.uuid4().hex[:6]}"
    ts_payload = {
        "name": ts_name,
        "description": "Transit routers in Isfahan province",
        "device_ids": [id1, id2],
        "filter_criteria": {"province": "ISF"},
    }
    res = client.post(
        "/api/v1/devices/target-sets",
        json=ts_payload,
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 201
    ts_data = res.get_json()
    assert ts_data["name"] == ts_name
    assert len(ts_data["device_ids"]) == 2

    # List Target Sets
    res = client.get("/api/v1/devices/target-sets")
    assert res.status_code == 200
    sets = res.get_json()
    assert any(s["name"] == ts_name for s in sets)


def test_devices_csv_export(client):
    _login(client)
    res = client.get("/api/v1/devices/export?format=csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("Content-Type", "")
    assert "NE Name,NE IP Address" in res.get_data(as_text=True)
