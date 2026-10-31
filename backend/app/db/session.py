"""SQLAlchemy engine, connection configuration, and session management.
Supports both PostgreSQL (primary target) and SQLite WAL mode (development/air-gap).
"""
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.engine import Engine

from backend.app.config import settings
from backend.app.db.base import Base

logger = logging.getLogger(__name__)

_engine: Engine = None
_session_factory = None
ScopedSession = None


def get_engine(db_url: str = None) -> Engine:
    """Initialize or return the global SQLAlchemy engine."""
    global _engine, _session_factory, ScopedSession
    url = db_url or settings.get_database_url()
    if _engine is not None and db_url is None and str(_engine.url) == str(url):
        return _engine

    if _engine is not None:
        try:
            if ScopedSession is not None:
                ScopedSession.remove()
            _engine.dispose()
        except Exception:
            pass

    logger.info("Initializing database engine with URL: %s", url.split("@")[-1] if "@" in url else url)

    if url.startswith("sqlite"):
        from sqlalchemy.pool import NullPool
        # SQLite with WAL mode, busy timeout, and NullPool for zero file lock retention
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
            echo=settings.debug,
        )

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # PostgreSQL with connection pooling
        engine = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=settings.debug,
        )

    _engine = engine
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    ScopedSession = scoped_session(_session_factory)

    if url.startswith("sqlite"):
        try:
            import backend.app.models  # noqa: F401
            Base.metadata.create_all(bind=_engine)
            # Lightweight schema sync for development SQLite
            with _engine.connect() as conn:
                try:
                    # config_snapshots columns
                    res = conn.execute(text("PRAGMA table_info(config_snapshots)")).fetchall()
                    cols = {r[1] for r in res}
                    if cols and "last_checked_at" not in cols:
                        conn.execute(text("ALTER TABLE config_snapshots ADD COLUMN last_checked_at DATETIME"))
                    if cols and "size_bytes" not in cols:
                        conn.execute(text("ALTER TABLE config_snapshots ADD COLUMN size_bytes INTEGER"))

                    # devices columns
                    dev_res = conn.execute(text("PRAGMA table_info(devices)")).fetchall()
                    dev_cols = {r[1] for r in dev_res}
                    if dev_cols:
                        if "software_version" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN software_version VARCHAR(100)"))
                        if "lsr_id" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN lsr_id VARCHAR(100)"))
                        if "role" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN role VARCHAR(50)"))
                        if "health_status" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN health_status VARCHAR(50) DEFAULT 'unknown'"))
                        if "last_health_check" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN last_health_check DATETIME"))
                        if "updated_at" not in dev_cols:
                            conn.execute(text("ALTER TABLE devices ADD COLUMN updated_at DATETIME"))
                    conn.commit()
                except Exception:
                    pass
        except Exception:
            pass

    return _engine


def close_db() -> None:
    """Close and dispose all active sessions and engine connections."""
    global _engine, _session_factory, ScopedSession
    if ScopedSession is not None:
        try:
            ScopedSession.remove()
        except Exception:
            pass
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _session_factory = None
    ScopedSession = None


def get_session() -> Session:
    """Return a scoped database session."""
    get_engine()
    return ScopedSession()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for atomic database operations with automatic commit/rollback."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine = None) -> None:
    """Create all tables defined in Base metadata if they do not exist."""
    eng = engine or get_engine()
    # Import all models to ensure they are registered with Base.metadata
    import backend.app.models  # noqa: F401
    Base.metadata.create_all(bind=eng)
    logger.info("Database schema initialized successfully.")
