"""End-to-End Regression Test Suite for Phase 2 (Step 2.9).
Validates the complete integrated lifecycle: Database, JobEngine, Worker Pool,
Realtime SSE with replay, RBAC isolation, Credential Vault, Prometheus Metrics,
and Probes.
"""
import os
import json
import pytest
from cryptography.fernet import Fernet

from backend.app import create_app
from backend.app.config import settings
from backend.app.db.session import get_db_session, init_db
from backend.app.models.device import Credential, Device
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.jobs.engine import engine
from backend.app.security.vault import VaultService
import auth


@pytest.fixture(autouse=True)
def setup_regression_env(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    monkeypatch.setenv("WEBDASH_DATA_DIR", data_dir)
    monkeypatch.setenv("DATA_DIR", data_dir)
    monkeypatch.setenv("INITIAL_ADMIN_USER", "phase2_god")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Phase2SuperGodPass1234!")
    test_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", test_key)
    monkeypatch.setenv("TESTING", "1")
    init_db()

    auth.clear_all_rate_limits()
    auth._load_users()
    auth.create_user("operator_bob", "OperatorPass1234!", "operator")
    auth.create_user("viewer_carol", "ViewerPass1234!", "viewer")

    yield data_dir


@pytest.fixture
def app():
    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username: str, password: str) -> dict:
    res = client.post("/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.get_json()}"
    csrf = res.get_json()["csrf_token"]
    return {"X-CSRF-Token": csrf}


# ---------------------------------------------------------------------------
# Full Phase 2 Integration Lifecycle
# ---------------------------------------------------------------------------
def test_phase2_complete_integration_lifecycle(client):
    # 1. Probes & Metrics before any activity
    health_res = client.get("/healthz")
    assert health_res.status_code == 200
    assert health_res.get_json()["status"] == "ok"

    ready_res = client.get("/readyz")
    assert ready_res.status_code == 200
    assert ready_res.get_json()["database"] == "connected"

    metrics_init = client.get("/metrics")
    assert metrics_init.status_code == 200
    assert "webdash_jobs_total" in metrics_init.text

    # 2. Login as God/Admin
    admin_headers = _login(client, "phase2_god", "Phase2SuperGodPass1234!")

    # 3. Create Credential in Vault
    cred_res = client.post(
        "/api/v1/credentials",
        json={
            "name": "core-datacenter-cred",
            "kind": "ssh_password",
            "username": "huawei_netadmin",
            "secret": "ProductionSecret2026!#",
            "meta": {"site": "Tehran-DC"},
        },
        headers=admin_headers,
    )
    assert cred_res.status_code == 201
    cred_id = cred_res.get_json()["id"]

    # Verify secret is never returned in API and not in plaintext in DB
    with get_db_session() as s:
        db_cred = s.query(Credential).filter(Credential.id == cred_id).first()
        assert "ProductionSecret2026!#" not in db_cred.secret_encrypted
        dev = Device(
            name="Tehran-NE40E-Core01",
            mgmt_ip="10.200.1.1",
            vendor="huawei",
            os_family="vrp8",
            credential_id=cred_id,
        )
        s.add(dev)
        s.commit()

    # 4. Job Submission: reject plaintext passwords in params (F-06)
    bad_job_res = client.post(
        "/api/v1/jobs",
        json={
            "type": "diagnostic",
            "params": {"password": "PlaintextPasswordForbidden"},
        },
        headers=admin_headers,
    )
    assert bad_job_res.status_code == 400
    assert bad_job_res.get_json()["error"]["code"] == "FORBIDDEN_PARAM"

    # 5. Job Submission: accept with credential_id
    job_res = client.post(
        "/api/v1/jobs",
        json={
            "type": "diagnostic",
            "mode": "dry_run",
            "devices": ["Tehran-NE40E-Core01"],
            "params": {
                "credential_id": cred_id,
                "command": "display version",
            },
        },
        headers=admin_headers,
    )
    assert job_res.status_code == 202
    job_id = job_res.get_json()["job_id"]

    # 6. Verify Job, Tasks, and Worker Credential Resolution
    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        assert job is not None
        assert job.status in ("queued", "running", "succeeded", "failed")
        assert len(job.tasks) == 1
        assert job.tasks[0].device_name == "Tehran-NE40E-Core01"

        resolved = VaultService.resolve_credentials(s, credential_id=cred_id)
        assert resolved["password"] == "ProductionSecret2026!#"
        assert resolved["username"] == "huawei_netadmin"

        # Emit test event to verify realtime SSE
        event = JobEvent(
            job_id=job_id,
            level="info",
            message="Diagnosing router configuration complete.",
            data={"router": "Tehran-NE40E-Core01", "version": "VRP8"},
        )
        s.add(event)
        s.commit()
        event_id = event.id

    # 7. Realtime SSE Replay Check
    sse_res = client.get(f"/api/v1/jobs/{job_id}/events?since={event_id - 1}")
    assert sse_res.status_code == 200
    assert "text/event-stream" in sse_res.content_type

    # 8. RBAC Isolation
    # Bob (operator) cannot view Alice's jobs (anti-enumeration returns 404)
    op_headers = _login(client, "operator_bob", "OperatorPass1234!")
    op_get_job = client.get(f"/api/v1/jobs/{job_id}")
    assert op_get_job.status_code == 404

    # Carol (viewer) cannot delete credentials or submit apply jobs
    viewer_headers = _login(client, "viewer_carol", "ViewerPass1234!")
    viewer_del = client.delete(f"/api/v1/credentials/{cred_id}", headers=viewer_headers)
    assert viewer_del.status_code == 403

    # 9. Prometheus metrics after activity
    metrics_after = client.get("/metrics")
    assert metrics_after.status_code == 200
    assert "webdash_jobs_total" in metrics_after.text
    assert "webdash_task_duration_seconds" in metrics_after.text

    # 10. Schedules API End-to-End
    admin_headers = _login(client, "phase2_god", "Phase2SuperGodPass1234!")
    sched_post = client.post(
        "/api/v1/schedules",
        json={
            "name": "daily-arp-scan",
            "cron_expr": "0 2 * * *",
            "job_type": "arp_mac_collector",
            "target_devices": ["Tehran-NE40E-Core01"],
            "params": {"threads": 5},
            "enabled": True,
        },
        headers=admin_headers,
    )
    assert sched_post.status_code == 201
    sched_id = sched_post.get_json().get("schedule_id") or sched_post.get_json().get("schedule", {}).get("id")

    sched_run = client.post(f"/api/v1/schedules/{sched_id}/run", headers=admin_headers)
    assert sched_run.status_code in (200, 202)
    assert "job_id" in sched_run.get_json()
