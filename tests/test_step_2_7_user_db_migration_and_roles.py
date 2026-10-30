"""Unit tests for Step 2.7: User Model to DB Migration and Roles (god, admin, operator, viewer)."""
import os
import json
import tempfile
import pytest
from app import app
from backend.app.extensions import get_db_session
from backend.app.models.user import User, Permission
from backend.app.db.migrate_files import migrate_users_from_json
import auth


@pytest.fixture
def auth_test_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USER", "supergod")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SuperGodPass1234!")

    app.config["TESTING"] = True
    auth.clear_all_rate_limits()
    auth._load_users()

    with app.test_client() as client:
        yield client, str(data_dir)


def test_user_json_to_db_migration_idempotent(auth_test_env):
    """Verify that users.json migrations to DB are idempotent and preserve credentials."""
    client, data_dir = auth_test_env

    # Create additional users in users.json
    auth.create_user("operator_one", "OperatorPassword123!", "operator", display_name="Operator 1")
    auth.create_user("viewer_one", "ViewerPassword1234!", "viewer", display_name="Viewer 1")

    # Run migration into DB
    with get_db_session() as s:
        migrated_count = migrate_users_from_json(s)
        assert migrated_count >= 3

        # Check DB User entries
        users = s.query(User).all()
        user_map = {u.username: u for u in users}
        assert "supergod" in user_map
        assert "operator_one" in user_map
        assert "viewer_one" in user_map

        assert user_map["supergod"].role == "god"
        assert user_map["operator_one"].role == "operator"
        assert user_map["viewer_one"].role == "viewer"

        # Check idempotency: second run shouldn't duplicate or fail
        second_run_count = migrate_users_from_json(s)
        assert second_run_count >= 3
        assert s.query(User).count() == len(users)


def test_viewer_role_access_restrictions():
    """Verify viewer role is strictly restricted to read-only features."""
    viewer_info = {
        "username": "viewer_alice",
        "role": "viewer",
        "permissions": {},
    }

    # Allowed read-only features
    assert auth.user_has_access(viewer_info, "reporting") is True
    assert auth.user_has_access(viewer_info, "vrf_routing") is True
    assert auth.user_has_access(viewer_info, "zabbix_search") is True
    assert auth.user_has_access(viewer_info, "code_site_search") is True
    assert auth.user_has_access(viewer_info, "session_extractor") is True

    # Forbidden mutating features
    assert auth.user_has_access(viewer_info, "alarm_clear_manual") is False
    assert auth.user_has_access(viewer_info, "alarm_clear_bulk") is False
    assert auth.user_has_access(viewer_info, "user_management") is False
    assert auth.user_has_access(viewer_info, "permission_management") is False
    assert auth.user_has_access(viewer_info, "zabbix_db_refresh") is False
    assert auth.user_has_access(viewer_info, "license_renewal_admin") is False


def test_god_and_admin_and_operator_role_access():
    """Verify god, admin, and operator roles have expected permissions."""
    god_info = {"username": "god_user", "role": "god", "permissions": {}}
    assert auth.user_has_access(god_info, "user_management") is True
    assert auth.user_has_access(god_info, "alarm_clear_bulk") is True

    admin_info = {"username": "admin_user", "role": "admin", "permissions": {}}
    assert auth.user_has_access(admin_info, "alarm_clear_bulk") is True
    assert auth.user_has_access(admin_info, "user_management") is False

    operator_info = {"username": "op_user", "role": "operator", "permissions": {}}
    assert auth.user_has_access(operator_info, "alarm_clear_bulk") is True
    assert auth.user_has_access(operator_info, "user_management") is False


def test_db_user_sync_on_create_update_delete(auth_test_env):
    """Verify auth CRUD operations stay synchronized with relational database."""
    client, data_dir = auth_test_env

    # 1. Create user
    auth.create_user("sync_test_user", "SyncPassword1234!", "operator", display_name="Sync Test")
    with get_db_session() as s:
        db_u = s.query(User).filter_by(username="sync_test_user").first()
        assert db_u is not None
        assert db_u.display_name == "Sync Test"
        assert db_u.role == "operator"

    # 2. Update user
    auth.update_user("sync_test_user", {"display_name": "Updated Sync Test", "role": "viewer"})
    with get_db_session() as s:
        db_u2 = s.query(User).filter_by(username="sync_test_user").first()
        assert db_u2.display_name == "Updated Sync Test"
        assert db_u2.role == "viewer"

    # 3. Delete user
    auth.delete_user("sync_test_user")
    with get_db_session() as s:
        db_u3 = s.query(User).filter_by(username="sync_test_user").first()
        assert db_u3 is None
