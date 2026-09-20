"""
Orchestrator for processing raw hourly ERA5 chunks into partitioned daily Parquet files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.ingestion.historical.daily_aggregator import DailyAggregator
from app.ingestion.historical.daily_manifest import DailyProcessingManifest
from app.ingestion.historical.daily_models import (
    DailyProcessingConfig,
    DailyProcessingStatus,
    DailyRecord,
    DailyValidationResult,
)
from app.ingestion.historical.daily_validator import DailyDatasetValidator
from app.ingestion.historical.grid import get_spatial_batches
from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    GridCell,
)
from app.ingestion.historical.validator import HistoricalChunkValidator


class DailyProcessor:
    """
    Processes raw historical ERA5 JSON.gz chunks into canonical daily Parquet datasets.

    Pipeline:
    1. Verify raw file existence and checksum.
    2. Check processing manifest for idempotency (skip if cached with identical input SHA-256).
    3. Decompress and parse raw hourly JSON.
    4. Hourly structural/value validation via HistoricalChunkValidator.
    5. Aggregate hourly observations into daily records via DailyAggregator.
    6. Daily quality/integrity validation via DailyDatasetValidator.
    7. Persist to partitioned Parquet (data/processed/era5_daily/year=YYYY/batch_BBB.parquet) using Snappy.
    8. Update processing manifest with provenance and validation metrics.
    """

    def __init__(
        self,
        config: DailyProcessingConfig | None = None,
        manifest: DailyProcessingManifest | None = None,
        aggregator: DailyAggregator | None = None,
        validator: DailyDatasetValidator | None = None,
    ):
        self.config = config or DailyProcessingConfig()
        self.manifest = manifest or DailyProcessingManifest(self.config.manifest_path)
        self.aggregator = aggregator or DailyAggregator(self.config.processing_version)
        self.validator = validator or DailyDatasetValidator()
        self.hourly_validator = HistoricalChunkValidator()

    def process_chunk(
        self,
        year: int,
        batch_id: int,
        cells: list[GridCell] | None = None,
    ) -> DailyValidationResult:
        """
        Process a single raw extraction chunk identified by year and batch_id.

        Returns DailyValidationResult.
        """
        chunk_id = f"era5_{year}_batch_{batch_id:03d}"

        # Resolve grid cells if not provided
        if cells is None:
            batches = get_spatial_batches(batch_size=10)
            if 1 <= batch_id <= len(batches):
                cells = batches[batch_id - 1]
            else:
                cells = []

        chunk = ExtractionChunk(
            chunk_id=chunk_id,
            year=year,
            batch_id=batch_id,
            cells=cells,
        )

        # 1. Locate raw file and companion metadata
        raw_dir = self.config.raw_base_dir / f"year={year}"
        raw_file = raw_dir / f"batch_{batch_id:03d}.json.gz"
        meta_file = raw_dir / f"batch_{batch_id:03d}.meta.json"

        if not raw_file.exists() or raw_file.stat().st_size == 0:
            err = f"Raw file {raw_file} does not exist or is empty"
            self.manifest.mark_failed(chunk_id, err)
            return DailyValidationResult(
                is_valid=False,
                status=DailyProcessingStatus.FAILED,
                errors=[err],
            )

        # Read compressed bytes and compute checksums
        try:
            with open(raw_file, "rb") as f:
                compressed_bytes = f.read()
            compressed_sha256 = hashlib.sha256(compressed_bytes).hexdigest()
            raw_bytes = gzip.decompress(compressed_bytes)
            payload_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            parsed_json = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            err = f"Failed to read/decompress raw file {raw_file}: {e}"
            self.manifest.mark_failed(chunk_id, err)
            return DailyValidationResult(
                is_valid=False,
                status=DailyProcessingStatus.FAILED,
                errors=[err],
            )

        # 2. Idempotency Check
        if self.manifest.is_chunk_processed(
            chunk_id=chunk_id,
            current_raw_sha256=payload_sha256,
            processing_version=self.config.processing_version,
        ):
            return DailyValidationResult(
                is_valid=True,
                status=DailyProcessingStatus.SUCCEEDED,
                warnings=[f"Chunk {chunk_id} already processed with matching SHA-256; skipped (cached)."],
            )

        # Register and mark running
        self.manifest.register_chunk(
            chunk_id=chunk_id,
            year=year,
            batch_id=batch_id,
            source_raw_path=str(raw_file),
            input_sha256=payload_sha256,
            processing_version=self.config.processing_version,
        )
        self.manifest.mark_running(chunk_id)

        # 3. Validate hourly input integrity
        hourly_val = self.hourly_validator.validate_chunk_response(chunk, parsed_json, http_status=200)
        if not hourly_val.is_valid:
            err = f"Raw hourly data validation failed: {'; '.join(hourly_val.errors[:3])}"
            self.manifest.mark_failed(chunk_id, err, status=DailyProcessingStatus.VALIDATION_FAILED)
            return DailyValidationResult(
                is_valid=False,
                status=DailyProcessingStatus.VALIDATION_FAILED,
                errors=[err],
            )

        # 4. Daily Aggregation
        daily_records = self.aggregator.aggregate_chunk_payload(
            payload=parsed_json,
            raw_chunk_id=chunk_id,
            raw_payload_sha256=payload_sha256,
        )

        # 5. Daily Validation
        val_result = self.validator.validate_daily_records(
            records=daily_records,
            expected_year=year,
            expected_cells=cells,
        )

        if not val_result.is_valid:
            err = f"Daily data validation failed: {'; '.join(val_result.errors[:3])}"
            self.manifest.mark_failed(chunk_id, err, status=DailyProcessingStatus.VALIDATION_FAILED)
            return val_result

        # 6. Partitioned Parquet Persistence
        target_dir = self.config.processed_base_dir / f"year={year}"
        output_parquet = target_dir / f"batch_{batch_id:03d}.parquet"

        if not self.config.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._write_parquet(daily_records, output_parquet, chunk_id, payload_sha256)

        # 7. Update Manifest
        self.manifest.mark_succeeded(
            chunk_id=chunk_id,
            output_path=str(output_parquet),
            output_record_count=len(daily_records),
            validation=val_result,
            input_sha256=payload_sha256,
            processing_version=self.config.processing_version,
        )

        return val_result

    def _write_parquet(
        self,
        records: list[DailyRecord],
        target_path: Path,
        chunk_id: str,
        payload_sha256: str,
    ) -> None:
        """Write daily records to Parquet with explicit schema and Snappy compression."""
        # Define strict Arrow schema
        schema = pa.schema(
            [
                ("date", pa.string()),
                ("latitude", pa.float64()),
                ("longitude", pa.float64()),
                ("precipitation_total_mm", pa.float64()),
                ("temperature_mean_c", pa.float64()),
                ("temperature_min_c", pa.float64()),
                ("temperature_max_c", pa.float64()),
                ("relative_humidity_mean_pct", pa.float64()),
                ("surface_pressure_mean_hpa", pa.float64()),
                ("hour_count", pa.int32()),
                ("quality_status", pa.string()),
                ("source", pa.string()),
                ("dataset_model", pa.string()),
                ("raw_chunk_id", pa.string()),
                ("raw_payload_sha256", pa.string()),
                ("processing_version", pa.string()),
            ],
            metadata={
                b"source": b"Open-Meteo Historical Weather API",
                b"dataset_model": b"ERA5",
                b"raw_chunk_id": chunk_id.encode("utf-8"),
                b"raw_payload_sha256": payload_sha256.encode("utf-8"),
                b"processing_version": self.config.processing_version.encode("utf-8"),
                b"created_at_utc": datetime.now(timezone.utc).isoformat().encode("utf-8"),
            },
        )

        # Build column arrays
        arrays = [
            pa.array([r.date for r in records], type=pa.string()),
            pa.array([r.latitude for r in records], type=pa.float64()),
            pa.array([r.longitude for r in records], type=pa.float64()),
            pa.array([r.precipitation_total_mm for r in records], type=pa.float64()),
            pa.array([r.temperature_mean_c for r in records], type=pa.float64()),
            pa.array([r.temperature_min_c for r in records], type=pa.float64()),
            pa.array([r.temperature_max_c for r in records], type=pa.float64()),
            pa.array([r.relative_humidity_mean_pct for r in records], type=pa.float64()),
            pa.array([r.surface_pressure_mean_hpa for r in records], type=pa.float64()),
            pa.array([r.hour_count for r in records], type=pa.int32()),
            pa.array([r.quality_status for r in records], type=pa.string()),
            pa.array([r.source for r in records], type=pa.string()),
            pa.array([r.dataset_model for r in records], type=pa.string()),
            pa.array([r.raw_chunk_id for r in records], type=pa.string()),
            pa.array([r.raw_payload_sha256 for r in records], type=pa.string()),
            pa.array([r.processing_version for r in records], type=pa.string()),
        ]

        table = pa.Table.from_arrays(arrays, schema=schema)

        # Atomic write via tempfile in target directory
        temp_dir = target_path.parent
        with tempfile.NamedTemporaryFile("wb", dir=temp_dir, delete=False, suffix=".parquet") as tf:
            pq.write_table(table, tf, compression=self.config.compression)
            temp_name = tf.name

        Path(temp_name).replace(target_path)
