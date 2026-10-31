"""Cron job scheduler module (driven by pycron and DB schedules table).
Enables automated periodic network tasks (e.g. updating ARP/MAC, refreshing Zabbix, license checks).
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import pycron

from backend.app.db.session import get_db_session
from backend.app.models.config_change import Schedule, SchedulerLease
from backend.app.jobs.engine import engine

logger = logging.getLogger(__name__)


def validate_cron_expression(cron_expr: str) -> None:
    """Validate 5-field cron expression syntax and bounds."""
    if not isinstance(cron_expr, str) or not cron_expr.strip():
        raise ValueError("Invalid cron expression: must be a non-empty string")

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression '{cron_expr}': expected 5 fields, got {len(parts)}")

    field_ranges = [
        (0, 59, "minute"),
        (0, 23, "hour"),
        (1, 31, "day-of-month"),
        (1, 12, "month"),
        (0, 7, "day-of-week"),
    ]

    for part, (min_val, max_val, name) in zip(parts, field_ranges):
        subparts = part.split(",")
        for sub in subparts:
            if not sub:
                raise ValueError(f"Invalid cron expression '{cron_expr}': empty token in {name}")

            # Handle step (e.g. */15 or 1-10/2)
            step_parts = sub.split("/")
            if len(step_parts) > 2:
                raise ValueError(f"Invalid cron expression '{cron_expr}': multiple steps in {name}")
            if len(step_parts) == 2:
                step = step_parts[1]
                if not step.isdigit() or int(step) <= 0:
                    raise ValueError(f"Invalid cron expression '{cron_expr}': invalid step '{step}' in {name}")
                base = step_parts[0]
            else:
                base = step_parts[0]

            if base == "*":
                continue

            # Handle range (e.g. 1-5)
            if "-" in base:
                range_parts = base.split("-")
                if len(range_parts) != 2 or not range_parts[0].isdigit() or not range_parts[1].isdigit():
                    raise ValueError(f"Invalid cron expression '{cron_expr}': invalid range '{base}' in {name}")
                start, end = int(range_parts[0]), int(range_parts[1])
                if not (min_val <= start <= max_val and min_val <= end <= max_val and start <= end):
                    raise ValueError(f"Invalid cron expression '{cron_expr}': range {start}-{end} out of bounds ({min_val}-{max_val}) for {name}")
            else:
                if not base.isdigit():
                    raise ValueError(f"Invalid cron expression '{cron_expr}': invalid token '{base}' in {name}")
                val = int(base)
                if not (min_val <= val <= max_val):
                    raise ValueError(f"Invalid cron expression '{cron_expr}': value {val} out of bounds ({min_val}-{max_val}) for {name}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        pycron.is_now(cron_expr, now)
    except Exception as exc:
        raise ValueError(f"Invalid cron expression '{cron_expr}': {exc}")


class JobScheduler:
    """Manages recurring cron-based tasks stored in the database with single leader lease."""

    def __init__(self, check_interval_seconds: float = 60.0, worker_id: Optional[str] = None):
        self.check_interval_seconds = check_interval_seconds
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def acquire_or_renew_lease(
        self,
        lease_duration_seconds: int = 30,
        worker_id: Optional[str] = None,
        db_session: Optional[Any] = None,
    ) -> bool:
        """
        Attempt to acquire or renew leader lease in DB.
        Returns True if this worker is the elected leader, False otherwise.
        """
        w_id = worker_id or self.worker_id
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = now + timedelta(seconds=lease_duration_seconds)

        def _do_lease(session):
            lease = session.query(SchedulerLease).filter(SchedulerLease.name == "scheduler_leader").first()
            if not lease:
                lease = SchedulerLease(
                    name="scheduler_leader",
                    holder_id=w_id,
                    acquired_at=now,
                    expires_at=expires,
                )
                session.add(lease)
                session.commit()
                return True

            # If current holder is this worker, renew
            if lease.holder_id == w_id:
                lease.expires_at = expires
                session.commit()
                return True

            # If lease has expired, take over
            if lease.expires_at < now:
                logger.info("Scheduler leader lease expired (was %s), taking over as %s", lease.holder_id, w_id)
                lease.holder_id = w_id
                lease.acquired_at = now
                lease.expires_at = expires
                session.commit()
                return True

            # Lease is active and held by another worker
            return False

        if db_session:
            return _do_lease(db_session)
        with get_db_session() as session:
            return _do_lease(session)

    def release_lease(self, worker_id: Optional[str] = None, db_session: Optional[Any] = None) -> bool:
        """Release leadership lease if held by this worker."""
        w_id = worker_id or self.worker_id

        def _do_release(session):
            lease = session.query(SchedulerLease).filter(
                SchedulerLease.name == "scheduler_leader",
                SchedulerLease.holder_id == w_id,
            ).first()
            if lease:
                session.delete(lease)
                session.commit()
                return True
            return False

        if db_session:
            return _do_release(db_session)
        with get_db_session() as session:
            return _do_release(session)

    def get_leader_status(self, db_session: Optional[Any] = None) -> Dict[str, Any]:
        """Inspect current scheduler leader lease status."""
        def _get_status(session):
            lease = session.query(SchedulerLease).filter(SchedulerLease.name == "scheduler_leader").first()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if not lease:
                return {"is_leader": False, "holder_id": None, "has_lease": False, "expired": True}
            is_expired = lease.expires_at < now
            is_me = (lease.holder_id == self.worker_id) and not is_expired
            return {
                "is_leader": is_me,
                "current_worker_id": self.worker_id,
                "holder_id": lease.holder_id,
                "acquired_at": lease.acquired_at.isoformat() if lease.acquired_at else None,
                "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
                "expired": is_expired,
            }

        if db_session:
            return _get_status(db_session)
        with get_db_session() as session:
            return _get_status(session)

    def add_schedule(
        self,
        job_type: str,
        cron_expression: str,
        params: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        db_session: Optional[Any] = None,
    ) -> int:
        """Add a new cron schedule to the database."""
        validate_cron_expression(cron_expression)

        def _do_add(session):
            schedule = Schedule(
                job_type=job_type,
                cron=cron_expression,
                params=params or {},
                enabled=enabled,
            )
            session.add(schedule)
            session.commit()
            return schedule.id

        if db_session:
            sid = _do_add(db_session)
        else:
            with get_db_session() as session:
                sid = _do_add(session)

        logger.info("Added schedule #%d for '%s' (%s)", sid, job_type, cron_expression)
        return sid

    def list_schedules(self, db_session: Optional[Any] = None) -> List[Dict[str, Any]]:
        """List all configured cron schedules."""
        def _list(session):
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

        if db_session:
            return _list(db_session)
        with get_db_session() as session:
            return _list(session)

    def toggle_schedule(self, schedule_id: int, enabled: bool, db_session: Optional[Any] = None) -> bool:
        """Enable or disable a schedule."""
        def _toggle(session):
            s = session.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not s:
                return False
            s.enabled = enabled
            session.commit()
            return True

        if db_session:
            return _toggle(db_session)
        with get_db_session() as session:
            return _toggle(session)

    def delete_schedule(self, schedule_id: int, db_session: Optional[Any] = None) -> bool:
        """Remove a schedule from database."""
        def _del(session):
            count = session.query(Schedule).filter(Schedule.id == schedule_id).delete()
            session.commit()
            return count > 0

        if db_session:
            return _del(db_session)
        with get_db_session() as session:
            return _del(session)

    def trigger_now(
        self,
        schedule_id: int,
        user: str = "admin_manual",
        db_session: Optional[Any] = None,
    ) -> Optional[str]:
        """Trigger a scheduled task immediately on demand (Run Now)."""
        def _get_and_touch(session):
            s = session.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not s:
                return None
            job_type = s.job_type
            params = s.params
            devices = params.get("devices") if isinstance(params, dict) else None

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            s.last_run_at = now
            session.commit()
            return job_type, params, devices

        if db_session:
            res = _get_and_touch(db_session)
        else:
            with get_db_session() as session:
                res = _get_and_touch(session)

        if not res:
            return None
        job_type, params, devices = res

        job_id = engine.submit(
            job_type=job_type,
            params=params or {},
            user=user,
            mode=params.get("mode", "apply"),
            target_devices=devices,
        )
        logger.info("Manually triggered schedule #%d -> Job %s", schedule_id, job_id)
        return job_id

    def check_and_run_due_jobs(
        self,
        current_time: Optional[datetime] = None,
        require_leader: bool = True,
        db_session: Optional[Any] = None,
    ) -> List[str]:
        """Check all active schedules and trigger jobs matching current time (if leader)."""
        if require_leader:
            is_leader = self.acquire_or_renew_lease(db_session=db_session)
            if not is_leader:
                logger.debug("Skipping scheduler cycle: %s is not elected leader", self.worker_id)
                return []

        now = current_time or datetime.now(timezone.utc).replace(tzinfo=None)
        triggered_jobs: List[str] = []

        def _process(session):
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

        if db_session:
            _process(db_session)
        else:
            with get_db_session() as session:
                _process(session)

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
        """Stop background scheduler and release leader lease."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        try:
            self.release_lease()
        except Exception:
            pass
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
