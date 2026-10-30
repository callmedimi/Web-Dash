"""Unit tests for Step 1.2: Kill the default god/god account (F-01)."""
import os
import json
import tempfile
import pytest
from werkzeug.security import check_password_hash


def test_password_policy_validation():
    """Verify password policy enforces length, username checks, and weak blocklist."""
    import auth

    # Too short (< 12)
    assert auth.validate_password("Short1!", "user1") is not None
    assert "at least 12 characters" in auth.validate_password("12345678901", "user1")

    # In weak list
    assert auth.validate_password("god", "user1") is not None
    assert auth.validate_password("admin", "user1") is not None
    assert auth.validate_password("password", "user1") is not None

    # Contains username
    assert auth.validate_password("operator1SecurePass!", "operator1") is not None
    assert "cannot contain the username" in auth.validate_password("MyUserAdminPass2026!", "useradmin")

    # Valid strong password
    assert auth.validate_password("SuperSecretNetwork2026!#", "nocuser") is None


def test_first_run_bootstrap_default(monkeypatch, capsys):
    """Verify fresh data dir bootstraps 'admin' with random password and must_change_password=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.delenv("INITIAL_ADMIN_USER", raising=False)
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)

        import auth
        users_file = auth._get_users_file()
        assert not os.path.exists(users_file)

        # Loading users triggers bootstrap
        users = auth._load_users()

        # Dimi/god must NOT exist
        assert "Dimi" not in users
        assert auth.authenticate("Dimi", "god") is None

        # admin must exist with role god
        assert "admin" in users
        admin_entry = users["admin"]
        assert admin_entry["role"] == "god"
        assert admin_entry["must_change_password"] is True

        # Check stdout has banner
        captured = capsys.readouterr()
        assert "[BOOTSTRAP] FIRST RUN INITIAL ADMIN ACCOUNT CREATED" in captured.out
        assert "Username: admin" in captured.out


def test_first_run_bootstrap_custom_env(monkeypatch):
    """Verify bootstrap honors INITIAL_ADMIN_USER and INITIAL_ADMIN_PASSWORD."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "customgod")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "CustomStrongPassword2026!")

        import auth
        users = auth._load_users()

        assert "customgod" in users
        assert "admin" not in users
        assert users["customgod"]["role"] == "god"
        assert users["customgod"]["must_change_password"] is False
        assert check_password_hash(users["customgod"]["password"], "CustomStrongPassword2026!")

        # Verify authenticate works
        auth_res = auth.authenticate("customgod", "CustomStrongPassword2026!")
        assert auth_res is not None
        assert auth_res["username"] == "customgod"
        assert auth_res["must_change_password"] is False


def test_create_and_update_user_password_policy(monkeypatch):
    """Verify create_user and update_user enforce password validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        import auth

        # Reject short password
        err = auth.create_user("netadmin", "short", "admin")
        assert err is not None

        # Reject password containing username
        err = auth.create_user("netadmin", "netadminStrong123!", "admin")
        assert err is not None

        # Accept valid password
        err = auth.create_user("netadmin", "StrongNetworkAdmin2026!#", "admin")
        assert err is None

        # Update with weak password rejected
        err = auth.update_user("netadmin", {"password": "weak"})
        assert err is not None

        # Update with strong password succeeds
        err = auth.update_user("netadmin", {"password": "NewStrongNetworkPass2026!"})
        assert err is None


def test_must_change_password_blocks_apis(monkeypatch):
    """Verify must_change_password returns 403 on protected APIs and allows password change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "testadmin")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "TemporaryPass2026!#")

        from app import app
        import auth

        # Set user must_change_password = True
        auth.update_user("testadmin", {"must_change_password": True})

        client = app.test_client()

        # Log in
        login_res = client.post("/login", json={
            "username": "testadmin",
            "password": "TemporaryPass2026!#"
        })
        assert login_res.status_code == 200
        assert login_res.json["must_change_password"] is True

        # /me should be allowed
        me_res = client.get("/me")
        assert me_res.status_code == 200
        assert me_res.json["must_change_password"] is True

        # /admin/users should be blocked with 403 PASSWORD_CHANGE_REQUIRED
        users_res = client.get("/admin/users")
        assert users_res.status_code == 403
        assert users_res.json["code"] == "PASSWORD_CHANGE_REQUIRED"

        # Change password to a weak password -> fails
        weak_change_res = client.post("/change-password", json={
            "current_password": "TemporaryPass2026!#",
            "new_password": "short"
        })
        assert weak_change_res.status_code == 400

        # Change password to a strong password -> succeeds
        valid_change_res = client.post("/change-password", json={
            "current_password": "TemporaryPass2026!#",
            "new_password": "BrandNewPermanentPassword2026!#"
        })
        assert valid_change_res.status_code == 200
        assert valid_change_res.json["status"] == "password_changed"

        # /admin/users is now unblocked
        users_res2 = client.get("/admin/users")
        assert users_res2.status_code == 200
