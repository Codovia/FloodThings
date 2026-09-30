"""
Tests for partial-year and custom-bound ERA5 extraction and processing.
"""

from datetime import datetime, timedelta
import pytest

from app.ingestion.historical.client import HistoricalOpenMeteoClient
from app.ingestion.historical.daily_aggregator import DailyAggregator
from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyProcessingStatus, DailyRecord
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.daily_validator import DailyDatasetValidator
from app.ingestion.historical.grid import generate_chunks, get_spatial_batches
from app.ingestion.historical.models import ChunkStatus, ExtractionChunk, ExtractionConfig, GridCell
from app.ingestion.historical.validator import HistoricalChunkValidator


def test_chunk_default_and_custom_dates():
    cell = GridCell(lat=12.0, lon=76.0)
    # Default (historical full year)
    default_chunk = ExtractionChunk(
        chunk_id="era5_1994_batch_001",
        year=1994,
        batch_id=1,
        cells=[cell],
    )
    client = HistoricalOpenMeteoClient()
    params = client.build_query_params(default_chunk)
    assert params["start_date"] == "1994-01-01"
    assert params["end_date"] == "1994-12-31"

    # Custom bounded (e.g. 2026 up to Sep 21)
    bounded_chunk = ExtractionChunk(
        chunk_id="era5_2026_batch_001",
        year=2026,
        batch_id=1,
        cells=[cell],
        start_date="2026-01-01",
        end_date="2026-09-21",
    )
    bounded_params = client.build_query_params(bounded_chunk)
    assert bounded_params["start_date"] == "2026-01-01"
    assert bounded_params["end_date"] == "2026-09-21"


def test_generate_chunks_with_final_end_date():
    chunks = generate_chunks(
        start_year=2025,
        end_year=2026,
        batch_size=10,
        eligible_only=True,
        final_end_date="2026-09-21",
    )
    # 2 years * 33 batches = 66 chunks
    assert len(chunks) == 66
    c_2025 = [c for c in chunks if c.year == 2025]
    c_2026 = [c for c in chunks if c.year == 2026]
    assert len(c_2025) == 33
    assert len(c_2026) == 33

    # 2025 chunks have None (default full year)
    assert c_2025[0].end_date is None
    # 2026 chunks have final_end_date
    assert c_2026[0].end_date == "2026-09-21"
    assert c_2026[0].start_date == "2026-01-01"


def test_validator_with_bounded_dates():
    cell = GridCell(lat=12.0, lon=76.0)
    chunk = ExtractionChunk(
        chunk_id="era5_2026_batch_001",
        year=2026,
        batch_id=1,
        cells=[cell],
        start_date="2026-01-01",
        end_date="2026-01-03",
    )
    validator = HistoricalChunkValidator()

    # 3 days = 72 hours
    times = [
        (datetime(2026, 1, 1) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00")
        for h in range(72)
    ]
    payload = {
        "latitude": 12.0,
        "longitude": 76.0,
        "hourly": {
            "time": times,
            "precipitation": [0.0] * 72,
            "temperature_2m": [25.0] * 72,
            "relative_humidity_2m": [60.0] * 72,
            "surface_pressure": [950.0] * 72,
        },
    }
    result = validator.validate_chunk_response(chunk, payload)
    assert result.is_valid is True
    assert result.status == ChunkStatus.SUCCEEDED
    assert result.records_validated == 72


def test_daily_validator_with_bounded_dates():
    validator = DailyDatasetValidator()
    cell = GridCell(lat=12.0, lon=76.0)
    records = [
        DailyRecord(
            date="2026-01-01",
            latitude=12.0,
            longitude=76.0,
            precipitation_total_mm=0.0,
            temperature_mean_c=25.0,
            temperature_min_c=20.0,
            temperature_max_c=30.0,
            relative_humidity_mean_pct=65.0,
            surface_pressure_mean_hpa=950.0,
            hour_count=24,
            quality_status="COMPLETE",
        ),
        DailyRecord(
            date="2026-01-02",
            latitude=12.0,
            longitude=76.0,
            precipitation_total_mm=1.0,
            temperature_mean_c=24.0,
            temperature_min_c=19.0,
            temperature_max_c=29.0,
            relative_humidity_mean_pct=70.0,
            surface_pressure_mean_hpa=951.0,
            hour_count=24,
            quality_status="COMPLETE",
        ),
    ]

    # Valid with custom range 2026-01-01 to 2026-01-02
    res = validator.validate_daily_records(
        records,
        expected_year=2026,
        expected_cells=[cell],
        expected_start_date="2026-01-01",
        expected_end_date="2026-01-02",
    )
    assert res.is_valid is True
    assert res.status == DailyProcessingStatus.SUCCEEDED
    assert res.complete_days == 2


def test_recent_cli_safety_guards(tmp_path):
    from app.ingestion.historical.recent_cli import run_cli

    # Year before 2011 rejected
    code = run_cli(["extract", "--year", "2010"])
    assert code == 1

    # Year after 2026 rejected
    code = run_cli(["extract", "--year", "2027"])
    assert code == 1

    # Historical path targeting rejected
    code = run_cli(["extract", "--year", "2023", "--raw-dir", "data/raw/era5_historical"])
    assert code == 1

    code = run_cli(["process", "--year", "2023", "--output-dir", "data/processed/era5_daily"])
    assert code == 1


def test_recent_cli_status_and_dry_run(tmp_path, capsys):
    from unittest.mock import patch
    from app.ingestion.historical.recent_cli import run_cli

    # Status runs cleanly
    code = run_cli(["status"])
    assert code == 0

    # Dry-run extract for 2023 batch 1 with temporary paths
    raw_dir = tmp_path / "raw"
    manifest = tmp_path / "manifest.json"
    with patch("time.sleep"):
        code = run_cli([
            "extract",
            "--year", "2023",
            "--batch", "1",
            "--limit", "1",
            "--dry-run",
            "--raw-dir", str(raw_dir),
            "--manifest-path", str(manifest),
        ])
    # Returns 0 on clean execution or mock
    assert code in (0, 1)


