import json
import os
import secrets
import string
import threading
import time
from functools import wraps
from flask import session, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LOCK = threading.RLock()


def _get_users_file() -> str:
    """Return the path to users.json resolved against the current DATA_DIR."""
    data_dir = os.environ.get("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "users.json")


DEFAULT_FEATURES = [
    "alarm_clear_manual",
    "alarm_clear_bulk",
    "reporting",
    "vrf_routing",
    "license_check",
    "zabbix_search",
    "code_site_search",
    "session_extractor",
    "ptp_troubleshoot",
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
    "session_extractor": "Session Extractor (SecureCRT)",
    "ptp_troubleshoot": "PTP Troubleshoot (Telecom Sync)",
    "user_management": "User Management (God only)",
    "permission_management": "Permission Management (God only)",
    "zabbix_db_refresh": "Zabbix DB Refresh",
    "license_renewal_admin": "License Renewal Admin (God, Admin only)",
}


DEFAULT_USER_FEATURES = [
    "alarm_clear_manual",
    "alarm_clear_bulk",
    "reporting",
    "vrf_routing",
    "license_check",
    "zabbix_search",
    "code_site_search",
    "session_extractor",
    "ptp_troubleshoot",
]


def _load_users() -> dict:
    users_file = _get_users_file()
    with LOCK:
        if not os.path.exists(users_file):
            _init_default_users()
        with open(users_file, "r", encoding="utf-8") as f:
            users = json.load(f)
            for u, data in users.items():
                if "token_version" not in data:
                    data["token_version"] = 1
                if "is_active" not in data:
                    data["is_active"] = True
            return users


def _sync_to_db(users: dict) -> None:
    """Synchronize users and permissions into database tables."""
    try:
        from backend.app.extensions import get_db_session
        from backend.app.models.user import User, Permission
        with get_db_session() as s:
            for username, data in users.items():
                u = s.query(User).filter(User.username == username).first()
                if not u:
                    u = User(username=username)
                    s.add(u)
                u.password_hash = data.get("password", "")
                role_val = data.get("role", "operator")
                u.role = "operator" if role_val == "user" else role_val
                u.display_name = data.get("display_name", username)
                u.is_active = data.get("is_active", True)
                u.token_version = data.get("token_version", 1)
                u.must_change_password = data.get("must_change_password", False)
                s.flush()

                # Sync permissions
                perms = data.get("permissions", {})
                existing_perms = {p.feature: p for p in u.permissions}
                for feat, granted in perms.items():
                    if feat in existing_perms:
                        existing_perms[feat].granted = bool(granted)
                    else:
                        s.add(Permission(user_id=u.id, feature=feat, granted=bool(granted)))
            s.commit()
    except Exception:
        pass


def _sync_delete_from_db(username: str) -> None:
    """Delete user from database table upon deletion in users.json."""
    try:
        from backend.app.extensions import get_db_session
        from backend.app.models.user import User
        with get_db_session() as s:
            s.query(User).filter(User.username == username).delete()
            s.commit()
    except Exception:
        pass


def _save_users(users: dict) -> None:
    users_file = _get_users_file()
    with LOCK:
        with open(users_file, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        _sync_to_db(users)


WEAK_PASSWORDS = {
    "god", "admin", "password", "123456", "12345678", "123456789", "1234567890",
    "qwerty", "letmein", "welcome", "admin123", "password123", "administrator",
}


def validate_password(password: str, username: str = "") -> str | None:
    """Validate password against security policy.

    Policy:
    - Minimum 12 characters.
    - Cannot equal or contain username (case-insensitive, if username len >= 3).
    - Cannot be in known weak passwords list.
    """
    if not password or len(password) < 12:
        return "Password must be at least 12 characters long"
    clean_pass = password.strip().lower()
    if clean_pass in WEAK_PASSWORDS:
        return "Password is in the weak password blocklist"
    if username and len(username.strip()) >= 3 and username.strip().lower() in clean_pass:
        return "Password cannot contain the username"
    return None


def _init_default_users() -> None:
    """Bootstrap initial admin user if zero users exist."""
    initial_user = (os.environ.get("INITIAL_ADMIN_USER") or "admin").strip()
    env_password = os.environ.get("INITIAL_ADMIN_PASSWORD")

    if env_password:
        password = env_password
        must_change = False
    else:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(secrets.choice(alphabet) for _ in range(20))
        must_change = True

        banner = f"""
======================================================================
[BOOTSTRAP] FIRST RUN INITIAL ADMIN ACCOUNT CREATED
Username: {initial_user}
Password: {password}
Please change your password immediately upon first login!
======================================================================
"""
        print(banner, flush=True)

    default_users = {
        initial_user: {
            "password": generate_password_hash(password),
            "role": "god",
            "permissions": {},
            "display_name": "Administrator",
            "must_change_password": must_change,
            "token_version": 1,
            "is_active": True,
        }
    }
    _save_users(default_users)


def _find_user(users: dict, username: str) -> str | None:
    for key in users:
        if key.lower() == username.lower():
            return key
    return None


DUMMY_PASSWORD_HASH = generate_password_hash("AntigravityTimingMitigationDummyPassword2026!")
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes

_LOGIN_ATTEMPTS: dict[tuple[str, str], dict] = {}
_LOGIN_LOCK = threading.Lock()


def check_login_rate_limit(username: str, ip: str) -> tuple[bool, int]:
    """Check if (username, ip) is currently locked out.

    Returns (is_locked, remaining_seconds).
    """
    key = ((username or "").strip().lower(), (ip or "").strip())
    now = time.time()
    with _LOGIN_LOCK:
        record = _LOGIN_ATTEMPTS.get(key)
        if not record:
            return False, 0
        locked_until = record.get("locked_until")
        if locked_until:
            if now < locked_until:
                return True, int(locked_until - now)
            # Lockout expired, reset counter
            _LOGIN_ATTEMPTS.pop(key, None)
            return False, 0
        return False, 0


def record_failed_login(username: str, ip: str) -> tuple[int, bool, int]:
    """Record a failed login attempt.

    Returns (failed_count, is_now_locked, remaining_seconds).
    """
    key = ((username or "").strip().lower(), (ip or "").strip())
    now = time.time()
    with _LOGIN_LOCK:
        record = _LOGIN_ATTEMPTS.setdefault(key, {"failures": 0, "locked_until": None})
        record["failures"] += 1
        if record["failures"] >= MAX_FAILED_LOGIN_ATTEMPTS:
            record["locked_until"] = now + LOCKOUT_DURATION_SECONDS
            return record["failures"], True, LOCKOUT_DURATION_SECONDS
        return record["failures"], False, 0


def record_successful_login(username: str, ip: str) -> None:
    """Clear failed login records upon successful login."""
    key = ((username or "").strip().lower(), (ip or "").strip())
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)


def clear_all_rate_limits() -> None:
    """Reset rate limiter state (for tests)."""
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.clear()


def authenticate(username: str, password: str) -> dict | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        check_password_hash(DUMMY_PASSWORD_HASH, password)
        return None
    user = users[actual]
    if not user.get("is_active", True):
        check_password_hash(DUMMY_PASSWORD_HASH, password)
        return None
    if not check_password_hash(user["password"], password):
        return None
    return {
        "username": actual,
        "role": user["role"],
        "permissions": user.get("permissions", {}),
        "display_name": user.get("display_name", actual),
        "must_change_password": bool(user.get("must_change_password", False)),
        "token_version": user.get("token_version", 1),
        "is_active": user.get("is_active", True),
    }


def user_has_access(user_info: dict, feature: str) -> bool:
    role = user_info.get("role", "user")
    if role == "god":
        return True
    if role == "viewer":
        # Viewer role has access to read-only diagnostic features only (Step 2.7)
        read_only_features = {
            "reporting",
            "vrf_routing",
            "zabbix_search",
            "code_site_search",
            "session_extractor",
        }
        return feature in read_only_features
    if role == "admin":
        return feature not in ("user_management", "permission_management", "zabbix_db_refresh", "license_renewal_admin")
    perms = user_info.get("permissions", {})
    if feature in perms:
        return bool(perms[feature])
    return feature in DEFAULT_USER_FEATURES


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


def role_required(*allowed_roles: str):
    """Decorator ensuring current session user has one of allowed roles (or god)."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user_info = session.get("user", {})
            user_role = user_info.get("role", "user")
            if user_role == "god" or user_role in allowed_roles:
                return f(*args, **kwargs)
            return jsonify({"error": "Forbidden", "message": f"Requires role in {allowed_roles}"}), 403
        return decorated
    return decorator


def get_user(username: str) -> dict | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        return None
    user = users[actual]
    return {
        "username": actual,
        "role": user.get("role", "user"),
        "permissions": user.get("permissions", {}),
        "display_name": user.get("display_name", actual),
        "must_change_password": bool(user.get("must_change_password", False)),
        "token_version": user.get("token_version", 1),
        "is_active": user.get("is_active", True),
    }


def get_all_users() -> dict:
    users = _load_users()
    result = {}
    for username, data in users.items():
        result[username] = {
            "role": data["role"],
            "display_name": data.get("display_name", username),
            "permissions": data.get("permissions", {}),
            "must_change_password": bool(data.get("must_change_password", False)),
            "token_version": data.get("token_version", 1),
            "is_active": data.get("is_active", True),
        }
    return result


def create_user(username: str, password: str, role: str, display_name: str = "", permissions: dict | None = None) -> str | None:
    users = _load_users()
    existing = _find_user(users, username)
    if existing:
        return f"User already exists (as '{existing}')"
    policy_err = validate_password(password, username)
    if policy_err:
        return policy_err
    if permissions is None:
        permissions = {feat: True for feat in DEFAULT_USER_FEATURES}
    users[username] = {
        "password": generate_password_hash(password),
        "role": role,
        "permissions": permissions,
        "display_name": display_name or username,
        "must_change_password": False,
        "token_version": 1,
        "is_active": True,
    }
    _save_users(users)
    return None


def update_user(username: str, updates: dict) -> str | None:
    users = _load_users()
    actual = _find_user(users, username)
    if actual is None:
        return "User not found"

    # Do not mutate caller's dict
    clean_updates = dict(updates)

    # Protect against demoting or disabling the last active god user
    if users[actual].get("role") == "god":
        new_role = clean_updates.get("role")
        is_active = clean_updates.get("is_active")
        other_gods = [
            u for u, d in users.items()
            if u != actual and d.get("role") == "god" and d.get("is_active", True)
        ]
        if new_role and new_role != "god" and not other_gods:
            return "Cannot demote the last god user"
        if is_active is False and not other_gods:
            return "Cannot disable the last god user"

    bump_token = False
    if "password" in clean_updates and clean_updates["password"]:
        policy_err = validate_password(clean_updates["password"], username)
        if policy_err:
            return policy_err
        clean_updates["password"] = generate_password_hash(clean_updates["password"])
        if "must_change_password" not in clean_updates:
            clean_updates["must_change_password"] = False
        bump_token = True
    else:
        clean_updates.pop("password", None)

    for field in ("role", "permissions", "is_active"):
        if field in clean_updates:
            bump_token = True

    for key, value in clean_updates.items():
        if value is not None:
            users[actual][key] = value

    if bump_token:
        users[actual]["token_version"] = users[actual].get("token_version", 1) + 1

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
    _sync_delete_from_db(actual)
    return None
