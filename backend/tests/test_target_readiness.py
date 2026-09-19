"""
Target Readiness Invariant Tests (Phase 2.8).

Pure audit tests verifying the readiness findings documented in docs/ML_TARGET_READINESS.md:
1. IFI historical flood evidence invariants (zero geometry, zero depth, zero confidence).
2. CWC telemetry metadata check (missing danger levels).
3. Database temporal disjointness check (zero overlap between current DB weather and flood obs).
4. District PostGIS geometry check (unpopulated prior to Phase 3).
5. Vijayanagara zero-evidence invariant.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import func

from app.db.models.flood import FloodEvent, FloodObservation
from app.db.models.geography import District
from app.db.models.weather import WeatherObservation
from app.db.session import _get_session_factory
from app.gis.ifi import IfiEventNormalizer
from app.gis.ifi_audit import IfiEvidenceAuditor
from app.gis.ksrsac import KsrsacAdminNormalizer


REAL_IFI_CSV = Path("data/raw/ifi/ifi_v3_karnataka_20260917_164914.csv")
SAMPLE_CWC_CSV = Path("data/raw/api_tests/nwic_cwc_river_level_cauvery_sample.csv")


class TestTargetReadinessInvariants:
    """Test suite verifying ML target readiness constraints and invariants."""

    @pytest.mark.skipif(not REAL_IFI_CSV.exists(), reason="Real IFI archive not present")
    def test_ifi_evidence_invariants(self) -> None:
        """Verify IFI evidence has zero geometry, zero depth, zero confidence, and 1271 observations."""
        districts = KsrsacAdminNormalizer().normalize().districts
        normalizer = IfiEventNormalizer(districts)
        norm_result = normalizer.normalize(REAL_IFI_CSV)

        assert len(norm_result.events) == 493
        assert len(norm_result.observations) == 1271

        # Invariant: No synthetic geometry, depth, or confidence
        assert all(obs.geometry is None for obs in norm_result.observations)
        assert all(obs.flood_depth is None for obs in norm_result.observations)
        assert all(obs.confidence is None for obs in norm_result.observations)
        assert all(ev.geometry is None for ev in norm_result.events)
        assert all(ev.confidence is None for ev in norm_result.events)

        # Invariant: All observations have valid KGIS district codes (01 to 30, none for 31)
        kgis_codes = {obs.kgis_district_code for obs in norm_result.observations}
        assert "31" not in kgis_codes
        assert len(kgis_codes) == 30

    @pytest.mark.skipif(not SAMPLE_CWC_CSV.exists(), reason="Sample CWC CSV not present")
    def test_cwc_telemetry_lacks_danger_levels(self) -> None:
        """Verify CWC river telemetry CSV omits official Danger Level and Warning Level columns."""
        with open(SAMPLE_CWC_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn.lower().strip() for fn in (reader.fieldnames or [])]

        # Official DL / WL columns must be absent, proving Candidate D requires external metadata
        assert "danger_level" not in fieldnames
        assert "warning_level" not in fieldnames
        assert "danger level" not in fieldnames
        assert "warning level" not in fieldnames

    def test_database_temporal_disjointness(self) -> None:
        """Verify current database has zero temporal overlap between weather and flood observations."""
        session_factory = _get_session_factory()
        db = session_factory()
        try:
            weather_min, weather_max = db.query(
                func.min(WeatherObservation.observed_at),
                func.max(WeatherObservation.observed_at),
            ).one()

            flood_min, flood_max = db.query(
                func.min(FloodObservation.observation_time),
                func.max(FloodObservation.observation_time),
            ).one()

            if weather_min and flood_max:
                # Weather observations are 2024+, flood observations in DB are 1969-1994
                assert weather_min > flood_max, "Expected zero temporal overlap in current DB"
        finally:
            db.close()

    def test_database_district_geometry_populated_in_phase_3(self) -> None:
        """Verify district geometries in PostgreSQL are populated in Phase 3 GIS ingestion."""
        session_factory = _get_session_factory()
        db = session_factory()
        try:
            dists = db.query(District).all()
            assert len(dists) == 31
            # In Phase 3.2, PostGIS polygons are ingested from KSR-SAC
            assert all(d.geometry is not None for d in dists)
        finally:
            db.close()

    @pytest.mark.skipif(not REAL_IFI_CSV.exists(), reason="Real IFI archive not present")
    def test_vijayanagara_zero_evidence_invariant(self) -> None:
        """Verify Vijayanagara (KGIS 31, LGD 738) has exactly zero observations in audited IFI data."""
        districts = KsrsacAdminNormalizer().normalize().districts
        auditor = IfiEvidenceAuditor(districts)
        report = auditor.audit_source(REAL_IFI_CSV)

        vj_rec = next(r for r in report.district_coverage if r.kgis_district_code == "31")
        assert vj_rec.district_name == "Vijayanagara"
        assert vj_rec.unique_events == 0
        assert vj_rec.district_observations == 0
        assert vj_rec.has_evidence is False
        assert vj_rec.first_event_date is None
        assert vj_rec.last_event_date is None
