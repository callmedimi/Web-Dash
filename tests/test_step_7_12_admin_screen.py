"""Integration and Acceptance tests for Step 9.12: System Administration Screen.
Tests Users & RBAC, Credential Vault, System Telemetry, Maintenance Kill-Switch, and Audit Log CSV Export.
"""
import os
import pytest
import uuid
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.user import User


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"webdash_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WEBDASH_DB_URL", db_url)
    monkeypatch.setenv("WEBDASH_SECRET_KEY", "test-secret-phase7-step12")
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="superadmin", role="god"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {
                "user_management": True if role in ("god", "admin") else False,
                "permission_management": True if role in ("god", "admin") else False,
                "admin_schedule_manage": True if role in ("god", "admin") else False,
                "admin": True if role in ("god", "admin") else False,
            },
            "display_name": username.title(),
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_admin_rbac_isolation(client):
    # 1. Anonymous access is blocked
    resp_anon = client.get("/admin/users")
    assert resp_anon.status_code == 401

    # 2. Operator/Viewer access to /admin/users is forbidden (403)
    _login(client, username="shift_viewer", role="viewer")
    resp_viewer = client.get("/admin/users")
    assert resp_viewer.status_code == 403

    resp_viewer_audit = client.get("/admin/audit-log")
    assert resp_viewer_audit.status_code == 403


def test_admin_user_and_permissions_lifecycle(client):
    _login(client, username="superadmin", role="god")

    # 1. Query users list
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "users" in data

    # 2. Create new operator user
    new_user = f"oper_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "username": new_user,
        "password": "SecurePassword123#",
        "role": "operator",
        "display_name": "Test Shift Operator",
    }
    resp_create = client.post(
        "/admin/users",
        json=create_payload,
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_create.status_code in (200, 201)

    # 3. Update user role and display name
    resp_update = client.put(
        f"/admin/users/{new_user}",
        json={"display_name": "Updated Shift Operator", "role": "operator"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_update.status_code == 200

    # 4. Get permissions matrix
    resp_perms = client.get("/admin/permissions")
    assert resp_perms.status_code == 200
    perms_data = resp_perms.get_json()
    assert "users" in perms_data

    # 5. Set permission for user
    resp_set_perm = client.put(
        f"/admin/permissions/{new_user}",
        json={"permissions": {"alarm_clear_manual": True, "vrf_routing": True}},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_set_perm.status_code == 200


def test_admin_credentials_vault_profiles(client):
    _login(client, username="superadmin", role="god")

    # 1. Create a credential profile
    cred_payload = {
        "name": f"Core-SSH-{uuid.uuid4().hex[:4]}",
        "username": "noc_operator",
        "password": "SecretSuperPassword99#",
        "cred_type": "ssh",
    }
    resp_create = client.post(
        "/api/v1/credentials",
        json=cred_payload,
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_create.status_code in (200, 201)
    res_json = resp_create.get_json()
    cred_id = res_json["id"] if "id" in res_json else res_json["credential"]["id"]

    # 2. List credentials - confirm secret is NEVER returned
    resp_list = client.get("/api/v1/credentials")
    assert resp_list.status_code == 200
    creds = resp_list.get_json()["credentials"]
    found = next((c for c in creds if c["id"] == cred_id), None)
    assert found is not None
    assert "password" not in found
    assert "secret" not in found

    # 3. Rotate credential secret
    resp_rotate = client.put(
        f"/api/v1/credentials/{cred_id}",
        json={"password": "RotatedPassword123#"},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_rotate.status_code == 200


def test_admin_system_info_and_maintenance_mode(client):
    _login(client, username="superadmin", role="god")

    # 1. Query System info
    resp_sys = client.get("/admin/system/info")
    assert resp_sys.status_code == 200
    sys_data = resp_sys.get_json()
    assert sys_data["version"] == "2.0.0"
    assert "read_only" in sys_data
    assert "workers" in sys_data

    # 2. Toggle maintenance mode
    resp_toggle = client.post(
        "/admin/system/toggle-maintenance",
        json={},
        headers={"X-CSRF-Token": "valid_csrf"},
    )
    assert resp_toggle.status_code == 200
    new_state = resp_toggle.get_json()["read_only"]

    # 3. Query audit log - confirm maintenance toggle event is recorded
    resp_audit = client.get("/admin/audit-log")
    assert resp_audit.status_code == 200
    entries = resp_audit.get_json()["entries"]
    assert any("maintenance" in e.get("action", "") for e in entries)

    # 4. Download audit log CSV export
    resp_export = client.get("/admin/audit-log/export")
    assert resp_export.status_code == 200
    assert "text/csv" in resp_export.content_type
    assert b"timestamp,action,user,ip_address,status,detail" in resp_export.data

    # Revert maintenance mode
    if new_state:
        client.post(
            "/admin/system/toggle-maintenance",
            json={},
            headers={"X-CSRF-Token": "valid_csrf"},
        )
