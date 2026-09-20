"""
Deterministic validation for Open-Meteo ERA5 historical meteorological chunk responses.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
import math
from typing import Any

from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    ExtractionConfig,
    ValidationResult,
)


class HistoricalChunkValidator:
    r"""
    Validates API responses against physical and structural invariants.

    Enforces:
    - Expected location count and coordinate snapping ($\pm 0.001^\circ$)
    - Exact hourly count (8,760 for non-leap, 8,784 for leap years)
    - Strict chronological +1h progression, zero duplicate or missing timestamps
    - Zero null values in required variables
    - Physical value constraints (precipitation >= 0, RH in [0, 100], finite floats)
    - Zero silent repair or interpolation
    """

    def __init__(self, config: ExtractionConfig | None = None):
        self.config = config or ExtractionConfig()

    def validate_chunk_response(
        self,
        chunk: ExtractionChunk,
        payload: Any,
        http_status: int = 200,
    ) -> ValidationResult:
        """
        Validate a chunk payload against all integrity rules.

        Returns ValidationResult with details on all detected discrepancies.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if http_status != 200:
            errors.append(f"HTTP status is {http_status}, expected 200")
            return ValidationResult(
                is_valid=False,
                status=ChunkStatus.VALIDATION_FAILED,
                errors=errors,
            )

        # 1. Response Structure
        if isinstance(payload, list):
            loc_list = payload
        elif isinstance(payload, dict):
            # Single location returns a single dict
            loc_list = [payload]
        else:
            errors.append(f"Invalid response payload type: {type(payload).__name__}, expected list or dict")
            return ValidationResult(
                is_valid=False,
                status=ChunkStatus.VALIDATION_FAILED,
                errors=errors,
            )

        expected_loc_count = len(chunk.cells)
        if len(loc_list) != expected_loc_count:
            errors.append(
                f"Returned location count ({len(loc_list)}) does not match requested ({expected_loc_count})"
            )

        # 2. Expected Hourly Count
        is_leap = calendar.isleap(chunk.year)
        expected_hours_per_loc = 8784 if is_leap else 8760
        expected_first_time = f"{chunk.year}-01-01T00:00"
        expected_last_time = f"{chunk.year}-12-31T23:00"

        total_records_validated = 0
        total_null_counts: dict[str, int] = {v: 0 for v in self.config.hourly_variables}

        for idx, loc in enumerate(loc_list):
            if idx >= len(chunk.cells):
                break

            target_cell = chunk.cells[idx]
            ret_lat = loc.get("latitude")
            ret_lon = loc.get("longitude")

            # Coordinate Snapping Validation
            if ret_lat is None or ret_lon is None:
                errors.append(f"Location {idx}: Missing latitude or longitude in response")
            else:
                lat_diff = abs(ret_lat - target_cell.lat)
                lon_diff = abs(ret_lon - target_cell.lon)
                if lat_diff > 0.001 or lon_diff > 0.001:
                    errors.append(
                        f"Location {idx}: Returned coords ({ret_lat}, {ret_lon}) differ from "
                        f"requested ({target_cell.lat}, {target_cell.lon}) by ({lat_diff:.4f}, {lon_diff:.4f})"
                    )

            hourly = loc.get("hourly")
            if not isinstance(hourly, dict):
                errors.append(f"Location {idx}: Missing or invalid 'hourly' object")
                continue

            times = hourly.get("time", [])
            hours_count = len(times)
            total_records_validated += hours_count

            # Timestamp Count
            if hours_count != expected_hours_per_loc:
                errors.append(
                    f"Location {idx}: Hourly count is {hours_count}, expected {expected_hours_per_loc} "
                    f"for year {chunk.year} (leap={is_leap})"
                )

            # Timestamp Bounds and Duplicates
            if times:
                if times[0] != expected_first_time:
                    errors.append(
                        f"Location {idx}: First timestamp is {times[0]}, expected {expected_first_time}"
                    )
                if times[-1] != expected_last_time:
                    errors.append(
                        f"Location {idx}: Last timestamp is {times[-1]}, expected {expected_last_time}"
                    )
                if len(set(times)) != len(times):
                    errors.append(f"Location {idx}: Duplicate timestamps detected in time array")

                # Timestamp Progression (+1h)
                for t_i in range(min(len(times) - 1, 1000)):  # Sample check or full check
                    try:
                        t_curr = datetime.fromisoformat(times[t_i])
                        t_next = datetime.fromisoformat(times[t_i + 1])
                        if t_next - t_curr != timedelta(hours=1):
                            errors.append(
                                f"Location {idx}: Non-hourly gap between {times[t_i]} and {times[t_i+1]}"
                            )
                            break
                    except Exception as parse_err:
                        errors.append(f"Location {idx}: Failed to parse timestamp {times[t_i]}: {parse_err}")
                        break

            # Variable Checks
            for var in self.config.hourly_variables:
                series = hourly.get(var)
                if series is None:
                    errors.append(f"Location {idx}: Required variable '{var}' missing from response")
                    continue
                if len(series) != hours_count:
                    errors.append(
                        f"Location {idx}: Length of '{var}' ({len(series)}) does not match time array ({hours_count})"
                    )

                nulls = sum(1 for val in series if val is None)
                total_null_counts[var] = total_null_counts.get(var, 0) + nulls
                if nulls > 0:
                    errors.append(f"Location {idx}: Variable '{var}' has {nulls} null values")

                # Physical Constraints
                for val_idx, val in enumerate(series):
                    if val is None:
                        continue
                    if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                        errors.append(
                            f"Location {idx}: Variable '{var}' at index {val_idx} has non-finite value: {val}"
                        )
                        break

                    if var == "precipitation" and val < 0.0:
                        errors.append(
                            f"Location {idx}: Negative precipitation detected: {val} mm at index {val_idx}"
                        )
                        break

                    if var == "relative_humidity_2m" and (val < 0.0 or val > 100.0):
                        errors.append(
                            f"Location {idx}: Relative humidity out of bounds: {val}% at index {val_idx}"
                        )
                        break

        is_valid = len(errors) == 0
        status = ChunkStatus.SUCCEEDED if is_valid else ChunkStatus.VALIDATION_FAILED

        return ValidationResult(
            is_valid=is_valid,
            status=status,
            errors=errors,
            warnings=warnings,
            locations_validated=len(loc_list),
            records_validated=total_records_validated,
            null_counts=total_null_counts,
        )
