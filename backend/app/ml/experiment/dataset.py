"""
Dataset Loader and Feature Contract Enforcer (Phase 5.4).

Ensures:
1. Canonical 27 predictors are selected in deterministic order.
2. All 30 non-predictor / forbidden leakage columns are strictly rejected.
3. Cold-start initialization rows (930 rows where is_weather_complete_30d == False) are excluded.
4. Source Parquet file SHA-256 is verified and never modified.
5. Three-state semantics are preserved (FLOOD = 1, UNKNOWN = None, NO_FLOOD = 0).
6. PU labeling proxy s in {0, 1} is constructed (1 = verified positive, 0 = unlabeled).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Expected SHA-256 digest of the audited supervised feature matrix (Recent 2011-2023)
EXPECTED_SUPERVISED_SHA256 = (
    "d459e4461166842e194de8f8373f227585169f124cd620160a4aea74651e5dac"
)

# Expected SHA-256 digest of the audited historical feature matrix (1969-1994)
EXPECTED_HISTORICAL_SHA256 = (
    "849f722b4f5f6a9ee85882abf787ae3d6ea5e0abdb563f499567ede738e06d55"
)

# Canonical 27 predictor features (deterministic ordering)
CANONICAL_PREDICTORS: list[str] = [
    # Dynamic Antecedent Meteorology ([t-30, t-1])
    "precip_1d_mm",
    "precip_3d_sum_mm",
    "precip_7d_sum_mm",
    "precip_14d_sum_mm",
    "precip_30d_sum_mm",
    "precip_7d_max_mm",
    "precip_14d_max_mm",
    "temp_mean_1d_c",
    "temp_min_1d_c",
    "temp_max_1d_c",
    "temp_7d_mean_c",
    "rh_mean_1d_pct",
    "rh_7d_mean_pct",
    "pressure_mean_1d_hpa",
    # Static Zonal Terrain (Copernicus DEM GLO-30)
    "elevation_mean_m",
    "elevation_min_m",
    "elevation_max_m",
    "elevation_std_m",
    "slope_mean_deg",
    "slope_max_deg",
    # Static Hydrological GIS (CWC Basins & HydroBASINS Level-7)
    "major_basin_count",
    "primary_basin_coverage_pct",
    "sub_basin_count",
    "mean_upstream_area_km2",
    # Spatial & Calendar Context
    "weather_cell_count",
    "day_of_year",
    "target_month",
]

# Columns strictly prohibited from predictor feature sets (leakage, target, metadata)
FORBIDDEN_COLUMNS: set[str] = {
    "district_id",
    "kgis_district_code",
    "lgd_district_code",
    "district_name",
    "target_date",
    "target_year",
    "target_day",
    "prediction_anchor_utc",
    "feature_window_start",
    "feature_window_end",
    "flood_occurrence",
    "label_state",
    "event_count",
    "source_event_ids",
    "main_causes",
    "severities",
    "fatalities",
    "displaced",
    "lead_time_days",
    "is_weather_complete_1d",
    "is_weather_complete_30d",
    "valid_weather_days_30d",
    "terrain_coverage_pct",
    "primary_basin_name",
    "feature_version",
    "source_era5",
    "source_ifi",
    "source_dem",
    "source_hydro",
    "source_admin",
}


def compute_file_sha256(file_path: Path | str) -> str:
    """Compute hex SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass(frozen=True)
class ExperimentDataset:
    """Encapsulates the pre-training audited supervised dataset."""

    df: pd.DataFrame
    features: list[str]
    sha256: str
    total_raw_rows: int
    excluded_cold_start_rows: int
    active_rows: int
    num_positives: int
    num_unlabeled: int
    num_negatives: int

    @property
    def X(self) -> np.ndarray:
        """Return NumPy 2D array of predictor features."""
        return self.df[self.features].to_numpy(dtype=np.float64)

    @property
    def s_proxy(self) -> np.ndarray:
        """
        Return binary labeling indicator s in {0, 1}.

        1 = verified positive flood event (P)
        0 = unrecorded / unlabeled observation (U)

        NOTE: s=0 does NOT represent verified negative ground truth.
        """
        return (self.df["label_state"] == "FLOOD").to_numpy(dtype=np.int32)

    @property
    def target_dates(self) -> pd.Series:
        return self.df["target_date"]

    @property
    def target_years(self) -> pd.Series:
        return self.df["target_year"]

    @property
    def district_ids(self) -> pd.Series:
        return self.df["district_id"]


def load_supervised_dataset(
    parquet_path: Path | str | None = None,
    verify_sha256: bool = True,
    exclude_cold_start: bool = True,
    expected_sha256: str | None = None,
) -> ExperimentDataset:
    """
    Load a supervised feature matrix (Recent or Historical), verify SHA-256 integrity,
    filter cold-start rows, and enforce canonical predictor whitelist.
    """
    if parquet_path is None:
        # Default project path (recent supervised matrix)
        curr = Path(__file__).resolve().parent
        project_root = curr.parents[3]
        parquet_path = (
            project_root
            / "data"
            / "processed"
            / "ml_matrix"
            / "recent"
            / "district_day_matrix_2011_2023.parquet"
        )
    else:
        parquet_path = Path(parquet_path)

    if not parquet_path.exists():
        raise FileNotFoundError(f"Supervised Parquet matrix not found: {parquet_path}")

    # Determine target expected SHA-256
    if expected_sha256 is None:
        if "district_day_feature_matrix.parquet" in str(parquet_path):
            target_sha = EXPECTED_HISTORICAL_SHA256
        else:
            target_sha = EXPECTED_SUPERVISED_SHA256
    else:
        target_sha = expected_sha256

    # 1. SHA-256 Verification
    actual_sha256 = compute_file_sha256(parquet_path)
    if verify_sha256 and actual_sha256 != target_sha:
        raise ValueError(
            f"SHA-256 digest mismatch on {parquet_path}.\n"
            f"Expected: {target_sha}\n"
            f"Observed: {actual_sha256}"
        )

    # 2. Read Parquet via PyArrow (zero disk modification)
    table = pq.read_table(parquet_path)
    df_raw = table.to_pandas()
    raw_rows = len(df_raw)

    # 3. Verify Three-State Label Semantics in Raw Data
    if (df_raw["label_state"] == "NO_FLOOD").sum() > 0:
        raise ValueError("Dataset violates three-state contract: found NO_FLOOD labels.")
    if (df_raw["flood_occurrence"] == 0).sum() > 0:
        raise ValueError("Dataset violates three-state contract: found 0 labels in flood_occurrence.")
    
    # 4. Check for forbidden columns in candidate predictor list
    overlap = set(CANONICAL_PREDICTORS).intersection(FORBIDDEN_COLUMNS)
    if overlap:
        raise ValueError(f"CRITICAL: Forbidden columns found in CANONICAL_PREDICTORS: {overlap}")

    # 5. Cold-Start Initialization Boundary Handling
    if exclude_cold_start:
        if "is_weather_complete_30d" in df_raw.columns:
            cold_start_mask = ~df_raw["is_weather_complete_30d"]
            excluded_count = int(cold_start_mask.sum())
            if excluded_count != 930:
                logger.warning(
                    "Expected exactly 930 cold-start rows, but found %d", excluded_count
                )
            df = df_raw.loc[~cold_start_mask].copy()
        else:
            excluded_count = 0
            df = df_raw.copy()
    else:
        excluded_count = 0
        df = df_raw.copy()

    df = df.reset_index(drop=True)
    active_rows = len(df)

    # Verify zero nulls remain in the 27 predictors
    null_counts = df[CANONICAL_PREDICTORS].isna().sum().sum()
    if null_counts > 0:
        raise ValueError(
            f"Predictor features contain {null_counts} null values after cold-start filtering."
        )

    num_pos = int((df["label_state"] == "FLOOD").sum())
    num_unlab = int((df["label_state"] == "UNKNOWN").sum())
    num_neg = int((df["label_state"] == "NO_FLOOD").sum())

    logger.info(
        "Loaded ExperimentDataset: %d active rows (%d raw - %d cold-start). Positives: %d, Unlabeled: %d, Negatives: %d",
        active_rows,
        raw_rows,
        excluded_count,
        num_pos,
        num_unlab,
        num_neg,
    )

    return ExperimentDataset(
        df=df,
        features=list(CANONICAL_PREDICTORS),
        sha256=actual_sha256,
        total_raw_rows=raw_rows,
        excluded_cold_start_rows=excluded_count,
        active_rows=active_rows,
        num_positives=num_pos,
        num_unlabeled=num_unlab,
        num_negatives=num_neg,
    )


def load_historical_dataset(
    parquet_path: Path | str | None = None,
    verify_sha256: bool = True,
    exclude_cold_start: bool = True,
) -> ExperimentDataset:
    """
    Load the historical 1969-1994 baseline feature matrix, verify SHA-256 integrity,
    filter cold-start rows, and enforce canonical predictor whitelist.
    """
    if parquet_path is None:
        curr = Path(__file__).resolve().parent
        project_root = curr.parents[3]
        parquet_path = (
            project_root
            / "data"
            / "processed"
            / "ml_matrix"
            / "district_day_feature_matrix.parquet"
        )
    return load_supervised_dataset(
        parquet_path=parquet_path,
        verify_sha256=verify_sha256,
        exclude_cold_start=exclude_cold_start,
        expected_sha256=EXPECTED_HISTORICAL_SHA256,
    )
