"""Tests for Step 2.8: Credential Vault, Fernet Encryption, RBAC, and F-06 hardening."""
import os
import json
import pytest
from cryptography.fernet import Fernet

from backend.app import create_app
from backend.app.config import settings
from backend.app.db.session import get_db_session, init_db
from backend.app.models.device import Credential, Device
from backend.app.models.job import Job
from backend.app.security.vault import (
    get_vault_key,
    encrypt_secret,
    decrypt_secret,
    VaultService,
)
import auth


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    monkeypatch.setenv("WEBDASH_DATA_DIR", data_dir)
    monkeypatch.setenv("DATA_DIR", data_dir)
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin_user")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "AdminPass1234!")
    test_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", test_key)
    monkeypatch.setenv("TESTING", "1")
    init_db()

    auth.clear_all_rate_limits()
    auth._load_users()
    auth.create_user("op_user", "OperatorPass1234!", "operator")
    auth.create_user("viewer_user", "ViewerPass1234!", "viewer")

    yield data_dir


@pytest.fixture
def test_app():
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(test_app):
    return test_app.test_client()


def _login(client, username: str, password: str) -> dict:
    res = client.post("/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.get_json()}"
    csrf = res.get_json()["csrf_token"]
    return {"X-CSRF-Token": csrf}


# ---------------------------------------------------------------------------
# 1. Fernet Encryption & DB Plaintext Absence
# ---------------------------------------------------------------------------
def test_fernet_encryption_and_no_plaintext_in_db():
    raw_secret = "SuperSecretNetworkPassword!@#123"
    encrypted = encrypt_secret(raw_secret)
    assert encrypted != raw_secret
    assert raw_secret not in encrypted
    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_secret

    with get_db_session() as s:
        cred = VaultService.create_credential(
            session=s,
            name="core-switches",
            kind="ssh_password",
            secret=raw_secret,
            username="netadmin",
            meta={"domain": "corp"},
        )
        s.commit()
        cred_id = cred.id

    # Verify directly via SQL that plaintext password is NOT in the DB column
    with get_db_session() as s:
        db_cred = s.query(Credential).filter(Credential.id == cred_id).first()
        assert db_cred.secret_encrypted != raw_secret
        assert raw_secret not in db_cred.secret_encrypted
        # Verify to_dict never includes the secret
        d = db_cred.to_dict()
        assert "secret" not in d
        assert "secret_encrypted" not in d
        assert d["username"] == "netadmin"
        assert d["name"] == "core-switches"


def test_credential_rotation():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()

    plaintext = "HuaweiRouterPass2026"
    encrypted_old = encrypt_secret(plaintext, key=old_key)
    assert decrypt_secret(encrypted_old, key=old_key) == plaintext

    with get_db_session() as s:
        cred = Credential(
            name="rot-test",
            kind="ssh_password",
            secret_encrypted=encrypted_old,
            meta_info={},
        )
        s.add(cred)
        s.commit()

        # Rotate all
        rotated_count = VaultService.rotate_all(s, old_key=old_key, new_key=new_key)
        assert rotated_count >= 1
        s.commit()

        # Verify decryption with new key
        reloaded = s.query(Credential).filter(Credential.name == "rot-test").first()
        assert decrypt_secret(reloaded.secret_encrypted, key=new_key) == plaintext


def test_missing_vault_key_in_production_raises(monkeypatch):
    monkeypatch.delenv("WEBDASH_VAULT_KEY", raising=False)
    monkeypatch.delenv("VAULT_KEY", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "vault_key", None)

    with pytest.raises(RuntimeError, match="WEBDASH_VAULT_KEY is required in production mode"):
        get_vault_key(require_prod=True)


# ---------------------------------------------------------------------------
# 2. Vault API & RBAC
# ---------------------------------------------------------------------------
def test_vault_api_crud_and_rbac(client):
    # Viewer cannot access credentials
    _login(client, "viewer_user", "ViewerPass1234!")
    res = client.get("/api/v1/credentials")
    assert res.status_code == 403

    # Admin can create credential
    headers = _login(client, "admin_user", "AdminPass1234!")
    post_res = client.post(
        "/api/v1/credentials",
        json={
            "name": "edge-routers",
            "kind": "ssh_password",
            "username": "huawei_admin",
            "secret": "SecretPass987!",
            "meta": {"location": "Tehran"},
        },
        headers=headers,
    )
    assert post_res.status_code == 201
    created = post_res.get_json()
    assert created["name"] == "edge-routers"
    assert created["username"] == "huawei_admin"
    assert "secret" not in created
    assert "secret_encrypted" not in created
    cred_id = created["id"]

    # List credentials
    list_res = client.get("/api/v1/credentials")
    assert list_res.status_code == 200
    creds_list = list_res.get_json()["credentials"]
    assert any(c["id"] == cred_id for c in creds_list)

    # Get single credential
    get_res = client.get(f"/api/v1/credentials/{cred_id}")
    assert get_res.status_code == 200
    single = get_res.get_json()
    assert single["name"] == "edge-routers"
    assert "secret" not in single

    # Rotate / update credential
    put_res = client.put(
        f"/api/v1/credentials/{cred_id}",
        json={"name": "edge-routers-renamed", "secret": "NewRotatedSecret555!"},
        headers=headers,
    )
    assert put_res.status_code == 200
    updated = put_res.get_json()
    assert updated["name"] == "edge-routers-renamed"
    assert "secret" not in updated

    # Verify secret was decrypted correctly internally
    with get_db_session() as s:
        _, secret = VaultService.get_decrypted_secret(s, cred_id)
        assert secret == "NewRotatedSecret555!"

    # Operator can read but cannot delete or create
    op_headers = _login(client, "op_user", "OperatorPass1234!")
    del_res_op = client.delete(f"/api/v1/credentials/{cred_id}", headers=op_headers)
    assert del_res_op.status_code == 403

    # Admin can delete
    adm_headers = _login(client, "admin_user", "AdminPass1234!")
    del_res = client.delete(f"/api/v1/credentials/{cred_id}", headers=adm_headers)
    assert del_res.status_code == 200
    assert del_res.get_json()["status"] == "deleted"

    # Verify 404 after deletion
    get_404 = client.get(f"/api/v1/credentials/{cred_id}")
    assert get_404.status_code == 404


# ---------------------------------------------------------------------------
# 3. Forbid Plaintext Passwords in Job Params (F-06)
# ---------------------------------------------------------------------------
def test_job_submission_forbids_plaintext_passwords(client):
    headers = _login(client, "admin_user", "AdminPass1234!")

    # 1. Attempting to submit job with plaintext password in params must fail with 400
    bad_payload = {
        "type": "diagnostic",
        "mode": "dry_run",
        "devices": ["RouterA"],
        "params": {
            "target": "RouterA",
            "password": "CleartextPassword123",
        },
    }
    res = client.post("/api/v1/jobs", json=bad_payload, headers=headers)
    assert res.status_code == 400
    body = res.get_json()
    assert body["error"]["code"] == "FORBIDDEN_PARAM"
    assert "forbidden" in body["error"]["message"].lower()

    # 2. Submitting with credential_id succeeds with 202 Accepted
    with get_db_session() as s:
        cred = VaultService.create_credential(
            session=s,
            name="job-cred",
            kind="ssh_password",
            secret="EncryptedSecret99",
            username="admin",
        )
        s.commit()
        valid_cred_id = cred.id

    good_payload = {
        "type": "diagnostic",
        "mode": "dry_run",
        "devices": ["RouterA"],
        "params": {
            "target": "RouterA",
            "credential_id": valid_cred_id,
        },
    }
    res_good = client.post("/api/v1/jobs", json=good_payload, headers=headers)
    assert res_good.status_code == 202
    job_id = res_good.get_json()["job_id"]

    # 3. Verify DB dump of job params contains NO plaintext password
    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        dumped_params = json.dumps(job.params)
        assert "CleartextPassword" not in dumped_params
        assert "EncryptedSecret99" not in dumped_params
        assert job.params["credential_id"] == valid_cred_id


# ---------------------------------------------------------------------------
# 4. Device Attachment & Resolution
# ---------------------------------------------------------------------------
def test_device_attachment_and_credential_resolution(client):
    headers = _login(client, "admin_user", "AdminPass1234!")

    with get_db_session() as s:
        cred = VaultService.create_credential(
            session=s,
            name="huawei-vrp8-cred",
            kind="ssh_password",
            secret="VaultSecretVal456",
            username="netops",
        )
        dev = Device(
            name="Tehran-NE40E-01",
            mgmt_ip="10.10.10.1",
            vendor="huawei",
            os_family="vrp8",
        )
        s.add(dev)
        s.commit()
        cred_id = cred.id

    # Attach credential to device via API
    attach_res = client.post(
        f"/api/v1/credentials/{cred_id}/attach",
        json={"device_name": "Tehran-NE40E-01"},
        headers=headers,
    )
    assert attach_res.status_code == 200
    assert attach_res.get_json()["status"] == "attached"

    # Resolve credentials via device_name
    with get_db_session() as s:
        resolved = VaultService.resolve_credentials(s, device_name="Tehran-NE40E-01")
        assert resolved is not None
        assert resolved["id"] == cred_id
        assert resolved["username"] == "netops"
        assert resolved["password"] == "VaultSecretVal456"

    # Detach / Delete credential verifies foreign key becomes NULL
    with get_db_session() as s:
        VaultService.delete_credential(s, cred_id)
        s.commit()

        dev_after = s.query(Device).filter(Device.name == "Tehran-NE40E-01").first()
        assert dev_after.credential_id is None


# ---------------------------------------------------------------------------
# 5. Legacy Endpoints Compatibility & Deprecation
# ---------------------------------------------------------------------------
def test_legacy_endpoint_with_credential_id_and_deprecation(client, caplog):
    headers = _login(client, "admin_user", "AdminPass1234!")

    with get_db_session() as s:
        cred = VaultService.create_credential(
            session=s,
            name="legacy-support-cred",
            kind="ssh_password",
            secret="MyPassword321",
            username="legacy_admin",
        )
        s.commit()
        c_id = cred.id

    # 1. Calling legacy endpoint with credential_id
    payload_vault = {
        "routers": [{"name": "R1", "host": "192.168.1.1"}],
        "credential_id": c_id,
    }
    res_vault = client.post("/run-manual", json=payload_vault, headers=headers)
    assert res_vault.status_code == 200
    assert "session_id" in res_vault.get_json()

    # 2. Calling legacy endpoint with plaintext password keeps working but logs deprecation
    import logging
    with caplog.at_level(logging.WARNING):
        payload_plain = {
            "routers": [{"name": "R2", "host": "192.168.1.2"}],
            "username": "legacy_admin",
            "password": "PlainPassword789",
        }
        res_plain = client.post("/run-manual", json=payload_plain, headers=headers)
        assert res_plain.status_code == 200
        assert "DEPRECATION" in caplog.text
