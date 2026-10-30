"""Job cancellation logic and status queries (Target Architecture §5)."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.models.job import Job, JobTask
from backend.app.jobs.events import event_bus

logger = logging.getLogger(__name__)


def request_job_cancellation(session: Session, job_id: str) -> bool:
    """
    Cancel an active or queued job.
    Queued tasks are immediately marked as 'cancelled'.
    Running tasks will observe the cancellation token and halt at next checkpoint.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = session.query(Job).filter(Job.id == job_id).first()
    if not job:
        return False

    if job.status in ("succeeded", "failed", "cancelled"):
        logger.info("Job %s is already in terminal state '%s'; cannot cancel.", job_id, job.status)
        return False

    job.status = "cancelling"

    # Immediately mark all queued tasks as cancelled
    queued_tasks = session.query(JobTask).filter(
        JobTask.job_id == job_id,
        JobTask.status == "queued",
    ).all()

    for task in queued_tasks:
        task.status = "cancelled"
        task.finished_at = now
        task.error = "Cancelled before execution"

    session.flush()

    event_bus.publish_event(
        session=session,
        job_id=job_id,
        task_id=None,
        level="warning",
        message="Cancellation requested. Aborting remaining tasks.",
    )

    logger.info("Cancellation requested for job %s. Cancelled %d queued tasks.", job_id, len(queued_tasks))
    return True


def is_job_cancelling(session: Session, job_id: str) -> bool:
    """Check if job has been marked as cancelling or cancelled."""
    status = session.query(Job.status).filter(Job.id == job_id).scalar()
    return status in ("cancelling", "cancelled")
