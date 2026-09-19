"""
Tests for AKKIHEBBAL River Station Provenance Investigation (Phase 3.4A).

Validates:
1. Raw source evidence: station name, agency, LGD 544, Mandya, KRISHNARAJPET, Cauvery/Hemavathi.
2. Database state: station AKKIHEBBAL assigned to Koppal, 101 river observations, 0 forecasts.
3. Spatial containment: point strictly inside Mandya district and Krishnarajpet taluk polygons.
4. Root cause diagnosis: LGD 544 in CWC matches official Mandya LGD, but geography.py seeded Koppal as 544.
5. Strict read-only invariant: zero database mutations during investigation.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.flood import FloodObservation
from app.db.models.geography import District, State, Taluk
from app.db.models.hydrology import RiverObservation, RiverStation
from app.db.models.weather import RainfallObservation, WeatherObservation
from app.db.session import _get_session_factory
from app.gis.akkihebbal_investigation import (
    AkkihebbalInvestigationReport,
    AkkihebbalProvenanceInvestigator,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to live test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def investigation_report(db_session: Session) -> AkkihebbalInvestigationReport:
    """Run investigation once for module assertions."""
    investigator = AkkihebbalProvenanceInvestigator(db_session)
    return investigator.investigate()


class TestAkkihebbalInvestigation:
    """Test suite for Phase 3.4A AKKIHEBBAL investigation."""

    def test_raw_source_evidence(self, investigation_report: AkkihebbalInvestigationReport):
        """Verify raw CWC source evidence extracted for AKKIHEBBAL."""
        r = investigation_report.raw_source_evidence
        assert r.station_code == "AKKIHEBBAL"
        assert r.station_name == "AKKIHEBBAL"
        assert r.agency == "CWC"
        assert r.state_name == "Karnataka"
        assert r.state_lgd_code == "29"
        assert r.district_name == "Mandya"
        assert r.district_lgd_code == "544"
        assert r.tehsil_name == "KRISHNARAJPET"
        assert r.river_name == "Cauvery"
        assert r.tributary_name == "Hemavathi"
        assert pytest.approx(r.latitude, rel=1e-4) == 12.5986
        assert pytest.approx(r.longitude, rel=1e-4) == 76.4005
        assert r.sample_records_count > 0

    def test_current_database_state(self, investigation_report: AkkihebbalInvestigationReport):
        """Verify current database state of AKKIHEBBAL after Phase 3.4B correction."""
        c = investigation_report.current_database_state
        assert c.station_code == "AKKIHEBBAL"
        assert c.assigned_district_name == "Mandya"
        assert c.assigned_district_code == "544"
        assert c.river_name == "Cauvery"
        assert c.basin_name == "Cauvery"
        assert c.is_active is True
        assert c.river_observations_count == 101
        assert c.river_forecasts_count == 0
        assert c.earliest_observation is not None
        assert c.latest_observation is not None

    def test_spatial_containment_in_ksrsac_polygons(
        self, investigation_report: AkkihebbalInvestigationReport
    ):
        """Verify authoritative KSR-SAC spatial containment inside Mandya / Krishnarajpet."""
        s = investigation_report.spatial_containment
        assert s.is_inside_karnataka is True
        assert s.spatial_district_name == "Mandya"
        assert s.spatial_district_code == "544"
        assert s.spatial_taluk_name == "Krishnarajpet"
        assert s.spatial_taluk_code == "5546"
        assert s.distance_to_assigned_district_m == 0.0  # Station is inside assigned district (Mandya)
        assert s.distance_to_spatial_district_boundary_m < 10_000  # ~2.9 km from Mandya boundary
        assert s.distance_to_spatial_taluk_boundary_m < 10_000

    def test_root_cause_analysis(self, investigation_report: AkkihebbalInvestigationReport):
        """Verify mechanical root cause diagnosis."""
        rc = investigation_report.root_cause
        assert rc.raw_cwc_supplied_lgd == "544"
        assert rc.raw_cwc_supplied_district == "Mandya"
        assert rc.geography_seeder_assigned_code_to_koppal == "544"
        assert rc.geography_seeder_assigned_code_to_mandya == "545"
        assert rc.official_lgd_for_mandya == "544"
        assert rc.official_lgd_for_koppal == "543"
        assert "nwic_river.py" in rc.mechanism

    def test_investigation_read_only_invariant(self, db_session: Session):
        """Verify investigation execution is strictly read-only and does not mutate any DB rows."""
        counts_before = {
            "river_stations": db_session.execute(select(func.count()).select_from(RiverStation)).scalar(),
            "river_observations": db_session.execute(select(func.count()).select_from(RiverObservation)).scalar(),
            "districts": db_session.execute(select(func.count()).select_from(District)).scalar(),
            "taluks": db_session.execute(select(func.count()).select_from(Taluk)).scalar(),
            "states": db_session.execute(select(func.count()).select_from(State)).scalar(),
        }

        rs_before = db_session.execute(
            select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        ).scalar_one()
        dist_id_before = rs_before.district_id

        # Run investigation
        investigator = AkkihebbalProvenanceInvestigator(db_session)
        investigator.investigate()

        counts_after = {
            "river_stations": db_session.execute(select(func.count()).select_from(RiverStation)).scalar(),
            "river_observations": db_session.execute(select(func.count()).select_from(RiverObservation)).scalar(),
            "districts": db_session.execute(select(func.count()).select_from(District)).scalar(),
            "taluks": db_session.execute(select(func.count()).select_from(Taluk)).scalar(),
            "states": db_session.execute(select(func.count()).select_from(State)).scalar(),
        }

        assert counts_before == counts_after

        rs_after = db_session.execute(
            select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        ).scalar_one()
        assert rs_after.district_id == dist_id_before
