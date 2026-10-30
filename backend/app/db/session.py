"""SQLAlchemy engine, connection configuration, and session management.
Supports both PostgreSQL (primary target) and SQLite WAL mode (development/air-gap).
"""
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
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
    if _engine is not None and db_url is None:
        return _engine

    url = db_url or settings.get_database_url()
    logger.info("Initializing database engine with URL: %s", url.split("@")[-1] if "@" in url else url)

    if url.startswith("sqlite"):
        # SQLite with WAL mode, busy timeout, and foreign keys enabled
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
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
    return _engine


def get_session() -> Session:
    """Return a scoped database session."""
    if ScopedSession is None:
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
