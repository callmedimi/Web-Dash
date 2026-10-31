"""Tests for Step 9.6: Safe Changes Planner Backend APIs and Dual-Custody Approval."""
import pytest
import uuid
from backend.app import create_app
from backend.app.models.device import Device
from backend.app.models.config_change import ChangeRequest
from backend.app.extensions import get_db_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"test_changes_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="requester_user", role="operator"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {"changes": True, "admin": True},
            "display_name": username,
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_changes_unauthenticated(client):
    res = client.get("/api/v1/changes")
    assert res.status_code == 401


def test_change_pipeline_lifecycle_and_dual_custody(client):
    # 1. Seed target router
    with get_db_session() as db:
        dev = Device(name="PE-TEH-CHANGE-01", mgmt_ip="10.220.1.1", province="TEH", role="PE", enabled=True)
        db.add(dev)
        db.commit()
        dev_id = dev.id

    # 2. Requester creates change plan
    _login(client, username="requester_user", role="admin")
    plan_payload = {
        "device_id": dev_id,
        "lines": ["interface GigabitEthernet0/1/0", "shutdown", "quit"],
        "inverse_lines": ["interface GigabitEthernet0/1/0", "undo shutdown", "quit"],
        "reason": "Shut down optical link flapping",
        "risk_level": "medium",
    }
    res = client.post("/api/v1/changes/plan", json=plan_payload, headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 201
    change_data = res.get_json()
    change_id = change_data["id"]
    assert change_data["creator_id"] == "requester_user"
    assert change_data["status"] == "planned"

    # 3. Run Pre-check
    res = client.post(f"/api/v1/changes/{change_id}/precheck", headers={"X-CSRF-Token": "valid_csrf"})
    assert res.status_code == 200
    assert res.get_json()["passed"] is True

    # 4. Requester attempts to approve their OWN change -> Must Fail (Separation of Duties / Dual Custody)
    res = client.post(
        f"/api/v1/changes/{change_id}/approve",
        json={"confirmation": "APPROVED"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 403
    assert "SEPARATION_OF_DUTIES" in res.get_json().get("error", "")

    # 5. Distinct Senior Operator logs in and approves change
    _login(client, username="distinct_approver", role="admin")
    res = client.post(
        f"/api/v1/changes/{change_id}/approve",
        json={"confirmation": "APPROVED"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res.status_code == 200
    approved_data = res.get_json()
    assert approved_data["status"] == "approved"
    assert approved_data["change"]["approver_id"] == "distinct_approver"

    # 6. Reject endpoint test on a separate change
    plan_payload_2 = {
        "device_id": dev_id,
        "lines": ["interface GigabitEthernet0/1/2", "shutdown"],
        "reason": "Test rejection",
    }
    res2 = client.post("/api/v1/changes/plan", json=plan_payload_2, headers={"X-CSRF-Token": "valid_csrf"})
    assert res2.status_code == 201
    change_id_2 = res2.get_json()["id"]

    res_reject = client.post(
        f"/api/v1/changes/{change_id_2}/reject",
        json={"reason": "Rejected by manager"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert res_reject.status_code == 200
    assert res_reject.get_json()["status"] == "rejected"
