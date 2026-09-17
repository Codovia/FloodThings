"""
Validation rules and utilities for FloodPulse data ingestion.

Enforces schema contracts:
- Physical measurement bounds (temperatures, rainfall, river stages, capacities).
- Geographic bounds (WGS84 EPSG:4326 coordinates, Karnataka envelope).
- UTC timezone standardization from local/IST timestamps.
- Explicit QualityStatus assignments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo

from geoalchemy2.elements import WKTElement

# Standard bounding box for Karnataka (with buffer for trans-boundary river basins)
KARNATAKA_LAT_MIN = 11.0
KARNATAKA_LAT_MAX = 19.0
KARNATAKA_LON_MIN = 73.5
KARNATAKA_LON_MAX = 79.0

IST_TZ = ZoneInfo("Asia/Kolkata")


class QualityStatus:
    """Allowed quality statuses per DATA_CONTRACT.md."""

    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    MISSING = "MISSING"
    STALE = "STALE"


def parse_utc_timestamp(
    ts_val: Any,
    default_tz: ZoneInfo = IST_TZ,
) -> datetime | None:
    """Parse various timestamp representations into timezone-aware UTC datetime.

    Handles:
    - datetime instances (if naive, assumes default_tz)
    - ISO 8601 strings (e.g. 2026-09-17T06:00:00Z, 2026-09-17T06:00)
    - Indian Standard Time string formats (e.g. DD-MM-YYYY HH:mm:ss, DD-MM-YYYY HH:mm)
    """
    if ts_val is None:
        return None

    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            ts_val = ts_val.replace(tzinfo=default_tz)
        return ts_val.astimezone(timezone.utc)

    ts_str = str(ts_val).strip()
    if not ts_str or ts_str.lower() in ("nan", "null", "none", ""):
        return None

    # Try ISO format
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    # Common Indian government formats (DD-MM-YYYY HH:mm:ss, DD-MM-YYYY HH:mm, DD/MM/YYYY)
    common_formats = [
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in common_formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            dt = dt.replace(tzinfo=default_tz)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def validate_coordinates(
    lat: Any,
    lon: Any,
    karnataka_only: bool = False,
) -> tuple[float, float] | None:
    """Validate that coordinates are numbers and fall within acceptable bounds.

    Returns:
        tuple (latitude, longitude) as floats, or None if invalid.
    """
    if lat is None or lon is None:
        return None

    try:
        f_lat = float(lat)
        f_lon = float(lon)
    except (ValueError, TypeError):
        return None

    # Global WGS84 range check
    if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0):
        return None

    if karnataka_only:
        if not (
            KARNATAKA_LAT_MIN <= f_lat <= KARNATAKA_LAT_MAX
            and KARNATAKA_LON_MIN <= f_lon <= KARNATAKA_LON_MAX
        ):
            return None

    return f_lat, f_lon


def validate_float(
    val: Any,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float | None:
    """Validate a numeric value and enforce range checks.

    Returns float if valid, None otherwise.
    """
    if val is None:
        return None

    try:
        # Handle string numbers with whitespace or commas
        if isinstance(val, str):
            clean_str = val.strip().replace(",", "")
            if not clean_str or clean_str.lower() in ("nan", "null", "none", "nr", "nd", "-"):
                return None
            f_val = float(clean_str)
        else:
            f_val = float(val)
    except (ValueError, TypeError):
        return None

    if min_val is not None and f_val < min_val:
        return None
    if max_val is not None and f_val > max_val:
        return None

    return f_val


def make_point_wkt(lat: float, lon: float) -> WKTElement:
    """Create a GeoAlchemy2 WKTElement for PostGIS insertion in EPSG:4326."""
    return WKTElement(f"POINT({lon} {lat})", srid=4326)
