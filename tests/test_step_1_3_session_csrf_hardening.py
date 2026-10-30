"""Unit tests for Step 1.3: Session & CSRF hardening (F-02, F-03)."""
import os
import json
import time
import tempfile
import pytest
from app import app
import auth


@pytest.fixture
def test_client_and_admin(monkeypatch):
    """Setup clean temporary DATA_DIR with an initial admin user."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "secadmin")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SuperSecurePassword2026!")

        # Initialize users file
        auth._load_users()

        app.config["TESTING"] = True
        client = app.test_client()
        yield client, "secadmin", "SuperSecurePassword2026!"


def test_login_returns_csrf_token_and_sets_cookies(test_client_and_admin):
    """Verify login clears old session, creates new CSRF token, and returns it."""
    client, username, password = test_client_and_admin

    res = client.post("/login", json={"username": username, "password": password})
    assert res.status_code == 200
    data = res.get_json()
    assert "csrf_token" in data
    assert len(data["csrf_token"]) == 64  # 32 hex bytes = 64 chars


def test_me_endpoint_returns_csrf_token(test_client_and_admin):
    """Verify /me returns csrf_token for authenticated sessions."""
    client, username, password = test_client_and_admin
    login_res = client.post("/login", json={"username": username, "password": password})
    csrf = login_res.get_json()["csrf_token"]

    me_res = client.get("/me")
    assert me_res.status_code == 200
    me_data = me_res.get_json()
    assert me_data["authenticated"] is True
    assert me_data["csrf_token"] == csrf


def test_post_without_csrf_header_rejected_403(test_client_and_admin):
    """Verify mutating requests without X-CSRF-Token return 403 CSRF_ERROR."""
    client, username, password = test_client_and_admin
    client.post("/login", json={"username": username, "password": password})

    # Mutating request without X-CSRF-Token header
    res = client.post("/admin/users", json={
        "username": "newuser1",
        "password": "StrongPassword123!",
        "role": "user"
    })
    assert res.status_code == 403
    data = res.get_json()
    assert data["code"] == "CSRF_ERROR"


def test_post_with_invalid_csrf_header_rejected_403(test_client_and_admin):
    """Verify mutating requests with invalid X-CSRF-Token return 403 CSRF_ERROR."""
    client, username, password = test_client_and_admin
    client.post("/login", json={"username": username, "password": password})

    res = client.post(
        "/admin/users",
        json={"username": "newuser1", "password": "StrongPassword123!", "role": "user"},
        headers={"X-CSRF-Token": "bad-token-value"}
    )
    assert res.status_code == 403
    assert res.get_json()["code"] == "CSRF_ERROR"


def test_post_with_unsupported_media_type_rejected_415(test_client_and_admin):
    """Verify JSON endpoints reject non-application/json requests with 415."""
    client, username, password = test_client_and_admin
    login_res = client.post("/login", json={"username": username, "password": password})
    csrf = login_res.get_json()["csrf_token"]

    res = client.post(
        "/admin/users",
        data="username=bad&password=bad",
        headers={"X-CSRF-Token": csrf, "Content-Type": "text/plain"}
    )
    assert res.status_code == 415
    data = res.get_json()
    assert data["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_post_with_malformed_json_rejected_400(test_client_and_admin):
    """Verify malformed JSON payloads return 400 INVALID_JSON."""
    client, username, password = test_client_and_admin
    login_res = client.post("/login", json={"username": username, "password": password})
    csrf = login_res.get_json()["csrf_token"]

    res = client.post(
        "/admin/users",
        data='{"username": "broken',
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"}
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "INVALID_JSON"


def test_successful_mutating_request_with_valid_csrf(test_client_and_admin):
    """Verify mutating requests with valid session & CSRF header succeed."""
    client, username, password = test_client_and_admin
    login_res = client.post("/login", json={"username": username, "password": password})
    csrf = login_res.get_json()["csrf_token"]

    res = client.post(
        "/admin/users",
        json={"username": "newuser2", "password": "StrongPassword123!", "role": "user"},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "created"


def test_user_deleted_invalidates_active_session_401(test_client_and_admin):
    """Verify user deleted in background immediately causes 401 on next request."""
    client, admin_user, admin_pass = test_client_and_admin
    login_admin = client.post("/login", json={"username": admin_user, "password": admin_pass})
    admin_csrf = login_admin.get_json()["csrf_token"]

    # 1. Create operator user
    auth.create_user("operator1", "StrongOperatorPass123!", "user")

    # 2. Operator logs in on a new client
    operator_client = app.test_client()
    op_login = operator_client.post("/login", json={
        "username": "operator1",
        "password": "StrongOperatorPass123!"
    })
    assert op_login.status_code == 200
    op_csrf = op_login.get_json()["csrf_token"]

    # Operator makes a request ok
    check_ok = operator_client.get("/me")
    assert check_ok.status_code == 200

    # 3. Admin deletes operator user
    del_res = client.delete(
        "/admin/users/operator1",
        headers={"X-CSRF-Token": admin_csrf}
    )
    assert del_res.status_code == 200

    # 4. Operator's next request must immediately be 401 USER_NOT_FOUND
    next_req = operator_client.get("/me")
    assert next_req.status_code == 401
    assert next_req.get_json()["code"] == "USER_NOT_FOUND"


def test_user_disabled_invalidates_active_session_401(test_client_and_admin):
    """Verify disabled account immediately causes 401 USER_DISABLED on next request."""
    client, admin_user, admin_pass = test_client_and_admin

    auth.create_user("operator2", "StrongOperatorPass123!", "user")
    operator_client = app.test_client()
    operator_client.post("/login", json={
        "username": "operator2",
        "password": "StrongOperatorPass123!"
    })

    # Disable operator2 in users.json
    auth.update_user("operator2", {"is_active": False})

    next_req = operator_client.get("/me")
    assert next_req.status_code == 401
    assert next_req.get_json()["code"] == "USER_DISABLED"


def test_credential_change_bumps_token_version_invalidating_session_401(test_client_and_admin):
    """Verify password/role change bumps token_version and invalidates old sessions."""
    client, admin_user, admin_pass = test_client_and_admin

    auth.create_user("operator3", "StrongOperatorPass123!", "user")
    operator_client = app.test_client()
    operator_client.post("/login", json={
        "username": "operator3",
        "password": "StrongOperatorPass123!"
    })

    # Admin changes operator3's password or role
    auth.update_user("operator3", {"password": "NewStrongOperatorPass456!"})

    # Old operator session now has obsolete token_version
    next_req = operator_client.get("/me")
    assert next_req.status_code == 401
    assert next_req.get_json()["code"] == "SESSION_INVALIDATED"


def test_idle_timeout_expires_session_401(test_client_and_admin):
    """Verify sessions inactive for > 30 minutes expire with 401 SESSION_EXPIRED."""
    client, admin_user, admin_pass = test_client_and_admin
    client.post("/login", json={"username": admin_user, "password": admin_pass})

    # Fast-forward last_seen to 31 minutes ago in the session cookie
    with client.session_transaction() as sess:
        sess["last_seen"] = time.time() - (31 * 60)

    res = client.get("/me")
    assert res.status_code == 401
    assert res.get_json()["code"] == "SESSION_EXPIRED"


def test_ptp_unauthenticated_stream_and_session_routes_require_login_401():
    """Verify F-91: unauthenticated requests to PTP stream and session return 401."""
    client = app.test_client()

    res_stream = client.get("/ptp/stream/dummy123")
    assert res_stream.status_code == 401

    res_session = client.get("/ptp/session/dummy123")
    assert res_session.status_code == 401
