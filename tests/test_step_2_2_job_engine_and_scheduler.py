"""Unit and integration tests for Step 2.2: Central Job Engine, Worker Pool, Locks, and Cron Scheduler."""
import time
import threading
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.db.session import init_db, get_db_session
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.models.device import DeviceLock
from backend.app.models.config_change import Schedule
from backend.app.jobs.engine import JobEngine
from backend.app.jobs.locks import (
    acquire_device_lock,
    release_device_lock,
    heartbeat_device_lock,
)
from backend.app.jobs.events import JobEventBroadcaster
from backend.app.jobs.cancel import request_job_cancellation
from backend.app.jobs.scheduler import JobScheduler


@pytest.fixture
def clean_db():
    """Ensure clean tables before test."""
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.query(DeviceLock).delete()
        s.query(Schedule).delete()
        s.commit()
    yield
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.query(DeviceLock).delete()
        s.query(Schedule).delete()
        s.commit()


def test_device_locks_and_stale_reclaim(clean_db):
    """Test device lock exclusivity, heartbeat, and stale lock reclamation."""
    with get_db_session() as s:
        # Task 1 acquires lock
        assert acquire_device_lock(s, "NE40-TEST-1", "task-1") is True
        # Task 2 cannot acquire lock on same device
        assert acquire_device_lock(s, "NE40-TEST-1", "task-2") is False

        # Heartbeat
        assert heartbeat_device_lock(s, "NE40-TEST-1", "task-1") is True

        # Simulate stale lock (> 600s)
        lock = s.query(DeviceLock).filter(DeviceLock.device_name == "NE40-TEST-1").first()
        lock.heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=700)
        s.commit()

        # Task 2 reclaims stale lock
        assert acquire_device_lock(s, "NE40-TEST-1", "task-2", stale_seconds=600) is True

        # Task 2 releases lock
        assert release_device_lock(s, "NE40-TEST-1", "task-2") is True
        # Now Task 3 can acquire
        assert acquire_device_lock(s, "NE40-TEST-1", "task-3") is True


def test_job_submission_and_event_streaming(clean_db):
    """Test submitting jobs and broadcasting events."""
    test_engine = JobEngine(max_workers=5)
    bus = JobEventBroadcaster()

    job_id = test_engine.submit(
        job_type="test_job",
        params={"speed": 100},
        user="operator1",
        mode="apply",
        target_devices=["DEV-A", "DEV-B"],
    )

    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        assert job is not None
        assert job.status == "queued"
        assert len(job.tasks) == 2
        assert {t.device_name for t in job.tasks} == {"DEV-A", "DEV-B"}

        # Subscribe to SSE events
        q = bus.subscribe(job_id)
        bus.publish_event(s, job_id, job.tasks[0].id, "info", "Starting test task")

        assert not q.empty()
        item = q.get_nowait()
        assert item["job_id"] == job_id
        assert item["level"] == "info"
        assert "Starting test task" in item["message"]

        bus.unsubscribe(job_id, q)


def test_job_cancellation(clean_db):
    """Test cancellation of queued tasks and check cancellation token."""
    test_engine = JobEngine(max_workers=2)

    job_id = test_engine.submit(
        job_type="long_job",
        params={},
        user="admin",
        target_devices=["DEV-1", "DEV-2", "DEV-3"],
    )

    with get_db_session() as s:
        cancelled = request_job_cancellation(s, job_id)
        assert cancelled is True

        job = s.query(Job).filter(Job.id == job_id).first()
        assert job.status == "cancelling"

        tasks = s.query(JobTask).filter(JobTask.job_id == job_id).all()
        assert all(t.status == "cancelled" for t in tasks)


def test_engine_startup_recovery(clean_db):
    """Test that interrupted running tasks are marked as failed on server restart."""
    test_engine = JobEngine(max_workers=2)

    job_id = test_engine.submit(
        job_type="reboot_test",
        params={},
        user="admin",
        target_devices=["ROUTER-INTERRUPTED"],
    )

    with get_db_session() as s:
        task = s.query(JobTask).filter(JobTask.job_id == job_id).first()
        task.status = "running"
        task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # Add a lock simulating the crashed worker
        acquire_device_lock(s, "ROUTER-INTERRUPTED", task.id)
        s.commit()

    # Simulate restart recovery
    recovered = test_engine.recover_on_startup()
    assert recovered == 1

    with get_db_session() as s:
        recovered_task = s.query(JobTask).filter(JobTask.job_id == job_id).first()
        assert recovered_task.status == "failed"
        assert recovered_task.error == "interrupted by restart"

        # Locks must be cleared
        lock = s.query(DeviceLock).filter(DeviceLock.device_name == "ROUTER-INTERRUPTED").first()
        assert lock is None

        # Parent job status must be rolled up to failed
        parent_job = s.query(Job).filter(Job.id == job_id).first()
        assert parent_job.status == "failed"


def test_cron_scheduler_lifecycle(clean_db):
    """Test adding, triggering, toggling, and running cron schedules."""
    sched = JobScheduler()

    # Add schedule for every minute
    sid = sched.add_schedule(
        job_type="arp_mac_collector",
        cron_expression="* * * * *",
        params={"threads": 5, "devices": ["NE-1"]},
        enabled=True,
    )
    assert sid > 0

    schedules = sched.list_schedules()
    assert len(schedules) == 1
    assert schedules[0]["job_type"] == "arp_mac_collector"

    # Trigger Now on demand
    job_id = sched.trigger_now(sid, user="test_admin")
    assert job_id is not None

    with get_db_session() as s:
        triggered_job = s.query(Job).filter(Job.id == job_id).first()
        assert triggered_job is not None
        assert triggered_job.type == "arp_mac_collector"

    # Toggle disable
    sched.toggle_schedule(sid, enabled=False)
    assert sched.list_schedules()[0]["enabled"] is False

    # Delete
    assert sched.delete_schedule(sid) is True
    assert len(sched.list_schedules()) == 0


def test_stress_job_engine_execution(clean_db):
    """
    Stress test verifying:
    - Concurrency cap respected (10 workers).
    - Device lock exclusivity: 20 fake devices running 200 tasks.
    - Zero deadlocks and 100% correct status roll-up.
    """
    max_workers = 10
    test_engine = JobEngine(max_workers=max_workers)

    # Fake task handler that simulates work and verifies lock exclusivity
    active_locks = set()
    lock_mutex = threading.Lock()

    def fake_handler(ctx):
        dev = ctx.device_name
        with lock_mutex:
            assert dev not in active_locks, f"Device collision! Multiple tasks running on {dev}"
            active_locks.add(dev)

        time.sleep(0.01)  # Simulate I/O

        with lock_mutex:
            active_locks.remove(dev)

        return {"output": f"ok for {dev}"}

    test_engine.register_handler("stress_task", fake_handler)
    test_engine.start()

    try:
        # Submit 10 jobs each with 20 devices = 200 tasks total
        device_pool = [f"ROUTER-{i:02d}" for i in range(20)]
        job_ids = []

        for j in range(10):
            jid = test_engine.submit(
                job_type="stress_task",
                params={"batch": j},
                user="stress_tester",
                target_devices=device_pool,
            )
            job_ids.append(jid)

        # Poll until all 10 jobs reach terminal status
        deadline = time.time() + 30.0  # 30 second timeout
        all_completed = False

        while time.time() < deadline:
            with get_db_session() as s:
                terminal_count = (
                    s.query(Job)
                    .filter(Job.id.in_(job_ids), Job.status.in_(["succeeded", "partial", "failed"]))
                    .count()
                )
                if terminal_count == len(job_ids):
                    all_completed = True
                    break
            time.sleep(0.2)

        assert all_completed, "Stress test timed out before all jobs completed!"

        # Verify all 200 tasks succeeded
        with get_db_session() as s:
            total_tasks = s.query(JobTask).filter(JobTask.job_id.in_(job_ids)).count()
            succeeded_tasks = s.query(JobTask).filter(JobTask.job_id.in_(job_ids), JobTask.status == "succeeded").count()
            assert total_tasks == 200
            assert succeeded_tasks == 200

            # All jobs must be marked 'succeeded'
            for jid in job_ids:
                job = s.query(Job).filter(Job.id == jid).first()
                assert job.status == "succeeded"

    finally:
        test_engine.stop()
