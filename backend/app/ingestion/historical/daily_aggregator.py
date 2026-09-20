"""
Daily meteorological aggregation logic for historical Open-Meteo ERA5 hourly chunks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from typing import Any

from app.ingestion.historical.daily_models import DailyQualityStatus, DailyRecord


class DailyAggregator:
    """
    Aggregates hourly ERA5 meteorological data into canonical daily UTC records.

    Enforces:
    - UTC calendar day grouping (YYYY-MM-DD).
    - Precipitation: arithmetic sum of valid hourly precipitation (mm). Zero mm != missing.
    - Temperature: arithmetic mean, minimum, maximum (°C).
    - Relative Humidity: arithmetic mean (%).
    - Surface Pressure: arithmetic mean (hPa).
    - Completeness: COMPLETE iff hour_count == 24, else INCOMPLETE.
    - Zero imputation, zero synthetic filling, zero interpolation.
    - Deterministic sorting: (latitude, longitude, date).
    """

    def __init__(self, processing_version: str = "1.0"):
        self.processing_version = processing_version

    def aggregate_chunk_payload(
        self,
        payload: list[dict[str, Any]] | dict[str, Any],
        raw_chunk_id: str,
        raw_payload_sha256: str,
    ) -> list[DailyRecord]:
        """
        Aggregate a complete chunk payload (list of location dictionaries or single dict) into daily records.

        Returns a deterministically sorted list of DailyRecord objects.
        """
        loc_list = payload if isinstance(payload, list) else [payload]
        all_daily_records: list[DailyRecord] = []

        for loc in loc_list:
            lat = float(loc["latitude"])
            lon = float(loc["longitude"])
            hourly = loc.get("hourly", {})
            times = hourly.get("time", [])
            precips = hourly.get("precipitation", [])
            temps = hourly.get("temperature_2m", [])
            rhs = hourly.get("relative_humidity_2m", [])
            pressures = hourly.get("surface_pressure", [])

            # Group hourly observations by UTC calendar date
            # Key: YYYY-MM-DD -> list of hourly dicts
            days_data: dict[str, list[dict[str, float | None]]] = defaultdict(list)

            for i, t_str in enumerate(times):
                # ISO timestamp: YYYY-MM-DDTHH:MM (in UTC)
                date_str = t_str[:10]
                days_data[date_str].append(
                    {
                        "precipitation": precips[i] if i < len(precips) else None,
                        "temperature_2m": temps[i] if i < len(temps) else None,
                        "relative_humidity_2m": rhs[i] if i < len(rhs) else None,
                        "surface_pressure": pressures[i] if i < len(pressures) else None,
                    }
                )

            # Aggregate each day
            for date_str in sorted(days_data.keys()):
                hours = days_data[date_str]
                daily_record = self._aggregate_single_day(
                    date=date_str,
                    lat=lat,
                    lon=lon,
                    hours=hours,
                    raw_chunk_id=raw_chunk_id,
                    raw_payload_sha256=raw_payload_sha256,
                )
                all_daily_records.append(daily_record)

        # Deterministic sorting by (latitude, longitude, date)
        all_daily_records.sort(key=lambda r: (r.latitude, r.longitude, r.date))
        return all_daily_records

    def _aggregate_single_day(
        self,
        date: str,
        lat: float,
        lon: float,
        hours: list[dict[str, float | None]],
        raw_chunk_id: str,
        raw_payload_sha256: str,
    ) -> DailyRecord:
        """Aggregate 1 calendar day of hourly records for a single grid cell."""
        valid_precips: list[float] = []
        valid_temps: list[float] = []
        valid_rhs: list[float] = []
        valid_pressures: list[float] = []

        valid_hours_count = 0

        for h in hours:
            p = h.get("precipitation")
            t = h.get("temperature_2m")
            rh = h.get("relative_humidity_2m")
            sp = h.get("surface_pressure")

            # An hour is valid only if all 4 required variables are non-null and finite
            if (
                p is not None
                and not math.isnan(p)
                and not math.isinf(p)
                and t is not None
                and not math.isnan(t)
                and not math.isinf(t)
                and rh is not None
                and not math.isnan(rh)
                and not math.isinf(rh)
                and sp is not None
                and not math.isnan(sp)
                and not math.isinf(sp)
            ):
                valid_hours_count += 1
                valid_precips.append(float(p))
                valid_temps.append(float(t))
                valid_rhs.append(float(rh))
                valid_pressures.append(float(sp))

        is_complete = valid_hours_count == 24 and len(hours) == 24
        quality_status = (
            DailyQualityStatus.COMPLETE.value if is_complete else DailyQualityStatus.INCOMPLETE.value
        )

        if valid_hours_count > 0:
            # Precipitation: SUM of hourly amounts (do NOT average)
            precip_total = round(sum(valid_precips), 4)
            # Temperature: arithmetic mean, min, max
            temp_mean = round(sum(valid_temps) / len(valid_temps), 4)
            temp_min = round(min(valid_temps), 4)
            temp_max = round(max(valid_temps), 4)
            # Relative humidity: arithmetic mean
            rh_mean = round(sum(valid_rhs) / len(valid_rhs), 4)
            # Surface pressure: arithmetic mean
            sp_mean = round(sum(valid_pressures) / len(valid_pressures), 4)
        else:
            # Completely missing day
            precip_total = 0.0
            temp_mean = 0.0
            temp_min = 0.0
            temp_max = 0.0
            rh_mean = 0.0
            sp_mean = 0.0

        return DailyRecord(
            date=date,
            latitude=lat,
            longitude=lon,
            precipitation_total_mm=precip_total,
            temperature_mean_c=temp_mean,
            temperature_min_c=temp_min,
            temperature_max_c=temp_max,
            relative_humidity_mean_pct=rh_mean,
            surface_pressure_mean_hpa=sp_mean,
            hour_count=valid_hours_count,
            quality_status=quality_status,
            source="Open-Meteo Historical Weather API",
            dataset_model="ERA5",
            raw_chunk_id=raw_chunk_id,
            raw_payload_sha256=raw_payload_sha256,
            processing_version=self.processing_version,
        )
