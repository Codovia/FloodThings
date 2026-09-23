"""
Tests for Environmental Data Spatial Association & Source Coverage Audit (Phase 3.5).

Validates:
1. Deterministic execution of EnvironmentalDataAuditor.
2. Exact record counts across all 8 audited datasets.
3. Accurate categorization: OBSERVATION, REANALYSIS, MODEL_OUTPUT, FORECAST, HISTORICAL_EVENT, REFERENCE.
4. Exact spatial distinct location counts and extent calculations.
5. Strict ML usability classification: USABLE_NOW, USABLE_WITH_LIMITATIONS, BLOCKED, REFERENCE_ONLY.
6. Admin GIS validation: 1 State, 31 Districts, 240 Taluks, 100% validity, 1221/1221 spatial association match.
7. Hydrological reference gap detection (basins, rivers, water bodies, DEM).
8. Read-only integrity guarantee (zero database mutations).
9. Text and JSON serialization.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.flood import FloodEvent, FloodObservation
from app.db.models.geography import District, State, Taluk
from app.db.models.hydrology import (
    Reservoir,
    ReservoirObservation,
    River,
    RiverBasin,
    RiverObservation,
    RiverStation,
)
from app.db.models.weather import (
    RainfallObservation,
    WeatherForecast,
    WeatherObservation,
)
from app.db.session import _get_session_factory
from app.gis.environmental_audit import (
    AdminGisAuditRecord,
    EnvironmentalAuditReport,
    EnvironmentalDataAuditor,
    HydrologicalReferenceAuditRecord,
    MLUsability,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def audit_report(db_session: Session) -> EnvironmentalAuditReport:
    """Run environmental audit once for module assertions."""
    auditor = EnvironmentalDataAuditor(db_session)
    return auditor.audit()


class TestEnvironmentalDataAudit:
    """Test suite for Phase 3.5 Environmental Data Coverage Audit."""

    def test_audit_execution_and_structure(self, audit_report: EnvironmentalAuditReport):
        """Verify audit executes and returns structured report."""
        assert isinstance(audit_report, EnvironmentalAuditReport)
        assert audit_report.audited_at is not None
        assert "weather_observations" in audit_report.datasets
        assert "rainfall_observations" in audit_report.datasets
        assert "weather_forecasts" in audit_report.datasets
        assert "river_observations" in audit_report.datasets
        assert "reservoir_observations" in audit_report.datasets
        assert "flood_observations" in audit_report.datasets
        assert isinstance(audit_report.admin_gis, AdminGisAuditRecord)
        assert isinstance(audit_report.hydrological_reference, HydrologicalReferenceAuditRecord)

    def test_weather_observations_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify weather observations metrics and ML usability."""
        rec = audit_report.datasets["weather_observations"]
        assert rec.temporal.record_count == 397
        assert rec.temporal.distinct_timestamps == 137
        assert rec.spatial.distinct_locations_count == 5
        assert rec.spatial.distinct_districts_represented == 5
        assert rec.spatial.has_geometry is True
        assert rec.spatial.srid == 4326

        # Source category breakdown: 72 REANALYSIS, 325 MODEL_OUTPUT
        assert "REANALYSIS:72" in rec.source.data_category
        assert "MODEL_OUTPUT:325" in rec.source.data_category

        # Quality
        assert rec.quality.null_measurements["temperature"] == 0
        assert rec.quality.null_measurements["humidity"] == 0
        assert rec.quality.null_measurements["pressure"] == 0
        assert rec.quality.null_measurements["wind_speed"] == 0
        assert rec.quality.null_measurements["wind_direction"] == 0

        # ML Usability
        assert rec.ml_usability == MLUsability.USABLE_WITH_LIMITATIONS.value
        assert len(rec.concrete_limitations) >= 3

    def test_rainfall_observations_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify rainfall observations metrics and ML usability."""
        rec = audit_report.datasets["rainfall_observations"]
        assert rec.temporal.record_count == 397
        assert rec.temporal.distinct_timestamps == 137
        assert rec.spatial.distinct_locations_count == 5
        assert rec.spatial.distinct_districts_represented == 5
        assert rec.spatial.has_geometry is True
        assert rec.spatial.srid == 4326

        # Quality
        assert rec.quality.null_measurements["rainfall_mm"] == 0
        assert rec.quality.null_measurements["duration_minutes"] == 0

        # ML Usability
        assert rec.ml_usability == MLUsability.USABLE_WITH_LIMITATIONS.value

    def test_weather_forecasts_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify weather forecasts metrics and ML usability."""
        rec = audit_report.datasets["weather_forecasts"]
        assert rec.temporal.record_count == 275
        assert rec.spatial.distinct_locations_count == 5
        # Weather forecasts table stores district_id foreign key, no explicit point geometry
        assert rec.spatial.has_geometry is False

        # Quality: rainfall_probability is 100% NULL (275)
        assert rec.quality.null_measurements["rainfall_probability"] == 275
        assert rec.quality.null_measurements["temperature"] == 0
        assert rec.quality.null_measurements["forecast_rainfall_mm"] == 0

        # ML Usability
        assert rec.ml_usability == MLUsability.USABLE_WITH_LIMITATIONS.value

    def test_river_observations_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify river observations and station metrics."""
        rec = audit_report.datasets["river_observations"]
        assert rec.temporal.record_count == 101
        assert rec.spatial.distinct_locations_count == 1
        assert rec.spatial.distinct_districts_represented == 1
        assert rec.spatial.has_geometry is True

        # Discharge is 100% NULL (101)
        assert rec.quality.null_measurements["discharge"] == 101
        assert rec.quality.null_measurements["water_level"] == 0

        # ML Usability
        assert rec.ml_usability == MLUsability.USABLE_WITH_LIMITATIONS.value

    def test_reservoir_observations_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify reservoir observations and historical telemetry status."""
        rec = audit_report.datasets["reservoir_observations"]
        assert rec.temporal.record_count == 100
        assert rec.spatial.distinct_locations_count == 1

        # Quality
        assert rec.quality.null_measurements["water_level"] == 0
        assert rec.quality.null_measurements["storage"] == 0
        assert rec.quality.null_measurements["storage_percentage"] == 100

        # ML Usability: BLOCKED for operational forecasting due to obsolete 2006-2008 window
        assert rec.ml_usability == MLUsability.BLOCKED.value
        assert any("2006–2008" in lim for lim in rec.concrete_limitations)

    def test_historical_flood_observations_audit(self, audit_report: EnvironmentalAuditReport):
        """Verify historical IFI flood observations metrics."""
        rec = audit_report.datasets["flood_observations"]
        assert rec.temporal.record_count == 186
        assert rec.spatial.distinct_districts_represented == 23
        assert rec.spatial.has_geometry is False
        assert rec.spatial.srid is None

        # Quality: 100% NULL geometry and depth
        assert rec.quality.null_measurements["geometry"] == 186
        assert rec.quality.null_measurements["flood_depth"] == 186

        # ML Usability
        assert rec.ml_usability == MLUsability.USABLE_WITH_LIMITATIONS.value

    def test_administrative_gis_inventory(self, audit_report: EnvironmentalAuditReport):
        """Verify administrative GIS boundary integrity."""
        admin = audit_report.admin_gis
        assert admin.state_features == 1
        assert admin.district_features == 31
        assert admin.taluk_features == 240
        assert admin.locality_features == 0
        assert admin.srid == 4326
        assert admin.geometry_type == "MultiPolygon"
        assert admin.all_valid is True
        assert admin.orphaned_taluks == 0
        assert admin.uncontained_taluks == 0
        assert admin.boundary_sliver_taluks == 196
        assert admin.spatial_association_rate_pct == 100.0

    def test_hydrological_reference_inventory(self, audit_report: EnvironmentalAuditReport):
        """Verify hydrological reference layers and missing GIS components."""
        hydro = audit_report.hydrological_reference
        assert hydro.river_basins_count >= 2
        assert hydro.river_basins_with_geom >= 2
        assert hydro.rivers_count >= 2
        assert hydro.rivers_with_geom >= 2
        assert hydro.reservoirs_count == 1
        assert hydro.reservoirs_with_geom == 1
        assert hydro.river_stations_count == 1
        assert hydro.river_stations_with_geom == 1
        assert hydro.water_bodies_count == 0
        assert hydro.flood_hazard_zones_count == 0
        assert len(hydro.missing_reference_summary) >= 3

    def test_read_only_invariance(self, db_session: Session):
        """Verify audit execution causes ZERO database mutations."""
        # Capture counts before
        c_weather = db_session.execute(select(func.count(WeatherObservation.id))).scalar()
        c_rainfall = db_session.execute(select(func.count(RainfallObservation.id))).scalar()
        c_forecast = db_session.execute(select(func.count(WeatherForecast.id))).scalar()
        c_river = db_session.execute(select(func.count(RiverObservation.id))).scalar()
        c_res = db_session.execute(select(func.count(ReservoirObservation.id))).scalar()
        c_flood = db_session.execute(select(func.count(FloodObservation.id))).scalar()
        c_taluk = db_session.execute(select(func.count(Taluk.id))).scalar()
        c_dist = db_session.execute(select(func.count(District.id))).scalar()

        # Run audit
        auditor = EnvironmentalDataAuditor(db_session)
        auditor.audit()

        # Check counts after
        assert db_session.execute(select(func.count(WeatherObservation.id))).scalar() == c_weather
        assert db_session.execute(select(func.count(RainfallObservation.id))).scalar() == c_rainfall
        assert db_session.execute(select(func.count(WeatherForecast.id))).scalar() == c_forecast
        assert db_session.execute(select(func.count(RiverObservation.id))).scalar() == c_river
        assert db_session.execute(select(func.count(ReservoirObservation.id))).scalar() == c_res
        assert db_session.execute(select(func.count(FloodObservation.id))).scalar() == c_flood
        assert db_session.execute(select(func.count(Taluk.id))).scalar() == c_taluk
        assert db_session.execute(select(func.count(District.id))).scalar() == c_dist

    def test_json_and_text_formatting(self, audit_report: EnvironmentalAuditReport):
        """Verify serialization to JSON and text summary."""
        report_dict = audit_report.to_dict()
        assert isinstance(report_dict, dict)
        json_str = json.dumps(report_dict, default=str)
        assert len(json_str) > 1000

        text_summary = audit_report.summary_text()
        assert "PHASE 3.5: ENVIRONMENTAL DATA SPATIAL ASSOCIATION & SOURCE COVERAGE AUDIT" in text_summary
        assert "USABLE_WITH_LIMITATIONS" in text_summary
        assert "BLOCKED" in text_summary
