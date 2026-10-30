"""Fair scheduling and atomic task claiming from DB (Target Architecture §5)."""
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, update

from backend.app.models.job import Job, JobTask

logger = logging.getLogger(__name__)


class TaskQueue:
    """Manages fair task dispatching and atomic status claims from the DB."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_job_index = 0

    def claim_next_task(self, session: Session) -> Optional[JobTask]:
        """
        Pull and claim one ready task using fair round-robin scheduling across active jobs.
        Atomically transitions task status from 'queued' to 'running'.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Find all active jobs that have queued tasks ready to run
        ready_condition = and_(
            JobTask.status == "queued",
            or_(JobTask.not_before.is_(None), JobTask.not_before <= now),
        )

        with self._lock:
            active_job_ids: List[str] = [
                r[0]
                for r in session.query(JobTask.job_id)
                .join(Job, Job.id == JobTask.job_id)
                .filter(ready_condition, Job.status.in_(["queued", "running"]))
                .distinct()
                .order_by(Job.created_at)
                .all()
            ]

            if not active_job_ids:
                return None

            # Round-robin selection of job
            self._last_job_index = self._last_job_index % len(active_job_ids)
            chosen_job_id = active_job_ids[self._last_job_index]
            self._last_job_index = (self._last_job_index + 1) % len(active_job_ids)

        # 2. Select the oldest ready task for this chosen job
        candidate_task = (
            session.query(JobTask)
            .filter(JobTask.job_id == chosen_job_id, ready_condition)
            .order_by(JobTask.started_at.asc().nullsfirst(), JobTask.id.asc())
            .first()
        )

        if not candidate_task:
            return None

        # 3. Atomic claim with UPDATE ... WHERE id = :id AND status = 'queued'
        stmt = (
            update(JobTask)
            .where(JobTask.id == candidate_task.id, JobTask.status == "queued")
            .values(status="running", started_at=now)
        )
        result = session.execute(stmt)
        session.flush()

        if result.rowcount == 1:
            # Also ensure parent job is marked as 'running'
            job = session.query(Job).filter(Job.id == chosen_job_id).first()
            if job and job.status == "queued":
                job.status = "running"
                if not job.started_at:
                    job.started_at = now
                session.flush()

            # Refresh and return the claimed task
            session.refresh(candidate_task)
            return candidate_task

        return None


# Global queue instance
task_queue = TaskQueue()
