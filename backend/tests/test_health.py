"""
Health endpoint tests for FloodPulse.

These tests verify the basic API foundation without requiring a live
database. The test suite must pass with no DATABASE_URL configured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    """Synchronous test client using Starlette/FastAPI TestClient."""
    with TestClient(app) as c:
        yield c


# ---- Isolate tests from real database ----


@pytest.fixture(autouse=True)
def _isolate_from_database(monkeypatch):
    """Ensure DATABASE_URL is not available during tests — neither from
    os.environ NOR from the local .env file — so we never accidentally
    connect to the real FloodPulse database.

    We override get_settings() to return a clean Settings object with
    database_url=None, bypassing pydantic-settings .env file reading.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.core.config import Settings

    _test_settings = Settings(
        database_url=None, app_env="testing", scheduler_enabled=False
    )

    monkeypatch.setattr("app.core.config.get_settings", lambda: _test_settings)
    monkeypatch.setattr("app.api.health.get_settings", lambda: _test_settings)

    # Reset the lazy engine/session singletons from db.session so that
    # each test starts clean.
    import app.db.session as db_mod
    db_mod._engine = None
    db_mod._SessionLocal = None


# ---- /health ----


class TestHealth:
    """GET /health — API process liveness."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_status_ok(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"


# ---- /health/database ----


class TestHealthDatabase:
    """GET /health/database — database connectivity check.

    Without DATABASE_URL configured, the endpoint must report
    unavailable/unconfigured WITHOUT crashing the application.
    """

    def test_database_health_without_config_returns_200(self, client):
        """The endpoint must not crash when DATABASE_URL is absent."""
        response = client.get("/health/database")
        assert response.status_code == 200

    def test_database_health_without_config_reports_unavailable(self, client):
        """When DATABASE_URL is absent, status must indicate unavailability."""
        response = client.get("/health/database")
        data = response.json()
        assert data["status"] in ("unavailable", "down")

    def test_database_health_without_config_does_not_crash(self, client):
        """Repeated calls must not cause cumulative errors."""
        for _ in range(3):
            response = client.get("/health/database")
            assert response.status_code == 200


# ---- /health/postgis ----


class TestHealthPostGIS:
    """GET /health/postgis — PostGIS extension check.

    Without DATABASE_URL configured, the endpoint must report
    unavailable/unconfigured WITHOUT crashing the application.
    """

    def test_postgis_health_without_config_returns_200(self, client):
        """The endpoint must not crash when DATABASE_URL is absent."""
        response = client.get("/health/postgis")
        assert response.status_code == 200

    def test_postgis_health_without_config_reports_unavailable(self, client):
        """When DATABASE_URL is absent, status must indicate unavailability."""
        response = client.get("/health/postgis")
        data = response.json()
        assert data["status"] in ("unavailable", "down")

    def test_postgis_health_without_config_does_not_crash(self, client):
        """Repeated calls must not cause cumulative errors."""
        for _ in range(3):
            response = client.get("/health/postgis")
            assert response.status_code == 200
