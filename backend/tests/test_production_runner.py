"""
Unit tests for the production historical runner, inventory generator, and safety guards.

Covers:
1. Full 858 inventory generation
2. 324 unique grid cells
3. 33 batches
4. Batch sizes (10 × 32 + 4)
5. 26 years (1969–1994)
6. Exactly 858 chunks
7. Cached chunk detection
8. Missing chunk detection
9. Invalid cached chunk detection
10. Processing cache detection
11. Explicit production scope requirement
12. Dry-run makes no HTTP requests
13. Dry-run makes no database writes
14. Restart/resume logic
15. Missing-chunk reporting
"""

import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.ingestion.historical.daily_manifest import DailyProcessingManifest
from app.ingestion.historical.daily_models import DailyProcessingConfig
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import (
    generate_chunks,
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
from app.ingestion.historical.production_cli import run_cli
from app.ingestion.historical.production_runner import ProductionHistoricalRunner


@pytest.fixture
def temp_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Temporary directories for raw payloads and processed Parquet."""
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, processed_dir


# =============================================================================
# 1. INVENTORY GENERATION AND MATHEMATICAL PROPERTIES
# =============================================================================


class TestInventoryProperties:
    """Test full 858 chunk inventory generation and spatial invariants."""

    def test_324_unique_cells(self):
        """Test 2: Exactly 324 unique Karnataka cells."""
        cells = get_karnataka_grid()
        assert len(cells) == 324
        coords = [(c.lat, c.lon) for c in cells]
        assert len(set(coords)) == 324

    def test_33_batches(self):
        """Test 3: Exactly 33 spatial batches."""
        batches = get_spatial_batches(batch_size=10)
        assert len(batches) == 33

    def test_batch_sizes(self):
        """Test 4: Batch sizes are 10 for batches 1-32 and 4 for batch 33."""
        batches = get_spatial_batches(batch_size=10)
        for i in range(32):
            assert len(batches[i]) == 10
        assert len(batches[32]) == 4

    def test_26_years(self):
        """Test 5: 1969 to 1994 spans exactly 26 calendar years."""
        start_year, end_year = 1969, 1994
        years = list(range(start_year, end_year + 1))
        assert len(years) == 26
        assert years[0] == 1969
        assert years[-1] == 1994

    def test_exactly_858_chunks(self):
        """Test 1 & 6: Exactly 858 unique chunks are generated for 1969-1994."""
        chunks = generate_chunks(1969, 1994, batch_size=10)
        assert len(chunks) == 858
        chunk_ids = [c.chunk_id for c in chunks]
        assert len(set(chunk_ids)) == 858
        assert chunk_ids[0] == "era5_1969_batch_001"
        assert chunk_ids[-1] == "era5_1994_batch_033"


# =============================================================================
# 2. STATE DETECTION AND AUDITING TESTS
# =============================================================================


class TestStateDetection:
    """Test detection of cached, missing, and invalid chunks."""

    def _setup_chunk_on_disk(
        self,
        raw_dir: Path,
        year: int,
        batch_id: int,
        corrupt_hash: bool = False,
    ) -> tuple[str, str]:
        """Helper to create a raw chunk file and metadata."""
        year_dir = raw_dir / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / f"batch_{batch_id:03d}.json.gz"

        data = b'{"mock": "data"}'
        compressed = gzip.compress(data)
        actual_hash = hashlib.sha256(compressed).hexdigest()

        with open(raw_file, "wb") as f:
            f.write(compressed)

        stored_hash = "wrong_hash" if corrupt_hash else actual_hash
        return str(raw_file), stored_hash

    def test_cached_and_missing_chunk_detection(self, temp_dirs: tuple[Path, Path]):
        """Test 7 & 8: Runner detects valid cached chunks and missing chunks."""
        raw_dir, processed_dir = temp_dirs

        raw_manifest_path = raw_dir / "extraction_manifest.json"
        raw_manifest = HistoricalExtractionManifest(raw_manifest_path)

        # Setup 1 valid cached chunk: 1994 batch 1
        raw_path, hash_val = self._setup_chunk_on_disk(raw_dir, 1994, 1)
        raw_manifest.mark_succeeded(
            chunk_id="era5_1994_batch_001",
            raw_path=raw_path,
            payload_sha256="payload_hash",
            compressed_sha256=hash_val,
            uncompressed_bytes=100,
            compressed_bytes=len(gzip.compress(b'{"mock": "data"}')),
            validation=ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED),
        )

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir, manifest_path=raw_manifest_path),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extraction_manifest=raw_manifest,
        )

        audit = runner.audit_inventory(1994, 1994)
        assert "era5_1994_batch_001" in audit.valid_raw_chunks
        assert len(audit.valid_raw_chunks) == 1
        # 33 batches in 1994 -> 32 missing
        assert len(audit.missing_raw_chunks) == 32
        assert "era5_1994_batch_002" in audit.missing_raw_chunks

    def test_invalid_cached_chunk_detection(self, temp_dirs: tuple[Path, Path]):
        """Test 9: Runner flags chunks with corrupted disk files or hash mismatches as invalid."""
        raw_dir, processed_dir = temp_dirs

        raw_manifest_path = raw_dir / "extraction_manifest.json"
        raw_manifest = HistoricalExtractionManifest(raw_manifest_path)

        # Setup 1 chunk with corrupted hash
        raw_path, corrupt_hash = self._setup_chunk_on_disk(raw_dir, 1994, 1, corrupt_hash=True)
        raw_manifest.mark_succeeded(
            chunk_id="era5_1994_batch_001",
            raw_path=raw_path,
            payload_sha256="payload_hash",
            compressed_sha256=corrupt_hash,
            uncompressed_bytes=100,
            compressed_bytes=50,
            validation=ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED),
        )

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir, manifest_path=raw_manifest_path),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extraction_manifest=raw_manifest,
        )

        audit = runner.audit_inventory(1994, 1994)
        assert "era5_1994_batch_001" in audit.invalid_raw_chunks
        assert len(audit.valid_raw_chunks) == 0

    def test_processing_cache_detection(self, temp_dirs: tuple[Path, Path]):
        """Test 10: Runner detects existing daily processed Parquet files."""
        raw_dir, processed_dir = temp_dirs

        daily_manifest_path = processed_dir / "processing_manifest.json"
        daily_manifest = DailyProcessingManifest(daily_manifest_path)

        # Create a mock parquet file
        out_dir = processed_dir / "year=1994"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "batch_001.parquet"
        out_file.write_bytes(b"PAR1mock")

        daily_manifest.mark_succeeded(
            chunk_id="era5_1994_batch_001",
            output_path=str(out_file),
            output_record_count=3650,
            validation=MagicMock(records_validated=3650, cells_validated=10, complete_days=3650, incomplete_days=0),
            input_sha256="test_sha",
        )

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir),
            daily_config=DailyProcessingConfig(
                raw_base_dir=raw_dir,
                processed_base_dir=processed_dir,
                manifest_path=daily_manifest_path,
            ),
            daily_manifest=daily_manifest,
        )

        audit = runner.audit_inventory(1994, 1994)
        assert "era5_1994_batch_001" in audit.valid_processed_chunks
        assert len(audit.valid_processed_chunks) == 1
        assert len(audit.missing_processed_chunks) == 32

    def test_missing_chunk_reporting(self, temp_dirs: tuple[Path, Path]):
        """Test 15: Missing chunks are accurately reported in audit."""
        raw_dir, processed_dir = temp_dirs
        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(
                raw_base_dir=raw_dir,
                manifest_path=raw_dir / "extraction_manifest.json",
            ),
            daily_config=DailyProcessingConfig(
                raw_base_dir=raw_dir,
                processed_base_dir=processed_dir,
                manifest_path=processed_dir / "processing_manifest.json",
            ),
        )

        audit = runner.audit_inventory(1969, 1994)
        assert len(audit.missing_raw_chunks) == 858
        assert len(audit.missing_processed_chunks) == 858


# =============================================================================
# 3. SAFETY CONTROLS AND CLI TESTS
# =============================================================================


class TestSafetyControls:
    """Test safety guards, dry-run guarantees, and restart logic."""

    def test_explicit_production_scope_requirement(self):
        """Test 11: CLI rejects execution without explicit scope flags."""
        assert run_cli([]) == 1

    def test_dry_run_makes_no_http_or_db_writes(self, temp_dirs: tuple[Path, Path]):
        """Test 12 & 13: Dry-run performs zero HTTP requests and zero DB writes."""
        raw_dir, processed_dir = temp_dirs

        mock_client = MagicMock()
        mock_extractor = HistoricalExtractor(
            config=ExtractionConfig(raw_base_dir=raw_dir),
            client=mock_client,
        )

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extractor=mock_extractor,
        )

        res = runner.run_production(start_year=1994, end_year=1994, dry_run=True)
        assert res["dry_run"] is True
        assert res["api_requests_made"] == 0
        assert res["database_writes_made"] == 0
        mock_client.fetch_chunk_payload.assert_not_called()

    def test_restart_and_resume_logic(self, temp_dirs: tuple[Path, Path]):
        """Test 14: Runner skips already completed chunks during live execution."""
        raw_dir, processed_dir = temp_dirs

        # Create mock chunk
        chunk = ExtractionChunk(
            chunk_id="era5_1994_batch_001",
            year=1994,
            batch_id=1,
            cells=[GridCell(lat=14.25, lon=76.5)],
        )

        mock_extractor = MagicMock()
        mock_extractor.extract_chunk.return_value = ValidationResult(
            is_valid=True,
            status=ChunkStatus.SUCCEEDED,
            warnings=["Chunk era5_1994_batch_001 already completed on disk with verified hash; skipped."],
        )

        mock_processor = MagicMock()
        mock_processor.process_chunk.return_value = MagicMock(
            is_valid=True,
            warnings=["Chunk era5_1994_batch_001 already processed; skipped (cached)."],
        )

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extractor=mock_extractor,
            daily_processor=mock_processor,
        )

        res = runner.run_production(start_year=1994, end_year=1994, limit=1, dry_run=False)
        assert res["cached_extract_count"] == 1
        assert res["cached_process_count"] == 1
        assert res["extracted_count"] == 0
        assert res["processed_count"] == 0
