"""Append-only audit logging system for Web-Dash.

Logs security-relevant actions to DATA_DIR/audit.log in JSON lines format.
Never logs passwords or sensitive credential values.
"""
import os
import json
import threading
from datetime import datetime, timezone


LOCK = threading.Lock()
SENSITIVE_KEYS = {"password", "secret", "current_password", "new_password", "token", "key", "creds"}


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


def record_audit(action: str, user: str, ip: str, status: str = "success", detail: dict | None = None) -> None:
    """Record an event to the append-only audit.log.

    Parameters:
    - action: Name of the action (e.g., 'login_success', 'user_created', 'job_started').
    - user: Username performing or targeted by the action.
    - ip: Client IP address.
    - status: 'success' | 'fail' | 'blocked'.
    - detail: Optional arbitrary context metadata (passwords are automatically redacted).
    """
    clean_detail = _sanitize_dict(detail or {})
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user": user or "anonymous",
        "ip": ip or "unknown",
        "status": status,
        "detail": clean_detail,
    }
    audit_file = _get_audit_log_path()
    with LOCK:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_audit_entries(limit: int = 100) -> list[dict]:
    """Read the latest audit entries."""
    audit_file = _get_audit_log_path()
    with LOCK:
        if not os.path.exists(audit_file):
            return []
        entries = []
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        return entries[-limit:]
