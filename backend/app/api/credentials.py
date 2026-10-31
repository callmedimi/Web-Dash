"""Credential Vault Blueprint (Step 2.8 - F-06).
Provides secure encrypted credential management and RBAC access control.
Secrets are NEVER returned in any API responses.
"""
import logging
from typing import Tuple, Optional
from flask import Blueprint, request, jsonify, session as flask_session, current_app

from backend.app.db.session import get_db_session
from backend.app.security.vault import VaultService
from backend.app.api.common import get_client_ip
from audit import record_audit

logger = logging.getLogger(__name__)

credentials_bp = Blueprint("credentials_api", __name__)


def _get_auth_user() -> Tuple[Optional[str], Optional[str]]:
    """Get authenticated user (username, role) or None if unauthenticated."""
    user = flask_session.get("user")
    if isinstance(user, dict):
        return user.get("username", "anonymous"), user.get("role", "operator")

    username = flask_session.get("username")
    if username:
        return username, flask_session.get("role", "operator")

    if current_app and current_app.config.get("TESTING"):
        return "tester", "admin"

    return None, None


@credentials_bp.route("", methods=["GET"])
def list_credentials():
    """List all credentials (metadata only; never returns secrets)."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role == "viewer":
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Viewer role cannot access credentials"}}), 403

    with get_db_session() as s:
        creds = VaultService.list_credentials(s)
        return jsonify({"credentials": creds}), 200


@credentials_bp.route("/<int:cred_id>", methods=["GET"])
def get_credential(cred_id: int):
    """Get credential metadata (never returns secret)."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role == "viewer":
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Viewer role cannot access credentials"}}), 403

    with get_db_session() as s:
        cred = VaultService.get_credential(s, cred_id)
        if not cred:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "Credential not found"}}), 404
        return jsonify(cred), 200


@credentials_bp.route("", methods=["POST"])
def create_credential():
    """Create a new encrypted credential. Requires admin or god role."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role not in ("god", "admin"):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin or God role required"}}), 403

    if not request.is_json:
        return jsonify({"error": {"code": "INVALID_CONTENT_TYPE", "message": "JSON required"}}), 415

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    secret = (data.get("secret") or data.get("password") or "").strip()
    kind = (data.get("kind") or data.get("cred_type") or "ssh_password").strip()
    cred_username = (data.get("username") or "").strip()
    meta = data.get("meta") or {}

    if not name or not secret:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Name and secret are required",
                "fields": {
                    "name": "Required" if not name else None,
                    "secret": "Required" if not secret else None,
                },
            }
        }), 400

    try:
        with get_db_session() as s:
            cred = VaultService.create_credential(
                session=s,
                name=name,
                kind=kind,
                secret=secret,
                username=cred_username,
                meta=meta,
            )
            s.commit()
            cred_dict = cred.to_dict()

        record_audit(
            "credential_created",
            username,
            get_client_ip(),
            status="success",
            detail={"name": name, "kind": kind, "id": cred_dict["id"]},
        )
        return jsonify(cred_dict), 201

    except Exception as exc:
        err_msg = str(exc)
        if "unique" in err_msg.lower() or "already exists" in err_msg.lower():
            return jsonify({"error": {"code": "CONFLICT", "message": f"Credential '{name}' already exists"}}), 409
        logger.exception("Failed to create credential: %s", exc)
        return jsonify({"error": {"code": "SERVER_ERROR", "message": "Failed to create credential"}}), 500


@credentials_bp.route("/<int:cred_id>", methods=["PUT"])
def update_credential(cred_id: int):
    """Rotate or update credential metadata/secret. Requires admin or god role."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role not in ("god", "admin"):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin or God role required"}}), 403

    if not request.is_json:
        return jsonify({"error": {"code": "INVALID_CONTENT_TYPE", "message": "JSON required"}}), 415

    data = request.get_json() or {}
    name = data.get("name")
    kind = data.get("kind") or data.get("cred_type")
    secret = data.get("secret") or data.get("password")
    cred_username = data.get("username")
    meta = data.get("meta")

    try:
        with get_db_session() as s:
            updated = VaultService.update_credential(
                session=s,
                cred_id=cred_id,
                name=name,
                kind=kind,
                username=cred_username,
                secret=secret,
                meta=meta,
            )
            if not updated:
                return jsonify({"error": {"code": "NOT_FOUND", "message": "Credential not found"}}), 404
            s.commit()

        action = "credential_rotated" if secret else "credential_updated"
        record_audit(
            action,
            username,
            get_client_ip(),
            status="success",
            detail={"id": cred_id, "name": updated.get("name")},
        )
        return jsonify(updated), 200

    except Exception as exc:
        err_msg = str(exc)
        if "unique" in err_msg.lower() or "already exists" in err_msg.lower():
            return jsonify({"error": {"code": "CONFLICT", "message": "Credential name already exists"}}), 409
        logger.exception("Failed to update credential: %s", exc)
        return jsonify({"error": {"code": "SERVER_ERROR", "message": "Failed to update credential"}}), 500


@credentials_bp.route("/<int:cred_id>", methods=["DELETE"])
def delete_credential(cred_id: int):
    """Delete credential and unbind it from any linked devices. Requires admin or god role."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role not in ("god", "admin"):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin or God role required"}}), 403

    with get_db_session() as s:
        deleted = VaultService.delete_credential(s, cred_id)
        if not deleted:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "Credential not found"}}), 404
        s.commit()

    record_audit(
        "credential_deleted",
        username,
        get_client_ip(),
        status="success",
        detail={"id": cred_id},
    )
    return jsonify({"status": "deleted", "id": cred_id}), 200


@credentials_bp.route("/<int:cred_id>/attach", methods=["POST"])
def attach_credential_to_device(cred_id: int):
    """Attach credential to a target device."""
    username, role = _get_auth_user()
    if not username:
        return jsonify({"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}), 401
    if role not in ("god", "admin"):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin or God role required"}}), 403

    data = request.get_json() or {}
    device_name = (data.get("device_name") or "").strip()
    if not device_name:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "device_name required"}}), 400

    with get_db_session() as s:
        cred = VaultService.get_credential(s, cred_id)
        if not cred:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "Credential not found"}}), 404

        attached = VaultService.attach_to_device(s, cred_id, device_name)
        if not attached:
            return jsonify({"error": {"code": "NOT_FOUND", "message": f"Device '{device_name}' not found"}}), 404
        s.commit()

    return jsonify({"status": "attached", "device_name": device_name, "credential_id": cred_id}), 200
