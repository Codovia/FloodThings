"""
Integration tests — health endpoints against a live database.

These tests require:
    - A running PostgreSQL instance with PostGIS.
    - DATABASE_URL set in the environment or backend/.env.

Run with:
    cd backend && python -m pytest tests/test_health_integration.py -v

These tests are marked with @pytest.mark.integration so they can be
excluded in environments without a database:
    python -m pytest -m "not integration"
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


# Skip the entire module if DATABASE_URL is not configured.
_has_db = bool(os.environ.get("DATABASE_URL")) or os.path.exists(
    os.path.join(os.path.dirname(__file__), "..", ".env")
)


@pytest.fixture()
def client():
    """Test client using the real database configuration."""
    # Reset cached engine/session so the live .env is used.
    import app.db.session as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    with TestClient(app) as c:
        yield c

    # Clean up after tests.
    db_mod._engine = None
    db_mod._SessionLocal = None


# ---- /health (always works, even without DB) ----


@pytest.mark.integration
class TestHealthLive:
    """GET /health — should always return ok."""

    def test_health_live(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---- /health/database ----


@pytest.mark.integration
class TestDatabaseHealthLive:
    """GET /health/database — real database connectivity."""

    def test_database_reports_ok(self, client):
        """With a live database, status must be 'ok'."""
        response = client.get("/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok", f"Expected ok, got: {data}"

    def test_database_health_is_idempotent(self, client):
        """Multiple calls must all succeed."""
        for _ in range(3):
            response = client.get("/health/database")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


# ---- /health/postgis ----


@pytest.mark.integration
class TestPostGISHealthLive:
    """GET /health/postgis — real PostGIS extension check."""

    def test_postgis_reports_ok(self, client):
        """With PostGIS installed, status must be 'ok'."""
        response = client.get("/health/postgis")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok", f"Expected ok, got: {data}"

    def test_postgis_returns_version(self, client):
        """The response must include the PostGIS version string."""
        response = client.get("/health/postgis")
        data = response.json()
        assert "postgis_version" in data
        assert "3.4" in data["postgis_version"]

    def test_postgis_health_is_idempotent(self, client):
        """Multiple calls must all succeed."""
        for _ in range(3):
            response = client.get("/health/postgis")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
