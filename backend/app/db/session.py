"""
SQLAlchemy engine, session factory, and FastAPI dependency.

The engine is created lazily — importing this module does NOT open a
database connection. A connection is only attempted when get_db() is
actually called by a request handler.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Lazy engine singleton
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    """Return the SQLAlchemy engine, creating it on first call."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        if settings.database_url is None:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in the environment "
                "or in a .env file."
            )
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    """Return the session factory, creating it on first call."""
    global _SessionLocal  # noqa: PLW0603
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_get_engine(),
        )
    return _SessionLocal


# ---------------------------------------------------------------------------
# Declarative base for future models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a database session, always closes it."""
    factory = _get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
