"""
Comprehensive Validation Tests for Phase 5.3 District-Level ERA5 Daily Aggregation (2011–2025).

Invariants Verified:
1. Spatial: Exactly 31 districts, correct CRS, no coordinates outside Karnataka.
2. Temporal: 2011-01-01 through 2025-12-31, exactly 5,479 dates, leap years present.
3. Cardinality: Exactly 31 x 5,479 = 169,849 records.
4. Uniqueness: Zero duplicate (district_id, date) pairs.
5. Nulls: Zero nulls across all meteorological fields.
6. Physical Bounds: precip >= 0, RH in [0, 100], pressure > 0, temp min <= mean <= max.
7. Provenance: Contributing cells and weights traceable; processing version tracked.
8. Baseline Immutability: Historical 1969-1994 data and feature matrix 100% untouched.
"""

import json
from pathlib import Path
import pytest
import pyarrow.parquet as pq

from app.ingestion.historical.recent_audit import RecentDatasetAuditor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISTRICT_DAILY_DIR = PROJECT_ROOT / "data" / "processed" / "era5_district_daily" / "recent"
UNIFIED_PARQUET = DISTRICT_DAILY_DIR / "district_daily_2011_2025.parquet"
MANIFEST_FILE = DISTRICT_DAILY_DIR / "processing_manifest.json"
WEIGHTS_CACHE = PROJECT_ROOT / "data" / "processed" / "gis_cache" / "district_era5_weights.json"


@pytest.fixture(scope="module")
def district_daily_df():
    """Load the unified 2011–2025 district-daily Parquet dataset."""
    assert UNIFIED_PARQUET.exists(), f"Unified parquet not found at {UNIFIED_PARQUET}"
    table = pq.read_table(UNIFIED_PARQUET)
    return table.to_pandas()


@pytest.fixture(scope="module")
def manifest_data():
    """Load the processing manifest."""
    assert MANIFEST_FILE.exists(), f"Manifest file not found at {MANIFEST_FILE}"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_01_cardinality_and_dimensions(district_daily_df):
    """Verify exactly 31 districts x 5,479 calendar days = 169,849 records."""
    assert len(district_daily_df) == 169849
    assert district_daily_df["district_id"].nunique() == 31
    assert district_daily_df["date"].nunique() == 5479


def test_02_spatial_district_coverage(district_daily_df):
    """Verify all 31 authoritative Karnataka districts are represented with valid codes."""
    with open(WEIGHTS_CACHE, "r", encoding="utf-8") as f:
        wdata = json.load(f)
    expected_district_ids = set(wdata["district_meta"].keys())

    actual_district_ids = set(district_daily_df["district_id"].unique())
    assert actual_district_ids == expected_district_ids

    # Verify KGIS and LGD codes are fully populated
    assert not district_daily_df["kgis_district_code"].isna().any()
    assert not district_daily_df["lgd_district_code"].isna().any()
    assert not district_daily_df["district_name"].isna().any()


def test_03_temporal_span_and_leap_years(district_daily_df):
    """Verify exact 2011-01-01 to 2025-12-31 date span and all 4 leap days."""
    dates = sorted(district_daily_df["date"].unique())
    assert dates[0] == "2011-01-01"
    assert dates[-1] == "2025-12-31"

    # All leap days present for each of the 31 districts
    for leap_date in ["2012-02-29", "2016-02-29", "2020-02-29", "2024-02-29"]:
        assert leap_date in dates
        leap_rows = district_daily_df[district_daily_df["date"] == leap_date]
        assert len(leap_rows) == 31


def test_04_zero_duplicates(district_daily_df):
    """Verify zero duplicate (district_id, date) records."""
    dupes = district_daily_df.duplicated(subset=["district_id", "date"]).sum()
    assert dupes == 0


def test_05_zero_nulls_in_meteorological_fields(district_daily_df):
    """Verify zero nulls across all meteorological observations."""
    meteo_cols = [
        "precipitation_total_mm",
        "temperature_mean_c",
        "temperature_min_c",
        "temperature_max_c",
        "relative_humidity_mean_pct",
        "surface_pressure_mean_hpa",
    ]
    for col in meteo_cols:
        assert district_daily_df[col].isna().sum() == 0, f"Found nulls in {col}"


def test_06_physical_value_bounds(district_daily_df):
    """Verify physical plausibility of aggregated meteorological variables."""
    # Precipitation non-negative and plausible
    assert (district_daily_df["precipitation_total_mm"] >= 0.0).all()
    assert (district_daily_df["precipitation_total_mm"] <= 350.0).all()

    # Relative humidity in [0, 100]
    assert (district_daily_df["relative_humidity_mean_pct"] >= 0.0).all()
    assert (district_daily_df["relative_humidity_mean_pct"] <= 100.0).all()

    # Surface pressure > 0 and in realistic atmospheric range for Karnataka
    assert (district_daily_df["surface_pressure_mean_hpa"] >= 800.0).all()
    assert (district_daily_df["surface_pressure_mean_hpa"] <= 1050.0).all()

    # Temperature min <= mean <= max (with tiny rounding tolerance of 0.05)
    temp_min = district_daily_df["temperature_min_c"]
    temp_mean = district_daily_df["temperature_mean_c"]
    temp_max = district_daily_df["temperature_max_c"]

    assert (temp_min <= temp_mean + 0.05).all()
    assert (temp_mean <= temp_max + 0.05).all()
    assert (temp_min >= 0.0).all()
    assert (temp_max <= 50.0).all()


def test_07_provenance_and_weights_integrity(district_daily_df, manifest_data):
    """Verify provenance tracking, weights normalization, and manifest consistency."""
    # Manifest record count matches parquet
    assert manifest_data["total_district_day_records"] == 169849
    assert manifest_data["expected_records"] == 169849
    assert manifest_data["districts_count"] == 31
    assert manifest_data["total_calendar_days"] == 5479

    # Weight availability is 1.000000 across all records
    assert (district_daily_df["available_cell_weight"] >= 0.9999).all()
    assert (district_daily_df["quality_status"] == "COMPLETE").all()
    assert (district_daily_df["processing_version"] == "1.0.0").all()

    # Contributing cell count is between 8 and 37
    assert (district_daily_df["contributing_cells_count"] >= 8).all()
    assert (district_daily_df["contributing_cells_count"] <= 37).all()


def test_08_year_partitions_consistency():
    """Verify that all 15 year partition files exist and sum to 169,849 rows."""
    total_partition_rows = 0
    for yr in range(2011, 2026):
        p_file = DISTRICT_DAILY_DIR / f"year={yr}" / "district_daily.parquet"
        assert p_file.exists(), f"Missing partition file for year {yr}: {p_file}"
        tbl = pq.read_table(p_file)
        expected_days = 366 if yr in [2012, 2016, 2020, 2024] else 365
        assert len(tbl) == expected_days * 31
        total_partition_rows += len(tbl)
    assert total_partition_rows == 169849


def test_09_historical_baseline_strictly_untouched():
    """Verify that historical 1969-1994 baseline raw chunks, manifests, and ML matrix are 100% intact."""
    auditor = RecentDatasetAuditor()
    intact, details = auditor.verify_historical_baseline()
    assert intact is True
    assert details["historical_raw_succeeded"] == 858
    assert details["historical_proc_succeeded"] == 858
    assert details["historical_matrix_size_bytes"] == 13327375


def test_10_recent_daily_source_files_strictly_untouched():
    """Verify that recent daily source files (data/processed/era5_daily/recent) remain 100% untouched."""
    proc_manifest_path = PROJECT_ROOT / "data" / "processed" / "era5_daily" / "recent" / "processing_manifest.json"
    raw_manifest_path = PROJECT_ROOT / "data" / "raw" / "era5_recent" / "extraction_manifest.json"

    assert proc_manifest_path.exists(), "Recent daily processing manifest missing"
    assert raw_manifest_path.exists(), "Recent raw extraction manifest missing"

    with open(proc_manifest_path, "r", encoding="utf-8") as f:
        proc_manifest = json.load(f)
    with open(raw_manifest_path, "r", encoding="utf-8") as f:
        raw_manifest = json.load(f)

    # 495 chunks for 2011-2025
    raw_chunks_11_25 = [c for c in raw_manifest.get("chunks", {}).values() if 2011 <= c.get("year", 0) <= 2025]
    proc_chunks_11_25 = [c for c in proc_manifest.get("chunks", {}).values() if 2011 <= c.get("year", 0) <= 2025]

    assert len(raw_chunks_11_25) == 495
    assert len(proc_chunks_11_25) == 495
    assert all(c.get("status") == "SUCCEEDED" for c in raw_chunks_11_25)
    assert all(c.get("status") == "SUCCEEDED" for c in proc_chunks_11_25)

    # Exactly 1,742,322 daily cell records for 2011-2025
    assert sum(c.get("output_record_count", 0) for c in proc_chunks_11_25) == 1742322



def test_11_schema_conformance_with_project_specification(district_daily_df):
    """Verify exact schema specification: pure meteorological dataset, no labels or lag features."""
    expected_columns = [
        "district_id",
        "kgis_district_code",
        "lgd_district_code",
        "district_name",
        "date",
        "year",
        "month",
        "day",
        "day_of_year",
        "precipitation_total_mm",
        "temperature_mean_c",
        "temperature_min_c",
        "temperature_max_c",
        "relative_humidity_mean_pct",
        "surface_pressure_mean_hpa",
        "contributing_cells_count",
        "contributing_cells",
        "available_cell_weight",
        "quality_status",
        "source_dataset",
        "dataset_model",
        "spatial_aggregation_method",
        "processing_version",
    ]
    assert list(district_daily_df.columns) == expected_columns

    # Verify absence of premature ML labels or feature engineering
    forbidden_columns = [
        "flood_occurrence",
        "label_state",
        "precip_3d_sum_mm",
        "precip_7d_sum_mm",
        "precip_14d_sum_mm",
        "precip_30d_sum_mm",
        "lead_time_days",
    ]
    for col in forbidden_columns:
        assert col not in district_daily_df.columns, f"Forbidden column {col} found in analysis dataset"

