"""Security, CSRF, and session validation middleware."""
import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, session, jsonify, current_app

from auth import get_user


def init_security_middleware(app: Flask) -> None:
    """Register session security, CSRF checks, and error handlers on the Flask app."""

    @app.before_request
    def security_and_session_checks():
        # 0. Skip static assets, healthz, readyz, metrics, openapi spec, and docs
        if (
            request.path.startswith("/static/")
            or request.path.startswith("/assets/")
            or request.path.startswith("/fonts/")
            or request.path in (
                "/",
                "/login",
                "/change-password",
                "/_ui",
                "/favicon.ico",
                "/healthz",
                "/readyz",
                "/metrics",
                "/api/v1/openapi.json",
                "/api/v1/docs",
                "/docs",
            )
        ):
            return None

        # 0.1 Check for Bearer API token in Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.strip().startswith("Bearer "):
            raw_token = auth_header.strip().split(" ", 1)[1].strip()
            from backend.app.services.tokens import ApiTokenService
            token_ctx = ApiTokenService.verify_token(raw_token)
            if not token_ctx:
                return (
                    jsonify({
                        "error": "Invalid or expired API token",
                        "code": "INVALID_TOKEN",
                        "message": "The Bearer API token supplied is invalid, revoked, or expired.",
                    }),
                    401,
                )
            session["user"] = {
                "id": token_ctx["user_id"],
                "username": token_ctx["username"],
                "role": token_ctx["role"],
                "token_id": token_ctx["token_id"],
                "scopes": token_ctx["scopes"],
            }
            # Bearer token authenticated API requests bypass browser CSRF checks
            return None

        # 1. CSRF Protection for mutating HTTP methods
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Exempt only login endpoints
            if request.path not in ("/login", "/api/v1/login"):
                expected_csrf = session.get("csrf_token")
                if expected_csrf:
                    provided_csrf = request.headers.get("X-CSRF-Token")
                    if not provided_csrf or not secrets.compare_digest(provided_csrf, expected_csrf):
                        return (
                            jsonify({
                                "error": "CSRF token missing or invalid",
                                "code": "CSRF_ERROR",
                                "message": "A valid X-CSRF-Token header matching your active session is required.",
                            }),
                            403,
                        )
                elif not current_app.config.get("TESTING"):
                    return (
                        jsonify({
                            "error": "CSRF token missing or invalid",
                            "code": "CSRF_ERROR",
                            "message": "A valid X-CSRF-Token header matching your active session is required.",
                        }),
                        403,
                    )

        # 2. Session validation & re-load user from store on every request
        username = session.get("username")
        if username:
            now = datetime.now().timestamp()
            last_seen = session.get("last_seen")
            # 30 minutes idle timeout
            if last_seen and (now - last_seen > 30 * 60):
                session.clear()
                return (
                    jsonify({
                        "error": "Session expired due to inactivity",
                        "code": "SESSION_EXPIRED",
                        "message": "Session expired due to inactivity. Please log in again.",
                    }),
                    401,
                )

            user_record = get_user(username)
            if not user_record:
                session.clear()
                return (
                    jsonify({
                        "error": "User account no longer exists",
                        "code": "USER_NOT_FOUND",
                        "message": "User account no longer exists.",
                    }),
                    401,
                )

            if not user_record.get("is_active", True):
                session.clear()
                return (
                    jsonify({
                        "error": "Account is disabled",
                        "code": "USER_DISABLED",
                        "message": "Account has been deactivated.",
                    }),
                    401,
                )

            current_token_ver = user_record.get("token_version", 1)
            stored_token_ver = session.get("token_version", 1)
            if stored_token_ver != current_token_ver:
                session.clear()
                return (
                    jsonify({
                        "error": "Session invalidated due to credential or role change",
                        "code": "SESSION_INVALIDATED",
                        "message": "Session has been invalidated. Please log in again.",
                    }),
                    401,
                )

            session["last_seen"] = now
            session["user"] = {
                "username": user_record["username"],
                "role": user_record["role"],
                "permissions": user_record.get("permissions", {}),
                "display_name": user_record.get("display_name", user_record["username"]),
                "must_change_password": bool(user_record.get("must_change_password", False)),
                "token_version": current_token_ver,
                "is_active": user_record.get("is_active", True),
            }

        # 3. Enforce must_change_password restriction
        user = session.get("user")
        if user and user.get("must_change_password"):
            exempt_paths = {
                "/",
                "/me",
                "/logout",
                "/change-password",
                "/api/v1/me",
                "/api/v1/logout",
                "/api/v1/change-password",
            }
            if request.path not in exempt_paths:
                return (
                    jsonify({
                        "error": "Password change required",
                        "code": "PASSWORD_CHANGE_REQUIRED",
                        "message": "You must change your temporary password before accessing other features.",
                    }),
                    403,
                )

    @app.after_request
    def apply_security_headers(response):
        grafana_url = os.environ.get("GRAFANA_URL", "http://localhost:3000")
        try:
            from urllib.parse import urlparse
            parsed = urlparse(grafana_url)
            grafana_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else grafana_url
        except Exception:
            grafana_origin = "http://localhost:3000"

        csp = (
            "default-src 'self'; "
            f"frame-src 'self' {grafana_origin}; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "font-src 'self'"
        )

        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    # Global Error Handlers (Target Architecture §4 & Step 1.6)
    @app.errorhandler(413)
    def handle_payload_too_large(e):
        max_mb = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "10"))
        msg = f"Request payload exceeds maximum allowed size ({max_mb} MB)"
        return (
            jsonify({
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": msg,
                    "fields": {},
                },
                "code": "PAYLOAD_TOO_LARGE",
                "message": msg,
            }),
            413,
        )

    @app.errorhandler(ValueError)
    def handle_value_error(e):
        msg = str(e)
        return (
            jsonify({
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": msg,
                    "fields": {},
                },
                "code": "VALIDATION_ERROR",
                "message": msg,
            }),
            400,
        )

    @app.errorhandler(KeyError)
    def handle_key_error(e):
        msg = f"Missing required field: {e}"
        return (
            jsonify({
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": msg,
                    "fields": {},
                },
                "code": "VALIDATION_ERROR",
                "message": msg,
            }),
            400,
        )
