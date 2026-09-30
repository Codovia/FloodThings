"""
Tests for Phase 5.3 Recent District-Day Supervised ML Matrix (2011–2023) & Spatial Mapping.
"""

import json
import math
from pathlib import Path
import pytest
import pyarrow.parquet as pq

from app.gis.recent_mapping_audit import audit_gis_and_mapping
from app.ingestion.historical.recent_audit import RecentDatasetAuditor
from app.ml.district_feature_matrix import TemporalLeakageAuditor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPERVISED_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "ml_matrix" / "recent" / "district_day_matrix_2011_2023.parquet"
SUPERVISED_AUDIT_PATH = PROJECT_ROOT / "data" / "processed" / "ml_matrix" / "recent" / "district_day_matrix_2011_2023_audit.json"
WEATHER_ONLY_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "ml_matrix" / "recent" / "district_day_weather_matrix.parquet"
HISTORICAL_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "ml_matrix" / "district_day_feature_matrix.parquet"


def test_01_mapping_audit_all_318_cells():
    audit = audit_gis_and_mapping()
    gm = audit["grid_mapping"]
    assert gm["total_eligible_cells"] == 318
    assert gm["mapped_cells_count"] == 318
    assert gm["unmapped_cells_count"] == 0
    assert gm["ambiguous_unassigned_cells_count"] == 0
    assert gm["districts_covered_count"] == 31
    assert gm["all_weight_sums_equal_one"] is True
    assert gm["single_district_cells_count"] == 127
    assert gm["multi_district_boundary_cells_count"] == 191


def test_02_district_geometry_validity():
    audit = audit_gis_and_mapping()
    assert audit["district_shapefile"]["all_valid"] is True
    assert audit["district_shapefile"]["row_count"] == 31
    assert audit["database_districts"]["all_valid"] is True
    assert audit["database_districts"]["count"] == 31


def test_03_supervised_matrix_structure_2011_2023():
    assert SUPERVISED_PARQUET_PATH.exists(), f"Missing supervised matrix at {SUPERVISED_PARQUET_PATH}"
    table = pq.read_table(SUPERVISED_PARQUET_PATH)
    df = table.to_pandas()

    # 4,588 calendar days (2011-01-01 to 2023-07-24) * 31 districts = 142,228 rows
    assert len(df) == 142228
    assert df["district_id"].nunique() == 31
    assert df["target_date"].min() == "2011-01-01"
    assert df["target_date"].max() == "2023-07-24"
    assert df["target_date"].nunique() == 4588

    # Grain: exactly 1 row per district x calendar date
    duplicates = df.duplicated(subset=["district_id", "target_date"]).sum()
    assert duplicates == 0

    # Exact schema parity with historical baseline matrix (57 columns)
    assert HISTORICAL_PARQUET_PATH.exists()
    hist_table = pq.read_table(HISTORICAL_PARQUET_PATH)
    assert table.column_names == hist_table.column_names
    assert table.schema == hist_table.schema


def test_04_supervised_matrix_temporal_anti_leakage():
    table = pq.read_table(SUPERVISED_PARQUET_PATH)
    df = table.to_pandas()

    # Lead time is strictly 1 day (L = 1)
    assert (df["lead_time_days"] == 1).all()

    # Feature window end is strictly target_date - 1 day
    target_dts = df["target_date"].astype("datetime64[ns]")
    fw_end_dts = df["feature_window_end"].astype("datetime64[ns]")
    diffs = (target_dts - fw_end_dts).dt.days
    assert (diffs == 1).all()

    # Feature window start is strictly feature_window_end - 29 days (30 days total)
    fw_start_dts = df["feature_window_start"].astype("datetime64[ns]")
    window_lengths = (fw_end_dts - fw_start_dts).dt.days + 1
    assert (window_lengths == 30).all()

    # Boundary missingness: exactly 930 rows have incomplete 30d weather (Jan 1-30, 2011)
    incomplete_30d = (~df["is_weather_complete_30d"]).sum()
    assert incomplete_30d == 930
    assert df[~df["is_weather_complete_30d"]]["target_date"].max() == "2011-01-30"


def test_05_three_state_labels_with_verified_ifi():
    table = pq.read_table(SUPERVISED_PARQUET_PATH)
    df = table.to_pandas()

    # Three-state label distribution
    flood_count = (df["label_state"] == "FLOOD").sum()
    no_flood_count = (df["label_state"] == "NO_FLOOD").sum()
    unknown_count = (df["label_state"] == "UNKNOWN").sum()

    assert flood_count == 13156
    assert no_flood_count == 0  # Zero synthetic NO_FLOOD labels
    assert unknown_count == 129072
    assert flood_count + unknown_count == len(df)

    # FLOOD rows must have flood_occurrence == 1
    assert (df[df["label_state"] == "FLOOD"]["flood_occurrence"] == 1).all()

    # UNKNOWN rows must have flood_occurrence as NaN / null
    assert df[df["label_state"] == "UNKNOWN"]["flood_occurrence"].isna().all()


def test_06_data_quality_and_physical_bounds():
    table = pq.read_table(SUPERVISED_PARQUET_PATH)
    df = table.to_pandas()

    # Precipitation non-negative
    precip_valid = df["precip_1d_mm"].dropna()
    assert (precip_valid >= 0.0).all()

    # Relative humidity within [0, 100]%
    rh_valid = df["rh_mean_1d_pct"].dropna()
    assert (rh_valid >= 0.0).all() and (rh_valid <= 100.0).all()

    # Surface pressure within [800, 1100] hPa
    press_valid = df["pressure_mean_1d_hpa"].dropna()
    assert (press_valid >= 800.0).all() and (press_valid <= 1100.0).all()

    # Temperature within [-20, 60] °C
    temp_valid = df["temp_mean_1d_c"].dropna()
    assert (temp_valid >= -20.0).all() and (temp_valid <= 60.0).all()

    # Static GIS features 100% complete across all 31 districts
    assert df["elevation_mean_m"].isna().sum() == 0
    assert df["major_basin_count"].isna().sum() == 0
    assert df["terrain_coverage_pct"].isna().sum() == 0


def test_07_historical_baseline_untouched():
    auditor = RecentDatasetAuditor()
    intact, details = auditor.verify_historical_baseline()
    assert intact is True
    assert details["historical_raw_succeeded"] == 858
    assert details["historical_proc_succeeded"] == 858
    assert details["historical_matrix_size_bytes"] == 13327375


def test_08_post_2023_weather_inference_matrix_structure():
    assert WEATHER_ONLY_PARQUET_PATH.exists()
    table = pq.read_table(WEATHER_ONLY_PARQUET_PATH)
    df = table.to_pandas()
    # 5,479 calendar days * 31 districts = 169,849
    assert len(df) == 169849
    assert df["district_id"].nunique() == 31
    assert df["target_date"].min() == "2011-01-01"
    assert df["target_date"].max() == "2025-12-31"
    # Zero synthetic NO_FLOOD labels
    assert (df["flood_occurrence"] == 0).sum() == 0
    assert df["flood_occurrence"].isna().all()
    assert (df["label_state"] == "UNKNOWN").all()


def test_09_spatial_weights_normalization_exact():
    """Verify that all 31 districts have geometric intersection weights summing exactly to 1.0."""
    weights_path = PROJECT_ROOT / "data" / "processed" / "gis_cache" / "district_era5_weights.json"
    assert weights_path.exists()
    with open(weights_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    weights = data.get("weights", {})
    assert len(weights) == 31
    for d_id, cell_weights in weights.items():
        w_sum = sum(float(w) for w in cell_weights.values())
        assert abs(w_sum - 1.0) < 1e-5, f"District {d_id} weight sum {w_sum} deviates from 1.0"


def test_10_canonical_predictor_whitelist_and_target_separation():
    """Verify strict separation between 27 safe predictors and prohibited target/event metadata."""
    from app.ml.baseline_modeling import CANONICAL_PREDICTOR_COLUMNS, PROHIBITED_LEAKAGE_COLUMNS

    assert len(CANONICAL_PREDICTOR_COLUMNS) == 27
    pred_set = set(CANONICAL_PREDICTOR_COLUMNS)
    proh_set = set(PROHIBITED_LEAKAGE_COLUMNS)

    overlap = pred_set.intersection(proh_set)
    assert len(overlap) == 0, f"Found prohibited columns in predictor list: {overlap}"

    # Target and event metadata must be strictly prohibited
    assert "flood_occurrence" in proh_set
    assert "label_state" in proh_set
    assert "event_count" in proh_set
    assert "source_event_ids" in proh_set
    assert "main_causes" in proh_set
    assert "severities" in proh_set
    assert "fatalities" in proh_set
    assert "displaced" in proh_set


def test_11_unknown_is_not_zero():
    """Verify three-state contract: UNKNOWN is strictly NULL and never converted to NO_FLOOD = 0."""
    table = pq.read_table(SUPERVISED_PARQUET_PATH)
    df = table.to_pandas()

    unknown_mask = df["label_state"] == "UNKNOWN"
    assert unknown_mask.sum() == 129072
    assert df.loc[unknown_mask, "flood_occurrence"].isna().all()
    assert (df["label_state"] == "NO_FLOOD").sum() == 0
    assert (df["flood_occurrence"] == 0).sum() == 0


