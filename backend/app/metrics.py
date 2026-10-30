"""Prometheus-compatible metrics collector and text exposition format generator (Step 2.6).
Provides job counts, task duration histogram, SSH failures, and lock contention metrics.
"""
import threading
from typing import Dict, List, Optional
from sqlalchemy import func

from backend.app.extensions import get_db_session
from backend.app.models.job import Job, JobTask

_METRICS_LOCK = threading.Lock()

# Duration histogram buckets in seconds
DURATION_BUCKETS = [0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]

# In-memory metric collectors
_ssh_failures_total: Dict[str, int] = {}
_device_lock_waits_total: int = 0
_task_duration_bucket_counts: Dict[float, int] = {b: 0 for b in DURATION_BUCKETS}
_task_duration_sum: float = 0.0
_task_duration_count: int = 0


def record_ssh_failure(reason: str) -> None:
    """Record an SSH connection or command execution failure by error class."""
    clean_reason = (reason or "generic_error").lower().replace(" ", "_")[:50]
    with _METRICS_LOCK:
        _ssh_failures_total[clean_reason] = _ssh_failures_total.get(clean_reason, 0) + 1


def record_device_lock_wait() -> None:
    """Record a device lock wait contention event."""
    global _device_lock_waits_total
    with _METRICS_LOCK:
        _device_lock_waits_total += 1


def record_task_duration(seconds: float) -> None:
    """Record task execution duration into the Prometheus histogram."""
    global _task_duration_sum, _task_duration_count
    if seconds < 0:
        seconds = 0.0
    with _METRICS_LOCK:
        _task_duration_sum += seconds
        _task_duration_count += 1
        for b in DURATION_BUCKETS:
            if seconds <= b:
                _task_duration_bucket_counts[b] += 1


def get_job_counts_from_db() -> Dict[tuple, int]:
    """Query live job counts grouped by type and status from database."""
    counts = {}
    try:
        with get_db_session() as session:
            rows = (
                session.query(Job.type, Job.status, func.count(Job.id))
                .group_by(Job.type, Job.status)
                .all()
            )
            for j_type, j_status, count in rows:
                counts[(j_type, j_status)] = count
    except Exception:
        pass
    return counts


def generate_prometheus_metrics() -> str:
    """Generate Prometheus text exposition format (version 0.0.4)."""
    lines: List[str] = []

    # 1. Job counts by type and status
    lines.append("# HELP webdash_jobs_total Total number of jobs created by type and status.")
    lines.append("# TYPE webdash_jobs_total counter")
    job_counts = get_job_counts_from_db()
    if not job_counts:
        # Default entry to establish metric presence
        lines.append('webdash_jobs_total{type="unknown",status="none"} 0')
    else:
        for (j_type, j_status), cnt in sorted(job_counts.items()):
            lines.append(f'webdash_jobs_total{{type="{j_type}",status="{j_status}"}} {cnt}')

    # 2. SSH failures by reason / error class
    lines.append("# HELP webdash_ssh_failures_total Total SSH communication failures by error class.")
    lines.append("# TYPE webdash_ssh_failures_total counter")
    with _METRICS_LOCK:
        if not _ssh_failures_total:
            lines.append('webdash_ssh_failures_total{reason="none"} 0')
        else:
            for r, val in sorted(_ssh_failures_total.items()):
                lines.append(f'webdash_ssh_failures_total{{reason="{r}"}} {val}')

    # 3. Device lock waits
    lines.append("# HELP webdash_device_lock_waits_total Total times a worker waited for a device lock.")
    lines.append("# TYPE webdash_device_lock_waits_total counter")
    with _METRICS_LOCK:
        lines.append(f"webdash_device_lock_waits_total {_device_lock_waits_total}")

    # 4. Task duration histogram
    lines.append("# HELP webdash_task_duration_seconds Task execution duration in seconds.")
    lines.append("# TYPE webdash_task_duration_seconds histogram")
    with _METRICS_LOCK:
        cum_count = 0
        for b in DURATION_BUCKETS:
            cum_count = _task_duration_bucket_counts[b]
            lines.append(f'webdash_task_duration_seconds_bucket{{le="{b}"}} {cum_count}')
        # +Inf bucket equals total count
        lines.append(f'webdash_task_duration_seconds_bucket{{le="+Inf"}} {_task_duration_count}')
        lines.append(f"webdash_task_duration_seconds_sum {_task_duration_sum:.4f}")
        lines.append(f"webdash_task_duration_seconds_count {_task_duration_count}")

    lines.append("")  # trailing newline required by Prometheus format
    return "\n".join(lines)
