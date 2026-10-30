"""Unit tests for Step 1.5: Validate user management input (F-07)."""
import os
import tempfile
import pytest
from app import app
import auth


@pytest.fixture
def clean_env_client(monkeypatch):
    """Setup temporary DATA_DIR with fresh admin credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "godadmin")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SuperSecurePassword2026!")

        auth.clear_all_rate_limits()
        auth._load_users()

        app.config["TESTING"] = True
        client = app.test_client()
        yield client, "godadmin", "SuperSecurePassword2026!"


def test_update_user_does_not_mutate_caller_dict():
    """Verify auth.update_user does not mutate the passed dictionary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DATA_DIR"] = tmpdir
        auth.create_user("testrunner", "ValidPassword123!", "user")

        input_dict = {
            "display_name": "New Name",
            "password": "NewStrongPass999!",
            "is_active": True,
            "custom_metadata": {"some": "value"}
        }
        original_dict_copy = dict(input_dict)

        auth.update_user("testrunner", input_dict)

        # input_dict must remain identical
        assert input_dict == original_dict_copy


def test_update_user_whitelists_allowed_keys(clean_env_client):
    """Verify only whitelisted keys (role, display_name, password, is_active) are saved."""
    client, admin_user, admin_pass = clean_env_client

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    auth.create_user("operator_wl", "ValidPassword123!", "user")

    # Send payload with unwhitelisted keys
    res = client.put(
        "/admin/users/operator_wl",
        json={
            "display_name": "Whitelisted Name",
            "is_superuser": True,
            "backdoor": "enabled",
            "role": "admin"
        },
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 200

    user_record = auth.get_user("operator_wl")
    assert user_record["display_name"] == "Whitelisted Name"
    assert user_record["role"] == "admin"
    assert "is_superuser" not in user_record
    assert "backdoor" not in user_record


def test_update_user_invalid_role_rejected_400(clean_env_client):
    """Verify updating a user with an invalid role returns 400 VALIDATION_ERROR."""
    client, admin_user, admin_pass = clean_env_client

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    auth.create_user("operator_role", "ValidPassword123!", "user")

    res = client.put(
        "/admin/users/operator_role",
        json={"role": "supergod"},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 400
    assert res.get_json()["code"] == "VALIDATION_ERROR"


def test_cannot_demote_or_disable_last_god_user(clean_env_client):
    """Verify the last remaining active god user cannot be demoted or deactivated."""
    client, admin_user, admin_pass = clean_env_client

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    # 1. Attempt to demote the sole god user
    demote_res = client.put(
        f"/admin/users/{admin_user}",
        json={"role": "admin"},
        headers={"X-CSRF-Token": csrf}
    )
    # Either blocked by self-role protection (403) or last-god protection (400)
    assert demote_res.status_code in (400, 403)

    # Direct auth layer check for last god demotion
    demote_err = auth.update_user(admin_user, {"role": "admin"})
    assert "Cannot demote the last god user" in demote_err

    # 2. Attempt to disable the sole god user
    disable_res = client.put(
        f"/admin/users/{admin_user}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf}
    )
    assert disable_res.status_code == 400
    assert "Cannot disable the last god user" in disable_res.get_json()["error"]

    # Direct auth layer check for last god disabling
    disable_err = auth.update_user(admin_user, {"is_active": False})
    assert "Cannot disable the last god user" in disable_err


def test_demote_god_allowed_when_another_active_god_exists(clean_env_client):
    """Verify demoting a god user is permitted if a second active god exists."""
    client, admin_user, admin_pass = clean_env_client

    # Create second god user
    auth.create_user("secondgod", "SuperSecureSecondPassword2026!", "god")

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    # Demote second god user
    demote_res = client.put(
        "/admin/users/secondgod",
        json={"role": "admin"},
        headers={"X-CSRF-Token": csrf}
    )
    assert demote_res.status_code == 200
    assert auth.get_user("secondgod")["role"] == "admin"


def test_set_permissions_validates_feature_names_and_boolean_types(clean_env_client):
    """Verify admin_set_permissions enforces DEFAULT_FEATURES and boolean values."""
    client, admin_user, admin_pass = clean_env_client

    login_res = client.post("/login", json={"username": admin_user, "password": admin_pass})
    csrf = login_res.get_json()["csrf_token"]

    auth.create_user("perm_user", "ValidPassword123!", "user")

    # 1. Unknown feature name -> 400
    bad_feat_res = client.put(
        "/admin/permissions/perm_user",
        json={"permissions": {"super_root_hack": True}},
        headers={"X-CSRF-Token": csrf}
    )
    assert bad_feat_res.status_code == 400
    assert "Invalid feature" in bad_feat_res.get_json()["error"]

    # 2. Non-boolean permission value -> 400
    bad_val_res = client.put(
        "/admin/permissions/perm_user",
        json={"permissions": {"alarm_clear_manual": "yes"}},
        headers={"X-CSRF-Token": csrf}
    )
    assert bad_val_res.status_code == 400
    assert "must be a boolean" in bad_val_res.get_json()["error"]

    # 3. Valid permissions dict -> 200
    good_res = client.put(
        "/admin/permissions/perm_user",
        json={"permissions": {"alarm_clear_manual": False, "reporting": True}},
        headers={"X-CSRF-Token": csrf}
    )
    assert good_res.status_code == 200

    perms = auth.get_user("perm_user")["permissions"]
    assert perms["alarm_clear_manual"] is False
    assert perms["reporting"] is True
