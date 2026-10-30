"""Realtime job events and SSE broadcaster (Target Architecture §3 & §5)."""
import logging
import threading
from datetime import datetime, timezone
from queue import Queue
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from backend.app.models.job import JobEvent

logger = logging.getLogger(__name__)


class JobEventBroadcaster:
    """Thread-safe event bus distributing job events to SSE subscribers and writing to DB."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Queue]] = {}

    def subscribe(self, job_id: str) -> Queue:
        """Register a new subscriber queue for job events."""
        q: Queue = Queue(maxsize=500)
        with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            self._subscribers[job_id].append(q)
        return q

    def unsubscribe(self, job_id: str, q: Queue) -> None:
        """Unregister a subscriber queue."""
        with self._lock:
            if job_id in self._subscribers:
                try:
                    self._subscribers[job_id].remove(q)
                    if not self._subscribers[job_id]:
                        del self._subscribers[job_id]
                except ValueError:
                    pass

    def publish_event(
        self,
        session: Session,
        job_id: str,
        task_id: Optional[str],
        level: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> JobEvent:
        """Persist event to DB and broadcast to in-memory subscriber queues."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        event = JobEvent(
            job_id=job_id,
            task_id=task_id,
            ts=now,
            level=level,
            message=message,
            data=data,
        )
        session.add(event)
        session.flush()

        event_payload = event.to_dict()

        # Push to subscribers
        with self._lock:
            subscribers = list(self._subscribers.get(job_id, []))

        for q in subscribers:
            try:
                q.put_nowait(event_payload)
            except Exception:
                # Subscriber queue full; drop oldest or skip to prevent worker starvation
                pass

        return event

    def broadcast_done(self, job_id: str, final_status: str) -> None:
        """Send terminal notification to all subscribers of a completed job."""
        terminal_payload = {
            "job_id": job_id,
            "level": "system",
            "message": f"Job completed with status: {final_status}",
            "status": final_status,
            "is_terminal": True,
        }
        with self._lock:
            subscribers = list(self._subscribers.get(job_id, []))

        for q in subscribers:
            try:
                q.put_nowait(terminal_payload)
            except Exception:
                pass


# Global singleton event bus
event_bus = JobEventBroadcaster()
