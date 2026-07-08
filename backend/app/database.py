"""SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from .config import settings


# Enable WAL mode and increase busy timeout for better concurrency
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # WAL mode: allows concurrent readers + single writer
    cursor.execute("PRAGMA journal_mode=WAL;")
    # Wait up to 30 seconds for lock instead of default (usually 5ms)
    cursor.execute("PRAGMA busy_timeout=30000;")
    # Slightly better performance, still safe with WAL
    cursor.execute("PRAGMA synchronous=NORMAL;")
    # Use more memory for cache (10MB instead of default pages = 4KB, so 2500 = ~10MB)
    cursor.execute("PRAGMA cache_size=-10000;")
    cursor.close()


# check_same_thread=False: FastAPI may use the session across threads.
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
    pool_pre_ping=True,  # Verify connections before use
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    """Create the SQLite file + tables if they do not exist yet."""
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
    # Import here so models register on Base before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
