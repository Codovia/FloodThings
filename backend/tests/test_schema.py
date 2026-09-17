"""
Schema smoke tests for FloodPulse.

Verifies:
    1. SQLAlchemy metadata imports correctly.
    2. The migration is valid (all expected tables registered).
    3. The database schema is reachable (live connectivity).
    4. PostGIS is available.
    5. No fake records are required.

These tests connect to the LIVE database (via DATABASE_URL from .env)
and perform read-only verification only.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from app.db.session import Base, _get_engine

# Import all models to populate metadata.
import app.db.models  # noqa: F401


# Expected application tables (34 total).
EXPECTED_TABLES = frozenset({
    "alerts", "audit_logs", "community_reports", "data_ingestion_runs",
    "data_sources", "districts", "emergency_facilities", "feature_snapshots",
    "flood_events", "flood_hazard_zones", "flood_observations",
    "flood_predictions", "land_covers", "localities", "ml_dataset_versions",
    "ml_models", "prediction_grid_cells", "rainfall_observations",
    "reservoir_observations", "reservoirs", "river_basins", "river_forecasts",
    "river_observations", "river_stations", "rivers", "states", "sub_basins",
    "taluks", "telegram_subscriptions", "terrain_datasets", "users",
    "water_bodies", "weather_forecasts", "weather_observations",
})


def _skip_if_no_db():
    """Skip schema tests if no DATABASE_URL is configured."""
    from app.core.config import get_settings
    settings = get_settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL not configured — skipping live schema tests")


class TestSchemaMetadata:
    """Verify SQLAlchemy model metadata is complete."""

    def test_all_expected_tables_registered(self):
        """All 34 documented entities are registered in Base.metadata."""
        registered = set(Base.metadata.tables.keys())
        missing = EXPECTED_TABLES - registered
        assert not missing, f"Missing tables in metadata: {missing}"

    def test_table_count(self):
        """Exactly 34 application tables are registered."""
        assert len(Base.metadata.tables) == 34


class TestLiveSchema:
    """Verify the live database foundation matches Phase 2.1 expectations.

    In Phase 2.1, the database is a clean PostGIS foundation.
    Application tables will be created when the initial Alembic migration
    is generated and applied in a future phase.
    """

    @pytest.fixture(autouse=True)
    def _require_db(self):
        _skip_if_no_db()

    def test_database_reachable(self):
        """Database accepts connections."""
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_postgis_available(self):
        """PostGIS extension is installed and functional."""
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT PostGIS_Version()"))
            version = result.scalar()
            assert version is not None
            assert "3.4" in version

    def test_clean_foundation_state(self):
        """Database should not contain application tables yet.

        In Phase 2.1, the database is a clean PostGIS foundation.
        Application tables will be deployed via Alembic migrations
        in a later phase.
        """
        engine = _get_engine()
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names(schema="public"))
        # Only PostGIS system tables should exist
        app_tables_present = EXPECTED_TABLES & db_tables
        assert not app_tables_present, (
            f"Application tables found unexpectedly in clean foundation: "
            f"{app_tables_present}"
        )
