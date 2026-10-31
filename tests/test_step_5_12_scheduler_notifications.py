"""Comprehensive tests for Phase 5 Step 5.12: Scheduler & Multi-Channel Notifications."""
import time
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.config_change import Schedule, SchedulerLease
from backend.app.jobs.scheduler import JobScheduler
from backend.app.services.notifications import (
    NotificationService,
    SUPPORTED_TRIGGERS,
    WebhookChannel,
    SyslogChannel,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


@pytest.fixture
def test_db_session(tmp_path, monkeypatch):
    """Provide a fresh SQLite test session."""
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    db_file = tmp_path / "test_scheduler.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client with test configuration and logged-in admin user."""
    db_file = tmp_path / "test_app_schedules.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_sched", role="admin", password_hash="dummy_hash")
            s.add(admin)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_sched",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_cron_syntax_validation(test_db_session):
    """Verify standard cron expressions pass validation and invalid expressions raise ValueError."""
    scheduler = JobScheduler(worker_id="test_worker")

    # Valid cron expressions
    sid1 = scheduler.add_schedule(
        job_type="config_backup",
        cron_expression="0 2 * * *",  # 2 AM daily
        params={"kind": "running"},
        db_session=test_db_session,
    )
    assert sid1 > 0

    sid2 = scheduler.add_schedule(
        job_type="license_check",
        cron_expression="*/15 * * * *",  # Every 15 min
        db_session=test_db_session,
    )
    assert sid2 > 0

    # Invalid cron expressions
    with pytest.raises(ValueError) as exc1:
        scheduler.add_schedule(job_type="test", cron_expression="invalid_cron_syntax", db_session=test_db_session)
    assert "Invalid cron expression" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        scheduler.add_schedule(job_type="test", cron_expression="60 * * * *", db_session=test_db_session)
    assert "Invalid cron expression" in str(exc2.value)


def test_db_lease_single_leader_election(test_db_session):
    """Verify single leader election via DB lease, renewal, handover on expiry, and release."""
    scheduler_w1 = JobScheduler(worker_id="worker_alpha")
    scheduler_w2 = JobScheduler(worker_id="worker_beta")

    # 1. Worker Alpha acquires lease
    acquired = scheduler_w1.acquire_or_renew_lease(
        lease_duration_seconds=2,
        db_session=test_db_session,
    )
    assert acquired is True

    status_w1 = scheduler_w1.get_leader_status(db_session=test_db_session)
    assert status_w1["is_leader"] is True
    assert status_w1["holder_id"] == "worker_alpha"

    # 2. Worker Beta tries to acquire lease while Alpha's lease is still active -> Denied
    denied = scheduler_w2.acquire_or_renew_lease(
        lease_duration_seconds=2,
        db_session=test_db_session,
    )
    assert denied is False
    status_w2 = scheduler_w2.get_leader_status(db_session=test_db_session)
    assert status_w2["is_leader"] is False
    assert status_w2["holder_id"] == "worker_alpha"

    # 3. Simulate lease expiration
    lease = test_db_session.query(SchedulerLease).filter(SchedulerLease.name == "scheduler_leader").first()
    lease.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    test_db_session.commit()

    # 4. Worker Beta now takes over expired lease
    taken_over = scheduler_w2.acquire_or_renew_lease(
        lease_duration_seconds=5,
        db_session=test_db_session,
    )
    assert taken_over is True
    status_w2_new = scheduler_w2.get_leader_status(db_session=test_db_session)
    assert status_w2_new["is_leader"] is True
    assert status_w2_new["holder_id"] == "worker_beta"

    # 5. Worker Beta releases lease
    released = scheduler_w2.release_lease(db_session=test_db_session)
    assert released is True
    status_empty = scheduler_w2.get_leader_status(db_session=test_db_session)
    assert status_empty["has_lease"] is False


def test_scheduler_due_jobs_and_deduplication(test_db_session):
    """Verify check_and_run_due_jobs triggers matching schedules and prevents double-execution in same minute."""
    scheduler = JobScheduler(worker_id="worker_leader")

    # Schedule running every minute
    sid = scheduler.add_schedule(job_type="config_backup", cron_expression="* * * * *", db_session=test_db_session)

    time_14_00 = datetime(2026, 10, 31, 14, 0, 0)
    time_14_00_sec30 = datetime(2026, 10, 31, 14, 0, 30)
    time_14_01 = datetime(2026, 10, 31, 14, 1, 0)

    # 1. First trigger at 14:00
    jobs1 = scheduler.check_and_run_due_jobs(
        current_time=time_14_00,
        require_leader=True,
        db_session=test_db_session,
    )
    assert len(jobs1) == 1

    # 2. Second check within same minute (14:00:30) -> deduplicated, 0 jobs
    jobs_dedup = scheduler.check_and_run_due_jobs(
        current_time=time_14_00_sec30,
        require_leader=True,
        db_session=test_db_session,
    )
    assert len(jobs_dedup) == 0

    # 3. Next minute (14:01:00) -> triggers next job
    jobs2 = scheduler.check_and_run_due_jobs(
        current_time=time_14_01,
        require_leader=True,
        db_session=test_db_session,
    )
    assert len(jobs2) == 1


def test_scheduler_non_leader_skips_run(test_db_session):
    """Verify that a worker that is not the elected leader skips check_and_run_due_jobs completely."""
    # Worker 1 holds active lease
    w1 = JobScheduler(worker_id="leader_node")
    w1.acquire_or_renew_lease(lease_duration_seconds=60, db_session=test_db_session)

    # Worker 2 is a follower
    w2 = JobScheduler(worker_id="follower_node")
    w2.add_schedule(job_type="license_check", cron_expression="* * * * *", db_session=test_db_session)

    triggered = w2.check_and_run_due_jobs(
        current_time=datetime(2026, 10, 31, 15, 0, 0),
        require_leader=True,
        db_session=test_db_session,
    )
    # Skipped because follower_node is not leader
    assert len(triggered) == 0


def test_schedule_toggle_delete_and_trigger_now(test_db_session):
    """Verify schedule lifecycle: toggle enable/disable, trigger_now, and delete."""
    scheduler = JobScheduler(worker_id="worker_lifecycle")

    sid = scheduler.add_schedule(job_type="site_arp_collector", cron_expression="0 * * * *", db_session=test_db_session)

    # Toggle to disabled
    assert scheduler.toggle_schedule(sid, enabled=False, db_session=test_db_session) is True
    sched_list = scheduler.list_schedules(db_session=test_db_session)
    item = next(s for s in sched_list if s["id"] == sid)
    assert item["enabled"] is False

    # Disabled schedule does not run in due check
    time_due = datetime(2026, 10, 31, 16, 0, 0)
    assert len(scheduler.check_and_run_due_jobs(time_due, db_session=test_db_session)) == 0

    # Trigger now runs immediately regardless of enabled status or cron
    job_id = scheduler.trigger_now(sid, user="test_operator", db_session=test_db_session)
    assert job_id is not None

    # Delete schedule
    assert scheduler.delete_schedule(sid, db_session=test_db_session) is True
    assert len(scheduler.list_schedules(db_session=test_db_session)) == 0


def test_multi_channel_notifications_dispatch():
    """Verify dispatching alerts across triggers and capturing in test mode."""
    captured = NotificationService.enable_test_capture()

    # 1. Job failed
    res_job = NotificationService.notify_job_failed(
        job_id="job-999",
        job_type="config_backup",
        error="SSH connection timeout",
        user="noc_admin",
    )
    assert res_job["status"] == "dispatched"

    # 2. Change awaiting approval
    res_change = NotificationService.notify_change_awaiting_approval(
        change_id="cr-101",
        device_name="TEH-AGG01",
        risk_level="high",
        approver_role="admin",
    )
    assert res_change["status"] == "dispatched"

    # 3. License expiring
    res_lic = NotificationService.notify_license_expiring(
        device_name="ISF-PE01",
        product="NetEngine",
        days_remaining=5,
    )
    assert res_lic["status"] == "dispatched"

    # 4. Device flapping
    res_flap = NotificationService.notify_device_flapping(
        device_name="SHZ-PE01",
        interface="10GE0/1/0",
        flap_count=15,
    )
    assert res_flap["status"] == "dispatched"

    # 5. Compliance regression
    res_comp = NotificationService.notify_compliance_regression(
        device_name="MHD-PE01",
        failed_rules=["SEC-001", "OPS-001"],
        province="MHD",
    )
    assert res_comp["status"] == "dispatched"

    # Verify captured events
    assert len(captured) == 5
    assert any(c["event_type"] == "job_failed" for c in captured)
    assert any(c["event_type"] == "license_expiring" and c["severity"] == "critical" for c in captured)

    # Verify history
    history = NotificationService.get_recent_history(limit=10)
    assert len(history) >= 5

    NotificationService.disable_test_capture()


def test_catalog_feature_scheduler_notifications(test_db_session):
    """Verify SchedulerNotificationsFeature execution via catalog registry."""
    feature = feature_registry.get("scheduler_notifications")
    assert feature is not None

    # 1. Action: add_schedule
    ctx_add = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "add_schedule",
            "job_type": "config_backup",
            "cron": "0 3 * * *",
            "params": {"kind": "running"},
        },
    )
    res_add = feature.run(ctx_add)
    assert res_add["status"] == "success"
    sid = res_add["schedule_id"]

    # 2. Action: list_schedules
    ctx_list = FeatureContext(db_session=test_db_session, params={"action": "list_schedules"})
    res_list = feature.run(ctx_list)
    assert res_list["status"] == "success"
    assert res_list["count"] >= 1

    # 3. Action: get_leader_status
    ctx_leader = FeatureContext(db_session=test_db_session, params={"action": "get_leader_status"})
    res_leader = feature.run(ctx_leader)
    assert res_leader["status"] == "success"
    assert "leader" in res_leader

    # 4. Action: send_notification
    NotificationService.enable_test_capture()
    ctx_notif = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "send_notification",
            "event_type": "compliance_regression",
            "title": "Test Catalog Alert",
            "message": "Sample notification via feature runner",
            "severity": "warning",
        },
    )
    res_notif = feature.run(ctx_notif)
    assert res_notif["status"] == "success"
    NotificationService.disable_test_capture()

    # 5. Action: delete_schedule
    ctx_del = FeatureContext(
        db_session=test_db_session,
        params={"action": "delete_schedule", "schedule_id": sid},
    )
    res_del = feature.run(ctx_del)
    assert res_del["status"] == "success"


def test_schedules_and_notifications_rest_api(app_client):
    """Verify REST API endpoints for schedules and notifications."""
    # 1. List schedules
    list_res = app_client.get("/api/v1/schedules")
    assert list_res.status_code == 200
    assert "schedules" in list_res.get_json()

    # 2. Create schedule
    create_payload = {
        "job_type": "license_check",
        "cron": "0 4 * * *",
        "params": {"notify": True},
    }
    c_res = app_client.post("/api/v1/schedules", json=create_payload)
    assert c_res.status_code == 201
    sid = c_res.get_json()["schedule_id"]

    # 3. Leader status endpoint
    leader_res = app_client.get("/api/v1/schedules/leader")
    assert leader_res.status_code == 200
    assert "leader" in leader_res.get_json()

    # 4. Trigger schedule now
    run_res = app_client.post(f"/api/v1/schedules/{sid}/run")
    assert run_res.status_code == 200
    assert "job_id" in run_res.get_json()

    # 5. Notification triggers list
    trig_res = app_client.get("/api/v1/notifications/triggers")
    assert trig_res.status_code == 200
    assert "job_failed" in trig_res.get_json()["triggers"]

    # 6. Send notification API
    NotificationService.enable_test_capture()
    send_res = app_client.post(
        "/api/v1/notifications/send",
        json={
            "event_type": "job_failed",
            "title": "API Test Alert",
            "message": "Testing notification delivery via REST API",
            "severity": "critical",
        },
    )
    assert send_res.status_code == 200
    assert send_res.get_json()["status"] == "success"

    # 7. Notification history
    hist_res = app_client.get("/api/v1/notifications/history")
    assert hist_res.status_code == 200
    assert hist_res.get_json()["count"] >= 1
    NotificationService.disable_test_capture()

    # 8. Delete schedule
    del_res = app_client.delete(f"/api/v1/schedules/{sid}")
    assert del_res.status_code == 200
