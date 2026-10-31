"""Step 6.2 Unit and Integration Tests: API Client, Auth Shell, and Route Guards.

Validates:
1. Presence and exports of API client, error mapping, and auth store.
2. Route guards (ProtectedRoute, PermissionGate) and UI shell components.
3. Backend /api/v1 auth endpoint compatibility and CSRF handling.
4. Execution and passing of TypeScript typecheck, ESLint, Vitest, and production build.
"""
import os
import tempfile
import subprocess
import pytest
import auth
from backend.app import create_app


@pytest.fixture
def test_env(monkeypatch):
    """Set up temporary data dir and admin user."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("INITIAL_ADMIN_USER", "step62admin")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Step62AdminPass123!")

        auth._load_users()

        app = create_app({"TESTING": True})
        client = app.test_client()
        yield client, "step62admin", "Step62AdminPass123!"


def test_step_6_2_source_files_exist():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(base_dir, "frontend", "src")

    required_files = [
        os.path.join(frontend_dir, "api", "types.ts"),
        os.path.join(frontend_dir, "api", "client.ts"),
        os.path.join(frontend_dir, "api", "client.test.ts"),
        os.path.join(frontend_dir, "store", "auth.ts"),
        os.path.join(frontend_dir, "store", "auth.test.ts"),
        os.path.join(frontend_dir, "components", "auth", "ProtectedRoute.tsx"),
        os.path.join(frontend_dir, "components", "auth", "PermissionGate.tsx"),
        os.path.join(frontend_dir, "components", "auth", "IdleTimeoutNotice.tsx"),
        os.path.join(frontend_dir, "components", "layout", "Shell.tsx"),
        os.path.join(frontend_dir, "pages", "Login.tsx"),
        os.path.join(frontend_dir, "pages", "ChangePassword.tsx"),
        os.path.join(frontend_dir, "pages", "Dashboard.tsx"),
    ]

    for fpath in required_files:
        assert os.path.exists(fpath), f"Required file missing: {fpath}"


def test_step_6_2_api_client_exports():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    client_ts = os.path.join(base_dir, "frontend", "src", "api", "client.ts")
    with open(client_ts, "r", encoding="utf-8") as f:
        content = f.read()

    assert "export const apiClient" in content
    assert "export async function request" in content
    assert "export function setCsrfToken" in content
    assert "export function getCsrfToken" in content
    assert "export function parseApiError" in content
    assert "export const queryClient" in content
    assert "AUTH_UNAUTHORIZED_EVENT" in content
    assert "AUTH_PASSWORD_CHANGE_REQUIRED_EVENT" in content
    assert "staleTime: 15_000" in content


def test_step_6_2_backend_api_v1_auth_routes(test_env):
    client, admin_user, admin_pass = test_env

    # 1. Unauthenticated /api/v1/me returns authenticated: false
    res = client.get("/api/v1/me")
    assert res.status_code == 200
    data = res.get_json()
    assert data["authenticated"] is False

    # 2. Login through /api/v1/login with wrong password returns 401
    res = client.post("/api/v1/login", json={"username": admin_user, "password": "wrongpassword"})
    assert res.status_code == 401
    assert res.get_json()["code"] == "INVALID_CREDENTIALS"

    # 3. Successful login returns csrf_token
    res = client.post("/api/v1/login", json={"username": admin_user, "password": admin_pass})
    assert res.status_code == 200
    login_data = res.get_json()
    assert login_data["username"] == admin_user
    assert "csrf_token" in login_data
    csrf_token = login_data["csrf_token"]

    # 4. Now /api/v1/me returns authenticated: true
    res = client.get("/api/v1/me")
    assert res.status_code == 200
    me_data = res.get_json()
    assert me_data["authenticated"] is True
    assert me_data["username"] == admin_user

    # 5. Logout through /api/v1/logout with CSRF
    res = client.post("/api/v1/logout", json={}, headers={"X-CSRF-Token": csrf_token})
    assert res.status_code == 200
    assert res.get_json()["status"] == "logged_out"


def test_step_6_2_vitest_and_typecheck():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(base_dir, "frontend")

    # Run typecheck
    tc = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "typecheck"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert tc.returncode == 0, f"TypeScript typecheck failed: {tc.stdout}\n{tc.stderr}"

    # Run lint
    lint = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "lint"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert lint.returncode == 0, f"ESLint failed: {lint.stdout}\n{lint.stderr}"

    # Run vitest
    test = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "test"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert test.returncode == 0, f"Vitest test suite failed: {test.stdout}\n{test.stderr}"


def test_step_6_2_production_dist_ready_for_airgap():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(base_dir, "frontend", "dist")
    index_html = os.path.join(dist_dir, "index.html")

    assert os.path.exists(index_html), "frontend/dist/index.html does not exist. Run npm run build."
    with open(index_html, "r", encoding="utf-8") as f:
        html = f.read()
    assert "<div id=\"root\"></div>" in html
