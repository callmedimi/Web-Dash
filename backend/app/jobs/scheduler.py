"""Cron job scheduler module (driven by pycron and DB schedules table).
Enables automated periodic network tasks (e.g. updating ARP/MAC, refreshing Zabbix, license checks).
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pycron

from backend.app.db.session import get_db_session
from backend.app.models.config_change import Schedule
from backend.app.jobs.engine import engine

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages recurring cron-based tasks stored in the database."""

    def __init__(self, check_interval_seconds: float = 60.0):
        self.check_interval_seconds = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def add_schedule(
        self,
        job_type: str,
        cron_expression: str,
        params: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> int:
        """Add a new cron schedule to the database."""
        # Validate cron expression
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            pycron.is_now(cron_expression, now)
        except Exception as exc:
            raise ValueError(f"Invalid cron expression '{cron_expression}': {exc}")

        with get_db_session() as session:
            schedule = Schedule(
                job_type=job_type,
                cron=cron_expression,
                params=params or {},
                enabled=enabled,
            )
            session.add(schedule)
            session.commit()
            sid = schedule.id

        logger.info("Added schedule #%d for '%s' (%s)", sid, job_type, cron_expression)
        return sid

    def list_schedules(self) -> List[Dict[str, Any]]:
        """List all configured cron schedules."""
        with get_db_session() as session:
            items = session.query(Schedule).order_by(Schedule.id).all()
            return [
                {
                    "id": s.id,
                    "job_type": s.job_type,
                    "cron": s.cron,
                    "params": s.params,
                    "enabled": s.enabled,
                    "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                }
                for s in items
            ]

    def toggle_schedule(self, schedule_id: int, enabled: bool) -> bool:
        """Enable or disable a schedule."""
        with get_db_session() as session:
            s = session.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not s:
                return False
            s.enabled = enabled
            session.commit()
            return True

    def delete_schedule(self, schedule_id: int) -> bool:
        """Remove a schedule from database."""
        with get_db_session() as session:
            count = session.query(Schedule).filter(Schedule.id == schedule_id).delete()
            session.commit()
            return count > 0

    def trigger_now(self, schedule_id: int, user: str = "admin_manual") -> Optional[str]:
        """Trigger a scheduled task immediately on demand (Run Now)."""
        with get_db_session() as session:
            s = session.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not s:
                return None
            job_type = s.job_type
            params = s.params
            devices = params.get("devices") if isinstance(params, dict) else None

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            s.last_run_at = now
            session.commit()

        job_id = engine.submit(
            job_type=job_type,
            params=params or {},
            user=user,
            mode=params.get("mode", "apply"),
            target_devices=devices,
        )
        logger.info("Manually triggered schedule #%d -> Job %s", schedule_id, job_id)
        return job_id

    def check_and_run_due_jobs(self, current_time: Optional[datetime] = None) -> List[str]:
        """Check all active schedules and trigger jobs matching current time."""
        now = current_time or datetime.now(timezone.utc).replace(tzinfo=None)
        triggered_jobs: List[str] = []

        with get_db_session() as session:
            schedules = session.query(Schedule).filter(Schedule.enabled.is_(True)).all()
            for s in schedules:
                try:
                    if pycron.is_now(s.cron, now):
                        # Avoid double-firing in the same minute
                        if (
                            s.last_run_at
                            and s.last_run_at.strftime("%Y-%m-%d %H:%M") == now.strftime("%Y-%m-%d %H:%M")
                        ):
                            continue

                        s.last_run_at = now
                        session.commit()

                        devices = s.params.get("devices") if isinstance(s.params, dict) else None
                        job_id = engine.submit(
                            job_type=s.job_type,
                            params=s.params or {},
                            user="system_cron",
                            mode=s.params.get("mode", "apply"),
                            target_devices=devices,
                        )
                        triggered_jobs.append(job_id)
                        logger.info("Cron triggered schedule #%d (%s) -> Job %s", s.id, s.job_type, job_id)
                except Exception as exc:
                    logger.error("Error evaluating schedule #%d: %s", s.id, exc)

        return triggered_jobs

    def start(self) -> None:
        """Start background cron checker loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._scheduler_loop, name="JobScheduler", daemon=True
            )
            self._thread.start()
            logger.info("JobScheduler started (interval: %.1f s).", self.check_interval_seconds)

    def stop(self) -> None:
        """Stop background scheduler."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        logger.info("JobScheduler stopped.")

    def _scheduler_loop(self) -> None:
        while self._running:
            try:
                self.check_and_run_due_jobs()
            except Exception as exc:
                logger.error("Unexpected error in scheduler loop: %s", exc)

            # Sleep in small increments to allow quick shutdown
            for _ in range(int(self.check_interval_seconds * 2)):
                if not self._running:
                    break
                time.sleep(0.5)


# Global scheduler singleton
scheduler = JobScheduler()
