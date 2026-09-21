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

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.content = mock_bytes

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = [resp_429, resp_200]

        cfg = ExtractionConfig(max_retries=2)
        client = HistoricalOpenMeteoClient(config=cfg, client=mock_http)

        with patch("time.sleep") as mock_sleep:
            raw_b, parsed_j, status, lat = client.fetch_chunk_payload(sample_chunk)
            assert status == 200
            assert mock_sleep.called

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
