"""
Quality and integrity validator for daily aggregated historical meteorological data.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta
import math
from typing import Sequence

from app.ingestion.historical.daily_models import (
    DailyProcessingStatus,
    DailyQualityStatus,
    DailyRecord,
    DailyValidationResult,
)
from app.ingestion.historical.models import GridCell


class DailyDatasetValidator:
    """
    Validates aggregated daily datasets against structural, physical, and completeness invariants.

    Enforces:
    - Complete calendar day sequence (365 days non-leap, 366 days leap year).
    - Leap day (Feb 29) handling: exactly once in leap years, zero in non-leap years.
    - Zero duplicate (latitude, longitude, date) records.
    - Coordinate preservation against expected grid cells (±0.0001°).
    - Physical value constraints:
        * precipitation >= 0.0
        * min_temp <= mean_temp <= max_temp, all finite
        * 0 <= RH <= 100
        * surface_pressure > 0, finite
    - Completeness semantics:
        * COMPLETE iff hour_count == 24
        * INCOMPLETE iff hour_count < 24
    """

    def validate_daily_records(
        self,
        records: Sequence[DailyRecord],
        expected_year: int,
        expected_cells: Sequence[GridCell] | None = None,
    ) -> DailyValidationResult:
        """
        Validate a collection of DailyRecord objects for a single chunk.

        Returns DailyValidationResult.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not records:
            errors.append("Empty daily records list provided")
            return DailyValidationResult(
                is_valid=False,
                status=DailyProcessingStatus.VALIDATION_FAILED,
                errors=errors,
            )

        is_leap = calendar.isleap(expected_year)
        expected_days_per_cell = 366 if is_leap else 365
        start_date = f"{expected_year}-01-01"
        end_date = f"{expected_year}-12-31"
        leap_day = f"{expected_year}-02-29"

        # Group records by (lat, lon)
        cell_records: dict[tuple[float, float], list[DailyRecord]] = defaultdict(list)
        for r in records:
            cell_records[(round(r.latitude, 4), round(r.longitude, 4))].append(r)

        # 1. Grid cell coverage and coordinate matching
        if expected_cells is not None:
            expected_cell_coords = [(round(c.lat, 4), round(c.lon, 4)) for c in expected_cells]
            if len(cell_records) != len(expected_cells):
                errors.append(
                    f"Cell count ({len(cell_records)}) does not match expected ({len(expected_cells)})"
                )

            for c_lat, c_lon in expected_cell_coords:
                # Check for matching cell within tolerance
                matched = any(
                    abs(rec_lat - c_lat) <= 0.001 and abs(rec_lon - c_lon) <= 0.001
                    for (rec_lat, rec_lon) in cell_records.keys()
                )
                if not matched:
                    errors.append(f"Expected grid cell ({c_lat}, {c_lon}) missing from daily records")

        complete_days = 0
        incomplete_days = 0

        # 2. Per-cell checks
        for (lat, lon), recs in cell_records.items():
            cell_tag = f"Cell ({lat}, {lon})"
            dates_seen: set[str] = set()

            if len(recs) != expected_days_per_cell:
                errors.append(
                    f"{cell_tag}: Daily record count is {len(recs)}, expected {expected_days_per_cell} "
                    f"for year {expected_year} (leap={is_leap})"
                )

            for r in recs:
                # Duplicate date check
                if r.date in dates_seen:
                    errors.append(f"{cell_tag}: Duplicate record for date {r.date}")
                dates_seen.add(r.date)

                # Year match
                if not r.date.startswith(f"{expected_year}-"):
                    errors.append(f"{cell_tag}: Date {r.date} does not belong to expected year {expected_year}")

                # Completeness rules
                if r.quality_status == DailyQualityStatus.COMPLETE.value:
                    complete_days += 1
                    if r.hour_count != 24:
                        errors.append(
                            f"{cell_tag} on {r.date}: quality_status is COMPLETE but hour_count is {r.hour_count} (expected 24)"
                        )
                elif r.quality_status == DailyQualityStatus.INCOMPLETE.value:
                    incomplete_days += 1
                    if r.hour_count >= 24:
                        errors.append(
                            f"{cell_tag} on {r.date}: quality_status is INCOMPLETE but hour_count is {r.hour_count}"
                        )
                else:
                    errors.append(
                        f"{cell_tag} on {r.date}: Unknown quality_status '{r.quality_status}'"
                    )

                # Physical value constraints
                # Precipitation: >= 0.0
                if math.isnan(r.precipitation_total_mm) or math.isinf(r.precipitation_total_mm):
                    errors.append(f"{cell_tag} on {r.date}: Non-finite precipitation: {r.precipitation_total_mm}")
                elif r.precipitation_total_mm < 0.0:
                    errors.append(f"{cell_tag} on {r.date}: Negative precipitation: {r.precipitation_total_mm}")

                # Temperature: finite, min <= mean <= max
                for t_name, t_val in [
                    ("mean", r.temperature_mean_c),
                    ("min", r.temperature_min_c),
                    ("max", r.temperature_max_c),
                ]:
                    if math.isnan(t_val) or math.isinf(t_val):
                        errors.append(f"{cell_tag} on {r.date}: Non-finite temperature_{t_name}: {t_val}")

                if r.hour_count > 0:
                    if r.temperature_min_c > r.temperature_mean_c or r.temperature_mean_c > r.temperature_max_c:
                        errors.append(
                            f"{cell_tag} on {r.date}: Inconsistent temperatures: "
                            f"min={r.temperature_min_c}, mean={r.temperature_mean_c}, max={r.temperature_max_c}"
                        )

                # Relative Humidity: 0 <= RH <= 100
                if math.isnan(r.relative_humidity_mean_pct) or math.isinf(r.relative_humidity_mean_pct):
                    errors.append(f"{cell_tag} on {r.date}: Non-finite RH: {r.relative_humidity_mean_pct}")
                elif r.hour_count > 0 and (r.relative_humidity_mean_pct < 0.0 or r.relative_humidity_mean_pct > 100.0):
                    errors.append(f"{cell_tag} on {r.date}: RH out of range [0, 100]: {r.relative_humidity_mean_pct}%")

                # Surface Pressure: > 0.0 and finite
                if math.isnan(r.surface_pressure_mean_hpa) or math.isinf(r.surface_pressure_mean_hpa):
                    errors.append(f"{cell_tag} on {r.date}: Non-finite surface pressure: {r.surface_pressure_mean_hpa}")
                elif r.hour_count > 0 and r.surface_pressure_mean_hpa <= 0.0:
                    errors.append(f"{cell_tag} on {r.date}: Non-positive surface pressure: {r.surface_pressure_mean_hpa}")

            # Leap day verification
            if is_leap:
                if leap_day not in dates_seen:
                    errors.append(f"{cell_tag}: Missing leap day {leap_day} for leap year {expected_year}")
            else:
                if leap_day in dates_seen:
                    errors.append(f"{cell_tag}: Unexpected leap day {leap_day} found in non-leap year {expected_year}")

            # Start and End bounds
            if start_date not in dates_seen:
                errors.append(f"{cell_tag}: Missing first calendar day {start_date}")
            if end_date not in dates_seen:
                errors.append(f"{cell_tag}: Missing last calendar day {end_date}")

        is_valid = len(errors) == 0
        status = DailyProcessingStatus.SUCCEEDED if is_valid else DailyProcessingStatus.VALIDATION_FAILED

        return DailyValidationResult(
            is_valid=is_valid,
            status=status,
            errors=errors,
            warnings=warnings,
            records_validated=len(records),
            cells_validated=len(cell_records),
            complete_days=complete_days,
            incomplete_days=incomplete_days,
        )
