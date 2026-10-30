"""Flask Application Factory with Database, Security Middleware, and Blueprint initialization."""
import os
import sys
import secrets
import logging
from datetime import timedelta
from flask import Flask, jsonify

from backend.app.config import settings
from backend.app.extensions import init_db, get_db_session
from backend.app.db.migrate_files import migrate_all_files
from backend.app.models.user import User
from backend.app.security.middleware import init_security_middleware

logger = logging.getLogger(__name__)


def create_app(config_override: dict = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates")),
        static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static")),
    )

    data_dir = settings.get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    secret_key_file = os.path.join(data_dir, ".secret_key")

    if os.environ.get("FLASK_SECRET_KEY"):
        secret_key = os.environ["FLASK_SECRET_KEY"]
    elif settings.secret_key:
        secret_key = settings.secret_key
    elif os.path.exists(secret_key_file):
        with open(secret_key_file, "r") as f:
            secret_key = f.read().strip()
    else:
        secret_key = secrets.token_hex(32)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600
            fd = os.open(secret_key_file, flags, mode)
            with os.fdopen(fd, "w") as f:
                f.write(secret_key)
        except Exception:
            with open(secret_key_file, "w") as f:
                f.write(secret_key)

    app.secret_key = secret_key
    app.config["SECRET_KEY"] = secret_key
    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Session cookie and security configuration (Step 1.3)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        hours=int(os.environ.get("PERMANENT_SESSION_LIFETIME_HOURS", "8"))
    )

    # Payload limits (Step 1.6 - F-09, F-10)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024

    if config_override:
        app.config.update(config_override)

    # Initialize Database
    try:
        init_db()
        # Initial boot migration: migrate legacy files if User table is empty
        with get_db_session() as session:
            user_count = session.query(User).count()
            if user_count == 0:
                logger.info("Database initialized with 0 users. Executing boot migration from legacy files...")
                migrate_all_files(session)
    except Exception as exc:
        logger.warning("Could not initialize DB or run boot migration: %s", exc)

    # Security & Error Middleware
    init_security_middleware(app)

    # Initialize Credential Vault key (Step 2.8 - F-06)
    from backend.app.security.vault import get_vault_key
    try:
        is_testing = bool(app.config.get("TESTING") or "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"))
        get_vault_key(require_prod=not is_testing)
    except Exception as exc:
        if not app.config.get("TESTING"):
            logger.error("Vault key initialization failed: %s", exc)
            raise

    # Initialize structured JSON logging
    from backend.app.logging import setup_logging
    setup_logging(app)

    # Core health & metrics probes
    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok", "app": "Web-Dash", "version": "2.0.0"}), 200

    @app.route("/readyz", methods=["GET"])
    def readyz():
        from settings import is_read_only_mode
        db_ok = True
        try:
            with get_db_session() as session:
                session.execute(User.__table__.select().limit(1))
        except Exception:
            db_ok = False

        return jsonify({
            "status": "ready" if db_ok else "degraded",
            "read_only": is_read_only_mode(),
            "data_dir": settings.get_data_dir(),
            "database": "connected" if db_ok else "disconnected",
        }), 200 if db_ok else 503

    @app.route("/metrics", methods=["GET"])
    def metrics():
        from flask import Response
        from backend.app.metrics import generate_prometheus_metrics
        return Response(
            generate_prometheus_metrics(),
            mimetype="text/plain; version=0.0.4; charset=utf-8",
        )

    # Register API Blueprints
    from backend.app.api.main import main_bp
    from backend.app.api.auth import auth_bp
    from backend.app.api.users import users_bp
    from backend.app.api.jobs import jobs_bp
    from backend.app.api.alarm_clear import alarm_clear_bp
    from backend.app.api.reports import reports_bp
    from backend.app.api.license import license_bp
    from backend.app.api.routing import routing_bp
    from backend.app.api.telemetry import telemetry_bp
    from backend.app.api.arp import arp_bp
    from backend.app.api.sessions_export import sessions_export_bp
    from backend.app.api.ptp import ptp_bp
    from backend.app.api.schedules import schedules_bp
    from backend.app.api.credentials import credentials_bp
    from backend.app.api.changes import changes_bp
    from backend.app.api.configs import configs_bp
    from backend.app.api.devices import devices_bp
    from backend.app.api.features import features_bp
    from backend.app.api.alarms import alarms_bp

    # Trigger features and job handlers registration
    import backend.app.features  # noqa: F401
    import backend.app.jobs.handlers  # noqa: F401

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(jobs_bp, url_prefix="/api/v1/jobs")
    app.register_blueprint(jobs_bp, url_prefix="/jobs", name="jobs_alias")
    app.register_blueprint(credentials_bp, url_prefix="/api/v1/credentials")
    app.register_blueprint(credentials_bp, url_prefix="/credentials", name="credentials_alias")
    app.register_blueprint(changes_bp, url_prefix="/api/v1/changes")
    app.register_blueprint(changes_bp, url_prefix="/changes", name="changes_alias")
    app.register_blueprint(devices_bp, url_prefix="/api/v1/devices")
    app.register_blueprint(devices_bp, url_prefix="/devices", name="devices_alias")
    app.register_blueprint(configs_bp, url_prefix="/api/v1/devices")
    app.register_blueprint(configs_bp, url_prefix="/devices", name="configs_alias")
    app.register_blueprint(features_bp, url_prefix="/api/v1/features")
    app.register_blueprint(features_bp, url_prefix="/features", name="features_alias")
    app.register_blueprint(alarms_bp, url_prefix="/api/v1/alarms")
    app.register_blueprint(alarms_bp, url_prefix="/alarms", name="alarms_alias")
    app.register_blueprint(alarm_clear_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(license_bp)
    app.register_blueprint(routing_bp)
    app.register_blueprint(telemetry_bp)
    app.register_blueprint(arp_bp)
    app.register_blueprint(sessions_export_bp)
    app.register_blueprint(ptp_bp)
    app.register_blueprint(schedules_bp, url_prefix="/api/v1/schedules")

    return app
