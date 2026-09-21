"""
Unit tests for the historical meteorological daily processing and aggregation engine.

Covers:
1. 24-hour complete day
2. Incomplete day (hour_count < 24)
3. Precipitation sum (not average)
4. Temperature mean/min/max
5. RH mean
6. Pressure mean
7. Leap day (Feb 29 in leap years 1980, 1988)
8. Non-leap year (no Feb 29 in 1994, 1979)
9. Zero precipitation vs missing/incomplete distinction
10. Duplicate date detection
11. Coordinate preservation (±0.0001°)
12. Provenance tracking
13. Checksum-based cache / idempotency
14. Changed-input reprocessing
15. Deterministic aggregation
16. Invalid physical values rejection
17. Multiple grid cells
18. Year partitioning and Parquet readability
"""

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import pytest
import pyarrow.parquet as pq

from app.ingestion.historical.daily_aggregator import DailyAggregator
from app.ingestion.historical.daily_manifest import DailyProcessingManifest
from app.ingestion.historical.daily_models import (
    DailyProcessingConfig,
    DailyProcessingStatus,
    DailyQualityStatus,
    DailyRecord,
)
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.daily_validator import DailyDatasetValidator
from app.ingestion.historical.models import GridCell


@pytest.fixture
def temp_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Provide temporary directories for raw input and processed output."""
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, processed_dir


@pytest.fixture
def sample_cell() -> GridCell:
    """Sample grid cell in Karnataka."""
    return GridCell(lat=14.25, lon=76.5, center_inside=True, name="Chitradurga")


def create_hourly_payload(
    year: int,
    cells: list[GridCell],
    precip_val: float = 1.0,
    temp_vals: list[float] | None = None,
    rh_val: float = 70.0,
    pressure_val: float = 950.0,
    drop_hours: int = 0,
) -> list[dict]:
    """Helper to generate mock raw hourly Open-Meteo payloads for a year."""
    import calendar

    is_leap = calendar.isleap(year)
    total_hours = 8784 if is_leap else 8760
    start_dt = datetime(year, 1, 1, 0, 0, tzinfo=timezone.utc)

    loc_list = []
    for cell in cells:
        times = [(start_dt + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(total_hours - drop_hours)]
        n = len(times)

        if temp_vals is None:
            temps = [25.0] * n
        else:
            temps = (temp_vals * (n // len(temp_vals) + 1))[:n]

        loc_list.append(
            {
                "latitude": cell.lat,
                "longitude": cell.lon,
                "elevation": 500.0,
                "hourly": {
                    "time": times,
                    "precipitation": [precip_val] * n,
                    "temperature_2m": temps,
                    "relative_humidity_2m": [rh_val] * n,
                    "surface_pressure": [pressure_val] * n,
                },
            }
        )
    return loc_list


# =============================================================================
# 1. AGGREGATION FORMULAS AND COMPLETENESS TESTS
# =============================================================================


class TestDailyAggregation:
    """Test daily aggregation formulas and completeness semantics."""

    def test_complete_24h_day(self, sample_cell: GridCell):
        """Test 1: 24-hour complete day produces COMPLETE status."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell], precip_val=0.5)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        assert len(records) == 365
        for r in records:
            assert r.hour_count == 24
            assert r.quality_status == DailyQualityStatus.COMPLETE.value

    def test_incomplete_day(self, sample_cell: GridCell):
        """Test 2: Incomplete day with missing hours produces INCOMPLETE status."""
        aggregator = DailyAggregator()
        # Drop 5 hours from the year
        payload = create_hourly_payload(1994, [sample_cell], drop_hours=5)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        # The last day (1994-12-31) has only 19 hours
        last_day = records[-1]
        assert last_day.date == "1994-12-31"
        assert last_day.hour_count == 19
        assert last_day.quality_status == DailyQualityStatus.INCOMPLETE.value

    def test_precipitation_sum(self, sample_cell: GridCell):
        """Test 3: Daily precipitation is sum of hourly values, NOT average."""
        aggregator = DailyAggregator()
        # 1.5 mm per hour for 24 hours = 36.0 mm daily
        payload = create_hourly_payload(1994, [sample_cell], precip_val=1.5)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.precipitation_total_mm == pytest.approx(36.0, rel=1e-3)

    def test_temperature_mean_min_max(self, sample_cell: GridCell):
        """Test 4: Daily temperature correctly computes mean, min, and max."""
        aggregator = DailyAggregator()
        # Hourly temperatures cycling 20.0, 25.0, 30.0
        payload = create_hourly_payload(1994, [sample_cell], temp_vals=[20.0, 25.0, 30.0])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.temperature_min_c == 20.0
            assert r.temperature_max_c == 30.0
            assert r.temperature_mean_c == pytest.approx(25.0, rel=1e-3)

    def test_rh_mean(self, sample_cell: GridCell):
        """Test 5: Daily RH is arithmetic mean."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell], rh_val=75.5)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.relative_humidity_mean_pct == 75.5

    def test_pressure_mean(self, sample_cell: GridCell):
        """Test 6: Daily surface pressure is arithmetic mean."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell], pressure_val=945.2)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.surface_pressure_mean_hpa == 945.2

    def test_zero_precipitation_vs_missing(self, sample_cell: GridCell):
        """Test 9: 0.0 mm precipitation is a valid dry day (COMPLETE), distinct from missing."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell], precip_val=0.0)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.precipitation_total_mm == 0.0
            assert r.hour_count == 24
            assert r.quality_status == DailyQualityStatus.COMPLETE.value


# =============================================================================
# 2. CALENDAR AND LEAP YEAR TESTS
# =============================================================================


class TestCalendarAndLeapYears:
    """Test calendar continuity and leap-year handling."""

    def test_leap_year_1988(self, sample_cell: GridCell):
        """Test 7: Leap year 1988 contains Feb 29 and produces 366 daily records."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1988, [sample_cell])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1988_batch_001", "sha123")

        assert len(records) == 366
        dates = [r.date for r in records]
        assert "1988-02-29" in dates
        assert dates.count("1988-02-29") == 1

        validator = DailyDatasetValidator()
        val_res = validator.validate_daily_records(records, expected_year=1988, expected_cells=[sample_cell])
        assert val_res.is_valid

    def test_non_leap_year_1994(self, sample_cell: GridCell):
        """Test 8: Non-leap year 1994 produces 365 daily records and no Feb 29."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        assert len(records) == 365
        dates = [r.date for r in records]
        assert "1994-02-29" not in dates

        validator = DailyDatasetValidator()
        val_res = validator.validate_daily_records(records, expected_year=1994, expected_cells=[sample_cell])
        assert val_res.is_valid

    def test_duplicate_date_detection(self, sample_cell: GridCell):
        """Test 10: Validator detects and rejects duplicate dates."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        # Duplicate the first record
        records_with_dup = list(records) + [records[0]]

        validator = DailyDatasetValidator()
        val_res = validator.validate_daily_records(records_with_dup, expected_year=1994, expected_cells=[sample_cell])
        assert not val_res.is_valid
        assert any("Duplicate" in e for e in val_res.errors)


# =============================================================================
# 3. SPATIAL, PROVENANCE, AND PHYSICAL INTEGRITY TESTS
# =============================================================================


class TestIntegrityAndProvenance:
    """Test spatial identity, provenance, and physical value constraints."""

    def test_coordinate_preservation(self, sample_cell: GridCell):
        """Test 11: Exact grid coordinates are preserved without alteration."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        for r in records:
            assert r.latitude == sample_cell.lat
            assert r.longitude == sample_cell.lon

    def test_provenance_metadata(self, sample_cell: GridCell):
        """Test 12: Provenance metadata fields are populated in all records."""
        aggregator = DailyAggregator(processing_version="1.0")
        payload = create_hourly_payload(1994, [sample_cell])
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha_test_456")

        for r in records:
            assert r.source == "Open-Meteo Historical Weather API"
            assert r.dataset_model == "ERA5"
            assert r.raw_chunk_id == "era5_1994_batch_001"
            assert r.raw_payload_sha256 == "sha_test_456"
            assert r.processing_version == "1.0"

    def test_deterministic_aggregation(self, sample_cell: GridCell):
        """Test 15: Repeated aggregation of identical input produces identical daily records."""
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, [sample_cell])
        records1 = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")
        records2 = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        assert len(records1) == len(records2)
        for r1, r2 in zip(records1, records2):
            assert r1 == r2

    def test_invalid_physical_values(self, sample_cell: GridCell):
        """Test 16: Validator rejects negative precipitation and out-of-bounds RH."""
        validator = DailyDatasetValidator()

        # Negative precipitation
        rec_neg_precip = DailyRecord(
            date="1994-01-01",
            latitude=sample_cell.lat,
            longitude=sample_cell.lon,
            precipitation_total_mm=-1.0,
            temperature_mean_c=25.0,
            temperature_min_c=20.0,
            temperature_max_c=30.0,
            relative_humidity_mean_pct=50.0,
            surface_pressure_mean_hpa=950.0,
            hour_count=24,
            quality_status=DailyQualityStatus.COMPLETE.value,
        )
        res1 = validator.validate_daily_records([rec_neg_precip], expected_year=1994)
        assert not res1.is_valid
        assert any("Negative precipitation" in e for e in res1.errors)

        # RH > 100
        rec_high_rh = DailyRecord(
            date="1994-01-01",
            latitude=sample_cell.lat,
            longitude=sample_cell.lon,
            precipitation_total_mm=0.0,
            temperature_mean_c=25.0,
            temperature_min_c=20.0,
            temperature_max_c=30.0,
            relative_humidity_mean_pct=110.0,
            surface_pressure_mean_hpa=950.0,
            hour_count=24,
            quality_status=DailyQualityStatus.COMPLETE.value,
        )
        res2 = validator.validate_daily_records([rec_high_rh], expected_year=1994)
        assert not res2.is_valid
        assert any("RH out of range" in e for e in res2.errors)

    def test_multiple_grid_cells(self):
        """Test 17: Aggregating multiple cells produces expected record count and sorted ordering."""
        cells = [
            GridCell(lat=14.25, lon=76.5, center_inside=True),
            GridCell(lat=13.25, lon=74.75, center_inside=True),
        ]
        aggregator = DailyAggregator()
        payload = create_hourly_payload(1994, cells)
        records = aggregator.aggregate_chunk_payload(payload, "era5_1994_batch_001", "sha123")

        # 2 cells * 365 = 730 records
        assert len(records) == 730
        # Check sorting: latitude ascending first
        assert records[0].latitude == 13.25
        assert records[-1].latitude == 14.25


# =============================================================================
# 4. PROCESSOR, PARQUET, AND MANIFEST CACHE TESTS
# =============================================================================


class TestProcessorAndParquet:
    """Test full processing pipeline, Parquet partitioning, and manifest caching."""

    def _setup_mock_raw_chunk(
        self,
        raw_dir: Path,
        year: int,
        batch_id: int,
        cells: list[GridCell],
        payload: list[dict],
    ) -> tuple[str, str]:
        """Helper to write raw mock .json.gz and .meta.json."""
        year_dir = raw_dir / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / f"batch_{batch_id:03d}.json.gz"
        meta_file = year_dir / f"batch_{batch_id:03d}.meta.json"

        raw_bytes = json.dumps(payload).encode("utf-8")
        payload_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        compressed_bytes = gzip.compress(raw_bytes)
        compressed_sha256 = hashlib.sha256(compressed_bytes).hexdigest()

        with open(raw_file, "wb") as f:
            f.write(compressed_bytes)

        metadata = {
            "chunk_id": f"era5_{year}_batch_{batch_id:03d}",
            "year": year,
            "batch_id": batch_id,
            "payload_sha256": payload_sha256,
            "compressed_sha256": compressed_sha256,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f)

        return payload_sha256, compressed_sha256

    def test_parquet_partitioning_and_readability(self, temp_dirs: tuple[Path, Path], sample_cell: GridCell):
        """Test 18: Parquet file is written in year=YYYY partition and readable by pyarrow."""
        raw_dir, processed_dir = temp_dirs
        payload = create_hourly_payload(1994, [sample_cell])
        self._setup_mock_raw_chunk(raw_dir, 1994, 1, [sample_cell], payload)

        config = DailyProcessingConfig(
            raw_base_dir=raw_dir,
            processed_base_dir=processed_dir,
            manifest_path=processed_dir / "processing_manifest.json",
        )
        processor = DailyProcessor(config=config)
        res = processor.process_chunk(year=1994, batch_id=1, cells=[sample_cell])

        assert res.is_valid
        expected_parquet = processed_dir / "year=1994" / "batch_001.parquet"
        assert expected_parquet.exists()

        # Read back table with pyarrow
        table = pq.read_table(expected_parquet)
        assert table.num_rows == 365
        assert "precipitation_total_mm" in table.column_names
        assert "quality_status" in table.column_names
        # Check metadata
        assert b"ERA5" in table.schema.metadata.get(b"dataset_model", b"")

    def test_checksum_based_cache(self, temp_dirs: tuple[Path, Path], sample_cell: GridCell):
        """Test 13: Reprocessing the same chunk skips without re-running aggregation."""
        raw_dir, processed_dir = temp_dirs
        payload = create_hourly_payload(1994, [sample_cell])
        self._setup_mock_raw_chunk(raw_dir, 1994, 1, [sample_cell], payload)

        config = DailyProcessingConfig(
            raw_base_dir=raw_dir,
            processed_base_dir=processed_dir,
            manifest_path=processed_dir / "processing_manifest.json",
        )
        processor = DailyProcessor(config=config)

        # First run: process
        res1 = processor.process_chunk(year=1994, batch_id=1, cells=[sample_cell])
        assert res1.is_valid
        assert len(res1.warnings) == 0

        # Second run: cache hit
        res2 = processor.process_chunk(year=1994, batch_id=1, cells=[sample_cell])
        assert res2.is_valid
        assert any("skipped (cached)" in w.lower() for w in res2.warnings)

    def test_changed_input_reprocessing(self, temp_dirs: tuple[Path, Path], sample_cell: GridCell):
        """Test 14: When raw file checksum changes, chunk is reprocessed."""
        raw_dir, processed_dir = temp_dirs
        payload1 = create_hourly_payload(1994, [sample_cell], precip_val=1.0)
        self._setup_mock_raw_chunk(raw_dir, 1994, 1, [sample_cell], payload1)

        config = DailyProcessingConfig(
            raw_base_dir=raw_dir,
            processed_base_dir=processed_dir,
            manifest_path=processed_dir / "processing_manifest.json",
        )
        processor = DailyProcessor(config=config)

        # First run
        res1 = processor.process_chunk(year=1994, batch_id=1, cells=[sample_cell])
        assert res1.is_valid
        table1 = pq.read_table(processed_dir / "year=1994" / "batch_001.parquet")
        assert table1.column("precipitation_total_mm")[0].as_py() == pytest.approx(24.0, rel=1e-3)

        # Change raw input (e.g. precip = 2.0)
        payload2 = create_hourly_payload(1994, [sample_cell], precip_val=2.0)
        self._setup_mock_raw_chunk(raw_dir, 1994, 1, [sample_cell], payload2)

        # Second run: must reprocess
        res2 = processor.process_chunk(year=1994, batch_id=1, cells=[sample_cell])
        assert res2.is_valid
        assert len(res2.warnings) == 0
        table2 = pq.read_table(processed_dir / "year=1994" / "batch_001.parquet")
        assert table2.column("precipitation_total_mm")[0].as_py() == pytest.approx(48.0, rel=1e-3)


class TestDailyManifestRecovery:
    """Focused tests for DailyProcessingManifest.recover_stale_running_chunks()."""

    def _setup_processed_chunk(
        self,
        raw_dir: Path,
        processed_dir: Path,
        year: int,
        batch_id: int,
        cells: list[GridCell] | None = None,
    ) -> tuple[str, DailyProcessor]:
        """Helper to create a valid processed chunk and return chunk_id and processor."""
        if cells is None:
            from app.ingestion.historical.grid import get_spatial_batches

            batches = get_spatial_batches(batch_size=10, eligible_only=True)
            cells = batches[batch_id - 1]

        payload = create_hourly_payload(year, cells)
        year_dir = raw_dir / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / f"batch_{batch_id:03d}.json.gz"
        raw_bytes = json.dumps(payload).encode("utf-8")
        payload_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        with open(raw_file, "wb") as f:
            f.write(gzip.compress(raw_bytes))

        config = DailyProcessingConfig(
            raw_base_dir=raw_dir,
            processed_base_dir=processed_dir,
            manifest_path=processed_dir / "processing_manifest.json",
        )
        processor = DailyProcessor(config=config)
        res = processor.process_chunk(year=year, batch_id=batch_id, cells=cells)
        assert res.is_valid

        chunk_id = f"era5_{year}_batch_{batch_id:03d}"
        return chunk_id, processor

    def test_recover_valid_artifact_reconciles_to_succeeded(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Valid artifact with matching output checksum and metadata reconciles to SUCCEEDED."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        # Simulate interruption while RUNNING
        manifest.mark_running(chunk_id)
        parquet_file = processed_dir / "year=1994" / "batch_001.parquet"
        out_sha = hashlib.sha256(parquet_file.read_bytes()).hexdigest()
        manifest.get_chunk(chunk_id)["output_sha256"] = out_sha
        manifest.save()

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reconciled_succeeded"]
        assert chunk_id not in res["reset_to_pending"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.SUCCEEDED.value
        assert rec["last_error"] is None

    def test_recover_corrupted_parquet_resets_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Corrupted/unreadable Parquet file safely resets stale RUNNING chunk to PENDING."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        manifest.mark_running(chunk_id)
        parquet_file = processed_dir / "year=1994" / "batch_001.parquet"
        with open(parquet_file, "wb") as f:
            f.write(b"CORRUPTED_PARQUET_FILE_DATA")

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reset_to_pending"]
        assert chunk_id not in res["reconciled_succeeded"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert rec["started_at"] is None
        assert "unreadable or corrupted" in rec["last_error"]

    def test_recover_row_count_mismatch_resets_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Row-count mismatch between Parquet file and manifest safely resets chunk to PENDING."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        manifest.mark_running(chunk_id)
        rec = manifest.get_chunk(chunk_id)
        rec["output_record_count"] = 9999  # Actual is 3650
        manifest.save()

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reset_to_pending"]
        assert chunk_id not in res["reconciled_succeeded"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert "Row count mismatch" in rec["last_error"]

    def test_recover_source_checksum_mismatch_resets_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Mismatch between source raw artifact and recorded input_sha256 resets chunk to PENDING."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        manifest.mark_running(chunk_id)
        rec = manifest.get_chunk(chunk_id)
        rec["input_sha256"] = "f" * 64  # Mismatch actual raw file
        manifest.save()

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reset_to_pending"]
        assert chunk_id not in res["reconciled_succeeded"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert "Source raw payload SHA-256 mismatch" in rec["last_error"]

    def test_recover_valid_legacy_record_without_output_checksum(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Legacy record without output checksum is safely reconciled if all other validations pass."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        manifest.mark_running(chunk_id)
        rec = manifest.get_chunk(chunk_id)
        # Ensure no output checksum exists (legacy format)
        rec.pop("output_sha256", None)
        rec.pop("output_checksum", None)
        manifest.save()

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reconciled_succeeded"]
        assert chunk_id not in res["reset_to_pending"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.SUCCEEDED.value
        # Confirm no checksum was fabricated into the record
        assert "output_sha256" not in rec
        assert "output_checksum" not in rec

    def test_recover_output_checksum_mismatch_resets_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Mismatch on recorded output checksum resets chunk to PENDING."""
        raw_dir, processed_dir = temp_dirs
        chunk_id, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 1)
        manifest = processor.manifest

        manifest.mark_running(chunk_id)
        rec = manifest.get_chunk(chunk_id)
        rec["output_sha256"] = "0" * 64
        manifest.save()

        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )
        assert chunk_id in res["reset_to_pending"]

        rec = manifest.get_chunk(chunk_id)
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert "Output checksum mismatch" in rec["last_error"]

    def test_recover_cross_batch_coordinates_mismatch_resets_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Parquet containing valid ERA5 coordinates from a different batch resets chunk to PENDING."""
        import shutil
        from app.ingestion.historical.grid import get_spatial_batches

        batches = get_spatial_batches(batch_size=10, eligible_only=True)
        batch_1_cells = batches[0]  # Canonical batch 1
        batch_2_cells = batches[1]  # Canonical batch 2

        raw_dir, processed_dir = temp_dirs

        # Create a valid daily Parquet artifact containing Batch 2 coordinates
        _, processor = self._setup_processed_chunk(raw_dir, processed_dir, 1994, 2, batch_2_cells)

        actual_parquet = processed_dir / "year=1994" / "batch_002.parquet"
        target_parquet_1 = processed_dir / "year=1994" / "batch_001.parquet"
        shutil.copyfile(actual_parquet, target_parquet_1)

        # Make the manifest identify it as batch 1, marked RUNNING
        manifest = processor.manifest
        b1_cell_ids = [c.cell_id for c in batch_1_cells]
        b1_fp = hashlib.sha256(",".join(sorted(b1_cell_ids)).encode("utf-8")).hexdigest()[:8]

        manifest.register_chunk(
            chunk_id="era5_1994_batch_001",
            year=1994,
            batch_id=1,
            source_raw_path=str(raw_dir / "year=1994" / "batch_001.json.gz"),
            input_sha256="dummy_sha",
            cell_ids=b1_cell_ids,
            spatial_fingerprint=b1_fp,
        )
        manifest.mark_running("era5_1994_batch_001")
        rec = manifest.get_chunk("era5_1994_batch_001")
        rec["output_path"] = str(target_parquet_1)
        manifest.save()

        # Run recovery
        res = manifest.recover_stale_running_chunks(
            processed_base_dir=processed_dir, raw_base_dir=raw_dir
        )

        assert "era5_1994_batch_001" in res["reset_to_pending"]
        assert "era5_1994_batch_001" not in res["reconciled_succeeded"]

        rec = manifest.get_chunk("era5_1994_batch_001")
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert rec["started_at"] is None

        # Verify failure reason identifies spatial / cell / fingerprint mismatch
        err_msg = rec["last_error"].lower()
        assert any(term in err_msg for term in ["spatial", "cell", "fingerprint"])
