"""Structured JSON logging with contextual fields (Target Architecture §2 & Step 2.6).
Provides JSON formatting with ts, level, logger, message, job_id, task_id, device, user.
"""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional, Any

# Context variables for request and background task correlation
job_id_var: ContextVar[str] = ContextVar("job_id", default="")
task_id_var: ContextVar[str] = ContextVar("task_id", default="")
device_var: ContextVar[str] = ContextVar("device", default="")
user_var: ContextVar[str] = ContextVar("user", default="")


def set_log_context(
    job_id: Optional[str] = None,
    task_id: Optional[str] = None,
    device: Optional[str] = None,
    user: Optional[str] = None,
) -> None:
    """Set logging context for current thread / async context."""
    if job_id is not None:
        job_id_var.set(str(job_id))
    if task_id is not None:
        task_id_var.set(str(task_id))
    if device is not None:
        device_var.set(str(device))
    if user is not None:
        user_var.set(str(user))


def clear_log_context() -> None:
    """Reset context variables to empty defaults."""
    job_id_var.set("")
    task_id_var.set("")
    device_var.set("")
    user_var.set("")


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with standard fields."""

    def format(self, record: logging.LogRecord) -> str:
        # Resolve contextual values: explicit extra kwargs take precedence over contextvars
        job_id = getattr(record, "job_id", None) or job_id_var.get()
        task_id = getattr(record, "task_id", None) or task_id_var.get()
        device = getattr(record, "device", None) or device_var.get()
        user = getattr(record, "user", None) or user_var.get()

        log_record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "job_id": job_id,
            "task_id": task_id,
            "device": device,
            "user": user,
        }

        # Include exception traceback if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)


def setup_logging(app: Optional[Any] = None, level: int = logging.INFO) -> None:
    """Configure root logger to use structured JSON formatter on stdout."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate JSON handlers if called multiple times
    for h in root.handlers:
        if isinstance(h.formatter, JsonFormatter):
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    if app:
        app.logger.handlers = [handler]
        app.logger.setLevel(level)
