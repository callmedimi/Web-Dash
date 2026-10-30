"""Flask Application Factory with Database and Configuration initialization."""
import os
import logging
from flask import Flask, jsonify

from backend.app.config import settings
from backend.app.extensions import init_db, get_db_session
from backend.app.db.migrate_files import migrate_all_files
from backend.app.models.user import User

logger = logging.getLogger(__name__)


def create_app(config_override: dict = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates")),
        static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static")),
    )

    # Basic app configurations
    app.config["SECRET_KEY"] = settings.secret_key or os.environ.get("SECRET_KEY", "fallback-secret-key-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

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

    # Core health probes
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

    # Register API Blueprints
    from backend.app.api.jobs import jobs_bp
    app.register_blueprint(jobs_bp, url_prefix="/api/v1/jobs")
    app.register_blueprint(jobs_bp, url_prefix="/jobs", name="jobs_alias")

    return app
