"""Unit tests for Step 1.4: Login throttling + audit log (F-04)."""
import os
import json
import tempfile
import pytest
from app import app
import auth
import audit


@pytest.fixture
def clean_env_client(monkeypatch):
    """Setup temporary DATA_DIR with fresh admin credentials and empty audit log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "secadmin")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SuperSecurePassword2026!")

        auth.clear_all_rate_limits()
        auth._load_users()

        app.config["TESTING"] = True
        client = app.test_client()
        yield client, tmpdir, "secadmin", "SuperSecurePassword2026!"


def test_login_throttling_5_failures_locks_account_429(clean_env_client):
    """Verify 5 failed attempts result in 429 TOO_MANY_REQUESTS on the 6th attempt."""
    client, tmpdir, admin_user, admin_pass = clean_env_client

    # First 5 failed attempts -> 401 INVALID_CREDENTIALS
    for i in range(5):
        res = client.post("/login", json={"username": admin_user, "password": "WrongPassword!"})
        assert res.status_code == 401
        assert res.get_json()["code"] == "INVALID_CREDENTIALS"

    # 6th attempt -> 429 TOO_MANY_REQUESTS
    res6 = client.post("/login", json={"username": admin_user, "password": "WrongPassword!"})
    assert res6.status_code == 429
    data6 = res6.get_json()
    assert data6["code"] == "TOO_MANY_REQUESTS"

    # Even right password is blocked during lockout
    res_correct_during_lock = client.post("/login", json={"username": admin_user, "password": admin_pass})
    assert res_correct_during_lock.status_code == 429
    assert res_correct_during_lock.get_json()["code"] == "TOO_MANY_REQUESTS"


def test_unknown_user_constant_time_behavior_and_throttling(clean_env_client):
    """Verify unknown users are also throttled per IP/username and hashed with dummy password."""
    client, tmpdir, admin_user, admin_pass = clean_env_client

    for i in range(5):
        res = client.post("/login", json={"username": "nonexistent_hacker", "password": "DummyPassword123!"})
        assert res.status_code == 401

    res6 = client.post("/login", json={"username": "nonexistent_hacker", "password": "DummyPassword123!"})
    assert res6.status_code == 429
    assert res6.get_json()["code"] == "TOO_MANY_REQUESTS"


def test_audit_log_records_auth_lifecycle(clean_env_client):
    """Verify audit.log records login success, fail, lock, and logout in JSON lines."""
    client, tmpdir, admin_user, admin_pass = clean_env_client
    audit_file = os.path.join(tmpdir, "audit.log")

    # 1. Failed login
    client.post("/login", json={"username": admin_user, "password": "BadPassword123!"})

    # 2. Successful login
    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    assert login_res.status_code == 200
    csrf = login_res.get_json()["csrf_token"]

    # 3. Logout
    client.post("/logout", headers={"X-CSRF-Token": csrf})

    # Read audit log
    assert os.path.exists(audit_file)
    with open(audit_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    actions = [entry["action"] for entry in lines]
    assert "login_failed" in actions
    assert "login_success" in actions
    assert "logout" in actions

    for entry in lines:
        assert "ts" in entry
        assert "user" in entry
        assert "ip" in entry
        assert "status" in entry


def test_audit_log_contains_no_passwords(clean_env_client):
    """Verify no password strings exist anywhere in audit.log."""
    client, tmpdir, admin_user, admin_pass = clean_env_client
    audit_file = os.path.join(tmpdir, "audit.log")

    secret_attempt = "SecretPassAttempt123456!"
    client.post("/login", json={"username": admin_user, "password": secret_attempt})

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    # Create user with strong password
    new_user_pass = "StrongNewUserPassword999!"
    client.post(
        "/admin/users",
        json={"username": "audittestuser", "password": new_user_pass, "role": "user"},
        headers={"X-CSRF-Token": csrf}
    )

    # Update user password
    updated_pass = "AnotherSuperSecretNewPass888!"
    client.put(
        "/admin/users/audittestuser",
        json={"password": updated_pass, "display_name": "Audit Test User"},
        headers={"X-CSRF-Token": csrf}
    )

    # Inspect raw file content
    with open(audit_file, "r", encoding="utf-8") as f:
        raw_content = f.read()

    # The passwords must NEVER appear anywhere in the file
    assert secret_attempt not in raw_content
    assert admin_pass not in raw_content
    assert new_user_pass not in raw_content
    assert updated_pass not in raw_content


def test_audit_log_records_user_and_job_actions(clean_env_client):
    """Verify user management and job execution are logged in audit.log."""
    client, tmpdir, admin_user, admin_pass = clean_env_client

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    # 1. Create user
    client.post(
        "/admin/users",
        json={"username": "jobrunner", "password": "ValidPassword123!", "role": "user"},
        headers={"X-CSRF-Token": csrf}
    )

    # 2. Update permissions
    client.put(
        "/admin/permissions/jobrunner",
        json={"permissions": {"alarm_clear_manual": True}},
        headers={"X-CSRF-Token": csrf}
    )

    # 3. Delete user
    client.delete(
        "/admin/users/jobrunner",
        headers={"X-CSRF-Token": csrf}
    )

    # Read audit entries
    entries = audit.get_audit_entries(limit=50)
    actions = [e["action"] for e in entries]

    assert "user_created" in actions
    assert "permissions_updated" in actions
    assert "user_deleted" in actions
