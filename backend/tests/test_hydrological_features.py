"""
Unit Test Suite for Phase 5.6: Hydrological Feature Integration & Multi-Scale Audit.

Verifies:
1. No future hydrological observation leakage.
2. No missing -> zero conversion.
3. Correct timezone handling.
4. Correct district/station spatial association.
5. M:N basin relationships preserved.
6. Crosswalk reproducibility.
7. Feature timestamp alignment.
8. Staleness detection.
9. Historical coverage calculation.
10. No synthetic hydrological values.
"""

from datetime import date, datetime, timedelta, timezone
import math

import numpy as np
import pytest
from sqlalchemy import text

from app.db.session import _get_session_factory
from app.ingestion.validation import IST_TZ
from app.ml.hydrology.audit import HydrologicalDataAuditor
from app.ml.hydrology.coverage import HistoricalCoverageGate
from app.ml.hydrology.crosswalk import HydrologicalCrosswalk
from app.ml.hydrology.features import (
    ABLATION_GROUPS,
    CANONICAL_27_PREDICTORS,
    CANDIDATE_HYDROLOGICAL_FEATURES,
    FeatureObservation,
    HydrologicalFeatureEngine,
)


@pytest.fixture(scope="module")
def db_session():
    """Provide a database session for tests."""
    SessionLocal = _get_session_factory()
    with SessionLocal() as session:
        yield session


def test_01_no_future_hydrological_observation_leakage():
    """Verify that observations on or after prediction issue time (00:00 UTC date t) are strictly excluded."""
    target_date = date(2023, 7, 15)
    
    # Target midnight is 2023-07-15 00:00:00 UTC
    obs_valid_past = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=datetime(2023, 7, 14, 23, 59, 0, tzinfo=timezone.utc),
        water_level_m=102.5,
        district_name="Mandya",
    )
    obs_future_same_day = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=datetime(2023, 7, 15, 0, 0, 1, tzinfo=timezone.utc),  # 1 second into date t!
        water_level_m=105.0,
        district_name="Mandya",
    )
    obs_future_noon = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=datetime(2023, 7, 15, 12, 0, 0, tzinfo=timezone.utc),
        water_level_m=106.0,
        district_name="Mandya",
    )
    obs_future_next_day = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=datetime(2023, 7, 16, 10, 0, 0, tzinfo=timezone.utc),
        water_level_m=108.0,
        district_name="Mandya",
    )

    filtered = HydrologicalFeatureEngine.filter_observations_anti_leakage(
        [obs_valid_past, obs_future_same_day, obs_future_noon, obs_future_next_day],
        target_date,
    )

    assert len(filtered) == 1
    assert filtered[0].water_level_m == 102.5
    assert filtered[0].observed_at_utc < datetime(2023, 7, 15, 0, 0, 0, tzinfo=timezone.utc)


def test_02_no_missing_to_zero_conversion():
    """Verify that absent hydrological observations produce NaN/None and are NEVER converted to 0.0."""
    target_date = date(2023, 7, 15)
    
    # Completely empty observation list
    features = HydrologicalFeatureEngine.compute_district_hydrological_features(
        target_date=target_date,
        district_name="Belagavi",
        observations=[],
    )

    # Level features must strictly be NaN, not 0.0
    for feat in ["river_level_current", "river_level_lag_1d", "river_level_lag_3d",
                 "river_level_change_1d", "river_level_rolling_max_3d", "river_level_rolling_max_7d"]:
        assert feat in features
        val = features[feat]
        assert np.isnan(val), f"{feat} must be NaN when missing, got {val}"
        assert val != 0.0, f"{feat} was converted to zero!"

    # Upstream station count is 0.0
    assert features["upstream_station_count"] == 0.0


def test_03_correct_timezone_handling():
    """Verify that IST timestamps from NWIC/CWC are converted to UTC and evaluated against anti-leakage bounds."""
    target_date = date(2026, 6, 1)  # Target 2026-06-01 00:00:00 UTC
    
    # Case A: 01-06-2026 05:00 IST = 31-05-2026 23:30 UTC -> In lookback window [t-30, t-1]!
    ist_time_past = datetime(2026, 6, 1, 5, 0, tzinfo=IST_TZ)
    utc_time_past = ist_time_past.astimezone(timezone.utc)
    assert utc_time_past == datetime(2026, 5, 31, 23, 30, tzinfo=timezone.utc)

    # Case B: 01-06-2026 06:00 IST = 01-06-2026 00:30 UTC -> Future leakage relative to 00:00 UTC!
    ist_time_future = datetime(2026, 6, 1, 6, 0, tzinfo=IST_TZ)
    utc_time_future = ist_time_future.astimezone(timezone.utc)
    assert utc_time_future == datetime(2026, 6, 1, 0, 30, tzinfo=timezone.utc)

    obs_past = FeatureObservation(
        station_code="STN_IST",
        observed_at_utc=utc_time_past,
        water_level_m=747.5,
        district_name="Mandya",
    )
    obs_future = FeatureObservation(
        station_code="STN_IST",
        observed_at_utc=utc_time_future,
        water_level_m=749.0,
        district_name="Mandya",
    )

    filtered = HydrologicalFeatureEngine.filter_observations_anti_leakage(
        [obs_past, obs_future],
        target_date,
    )

    assert len(filtered) == 1
    assert filtered[0].water_level_m == 747.5


def test_04_correct_district_station_spatial_association(db_session):
    """Verify that river stations in the database are spatially mapped to their correct district."""
    crosswalk = HydrologicalCrosswalk(db_session)
    gauge_links = crosswalk.get_gauge_links()

    assert len(gauge_links) >= 1
    akkihebbal = next((g for g in gauge_links if g.station_code == "AKKIHEBBAL"), None)
    assert akkihebbal is not None
    assert akkihebbal.district_name == "Mandya"
    assert akkihebbal.basin_name == "Cauvery"
    assert akkihebbal.sub_basin_name.startswith("HYBAS_")
    assert akkihebbal.upstream_area_km2 > 0.0


def test_05_mn_basin_relationships_preserved(db_session):
    """Verify that M:N relationships between districts and CWC basins / HydroBASINS are preserved."""
    crosswalk = HydrologicalCrosswalk(db_session)
    district_basin_links = crosswalk.get_district_basin_links()
    district_sub_basin_links = crosswalk.get_district_sub_basin_links()

    # 54 district-basin intersections across 31 districts
    assert len(district_basin_links) == 54
    # 264 district-subbasin intersections
    assert len(district_sub_basin_links) == 264

    # Multi-basin check: verify at least one district intersects > 1 basin
    from collections import Counter
    basin_counts = Counter(l.district_name for l in district_basin_links)
    assert basin_counts["Hassan"] == 3
    assert basin_counts["Chikkamagaluru"] == 3
    assert basin_counts["Bangalore Rural"] == 3
    assert basin_counts["Belagavi"] == 2
    assert basin_counts["Mandya"] == 1


def test_06_crosswalk_reproducibility(db_session):
    """Verify that the crosswalk integrity audit succeeds and covers all 31 districts."""
    crosswalk = HydrologicalCrosswalk(db_session)
    audit = crosswalk.verify_crosswalk_integrity()

    assert audit["is_valid"] is True
    assert audit["total_districts_covered"] == 31
    assert audit["total_district_basin_links"] == 54
    assert audit["total_district_sub_basin_links"] == 264
    assert audit["multi_basin_districts_count"] == 16


def test_07_feature_timestamp_alignment():
    """Verify that lag and rolling window features correctly align with historical days."""
    target_date = date(2026, 6, 5)
    midnight = datetime(2026, 6, 5, 0, 0, 0, tzinfo=timezone.utc)
    
    obs_t_minus_1 = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=midnight - timedelta(hours=6),  # 2026-06-04 18:00 UTC (day t-1)
        water_level_m=748.0,
        district_name="Mandya",
    )
    obs_t_minus_2 = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=midnight - timedelta(hours=30),  # 2026-06-03 18:00 UTC (day t-2)
        water_level_m=746.0,
        district_name="Mandya",
    )
    obs_t_minus_3 = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=midnight - timedelta(hours=54),  # 2026-06-02 18:00 UTC (day t-3)
        water_level_m=745.0,
        district_name="Mandya",
    )
    obs_t_minus_4 = FeatureObservation(
        station_code="STN_1",
        observed_at_utc=midnight - timedelta(hours=78),  # 2026-06-01 18:00 UTC (day t-4)
        water_level_m=744.0,
        district_name="Mandya",
    )

    features = HydrologicalFeatureEngine.compute_district_hydrological_features(
        target_date=target_date,
        district_name="Mandya",
        observations=[obs_t_minus_1, obs_t_minus_2, obs_t_minus_3, obs_t_minus_4],
    )

    assert features["river_level_current"] == 748.0
    assert features["river_level_lag_1d"] == 748.0
    assert features["river_level_lag_3d"] == 745.0
    # Change 1d: level(t-1) - level(t-2) = 748 - 746 = 2.0
    assert features["river_level_change_1d"] == 2.0
    # Change 3d: level(t-1) - level(t-4) = 748 - 744 = 4.0
    assert features["river_level_change_3d"] == 4.0
    # Rolling max 3d: max in [t-3, t-1] = max(748, 746, 745) = 748.0
    assert features["river_level_rolling_max_3d"] == 748.0


def test_08_staleness_detection():
    """Verify that observations older than 72 hours are flagged as stale."""
    target_date = date(2026, 6, 10)
    midnight = datetime(2026, 6, 10, 0, 0, 0, tzinfo=timezone.utc)
    
    # 5 days stale observation
    obs_old = FeatureObservation(
        station_code="STN_OLD",
        observed_at_utc=midnight - timedelta(days=5),
        water_level_m=740.0,
        district_name="Mandya",
    )

    age_hours = (midnight - obs_old.observed_at_utc).total_seconds() / 3600.0
    assert age_hours == 120.0
    assert age_hours > HydrologicalFeatureEngine.STALENESS_HOURS


def test_09_historical_coverage_calculation(db_session):
    """Verify that historical and recent supervised periods are marked BLOCKED_FOR_HISTORICAL_TRAINING."""
    coverage_dict = HistoricalCoverageGate.evaluate_all_periods(db_session)

    hist = coverage_dict["historical_baseline_1969_1994"]
    assert hist.status == "BLOCKED_FOR_HISTORICAL_TRAINING"
    assert hist.total_observations == 0
    assert hist.temporal_coverage_pct == 0.0

    recent = coverage_dict["recent_supervised_2011_2023"]
    assert recent.status == "BLOCKED_FOR_HISTORICAL_TRAINING"
    assert recent.total_observations == 0
    assert recent.temporal_coverage_pct == 0.0

    inference = coverage_dict["forward_inference_2023_2025"]
    assert inference.status == "BLOCKED_FOR_HISTORICAL_TRAINING"
    assert inference.total_observations == 0


def test_10_no_synthetic_hydrological_values(db_session):
    """Verify that warning and danger thresholds are not fabricated when missing in source records."""
    q = text("SELECT warning_level, danger_level, highest_flood_level FROM river_stations WHERE station_code = 'AKKIHEBBAL';")
    row = db_session.execute(q).fetchone()
    
    # In CWC database, AKKIHEBBAL has None for warning/danger/hfl. They must remain None.
    assert row.warning_level is None
    assert row.danger_level is None
    assert row.highest_flood_level is None
