"""
Production orchestrator and preflight auditor for the full historical ERA5 extraction & processing pipeline.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from app.ingestion.historical.daily_manifest import DailyProcessingManifest
from app.ingestion.historical.daily_models import DailyProcessingConfig
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
)


@dataclass
class PreflightAuditResult:
    """Detailed audit metrics and state of the historical extraction and processing pipeline."""

    total_cells: int
    total_batches: int
    total_years: int
    total_chunks: int
    batch_sizes: list[int]
    years_range: tuple[int, int]
    authoritative_cells_count: int = 324
    eligible_cells_count: int = 318
    excluded_cells_count: int = 6

    # Raw Extraction State
    valid_raw_chunks: list[str] = field(default_factory=list)
    missing_raw_chunks: list[str] = field(default_factory=list)
    invalid_raw_chunks: list[str] = field(default_factory=list)

    # Daily Processing State
    valid_processed_chunks: list[str] = field(default_factory=list)
    missing_processed_chunks: list[str] = field(default_factory=list)
    invalid_processed_chunks: list[str] = field(default_factory=list)

    # Storage Metrics (observed and estimated)
    observed_raw_compressed_min: int = 0
    observed_raw_compressed_max: int = 0
    observed_raw_compressed_mean: float = 0.0
    estimated_total_raw_compressed_bytes: float = 0.0

    observed_raw_uncompressed_min: int = 0
    observed_raw_uncompressed_max: int = 0
    observed_raw_uncompressed_mean: float = 0.0
    estimated_total_raw_uncompressed_bytes: float = 0.0

    observed_daily_parquet_bytes: int = 0
    estimated_total_daily_parquet_bytes: float = 0.0
    estimated_total_daily_rows: int = 3019728

    available_disk_bytes: int = 0


class ProductionHistoricalRunner:
    """
    Manages the complete 1969–1994 historical ERA5 extraction and daily processing pipeline.

    Guarantees:
    - Preflight verification and inventory audit before execution.
    - Interleaved chunk lifecycle:
        extract -> validate raw -> checkpoint raw -> aggregate daily -> validate daily -> write Parquet -> checkpoint daily
    - Strict idempotency: Valid cached raw chunks and daily Parquet files are never re-extracted or re-processed.
    - Raw data permanence: Raw files are never deleted.
    - Dry-run mode: Complete inventory and audit with zero network calls and zero disk writes.
    """

    def __init__(
        self,
        extraction_config: ExtractionConfig | None = None,
        daily_config: DailyProcessingConfig | None = None,
        extraction_manifest: HistoricalExtractionManifest | None = None,
        daily_manifest: DailyProcessingManifest | None = None,
        extractor: HistoricalExtractor | None = None,
        daily_processor: DailyProcessor | None = None,
        auto_recover: bool = True,
    ):
        self.extraction_config = extraction_config or ExtractionConfig()
        self.daily_config = daily_config or DailyProcessingConfig()

        self.extraction_manifest = extraction_manifest or HistoricalExtractionManifest(
            self.extraction_config.manifest_path
        )
        self.daily_manifest = daily_manifest or DailyProcessingManifest(
            self.daily_config.manifest_path
        )

        if auto_recover:
            self.recover_stale_chunks()

        self.extractor = extractor or HistoricalExtractor(
            config=self.extraction_config, manifest=self.extraction_manifest
        )
        self.daily_processor = daily_processor or DailyProcessor(
            config=self.daily_config, manifest=self.daily_manifest
        )

    def recover_stale_chunks(self) -> dict[str, Any]:
        """Safely recover stale RUNNING chunks across extraction and daily manifests."""
        ext_res = self.extraction_manifest.recover_stale_running_chunks(
            raw_base_dir=self.extraction_config.raw_base_dir
        )
        proc_res = self.daily_manifest.recover_stale_running_chunks(
            processed_base_dir=self.daily_config.processed_base_dir,
            raw_base_dir=self.extraction_config.raw_base_dir,
        )
        return {
            "extraction": ext_res,
            "processing": proc_res,
        }

    def audit_inventory(
        self,
        start_year: int = 1969,
        end_year: int = 1994,
    ) -> PreflightAuditResult:
        """
        Perform a comprehensive preflight audit of the inventory, disk space, and existing state.
        Does not perform any network calls or database writes.
        """
        auth_cells = get_karnataka_grid()
        eligible_cells = get_era5_eligible_grid()
        excluded_cells = get_era5_excluded_cells()

        batches = get_spatial_batches(batch_size=self.extraction_config.batch_size, eligible_only=True)
        batch_sizes = [len(b) for b in batches]
        years_count = end_year - start_year + 1

        all_chunks = generate_chunks(
            start_year,
            end_year,
            batch_size=self.extraction_config.batch_size,
            eligible_only=True,
        )
        total_chunks = len(all_chunks)

        # 1. Audit Raw Extraction State
        valid_raw: list[str] = []
        missing_raw: list[str] = []
        invalid_raw: list[str] = []

        compressed_sizes: list[int] = []
        uncompressed_sizes: list[int] = []

        for chunk in all_chunks:
            chunk_id = chunk.chunk_id
            manifest_entry = self.extraction_manifest.get_chunk(chunk_id)

            if manifest_entry and manifest_entry.get("status") == ChunkStatus.SUCCEEDED.value:
                # Verify spatial fingerprint matches expected chunk cells
                actual_fp = manifest_entry.get("spatial_fingerprint")
                if not actual_fp:
                    coords = manifest_entry.get("coordinates", [])
                    cell_ids = [
                        f"ERA5_{int(round(lat * 100)):04d}_{int(round(lon * 100)):05d}"
                        for lat, lon in coords
                    ]
                    actual_fp = hashlib.sha256(",".join(sorted(cell_ids)).encode("utf-8")).hexdigest()[:8]
                if actual_fp != chunk.spatial_fingerprint:
                    invalid_raw.append(chunk_id)
                    continue

                raw_path_str = manifest_entry.get("raw_path")
                if raw_path_str:
                    raw_path = Path(raw_path_str)
                    if raw_path.exists() and raw_path.stat().st_size > 0:
                        try:
                            with open(raw_path, "rb") as f:
                                actual_hash = hashlib.sha256(f.read()).hexdigest()
                            if actual_hash == manifest_entry.get("compressed_sha256"):
                                valid_raw.append(chunk_id)
                                compressed_sizes.append(raw_path.stat().st_size)
                                if manifest_entry.get("uncompressed_bytes"):
                                    uncompressed_sizes.append(manifest_entry["uncompressed_bytes"])
                            else:
                                invalid_raw.append(chunk_id)
                        except Exception:
                            invalid_raw.append(chunk_id)
                    else:
                        invalid_raw.append(chunk_id)
                else:
                    invalid_raw.append(chunk_id)
            else:
                missing_raw.append(chunk_id)

        # 2. Audit Daily Processing State
        valid_processed: list[str] = []
        missing_processed: list[str] = []
        invalid_processed: list[str] = []

        for chunk in all_chunks:
            chunk_id = chunk.chunk_id
            proc_entry = self.daily_manifest.get_chunk(chunk_id)

            if proc_entry and proc_entry.get("status") == "SUCCEEDED":
                out_path_str = proc_entry.get("output_path")
                if out_path_str:
                    out_path = Path(out_path_str)
                    if out_path.exists() and out_path.stat().st_size > 0:
                        valid_processed.append(chunk_id)
                    else:
                        invalid_processed.append(chunk_id)
                else:
                    invalid_processed.append(chunk_id)
            else:
                missing_processed.append(chunk_id)

        # 3. Storage Calculations
        min_c = min(compressed_sizes) if compressed_sizes else 0
        max_c = max(compressed_sizes) if compressed_sizes else 0
        mean_c = sum(compressed_sizes) / len(compressed_sizes) if compressed_sizes else 0.0
        est_total_c = mean_c * total_chunks

        min_u = min(uncompressed_sizes) if uncompressed_sizes else 0
        max_u = max(uncompressed_sizes) if uncompressed_sizes else 0
        mean_u = sum(uncompressed_sizes) / len(uncompressed_sizes) if uncompressed_sizes else 0.0
        est_total_u = mean_u * total_chunks

        # Compute exact daily rows across the given year range for 318 eligible cells
        total_days = sum(366 if calendar.isleap(yr) else 365 for yr in range(start_year, end_year + 1))
        est_daily_rows = total_days * len(eligible_cells)

        # Parquet metrics from existing test file
        parquet_file = self.daily_config.processed_base_dir / "year=1994" / "batch_001.parquet"
        pq_size = parquet_file.stat().st_size if parquet_file.exists() else 65372
        bytes_per_row = pq_size / 3650.0 if pq_size else 17.91
        est_total_pq = bytes_per_row * est_daily_rows

        # Disk space
        try:
            import shutil

            stat = shutil.disk_usage(self.extraction_config.raw_base_dir.parent)
            available_disk = stat.free
        except Exception:
            available_disk = 0

        return PreflightAuditResult(
            total_cells=len(eligible_cells),
            total_batches=len(batches),
            total_years=years_count,
            total_chunks=total_chunks,
            batch_sizes=batch_sizes,
            years_range=(start_year, end_year),
            authoritative_cells_count=len(auth_cells),
            eligible_cells_count=len(eligible_cells),
            excluded_cells_count=len(excluded_cells),
            valid_raw_chunks=valid_raw,
            missing_raw_chunks=missing_raw,
            invalid_raw_chunks=invalid_raw,
            valid_processed_chunks=valid_processed,
            missing_processed_chunks=missing_processed,
            invalid_processed_chunks=invalid_processed,
            observed_raw_compressed_min=min_c,
            observed_raw_compressed_max=max_c,
            observed_raw_compressed_mean=mean_c,
            estimated_total_raw_compressed_bytes=est_total_c,
            observed_raw_uncompressed_min=min_u,
            observed_raw_uncompressed_max=max_u,
            observed_raw_uncompressed_mean=mean_u,
            estimated_total_raw_uncompressed_bytes=est_total_u,
            observed_daily_parquet_bytes=pq_size,
            estimated_total_daily_parquet_bytes=est_total_pq,
            estimated_total_daily_rows=est_daily_rows,
            available_disk_bytes=available_disk,
        )

    def run_production(
        self,
        start_year: int = 1969,
        end_year: int = 1994,
        batch_filter: int | None = None,
        limit: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """
        Execute the production historical pipeline with interleaved extraction and daily processing.
        If dry_run is True, audits inventory and returns planned execution without performing I/O.
        """
        audit = self.audit_inventory(start_year, end_year)

        all_chunks = generate_chunks(
            start_year,
            end_year,
            batch_size=self.extraction_config.batch_size,
            eligible_only=True,
        )
        if batch_filter is not None:
            all_chunks = [c for c in all_chunks if c.batch_id == batch_filter]

        if limit is not None:
            all_chunks = all_chunks[:limit]

        if dry_run:
            return {
                "dry_run": True,
                "audit": audit,
                "target_chunks_count": len(all_chunks),
                "planned_extractions": len([c for c in all_chunks if c.chunk_id in audit.missing_raw_chunks]),
                "planned_processings": len([c for c in all_chunks if c.chunk_id in audit.missing_processed_chunks]),
                "api_requests_made": 0,
                "database_writes_made": 0,
            }

        # Live execution (interleaved)
        extracted_count = 0
        cached_extract_count = 0
        processed_count = 0
        cached_process_count = 0
        failed_count = 0

        for chunk in all_chunks:
            # 1. Extraction Stage
            extract_res = self.extractor.extract_chunk(chunk)
            if not extract_res.is_valid:
                failed_count += 1
                continue

            if extract_res.warnings and "already completed" in extract_res.warnings[0]:
                cached_extract_count += 1
            else:
                extracted_count += 1

            # 2. Daily Processing Stage
            proc_res = self.daily_processor.process_chunk(
                year=chunk.year,
                batch_id=chunk.batch_id,
                cells=chunk.cells,
            )
            if not proc_res.is_valid:
                failed_count += 1
                continue

            if proc_res.warnings and "already processed" in proc_res.warnings[0]:
                cached_process_count += 1
            else:
                processed_count += 1

        return {
            "dry_run": False,
            "target_chunks_count": len(all_chunks),
            "extracted_count": extracted_count,
            "cached_extract_count": cached_extract_count,
            "processed_count": processed_count,
            "cached_process_count": cached_process_count,
            "failed_count": failed_count,
            "api_requests_made": extracted_count,
            "database_writes_made": 0,
        }
