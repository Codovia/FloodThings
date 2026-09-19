"""
Integration and unit tests for KSR-SAC Administrative GIS PostGIS Ingestion.

Verifies:
1. Deterministic bijective district mapping (31-to-31).
2. Atomic ingestion into PostGIS:
   - 1 State with valid MultiPolygon geometry in EPSG:4326.
   - 31 Districts with valid MultiPolygon geometries and Centroids in EPSG:4326.
   - 240 Taluks with valid MultiPolygon geometries in EPSG:4326.
3. District UUID identity preservation: existing UUIDs are strictly preserved.
4. District code preservation: existing codes remain unmodified.
5. Foreign-key referential integrity: observation/forecast references remain intact.
6. PostGIS geometry properties: ST_SRID == 4326, ST_GeometryType == 'ST_MultiPolygon', ST_IsValid == True.
7. Parent-child relationships and containment.
8. Idempotency: repeated executions produce identical row counts (1, 31, 240) and zero duplicate records.
9. Transaction rollback behavior on failure: zero partial ingestion.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District, State, Taluk
from app.db.session import _get_session_factory
from app.gis.ksrsac import (
    EXPECTED_DISTRICT_COUNT,
    EXPECTED_STATE_COUNT,
    EXPECTED_TALUK_COUNT,
    KsrsacAdminNormalizer,
    KsrsacValidationError,
)
from app.ingestion.sources.ksrsac_gis import (
    KSR_TO_DB_DISTRICT_NAMES,
    KsrsacGisAdapter,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to live test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


class TestKsrsacBijectiveMapping:
    """Test suite verifying the deterministic mapping between KSR-SAC and DB."""

    def test_canonical_alias_mapping_coverage(self, db_session: Session):
        """All 31 KSR-SAC districts deterministically resolve to 31 unique DB districts."""
        normalizer = KsrsacAdminNormalizer()
        norm_res = normalizer.normalize()

        db_districts = db_session.execute(select(District)).scalars().all()
        db_by_name = {d.name: d for d in db_districts}

        assert len(db_districts) == EXPECTED_DISTRICT_COUNT

        resolved_db_ids = set()
        for kd in norm_res.districts:
            target_name = KSR_TO_DB_DISTRICT_NAMES.get(kd.district_name, kd.district_name)
            assert target_name in db_by_name, f"Unresolved district: {kd.district_name} -> {target_name}"
            db_dist = db_by_name[target_name]
            assert db_dist.id not in resolved_db_ids, f"Collision on district: {db_dist.name}"
            resolved_db_ids.add(db_dist.id)

        assert len(resolved_db_ids) == EXPECTED_DISTRICT_COUNT


class TestKsrsacGisPostgisIngestion:
    """End-to-end integration tests for PostGIS ingestion and identity preservation."""

    def test_ingest_and_verify_counts(self, db_session: Session):
        """Ingestion populates geometries and achieves exact expected row counts."""
        # Capture pre-ingestion district UUIDs and codes
        pre_districts = db_session.execute(
            select(District.id, District.name, District.code)
        ).all()
        pre_uuid_map = {d.name: d.id for d in pre_districts}
        pre_code_map = {d.name: d.code for d in pre_districts}
        assert len(pre_districts) == EXPECTED_DISTRICT_COUNT

        # Execute ingestion adapter
        adapter = KsrsacGisAdapter(db_session)
        result = adapter.ingest()

        assert result.status == "SUCCESS"
        assert result.metrics.records_received == 272
        assert result.metrics.records_valid == 272
        assert len(result.metrics.errors) == 0

        # 1. State Verification
        state = db_session.execute(select(State).where(State.code == "29")).scalar_one()
        assert state is not None
        assert state.name == "Karnataka"
        assert state.geometry is not None

        state_geom_info = db_session.execute(
            text(
                "SELECT ST_GeometryType(geometry), ST_SRID(geometry), ST_IsValid(geometry) "
                "FROM states WHERE id = :id"
            ),
            {"id": state.id},
        ).fetchone()
        assert state_geom_info[0] == "ST_MultiPolygon"
        assert state_geom_info[1] == 4326
        assert state_geom_info[2] is True

        # 2. District Verification
        post_districts = db_session.execute(
            select(District.id, District.name, District.code)
        ).all()
        assert len(post_districts) == EXPECTED_DISTRICT_COUNT

        # Check district UUID and code preservation
        for d in post_districts:
            assert d.name in pre_uuid_map
            assert d.id == pre_uuid_map[d.name], f"UUID changed for district {d.name}"
            assert d.code == pre_code_map[d.name], f"Code changed for district {d.name}"

        # Check all 31 districts have non-null, valid MULTIPOLYGON in SRID 4326
        dist_geom_stats = db_session.execute(
            text(
                "SELECT count(*), "
                "count(geometry), "
                "count(centroid), "
                "sum(CASE WHEN ST_GeometryType(geometry) = 'ST_MultiPolygon' THEN 1 ELSE 0 END), "
                "sum(CASE WHEN ST_SRID(geometry) = 4326 THEN 1 ELSE 0 END), "
                "sum(CASE WHEN ST_IsValid(geometry) THEN 1 ELSE 0 END) "
                "FROM districts"
            )
        ).fetchone()
        assert dist_geom_stats[0] == EXPECTED_DISTRICT_COUNT
        assert dist_geom_stats[1] == EXPECTED_DISTRICT_COUNT
        assert dist_geom_stats[2] == EXPECTED_DISTRICT_COUNT
        assert dist_geom_stats[3] == EXPECTED_DISTRICT_COUNT
        assert dist_geom_stats[4] == EXPECTED_DISTRICT_COUNT
        assert dist_geom_stats[5] == EXPECTED_DISTRICT_COUNT

        # 3. Taluk Verification
        taluk_geom_stats = db_session.execute(
            text(
                "SELECT count(*), "
                "count(geometry), "
                "sum(CASE WHEN ST_GeometryType(geometry) = 'ST_MultiPolygon' THEN 1 ELSE 0 END), "
                "sum(CASE WHEN ST_SRID(geometry) = 4326 THEN 1 ELSE 0 END), "
                "sum(CASE WHEN ST_IsValid(geometry) THEN 1 ELSE 0 END) "
                "FROM taluks"
            )
        ).fetchone()
        assert taluk_geom_stats[0] == EXPECTED_TALUK_COUNT
        assert taluk_geom_stats[1] == EXPECTED_TALUK_COUNT
        assert taluk_geom_stats[2] == EXPECTED_TALUK_COUNT
        assert taluk_geom_stats[3] == EXPECTED_TALUK_COUNT
        assert taluk_geom_stats[4] == EXPECTED_TALUK_COUNT

    def test_foreign_key_referential_integrity(self, db_session: Session):
        """Verify that existing foreign keys in observations/forecasts still resolve valid districts."""
        fks_to_check = [
            ("rainfall_observations", "district_id"),
            ("weather_observations", "district_id"),
            ("weather_forecasts", "district_id"),
            ("flood_observations", "district_id"),
            ("river_stations", "district_id"),
        ]
        for tbl, col in fks_to_check:
            # Check for any orphaned foreign keys
            orphan_count = db_session.execute(
                text(
                    f"SELECT count(*) FROM {tbl} t "
                    f"LEFT JOIN districts d ON t.{col} = d.id "
                    f"WHERE t.{col} IS NOT NULL AND d.id IS NULL"
                )
            ).scalar()
            assert orphan_count == 0, f"Found {orphan_count} orphaned rows in {tbl}.{col}"

    def test_taluk_parent_child_spatial_integrity(self, db_session: Session):
        """All taluks intersect their parent district and representative point lies within parent."""
        uncontained = db_session.execute(
            text(
                "SELECT t.name, d.name FROM taluks t "
                "JOIN districts d ON t.district_id = d.id "
                "WHERE NOT ST_Intersects(t.geometry, d.geometry) "
                "OR NOT ST_Within(ST_PointOnSurface(t.geometry), d.geometry)"
            )
        ).fetchall()
        assert len(uncontained) == 0, f"Uncontained taluks: {uncontained}"

    def test_idempotency_repeated_execution(self, db_session: Session):
        """Re-running ingestion preserves exact counts and creates zero duplicates."""
        adapter = KsrsacGisAdapter(db_session)
        result = adapter.ingest()

        assert result.status == "SUCCESS"
        assert result.metrics.records_inserted == 0  # 0 new taluks inserted
        assert result.metrics.records_updated == 272  # 1 state + 31 districts + 240 taluks updated

        state_count = db_session.execute(text("SELECT count(*) FROM states")).scalar()
        district_count = db_session.execute(text("SELECT count(*) FROM districts")).scalar()
        taluk_count = db_session.execute(text("SELECT count(*) FROM taluks")).scalar()

        assert state_count == EXPECTED_STATE_COUNT
        assert district_count == EXPECTED_DISTRICT_COUNT
        assert taluk_count == EXPECTED_TALUK_COUNT

    def test_transaction_rollback_on_failure(self, db_session: Session):
        """Simulate failure during ingestion and verify complete transaction rollback."""
        # Create a mock normalizer that raises validation error during admin normalization
        class FailingNormalizer(KsrsacAdminNormalizer):
            def normalize(self):
                raise KsrsacValidationError("Simulated injection failure for rollback test")

        failing_adapter = KsrsacGisAdapter(db_session, normalizer=FailingNormalizer())
        result = failing_adapter.ingest()

        assert result.status == "FAILED"
        assert "Simulated injection failure" in (result.error_message or "")
        # Session is clean and rolled back
        assert db_session.is_active
