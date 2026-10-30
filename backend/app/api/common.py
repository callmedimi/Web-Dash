"""Shared API utilities, decorators, and request payload helpers."""
import json
import logging
from functools import wraps
from flask import request, jsonify, abort, Response
from werkzeug.exceptions import RequestEntityTooLarge

from settings import is_read_only_mode

logger = logging.getLogger(__name__)


def get_client_ip() -> str:
    """Extract real client IP address respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def get_json_payload(silent: bool = False) -> dict:
    """
    Extract and validate JSON payload from request body.
    Enforces Content-Type: application/json (HTTP 415 otherwise).
    Returns HTTP 400 on malformed JSON.
    """
    content_type = request.headers.get("Content-Type", "")
    if not (request.is_json or content_type.lower().startswith("application/json")):
        if silent:
            return {}
        abort(
            Response(
                json.dumps({
                    "error": "Unsupported Media Type",
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": "Content-Type must be application/json",
                }),
                status=415,
                mimetype="application/json",
            )
        )
    try:
        data = request.get_json(force=False, silent=False)
        return data if data is not None else {}
    except RequestEntityTooLarge:
        raise
    except Exception as e:
        if silent:
            return {}
        abort(
            Response(
                json.dumps({
                    "error": "Bad Request",
                    "code": "INVALID_JSON",
                    "message": f"Malformed JSON: {e}",
                }),
                status=400,
                mimetype="application/json",
            )
        )


def read_only_blocked(f):
    """Safety kill-switch decorator: blocks device-modifying operations when READ_ONLY_MODE is enabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_read_only_mode():
            return (
                jsonify({
                    "error": {
                        "code": "READ_ONLY",
                        "message": "System is running in READ-ONLY mode. Device-modifying operations are disabled.",
                        "fields": {},
                    },
                    "code": "READ_ONLY",
                    "message": "System is running in READ-ONLY mode. Device-modifying operations are disabled.",
                }),
                403,
            )
        return f(*args, **kwargs)

    return decorated


def parse_csv_to_routers(file_storage) -> tuple[list[dict], str | None]:
    """Parse Huawei CSV node export file into normalized router dicts."""
    import csv
    import re

    raw = file_storage.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    lines = text.splitlines()

    def _clean(line: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)

    header_idx = -1
    for i, line in enumerate(lines):
        if _clean(line).strip().startswith("NE Name,"):
            header_idx = i
            break

    if header_idx == -1:
        return [], "Could not find header row starting with 'NE Name,'"

    cleaned = [_clean(l) for l in lines]
    reader = csv.DictReader(cleaned[header_idx:])
    if "NE Name" not in (reader.fieldnames or []):
        return [], f"'NE Name' not in parsed headers: {reader.fieldnames}"

    routers = []
    for row in reader:
        ne = row.get("NE Name", "").strip()
        ip = row.get("NE IP Address", "").strip()
        if not ne or not ip:
            continue
        esn_val = (
            row.get("ESN")
            or row.get("esn")
            or row.get("Serial Number")
            or row.get("Equipment ESN")
            or row.get("NE ESN")
            or ""
        ).strip()
        routers.append({
            "name": ne,
            "ip": ip,
            "ne_type": row.get("NE Type (MPU Type)", "").strip(),
            "version": row.get("Software Version", "").strip(),
            "lsr_id": row.get("LSR ID", "").strip(),
            "esn": esn_val,
        })

    return routers, None


def resolve_request_credentials(data: dict) -> tuple[str, str]:
    """
    Extract (username, password) from request body, either via:
    1. Direct 'credential_id' pointing to encrypted vault (Step 2.8)
    2. Legacy 'username' and 'password' (logs deprecation warning for F-06)
    """
    cred_id = data.get("credential_id")
    if cred_id:
        try:
            from backend.app.db.session import get_db_session
            from backend.app.security.vault import VaultService
            with get_db_session() as session:
                username, password = VaultService.get_decrypted_secret(session, int(cred_id))
                return username, password
        except Exception as exc:
            logger.warning("Failed to resolve credential_id %s: %s", cred_id, exc)

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if password:
        logger.warning(
            "DEPRECATION [F-06]: Endpoint %s received plaintext password in request body. Migrate to vault credential_id.",
            request.path if request else "unknown",
        )
    return username, password
