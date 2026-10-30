"""Task worker, execution context, and device-locked task runner (Target Architecture §5)."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Callable
from sqlalchemy.orm import Session

from backend.app.models.job import Job, JobTask
from backend.app.jobs.locks import (
    acquire_device_lock,
    release_device_lock,
    heartbeat_device_lock,
)
from backend.app.jobs.events import event_bus
from backend.app.jobs.cancel import is_job_cancelling

logger = logging.getLogger(__name__)


class TaskContext:
    """Execution context injected into task runner functions."""

    def __init__(
        self,
        session: Session,
        job_id: str,
        task_id: str,
        device_name: str,
        mode: str,
        params: Dict[str, Any],
        creds: Optional[Dict[str, Any]] = None,
    ):
        self.session = session
        self.job_id = job_id
        self.task_id = task_id
        self.device_name = device_name
        self.device = device_name
        self.mode = mode
        self.params = params
        self.creds = creds or {}
        self._is_cancelled = False

    def log(self, level: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Write job event to DB and stream to realtime subscribers."""
        event_bus.publish_event(
            session=self.session,
            job_id=self.job_id,
            task_id=self.task_id,
            level=level,
            message=f"[{self.device_name}] {msg}",
            data=data,
        )

    def heartbeat(self) -> None:
        """Refresh active lock heartbeat."""
        heartbeat_device_lock(self.session, self.device_name, self.task_id)

    def cancelled(self) -> bool:
        """Check if job has been cancelled mid-run."""
        if not self._is_cancelled:
            self._is_cancelled = is_job_cancelling(self.session, self.job_id)
        return self._is_cancelled


def execute_task(
    session: Session,
    task: JobTask,
    handler: Callable[[TaskContext], Dict[str, Any]],
    creds: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Execute a single task with device mutex locking, cancellation checks, and status roll-up.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = session.query(Job).filter(Job.id == task.job_id).first()
    mode = job.mode if job else "apply"
    params = job.params if job else {}

    # Check cancellation before locking
    if is_job_cancelling(session, task.job_id):
        task.status = "cancelled"
        task.finished_at = now
        task.error = "Cancelled prior to acquiring device lock"
        session.commit()
        rollup_job_status(session, task.job_id)
        return

    # Acquire device mutex
    locked = acquire_device_lock(session, task.device_name, task.id)
    if not locked:
        # Requeue task with 5-second backoff
        task.status = "queued"
        task.started_at = None
        task.not_before = now + timedelta(seconds=5)
        session.commit()
        logger.debug("Device %s is locked. Requeued task %s for +5s.", task.device_name, task.id)
        return

    ctx = TaskContext(
        session=session,
        job_id=task.job_id,
        task_id=task.id,
        device_name=task.device_name,
        mode=mode,
        params=params,
        creds=creds,
    )

    try:
        ctx.log("info", f"Started task on device (mode: {mode})")

        # Execute handler
        result = handler(ctx)

        if ctx.cancelled():
            task.status = "cancelled"
            task.error = "Cancelled mid-execution"
            ctx.log("warning", "Task stopped due to cancellation request")
        else:
            task.status = "succeeded"
            task.result = result or {}
            task.error = None
            ctx.log("info", "Task completed successfully")

    except Exception as exc:
        logger.exception("Task %s failed on %s: %s", task.id, task.device_name, exc)
        task.status = "failed"
        task.error = str(exc)
        ctx.log("error", f"Task failed: {exc}")

    finally:
        task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        release_device_lock(session, task.device_name, task.id)
        session.commit()
        rollup_job_status(session, task.job_id)


def rollup_job_status(session: Session, job_id: str) -> None:
    """
    Evaluate all tasks of the job and update overall status:
    - all succeeded -> succeeded
    - mixture of succeeded and failed/cancelled -> partial
    - all failed/cancelled -> failed
    - still running/queued tasks -> keep current status
    """
    job = session.query(Job).filter(Job.id == job_id).first()
    if not job or job.status in ("succeeded", "failed", "partial", "cancelled"):
        return

    tasks = session.query(JobTask).filter(JobTask.job_id == job_id).all()
    if not tasks:
        return

    statuses = [t.status for t in tasks]
    any_active = any(s in ("queued", "running") for s in statuses)

    if any_active:
        return  # Job is still in progress

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job.finished_at = now

    succeeded_count = sum(1 for s in statuses if s == "succeeded")
    failed_count = sum(1 for s in statuses if s == "failed")
    cancelled_count = sum(1 for s in statuses if s == "cancelled")
    total_count = len(statuses)

    job.summary = {
        "total": total_count,
        "succeeded": succeeded_count,
        "failed": failed_count,
        "cancelled": cancelled_count,
    }

    if succeeded_count == total_count:
        job.status = "succeeded"
    elif succeeded_count > 0:
        job.status = "partial"
    elif cancelled_count == total_count:
        job.status = "cancelled"
    else:
        job.status = "failed"

    session.commit()
    logger.info("Job %s rolled up to status '%s' (Summary: %s)", job_id, job.status, job.summary)
    event_bus.broadcast_done(job_id, job.status)
