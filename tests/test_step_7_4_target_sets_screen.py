"""Tests for Step 9.4: Target Sets Screen Backend APIs and Resolution."""
import pytest
import uuid
from backend.app import create_app
from backend.app.models.device import Device, TargetSet
from backend.app.extensions import get_db_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"test_targets_{uuid.uuid4().hex[:8]}.db"
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


def test_target_sets_unauthenticated(client):
    res = client.get("/api/v1/devices/target-sets")
    assert res.status_code == 401


def test_target_sets_crud_and_dynamic_resolution(client):
    _login(client)

    # 1. Seed devices
    uid = uuid.uuid4().hex[:6]
    with get_db_session() as db:
        d1 = Device(name=f"PE-TEH-{uid}-1", mgmt_ip="10.10.1.1", province="TEH", role="PE", os_family="vrp8", tags=["mpls", "core"], enabled=True)
        d2 = Device(name=f"PE-TEH-{uid}-2", mgmt_ip="10.10.1.2", province="TEH", role="PE", os_family="vrp8", tags=["mpls"], enabled=True)
        d3 = Device(name=f"P-ISF-{uid}-1", mgmt_ip="10.20.1.1", province="ISF", role="P", os_family="vrp8", tags=["transit"], enabled=True)
        db.add_all([d1, d2, d3])
        db.commit()
        d1_id, d2_id = d1.id, d2.id

    # 2. Create static target set
    static_payload = {
        "name": f"Static_TEH_{uid}",
        "description": "Static pair of Tehran routers",
        "device_ids": [d1_id, d2_id],
        "filter_criteria": {},
    }
    res = client.post("/api/v1/devices/target-sets", json=static_payload, headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 201
    static_id = res.get_json()["id"]

    # 3. Create dynamic target set (query: province = TEH AND role = PE)
    dynamic_payload = {
        "name": f"Dynamic_TEH_PE_{uid}",
        "description": "All PE routers in Tehran",
        "device_ids": [],
        "filter_criteria": {"province": "TEH", "role": "PE"},
    }
    res = client.post("/api/v1/devices/target-sets", json=dynamic_payload, headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 201
    dynamic_id = res.get_json()["id"]

    # 4. Resolve dynamic target set devices
    res = client.get(f"/api/v1/devices/target-sets/{dynamic_id}/devices")
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["count"] >= 2
    dev_names = [d["name"] for d in res_data["devices"]]
    assert f"PE-TEH-{uid}-1" in dev_names
    assert f"PE-TEH-{uid}-2" in dev_names
    assert f"P-ISF-{uid}-1" not in dev_names

    # 5. Update target set
    res = client.put(
        f"/api/v1/devices/target-sets/{dynamic_id}",
        json={"description": "Updated Tehran PE description"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 200
    assert res.get_json()["description"] == "Updated Tehran PE description"

    # 6. Delete static target set
    res = client.delete(f"/api/v1/devices/target-sets/{static_id}", headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 200
    assert res.get_json()["status"] == "deleted"

    # Verify 404 on deleted set
    res = client.get(f"/api/v1/devices/target-sets/{static_id}/devices")
    assert res.status_code == 404
