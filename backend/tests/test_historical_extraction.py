"""
Unit tests for the historical meteorological extraction engine.

All tests use mocked responses and local filesystem fixtures (zero external network dependency).
"""

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import httpx

from app.ingestion.historical.client import (
    HistoricalExtractionError,
    HistoricalOpenMeteoClient,
    MalformedResponseError,
    RateLimitExceededError,
    ServerError,
)
from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import (
    ERA5_EXCLUDED_CELL_IDS,
    ERA5_EXCLUSION_REASON,
    generate_chunks,
    get_era5_eligible_grid,
    get_era5_excluded_cells,
    get_karnataka_grid,
    get_spatial_batches,
)
from app.ingestion.historical.manifest import HistoricalExtractionManifest
from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    ExtractionConfig,
    GridCell,
    ValidationResult,
)
from app.ingestion.historical.validator import HistoricalChunkValidator
from app.ingestion.historical.cli import run_cli


@pytest.fixture
def temp_raw_dir(tmp_path: Path) -> Path:
    """Temporary directory for raw extraction payloads and manifests."""
    raw_dir = tmp_path / "raw_era5"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


@pytest.fixture
def sample_cells() -> list[GridCell]:
    """Sample 3 Karnataka cells for lightweight testing."""
    return [
        GridCell(lat=14.25, lon=76.50, center_inside=True, name="Chitradurga"),
        GridCell(lat=13.25, lon=74.75, center_inside=True, name="Udupi"),
        GridCell(lat=18.25, lon=77.25, center_inside=True, name="Bidar"),
    ]


@pytest.fixture
def sample_chunk(sample_cells: list[GridCell]) -> ExtractionChunk:
    """Sample extraction chunk for non-leap year 1994."""
    return ExtractionChunk(
        chunk_id="era5_1994_batch_001",
        year=1994,
        batch_id=1,
        cells=sample_cells,
    )


def create_mock_payload(
    chunk: ExtractionChunk,
    hours_count: int | None = None,
    null_precip: bool = False,
    negative_precip: bool = False,
    invalid_rh: bool = False,
    duplicate_time: bool = False,
    time_gap: bool = False,
) -> list[dict]:
    """Helper to generate mock Open-Meteo ERA5 API payloads."""
    import calendar

    if hours_count is None:
        hours_count = 8784 if calendar.isleap(chunk.year) else 8760

    start_dt = datetime(chunk.year, 1, 1, 0, 0, tzinfo=timezone.utc)
    times = []
    for h in range(hours_count):
        dt = start_dt + timedelta(hours=h)
        times.append(dt.strftime("%Y-%m-%dT%H:%M"))

    if duplicate_time and len(times) > 1:
        times[1] = times[0]

    if time_gap and len(times) > 2:
        times[1] = (start_dt + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")

    loc_list = []
    for cell in chunk.cells:
        precip_series = [0.5] * hours_count
        if null_precip:
            precip_series[10] = None
        if negative_precip:
            precip_series[15] = -1.0

        rh_series = [65.0] * hours_count
        if invalid_rh:
            rh_series[20] = 110.0

        loc_list.append(
            {
                "latitude": cell.lat,
                "longitude": cell.lon,
                "elevation": 500.0,
                "hourly": {
                    "time": list(times),
                    "precipitation": precip_series,
                    "temperature_2m": [25.0] * hours_count,
                    "relative_humidity_2m": rh_series,
                    "surface_pressure": [950.0] * hours_count,
                },
            }
        )

    return loc_list


# =============================================================================
# 1. GRID AND CHUNK GENERATION TESTS
# =============================================================================


class TestGridAndChunkGeneration:
    """Test deterministic grid and chunk generation."""

    def test_karnataka_authoritative_grid_count(self):
        """Authoritative grid contains 324 cells (253 inside, 71 boundary/coastal)."""
        grid = get_karnataka_grid()
        assert len(grid) == 324
        centers_inside = sum(1 for c in grid if c.center_inside)
        assert centers_inside == 253
        assert len(grid) - centers_inside == 71
        # Check cell ID formatting
        assert grid[0].cell_id.startswith("ERA5_")

    def test_era5_eligible_grid_count(self):
        """Extraction-eligible grid contains 318 cells (324 - 6 offshore snapping cells)."""
        eligible = get_era5_eligible_grid()
        assert len(eligible) == 318
        # Ensure no excluded cell is present in eligible grid
        eligible_ids = {c.cell_id for c in eligible}
        assert eligible_ids.isdisjoint(ERA5_EXCLUDED_CELL_IDS)

    def test_era5_excluded_cells(self):
        """Exactly 6 offshore boundary cells are excluded with documented reason."""
        excluded = get_era5_excluded_cells()
        assert len(excluded) == 6
        excluded_ids = {c.cell_id for c in excluded}
        assert excluded_ids == ERA5_EXCLUDED_CELL_IDS
        # All 6 are coastal/offshore cells (center_inside is False)
        for c in excluded:
            assert c.center_inside is False
        # Documented reason matches requirement
        expected_reason = (
            "Open-Meteo ERA5 archive snaps requested offshore coordinate to a"
            " neighboring land-side ERA5 coordinate, preventing one-to-one spatial"
            " identity."
        )
        assert ERA5_EXCLUSION_REASON == expected_reason

    def test_zero_excluded_cells_in_eligible_batches(self):
        """Zero excluded cells are partitioned into production API extraction batches."""
        batches = get_spatial_batches(batch_size=10, eligible_only=True)
        for b in batches:
            batch_cell_ids = {c.cell_id for c in b}
            assert batch_cell_ids.isdisjoint(ERA5_EXCLUDED_CELL_IDS)

    def test_no_duplicate_coordinates_among_eligible_cells(self):
        """All 318 eligible cells possess unique spatial coordinates."""
        eligible = get_era5_eligible_grid()
        coords = [(c.lat, c.lon) for c in eligible]
        assert len(coords) == len(set(coords)) == 318

    def test_spatial_batches_eligible(self):
        """Authoritative grid partitioned into 33 permanent batches with in-batch exclusion."""
        batches = get_spatial_batches(batch_size=10, eligible_only=True)
        assert len(batches) == 33
        # 26 batches have 10 cells, 6 have 9 cells, 1 has 4 cells
        nine_cell_batches = [idx for idx, b in enumerate(batches, start=1) if len(b) == 9]
        assert nine_cell_batches == [4, 11, 12, 15, 16, 18]
        assert len(batches[32]) == 4  # final batch 33 has 4 cells
        total_eligible = sum(len(b) for b in batches)
        assert total_eligible == 318

    def test_spatial_batches_authoritative_full(self):
        """Full authoritative grid partitions into 33 batches: 32 of 10 and 1 of 4."""
        batches = get_spatial_batches(batch_size=10, eligible_only=False)
        assert len(batches) == 33
        for i in range(32):
            assert len(batches[i]) == 10
        assert len(batches[32]) == 4  # 32 * 10 + 4 = 324
        assert sum(len(b) for b in batches) == 324

    def test_chunk_generation_single_year(self):
        """Single year generates 33 production chunks (batches 001 to 033)."""
        chunks = generate_chunks(start_year=1994, end_year=1994, batch_size=10, eligible_only=True)
        assert len(chunks) == 33
        assert chunks[0].chunk_id == "era5_1994_batch_001"
        assert chunks[-1].chunk_id == "era5_1994_batch_033"
        assert chunks[0].spatial_fingerprint == "57ba28d6"

    def test_chunk_generation_full_26_years_eligible(self):
        """Full 26 years produces exactly 858 chunks across the 33 permanent batches (26 * 33)."""
        chunks = generate_chunks(start_year=1969, end_year=1994, batch_size=10, eligible_only=True)
        assert len(chunks) == 858
        assert chunks[0].chunk_id == "era5_1969_batch_001"
        assert chunks[-1].chunk_id == "era5_1994_batch_033"

    def test_chunk_spatial_fingerprint_determinism(self):
        """ExtractionChunk spatial_fingerprint is deterministic and detects cell alterations."""
        chunks = generate_chunks(start_year=1969, end_year=1969, batch_size=10, eligible_only=True)
        fp_001 = chunks[0].spatial_fingerprint
        assert len(fp_001) == 8
        # Deterministic across calls
        chunks_repeat = generate_chunks(start_year=1969, end_year=1969, batch_size=10, eligible_only=True)
        assert chunks_repeat[0].spatial_fingerprint == fp_001
        # Distinct batches have distinct fingerprints
        assert chunks[0].spatial_fingerprint != chunks[1].spatial_fingerprint
        assert chunks[0].chunk_id == "era5_1969_batch_001"
        assert chunks[-1].chunk_id == "era5_1969_batch_033"

    def test_chunk_generation_invalid_range(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            generate_chunks(start_year=1994, end_year=1969)


# =============================================================================
# 2. CLIENT AND PARAMETER CONSTRUCTION TESTS
# =============================================================================


class TestClientAndParameters:
    """Test HTTP client query construction and error handling."""

    def test_build_query_params(self, sample_chunk: ExtractionChunk):
        client = HistoricalOpenMeteoClient()
        params = client.build_query_params(sample_chunk)

        assert params["models"] == "era5"
        assert params["timezone"] == "UTC"
        assert params["precipitation_unit"] == "mm"
        assert params["temperature_unit"] == "celsius"
        assert params["start_date"] == "1994-01-01"
        assert params["end_date"] == "1994-12-31"
        assert "precipitation" in params["hourly"]
        assert "temperature_2m" in params["hourly"]
        assert "relative_humidity_2m" in params["hourly"]
        assert "surface_pressure" in params["hourly"]
        assert params["latitude"] == "14.25,13.25,18.25"
        assert params["longitude"] == "76.5,74.75,77.25"

    def test_client_fetch_success(self, sample_chunk: ExtractionChunk):
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_resp

        client = HistoricalOpenMeteoClient(client=mock_http)
        raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)

        assert status == 200
        assert raw_b == mock_bytes
        assert len(parsed_j) == 3
        assert lat >= 0.0

    def test_client_rate_limit_retry(self, sample_chunk: ExtractionChunk):
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(max_retries=2, rate_limit_cooldown_seconds=10.0, min_request_interval_seconds=1.0)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            assert mock_sleep.called
            # Fallback cooldown of 10.0s was used
            assert any(10.0 in call.args for call in mock_sleep.call_args_list)

    def test_client_request_pacing_minimum_interval(self, sample_chunk: ExtractionChunk):
        """Sequential requests on the same client are separated by min_request_interval_seconds."""
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp

        cfg = ExtractionConfig(min_request_interval_seconds=2.0)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        # First request sets _last_request_time without sleep
        client.fetch_chunk_payload(sample_chunk)

        # Second request immediately after must sleep for remainder of 2.0s
        with patch("time.sleep") as mock_sleep:
            client.fetch_chunk_payload(sample_chunk)
            assert mock_sleep.called
            sleep_arg = mock_sleep.call_args[0][0]
            assert 1.5 <= sleep_arg <= 2.05

    def test_client_retry_after_respected(self, sample_chunk: ExtractionChunk):
        """HTTP 429 with Retry-After header respects the header value."""
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "15"}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(max_retries=2, min_request_interval_seconds=1.0)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            assert 15.0 in sleep_calls

    def test_client_429_fallback_cooldown(self, sample_chunk: ExtractionChunk):
        """HTTP 429 without Retry-After header falls back to rate_limit_cooldown_seconds."""
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(
            max_retries=2,
            min_request_interval_seconds=1.0,
            rate_limit_cooldown_seconds=45.0,
        )
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            assert 45.0 in sleep_calls

    def test_client_429_not_faster_than_min_interval(self, sample_chunk: ExtractionChunk):
        """HTTP 429 with small Retry-After does not retry faster than min_request_interval_seconds."""
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.5"}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(max_retries=2, min_request_interval_seconds=3.0)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            # Must sleep max(0.5, 3.0) = 3.0
            assert 3.0 in sleep_calls

    def test_client_429_max_retries_exhausted_remains_retryable(self, sample_chunk: ExtractionChunk):
        """HTTP 429 exhausting all retries raises RateLimitExceededError with retryable=True."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1.0"}

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp_429

        cfg = ExtractionConfig(max_retries=2, min_request_interval_seconds=0.1)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep"):
            with pytest.raises(RateLimitExceededError) as exc_info:
                client.fetch_chunk_payload(sample_chunk)

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status == 429

    def test_extraction_config_default_interval_is_10_seconds(self):
        """ExtractionConfig defaults to 10.0s request interval and 2 rate limit max retries."""
        cfg = ExtractionConfig()
        assert cfg.min_request_interval_seconds == 10.0
        assert cfg.pacing_delay_seconds == 10.0
        assert cfg.rate_limit_cooldown_seconds == 60.0
        assert cfg.rate_limit_max_retries == 2

    def test_extraction_config_pacing_delay_sync(self):
        """ExtractionConfig synchronizes pacing_delay_seconds and min_request_interval_seconds."""
        cfg1 = ExtractionConfig(pacing_delay_seconds=4.0)
        assert cfg1.min_request_interval_seconds == 4.0
        assert cfg1.pacing_delay_seconds == 4.0

        cfg2 = ExtractionConfig(min_request_interval_seconds=6.0)
        assert cfg2.min_request_interval_seconds == 6.0
        assert cfg2.pacing_delay_seconds == 6.0

    def test_client_retry_after_http_date_format(self, sample_chunk: ExtractionChunk):
        """HTTP 429 with RFC 7231 / RFC 2822 HTTP-date Retry-After header is correctly parsed and waited."""
        import email.utils
        mock_data = create_mock_payload(sample_chunk)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        future_target = datetime.now(timezone.utc) + timedelta(seconds=25)
        http_date_str = email.utils.format_datetime(future_target)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": http_date_str}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(max_retries=2, min_request_interval_seconds=1.0)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            assert any(23.0 <= s <= 27.0 for s in sleep_calls)

    def test_client_rate_limit_bounded_retries(self, sample_chunk: ExtractionChunk):
        """Client only retries 429 up to rate_limit_max_retries without blocking for full max_retries."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1.0"}

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp_429

        # max_retries=5, but rate_limit_max_retries=2
        cfg = ExtractionConfig(max_retries=5, rate_limit_max_retries=2, min_request_interval_seconds=0.1)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(RateLimitExceededError):
                client.fetch_chunk_payload(sample_chunk)

        # 1 initial attempt + 1 retry = 2 total attempts made before raising
        assert mock_http.get.call_count == 2
        # Only 1 rate limit cooldown sleep occurred, not 4
        cooldown_sleeps = [c[0][0] for c in mock_sleep.call_args_list if c[0][0] >= 1.0]
        assert len(cooldown_sleeps) == 1

    def test_client_client_error_non_retryable(self, sample_chunk: ExtractionChunk):
        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400
        resp_400.text = "Bad Request"

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp_400

        client = HistoricalOpenMeteoClient(client=mock_http)
        with pytest.raises(HistoricalExtractionError) as exc_info:
            client.fetch_chunk_payload(sample_chunk)
        assert exc_info.value.retryable is False
        assert exc_info.value.http_status == 400

    def test_client_malformed_json(self, sample_chunk: ExtractionChunk):
        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = b"INVALID JSON CONTENT"

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp_200

        client = HistoricalOpenMeteoClient(client=mock_http)
        with pytest.raises(MalformedResponseError):
            client.fetch_chunk_payload(sample_chunk)


# =============================================================================
# 3. VALIDATION SUITE TESTS
# =============================================================================


class TestValidation:
    """Test deterministic response validation rules."""

    def test_valid_normal_year(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, hours_count=8760)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is True
        assert res.status == ChunkStatus.SUCCEEDED
        assert len(res.errors) == 0
        assert res.records_validated == 3 * 8760

    def test_valid_leap_year(self, sample_cells: list[GridCell]):
        chunk_leap = ExtractionChunk("era5_1992_batch_001", 1992, 1, sample_cells)
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(chunk_leap, hours_count=8784)
        res = validator.validate_chunk_response(chunk_leap, payload, http_status=200)

        assert res.is_valid is True
        assert res.status == ChunkStatus.SUCCEEDED
        assert res.records_validated == 3 * 8784

    def test_leap_year_hour_mismatch(self, sample_cells: list[GridCell]):
        chunk_leap = ExtractionChunk("era5_1992_batch_001", 1992, 1, sample_cells)
        validator = HistoricalChunkValidator()
        # Non-leap count (8760) provided for leap year 1992
        payload = create_mock_payload(chunk_leap, hours_count=8760)
        res = validator.validate_chunk_response(chunk_leap, payload, http_status=200)

        assert res.is_valid is False
        assert res.status == ChunkStatus.VALIDATION_FAILED
        assert any("Hourly count is 8760, expected 8784" in e for e in res.errors)

    def test_coordinate_mismatch(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk)
        # Shift coordinate beyond tolerance
        payload[0]["latitude"] = 15.00

        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)
        assert res.is_valid is False
        assert any("differ from requested" in e for e in res.errors)

    def test_duplicate_timestamps(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, duplicate_time=True)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is False
        assert any("Duplicate timestamps detected" in e for e in res.errors)

    def test_timestamp_progression_gap(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, time_gap=True)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is False
        assert any("Non-hourly gap" in e for e in res.errors)

    def test_null_value_detection(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, null_precip=True)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is False
        assert any("has 1 null values" in e for e in res.errors)
        assert res.null_counts["precipitation"] > 0

    def test_negative_precipitation_detection(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, negative_precip=True)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is False
        assert any("Negative precipitation detected" in e for e in res.errors)

    def test_invalid_relative_humidity_detection(self, sample_chunk: ExtractionChunk):
        validator = HistoricalChunkValidator()
        payload = create_mock_payload(sample_chunk, invalid_rh=True)
        res = validator.validate_chunk_response(sample_chunk, payload, http_status=200)

        assert res.is_valid is False
        assert any("Relative humidity out of bounds" in e for e in res.errors)


# =============================================================================
# 4. MANIFEST AND IDEMPOTENCY TESTS
# =============================================================================


class TestManifestAndIdempotency:
    """Test checkpoint manifest state transitions and hash-verified idempotency."""

    def test_manifest_lifecycle(self, temp_raw_dir: Path, sample_chunk: ExtractionChunk):
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)

        # 1. Register PENDING
        manifest.register_chunks([sample_chunk])
        chunk_data = manifest.get_chunk(sample_chunk.chunk_id)
        assert chunk_data["status"] == ChunkStatus.PENDING.value

        # 2. Transition RUNNING
        manifest.mark_running(sample_chunk.chunk_id)
        chunk_data = manifest.get_chunk(sample_chunk.chunk_id)
        assert chunk_data["status"] == ChunkStatus.RUNNING.value
        assert chunk_data["attempt_count"] == 1

        # 3. Create dummy file and transition SUCCEEDED
        dummy_file = temp_raw_dir / "batch_001.json.gz"
        with open(dummy_file, "wb") as f:
            f.write(b"MOCK_COMPRESSED_DATA")
        file_hash = hashlib.sha256(b"MOCK_COMPRESSED_DATA").hexdigest()

        val = ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED)
        manifest.mark_succeeded(
            sample_chunk.chunk_id,
            raw_path=str(dummy_file),
            payload_sha256="mock_raw_hash",
            compressed_sha256=file_hash,
            uncompressed_bytes=100,
            compressed_bytes=len(b"MOCK_COMPRESSED_DATA"),
            validation=val,
        )

        assert manifest.is_chunk_completed(sample_chunk.chunk_id) is True

    def test_corrupted_raw_file_detection(self, temp_raw_dir: Path, sample_chunk: ExtractionChunk):
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)
        dummy_file = temp_raw_dir / "batch_001.json.gz"

        with open(dummy_file, "wb") as f:
            f.write(b"ORIGINAL_DATA")
        original_hash = hashlib.sha256(b"ORIGINAL_DATA").hexdigest()

        val = ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED)
        manifest.mark_succeeded(
            sample_chunk.chunk_id,
            raw_path=str(dummy_file),
            payload_sha256="mock_raw_hash",
            compressed_sha256=original_hash,
            uncompressed_bytes=100,
            compressed_bytes=len(b"ORIGINAL_DATA"),
            validation=val,
        )

        assert manifest.is_chunk_completed(sample_chunk.chunk_id) is True

        # Corrupt file content on disk
        with open(dummy_file, "wb") as f:
            f.write(b"CORRUPTED_MODIFIED_DATA")

        # Must detect hash mismatch and return False
        assert manifest.is_chunk_completed(sample_chunk.chunk_id) is False

    def test_missing_raw_file_detection(self, temp_raw_dir: Path, sample_chunk: ExtractionChunk):
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)
        non_existent_file = temp_raw_dir / "does_not_exist.json.gz"

        val = ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED)
        manifest.mark_succeeded(
            sample_chunk.chunk_id,
            raw_path=str(non_existent_file),
            payload_sha256="mock_raw_hash",
            compressed_sha256="mock_comp_hash",
            uncompressed_bytes=100,
            compressed_bytes=50,
            validation=val,
        )

        assert manifest.is_chunk_completed(sample_chunk.chunk_id) is False

    def test_recover_stale_running_without_artifact_resets_to_pending(
        self, temp_raw_dir: Path, sample_chunk: ExtractionChunk
    ):
        """Stale RUNNING chunk with no artifact on disk is safely reset to PENDING."""
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)
        manifest.register_chunks([sample_chunk])
        manifest.mark_running(sample_chunk.chunk_id)

        assert manifest.get_chunk(sample_chunk.chunk_id)["status"] == ChunkStatus.RUNNING.value

        res = manifest.recover_stale_running_chunks(raw_base_dir=temp_raw_dir)
        assert sample_chunk.chunk_id in res["reset_to_pending"]
        assert sample_chunk.chunk_id not in res["reconciled_succeeded"]

        rec = manifest.get_chunk(sample_chunk.chunk_id)
        assert rec["status"] == ChunkStatus.PENDING.value
        assert rec["started_at"] is None

    def test_recover_stale_running_with_valid_artifact_reconciles_to_succeeded(
        self, temp_raw_dir: Path, sample_chunk: ExtractionChunk
    ):
        """Stale RUNNING chunk with a valid raw artifact on disk is reconciled to SUCCEEDED."""
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)
        manifest.register_chunks([sample_chunk])
        manifest.mark_running(sample_chunk.chunk_id)

        # Write valid compressed payload to expected location
        year_dir = temp_raw_dir / f"year={sample_chunk.year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / f"batch_{sample_chunk.batch_id:03d}.json.gz"

        payload = create_mock_payload(sample_chunk, hours_count=8760)
        raw_bytes = json.dumps(payload).encode("utf-8")
        comp_bytes = gzip.compress(raw_bytes)
        with open(raw_file, "wb") as f:
            f.write(comp_bytes)

        res = manifest.recover_stale_running_chunks(raw_base_dir=temp_raw_dir)
        assert sample_chunk.chunk_id in res["reconciled_succeeded"]

        rec = manifest.get_chunk(sample_chunk.chunk_id)
        assert rec["status"] == ChunkStatus.SUCCEEDED.value
        assert rec["raw_path"] == str(raw_file)
        assert rec["compressed_sha256"] == hashlib.sha256(comp_bytes).hexdigest()
        assert rec["payload_sha256"] == hashlib.sha256(raw_bytes).hexdigest()

    def test_recover_stale_running_with_corrupted_artifact_resets_to_pending(
        self, temp_raw_dir: Path, sample_chunk: ExtractionChunk
    ):
        """Stale RUNNING chunk with corrupted payload on disk is safely reset to PENDING."""
        manifest_path = temp_raw_dir / "manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)
        manifest.register_chunks([sample_chunk])
        manifest.mark_running(sample_chunk.chunk_id)

        year_dir = temp_raw_dir / f"year={sample_chunk.year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / f"batch_{sample_chunk.batch_id:03d}.json.gz"
        with open(raw_file, "wb") as f:
            f.write(b"CORRUPTED_NOT_A_GZIP_FILE")

        res = manifest.recover_stale_running_chunks(raw_base_dir=temp_raw_dir)
        assert sample_chunk.chunk_id in res["reset_to_pending"]
        assert manifest.get_chunk(sample_chunk.chunk_id)["status"] == ChunkStatus.PENDING.value


# =============================================================================
# 5. EXTRACTOR INTEGRATION TESTS (MOCKED HTTP)
# =============================================================================


class TestExtractorMocked:
    """Test full extraction orchestration with mocked HTTP client."""

    def test_extract_chunk_and_idempotency(self, temp_raw_dir: Path, sample_chunk: ExtractionChunk):
        mock_data = create_mock_payload(sample_chunk, hours_count=8760)
        mock_bytes = json.dumps(mock_data).encode("utf-8")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = mock_resp

        config = ExtractionConfig(
            raw_base_dir=temp_raw_dir,
            manifest_path=temp_raw_dir / "manifest.json",
            pacing_delay_seconds=0.0,
        )
        manifest = HistoricalExtractionManifest(config.manifest_path)
        client = HistoricalOpenMeteoClient(config=config, client=mock_http)
        validator = HistoricalChunkValidator(config)

        extractor = HistoricalExtractor(
            config=config,
            manifest=manifest,
            client=client,
            validator=validator,
        )

        # 1. First execution: extracts and saves
        res1 = extractor.extract_chunk(sample_chunk)
        assert res1.is_valid is True
        assert res1.status == ChunkStatus.SUCCEEDED
        assert mock_http.get.call_count == 1

        raw_file = temp_raw_dir / "year=1994" / "batch_001.json.gz"
        meta_file = temp_raw_dir / "year=1994" / "batch_001.meta.json"
        assert raw_file.exists()
        assert meta_file.exists()

        # Verify raw decompressed payload matches original bytes
        with gzip.open(raw_file, "rb") as f:
            decompressed = f.read()
        assert decompressed == mock_bytes

        # 2. Second execution: skips network call due to idempotency
        res2 = extractor.extract_chunk(sample_chunk)
        assert res2.is_valid is True
        assert res2.status == ChunkStatus.SUCCEEDED
        assert "already completed" in res2.warnings[0]
        # Call count must still be 1 (no second HTTP call)
        assert mock_http.get.call_count == 1

    def test_extract_chunk_429_safely_becomes_retryable_without_manifest_corruption(
        self, temp_raw_dir: Path, sample_chunk: ExtractionChunk
    ):
        """HTTP 429 exhaustion marks chunk RETRYABLE in manifest and preserves manifest validity."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.1"}

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = resp_429

        manifest_file = temp_raw_dir / "manifest.json"
        config = ExtractionConfig(
            raw_base_dir=temp_raw_dir,
            manifest_path=manifest_file,
            pacing_delay_seconds=0.0,
            rate_limit_max_retries=2,
        )
        manifest = HistoricalExtractionManifest(config.manifest_path)
        client = HistoricalOpenMeteoClient(config=config, client=mock_http)
        validator = HistoricalChunkValidator(config)

        extractor = HistoricalExtractor(
            config=config,
            manifest=manifest,
            client=client,
            validator=validator,
        )

        with patch("time.sleep"):
            res = extractor.extract_chunk(sample_chunk)

        assert res.is_valid is False
        assert res.status == ChunkStatus.RETRYABLE

        # Manifest must record chunk as RETRYABLE
        chunk_rec = manifest.get_chunk(sample_chunk.chunk_id)
        assert chunk_rec is not None
        assert chunk_rec["status"] == ChunkStatus.RETRYABLE.value
        assert "429" in chunk_rec["last_error"]

        # Manifest on disk must be valid JSON
        assert manifest_file.exists()
        with open(manifest_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert disk_data["chunks"][sample_chunk.chunk_id]["status"] == ChunkStatus.RETRYABLE.value

        # No raw files should have been written to disk
        raw_file = temp_raw_dir / f"year={sample_chunk.year}" / f"batch_{sample_chunk.batch_id:03d}.json.gz"
        assert not raw_file.exists()


# =============================================================================
# 6. CLI SAFETY GUARD TESTS
# =============================================================================


class TestCliSafetyGuards:
    """Test CLI argument validation and safety controls."""

    def test_cli_requires_scope(self):
        # Calling CLI without any scope flags must fail with exit code 1
        exit_code = run_cli([])
        assert exit_code == 1

    def test_cli_full_26_years_blocked_without_force(self):
        # Targeting 1969-1994 without limit or force flag must fail
        exit_code = run_cli(["--start-year", "1969", "--end-year", "1994"])
        assert exit_code == 1

    def test_cli_single_year_with_dry_run(self, temp_raw_dir: Path):
        # Targeting 1 year with dry run and limit=1 should succeed
        with patch.object(HistoricalExtractor, "extract_chunks") as mock_extract:
            mock_extract.return_value = {
                "total_processed": 1,
                "succeeded": 1,
                "failed": 0,
                "skipped": 0,
                "manifest_summary": {"SUCCEEDED": 1},
            }
            exit_code = run_cli(
                [
                    "--year", "1994",
                    "--batch", "1",
                    "--limit", "1",
                    "--dry-run",
                    "--manifest-path", str(temp_raw_dir / "manifest.json"),
                ]
            )
            assert exit_code == 0
            assert mock_extract.called

    def test_cli_pacing_wiring(self, temp_raw_dir: Path):
        """CLI --pacing flag defaults to 10.0 and wires to ExtractionConfig.min_request_interval_seconds."""
        from app.ingestion.historical.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["--year", "1994"])
        # Default is 10.0
        assert args.pacing == 10.0

        args_custom = parser.parse_args(["--year", "1994", "--pacing", "15.5"])
        assert args_custom.pacing == 15.5

        with patch("app.ingestion.historical.cli.HistoricalExtractor") as mock_extractor_cls:
            mock_inst = MagicMock()
            mock_inst.extract_chunks.return_value = {
                "total_processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "manifest_summary": {},
            }
            mock_extractor_cls.return_value = mock_inst

            exit_code = run_cli(
                [
                    "--year", "1994",
                    "--batch", "1",
                    "--limit", "1",
                    "--dry-run",
                    "--pacing", "12.0",
                    "--manifest-path", str(temp_raw_dir / "manifest.json"),
                ]
            )
            assert exit_code == 0
            cfg_used = mock_extractor_cls.call_args.kwargs["config"]
            assert cfg_used.min_request_interval_seconds == 12.0
            assert cfg_used.pacing_delay_seconds == 12.0
