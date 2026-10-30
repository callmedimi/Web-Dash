"""Phase 1 Regression Pass and Smoke Tests (Step 1.9, 11_TESTING_ACCEPTANCE.md §2)."""
import os
import json
import pytest
from app import app
import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USER", "secadmin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SuperSecurePassword2026!")

    auth.clear_all_rate_limits()
    auth._load_users()

    with app.test_client() as c:
        yield c


def login(client, username="secadmin", password="SuperSecurePassword2026!"):
    auth.clear_all_rate_limits()
    res = client.post("/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return res.get_json()["csrf_token"]


def test_healthz_and_readyz_probes(client):
    """Verify /healthz and /readyz observability endpoints return 200 OK."""
    # Liveness
    res_h = client.get("/healthz")
    assert res_h.status_code == 200
    assert res_h.get_json()["status"] == "ok"

    # Readiness
    res_r = client.get("/readyz")
    assert res_r.status_code == 200
    data_r = res_r.get_json()
    assert data_r["status"] == "ready"
    assert "data_dir" in data_r


def test_phase1_security_full_flow(client):
    """Smoke test of complete Phase 1 security pipeline."""
    # 1. Unauthenticated request without CSRF rejected
    res = client.post("/admin/users", json={"username": "attacker", "password": "WeakPassword1!"})
    assert res.status_code in (401, 403)

    # 2. Login as admin
    csrf = login(client)
    assert csrf is not None

    # 3. Create normal user with compliant password
    res_create = client.post(
        "/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "operator1",
            "password": "StrongPassword2026!",
            "role": "user",
            "display_name": "Operator One",
        },
    )
    assert res_create.status_code in (200, 201)

    # 4. Input validation: rejecting CLI injection in router target
    res_inject = client.post(
        "/check-bgp-route",
        headers={"X-CSRF-Token": csrf},
        json={"username": "u", "password": "p", "target_ip": "10.0.0.1; rm -rf /"},
    )
    assert res_inject.status_code == 400
    assert res_inject.get_json()["code"] == "VALIDATION_ERROR"

    # 5. Mass-assignment whitelist test: unknown fields rejected/ignored
    res_update = client.put(
        "/admin/users/operator1",
        headers={"X-CSRF-Token": csrf},
        json={"role": "user", "display_name": "Updated Operator", "is_hacked": True},
    )
    assert res_update.status_code == 200
    u = auth.get_user("operator1")
    assert "is_hacked" not in u

    # 6. Safety Net / Read-Only Mode test
    os.environ["READ_ONLY_MODE"] = "true"
    try:
        res_blocked = client.post(
            "/run-manual",
            headers={"X-CSRF-Token": csrf},
            json={"username": "u", "password": "p", "routers": [{"name": "R1", "host": "10.0.0.1"}]},
        )
        assert res_blocked.status_code == 403
        assert res_blocked.get_json()["code"] == "READ_ONLY"

        # Diagnostic report still permitted in read-only mode
        res_report = client.post(
            "/run-report",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": "u",
                "password": "p",
                "province": "TEH",
                "age_value": 2,
                "routers": [{"name": "R1_TEH", "host": "10.0.0.1"}],
            },
        )
        assert res_report.status_code == 200
    finally:
        os.environ.pop("READ_ONLY_MODE", None)
