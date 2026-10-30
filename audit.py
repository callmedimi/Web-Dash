"""Append-only audit logging system for Web-Dash (Target Architecture §3 & Step 2.6).

Logs security-relevant actions to relational audit_logs table with DATA_DIR/audit.log fallback.
Never logs passwords or sensitive credential values.
"""
import os
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend.app.extensions import get_db_session
from backend.app.models.audit import AuditLog

logger = logging.getLogger(__name__)

LOCK = threading.Lock()
SENSITIVE_KEYS = {
    "password",
    "secret",
    "current_password",
    "new_password",
    "token",
    "key",
    "creds",
}


def _get_audit_log_path() -> str:
    data_dir = os.environ.get("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "audit.log")


def _sanitize_dict(d: dict) -> dict:
    clean = {}
    for k, v in d.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            clean[k] = "[REDACTED]"
        elif isinstance(v, dict):
            clean[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            clean[k] = [
                _sanitize_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            clean[k] = v
    return clean


def record_audit(
    action: str,
    user: str,
    ip: str,
    status: str = "success",
    detail: Optional[dict] = None,
) -> None:
    """Record an event to the audit_logs database table and fallback audit.log file.

    Parameters:
    - action: Name of the action (e.g., 'login_success', 'user_created', 'job_started').
    - user: Username performing or targeted by the action.
    - ip: Client IP address.
    - status: 'success' | 'fail' | 'blocked'.
    - detail: Optional arbitrary context metadata (passwords are automatically redacted).
    """
    clean_detail = _sanitize_dict(detail or {})
    clean_detail["status"] = status
    user_val = user or "anonymous"
    ip_val = ip or "unknown"
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Primary write: Relational DB table
    try:
        target_val = (
            str(clean_detail.get("target") or clean_detail.get("target_user") or clean_detail.get("feature") or clean_detail.get("device") or action)
        )[:200]
        with get_db_session() as session:
            entry = AuditLog(
                ts=now_utc,
                user_id=user_val[:100],
                ip=ip_val[:50],
                action=action[:100],
                target=target_val,
                detail=clean_detail,
            )
            session.add(entry)
            session.commit()
    except Exception as exc:
        logger.warning("Could not write audit log to database (falling back to file): %s", exc)

    # 2. Dual-write fallback: JSON Lines file in DATA_DIR
    file_entry = {
        "ts": now_utc.isoformat(),
        "action": action,
        "user": user_val,
        "ip": ip_val,
        "status": status,
        "detail": clean_detail,
    }
    audit_file = _get_audit_log_path()
    try:
        with LOCK:
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(file_entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to append to audit log file: %s", exc)


def get_audit_entries(limit: int = 100) -> List[Dict[str, Any]]:
    """Read the latest audit entries, prioritizing DB with file fallback."""
    # 1. Try DB
    try:
        with get_db_session() as session:
            rows = (
                session.query(AuditLog)
                .order_by(AuditLog.id.desc())
                .limit(limit)
                .all()
            )
            if rows:
                # Return chronological order
                results = []
                for r in reversed(rows):
                    results.append({
                        "ts": r.ts.isoformat(),
                        "action": r.action,
                        "user": r.user_id,
                        "ip": r.ip,
                        "status": r.detail.get("status", "success") if isinstance(r.detail, dict) else "success",
                        "detail": r.detail,
                        "target": r.target,
                    })
                return results
    except Exception as exc:
        logger.warning("Could not query audit logs from DB, falling back to file: %s", exc)

    # 2. File fallback
    audit_file = _get_audit_log_path()
    with LOCK:
        if not os.path.exists(audit_file):
            return []
        entries = []
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
            return entries[-limit:]
        except Exception:
            return []
