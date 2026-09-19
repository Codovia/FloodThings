"""
Tests for Administrative GIS ↔ Environmental Spatial Association Audit (Phase 3.3).

Validates:
1. Deterministic execution of SpatialAssociationAuditor.
2. 100% spatial containment of weather observations within assigned districts.
3. 100% spatial containment of rainfall observations within assigned districts.
4. Detection of river station Akkihebbal spatial discrepancy (Koppal assigned vs Mandya spatial).
5. 100% point-on-surface containment of 240 taluks within assigned districts,
   with 196 boundary slivers accurately classified under digitization precision tolerance.
6. Verification of 186 IFI historical flood observations: 100% valid district FKs,
   100% NULL geometry (zero coordinate fabrication).
7. Strict read-only enforcement (no database mutations).
8. JSON export and text summary formatting.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.flood import FloodObservation
from app.db.models.geography import District, State, Taluk
from app.db.models.hydrology import RiverStation
from app.db.models.weather import RainfallObservation, WeatherObservation
from app.db.session import _get_session_factory
from app.gis.spatial_audit import (
    EntityAuditMetrics,
    IfiAdministrativeRecord,
    SpatialAssociationAuditor,
    SpatialAssociationAuditReport,
    SpatialDiscrepancy,
    TalukContainmentRecord,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to live test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def audit_report(db_session: Session) -> SpatialAssociationAuditReport:
    """Run audit once for module-level assertions."""
    auditor = SpatialAssociationAuditor(db_session)
    return auditor.audit()


class TestSpatialAssociationAudit:
    """Test suite for Phase 3.3 Spatial Association Audit."""

    def test_audit_execution_and_structure(self, audit_report: SpatialAssociationAuditReport):
        """Verify audit executes and returns all expected top-level structures."""
        assert isinstance(audit_report, SpatialAssociationAuditReport)
        assert audit_report.audited_at is not None
        assert isinstance(audit_report.weather_metrics, EntityAuditMetrics)
        assert isinstance(audit_report.rainfall_metrics, EntityAuditMetrics)
        assert isinstance(audit_report.river_station_metrics, EntityAuditMetrics)
        assert isinstance(audit_report.taluk_metrics, EntityAuditMetrics)
        assert isinstance(audit_report.ifi_metrics, EntityAuditMetrics)
        assert isinstance(audit_report.ifi_details, IfiAdministrativeRecord)

    def test_weather_observations_spatial_containment(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """Verify all 397 weather observations are strictly inside assigned districts."""
        m = audit_report.weather_metrics
        assert m.entity_type == "weather_observations"
        assert m.total_examined == 397
        assert m.spatially_matched == 397
        assert m.outside_karnataka == 0
        assert m.outside_assigned_district == 0
        assert m.missing_or_invalid_geometry == 0
        assert m.requires_manual_review == 0

    def test_rainfall_observations_spatial_containment(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """Verify all 397 rainfall observations are strictly inside assigned districts."""
        m = audit_report.rainfall_metrics
        assert m.entity_type == "rainfall_observations"
        assert m.total_examined == 397
        assert m.spatially_matched == 397
        assert m.outside_karnataka == 0
        assert m.outside_assigned_district == 0
        assert m.missing_or_invalid_geometry == 0
        assert m.requires_manual_review == 0

    def test_river_station_akkihebbal_discrepancy(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """
        Verify river station Akkihebbal spatial mismatch is detected without mutation:
        - Stored assigned district: Koppal
        - Actual spatial district: Mandya
        """
        m = audit_report.river_station_metrics
        assert m.entity_type == "river_stations"
        assert m.total_examined == 1
        assert m.spatially_matched == 0
        assert m.outside_karnataka == 0
        assert m.outside_assigned_district == 1
        assert m.requires_manual_review == 1

        river_discrepancies = [
            d for d in audit_report.discrepancies if d.entity_type == "river_stations"
        ]
        assert len(river_discrepancies) == 1
        disc = river_discrepancies[0]
        assert disc.identifier == "AKKIHEBBAL"
        assert disc.assigned_district_name == "Koppal"
        assert disc.spatial_district_name == "Mandya"
        assert disc.is_in_karnataka is True
        assert disc.discrepancy_type == "OUTSIDE_ASSIGNED_DISTRICT"
        assert disc.distance_to_assigned_district_m is not None
        assert disc.distance_to_assigned_district_m > 250_000  # ~284 km away
        assert disc.distance_to_spatial_boundary_m is not None
        assert disc.distance_to_spatial_boundary_m < 10_000  # ~2.9 km from Mandya boundary

    def test_taluk_containment_and_boundary_precision(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """
        Verify taluk-to-district containment:
        - 240 taluks examined
        - 240 have PointOnSurface inside assigned district (100.0%)
        - 44 are strictly within (ST_Within = TRUE)
        - 196 have micro boundary slivers (overlap >= 99.999%)
        - 0 cross-district mismatches or disjoint taluks
        """
        m = audit_report.taluk_metrics
        assert m.entity_type == "taluk_containment"
        assert m.total_examined == 240
        assert m.spatially_matched == 240
        assert m.outside_karnataka == 0
        assert m.outside_assigned_district == 0
        assert m.missing_or_invalid_geometry == 0
        assert m.boundary_or_ambiguous == 196
        assert m.requires_manual_review == 0
        assert m.details["strictly_within_count"] == 44
        assert m.details["point_on_surface_within_count"] == 240

        assert len(audit_report.boundary_cases) == 196
        for case in audit_report.boundary_cases:
            assert isinstance(case, TalukContainmentRecord)
            assert case.point_on_surface_within is True
            assert case.overlap_percentage >= 99.999
            assert case.status == "BOUNDARY_SLIVER"

    def test_ifi_historical_evidence_administrative_alignment(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """
        Verify historical IFI flood observations:
        - 186 records examined
        - 186 reference valid KSR-SAC districts (100.0%)
        - 186 have geometry IS NULL (100.0% zero-fabrication)
        - 0 have fabricated coordinates or inferred centroids
        - 23 distinct districts represented
        """
        m = audit_report.ifi_metrics
        assert m.entity_type == "flood_observations_ifi"
        assert m.total_examined == 186
        assert m.spatially_matched == 186
        assert m.outside_karnataka == 0
        assert m.outside_assigned_district == 0
        assert m.missing_or_invalid_geometry == 0
        assert m.requires_manual_review == 0

        details = audit_report.ifi_details
        assert details.total_records == 186
        assert details.valid_district_references == 186
        assert details.invalid_district_references == 0
        assert details.null_geometry_verified == 186
        assert details.unexpected_geometry_count == 0
        assert details.distinct_districts_referenced == 23

    def test_read_only_invariant(self, db_session: Session):
        """Verify audit execution is strictly read-only and does not mutate any DB rows."""
        # Capture counts before
        counts_before = {
            "weather": db_session.execute(select(func.count()).select_from(WeatherObservation)).scalar(),
            "rainfall": db_session.execute(select(func.count()).select_from(RainfallObservation)).scalar(),
            "river_stations": db_session.execute(select(func.count()).select_from(RiverStation)).scalar(),
            "taluks": db_session.execute(select(func.count()).select_from(Taluk)).scalar(),
            "flood_obs": db_session.execute(select(func.count()).select_from(FloodObservation)).scalar(),
            "districts": db_session.execute(select(func.count()).select_from(District)).scalar(),
            "states": db_session.execute(select(func.count()).select_from(State)).scalar(),
        }

        # Check Akkihebbal district_id before
        rs_before = db_session.execute(
            select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        ).scalar_one()
        akkihebbal_dist_id_before = rs_before.district_id

        # Run audit
        auditor = SpatialAssociationAuditor(db_session)
        auditor.audit()

        # Capture counts after
        counts_after = {
            "weather": db_session.execute(select(func.count()).select_from(WeatherObservation)).scalar(),
            "rainfall": db_session.execute(select(func.count()).select_from(RainfallObservation)).scalar(),
            "river_stations": db_session.execute(select(func.count()).select_from(RiverStation)).scalar(),
            "taluks": db_session.execute(select(func.count()).select_from(Taluk)).scalar(),
            "flood_obs": db_session.execute(select(func.count()).select_from(FloodObservation)).scalar(),
            "districts": db_session.execute(select(func.count()).select_from(District)).scalar(),
            "states": db_session.execute(select(func.count()).select_from(State)).scalar(),
        }

        assert counts_before == counts_after

        # Verify Akkihebbal district_id was NOT changed
        rs_after = db_session.execute(
            select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        ).scalar_one()
        assert rs_after.district_id == akkihebbal_dist_id_before

    def test_report_serialization_and_summary(
        self, audit_report: SpatialAssociationAuditReport
    ):
        """Verify report serialization to dict, JSON, and summary text."""
        # Dict
        d = audit_report.to_dict()
        assert "audited_at" in d
        assert "entities" in d
        assert "discrepancies" in d
        assert "summary" in d
        assert d["summary"]["total_records_examined"] == 397 + 397 + 1 + 240 + 186
        assert d["summary"]["total_discrepancies"] == 1
        assert d["summary"]["total_requiring_manual_review"] == 1

        # JSON
        json_str = audit_report.to_json()
        parsed = json.loads(json_str)
        assert parsed["summary"]["total_discrepancies"] == 1

        # Summary text
        summary = audit_report.summary_text()
        assert "ADMINISTRATIVE GIS <-> ENVIRONMENTAL SPATIAL ASSOCIATION AUDIT" in summary
        assert "AKKIHEBBAL" in summary
        assert "Koppal" in summary
        assert "Mandya" in summary
        assert "TALUK BOUNDARY CASES (196)" in summary
        assert "IFI HISTORICAL FLOOD EVIDENCE ALIGNMENT" in summary
