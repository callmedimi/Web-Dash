"""User & Permission Management Blueprint."""
from flask import Blueprint, jsonify, session, request

from backend.app.api.common import get_client_ip, get_json_payload
from auth import (
    permission_required,
    get_all_users,
    create_user,
    update_user,
    delete_user,
    DEFAULT_FEATURES,
)
from audit import record_audit, get_audit_entries

users_bp = Blueprint("users_api", __name__, url_prefix="/admin")


@users_bp.route("/users", methods=["GET"])
@permission_required("user_management")
def admin_list_users():
    users = get_all_users()
    return jsonify({"users": users})


@users_bp.route("/users", methods=["POST"])
@permission_required("user_management")
def admin_create_user():
    data = get_json_payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()
    display_name = (data.get("display_name") or "").strip()
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if role not in ("god", "admin", "user"):
        return jsonify({"error": "Invalid role"}), 400
    err = create_user(username, password, role, display_name)
    if err:
        return jsonify({"error": err}), 409
    current_admin = session.get("username") or "admin"
    record_audit(
        "user_created",
        current_admin,
        get_client_ip(),
        status="success",
        detail={"target_user": username, "role": role},
    )
    return jsonify({"status": "created"})


@users_bp.route("/users/<username>", methods=["PUT"])
@permission_required("user_management")
def admin_update_user(username):
    raw_data = get_json_payload()
    current_info = session.get("user", {})

    # Whitelist keys: {role, display_name, password, is_active} (F-07)
    allowed_keys = {"role", "display_name", "password", "is_active"}
    data = {k: raw_data[k] for k in allowed_keys if k in raw_data}

    # Validate role if provided
    if "role" in data:
        role = str(data["role"]).strip()
        if role not in ("god", "admin", "user"):
            return jsonify({
                "error": f"Invalid role '{role}'. Role must be one of: god, admin, user",
                "code": "VALIDATION_ERROR",
            }), 400
        data["role"] = role

    # Validate is_active if provided
    if "is_active" in data and not isinstance(data["is_active"], bool):
        return jsonify({
            "error": "is_active must be a boolean",
            "code": "VALIDATION_ERROR",
        }), 400

    if (
        username == current_info.get("username")
        and data.get("role")
        and data["role"] != current_info.get("role")
    ):
        return jsonify({"error": "Cannot change your own role", "code": "FORBIDDEN"}), 403

    err = update_user(username, data)
    if err:
        if "User not found" in err:
            return jsonify({"error": err, "code": "NOT_FOUND"}), 404
        if "Cannot demote" in err or "Cannot disable" in err:
            return jsonify({"error": err, "code": "FORBIDDEN"}), 400
        return jsonify({"error": err, "code": "VALIDATION_ERROR"}), 400

    current_admin = session.get("username") or "admin"
    fields_changed = [k for k in data.keys() if k != "password"]
    if "password" in data and data["password"]:
        fields_changed.append("password")
    record_audit(
        "user_updated",
        current_admin,
        get_client_ip(),
        status="success",
        detail={"target_user": username, "fields_changed": fields_changed},
    )
    return jsonify({"status": "updated"})


@users_bp.route("/users/<username>", methods=["DELETE"])
@permission_required("user_management")
def admin_delete_user(username):
    current_info = session.get("user", {})
    if username == current_info.get("username"):
        return jsonify({"error": "Cannot delete yourself"}), 403
    err = delete_user(username)
    if err:
        return jsonify({"error": err}), 400
    current_admin = session.get("username") or "admin"
    record_audit(
        "user_deleted",
        current_admin,
        get_client_ip(),
        status="success",
        detail={"target_user": username},
    )
    return jsonify({"status": "deleted"})


@users_bp.route("/permissions", methods=["GET"])
@permission_required("permission_management")
def admin_get_permissions():
    users = get_all_users()
    clean = {}
    for username, info in users.items():
        clean[username] = {
            "role": info["role"],
            "display_name": info["display_name"],
            "permissions": info.get("permissions", {}),
        }
    return jsonify({"users": clean})


@users_bp.route("/permissions/<username>", methods=["PUT"])
@permission_required("permission_management")
def admin_set_permissions(username):
    raw_payload = get_json_payload()
    if not isinstance(raw_payload, dict):
        return jsonify({"error": "Payload must be a JSON object", "code": "VALIDATION_ERROR"}), 400

    raw_perms = raw_payload.get("permissions") if "permissions" in raw_payload else raw_payload
    if not isinstance(raw_perms, dict):
        return jsonify({
            "error": "Permissions must be an object of {feature: boolean}",
            "code": "VALIDATION_ERROR",
        }), 400

    clean_perms = {}
    for feat, val in raw_perms.items():
        if feat not in DEFAULT_FEATURES:
            return jsonify({
                "error": f"Invalid feature '{feat}'. Must be in DEFAULT_FEATURES.",
                "code": "VALIDATION_ERROR",
            }), 400
        if not isinstance(val, bool):
            return jsonify({
                "error": f"Permission for '{feat}' must be a boolean",
                "code": "VALIDATION_ERROR",
            }), 400
        clean_perms[feat] = val

    users = get_all_users()
    if username not in users:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404

    err = update_user(username, {"permissions": clean_perms})
    if err:
        return jsonify({"error": err, "code": "VALIDATION_ERROR"}), 400

    current_admin = session.get("username") or "admin"
    record_audit(
        "permissions_updated",
        current_admin,
        get_client_ip(),
        status="success",
        detail={"target_user": username},
    )
    return jsonify({"status": "updated"})


@users_bp.route("/audit-log", methods=["GET"])
@permission_required("user_management")
def admin_audit_log():
    limit = int(request.args.get("limit", 100))
    entries = get_audit_entries(limit=limit)
    return jsonify({"entries": entries, "count": len(entries)})
