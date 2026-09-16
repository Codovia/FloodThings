"""
Health-check endpoints.

    GET /health          — API process liveness
    GET /health/database — genuine database connectivity check
    GET /health/postgis  — genuine PostGIS extension check

Each endpoint reports its own status independently. An unreachable
database is a condition to report honestly, not an unhandled exception
that crashes the process.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """API process liveness check."""
    return {"status": "ok"}


@router.get("/health/database")
def health_database() -> dict:
    """Genuine database connectivity check.

    If DATABASE_URL is not configured, reports that clearly.
    If the database is unreachable, reports the failure without crashing.
    """
    settings = get_settings()
    if settings.database_url is None:
        return {"status": "unavailable", "detail": "DATABASE_URL is not configured"}

    try:
        # Resolve the get_db generator manually so we control the
        # lifecycle without requiring FastAPI's dependency injection
        # (which would raise a RuntimeError if DATABASE_URL is missing
        # inside _get_engine).
        db_gen = get_db()
        db: Session = next(db_gen)
        try:
            db.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "down", "detail": str(exc)}
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    except RuntimeError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)}


@router.get("/health/postgis")
def health_postgis() -> dict:
    """Genuine PostGIS extension check.

    Executes an actual PostGIS query against the configured database.
    Does not assume PostGIS is available merely because PostgreSQL is
    configured.
    """
    settings = get_settings()
    if settings.database_url is None:
        return {"status": "unavailable", "detail": "DATABASE_URL is not configured"}

    try:
        db_gen = get_db()
        db: Session = next(db_gen)
        try:
            result = db.execute(text("SELECT PostGIS_Version()")).scalar()
            return {"status": "ok", "postgis_version": result}
        except Exception as exc:
            return {"status": "down", "detail": str(exc)}
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    except RuntimeError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)}
