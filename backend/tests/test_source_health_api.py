"""
API integration tests for /api/v1/health/sources and run history endpoints.

Verifies:
- GET /api/v1/health/sources returns 200 and schema compliant source health list.
- GET /api/v1/health/sources/{source_id}/runs returns 200 with paginated run list.
- GET /api/v1/health/sources/{unknown_uuid}/runs returns 404.
- GET /api/v1/health/sources/{invalid_uuid}/runs returns 422.
- Existing /health, /health/database, /health/postgis endpoints continue to function.
"""

from __future__ import annotations

import os
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db.models.system import DataSource
from app.db.session import _get_session_factory
from app.main import app


@pytest.fixture
def live_client():
    """Client for live database API tests."""
    import app.db.session as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    with TestClient(app) as client:
        yield client

    db_mod._engine = None
    db_mod._SessionLocal = None


class TestSourceHealthEndpoints:
    """Tests for GET /api/v1/health/sources."""

    def test_get_all_sources_health_returns_200(self, live_client):
        """GET /api/v1/health/sources must return 200 and list registered sources."""
        response = live_client.get("/api/v1/health/sources")
        assert response.status_code == 200

        data = response.json()
        assert "sources" in data
        assert "total_sources" in data
        assert "evaluated_at" in data
        assert isinstance(data["sources"], list)
        assert data["total_sources"] >= 5  # 5 verified sources seeded in Phase 2.4

        for item in data["sources"]:
            assert "source_id" in item
            assert "name" in item
            assert item["health_status"] in ("HEALTHY", "DEGRADED", "DOWN")
            assert "health_reason" in item
            assert isinstance(item["is_active"], bool)

    def test_get_source_runs_existing_source(self, live_client):
        """GET /api/v1/health/sources/{source_id}/runs returns 200 for known source."""
        # Find any registered source id
        factory = _get_session_factory()
        with factory() as session:
            source = session.query(DataSource).first()
            assert source is not None
            source_id = str(source.id)

        response = live_client.get(f"/api/v1/health/sources/{source_id}/runs")
        assert response.status_code == 200

        data = response.json()
        assert data["source_id"] == source_id
        assert "runs" in data
        assert "total_runs" in data
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert isinstance(data["runs"], list)

    def test_get_source_runs_pagination(self, live_client):
        """GET /api/v1/health/sources/{source_id}/runs respects limit and offset parameters."""
        factory = _get_session_factory()
        with factory() as session:
            source = session.query(DataSource).first()
            source_id = str(source.id)

        response = live_client.get(f"/api/v1/health/sources/{source_id}/runs?limit=2&offset=0")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["runs"]) <= 2

    def test_get_source_runs_unknown_uuid_returns_404(self, live_client):
        """Requesting run history for non-existent source UUID returns 404."""
        random_uuid = str(uuid.uuid4())
        response = live_client.get(f"/api/v1/health/sources/{random_uuid}/runs")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_source_runs_invalid_uuid_returns_422(self, live_client):
        """Requesting run history with malformed non-UUID string returns 422."""
        response = live_client.get("/api/v1/health/sources/not-a-valid-uuid/runs")
        assert response.status_code == 422


class TestLegacyHealthEndpointsPreserved:
    """Verify that unversioned operational health endpoints still function correctly."""

    def test_legacy_health_ok(self, live_client):
        response = live_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_legacy_health_database_ok(self, live_client):
        response = live_client.get("/health/database")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_legacy_health_postgis_ok(self, live_client):
        response = live_client.get("/health/postgis")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
