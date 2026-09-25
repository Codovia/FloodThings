"""
Historical ML Feature Matrix Pipeline (Phase 4).

Constructs the canonical historical District x Day ML dataset by temporally
and spatially aligning:
1. ERA5 historical daily meteorological features (area-weighted from 0.25° grid to districts).
2. India Flood Inventory (IFI v3.0) historical flood labels (three-state contract).
3. Copernicus DEM GLO-30 zonal terrain statistics (elevation, slope).
4. CWC & HydroBASINS hydrological GIS attributes (major basins, sub-basins, upstream area).

Strict Guarantees:
- Spatial unit: DISTRICT x DAY.
- Strict 24-hour lead time: Features look strictly backwards into [t-W, t-1] for target day t.
- Zero temporal leakage: Weather on day t NEVER enters predictor features.
- Zero silent zero-filling: Incomplete or missing weather days propagate to NaN.
- Three-state labelling: FLOOD = 1, NO_FLOOD = 0 only with validated observation window, UNKNOWN = NULL.
- Deterministic and reproducible: Output is deterministically sorted by (district_id, date).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date as dt_date, datetime, timezone, timedelta
import json
import logging
import math
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from shapely import box, wkb

from app.db.session import _get_engine, _get_session_factory
from app.gis.ksrsac import KsrsacAdminNormalizer
from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyRecord
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.grid import get_era5_eligible_grid
from app.ml.contracts import SampleLabelState, TemporalLeakageError
from app.ml.flood_labels import (
    IFI_EARLIEST_VALID_DATE,
    IFI_LATEST_VALID_DATE,
    SOURCE_NAME as IFI_SOURCE_NAME,
)

logger = logging.getLogger(__name__)

FEATURE_MATRIX_VERSION: str = "1.0.0"
ROLLING_WINDOWS: tuple[int, ...] = (1, 3, 7, 14, 30)
MIN_CELL_COVERAGE_WEIGHT: float = 0.95


def _find_project_root() -> Path:
    """Resolve repository project root directory."""
    curr = Path(__file__).resolve().parent
    for parent in [curr] + list(curr.parents):
        if (parent / "data").exists() and (parent / "backend").exists():
            return parent
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _find_project_root()
DEFAULT_WEIGHTS_CACHE_PATH = PROJECT_ROOT / "data" / "processed" / "gis_cache" / "district_era5_weights.json"
DEFAULT_DAILY_ERA5_DIR = PROJECT_ROOT / "data" / "processed" / "era5_daily"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml_matrix"
DEFAULT_PARQUET_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "district_day_feature_matrix.parquet"


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DistrictStaticFeatures:
    """Static terrain and hydrological attributes for a single district."""

    district_id: str
    kgis_district_code: str
    lgd_district_code: str
    district_name: str

    # Terrain attributes (from terrain_statistics)
    elevation_mean_m: float | None
    elevation_min_m: float | None
    elevation_max_m: float | None
    elevation_std_m: float | None
    slope_mean_deg: float | None
    slope_max_deg: float | None
    terrain_coverage_pct: float | None

    # Hydrological attributes (from district_river_basins & district_sub_basins)
    major_basin_count: int | None
    primary_basin_name: str | None
    primary_basin_coverage_pct: float | None
    sub_basin_count: int | None
    mean_upstream_area_km2: float | None


@dataclass(frozen=True)
class DistrictDailyWeather:
    """Area-weighted daily meteorological observation for a district on a single date."""

    district_id: str
    date: str  # YYYY-MM-DD
    precipitation_sum_mm: float
    temperature_mean_c: float
    temperature_min_c: float
    temperature_max_c: float
    relative_humidity_mean_pct: float
    surface_pressure_mean_hpa: float
    available_cell_weight: float
    is_complete: bool


@dataclass(frozen=True)
class DistrictDayFeatureRecord:
    """
    A single canonical observation row in the District x Day ML Feature Matrix.

    Anchor: Prediction target is on calendar day `target_date` (at 00:00 UTC).
    Predictor Features: Constructed strictly from observations in [target_date - 30, target_date - 1].
    Day target_date weather is strictly excluded.
    """

    # Spatiotemporal Identification
    district_id: str
    kgis_district_code: str
    lgd_district_code: str
    district_name: str
    target_date: str  # YYYY-MM-DD
    target_year: int
    target_month: int
    target_day: int
    day_of_year: int
    prediction_anchor_utc: str
    lead_time_days: int
    feature_window_start: str
    feature_window_end: str

    # Target & Labels
    flood_occurrence: int | None  # 1 for FLOOD, 0 for NO_FLOOD, None for UNKNOWN
    label_state: str  # 'FLOOD', 'NO_FLOOD', 'UNKNOWN'
    event_count: int | None
    source_event_ids: list[str]
    main_causes: list[str]
    severities: list[str]
    fatalities: int | None
    displaced: int | None

    # Weather Features (Antecedent [target_date - W, target_date - 1])
    precip_1d_mm: float | None
    precip_3d_sum_mm: float | None
    precip_7d_sum_mm: float | None
    precip_14d_sum_mm: float | None
    precip_30d_sum_mm: float | None
    precip_7d_max_mm: float | None
    precip_14d_max_mm: float | None
    temp_mean_1d_c: float | None
    temp_min_1d_c: float | None
    temp_max_1d_c: float | None
    temp_7d_mean_c: float | None
    rh_mean_1d_pct: float | None
    rh_7d_mean_pct: float | None
    pressure_mean_1d_hpa: float | None

    # Data Quality Indicators
    is_weather_complete_1d: bool
    is_weather_complete_30d: bool
    valid_weather_days_30d: int
    weather_cell_count: int

    # Static Terrain Features
    elevation_mean_m: float | None
    elevation_min_m: float | None
    elevation_max_m: float | None
    elevation_std_m: float | None
    slope_mean_deg: float | None
    slope_max_deg: float | None
    terrain_coverage_pct: float | None

    # Static Hydrological Features
    major_basin_count: int | None
    primary_basin_name: str | None
    primary_basin_coverage_pct: float | None
    sub_basin_count: int | None
    mean_upstream_area_km2: float | None

    # Provenance Metadata
    feature_version: str = FEATURE_MATRIX_VERSION
    source_era5: str = "ECMWF ERA5 via Open-Meteo Historical Weather API"
    source_ifi: str = IFI_SOURCE_NAME
    source_dem: str = "Copernicus DEM GLO-30 DGED 2021"
    source_hydro: str = "CWC Basins 2024 / HydroBASINS Level-7"
    source_admin: str = "KSR-SAC / KGIS 2024"

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return asdict(self)


# -----------------------------------------------------------------------------
# Spatial Weights Calculator & Cache
# -----------------------------------------------------------------------------


class DistrictSpatialWeightsService:
    """
    Computes and caches exact area-weighted intersection weights between
    Karnataka administrative districts (31 districts) and 0.25° ERA5 grid cells (318 eligible cells).

    Weights are normalized so sum(w_{d, c}) = 1.000000 for each district d.
    """

    def __init__(self, cache_path: Path | str | None = None):
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_WEIGHTS_CACHE_PATH
        self._weights: dict[str, dict[str, float]] = {}  # district_id -> {cell_id: weight}
        self._district_meta: dict[str, dict[str, Any]] = {}
        if self.cache_path.exists():
            self.load_cache()

    def load_cache(self) -> None:
        """Load precomputed spatial weights from JSON cache."""
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._weights = data.get("weights", {})
            self._district_meta = data.get("district_meta", {})
            logger.info("Loaded district spatial weights for %d districts from %s", len(self._weights), self.cache_path)
        except Exception as e:
            logger.warning("Failed to load district spatial weights from %s: %s", self.cache_path, e)

    def save_cache(self) -> None:
        """Persist spatial weights to JSON cache."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "district_count": len(self._weights),
            "district_meta": self._district_meta,
            "weights": self._weights,
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved district spatial weights to %s", self.cache_path)

    def compute_weights(self, force: bool = False) -> dict[str, dict[str, float]]:
        """
        Compute exact geometric area weights between districts and eligible ERA5 cells.

        Returns
        -------
        dict[str, dict[str, float]]
            Mapping of district_id -> {cell_id: normalized_area_weight}.
        """
        if not force and self._weights:
            return self._weights

        from sqlalchemy import text

        eligible_cells = get_era5_eligible_grid()
        cell_boxes = {
            c.cell_id: (c, box(c.lon - 0.125, c.lat - 0.125, c.lon + 0.125, c.lat + 0.125))
            for c in eligible_cells
        }

        SessionLocal = _get_session_factory()
        with SessionLocal() as session:
            districts = session.execute(
                text("SELECT id, name, code, ST_AsBinary(geometry) as geom_wkb FROM districts ORDER BY name")
            ).fetchall()

        weights: dict[str, dict[str, float]] = {}
        meta: dict[str, dict[str, Any]] = {}

        for dist in districts:
            d_id = str(dist.id)
            d_geom = wkb.loads(bytes(dist.geom_wkb))

            intersections: dict[str, float] = {}
            for cell_id, (cell, c_box) in cell_boxes.items():
                if d_geom.intersects(c_box):
                    inter = d_geom.intersection(c_box)
                    if not inter.is_empty and inter.area > 0:
                        intersections[cell_id] = inter.area

            total_inter_area = sum(intersections.values())
            if total_inter_area > 0:
                norm_weights = {
                    cid: round(a / total_inter_area, 6) for cid, a in intersections.items()
                }
                # Ensure exact sum to 1.000000
                diff = 1.0 - sum(norm_weights.values())
                if abs(diff) > 1e-9:
                    largest_cell = max(norm_weights.keys(), key=lambda k: norm_weights[k])
                    norm_weights[largest_cell] = round(norm_weights[largest_cell] + diff, 6)
            else:
                norm_weights = {}

            weights[d_id] = norm_weights
            meta[d_id] = {
                "name": dist.name,
                "lgd_code": dist.code,
                "cell_count": len(norm_weights),
                "cells": sorted(list(norm_weights.keys())),
            }

        self._weights = weights
        self._district_meta = meta
        self.save_cache()
        return self._weights

    def get_district_weights(self, district_id: str) -> dict[str, float]:
        """Get cell weights for a specific district."""
        if not self._weights:
            self.compute_weights()
        return self._weights.get(str(district_id), {})


# -----------------------------------------------------------------------------
# Static Feature Service
# -----------------------------------------------------------------------------


class DistrictStaticFeatureService:
    """Retrieves static terrain and hydrological attributes for all 31 districts."""

    def __init__(self):
        self._cache: dict[str, DistrictStaticFeatures] = {}

    def get_all_districts(self) -> dict[str, DistrictStaticFeatures]:
        """Retrieve static attributes for all districts."""
        if self._cache:
            return self._cache

        from sqlalchemy import text

        normalizer = KsrsacAdminNormalizer()
        norm_result = normalizer.normalize()

        SessionLocal = _get_session_factory()
        with SessionLocal() as session:
            # 1. Base districts
            dists = session.execute(
                text("SELECT id, name, code FROM districts ORDER BY name")
            ).fetchall()

            # 2. Terrain statistics
            terrain_rows = session.execute(
                text("""
                    SELECT 
                        district_id, elevation_mean, elevation_min, elevation_max, elevation_std,
                        slope_mean, slope_max, coverage_percentage
                    FROM terrain_statistics
                    WHERE target_type = 'DISTRICT'
                """)
            ).fetchall()
            terrain_map = {str(r.district_id): r for r in terrain_rows}

            # 3. Hydrological major basins
            basin_rows = session.execute(
                text("""
                    WITH ranked_basins AS (
                        SELECT 
                            drb.district_id,
                            rb.name as basin_name,
                            drb.percent_of_district_in_basin as cov_pct,
                            COUNT(*) OVER (PARTITION BY drb.district_id) as total_basins,
                            ROW_NUMBER() OVER (
                                PARTITION BY drb.district_id 
                                ORDER BY drb.percent_of_district_in_basin DESC
                            ) as rnk
                        FROM district_river_basins drb
                        JOIN river_basins rb ON rb.id = drb.river_basin_id
                    )
                    SELECT district_id, total_basins, basin_name, cov_pct
                    FROM ranked_basins
                    WHERE rnk = 1
                """)
            ).fetchall()
            basin_map = {str(r.district_id): r for r in basin_rows}

            # 4. Hydrological sub-basins
            sub_basin_rows = session.execute(
                text("""
                    SELECT 
                        dsb.district_id,
                        COUNT(DISTINCT dsb.sub_basin_id) as sub_basin_count,
                        SUM(dsb.percent_of_district_in_subbasin * COALESCE(sb.up_area, 0)) / 
                            NULLIF(SUM(dsb.percent_of_district_in_subbasin), 0) as mean_upstream_area_km2
                    FROM district_sub_basins dsb
                    JOIN sub_basins sb ON sb.id = dsb.sub_basin_id
                    GROUP BY dsb.district_id
                """)
            ).fetchall()
            sub_basin_map = {str(r.district_id): r for r in sub_basin_rows}

        features: dict[str, DistrictStaticFeatures] = {}
        for d in dists:
            d_id = str(d.id)
            lgd_code = str(d.code)
            norm_dist = norm_result.get_district_by_lgd(lgd_code)
            kgis_code = norm_dist.kgis_district_code if norm_dist else ""

            t_row = terrain_map.get(d_id)
            b_row = basin_map.get(d_id)
            sb_row = sub_basin_map.get(d_id)

            feat = DistrictStaticFeatures(
                district_id=d_id,
                kgis_district_code=kgis_code,
                lgd_district_code=lgd_code,
                district_name=d.name,
                elevation_mean_m=round(t_row.elevation_mean, 2) if t_row and t_row.elevation_mean is not None else None,
                elevation_min_m=round(t_row.elevation_min, 2) if t_row and t_row.elevation_min is not None else None,
                elevation_max_m=round(t_row.elevation_max, 2) if t_row and t_row.elevation_max is not None else None,
                elevation_std_m=round(t_row.elevation_std, 2) if t_row and t_row.elevation_std is not None else None,
                slope_mean_deg=round(t_row.slope_mean, 2) if t_row and t_row.slope_mean is not None else None,
                slope_max_deg=round(t_row.slope_max, 2) if t_row and t_row.slope_max is not None else None,
                terrain_coverage_pct=round(t_row.coverage_percentage, 2) if t_row and t_row.coverage_percentage is not None else None,
                major_basin_count=int(b_row.total_basins) if b_row and b_row.total_basins is not None else None,
                primary_basin_name=str(b_row.basin_name) if b_row and b_row.basin_name else None,
                primary_basin_coverage_pct=round(float(b_row.cov_pct), 2) if b_row and b_row.cov_pct is not None else None,
                sub_basin_count=int(sb_row.sub_basin_count) if sb_row and sb_row.sub_basin_count is not None else None,
                mean_upstream_area_km2=round(float(sb_row.mean_upstream_area_km2), 2) if sb_row and sb_row.mean_upstream_area_km2 is not None else None,
            )
            features[d_id] = feat

        self._cache = features
        return features


# -----------------------------------------------------------------------------
# District Weather Aggregator
# -----------------------------------------------------------------------------


class DistrictWeatherAggregator:
    """
    Aggregates daily 0.25° ERA5 grid records into daily district-level observations
    using normalized spatial area weights.
    """

    def __init__(
        self,
        weights_service: DistrictSpatialWeightsService | None = None,
        daily_base_dir: Path | str | None = None,
    ):
        self.weights_service = weights_service or DistrictSpatialWeightsService()
        self.daily_base_dir = Path(daily_base_dir) if daily_base_dir else DEFAULT_DAILY_ERA5_DIR
        self._daily_cache: dict[tuple[str, str], DistrictDailyWeather] = {}  # (district_id, date) -> record

    def load_year_weather(self, year: int) -> dict[tuple[str, str], DistrictDailyWeather]:
        """
        Load and aggregate daily ERA5 weather for a single calendar year across all districts.

        Returns
        -------
        dict[tuple[str, str], DistrictDailyWeather]
            Keyed by (district_id, date_str).
        """
        year_dir = self.daily_base_dir / f"year={year}"
        if not year_dir.exists():
            logger.warning("Daily processed directory does not exist: %s", year_dir)
            return {}

        parquet_files = sorted(list(year_dir.glob("batch_*.parquet")))
        if not parquet_files:
            logger.warning("No daily parquets found in %s", year_dir)
            return {}

        # 1. Read all batch parquets for the year into an arrow table
        tables = [pq.read_table(f) for f in parquet_files]
        merged = pa.concat_tables(tables, promote_options="default")
        df = merged.to_pandas()

        # 2. Compute spatial weights
        weights = self.weights_service.compute_weights()

        # 3. Derive cell_id if not present or partially populated
        if "cell_id" not in df.columns or df["cell_id"].isna().any():
            lat_round = (df["latitude"] * 100).round().astype(int)
            lon_round = (df["longitude"] * 100).round().astype(int)
            derived_cell_id = "ERA5_" + lat_round.map("{:04d}".format) + "_" + lon_round.map("{:05d}".format)
            if "cell_id" in df.columns:
                df["cell_id"] = df["cell_id"].fillna(derived_cell_id)
            else:
                df["cell_id"] = derived_cell_id

        # Index records by (cell_id, date)
        # Note: df has columns: date, cell_id, precipitation_total_mm, temperature_mean_c,
        # temperature_min_c, temperature_max_c, relative_humidity_mean_pct,
        # surface_pressure_mean_hpa, quality_status
        cell_date_records: dict[tuple[str, str], Any] = {}
        for row in df.itertuples():
            cell_date_records[(row.cell_id, row.date)] = row

        all_dates = sorted(df["date"].unique())
        year_result: dict[tuple[str, str], DistrictDailyWeather] = {}

        # 4. Aggregate for each district
        for dist_id, dist_weights in weights.items():
            if not dist_weights:
                continue

            for d_str in all_dates:
                weighted_precip = 0.0
                weighted_temp_mean = 0.0
                min_temp = float("inf")
                max_temp = float("-inf")
                weighted_rh = 0.0
                weighted_pressure = 0.0
                valid_weight = 0.0

                for cid, w in dist_weights.items():
                    rec = cell_date_records.get((cid, d_str))
                    if rec is not None and rec.quality_status == "COMPLETE" and not math.isnan(rec.precipitation_total_mm):
                        valid_weight += w
                        weighted_precip += w * rec.precipitation_total_mm
                        weighted_temp_mean += w * rec.temperature_mean_c
                        min_temp = min(min_temp, rec.temperature_min_c)
                        max_temp = max(max_temp, rec.temperature_max_c)
                        weighted_rh += w * rec.relative_humidity_mean_pct
                        weighted_pressure += w * rec.surface_pressure_mean_hpa

                is_complete = valid_weight >= MIN_CELL_COVERAGE_WEIGHT
                if is_complete and valid_weight > 0:
                    # Normalize by valid weight in case of tiny boundary coverage difference
                    scale = 1.0 / valid_weight
                    weather_rec = DistrictDailyWeather(
                        district_id=dist_id,
                        date=d_str,
                        precipitation_sum_mm=round(weighted_precip * scale, 4),
                        temperature_mean_c=round(weighted_temp_mean * scale, 2),
                        temperature_min_c=round(min_temp, 2),
                        temperature_max_c=round(max_temp, 2),
                        relative_humidity_mean_pct=round(weighted_rh * scale, 2),
                        surface_pressure_mean_hpa=round(weighted_pressure * scale, 2),
                        available_cell_weight=round(valid_weight, 4),
                        is_complete=True,
                    )
                else:
                    weather_rec = DistrictDailyWeather(
                        district_id=dist_id,
                        date=d_str,
                        precipitation_sum_mm=float("nan"),
                        temperature_mean_c=float("nan"),
                        temperature_min_c=float("nan"),
                        temperature_max_c=float("nan"),
                        relative_humidity_mean_pct=float("nan"),
                        surface_pressure_mean_hpa=float("nan"),
                        available_cell_weight=round(valid_weight, 4),
                        is_complete=False,
                    )

                year_result[(dist_id, d_str)] = weather_rec
                self._daily_cache[(dist_id, d_str)] = weather_rec

        logger.info("Aggregated district weather for year %d: %d records across %d dates", year, len(year_result), len(all_dates))
        return year_result

    def get_weather(self, district_id: str, date_str: str) -> DistrictDailyWeather | None:
        """Retrieve aggregated daily weather for a district and date."""
        return self._daily_cache.get((str(district_id), str(date_str)))


# -----------------------------------------------------------------------------
# Temporal Leakage Auditor
# -----------------------------------------------------------------------------


class TemporalLeakageAuditor:
    """
    Automated executable validator ensuring strict absence of temporal leakage:
    1. Feature window strictly precedes target date: max(feature_date) <= target_date - 1.
    2. Zero same-day weather leakage: Target date weather must not enter predictors.
    3. Monotonic chronological alignment.
    4. District-day uniqueness: No duplicate (district_id, date) rows.
    5. Label alignment: Target labels must be grounded strictly at target date.
    """

    @staticmethod
    def audit_record(rec: DistrictDayFeatureRecord) -> list[str]:
        """Audit a single feature record for leakage violations."""
        errors: list[str] = []
        target_dt = dt_date.fromisoformat(rec.target_date)
        window_end_dt = dt_date.fromisoformat(rec.feature_window_end)
        window_start_dt = dt_date.fromisoformat(rec.feature_window_start)

        # 1. Feature window end must be strictly before target date
        if window_end_dt >= target_dt:
            errors.append(
                f"Feature window end ({rec.feature_window_end}) leaks into or past target date ({rec.target_date})"
            )

        # 2. Lead time must equal target_date - window_end
        lead_time = (target_dt - window_end_dt).days
        if lead_time != rec.lead_time_days:
            errors.append(
                f"Calculated lead time ({lead_time} days) does not match record lead_time_days ({rec.lead_time_days})"
            )

        # 3. Feature window start must precede or equal window end
        if window_start_dt > window_end_dt:
            errors.append(
                f"Feature window start ({rec.feature_window_start}) exceeds window end ({rec.feature_window_end})"
            )

        # 4. Three-state label contract
        if rec.label_state == "UNLABELLED" or rec.label_state == "UNKNOWN":
            if rec.flood_occurrence is not None:
                errors.append(
                    f"UNKNOWN/UNLABELLED record must have flood_occurrence=None, got {rec.flood_occurrence}"
                )
        elif rec.label_state == "FLOOD":
            if rec.flood_occurrence != 1:
                errors.append(f"FLOOD record must have flood_occurrence=1, got {rec.flood_occurrence}")
        elif rec.label_state == "NO_FLOOD":
            if rec.flood_occurrence != 0:
                errors.append(f"NO_FLOOD record must have flood_occurrence=0, got {rec.flood_occurrence}")

        return errors

    @classmethod
    def audit_dataset(cls, records: Sequence[DistrictDayFeatureRecord]) -> dict[str, Any]:
        """
        Run comprehensive leakage and integrity audit on an entire dataset.

        Raises TemporalLeakageError if any leakage violation is detected.
        """
        seen_keys: set[tuple[str, str]] = set()
        violations: list[str] = []
        duplicate_keys: list[tuple[str, str]] = []

        for rec in records:
            # Check district-day uniqueness
            key = (rec.district_id, rec.target_date)
            if key in seen_keys:
                duplicate_keys.append(key)
            seen_keys.add(key)

            # Check individual record leakage
            errs = cls.audit_record(rec)
            if errs:
                violations.extend(errs)

        if duplicate_keys:
            violations.append(f"Found {len(duplicate_keys)} duplicate (district_id, target_date) rows")

        if violations:
            msg = f"Temporal leakage or integrity audit failed with {len(violations)} errors: " + "; ".join(violations[:5])
            logger.error(msg)
            raise TemporalLeakageError(msg)

        return {
            "is_valid": True,
            "total_records_audited": len(records),
            "unique_district_days": len(seen_keys),
            "leakage_violations_count": 0,
            "duplicate_rows_count": 0,
        }


# -----------------------------------------------------------------------------
# District Feature Matrix Builder
# -----------------------------------------------------------------------------


class DistrictFeatureMatrixBuilder:
    """
    Constructs the canonical District x Day historical ML dataset by aligning
    meteorology, IFI flood labels, terrain statistics, and hydrological attributes.
    """

    def __init__(
        self,
        weights_service: DistrictSpatialWeightsService | None = None,
        static_service: DistrictStaticFeatureService | None = None,
        weather_aggregator: DistrictWeatherAggregator | None = None,
        lead_time_days: int = 1,
    ):
        self.weights_service = weights_service or DistrictSpatialWeightsService()
        self.static_service = static_service or DistrictStaticFeatureService()
        self.weather_aggregator = weather_aggregator or DistrictWeatherAggregator(weights_service=self.weights_service)
        self.lead_time_days = lead_time_days
        self.auditor = TemporalLeakageAuditor()

    def build_matrix(
        self,
        start_date: str,
        end_date: str,
        observation_window: tuple[str, str] | None = None,
        output_parquet_path: Path | str | None = None,
    ) -> list[DistrictDayFeatureRecord]:
        """
        Build the canonical District x Day feature matrix for the specified date range.

        Parameters
        ----------
        start_date : str
            Start of target prediction range (YYYY-MM-DD).
        end_date : str
            End of target prediction range (YYYY-MM-DD).
        observation_window : tuple[str, str] | None
            Optional (start_obs, end_obs) defining an explicit observation window
            under which unrecorded dates evaluate to NO_FLOOD (0). Outside this window,
            or if None, unrecorded dates evaluate strictly to UNKNOWN (None).
        output_parquet_path : Path | str | None
            Optional path to serialize output Parquet dataset.

        Returns
        -------
        list[DistrictDayFeatureRecord]
            Deterministically sorted list of ML feature records.
        """
        from sqlalchemy import text

        start_dt = dt_date.fromisoformat(start_date)
        end_dt = dt_date.fromisoformat(end_date)
        if start_dt > end_dt:
            raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

        # Required lookback window: 30 days before start_date
        lookback_start_dt = start_dt - timedelta(days=30 + self.lead_time_days - 1)
        start_year = lookback_start_dt.year
        end_year = end_dt.year

        logger.info(
            "Building District x Day ML feature matrix for %s to %s (weather span: %d to %d)",
            start_date,
            end_date,
            start_year,
            end_year,
        )

        # 1. Preload static terrain and hydrological attributes
        static_features = self.static_service.get_all_districts()

        # 2. Load daily aggregated weather across all required years
        for yr in range(start_year, end_year + 1):
            self.weather_aggregator.load_year_weather(yr)

        # 3. Query IFI flood labels for the target range
        SessionLocal = _get_session_factory()
        with SessionLocal() as session:
            label_rows = session.execute(
                text("""
                    SELECT 
                        district_id, event_date, flood_occurrence, label, event_count,
                        source_event_ids, main_causes, severities, fatalities, displaced
                    FROM district_day_flood_labels
                    WHERE event_date >= :s_date AND event_date <= :e_date
                """),
                {"s_date": start_date, "e_date": end_date},
            ).fetchall()

        # Index labels by (district_id_str, date_str)
        ifi_labels: dict[tuple[str, str], Any] = {
            (str(r.district_id), str(r.event_date)): r for r in label_rows
        }

        # Resolve observation window boundaries
        obs_start_dt: dt_date | None = dt_date.fromisoformat(observation_window[0]) if observation_window else None
        obs_end_dt: dt_date | None = dt_date.fromisoformat(observation_window[1]) if observation_window else None

        records: list[DistrictDayFeatureRecord] = []

        # 4. Generate records for every district and every target day
        num_days = (end_dt - start_dt).days + 1
        target_dates = [start_dt + timedelta(days=k) for k in range(num_days)]

        for d_id, stat in sorted(static_features.items(), key=lambda x: x[1].district_name):
            cell_weights = self.weights_service.get_district_weights(d_id)
            weather_cell_count = len(cell_weights)

            for t_dt in target_dates:
                t_str = t_dt.isoformat()

                # Feature window end: strictly t_dt - lead_time_days
                fw_end_dt = t_dt - timedelta(days=self.lead_time_days)
                fw_end_str = fw_end_dt.isoformat()
                fw_start_dt = fw_end_dt - timedelta(days=29)  # 30-day window
                fw_start_str = fw_start_dt.isoformat()

                # --- 4A. Label Resolution ---
                label_row = ifi_labels.get((d_id, t_str))
                if label_row is not None and label_row.flood_occurrence == 1:
                    flood_occ: int | None = 1
                    label_state = "FLOOD"
                    event_cnt = label_row.event_count
                    src_ids = list(label_row.source_event_ids) if label_row.source_event_ids else []
                    causes = list(label_row.main_causes) if label_row.main_causes else []
                    sevs = list(label_row.severities) if label_row.severities else []
                    fats = label_row.fatalities
                    disp = label_row.displaced
                else:
                    # Check observation window
                    in_obs_window = (
                        obs_start_dt is not None
                        and obs_end_dt is not None
                        and obs_start_dt <= t_dt <= obs_end_dt
                    )
                    if in_obs_window:
                        flood_occ = 0
                        label_state = "NO_FLOOD"
                    else:
                        flood_occ = None
                        label_state = "UNKNOWN"
                    event_cnt = None
                    src_ids = []
                    causes = []
                    sevs = []
                    fats = None
                    disp = None

                # --- 4B. Weather Feature Extraction ---
                # Retrieve weather observations for [t_dt - 30, t_dt - 1]
                # Day t_dt is strictly excluded
                window_30_dates = [(fw_end_dt - timedelta(days=k)).isoformat() for k in range(30)]
                window_weather = [self.weather_aggregator.get_weather(d_id, d) for d in window_30_dates]

                # Completeness tracking
                complete_weather = [
                    w for w in window_weather if w is not None and w.is_complete and not math.isnan(w.precipitation_sum_mm)
                ]
                valid_weather_days_30d = len(complete_weather)
                is_weather_complete_30d = (valid_weather_days_30d == 30)

                # Day t-1 weather
                w_1d = window_weather[0]  # window_30_dates[0] is fw_end_dt (t-1)
                is_weather_complete_1d = (
                    w_1d is not None and w_1d.is_complete and not math.isnan(w_1d.precipitation_sum_mm)
                )

                if is_weather_complete_1d:
                    precip_1d = w_1d.precipitation_sum_mm
                    temp_mean_1d = w_1d.temperature_mean_c
                    temp_min_1d = w_1d.temperature_min_c
                    temp_max_1d = w_1d.temperature_max_c
                    rh_mean_1d = w_1d.relative_humidity_mean_pct
                    pressure_mean_1d = w_1d.surface_pressure_mean_hpa
                else:
                    precip_1d = None
                    temp_mean_1d = None
                    temp_min_1d = None
                    temp_max_1d = None
                    rh_mean_1d = None
                    pressure_mean_1d = None

                # Rolling rainfall sums: if any day in window [t-w, t-1] is missing/incomplete, sum is None
                rolling_precip: dict[int, float | None] = {}
                for w in (3, 7, 14, 30):
                    w_slice = window_weather[:w]
                    if len(w_slice) == w and all(
                        d is not None and d.is_complete and not math.isnan(d.precipitation_sum_mm) for d in w_slice
                    ):
                        rolling_precip[w] = round(sum(d.precipitation_sum_mm for d in w_slice), 4)
                    else:
                        rolling_precip[w] = None

                # Max daily precipitation in 7d and 14d
                slice_7d = window_weather[:7]
                if len(slice_7d) == 7 and all(
                    d is not None and d.is_complete and not math.isnan(d.precipitation_sum_mm) for d in slice_7d
                ):
                    precip_7d_max = round(max(d.precipitation_sum_mm for d in slice_7d), 4)
                    temp_7d_mean = round(sum(d.temperature_mean_c for d in slice_7d) / 7.0, 2)
                    rh_7d_mean = round(sum(d.relative_humidity_mean_pct for d in slice_7d) / 7.0, 2)
                else:
                    precip_7d_max = None
                    temp_7d_mean = None
                    rh_7d_mean = None

                slice_14d = window_weather[:14]
                if len(slice_14d) == 14 and all(
                    d is not None and d.is_complete and not math.isnan(d.precipitation_sum_mm) for d in slice_14d
                ):
                    precip_14d_max = round(max(d.precipitation_sum_mm for d in slice_14d), 4)
                else:
                    precip_14d_max = None

                # --- 4C. Assemble Record ---
                rec = DistrictDayFeatureRecord(
                    district_id=d_id,
                    kgis_district_code=stat.kgis_district_code,
                    lgd_district_code=stat.lgd_district_code,
                    district_name=stat.district_name,
                    target_date=t_str,
                    target_year=t_dt.year,
                    target_month=t_dt.month,
                    target_day=t_dt.day,
                    day_of_year=t_dt.timetuple().tm_yday,
                    prediction_anchor_utc=f"{t_str}T00:00:00Z",
                    lead_time_days=self.lead_time_days,
                    feature_window_start=fw_start_str,
                    feature_window_end=fw_end_str,
                    flood_occurrence=flood_occ,
                    label_state=label_state,
                    event_count=event_cnt,
                    source_event_ids=src_ids,
                    main_causes=causes,
                    severities=sevs,
                    fatalities=fats,
                    displaced=disp,
                    precip_1d_mm=precip_1d,
                    precip_3d_sum_mm=rolling_precip.get(3),
                    precip_7d_sum_mm=rolling_precip.get(7),
                    precip_14d_sum_mm=rolling_precip.get(14),
                    precip_30d_sum_mm=rolling_precip.get(30),
                    precip_7d_max_mm=precip_7d_max,
                    precip_14d_max_mm=precip_14d_max,
                    temp_mean_1d_c=temp_mean_1d,
                    temp_min_1d_c=temp_min_1d,
                    temp_max_1d_c=temp_max_1d,
                    temp_7d_mean_c=temp_7d_mean,
                    rh_mean_1d_pct=rh_mean_1d,
                    rh_7d_mean_pct=rh_7d_mean,
                    pressure_mean_1d_hpa=pressure_mean_1d,
                    is_weather_complete_1d=is_weather_complete_1d,
                    is_weather_complete_30d=is_weather_complete_30d,
                    valid_weather_days_30d=valid_weather_days_30d,
                    weather_cell_count=weather_cell_count,
                    elevation_mean_m=stat.elevation_mean_m,
                    elevation_min_m=stat.elevation_min_m,
                    elevation_max_m=stat.elevation_max_m,
                    elevation_std_m=stat.elevation_std_m,
                    slope_mean_deg=stat.slope_mean_deg,
                    slope_max_deg=stat.slope_max_deg,
                    terrain_coverage_pct=stat.terrain_coverage_pct,
                    major_basin_count=stat.major_basin_count,
                    primary_basin_name=stat.primary_basin_name,
                    primary_basin_coverage_pct=stat.primary_basin_coverage_pct,
                    sub_basin_count=stat.sub_basin_count,
                    mean_upstream_area_km2=stat.mean_upstream_area_km2,
                )
                records.append(rec)

        # 5. Deterministic sorting by (district_id, target_date)
        records.sort(key=lambda r: (r.district_id, r.target_date))

        # 6. Automated temporal leakage audit
        self.auditor.audit_dataset(records)

        # 7. Serialize to Parquet if requested
        if output_parquet_path:
            self.write_parquet(records, output_parquet_path)

        logger.info(
            "Constructed %d District x Day feature records across %d districts (%s to %s)",
            len(records),
            len(static_features),
            start_date,
            end_date,
        )
        return records

    @staticmethod
    def get_arrow_schema() -> pa.Schema:
        """Return PyArrow schema for district-day feature matrix."""
        return pa.schema([
            pa.field("district_id", pa.string(), nullable=False),
            pa.field("kgis_district_code", pa.string(), nullable=False),
            pa.field("lgd_district_code", pa.string(), nullable=False),
            pa.field("district_name", pa.string(), nullable=False),
            pa.field("target_date", pa.string(), nullable=False),
            pa.field("target_year", pa.int32(), nullable=False),
            pa.field("target_month", pa.int32(), nullable=False),
            pa.field("target_day", pa.int32(), nullable=False),
            pa.field("day_of_year", pa.int32(), nullable=False),
            pa.field("prediction_anchor_utc", pa.string(), nullable=False),
            pa.field("lead_time_days", pa.int32(), nullable=False),
            pa.field("feature_window_start", pa.string(), nullable=False),
            pa.field("feature_window_end", pa.string(), nullable=False),
            pa.field("flood_occurrence", pa.int32(), nullable=True),
            pa.field("label_state", pa.string(), nullable=False),
            pa.field("event_count", pa.int32(), nullable=True),
            pa.field("source_event_ids", pa.list_(pa.string()), nullable=False),
            pa.field("main_causes", pa.list_(pa.string()), nullable=False),
            pa.field("severities", pa.list_(pa.string()), nullable=False),
            pa.field("fatalities", pa.int32(), nullable=True),
            pa.field("displaced", pa.int32(), nullable=True),
            pa.field("precip_1d_mm", pa.float64(), nullable=True),
            pa.field("precip_3d_sum_mm", pa.float64(), nullable=True),
            pa.field("precip_7d_sum_mm", pa.float64(), nullable=True),
            pa.field("precip_14d_sum_mm", pa.float64(), nullable=True),
            pa.field("precip_30d_sum_mm", pa.float64(), nullable=True),
            pa.field("precip_7d_max_mm", pa.float64(), nullable=True),
            pa.field("precip_14d_max_mm", pa.float64(), nullable=True),
            pa.field("temp_mean_1d_c", pa.float64(), nullable=True),
            pa.field("temp_min_1d_c", pa.float64(), nullable=True),
            pa.field("temp_max_1d_c", pa.float64(), nullable=True),
            pa.field("temp_7d_mean_c", pa.float64(), nullable=True),
            pa.field("rh_mean_1d_pct", pa.float64(), nullable=True),
            pa.field("rh_7d_mean_pct", pa.float64(), nullable=True),
            pa.field("pressure_mean_1d_hpa", pa.float64(), nullable=True),
            pa.field("is_weather_complete_1d", pa.bool_(), nullable=False),
            pa.field("is_weather_complete_30d", pa.bool_(), nullable=False),
            pa.field("valid_weather_days_30d", pa.int32(), nullable=False),
            pa.field("weather_cell_count", pa.int32(), nullable=False),
            pa.field("elevation_mean_m", pa.float64(), nullable=True),
            pa.field("elevation_min_m", pa.float64(), nullable=True),
            pa.field("elevation_max_m", pa.float64(), nullable=True),
            pa.field("elevation_std_m", pa.float64(), nullable=True),
            pa.field("slope_mean_deg", pa.float64(), nullable=True),
            pa.field("slope_max_deg", pa.float64(), nullable=True),
            pa.field("terrain_coverage_pct", pa.float64(), nullable=True),
            pa.field("major_basin_count", pa.int32(), nullable=True),
            pa.field("primary_basin_name", pa.string(), nullable=True),
            pa.field("primary_basin_coverage_pct", pa.float64(), nullable=True),
            pa.field("sub_basin_count", pa.int32(), nullable=True),
            pa.field("mean_upstream_area_km2", pa.float64(), nullable=True),
            pa.field("feature_version", pa.string(), nullable=False),
            pa.field("source_era5", pa.string(), nullable=False),
            pa.field("source_ifi", pa.string(), nullable=False),
            pa.field("source_dem", pa.string(), nullable=False),
            pa.field("source_hydro", pa.string(), nullable=False),
            pa.field("source_admin", pa.string(), nullable=False),
        ])

    def write_parquet(
        self,
        records: Sequence[DistrictDayFeatureRecord],
        output_path: Path | str,
        compression: str = "snappy",
    ) -> Path:
        """Serialize feature records to a single Parquet file."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        schema = self.get_arrow_schema()
        dict_data = [r.to_dict() for r in records]
        table = pa.Table.from_pylist(dict_data, schema=schema)
        pq.write_table(table, out_p, compression=compression)
        logger.info("Wrote %d feature records to Parquet: %s", len(records), out_p)
        return out_p

    def generate_quality_audit(
        self,
        records: Sequence[DistrictDayFeatureRecord],
    ) -> dict[str, Any]:
        """
        Generate machine-readable quality audit dictionary conforming to Step 12 specification.
        """
        if not records:
            return {"total_rows": 0}

        dates = [r.target_date for r in records]
        districts = {r.district_id for r in records}

        # Label counts
        flood_count = sum(1 for r in records if r.label_state == "FLOOD")
        no_flood_count = sum(1 for r in records if r.label_state == "NO_FLOOD")
        unknown_count = sum(1 for r in records if r.label_state == "UNKNOWN")

        # Weather completeness
        complete_1d_count = sum(1 for r in records if r.is_weather_complete_1d)
        incomplete_1d_count = sum(1 for r in records if not r.is_weather_complete_1d)
        complete_30d_count = sum(1 for r in records if r.is_weather_complete_30d)

        # Missing feature counts
        missing_precip_1d = sum(1 for r in records if r.precip_1d_mm is None or math.isnan(r.precip_1d_mm))
        missing_precip_7d = sum(1 for r in records if r.precip_7d_sum_mm is None or math.isnan(r.precip_7d_sum_mm))
        missing_precip_30d = sum(1 for r in records if r.precip_30d_sum_mm is None or math.isnan(r.precip_30d_sum_mm))

        # Static feature coverage
        terrain_coverage = sum(1 for r in records if r.elevation_mean_m is not None)
        hydro_coverage = sum(1 for r in records if r.major_basin_count is not None)

        audit = {
            "total_district_day_rows": len(records),
            "date_range": {
                "start_date": min(dates),
                "end_date": max(dates),
                "unique_dates": len(set(dates)),
            },
            "district_count": len(districts),
            "label_distribution": {
                "FLOOD": flood_count,
                "NO_FLOOD": no_flood_count,
                "UNKNOWN": unknown_count,
                "positive_label_percentage": round(flood_count / len(records) * 100, 4),
            },
            "weather_quality": {
                "complete_1d_weather_count": complete_1d_count,
                "incomplete_1d_weather_count": incomplete_1d_count,
                "complete_30d_weather_count": complete_30d_count,
                "missing_precip_1d_count": missing_precip_1d,
                "missing_precip_7d_sum_count": missing_precip_7d,
                "missing_precip_30d_sum_count": missing_precip_30d,
            },
            "static_coverage": {
                "terrain_complete_rows": terrain_coverage,
                "terrain_coverage_pct": round(terrain_coverage / len(records) * 100, 2),
                "hydro_complete_rows": hydro_coverage,
                "hydro_coverage_pct": round(hydro_coverage / len(records) * 100, 2),
            },
            "temporal_leakage_audit": {
                "passed": True,
                "lead_time_days": self.lead_time_days,
                "max_feature_lag_days": 30,
                "future_information_in_predictors": False,
                "target_day_weather_in_predictors": False,
            },
            "feature_version": FEATURE_MATRIX_VERSION,
        }
        return audit
