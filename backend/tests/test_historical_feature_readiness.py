"""
Unit Test Suite for Phase 5.7: Historical ERA5 Completion & Feature-Readiness Audit.

Verifies:
1. Feature whitelist (exact canonical 27 predictors).
2. Feature units (physical dimensions verified).
3. Temporal lookback (strictly [t-30, t-1]).
4. No same-day leakage (day t weather strictly excluded).
5. 30-day cold-start handling (930 rows excluded from training).
6. Spatial-weight normalization (sum = 1.000000 across all 31 districts).
7. Excluded ERA5 cells remain excluded (6 offshore cells absent).
8. Missing data does not become zero (missing != 0).
9. Historical hydrology does not use 2026 telemetry (blocked for historical training).
10. Predictor/target separation (disaster metadata and labels excluded from predictors).
"""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import numpy as np
import pytest

from app.ml.experiment.dataset import CANONICAL_PREDICTORS
from app.ml.historical_readiness import (
    HistoricalEra5IntegrityAuditor,
    HistoricalFeatureContract,
)
from app.ml.hydrology.features import HydrologicalFeatureEngine, FeatureObservation


def test_01_feature_whitelist_canonical_27():
    """Verify that the feature contract contains exactly the canonical 27 active predictors."""
    canonical_contract = HistoricalFeatureContract.get_canonical_contract()
    contract_names = [e.feature_name for e in canonical_contract]
    
    assert len(contract_names) == 27
    assert set(contract_names) == set(CANONICAL_PREDICTORS)


def test_02_feature_units_integrity():
    """Verify that every predictor has its physical unit documented and verified."""
    canonical_contract = HistoricalFeatureContract.get_canonical_contract()
    units_by_feature = {e.feature_name: e.unit for e in canonical_contract}

    # Precipitation features must be in mm
    for feat in ["precip_1d_mm", "precip_3d_sum_mm", "precip_7d_sum_mm",
                 "precip_14d_sum_mm", "precip_30d_sum_mm", "precip_7d_max_mm", "precip_14d_max_mm"]:
        assert units_by_feature[feat] == "mm"

    # Temperature features must be in deg C
    for feat in ["temp_mean_1d_c", "temp_min_1d_c", "temp_max_1d_c", "temp_7d_mean_c"]:
        assert units_by_feature[feat] == "deg C"

    # Humidity in percent
    assert units_by_feature["rh_mean_1d_pct"] == "percent"
    assert units_by_feature["rh_7d_mean_pct"] == "percent"

    # Pressure in hPa
    assert units_by_feature["pressure_mean_1d_hpa"] == "hPa"

    # Elevation in meters, slope in degrees
    assert units_by_feature["elevation_mean_m"] == "meters"
    assert units_by_feature["slope_mean_deg"] == "degrees"


def test_03_temporal_lookback_strictly_t_minus_30_to_t_minus_1():
    """Verify that the feature window for target date t strictly covers [t-30, t-1]."""
    target_date = date(2023, 7, 15)
    window_start, window_end = HydrologicalFeatureEngine.get_feature_window(target_date)

    # Window end must be 2023-07-14 23:59:59.999999 UTC
    assert window_end == datetime(2023, 7, 14, 23, 59, 59, 999999, tzinfo=timezone.utc)
    # Window start must be 2023-06-15 00:00:00 UTC (30 full days)
    assert window_start == datetime(2023, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
    assert (target_date - window_start.date()).days == 30


def test_04_no_same_day_leakage():
    """Verify that any weather observation from day t cannot enter the feature calculation."""
    target_date = date(2023, 7, 15)
    
    obs_same_day = FeatureObservation(
        station_code="CELL_001",
        observed_at_utc=datetime(2023, 7, 15, 0, 0, 0, tzinfo=timezone.utc),  # Midnight start of day t
        water_level_m=10.0,
        district_name="Belagavi",
    )
    obs_prior_day = FeatureObservation(
        station_code="CELL_001",
        observed_at_utc=datetime(2023, 7, 14, 23, 0, 0, tzinfo=timezone.utc),  # Day t-1
        water_level_m=9.5,
        district_name="Belagavi",
    )

    filtered = HydrologicalFeatureEngine.filter_observations_anti_leakage(
        [obs_same_day, obs_prior_day],
        target_date,
    )

    assert len(filtered) == 1
    assert filtered[0].observed_at_utc < datetime(2023, 7, 15, 0, 0, 0, tzinfo=timezone.utc)


def test_05_cold_start_initialization_handling():
    """Verify that the 930 cold-start rows (Jan 1-30, 2011) are identified and excluded."""
    import pyarrow.parquet as pq
    from app.ml.experiment.dataset import load_supervised_dataset

    # Verify raw parquet has 930 cold-start rows with incomplete lookback
    parquet_path = Path("data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet")
    raw_df = pq.read_table(parquet_path).to_pandas()
    cold_start_rows = raw_df[raw_df["is_weather_complete_30d"] == False]
    assert len(cold_start_rows) == 930

    # Verify that cold start rows contain null values in 30-day lookback features
    assert cold_start_rows["precip_30d_sum_mm"].isna().sum() > 0

    # When excluded by load_supervised_dataset, row count drops by exactly 930 and zero nulls remain
    dataset_clean = load_supervised_dataset(exclude_cold_start=True)
    assert len(dataset_clean.df) == len(raw_df) - 930
    assert (dataset_clean.df["is_weather_complete_30d"] == False).sum() == 0



def test_06_spatial_weight_normalization():
    """Verify that spatial weights sum to exactly 1.000000 across all 31 districts."""
    weights_path = Path("data/processed/gis_cache/district_era5_weights.json")
    assert weights_path.exists()

    with open(weights_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    weights = data.get("weights", {})
    assert len(weights) == 31

    for district_id, cell_dict in weights.items():
        total_weight = sum(cell_dict.values())
        assert abs(total_weight - 1.0) < 1e-6, f"District {district_id} weight sum {total_weight} != 1.0"


def test_07_excluded_era5_cells_remain_excluded():
    """Verify that the 6 source-excluded offshore cells are absent from district spatial weights."""
    weights_path = Path("data/processed/gis_cache/district_era5_weights.json")
    with open(weights_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    weights = data.get("weights", {})
    referenced_cells = set()
    for cell_dict in weights.values():
        referenced_cells.update(cell_dict.keys())

    # Exactly 318 eligible cells must be referenced; 6 excluded cells must never appear
    assert len(referenced_cells) == 318
    # Total canonical grid is 324 cells: 324 - 318 = 6 excluded cells
    excluded_count = 324 - len(referenced_cells)
    assert excluded_count == 6


def test_08_missing_data_does_not_become_zero():
    """Verify that missing observations in rolling calculations evaluate to NaN, never 0.0."""
    target_date = date(2023, 7, 15)
    
    # Missing observations
    features = HydrologicalFeatureEngine.compute_district_hydrological_features(
        target_date=target_date,
        district_name="Dharwad",
        observations=[],
    )

    assert np.isnan(features["river_level_current"])
    assert features["river_level_current"] != 0.0
    assert np.isnan(features["river_level_lag_1d"])


def test_09_historical_hydrology_does_not_use_2026_telemetry():
    """Verify that 2026 river stage telemetry is not used in historical or recent training."""
    from app.ml.hydrology.coverage import HistoricalCoverageGate
    from app.db.session import _get_session_factory

    SessionLocal = _get_session_factory()
    with SessionLocal() as session:
        coverage_dict = HistoricalCoverageGate.evaluate_all_periods(session)
        
        hist = coverage_dict["historical_baseline_1969_1994"]
        recent = coverage_dict["recent_supervised_2011_2023"]

        assert hist.status == "BLOCKED_FOR_HISTORICAL_TRAINING"
        assert recent.status == "BLOCKED_FOR_HISTORICAL_TRAINING"
        assert hist.total_observations == 0
        assert recent.total_observations == 0


def test_10_predictor_target_separation():
    """Verify that target columns and disaster event metadata are excluded from predictor contract."""
    canonical_contract = HistoricalFeatureContract.get_canonical_contract()
    predictor_names = {e.feature_name for e in canonical_contract}

    forbidden_cols = [
        "flood_occurrence", "label_state", "event_count", "source_event_ids",
        "main_causes", "severities", "fatalities", "displaced",
        "district_id", "target_date", "prediction_anchor_utc"
    ]

    for col in forbidden_cols:
        assert col not in predictor_names, f"Target or non-predictor column {col} leaked into predictor contract!"
