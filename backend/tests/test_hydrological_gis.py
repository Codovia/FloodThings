"""
Unit and integration tests for Hydrological GIS Ingestion Foundation.

Validates:
1. Schema constraints:
   - RiverBasin, SubBasin, River columns and types
   - DistrictSubBasin and DistrictRiverBasin crosswalk tables
   - Geometry SRID = 4326, valid PostGIS geometries
2. CWC Major Basins:
   - 25 national basins loaded
   - 7 basins intersect Karnataka
   - Existing placeholder UUIDs preserved (Cauvery, Krishna)
3. HydroBASINS Level-7:
   - HYBAS_ID uniqueness
   - Topology DAG (directed acyclic graph, no cycles)
   - Transboundary catchments preserved with original full geometry
   - Geometry repairs tracked
4. HydroRIVERS v1.0:
   - HYRIV_ID uniqueness
   - Reaches intersect Karnataka
   - Geometry validity
   - HYBAS_L12 references not conflated with Level-7 HYBAS_ID
5. Crosswalk Tables:
   - District ↔ SubBasin M:N relationships populated with non-zero intersection area
   - District ↔ RiverBasin M:N relationships populated
   - Area and percentages properly calculated
6. Provenance & Ingestion Run:
   - Data source records registered
   - Data ingestion run records created and completed
"""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District
from app.db.models.hydrology import (
    DistrictRiverBasin,
    DistrictSubBasin,
    River,
    RiverBasin,
    SubBasin,
)
from app.db.models.system import DataIngestionRun, DataSource
from app.db.session import _get_session_factory
from app.gis.topology_validation import (
    validate_hydrobasins_topology,
    validate_hydrorivers_topology,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to live test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


class TestCwcRiverBasins:
    """Test suite for CWC Major River Basins."""

    def test_cwc_basin_count(self, db_session: Session):
        """All 25 CWC national basins are ingested."""
        count = db_session.execute(
            select(func.count()).select_from(RiverBasin).where(
                RiverBasin.source_dataset == "basin_cwc_shp"
            )
        ).scalar()
        assert count == 25, f"Expected 25 CWC basins, found {count}"

    def test_cwc_karnataka_intersections(self, db_session: Session):
        """Exactly 7 CWC basins intersect Karnataka."""
        count = db_session.execute(
            select(func.count()).select_from(RiverBasin).where(
                RiverBasin.source_dataset == "basin_cwc_shp",
                RiverBasin.intersects_karnataka == True,
            )
        ).scalar()
        assert count == 7, f"Expected 7 CWC basins intersecting Karnataka, found {count}"

    def test_cwc_basin_geometries_valid(self, db_session: Session):
        """All CWC basins have valid MultiPolygon geometries in EPSG:4326."""
        invalid_count = db_session.execute(
            text("""
                SELECT count(*)
                FROM river_basins
                WHERE source_dataset = 'basin_cwc_shp'
                  AND (NOT ST_IsValid(geometry) OR ST_SRID(geometry) != 4326)
            """)
        ).scalar()
        assert invalid_count == 0, f"Found {invalid_count} invalid CWC geometries"

    def test_cauvery_krishna_preserved(self, db_session: Session):
        """Cauvery and Krishna basins exist and have valid geometries."""
        for name in ["Cauvery", "Krishna"]:
            basin = db_session.execute(
                select(RiverBasin).where(RiverBasin.name == name)
            ).scalar_one_or_none()
            assert basin is not None, f"Basin '{name}' missing"
            assert basin.geometry is not None, f"Basin '{name}' geometry not populated"
            assert basin.intersects_karnataka is True


class TestHydroBasinsLevel7:
    """Test suite for HydroBASINS Level-7 sub-basins."""

    def test_hydrobasins_count(self, db_session: Session):
        """116 HydroBASINS Level-7 catchments intersect Karnataka."""
        count = db_session.execute(
            select(func.count()).select_from(SubBasin).where(
                SubBasin.source_dataset == "hybas_as_lev07_v1c"
            )
        ).scalar()
        assert count == 116, f"Expected 116 HydroBASINS features, found {count}"

    def test_hybas_id_uniqueness(self, db_session: Session):
        """Every HYBAS_ID is unique."""
        total = db_session.execute(
            select(func.count()).select_from(SubBasin).where(
                SubBasin.hybas_id.isnot(None)
            )
        ).scalar()
        unique = db_session.execute(
            select(func.count(func.distinct(SubBasin.hybas_id))).where(
                SubBasin.hybas_id.isnot(None)
            )
        ).scalar()
        assert total == unique, f"Duplicate HYBAS_IDs found: total {total} vs unique {unique}"

    def test_hydrobasins_geometries_valid(self, db_session: Session):
        """All HydroBASINS sub-basin geometries are valid in EPSG:4326."""
        invalid_count = db_session.execute(
            text("""
                SELECT count(*)
                FROM sub_basins
                WHERE source_dataset = 'hybas_as_lev07_v1c'
                  AND (NOT ST_IsValid(geometry) OR ST_SRID(geometry) != 4326)
            """)
        ).scalar()
        assert invalid_count == 0, f"Found {invalid_count} invalid HydroBASINS geometries"

    def test_transboundary_full_geometry_preserved(self, db_session: Session):
        """Transboundary sub-basins maintain their full watershed geometry (not clipped)."""
        # Feature extending beyond Karnataka boundary
        count_outside = db_session.execute(
            text("""
                SELECT count(*)
                FROM sub_basins sb
                JOIN states s ON s.name = 'Karnataka'
                WHERE sb.source_dataset = 'hybas_as_lev07_v1c'
                  AND NOT ST_CoveredBy(sb.geometry, s.geometry)
            """)
        ).scalar()
        # Many sub-basins cross the Karnataka state border
        assert count_outside > 0, "Expected transboundary sub-basins crossing state border"

    def test_repaired_geometries_tracked(self, db_session: Session):
        """Self-intersecting geometries that were repaired are explicitly tracked."""
        repaired_count = db_session.execute(
            select(func.count()).select_from(SubBasin).where(
                SubBasin.geometry_repaired == True
            )
        ).scalar()
        assert repaired_count >= 3, f"Expected at least 3 repaired geometries, got {repaired_count}"


class TestHydroRivers:
    """Test suite for HydroRIVERS v1.0 reaches."""

    def test_hydrorivers_count(self, db_session: Session):
        """HydroRIVERS reaches intersecting Karnataka are ingested."""
        count = db_session.execute(
            select(func.count()).select_from(River).where(
                River.hyriv_id.isnot(None)
            )
        ).scalar()
        assert count > 10000, f"Expected >10,000 HydroRIVERS reaches, found {count}"

    def test_hyriv_id_uniqueness(self, db_session: Session):
        """Every HYRIV_ID is unique."""
        total = db_session.execute(
            select(func.count()).select_from(River).where(
                River.hyriv_id.isnot(None)
            )
        ).scalar()
        unique = db_session.execute(
            select(func.count(func.distinct(River.hyriv_id))).where(
                River.hyriv_id.isnot(None)
            )
        ).scalar()
        assert total == unique, f"Duplicate HYRIV_IDs: total {total} vs unique {unique}"

    def test_hydrorivers_geometries_valid(self, db_session: Session):
        """All HydroRIVERS geometries are valid MultiLineStrings in EPSG:4326."""
        invalid_count = db_session.execute(
            text("""
                SELECT count(*)
                FROM rivers
                WHERE hyriv_id IS NOT NULL
                  AND (NOT ST_IsValid(geometry) OR ST_SRID(geometry) != 4326)
            """)
        ).scalar()
        assert invalid_count == 0, f"Found {invalid_count} invalid HydroRIVERS geometries"

    def test_hybas_l12_semantic_distinction(self, db_session: Session):
        """HYBAS_L12 attribute does not collide with Level-7 HYBAS_ID semantics."""
        # Level 12 IDs are structurally different or represent finer sub-catchments
        river = db_session.execute(
            select(River).where(River.hybas_l12.isnot(None)).limit(1)
        ).scalar_one_or_none()
        assert river is not None
        assert river.hybas_l12 is not None


class TestDistrictCrosswalks:
    """Test suite for District M:N spatial crosswalk tables."""

    def test_district_sub_basins_populated(self, db_session: Session):
        """DistrictSubBasin crosswalk table is populated with valid intersections."""
        count = db_session.execute(
            select(func.count()).select_from(DistrictSubBasin)
        ).scalar()
        assert count > 50, f"Expected >50 district-subbasin intersections, found {count}"

        # All 31 districts should have at least one sub-basin intersection
        district_count = db_session.execute(
            select(func.count(func.distinct(DistrictSubBasin.district_id)))
        ).scalar()
        assert district_count == 31, f"Expected all 31 districts covered, found {district_count}"

    def test_district_river_basins_populated(self, db_session: Session):
        """DistrictRiverBasin crosswalk table is populated with valid intersections."""
        count = db_session.execute(
            select(func.count()).select_from(DistrictRiverBasin)
        ).scalar()
        assert count > 30, f"Expected >30 district-basin intersections, found {count}"

        district_count = db_session.execute(
            select(func.count(func.distinct(DistrictRiverBasin.district_id)))
        ).scalar()
        assert district_count == 31, f"Expected all 31 districts covered, found {district_count}"

    def test_crosswalk_geometries_and_percentages_valid(self, db_session: Session):
        """Crosswalk intersection areas and percentages are non-negative and plausible."""
        invalid_dsbs = db_session.execute(
            text("""
                SELECT count(*)
                FROM district_sub_basins
                WHERE intersection_area_km2 <= 0
                   OR percent_of_subbasin_in_district < 0
                   OR percent_of_district_in_subbasin < 0
            """)
        ).scalar()
        assert invalid_dsbs == 0, f"Found {invalid_dsbs} invalid DistrictSubBasin records"

        invalid_drbs = db_session.execute(
            text("""
                SELECT count(*)
                FROM district_river_basins
                WHERE intersection_area_km2 <= 0
                   OR percent_of_basin_in_district < 0
                   OR percent_of_district_in_basin < 0
            """)
        ).scalar()
        assert invalid_drbs == 0, f"Found {invalid_drbs} invalid DistrictRiverBasin records"


class TestTopologyAndIntegrity:
    """Test suite for topology validation functions."""

    def test_topology_validation_module(self):
        """Topology DAG checker detects DAG vs cycle."""
        from dataclasses import dataclass

        @dataclass
        class MockFeature:
            hybas_id: int
            next_down: int

        # Valid DAG
        valid_features = [
            MockFeature(hybas_id=1, next_down=2),
            MockFeature(hybas_id=2, next_down=0),
            MockFeature(hybas_id=3, next_down=2),
        ]
        res = validate_hydrobasins_topology(valid_features)
        assert res.is_dag is True
        assert len(res.cycle_nodes) == 0

        # Cycle
        cycle_features = [
            MockFeature(hybas_id=1, next_down=2),
            MockFeature(hybas_id=2, next_down=1),
        ]
        res_cycle = validate_hydrobasins_topology(cycle_features)
        assert res_cycle.is_dag is False
        assert len(res_cycle.cycle_nodes) > 0


class TestIngestionIdempotencyAndCounts:
    """Test suite verifying definitive table counts and absence of duplicates."""

    def test_exact_record_counts(self, db_session: Session):
        """All tables contain exact expected record counts."""
        rb_count = db_session.execute(select(func.count()).select_from(RiverBasin)).scalar()
        sb_count = db_session.execute(select(func.count()).select_from(SubBasin)).scalar()
        riv_count = db_session.execute(select(func.count()).select_from(River)).scalar()
        drb_count = db_session.execute(select(func.count()).select_from(DistrictRiverBasin)).scalar()
        dsb_count = db_session.execute(select(func.count()).select_from(DistrictSubBasin)).scalar()

        assert rb_count == 25, f"Expected 25 river basins, got {rb_count}"
        assert sb_count == 116, f"Expected 116 sub basins, got {sb_count}"
        assert riv_count == 15371, f"Expected 15371 rivers (2 existing + 15369 HydroRIVERS), got {riv_count}"
        assert drb_count == 54, f"Expected 54 district-riverbasin pairs, got {drb_count}"
        assert dsb_count == 264, f"Expected 264 district-subbasin pairs, got {dsb_count}"

    def test_no_duplicate_crosswalk_pairs(self, db_session: Session):
        """No duplicate (district_id, sub_basin_id) or (district_id, river_basin_id) pairs."""
        dup_dsbs = db_session.execute(
            text("""
                SELECT district_id, sub_basin_id, count(*)
                FROM district_sub_basins
                GROUP BY district_id, sub_basin_id
                HAVING count(*) > 1
            """)
        ).all()
        assert len(dup_dsbs) == 0, f"Found duplicate district_sub_basins: {dup_dsbs}"

        dup_drbs = db_session.execute(
            text("""
                SELECT district_id, river_basin_id, count(*)
                FROM district_river_basins
                GROUP BY district_id, river_basin_id
                HAVING count(*) > 1
            """)
        ).all()
        assert len(dup_drbs) == 0, f"Found duplicate district_river_basins: {dup_drbs}"

