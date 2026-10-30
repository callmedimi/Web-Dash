"""Per-device mutex and distributed lock management (Target Architecture §5).
Ensures only one active configuration or execution session per device at a time.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.app.models.device import DeviceLock

logger = logging.getLogger(__name__)

STALE_LOCK_TIMEOUT_SECONDS = 600  # 10 minutes


def acquire_device_lock(
    session: Session,
    device_name: str,
    task_id: str,
    stale_seconds: int = STALE_LOCK_TIMEOUT_SECONDS,
) -> bool:
    """
    Attempt to acquire exclusive lock on a device.
    If existing lock is older than stale_seconds without heartbeat, reclaims it.
    Returns True if acquired, False otherwise.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lock = session.query(DeviceLock).filter(DeviceLock.device_name == device_name).first()

    if lock:
        # Check if lock belongs to the same task
        if lock.owner_task_id == task_id:
            lock.heartbeat_at = now
            session.flush()
            return True

        # Check if lock is stale
        heartbeat = lock.heartbeat_at or lock.acquired_at
        age_seconds = (now - heartbeat).total_seconds()
        if age_seconds > stale_seconds:
            logger.warning(
                "Reclaiming stale lock on device '%s' (owner was %s, idle for %.1f s)",
                device_name,
                lock.owner_task_id,
                age_seconds,
            )
            lock.owner_task_id = task_id
            lock.acquired_at = now
            lock.heartbeat_at = now
            session.flush()
            return True

        return False

    # Create new lock
    try:
        new_lock = DeviceLock(
            device_name=device_name,
            owner_task_id=task_id,
            acquired_at=now,
            heartbeat_at=now,
        )
        session.add(new_lock)
        session.flush()
        return True
    except Exception as exc:
        logger.debug("Failed to acquire lock for %s (likely race condition): %s", device_name, exc)
        session.rollback()
        return False


def release_device_lock(session: Session, device_name: str, task_id: str) -> bool:
    """Release device lock if owned by task_id."""
    lock = session.query(DeviceLock).filter(
        DeviceLock.device_name == device_name,
        DeviceLock.owner_task_id == task_id,
    ).first()

    if lock:
        session.delete(lock)
        session.flush()
        return True
    return False


def heartbeat_device_lock(session: Session, device_name: str, task_id: str) -> bool:
    """Update heartbeat timestamp for active device lock."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lock = session.query(DeviceLock).filter(
        DeviceLock.device_name == device_name,
        DeviceLock.owner_task_id == task_id,
    ).first()

    if lock:
        lock.heartbeat_at = now
        session.flush()
        return True
    return False


def cleanup_all_device_locks(session: Session, task_id: Optional[str] = None) -> int:
    """Clean up locks. If task_id provided, cleans only that task's locks; otherwise all locks."""
    query = session.query(DeviceLock)
    if task_id:
        query = query.filter(DeviceLock.owner_task_id == task_id)
    count = query.delete(synchronize_session=False)
    session.flush()
    return count
