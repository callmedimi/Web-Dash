import json
import os
import threading
from functools import wraps
from flask import session, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
LOCK = threading.RLock()

DEFAULT_FEATURES = [
    "alarm_clear_manual",
    "alarm_clear_bulk",
    "reporting",
    "vrf_routing",
    "license_check",
    "zabbix_search",
    "code_site_search",
    "user_management",
    "permission_management",
    "zabbix_db_refresh",
    "license_renewal_admin",
]

FEATURE_LABELS = {
    "alarm_clear_manual": "Alarm Clear — Manual Entry",
    "alarm_clear_bulk": "Alarm Clear — Bulk CSV",
    "reporting": "Reporting (Down-Links)",
    "vrf_routing": "VRF Routing Check",
    "license_check": "License Check",
    "zabbix_search": "Zabbix Interface Search",
    "code_site_search": "Code SITE Search",
    "user_management": "User Management (God only)",
    "permission_management": "Permission Management (God only)",
    "zabbix_db_refresh": "Zabbix DB Refresh",
    "license_renewal_admin": "License Renewal Admin (God, Admin only)",
}


def _load_users() -> dict:
    with LOCK:
        if not os.path.exists(USERS_FILE):
            _init_default_users()
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def _save_users(users: dict) -> None:
    with LOCK:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)


def _init_default_users() -> None:
    default = {
        "Dimi": {
            "password": generate_password_hash("god"),
            "role": "god",
            "permissions": {},
            "display_name": "God",
        }
    }
    _save_users(default)


def _find_user(users: dict, username: str) -> str | None:
    for key in users:
        if key.lower() == username.lower():
            return key
    return None


def authenticate(username: str, password: str) -> dict | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        return None
    user = users[actual]
    if not check_password_hash(user["password"], password):
        return None
    return {
        "username": actual,
        "role": user["role"],
        "permissions": user.get("permissions", {}),
        "display_name": user.get("display_name", actual),
    }


def user_has_access(user_info: dict, feature: str) -> bool:
    role = user_info.get("role", "user")
    if role == "god":
        return True
    if role == "admin":
        return feature not in ("user_management", "permission_management", "zabbix_db_refresh", "license_renewal_admin")
    perms = user_info.get("permissions", {})
    return perms.get(feature, False)


def get_accessible_features(user_info: dict) -> dict:
    result = {}
    for feat in DEFAULT_FEATURES:
        if feat == "zabbix_db_refresh":
            result[feat] = {
                "label": FEATURE_LABELS.get(feat, feat),
                "granted": user_has_access(user_info, feat),
            }
            continue
        result[feat] = {
            "label": FEATURE_LABELS.get(feat, feat),
            "granted": user_has_access(user_info, feat),
        }
    return result


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            if request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


def permission_required(feature: str):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user_info = session.get("user", {})
            if not user_has_access(user_info, feature):
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_all_users() -> dict:
    users = _load_users()
    result = {}
    for username, data in users.items():
        result[username] = {
            "role": data["role"],
            "display_name": data.get("display_name", username),
            "permissions": data.get("permissions", {}),
        }
    return result


def create_user(username: str, password: str, role: str, display_name: str = "", permissions: dict | None = None) -> str | None:
    users = _load_users()
    existing = _find_user(users, username)
    if existing:
        return f"User already exists (as '{existing}')"
    users[username] = {
        "password": generate_password_hash(password),
        "role": role,
        "permissions": permissions or {},
        "display_name": display_name or username,
    }
    _save_users(users)
    return None


def update_user(username: str, updates: dict) -> str | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        return "User not found"
    if "password" in updates and updates["password"]:
        updates["password"] = generate_password_hash(updates["password"])
    else:
        updates.pop("password", None)
    for key, value in updates.items():
        if value is not None:
            users[actual][key] = value
    _save_users(users)
    return None


def delete_user(username: str) -> str | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        return "User not found"
    if users[actual]["role"] == "god":
        return "Cannot delete god user"
    del users[actual]
    _save_users(users)
    return None
