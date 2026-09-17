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
    """Verify the live database schema matches expectations (read-only)."""

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

    def test_all_application_tables_exist(self):
        """All 34 application tables exist in the database."""
        engine = _get_engine()
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names(schema="public"))
        missing = EXPECTED_TABLES - db_tables
        assert not missing, f"Missing tables in database: {missing}"

    def test_geometry_columns_use_srid_4326(self):
        """All FloodPulse geometry columns use SRID 4326."""
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT f_table_name, f_geometry_column, srid
                FROM geometry_columns
                WHERE f_table_schema = 'public'
                  AND f_table_name != 'spatial_ref_sys'
            """))
            rows = result.fetchall()
            assert len(rows) > 0, "No geometry columns found"
            bad_srid = [(r[0], r[1], r[2]) for r in rows if r[2] != 4326]
            assert not bad_srid, f"Geometry columns with wrong SRID: {bad_srid}"

    def test_no_application_data_inserted(self):
        """Application tables must be empty — no seed/fake data."""
        engine = _get_engine()
        with engine.connect() as conn:
            for table_name in sorted(EXPECTED_TABLES):
                result = conn.execute(
                    text(f'SELECT count(*) FROM "{table_name}"')
                )
                count = result.scalar()
                assert count == 0, (
                    f"Table {table_name} has {count} rows — "
                    "no data should have been inserted"
                )
