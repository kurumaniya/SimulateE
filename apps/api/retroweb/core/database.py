"""SQLAlchemy engine + session management.

The engine is created lazily from settings so tests can point it at a
temporary SQLite file. Only portable SQL is used; SQLite and PostgreSQL are
both first-class.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from retroweb.core.config import Settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _sqlite_file_from_url(url: str) -> Path | None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    location = url[len(prefix) :]
    if location == ":memory:" or not location:
        return None
    return Path(location)


def build_engine(settings: Settings) -> Engine:
    url = settings.database_url
    sqlite_file = _sqlite_file_from_url(url)
    if sqlite_file is not None:
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_engine(settings: Settings) -> Engine:
    global _engine, _session_factory
    _engine = build_engine(settings)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not initialised; call init_engine() first")
    return _engine


def get_session() -> Iterator[Session]:
    if _session_factory is None:
        raise RuntimeError("Database engine not initialised; call init_engine() first")
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()
