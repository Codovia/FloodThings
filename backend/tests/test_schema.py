"""
Phase 2.2 Schema and Data Contract tests for FloodPulse.

Verifies:
    1. SQLAlchemy metadata completeness (34 entities, UUID PKs, provenance fields).
    2. Live database table creation via Alembic (all 34 tables present).
    3. PostGIS spatial foundation (23 geometry columns in EPSG:4326).
    4. GiST spatial indexes active on all 23 geometry columns.
    5. Referential integrity (foreign keys use NO ACTION/RESTRICT).
    6. Check constraints (coordinate bounds, probability bounds, controlled vocabularies).
    7. Data contract rules: missing values are stored as NULL (missing != 0).
    8. Zero fabricated data: observation tables are empty.

These tests connect to the LIVE database (via DATABASE_URL from .env).
All write operations are executed within transactions that are strictly rolled back.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.session import Base, _get_engine, _get_session_factory
import app.db.models  # noqa: F401
from app.db.models.system import DataSource
from app.db.models.hydrology import RiverBasin, River, RiverStation, RiverObservation


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

# Expected 23 spatial columns across application tables in PostGIS.
EXPECTED_SPATIAL_COLUMNS = frozenset({
    ("alerts", "geometry"),
    ("community_reports", "geometry"),
    ("districts", "centroid"),
    ("districts", "geometry"),
    ("emergency_facilities", "geometry"),
    ("flood_events", "geometry"),
    ("flood_hazard_zones", "geometry"),
    ("flood_observations", "geometry"),
    ("land_covers", "geometry"),
    ("localities", "centroid"),
    ("localities", "geometry"),
    ("prediction_grid_cells", "geometry"),
    ("rainfall_observations", "geometry"),
    ("reservoirs", "geometry"),
    ("river_basins", "geometry"),
    ("river_stations", "geometry"),
    ("rivers", "geometry"),
    ("states", "geometry"),
    ("sub_basins", "geometry"),
    ("taluks", "geometry"),
    ("terrain_datasets", "coverage"),
    ("water_bodies", "geometry"),
    ("weather_observations", "geometry"),
})


def _skip_if_no_db():
    """Skip schema tests if no DATABASE_URL is configured."""
    from app.core.config import get_settings
    settings = get_settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL not configured — skipping live schema tests")


class TestSchemaMetadata:
    """Verify SQLAlchemy model metadata is complete and structurally sound."""

    def test_all_expected_tables_registered(self):
        """All 34 documented entities are registered in Base.metadata."""
        registered = set(Base.metadata.tables.keys())
        missing = EXPECTED_TABLES - registered
        assert not missing, f"Missing tables in metadata: {missing}"

    def test_table_count(self):
        """Exactly 34 application tables are registered in metadata."""
        assert len(Base.metadata.tables) == 34

    def test_all_tables_have_uuid_primary_key(self):
        """Every table must have a primary key named 'id'."""
        for table_name, table in Base.metadata.tables.items():
            assert "id" in table.columns, f"Table {table_name} lacks 'id' column"
            assert table.columns["id"].primary_key, f"Table {table_name}.id is not PK"

    def test_observation_tables_have_provenance_columns(self):
        """Observation tables must carry data provenance and quality audit fields."""
        sensor_tables = [
            "river_observations",
            "rainfall_observations",
            "weather_observations",
            "reservoir_observations",
        ]
        for tbl_name in sensor_tables:
            tbl = Base.metadata.tables[tbl_name]
            assert "source_id" in tbl.columns, f"{tbl_name} missing source_id"
            assert "observed_at" in tbl.columns, f"{tbl_name} missing observed_at"
            assert "retrieved_at" in tbl.columns, f"{tbl_name} missing retrieved_at"
            assert "quality_status" in tbl.columns, f"{tbl_name} missing quality_status"

        flood_obs = Base.metadata.tables["flood_observations"]
        assert "source_id" in flood_obs.columns, "flood_observations missing source_id"
        assert "observation_time" in flood_obs.columns, "flood_observations missing observation_time"
        assert "quality_status" in flood_obs.columns, "flood_observations missing quality_status"


class TestLiveSchema:
    """Verify the live PostgreSQL/PostGIS database against Phase 2.2 requirements."""

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

    def test_all_34_tables_exist_in_live_db(self):
        """All 34 application tables are present in the public schema."""
        engine = _get_engine()
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names(schema="public"))
        missing = EXPECTED_TABLES - db_tables
        assert not missing, f"Missing tables in live database: {missing}"

    def test_spatial_columns_and_srid(self):
        """All 23 geometry columns must be registered in EPSG:4326."""
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT f_table_name, f_geometry_column, srid, type "
                "FROM geometry_columns "
                "WHERE f_table_schema = 'public' "
                "ORDER BY f_table_name, f_geometry_column"
            )).fetchall()

        registered_spatial = {(row[0], row[1]) for row in rows}
        missing_spatial = EXPECTED_SPATIAL_COLUMNS - registered_spatial
        assert not missing_spatial, f"Missing spatial columns in geometry_columns: {missing_spatial}"
        assert len(registered_spatial) == 23, f"Expected 23 spatial columns, got {len(registered_spatial)}"

        for row in rows:
            table_name, col_name, srid, geom_type = row
            assert srid == 4326, f"{table_name}.{col_name} SRID is {srid}, expected 4326"

    def test_gist_spatial_indexes_exist(self):
        """Every geometry column must have an active GiST spatial index."""
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT tablename, indexname, indexdef "
                "FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexdef LIKE '%USING gist%'"
            )).fetchall()

        gist_index_count = len(rows)
        assert gist_index_count == 23, f"Expected exactly 23 GiST indexes, found {gist_index_count}"

        # Verify each table with geometry has at least one GiST index
        indexed_tables = {row[0] for row in rows}
        expected_tables_with_geom = {tbl for tbl, _ in EXPECTED_SPATIAL_COLUMNS}
        missing_index_tables = expected_tables_with_geom - indexed_tables
        assert not missing_index_tables, f"Tables missing GiST index: {missing_index_tables}"

    def test_foreign_key_referential_integrity(self):
        """Foreign keys must protect against accidental cascade deletions."""
        engine = _get_engine()
        inspector = inspect(engine)
        for tbl_name in EXPECTED_TABLES:
            fks = inspector.get_foreign_keys(tbl_name, schema="public")
            for fk in fks:
                ondelete = fk.get("options", {}).get("ondelete", "").upper() if "options" in fk else ""
                assert ondelete not in ("CASCADE",), (
                    f"Forbidden CASCADE deletion on foreign key {fk['name']} in table {tbl_name}"
                )

    def test_check_constraints_registered(self):
        """Check constraints for coordinate bounds, probabilities, and statuses must exist."""
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT conname, relname "
                "FROM pg_constraint c "
                "JOIN pg_class r ON c.conrelid = r.oid "
                "JOIN pg_namespace n ON r.relnamespace = n.oid "
                "WHERE n.nspname = 'public' AND c.contype = 'c'"
            )).fetchall()

        assert len(rows) >= 50, f"Expected >= 50 check constraints, found {len(rows)}"

    def test_coordinate_check_constraint_enforcement(self):
        """Inserting invalid latitude (>90) must be rejected by check constraints."""
        engine = _get_engine()
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                # Attempt to insert an invalid station with latitude = 95.0
                conn.execute(text(
                    "INSERT INTO river_stations ("
                    "  id, name, station_code, latitude, longitude"
                    ") VALUES ("
                    f"  '{uuid.uuid4()}', 'Invalid Station', 'TEST_INVALID_LAT', 95.0, 77.0"
                    ")"
                ))
                pytest.fail("Database allowed latitude = 95.0; check constraint failed to enforce")
            except IntegrityError:
                # Expected check violation
                trans.rollback()

    def test_status_check_constraint_enforcement(self):
        """Inserting an invalid status value must be rejected by check constraints."""
        engine = _get_engine()
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(
                    "INSERT INTO users ("
                    "  id, email, role, created_at, updated_at"
                    ") VALUES ("
                    f"  '{uuid.uuid4()}', 'test_invalid_role@example.com', 'INVALID_ROLE', NOW(), NOW()"
                    ")"
                ))
                pytest.fail("Database allowed role = 'INVALID_ROLE'; check constraint failed to enforce")
            except IntegrityError:
                # Expected check violation
                trans.rollback()

    def test_data_contract_nullability_and_preservation(self):
        """Data contract rule: missing sensor readings must be stored as NULL (missing != 0)."""
        session_factory = _get_session_factory()
        with session_factory() as session:
            # Create minimal parent hierarchy for river observation
            src_id = uuid.uuid4()
            basin_id = uuid.uuid4()
            river_id = uuid.uuid4()
            station_id = uuid.uuid4()
            obs_id = uuid.uuid4()

            now = datetime.now(timezone.utc)

            src = DataSource(
                id=src_id,
                name="CWC Test Observation Source",
                organization="Central Water Commission",
                source_url="https://cwc.gov.in",
                access_method="REST_API",
                data_type="HYDROLOGICAL",
            )
            basin = RiverBasin(
                id=basin_id,
                name="Test Cauvery Basin",
                code="CAUV_TEST",
            )
            river = River(
                id=river_id,
                name="Test Cauvery",
                basin_id=basin_id,
            )
            station = RiverStation(
                id=station_id,
                station_code="STN_TEST_001",
                name="Test Station 1",
                river_id=river_id,
                latitude=12.5,
                longitude=76.8,
            )
            # Insert observation with NULL measurements — sensor offline scenario
            obs = RiverObservation(
                id=obs_id,
                station_id=station_id,
                source_id=src_id,
                observed_at=now,
                water_level=None,      # MISSING != 0
                discharge=None,        # MISSING != 0
                quality_status="MISSING",
                source_record_id="REC_001",
            )

            session.add_all([src, basin])
            session.flush()
            session.add(river)
            session.flush()
            session.add(station)
            session.flush()
            session.add(obs)
            session.flush()

            # Retrieve and verify measurements are strictly NULL, not converted to 0.0
            queried_obs = session.query(RiverObservation).filter_by(id=obs_id).one()
            assert queried_obs.water_level is None, "Missing water level was mutated away from NULL"
            assert queried_obs.discharge is None, "Missing discharge was mutated away from NULL"
            assert queried_obs.quality_status == "MISSING"
            assert queried_obs.source_id == src_id

            # Roll back so the test leaves no database footprint
            session.rollback()

    def test_observation_tables_empty_no_fake_data(self):
        """All observation tables must currently have 0 rows (no mock/fabricated data)."""
        engine = _get_engine()
        observation_tables = [
            "river_observations",
            "rainfall_observations",
            "weather_observations",
            "reservoir_observations",
            "flood_observations",
        ]
        with engine.connect() as conn:
            for tbl in observation_tables:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                assert count == 0, f"Table {tbl} contains {count} rows; expected 0 (no fake data allowed)"
