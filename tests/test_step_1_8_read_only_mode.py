"""Unit tests for Step 1.8: Safety net, kill-switch & read-only mode (READ_ONLY_MODE)."""
import os
import pytest
from app import app
import auth
from settings import is_read_only_mode


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "InitialAdminPassword123!")

    auth.clear_all_rate_limits()
    auth._load_users()

    u = auth.get_user("admin")
    if not u:
        auth.create_user("admin", "InitialAdminPassword123!", role="god")
    auth.update_user("admin", {"password": "InitialAdminPassword123!", "must_change_password": False, "is_active": True})

    with app.test_client() as c:
        yield c


def login_admin(client):
    auth.clear_all_rate_limits()
    res = client.post("/login", json={"username": "admin", "password": "InitialAdminPassword123!"})
    assert res.status_code == 200
    me = client.get("/me").get_json()
    return me.get("csrf_token")


def test_default_read_only_mode_is_false(monkeypatch):
    """By default, READ_ONLY_MODE is False."""
    monkeypatch.delenv("READ_ONLY_MODE", raising=False)
    assert is_read_only_mode() is False


def test_read_only_mode_env_flag(monkeypatch):
    """Setting READ_ONLY_MODE to true, 1, or yes activates read-only mode."""
    for val in ("true", "1", "yes", "True", "YES"):
        monkeypatch.setenv("READ_ONLY_MODE", val)
        assert is_read_only_mode() is True

    for val in ("false", "0", "no", "False"):
        monkeypatch.setenv("READ_ONLY_MODE", val)
        assert is_read_only_mode() is False


def test_me_endpoint_returns_read_only_flag(client, monkeypatch):
    """The /me and /login endpoints reflect the current read_only flag."""
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    res = client.get("/me")
    assert res.status_code == 200
    assert res.get_json()["read_only"] is True

    csrf = login_admin(client)
    res_me = client.get("/me")
    assert res_me.status_code == 200
    assert res_me.get_json()["read_only"] is True


def test_mutating_routes_blocked_in_read_only_mode(client, monkeypatch):
    """When READ_ONLY_MODE=true, mutating routes return 403 READ_ONLY."""
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    csrf = login_admin(client)
    headers = {"X-CSRF-Token": csrf}

    # /run-manual
    res_manual = client.post(
        "/run-manual",
        headers=headers,
        json={"username": "u", "password": "p", "routers": [{"name": "R1", "host": "10.0.0.1"}]},
    )
    assert res_manual.status_code == 403
    data = res_manual.get_json()
    assert data["code"] == "READ_ONLY"
    assert data["error"]["code"] == "READ_ONLY"

    # /run-bulk
    res_bulk = client.post(
        "/run-bulk",
        headers=headers,
        json={"username": "u", "password": "p", "routers": [{"name": "R1", "host": "10.0.0.1"}]},
    )
    assert res_bulk.status_code == 403
    assert res_bulk.get_json()["code"] == "READ_ONLY"

    # /start-renewal
    res_renewal = client.post(
        "/start-renewal",
        headers=headers,
        json={"username": "u", "password": "p", "selected_routers": [{"name": "R1", "host": "10.0.0.1"}]},
    )
    assert res_renewal.status_code == 403
    assert res_renewal.get_json()["code"] == "READ_ONLY"

    # /confirm-renewal/<sid>
    res_confirm = client.post(
        "/confirm-renewal/test_sid",
        headers=headers,
        json={"confirmation_id": "c1", "action": "proceed"},
    )
    assert res_confirm.status_code == 403
    assert res_confirm.get_json()["code"] == "READ_ONLY"


def test_read_only_routes_still_work_in_read_only_mode(client, monkeypatch):
    """When READ_ONLY_MODE=true, diagnostic and reporting routes still work."""
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    csrf = login_admin(client)
    headers = {"X-CSRF-Token": csrf}

    # /run-report is read-only -> does not return 403 READ_ONLY
    res_report = client.post(
        "/run-report",
        headers=headers,
        json={
            "username": "u",
            "password": "p",
            "province": "TEH",
            "age_value": 2,
            "routers": [{"name": "R1_TEH", "host": "10.0.0.1"}],
        },
    )
    # It starts report job -> returns 200
    assert res_report.status_code == 200
    assert "session_id" in res_report.get_json()

    # /run-license-check is diagnostic read-only -> returns 200
    res_lic = client.post(
        "/run-license-check",
        headers=headers,
        json={"username": "u", "password": "p", "routers": [{"name": "R1", "host": "10.0.0.1"}]},
    )
    assert res_lic.status_code == 200
    assert "session_id" in res_lic.get_json()
