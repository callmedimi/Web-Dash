"""Unit tests for Step 2.6: Structured JSON Logging, DB Audit Log, and Prometheus Metrics (F-44)."""
import json
import logging
import time
import pytest
from app import app
from backend.app.logging import JsonFormatter, set_log_context, clear_log_context
from backend.app.extensions import get_db_session
from backend.app.models.audit import AuditLog
from backend.app.models.job import Job
from backend.app.metrics import (
    record_ssh_failure,
    record_device_lock_wait,
    record_task_duration,
    generate_prometheus_metrics,
)
import audit


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_structured_json_logging_fields():
    """Verify JsonFormatter outputs valid JSON with ts, level, logger, job_id, task_id, device, user."""
    formatter = JsonFormatter()
    logger = logging.getLogger("test_structured_logger")

    # Set context variables
    set_log_context(job_id="job-1234", task_id="task-5678", device="HUAWEI-NE40E", user="netadmin")
    record = logger.makeRecord(
        name="test_logger",
        level=logging.INFO,
        fn="worker.py",
        lno=42,
        msg="Connecting to BGP peer",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)

    data = json.loads(formatted)
    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Connecting to BGP peer"
    assert data["job_id"] == "job-1234"
    assert data["task_id"] == "task-5678"
    assert data["device"] == "HUAWEI-NE40E"
    assert data["user"] == "netadmin"
    assert "ts" in data

    # Clear context
    clear_log_context()
    record2 = logger.makeRecord(
        name="test_logger",
        level=logging.WARNING,
        fn="worker.py",
        lno=50,
        msg="No context present",
        args=(),
        exc_info=None,
    )
    data2 = json.loads(formatter.format(record2))
    assert data2["job_id"] == ""
    assert data2["device"] == ""


def test_audit_log_persists_to_db_and_file_redacting_passwords(test_client):
    """Verify record_audit writes to relational audit_logs table and fallback file, redacting secrets."""
    audit.record_audit(
        action="user_password_change",
        user="test_operator",
        ip="192.168.1.100",
        status="success",
        detail={
            "target_user": "operator_b",
            "current_password": "PlainOldPassword123!",
            "new_password": "NewSecretPassword456!",
            "token": "secret-jwt-token",
            "safe_metadata": "audit_test_run",
        },
    )

    # 1. Verify DB record
    with get_db_session() as s:
        db_entry = (
            s.query(AuditLog)
            .filter_by(action="user_password_change", user_id="test_operator")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert db_entry is not None
        assert db_entry.ip == "192.168.1.100"
        detail = db_entry.detail
        assert detail["current_password"] == "[REDACTED]"
        assert detail["new_password"] == "[REDACTED]"
        assert detail["token"] == "[REDACTED]"
        assert detail["safe_metadata"] == "audit_test_run"

    # 2. Verify fallback file write
    entries = audit.get_audit_entries(limit=10)
    assert len(entries) >= 1
    last = entries[-1]
    assert last["action"] == "user_password_change"
    assert last["user"] == "test_operator"
    assert last["detail"]["new_password"] == "[REDACTED]"


def test_metrics_prometheus_exposition_format(test_client):
    """Verify /metrics returns Prometheus text exposition with jobs, tasks, ssh failures, and locks."""
    # Record sample metrics
    record_ssh_failure("auth_failed")
    record_ssh_failure("timeout")
    record_device_lock_wait()
    record_task_duration(1.25)
    record_task_duration(4.5)

    res = test_client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("Content-Type", "")

    text = res.data.decode("utf-8")
    assert "# HELP webdash_jobs_total" in text
    assert "# TYPE webdash_jobs_total counter" in text
    assert "# HELP webdash_ssh_failures_total" in text
    assert 'webdash_ssh_failures_total{reason="auth_failed"}' in text
    assert 'webdash_ssh_failures_total{reason="timeout"}' in text
    assert "# HELP webdash_device_lock_waits_total" in text
    assert "webdash_device_lock_waits_total" in text
    assert "# HELP webdash_task_duration_seconds" in text
    assert "webdash_task_duration_seconds_bucket" in text
    assert "webdash_task_duration_seconds_count" in text
    assert "webdash_task_duration_seconds_sum" in text


def test_healthz_and_readyz_probes(test_client):
    """Verify /healthz liveness and /readyz readiness probes."""
    res_liveness = test_client.get("/healthz")
    assert res_liveness.status_code == 200
    data_l = res_liveness.get_json()
    assert data_l["status"] == "ok"
    assert data_l["app"] == "Web-Dash"

    res_readiness = test_client.get("/readyz")
    assert res_readiness.status_code == 200
    data_r = res_readiness.get_json()
    assert data_r["status"] in ("ready", "degraded")
    assert data_r["database"] == "connected"
