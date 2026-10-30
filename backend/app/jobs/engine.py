"""Central Job Engine and Worker Pool (Target Architecture §5)."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from backend.app.config import settings
from backend.app.db.session import get_db_session
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.models.device import DeviceLock
from backend.app.jobs.queue import task_queue
from backend.app.jobs.worker import execute_task, rollup_job_status
from backend.app.jobs.cancel import request_job_cancellation
from backend.app.jobs.locks import cleanup_all_device_locks

logger = logging.getLogger(__name__)


class JobEngine:
    """Central Job orchestration engine, managing worker threads, handlers, and lifecycle."""

    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or settings.max_ssh_workers
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._pool: Optional[ThreadPoolExecutor] = None
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._active_task_futures = set()
        self._lock = threading.Lock()

    def register_handler(self, job_type: str, handler_fn: Callable) -> None:
        """Register a handler function for a given job type."""
        self._handlers[job_type] = handler_fn
        logger.debug("Registered task handler for job type '%s'", job_type)

    def submit(
        self,
        job_type: str,
        params: Dict[str, Any],
        user: str,
        mode: str = "dry_run",
        target_devices: Optional[List[str]] = None,
        parent_job_id: Optional[str] = None,
    ) -> str:
        """
        Submit a new job. Inserts Job (queued) + one JobTask per target device.
        Returns the generated UUID4 job_id.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        devices = target_devices or ["default"]

        with get_db_session() as session:
            job = Job(
                type=job_type,
                status="queued",
                mode=mode,
                created_by=user,
                created_at=now,
                params=params,
                summary={"total": len(devices), "succeeded": 0, "failed": 0, "cancelled": 0},
                parent_job_id=parent_job_id,
            )
            session.add(job)
            session.flush()

            for dev in devices:
                task = JobTask(
                    job_id=job.id,
                    device_name=dev,
                    status="queued",
                    not_before=now,
                )
                session.add(task)

            session.commit()
            job_id = job.id

        logger.info(
            "Submitted job %s of type '%s' with %d tasks (mode: %s, user: %s)",
            job_id,
            job_type,
            len(devices),
            mode,
            user,
        )
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Request cancellation of a job."""
        with get_db_session() as session:
            return request_job_cancellation(session, job_id)

    def recover_on_startup(self) -> int:
        """
        Startup recovery: find tasks left in 'running' status,
        mark them as 'failed' with error 'interrupted by restart', and release device locks.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        recovered_count = 0

        with get_db_session() as session:
            running_tasks = session.query(JobTask).filter(JobTask.status == "running").all()
            affected_job_ids = set()

            for t in running_tasks:
                t.status = "failed"
                t.finished_at = now
                t.error = "interrupted by restart"
                affected_job_ids.add(t.job_id)
                recovered_count += 1

            # Release all orphaned locks
            cleanup_all_device_locks(session)
            session.commit()

            # Roll-up affected jobs
            for jid in affected_job_ids:
                rollup_job_status(session, jid)

        if recovered_count > 0:
            logger.warning("Startup recovery: marked %d interrupted tasks as failed.", recovered_count)
        return recovered_count

    def purge_old_events(self, retention_days: Optional[int] = None) -> int:
        """Delete job events older than retention_days (default from settings)."""
        days = retention_days or settings.job_event_retention_days
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        with get_db_session() as session:
            count = session.query(JobEvent).filter(JobEvent.ts < cutoff).delete()
            session.commit()

        if count > 0:
            logger.info("Purged %d job events older than %d days.", count, days)
        return count

    def start(self) -> None:
        """Start the worker pool and dispatcher thread."""
        with self._lock:
            if self._running:
                return
            self._running = True

            self.recover_on_startup()
            self._pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="JobWorker")
            self._dispatcher_thread = threading.Thread(
                target=self._dispatch_loop, name="JobEngineDispatcher", daemon=True
            )
            self._dispatcher_thread.start()
            logger.info("JobEngine started with %d workers.", self.max_workers)

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop workers and dispatcher."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._pool:
            self._pool.shutdown(wait=False)
        logger.info("JobEngine stopped.")

    def _dispatch_loop(self) -> None:
        """Continuous task dispatch loop pulling ready tasks and dispatching to worker pool."""
        while self._running:
            try:
                task = None
                with get_db_session() as session:
                    task = task_queue.claim_next_task(session)
                    if task:
                        # Extract task attributes to pass safely to worker thread
                        task_id = task.id
                        job_id = task.job_id

                if task:
                    self._pool.submit(self._worker_execute, task_id, job_id)
                else:
                    time.sleep(0.1)
            except Exception as exc:
                logger.error("Error in job dispatch loop: %s", exc)
                time.sleep(0.5)

    def _worker_execute(self, task_id: str, job_id: str) -> None:
        """Worker thread entrypoint for an individual claimed task."""
        try:
            with get_db_session() as session:
                task = session.query(JobTask).filter(JobTask.id == task_id).first()
                if not task:
                    return

                job = session.query(Job).filter(Job.id == job_id).first()
                job_type = job.type if job else ""
                handler = self._handlers.get(job_type, self._default_unknown_handler)

                execute_task(session, task, handler)
        except Exception as exc:
            logger.exception("Worker execution uncaught exception: %s", exc)

    def _default_unknown_handler(self, ctx) -> Dict[str, Any]:
        raise ValueError(f"No handler registered for job type '{ctx.params.get('type')}'")


# Global engine singleton
engine = JobEngine()
