"""
Chronological rolling feature generator for historical meteorological records.

Step 3 of the ML Feature Engineering Pipeline.
Transforms daily meteorological records into ML-ready feature records by:
1. Sorting records strictly chronologically per grid cell (zero temporal leakage).
2. Calculating backward-looking rolling rainfall windows (1d, 3d, 7d, 14d, 30d).
3. Explicitly preserving missing/incomplete day semantics (zero silent zero-filling).
4. Attaching static terrain (elevation, slope) and hydrological attributes from SpatialEnrichmentService.
5. Preserving exact provenance (cell_id, chunk_id, raw_chunk_id, raw_payload_sha256).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as dt_date, timedelta
import logging
import math
from typing import Sequence

from app.ingestion.historical.daily_models import DailyQualityStatus, DailyRecord
from app.ml.feature_schema import MLFeatureRecord
from app.ml.spatial_enrichment import CellSpatialAttributes, SpatialEnrichmentService

logger = logging.getLogger(__name__)

ROLLING_WINDOWS = (1, 3, 7, 14, 30)


class FeatureGenerator:
    """
    Transforms daily meteorological observations into ML-ready feature records.

    Guarantees:
    - Zero temporal leakage: No future observations enter any feature (all windows look strictly backwards).
    - Zero silent zero-filling: If any day in the rolling window is missing or incomplete, the window is NaN/None.
    - Deterministic output: Sorts strictly by (latitude, longitude, date).
    - Spatial & provenance preservation: cell_id, chunk_id, and raw SHA-256 are passed through untouched.
    """

    def __init__(
        self,
        spatial_service: SpatialEnrichmentService | None = None,
        feature_version: str = "1.0",
    ):
        self.spatial_service = spatial_service or SpatialEnrichmentService()
        self.feature_version = feature_version

    def generate_features(
        self,
        daily_records: Sequence[DailyRecord],
        lookback_records: Sequence[DailyRecord] | None = None,
    ) -> list[MLFeatureRecord]:
        """
        Generate ML feature records from a sequence of DailyRecord objects.

        Parameters
        ----------
        daily_records : Sequence[DailyRecord]
            Target daily records for which features will be emitted.
        lookback_records : Sequence[DailyRecord] | None
            Optional trailing daily records from preceding period (e.g. prior 29 days of year Y-1)
            used strictly to populate backward-looking windows for early days in daily_records.
            Lookback records are never emitted as output feature rows.

        Returns
        -------
        list[MLFeatureRecord]
            Deterministically sorted list of MLFeatureRecord objects.
        """
        if not daily_records:
            return []

        # Target cell-date pairs that should be emitted
        target_keys: set[tuple[str, str]] = {
            (r.cell_id, r.date) for r in daily_records
        }

        # Group all available records (target + lookback) by cell_id
        # Key: cell_id -> dict[date_str, DailyRecord]
        cell_daily_map: dict[str, dict[str, DailyRecord]] = defaultdict(dict)

        if lookback_records:
            for r in lookback_records:
                cell_daily_map[r.cell_id][r.date] = r

        for r in daily_records:
            cell_daily_map[r.cell_id][r.date] = r

        feature_records: list[MLFeatureRecord] = []

        # Process each cell
        for cell_id, date_map in cell_daily_map.items():
            # Get cell coordinates from one of the records
            any_rec = next(iter(date_map.values()))
            lat = any_rec.latitude
            lon = any_rec.longitude

            # Retrieve static spatial, terrain, and hydrological attributes
            try:
                spatial_attrs = self.spatial_service.get_cell_attributes(
                    cell_id=cell_id, latitude=lat, longitude=lon
                )
            except Exception as e:
                logger.warning("Could not retrieve spatial attributes for %s: %s", cell_id, e)
                spatial_attrs = CellSpatialAttributes(
                    cell_id=cell_id,
                    latitude=lat,
                    longitude=lon,
                    elevation_mean=None,
                    slope_mean=None,
                    basin_id=None,
                    basin_name=None,
                    sub_basin_id=None,
                    sub_basin_name=None,
                    hybas_id=None,
                    distance_to_river_m=None,
                    nearest_river_id=None,
                    district_id=None,
                    district_name=None,
                )

            # Generate features for every target date of this cell
            for target_date_str in sorted(date_map.keys()):
                if (cell_id, target_date_str) not in target_keys:
                    # Skip lookback records that are not in target set
                    continue

                curr_rec = date_map[target_date_str]
                feat_rec = self._compute_single_feature_record(
                    cell_id=cell_id,
                    date_str=target_date_str,
                    curr_rec=curr_rec,
                    date_map=date_map,
                    spatial_attrs=spatial_attrs,
                )
                feature_records.append(feat_rec)

        # Deterministic sort by (latitude, longitude, date)
        feature_records.sort(key=lambda r: (r.latitude, r.longitude, r.date))
        return feature_records

    def _compute_single_feature_record(
        self,
        cell_id: str,
        date_str: str,
        curr_rec: DailyRecord,
        date_map: dict[str, DailyRecord],
        spatial_attrs: CellSpatialAttributes,
    ) -> MLFeatureRecord:
        """Compute rolling features and assemble MLFeatureRecord for 1 cell on 1 calendar day."""
        year_val = int(date_str[:4])
        month_val = int(date_str[5:7])
        day_val = int(date_str[8:10])
        curr_dt = dt_date(year_val, month_val, day_val)

        # 1. Rolling rainfall windows
        rolling_sums: dict[int, float | None] = {}

        for w in ROLLING_WINDOWS:
            # Expected dates in [t - (w - 1), t]
            window_dates = [(curr_dt - timedelta(days=k)).isoformat() for k in range(w)]
            is_window_valid = True
            w_sum = 0.0

            for d in window_dates:
                d_rec = date_map.get(d)
                # Day is valid only if present, COMPLETE, and has finite non-negative precipitation
                if (
                    d_rec is None
                    or d_rec.quality_status != DailyQualityStatus.COMPLETE.value
                    or d_rec.hour_count != 24
                    or math.isnan(d_rec.precipitation_total_mm)
                    or math.isinf(d_rec.precipitation_total_mm)
                    or d_rec.precipitation_total_mm < 0.0
                ):
                    is_window_valid = False
                    break
                w_sum += d_rec.precipitation_total_mm

            if is_window_valid:
                rolling_sums[w] = round(w_sum, 4)
            else:
                rolling_sums[w] = None

        # Count COMPLETE days in the 30-day window [t - 29, t]
        dates_30 = [(curr_dt - timedelta(days=k)).isoformat() for k in range(30)]
        valid_days_30d = sum(
            1
            for d in dates_30
            if d in date_map
            and date_map[d].quality_status == DailyQualityStatus.COMPLETE.value
            and date_map[d].hour_count == 24
            and not math.isnan(date_map[d].precipitation_total_mm)
        )

        # 2. Weather statistics for day t
        is_day_complete = (
            curr_rec.quality_status == DailyQualityStatus.COMPLETE.value
            and curr_rec.hour_count == 24
        )

        if is_day_complete:
            temp_mean = (
                curr_rec.temperature_mean_c
                if not math.isnan(curr_rec.temperature_mean_c)
                else None
            )
            temp_min = (
                curr_rec.temperature_min_c
                if not math.isnan(curr_rec.temperature_min_c)
                else None
            )
            temp_max = (
                curr_rec.temperature_max_c
                if not math.isnan(curr_rec.temperature_max_c)
                else None
            )
            rh_mean = (
                curr_rec.relative_humidity_mean_pct
                if not math.isnan(curr_rec.relative_humidity_mean_pct)
                else None
            )
            sp_mean = (
                curr_rec.surface_pressure_mean_hpa
                if not math.isnan(curr_rec.surface_pressure_mean_hpa)
                else None
            )
        else:
            temp_mean = None
            temp_min = None
            temp_max = None
            rh_mean = None
            sp_mean = None

        # 3. Overall sample completeness flag
        is_fully_complete = bool(
            is_day_complete
            and rolling_sums[30] is not None
            and temp_mean is not None
            and spatial_attrs.elevation_mean is not None
            and spatial_attrs.slope_mean is not None
        )

        return MLFeatureRecord(
            date=date_str,
            cell_id=cell_id,
            chunk_id=curr_rec.chunk_id or curr_rec.raw_chunk_id,
            latitude=curr_rec.latitude,
            longitude=curr_rec.longitude,
            rainfall_1d=rolling_sums[1],
            rainfall_3d=rolling_sums[3],
            rainfall_7d=rolling_sums[7],
            rainfall_14d=rolling_sums[14],
            rainfall_30d=rolling_sums[30],
            temperature_mean_c=temp_mean,
            temperature_min_c=temp_min,
            temperature_max_c=temp_max,
            relative_humidity_mean_pct=rh_mean,
            surface_pressure_mean_hpa=sp_mean,
            elevation=spatial_attrs.elevation_mean,
            slope=spatial_attrs.slope_mean,
            basin_id=spatial_attrs.basin_id,
            basin_name=spatial_attrs.basin_name,
            sub_basin_id=spatial_attrs.sub_basin_id,
            sub_basin_name=spatial_attrs.sub_basin_name,
            hybas_id=spatial_attrs.hybas_id,
            distance_to_river_m=spatial_attrs.distance_to_river_m,
            nearest_river_id=spatial_attrs.nearest_river_id,
            district_id=spatial_attrs.district_id,
            district_name=spatial_attrs.district_name,
            hour_count=curr_rec.hour_count,
            quality_status=curr_rec.quality_status,
            window_30d_valid_days=valid_days_30d,
            is_complete=is_fully_complete,
            raw_chunk_id=curr_rec.raw_chunk_id or curr_rec.chunk_id,
            raw_payload_sha256=curr_rec.raw_payload_sha256,
            feature_version=self.feature_version,
        )
