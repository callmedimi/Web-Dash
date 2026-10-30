"""Authentication Blueprint (login, logout, me, change-password)."""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash

from backend.app.api.common import get_client_ip, get_json_payload
from auth import (
    authenticate,
    login_required,
    validate_password,
    check_login_rate_limit,
    record_failed_login,
    record_successful_login,
    get_accessible_features,
    update_user,
    _load_users,
    _find_user,
)
from audit import record_audit
from settings import is_read_only_mode

auth_bp = Blueprint("auth_api", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    client_ip = get_client_ip()
    data = get_json_payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password required", "code": "VALIDATION_ERROR"}), 400

    # Rate limiting / brute-force lockout check (F-04)
    is_locked, remaining_secs = check_login_rate_limit(username, client_ip)
    if is_locked:
        record_audit(
            "login_blocked_rate_limit",
            username,
            client_ip,
            status="blocked",
            detail={"locked_until_seconds": remaining_secs},
        )
        return jsonify({
            "error": "Too many failed login attempts. Account temporarily locked for 15 minutes.",
            "code": "TOO_MANY_REQUESTS",
            "message": "Too many failed login attempts. Please try again later.",
        }), 429

    user_info = authenticate(username, password)
    if user_info is None:
        failed_count, is_now_locked, lock_secs = record_failed_login(username, client_ip)
        record_audit(
            "login_failed",
            username,
            client_ip,
            status="fail",
            detail={"failed_attempts": failed_count},
        )
        if is_now_locked:
            record_audit(
                "account_locked",
                username,
                client_ip,
                status="fail",
                detail={"duration_seconds": lock_secs},
            )
        return jsonify({"error": "Invalid credentials", "code": "INVALID_CREDENTIALS"}), 401

    record_successful_login(username, client_ip)
    record_audit("login_success", username, client_ip, status="success")

    session.clear()  # Session fixation defense
    session.permanent = True
    session["username"] = user_info["username"]
    session["token_version"] = user_info.get("token_version", 1)
    session["csrf_token"] = secrets.token_hex(32)
    session["last_seen"] = datetime.now().timestamp()
    session["user"] = user_info

    return jsonify({
        "username": username,
        "role": user_info["role"],
        "display_name": user_info["display_name"],
        "must_change_password": user_info.get("must_change_password", False),
        "features": get_accessible_features(user_info),
        "csrf_token": session["csrf_token"],
        "read_only": is_read_only_mode(),
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    username = session.get("username") or "anonymous"
    client_ip = get_client_ip()
    record_audit("logout", username, client_ip, status="success")
    session.clear()
    return jsonify({"status": "logged_out"})


@auth_bp.route("/me", methods=["GET"])
def current_user():
    user_info = session.get("user")
    if user_info is None:
        return jsonify({"authenticated": False, "read_only": is_read_only_mode()}), 200
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return jsonify({
        "authenticated": True,
        "username": user_info["username"],
        "role": user_info["role"],
        "display_name": user_info["display_name"],
        "must_change_password": user_info.get("must_change_password", False),
        "features": get_accessible_features(user_info),
        "csrf_token": session["csrf_token"],
        "read_only": is_read_only_mode(),
    })


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = get_json_payload()
    current_pass = data.get("current_password") or ""
    new_pass = data.get("new_password") or ""

    user_info = session.get("user", {})
    username = user_info.get("username", "")

    users = _load_users()
    actual = _find_user(users, username)
    if not actual or not check_password_hash(users[actual]["password"], current_pass):
        return jsonify({"error": "Current password incorrect"}), 400

    policy_err = validate_password(new_pass, username)
    if policy_err:
        return jsonify({"error": policy_err}), 400

    err = update_user(username, {"password": new_pass, "must_change_password": False})
    if err:
        return jsonify({"error": err}), 400

    # User's token_version was bumped, update current session to match
    updated_users = _load_users()
    session["token_version"] = updated_users[actual].get("token_version", 1)
    user_info["must_change_password"] = False
    session["user"] = user_info
    record_audit("password_changed", username, get_client_ip(), status="success")
    return jsonify({"status": "password_changed", "message": "Password updated successfully"})
