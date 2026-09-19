"""
Phase 3.4B: Karnataka District Code Integrity & Controlled Station Correction Tests.

Tests:
1. Complete 31-district authoritative LGD code integrity in database.
2. AKKIHEBBAL river station association to Mandya (district_id and spatial containment).
3. Preservation of 101 river observations and station FK integrity.
4. Absence of unintended FK changes across all environmental tables.
5. Atomic transaction rollback safety in ControlledDistrictCorrector.
6. Ingestion adapter hardening in NwicRiverLevelAdapter (code/name cross-validation and conflict rejection).
7. Spatial association audit verification (100% matched, 0 discrepancies).
"""

from __future__ import annotations

import io
from typing import Any
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.flood import FloodObservation
from app.db.models.geography import District, Taluk
from app.db.models.hydrology import RiverObservation, RiverStation
from app.db.models.weather import RainfallObservation, WeatherForecast, WeatherObservation
from app.db.session import _get_session_factory
from app.gis.controlled_correction import ControlledDistrictCorrector
from app.gis.district_code_audit import DistrictCodeAuditor
from app.gis.spatial_audit import SpatialAssociationAuditor
from app.ingestion.base import IngestionMetrics
from app.ingestion.sources.geography import KARNATAKA_DISTRICTS_LGD
from app.ingestion.sources.nwic_river import NwicRiverLevelAdapter


@pytest.fixture
def db_session() -> Session:
    factory = _get_session_factory()
    with factory() as session:
        yield session


class TestDistrictCodeIntegrity:
    """Test suite for Phase 3.4B district code audit and correction."""

    def test_all_31_district_codes_authoritative(self, db_session: Session) -> None:
        """Verify all 31 districts in DB have exact authoritative LGD codes."""
        districts = list(db_session.execute(select(District).order_by(District.name)).scalars().all())
        assert len(districts) == 31, f"Expected 31 districts, found {len(districts)}"

        expected_map = {d["name"]: d["code"] for d in KARNATAKA_DISTRICTS_LGD}
        assert len(expected_map) == 31

        mismatches: list[str] = []
        for d in districts:
            exp_code = expected_map.get(d.name)
            if exp_code != d.code:
                mismatches.append(f"{d.name}: expected {exp_code}, found {d.code}")

        assert not mismatches, f"District code mismatches found: {mismatches}"

    def test_district_code_auditor_reports_zero_mismatches(self, db_session: Session) -> None:
        """Verify DistrictCodeAuditor reports 31 matches and 0 mismatches."""
        auditor = DistrictCodeAuditor(db_session)
        report = auditor.audit()

        assert report.total_districts == 31
        assert report.matching_codes_count == 31
        assert report.mismatched_codes_count == 0
        assert report.affected_tables_summary["districts"] == 31

    def test_akkihebbal_station_associated_with_mandya(self, db_session: Session) -> None:
        """Verify AKKIHEBBAL river station is linked to Mandya district."""
        rs_stmt = select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        rs = db_session.execute(rs_stmt).scalar_one_or_none()
        assert rs is not None, "Station AKKIHEBBAL not found"

        mandya = db_session.execute(select(District).where(District.name == "Mandya")).scalar_one()
        assert rs.district_id == mandya.id, (
            f"AKKIHEBBAL district_id {rs.district_id} does not match Mandya {mandya.id}"
        )
        assert mandya.code == "544", f"Expected Mandya LGD code 544, found {mandya.code}"

    def test_akkihebbal_spatially_contained_in_mandya(self, db_session: Session) -> None:
        """Verify AKKIHEBBAL coordinates are spatially contained within Mandya district boundary."""
        spatial_query = text("""
            SELECT d.name, d.code
            FROM districts d, river_stations rs
            WHERE rs.station_code = 'AKKIHEBBAL'
              AND ST_Contains(d.geometry, ST_SetSRID(ST_Point(rs.longitude, rs.latitude), 4326));
        """)
        row = db_session.execute(spatial_query).first()
        assert row is not None, "AKKIHEBBAL point not contained in any district"
        assert row[0] == "Mandya", f"Expected spatial district Mandya, found {row[0]}"
        assert row[1] == "544", f"Expected spatial district code 544, found {row[1]}"

    def test_river_observations_preservation(self, db_session: Session) -> None:
        """Verify all 101 river observations remain intact with unchanged station FK."""
        rs_stmt = select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        rs = db_session.execute(rs_stmt).scalar_one()

        obs_count = db_session.execute(
            select(func.count()).select_from(RiverObservation).where(RiverObservation.station_id == rs.id)
        ).scalar()
        assert obs_count == 101, f"Expected 101 observations, found {obs_count}"

        # Verify no orphan observations exist
        orphan_count = db_session.execute(
            select(func.count())
            .select_from(RiverObservation)
            .outerjoin(RiverStation, RiverObservation.station_id == RiverStation.id)
            .where(RiverStation.id.is_(None))
        ).scalar()
        assert orphan_count == 0, f"Found {orphan_count} orphan river observations"

    def test_no_unintended_fk_changes(self, db_session: Session) -> None:
        """Verify all FK-bearing tables reference valid district UUIDs and have expected row counts."""
        # Row count checks
        w_cnt = db_session.execute(select(func.count()).select_from(WeatherObservation)).scalar()
        r_cnt = db_session.execute(select(func.count()).select_from(RainfallObservation)).scalar()
        wf_cnt = db_session.execute(select(func.count()).select_from(WeatherForecast)).scalar()
        fo_cnt = db_session.execute(select(func.count()).select_from(FloodObservation)).scalar()
        t_cnt = db_session.execute(select(func.count()).select_from(Taluk)).scalar()

        assert w_cnt == 397, f"Weather observations count changed: {w_cnt}"
        assert r_cnt == 397, f"Rainfall observations count changed: {r_cnt}"
        assert wf_cnt == 275, f"Weather forecasts count changed: {wf_cnt}"
        assert fo_cnt == 186, f"Flood observations count changed: {fo_cnt}"
        assert t_cnt == 240, f"Taluks count changed: {t_cnt}"

        # Foreign key integrity: verify 0 broken district_id references
        for model, col_name in [
            (WeatherObservation, "district_id"),
            (RainfallObservation, "district_id"),
            (WeatherForecast, "district_id"),
            (FloodObservation, "district_id"),
            (Taluk, "district_id"),
        ]:
            col = getattr(model, col_name)
            broken = db_session.execute(
                select(func.count())
                .select_from(model)
                .outerjoin(District, col == District.id)
                .where(col.isnot(None), District.id.is_(None))
            ).scalar()
            assert broken == 0, f"Broken district FK references in {model.__name__}: {broken}"

    def test_transaction_rollback_safety(self, db_session: Session) -> None:
        """Verify ControlledDistrictCorrector dry-run rolls back without committing."""
        corrector = ControlledDistrictCorrector(db_session)
        res = corrector.execute_correction(dry_run=True)

        assert res.transaction_committed is False
        assert res.districts_updated_count == 31
        assert res.river_stations_updated_count == 1
        assert res.district_uuids_preserved is True
        assert res.river_observations_count_intact == 101

    def test_nwic_river_adapter_hardening(self, db_session: Session) -> None:
        """Verify NwicRiverLevelAdapter validates district code and rejects conflicting code/name."""
        adapter = NwicRiverLevelAdapter(db_session)

        all_districts = list(db_session.execute(select(District)).scalars().all())
        districts_by_name = {d.name: d for d in all_districts}
        districts_by_code = {d.code: d for d in all_districts if d.code}

        # 1. Matching authoritative code and matching name -> success
        m1 = IngestionMetrics()
        d1 = adapter._resolve_district(
            dist_lgd="544",
            dist_name_raw="Mandya",
            station_name="TEST_STN_1",
            districts_by_name=districts_by_name,
            districts_by_code=districts_by_code,
            metrics=m1,
        )
        assert d1 is not None
        assert d1.name == "Mandya"
        assert len(m1.errors) == 0

        # 2. Conflicting code and name -> rejected (returns None and logs error)
        m2 = IngestionMetrics()
        d2 = adapter._resolve_district(
            dist_lgd="543",  # Koppal code
            dist_name_raw="Mandya",  # Mandya name
            station_name="TEST_STN_2",
            districts_by_name=districts_by_name,
            districts_by_code=districts_by_code,
            metrics=m2,
        )
        assert d2 is None, "Conflicting code and name must be rejected"
        assert any("CONFLICT" in err for err in m2.errors)

        # 3. Valid name with unrecognized code -> resolves by name
        m3 = IngestionMetrics()
        d3 = adapter._resolve_district(
            dist_lgd="9999",
            dist_name_raw="Mandya",
            station_name="TEST_STN_3",
            districts_by_name=districts_by_name,
            districts_by_code=districts_by_code,
            metrics=m3,
        )
        assert d3 is not None
        assert d3.name == "Mandya"

        # 4. Valid authoritative code with no name -> resolves by authoritative code
        m4 = IngestionMetrics()
        d4 = adapter._resolve_district(
            dist_lgd="544",
            dist_name_raw=None,
            station_name="TEST_STN_4",
            districts_by_name=districts_by_name,
            districts_by_code=districts_by_code,
            metrics=m4,
        )
        assert d4 is not None
        assert d4.name == "Mandya"

        # 5. Name alias normalization (e.g. "Bengaluru (Urban)") -> resolves to Bangalore Urban
        m5 = IngestionMetrics()
        d5 = adapter._resolve_district(
            dist_lgd="525",
            dist_name_raw="Bengaluru (Urban)",
            station_name="TEST_STN_5",
            districts_by_name=districts_by_name,
            districts_by_code=districts_by_code,
            metrics=m5,
        )
        assert d5 is not None
        assert d5.name == "Bangalore Urban"

    def test_spatial_audit_zero_discrepancies(self, db_session: Session) -> None:
        """Verify Phase 3.3 spatial association audit reports 100% match and 0 discrepancies."""
        auditor = SpatialAssociationAuditor(db_session)
        report = auditor.audit()

        assert report.weather_metrics.total_examined == 397
        assert report.weather_metrics.spatially_matched == 397

        assert report.rainfall_metrics.total_examined == 397
        assert report.rainfall_metrics.spatially_matched == 397

        assert report.taluk_metrics.total_examined == 240
        assert report.taluk_metrics.spatially_matched == 240

        assert report.ifi_metrics.total_examined == 186
        assert report.ifi_metrics.spatially_matched == 186

        # River station: 1/1 matched, 0 outside, 0 manual review
        rs = report.river_station_metrics
        assert rs.total_examined == 1
        assert rs.spatially_matched == 1
        assert rs.outside_assigned_district == 0
        assert rs.requires_manual_review == 0

        # Zero discrepancies overall
        assert len(report.discrepancies) == 0

        total_examined = (
            report.weather_metrics.total_examined
            + report.rainfall_metrics.total_examined
            + report.river_station_metrics.total_examined
            + report.taluk_metrics.total_examined
            + report.ifi_metrics.total_examined
        )
        total_matched = (
            report.weather_metrics.spatially_matched
            + report.rainfall_metrics.spatially_matched
            + report.river_station_metrics.spatially_matched
            + report.taluk_metrics.spatially_matched
            + report.ifi_metrics.spatially_matched
        )
        assert total_examined == 1221
        assert total_matched == 1221
