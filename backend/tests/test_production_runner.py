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
from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyProcessingStatus
from app.ingestion.historical.daily_processor import DailyProcessor
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
    """Test 832/858 chunk inventory generation and spatial invariants."""

    def test_324_authoritative_cells(self):
        """Authoritative Karnataka grid contains exactly 324 unique cells."""
        cells = get_karnataka_grid()
        assert len(cells) == 324
        coords = [(c.lat, c.lon) for c in cells]
        assert len(set(coords)) == 324

    def test_318_eligible_cells(self):
        """Extraction-eligible grid contains exactly 318 cells."""
        eligible = get_era5_eligible_grid()
        assert len(eligible) == 318
        coords = [(c.lat, c.lon) for c in eligible]
        assert len(set(coords)) == 318

    def test_6_excluded_cells(self):
        """Exactly 6 offshore boundary cells are excluded with reason."""
        excluded = get_era5_excluded_cells()
        assert len(excluded) == 6
        assert {c.cell_id for c in excluded} == ERA5_EXCLUDED_CELL_IDS
        assert "snaps requested offshore coordinate" in ERA5_EXCLUSION_REASON

    def test_33_batches_eligible(self):
        """Eligible grid produces exactly 33 permanent batches with in-batch exclusions (318 cells)."""
        batches = get_spatial_batches(batch_size=10, eligible_only=True)
        assert len(batches) == 33
        # 26 batches of 10, 6 of 9, 1 of 4
        assert sum(len(b) for b in batches) == 318
        nine_cell_batches = [idx for idx, b in enumerate(batches, start=1) if len(b) == 9]
        assert nine_cell_batches == [4, 11, 12, 15, 16, 18]
        assert len(batches[32]) == 4

    def test_33_batches_all(self):
        """Authoritative grid produces exactly 33 batches: 32 of 10 and 1 of 4 (324 cells)."""
        batches = get_spatial_batches(batch_size=10, eligible_only=False)
        assert len(batches) == 33
        for i in range(32):
            assert len(batches[i]) == 10
        assert len(batches[32]) == 4
        assert sum(len(b) for b in batches) == 324

    def test_26_years(self):
        """1969 to 1994 spans exactly 26 calendar years."""
        start_year, end_year = 1969, 1994
        years = list(range(start_year, end_year + 1))
        assert len(years) == 26
        assert years[0] == 1969
        assert years[-1] == 1994

    def test_exactly_858_production_chunks(self):
        """Eligible grid generates exactly 858 unique production chunks for 1969-1994 (26 * 33)."""
        chunks = generate_chunks(1969, 1994, batch_size=10, eligible_only=True)
        assert len(chunks) == 858
        chunk_ids = [c.chunk_id for c in chunks]
        assert len(set(chunk_ids)) == 858
        assert chunk_ids[0] == "era5_1969_batch_001"
        assert chunk_ids[-1] == "era5_1994_batch_033"

    def test_exactly_858_authoritative_chunks(self):
        """Authoritative grid generates exactly 858 chunks for 1969-1994 (26 * 33)."""
        chunks = generate_chunks(1969, 1994, batch_size=10, eligible_only=False)
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
        chunks_1994 = generate_chunks(1994, 1994, batch_size=10, eligible_only=True)
        raw_manifest.register_chunks(chunks_1994)

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
        # 33 batches in 1994 eligible grid -> 32 missing
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

    def test_spatial_fingerprint_mismatch_detection(self, temp_dirs: tuple[Path, Path]):
        """Runner flags chunks with mismatched spatial fingerprints as invalid."""
        raw_dir, processed_dir = temp_dirs

        raw_manifest_path = raw_dir / "extraction_manifest.json"
        raw_manifest = HistoricalExtractionManifest(raw_manifest_path)

        raw_path, valid_hash = self._setup_chunk_on_disk(raw_dir, 1994, 1)
        raw_manifest.mark_succeeded(
            chunk_id="era5_1994_batch_001",
            raw_path=raw_path,
            payload_sha256="payload_hash",
            compressed_sha256=valid_hash,
            uncompressed_bytes=100,
            compressed_bytes=50,
            validation=ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED),
        )
        # Artificially set an incorrect spatial fingerprint
        raw_manifest._data["chunks"]["era5_1994_batch_001"]["spatial_fingerprint"] = "bad_fp00"

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
        """Test 15: Missing chunks are accurately reported in audit (858 chunks across 1969-1994)."""
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

    def test_batch_coordinate_stability_across_all_batches(self):
        """Permanent 33-batch partitioning guarantees zero coordinate drift for subsequent batches."""
        auth_batches = get_spatial_batches(batch_size=10, eligible_only=False)
        elig_batches = get_spatial_batches(batch_size=10, eligible_only=True)

        assert len(auth_batches) == len(elig_batches) == 33

        # Batches 1, 2, 3 have 10 identical cells
        for b in [0, 1, 2]:
            assert [c.cell_id for c in auth_batches[b]] == [c.cell_id for c in elig_batches[b]]

        # Batch 4: eligible has 9 cells (omits index 9: ERA5_1275_07475)
        assert len(auth_batches[3]) == 10
        assert len(elig_batches[3]) == 9
        assert "ERA5_1275_07475" not in [c.cell_id for c in elig_batches[3]]

        # Crucial invariant: Batch 5 does NOT shift! It has the exact same 10 cells as authoritative Batch 5
        assert [c.cell_id for c in auth_batches[4]] == [c.cell_id for c in elig_batches[4]]
        assert [c.cell_id for c in auth_batches[5]] == [c.cell_id for c in elig_batches[5]]
        assert [c.cell_id for c in auth_batches[6]] == [c.cell_id for c in elig_batches[6]]


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

    def test_resume_failed_chunk_updates_spatial_metadata_and_fingerprint(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Verify that re-registering and extracting a previously failed chunk updates its spatial fingerprint."""
        raw_dir, processed_dir = temp_dirs
        manifest_path = raw_dir / "extraction_manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)

        # Chunk starts with old 10-cell failed definition
        old_chunk = ExtractionChunk(
            chunk_id="era5_1969_batch_004",
            year=1969,
            batch_id=4,
            cells=[GridCell(lat=12.5, lon=75.75 + i * 0.25) for i in range(10)],
        )
        manifest.register_chunks([old_chunk])
        manifest.mark_failed("era5_1969_batch_004", "Snapping error", ChunkStatus.VALIDATION_FAILED)

        entry = manifest.get_chunk("era5_1969_batch_004")
        assert entry["status"] == ChunkStatus.VALIDATION_FAILED.value
        assert entry["locations_count"] == 10
        old_fp = entry["spatial_fingerprint"]

        # New chunk definition has 9 eligible cells
        new_cells = [GridCell(lat=12.5, lon=75.75 + i * 0.25) for i in range(9)]
        new_chunk = ExtractionChunk(
            chunk_id="era5_1969_batch_004",
            year=1969,
            batch_id=4,
            cells=new_cells,
        )

        # Re-registering updates the pending/failed record's spatial definition
        manifest.register_chunks([new_chunk])
        updated_entry = manifest.get_chunk("era5_1969_batch_004")
        assert updated_entry["locations_count"] == 9
        assert updated_entry["spatial_fingerprint"] != old_fp
        assert updated_entry["spatial_fingerprint"] == new_chunk.spatial_fingerprint

        # Marking succeeded also records the new chunk metadata
        manifest.mark_succeeded(
            chunk_id="era5_1969_batch_004",
            raw_path="/fake/path",
            payload_sha256="hash1",
            compressed_sha256="hash2",
            uncompressed_bytes=1000,
            compressed_bytes=200,
            validation=ValidationResult(is_valid=True, status=ChunkStatus.SUCCEEDED),
            chunk=new_chunk,
        )
        final_entry = manifest.get_chunk("era5_1969_batch_004")
        assert final_entry["status"] == ChunkStatus.SUCCEEDED.value
        assert final_entry["spatial_fingerprint"] == new_chunk.spatial_fingerprint
        assert len(final_entry["cell_ids"]) == 9

    def test_runner_startup_recovers_stale_running_chunk_to_pending(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Production runner startup recovers stale RUNNING chunks without artifacts to PENDING."""
        raw_dir, processed_dir = temp_dirs
        manifest_path = raw_dir / "extraction_manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)

        chunk = ExtractionChunk(
            chunk_id="era5_1970_batch_030",
            year=1970,
            batch_id=30,
            cells=[GridCell(lat=14.0, lon=75.0)],
        )
        manifest.register_chunks([chunk])
        manifest.mark_running("era5_1970_batch_030")

        assert manifest.get_chunk("era5_1970_batch_030")["status"] == ChunkStatus.RUNNING.value

        # Starting runner must automatically recover the stale RUNNING chunk to PENDING
        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir, manifest_path=manifest_path),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extraction_manifest=manifest,
        )

        rec = runner.extraction_manifest.get_chunk("era5_1970_batch_030")
        assert rec["status"] == ChunkStatus.PENDING.value
        assert rec["started_at"] is None

        # Preflight audit reports it in missing_raw_chunks, ready for extraction
        audit = runner.audit_inventory(1970, 1970)
        assert "era5_1970_batch_030" in audit.missing_raw_chunks

    def test_runner_startup_reconciles_valid_running_chunk_to_succeeded(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Production runner startup reconciles stale RUNNING chunk with valid artifact to SUCCEEDED."""
        import gzip
        from tests.test_historical_extraction import create_mock_payload

        raw_dir, processed_dir = temp_dirs
        manifest_path = raw_dir / "extraction_manifest.json"
        manifest = HistoricalExtractionManifest(manifest_path)

        from app.ingestion.historical.grid import get_spatial_batches
        batches = get_spatial_batches(batch_size=10, eligible_only=True)
        cells = batches[29]
        chunk = ExtractionChunk(
            chunk_id="era5_1970_batch_030",
            year=1970,
            batch_id=30,
            cells=cells,
        )
        manifest.register_chunks([chunk])
        manifest.mark_running("era5_1970_batch_030")

        # Write valid raw file to disk
        year_dir = raw_dir / "year=1970"
        year_dir.mkdir(parents=True, exist_ok=True)
        raw_file = year_dir / "batch_030.json.gz"

        payload = create_mock_payload(chunk, hours_count=8760)
        raw_bytes = json.dumps(payload).encode("utf-8")
        comp_bytes = gzip.compress(raw_bytes)
        with open(raw_file, "wb") as f:
            f.write(comp_bytes)

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir, manifest_path=manifest_path),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir),
            extraction_manifest=manifest,
        )

        rec = runner.extraction_manifest.get_chunk("era5_1970_batch_030")
        assert rec["status"] == ChunkStatus.SUCCEEDED.value
        assert rec["raw_path"] == str(raw_file)

        audit = runner.audit_inventory(1970, 1970)
        assert "era5_1970_batch_030" in audit.valid_raw_chunks

    def test_runner_startup_recovers_stale_daily_running_chunk(
        self, temp_dirs: tuple[Path, Path]
    ):
        """Production runner startup recovers stale RUNNING daily chunk to PENDING if invalid."""
        raw_dir, processed_dir = temp_dirs
        ext_manifest_path = raw_dir / "extraction_manifest.json"
        daily_manifest_path = processed_dir / "processing_manifest.json"

        daily_manifest = DailyProcessingManifest(daily_manifest_path)
        daily_manifest.register_chunk(
            chunk_id="era5_1970_batch_030",
            year=1970,
            batch_id=30,
            source_raw_path=str(raw_dir / "year=1970" / "batch_030.json.gz"),
            input_sha256="dummy_sha",
        )
        daily_manifest.mark_running("era5_1970_batch_030")
        assert daily_manifest.get_chunk("era5_1970_batch_030")["status"] == DailyProcessingStatus.RUNNING.value

        runner = ProductionHistoricalRunner(
            extraction_config=ExtractionConfig(raw_base_dir=raw_dir, manifest_path=ext_manifest_path),
            daily_config=DailyProcessingConfig(raw_base_dir=raw_dir, processed_base_dir=processed_dir, manifest_path=daily_manifest_path),
            daily_manifest=daily_manifest,
        )

        rec = runner.daily_manifest.get_chunk("era5_1970_batch_030")
        assert rec["status"] == DailyProcessingStatus.PENDING.value
        assert rec["started_at"] is None
