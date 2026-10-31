"""Comprehensive tests for Phase 5 Step 5.14: Public API, Scoped Tokens, OpenAPI Spec & CLI."""
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.models.api_token import ApiToken
from backend.app.services.tokens import ApiTokenService, hash_token
from backend.app.api.openapi_spec import OPENAPI_SPEC
from backend.app import create_app
from scripts.webdash_cli import WebDashCliClient, format_table, main as cli_main


@pytest.fixture
def test_db_session(tmp_path, monkeypatch):
    """Provide a fresh SQLite test session."""
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    db_file = tmp_path / "test_public_api.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    admin = User(username="admin_api", role="admin", password_hash="dummy_hash")
    session.add(admin)
    session.commit()

    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client with test configuration."""
    db_file = tmp_path / "test_app_public_api.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_api", role="admin", password_hash="dummy_hash")
            s.add(admin)
            dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
            s.add(dev1)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_api",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_api_token_generation_and_hashing(test_db_session):
    """Verify API token creation produces wbd_ prefix, stores SHA-256 hash in DB, and returns plaintext secret once."""
    admin = test_db_session.query(User).filter(User.username == "admin_api").first()

    token_info, raw_secret = ApiTokenService.create_token(
        user_id=admin.id,
        name="Ansible Automation Token",
        scopes=["devices:read", "jobs:run"],
        expires_in_days=15,
        db_session=test_db_session,
    )

    # 1. Plaintext secret validation
    assert raw_secret.startswith("wbd_")
    assert len(raw_secret) > 20

    # 2. Token info dict
    assert token_info["name"] == "Ansible Automation Token"
    assert token_info["token_prefix"].startswith("wbd_")
    assert token_info["is_active"] is True
    assert token_info["scopes"] == ["devices:read", "jobs:run"]

    # 3. DB validation: Plaintext secret MUST NOT be stored in DB
    db_token = test_db_session.query(ApiToken).filter(ApiToken.id == token_info["id"]).first()
    assert db_token is not None
    assert db_token.token_hash == hash_token(raw_secret)
    assert raw_secret not in db_token.token_hash


def test_api_token_verification_and_expiry(test_db_session):
    """Verify token verification, last_used_at update, and expiry/revocation rejection."""
    admin = test_db_session.query(User).filter(User.username == "admin_api").first()

    token_info, raw_secret = ApiTokenService.create_token(
        user_id=admin.id,
        name="Verification Test Token",
        scopes=["*"],
        expires_in_days=1,
        db_session=test_db_session,
    )

    # 1. Valid verification
    ctx = ApiTokenService.verify_token(raw_secret, db_session=test_db_session)
    assert ctx is not None
    assert ctx["username"] == "admin_api"
    assert ctx["user_id"] == admin.id

    # Verify last_used_at was updated
    db_token = test_db_session.query(ApiToken).filter(ApiToken.id == token_info["id"]).first()
    assert db_token.last_used_at is not None

    # 2. Expiry verification
    db_token.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    test_db_session.commit()
    expired_ctx = ApiTokenService.verify_token(raw_secret, db_session=test_db_session)
    assert expired_ctx is None

    # 3. Revocation verification
    db_token.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
    db_token.revoked = True
    test_db_session.commit()
    revoked_ctx = ApiTokenService.verify_token(raw_secret, db_session=test_db_session)
    assert revoked_ctx is None

    # 4. Bogus token verification
    assert ApiTokenService.verify_token("wbd_invalid_secret_key", db_session=test_db_session) is None
    assert ApiTokenService.verify_token("not_a_wbd_token", db_session=test_db_session) is None


def test_api_token_scope_enforcement(test_db_session):
    """Verify fine-grained scope enforcement (e.g. read vs mutate)."""
    admin = test_db_session.query(User).filter(User.username == "admin_api").first()

    # Read-only token
    _, read_token = ApiTokenService.create_token(
        user_id=admin.id,
        name="Read Only Token",
        scopes=["devices:read", "reports:read"],
        db_session=test_db_session,
    )

    # Matches granted scope
    assert ApiTokenService.verify_token(read_token, required_scope="devices:read", db_session=test_db_session) is not None
    assert ApiTokenService.verify_token(read_token, required_scope="reports:read", db_session=test_db_session) is not None

    # Denied mutating scope
    assert ApiTokenService.verify_token(read_token, required_scope="jobs:run", db_session=test_db_session) is None

    # Wildcard token
    _, wildcard_token = ApiTokenService.create_token(
        user_id=admin.id,
        name="Super Admin Token",
        scopes=["*"],
        db_session=test_db_session,
    )
    assert ApiTokenService.verify_token(wildcard_token, required_scope="jobs:run", db_session=test_db_session) is not None


def test_openapi_spec_json_endpoint(app_client):
    """Verify GET /api/v1/openapi.json serves valid OpenAPI 3.0.3 specification publicly."""
    res = app_client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    spec = res.get_json()

    assert spec["openapi"] == "3.0.3"
    assert "Web-Dash" in spec["info"]["title"]
    assert "BearerAuth" in spec["components"]["securitySchemes"]
    assert "/api/v1/devices" in spec["paths"]
    assert "/api/v1/tokens" in spec["paths"]
    assert "/api/v1/reports/digest" in spec["paths"]


def test_api_docs_html_endpoint(app_client):
    """Verify GET /api/v1/docs serves interactive Swagger UI page."""
    res = app_client.get("/api/v1/docs")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("Content-Type", "")
    assert "SwaggerUIBundle" in res.data.decode("utf-8")

    # Alias /docs
    res_alias = app_client.get("/docs")
    assert res_alias.status_code == 200


def test_bearer_token_authentication_middleware(app_client):
    """Verify request authenticated with Authorization: Bearer wbd_... succeeds without cookies or CSRF."""
    from backend.app.db.session import get_db_session
    with get_db_session() as s:
        admin = s.query(User).filter(User.username == "admin_api").first()
        _, raw_secret = ApiTokenService.create_token(
            user_id=admin.id,
            name="CI Bearer Token",
            scopes=["*"],
            db_session=s,
        )

    # Clean client session (simulate external API client without browser cookie)
    with app_client.session_transaction() as sess:
        sess.clear()

    # 1. Unauthenticated request -> 401
    res_unauth = app_client.get("/api/v1/devices")
    assert res_unauth.status_code == 401

    # 2. Bearer token authenticated request -> 200 OK
    res_auth = app_client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {raw_secret}"},
    )
    assert res_auth.status_code == 200
    assert "devices" in res_auth.get_json()

    # 3. Invalid Bearer token -> 401
    res_bad_token = app_client.get(
        "/api/v1/devices",
        headers={"Authorization": "Bearer wbd_invalid_dummy_token_12345"},
    )
    assert res_bad_token.status_code == 401
    assert "INVALID_TOKEN" in res_bad_token.get_json().get("code", "")


def test_tokens_rest_api_lifecycle(app_client):
    """Verify REST API lifecycle: create token, list tokens, and revoke token."""
    # 1. Create token
    c_res = app_client.post(
        "/api/v1/tokens",
        json={"name": "Integration Test Token", "scopes": ["devices:read"], "expires_in_days": 7},
    )
    assert c_res.status_code == 201
    payload = c_res.get_json()
    token_id = payload["token"]["id"]
    secret = payload["token_secret"]
    assert secret.startswith("wbd_")

    # 2. List tokens
    l_res = app_client.get("/api/v1/tokens")
    assert l_res.status_code == 200
    tokens = l_res.get_json()["tokens"]
    assert any(t["id"] == token_id for t in tokens)

    # 3. Revoke token
    del_res = app_client.delete(f"/api/v1/tokens/{token_id}")
    assert del_res.status_code == 200
    assert del_res.get_json()["status"] == "revoked"

    # 4. Revoked token can no longer authenticate
    with app_client.session_transaction() as sess:
        sess.clear()
    check_res = app_client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert check_res.status_code == 401


def test_webdash_cli_wrapper(tmp_path):
    """Verify webdash-cli utility table formatting and client API methods."""
    # 1. Test table formatting
    headers = ["ID", "Name", "Role"]
    rows = [[1, "TEH-AGG01", "AGG"], [2, "ISF-PE01", "PE"]]
    table_str = format_table(headers, rows)
    assert "TEH-AGG01" in table_str
    assert "ISF-PE01" in table_str
    assert "+-" in table_str

    # 2. Test CLI client with mocked urllib responses
    client = WebDashCliClient(base_url="http://test-server:5000", token="wbd_mock_token")

    with patch.object(client, "_request") as mock_req:
        # Test list_devices
        mock_req.return_value = (200, {"devices": [{"id": 1, "name": "TEH-AGG01"}]})
        devs = client.list_devices(province="TEH")
        assert len(devs) == 1
        assert devs[0]["name"] == "TEH-AGG01"

        # Test start_job
        mock_req.return_value = (201, {"job_id": "job-12345"})
        jid = client.start_job(job_type="config_backup", devices=["TEH-AGG01"])
        assert jid == "job-12345"

        # Test get_job_status
        mock_req.return_value = (200, {"id": "job-12345", "status": "succeeded"})
        j_stat = client.get_job_status("job-12345")
        assert j_stat["status"] == "succeeded"

        # Test wait_for_job
        completed = client.wait_for_job("job-12345", timeout=5, poll_interval=0.1)
        assert completed["status"] == "succeeded"

        # Test download_digest
        mock_req.return_value = (200, b"PK\x03\x04fake_xlsx_bytes")
        out_file = tmp_path / "noc_digest.xlsx"
        client.download_digest(str(out_file), format_type="xlsx", hours=24)
        assert out_file.exists()
        assert out_file.read_bytes() == b"PK\x03\x04fake_xlsx_bytes"
