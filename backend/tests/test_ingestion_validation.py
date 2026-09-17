"""
Tests for FloodPulse data ingestion validation rules and utilities.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest

from app.ingestion.validation import (
    IST_TZ,
    QualityStatus,
    make_point_wkt,
    parse_utc_timestamp,
    validate_coordinates,
    validate_float,
)


class TestTimestampValidation:
    """Test UTC normalization from various timestamps."""

    def test_parse_iso_utc_string(self):
        ts = "2026-09-17T12:00:00Z"
        dt = parse_utc_timestamp(ts)
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 12

    def test_parse_naive_datetime_assumes_ist(self):
        naive = datetime(2026, 9, 17, 17, 30, 0)  # 17:30 IST is 12:00 UTC
        dt = parse_utc_timestamp(naive, default_tz=IST_TZ)
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 12
        assert dt.minute == 0

    def test_parse_indian_gov_date_formats(self):
        # DD-MM-YYYY HH:mm
        dt1 = parse_utc_timestamp("02-01-2026 08:00", default_tz=IST_TZ)
        assert dt1 is not None
        assert dt1.year == 2026
        assert dt1.month == 1
        assert dt1.day == 2
        # 08:00 IST is 02:30 UTC
        assert dt1.hour == 2
        assert dt1.minute == 30

        # DD-MM-YYYY HH:mm:ss
        dt2 = parse_utc_timestamp("08-06-2006 12:06:00", default_tz=IST_TZ)
        assert dt2 is not None
        assert dt2.year == 2006
        assert dt2.month == 6
        assert dt2.day == 8

    def test_parse_invalid_timestamps_return_none(self):
        assert parse_utc_timestamp(None) is None
        assert parse_utc_timestamp("") is None
        assert parse_utc_timestamp("nan") is None
        assert parse_utc_timestamp("invalid_date") is None


class TestCoordinateValidation:
    """Test WGS84 and Karnataka bounding box validation."""

    def test_valid_wgs84_coordinates(self):
        coords = validate_coordinates(12.9716, 77.5946)
        assert coords == (12.9716, 77.5946)

    def test_string_coordinates_converted(self):
        coords = validate_coordinates("15.85", "74.50")
        assert coords == (15.85, 74.50)

    def test_out_of_range_coordinates_rejected(self):
        assert validate_coordinates(95.0, 77.0) is None
        assert validate_coordinates(12.0, 190.0) is None
        assert validate_coordinates("abc", 77.0) is None
        assert validate_coordinates(None, 77.0) is None

    def test_karnataka_bounding_box(self):
        # Inside Karnataka
        assert validate_coordinates(13.0, 76.0, karnataka_only=True) is not None
        # Outside Karnataka (e.g. Delhi)
        assert validate_coordinates(28.6, 77.2, karnataka_only=True) is None

    def test_make_point_wkt(self):
        wkt = make_point_wkt(12.5, 76.8)
        assert str(wkt) == "POINT(76.8 12.5)"
        assert wkt.srid == 4326


class TestFloatValidation:
    """Test numeric range validation and missingness preservation."""

    def test_valid_float_within_range(self):
        val = validate_float("25.4", min_val=0.0, max_val=100.0)
        assert val == 25.4

    def test_missing_values_remain_none(self):
        assert validate_float(None) is None
        assert validate_float("") is None
        assert validate_float("nan") is None
        assert validate_float("null") is None
        assert validate_float("NR") is None  # Not Reported
        assert validate_float("-") is None

    def test_out_of_bounds_returns_none(self):
        # Negative rainfall rejected
        assert validate_float(-5.0, min_val=0.0) is None
        # Humidity > 100% rejected
        assert validate_float(105.0, min_val=0.0, max_val=100.0) is None


class TestQualityStatusConstants:
    """Ensure QualityStatus matches DATA_CONTRACT.md."""

    def test_all_statuses_valid(self):
        expected = {"VALID", "SUSPECT", "INVALID", "MISSING", "STALE"}
        actual = {
            QualityStatus.VALID,
            QualityStatus.SUSPECT,
            QualityStatus.INVALID,
            QualityStatus.MISSING,
            QualityStatus.STALE,
        }
        assert actual == expected
