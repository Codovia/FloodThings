"""
Pipeline orchestrator for generating, validating, and persisting ML-ready historical features.

Step 3 of the ML Feature Engineering Pipeline.
Manages:
1. Sourcing canonical daily records from data/processed/era5_daily (triggering DailyProcessor if raw chunk exists but unaggregated).
2. Sourcing trailing lookback daily records across calendar year boundaries (e.g. trailing 29 days of year Y-1).
3. Applying FeatureGenerator to build validated ML feature records.
4. Serializing to partitioned Parquet (data/processed/ml_features/year=YYYY/batch_BBB.parquet).
5. Maintaining an auditable processing manifest with provenance and missing-data statistics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from typing import Any, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyRecord
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ml.feature_generator import FeatureGenerator
from app.ml.feature_schema import ARROW_FEATURE_SCHEMA, FeatureQualityValidator, MLFeatureRecord
from app.ml.spatial_enrichment import SpatialEnrichmentService

logger = logging.getLogger(__name__)


def _find_project_root() -> Path:
    """Resolve repository project root directory."""
    curr = Path(__file__).resolve().parent
    for parent in [curr] + list(curr.parents):
        if (parent / "data").exists() and (parent / "backend").exists():
            return parent
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _find_project_root()


@dataclass
class FeaturePipelineConfig:
    """Configuration for historical ML feature generation and storage."""

    raw_base_dir: Path = PROJECT_ROOT / "data" / "raw" / "era5_historical"
    daily_base_dir: Path = PROJECT_ROOT / "data" / "processed" / "era5_daily"
    feature_base_dir: Path = PROJECT_ROOT / "data" / "processed" / "ml_features"
    manifest_path: Path = PROJECT_ROOT / "data" / "processed" / "ml_features" / "feature_manifest.json"
    feature_version: str = "1.0"
    compression: str = "snappy"
    dry_run: bool = False


@dataclass
class FeatureGenerationResult:
    """Execution metrics and audit statistics for a single feature chunk."""

    chunk_id: str
    year: int
    batch_id: int
    output_path: str
    is_valid: bool
    record_count: int
    complete_samples_count: int
    incomplete_samples_count: int
    missing_30d_rainfall_count: int
    input_daily_sha256: str
    output_feature_sha256: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return asdict(self)


class FeaturePipelineManifest:
    """Manages persistent JSON manifest for feature pipeline idempotency and auditability."""

    def __init__(self, manifest_path: Path):
        self.manifest_path = Path(manifest_path)
        self.data: dict[str, Any] = {"version": "1.0", "chunks": {}}
        self._load()

    def _load(self) -> None:
        """Load manifest from disk if it exists."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.warning("Failed to load feature manifest %s: %s", self.manifest_path, e)

    def _save(self) -> None:
        """Atomically persist manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.manifest_path.parent, delete=False, suffix=".tmp") as tf:
            json.dump(self.data, tf, indent=2, sort_keys=True)
            temp_name = tf.name
        Path(temp_name).replace(self.manifest_path)

    def is_chunk_processed(
        self,
        chunk_id: str,
        current_input_sha256: str,
        feature_version: str,
    ) -> bool:
        """Check if chunk has already been processed with matching input SHA256 and feature version."""
        entry = self.data["chunks"].get(chunk_id)
        if not entry:
            return False
        if entry.get("status") != "SUCCEEDED":
            return False
        if entry.get("input_daily_sha256") != current_input_sha256:
            return False
        if entry.get("feature_version") != feature_version:
            return False
        out_path = Path(entry.get("output_path", ""))
        return out_path.exists() and out_path.stat().st_size > 0

    def record_result(self, result: FeatureGenerationResult, feature_version: str) -> None:
        """Update manifest with feature generation result."""
        status = "SUCCEEDED" if result.is_valid else "FAILED"
        self.data["chunks"][result.chunk_id] = {
            "year": result.year,
            "batch_id": result.batch_id,
            "status": status,
            "output_path": result.output_path,
            "record_count": result.record_count,
            "complete_samples_count": result.complete_samples_count,
            "incomplete_samples_count": result.incomplete_samples_count,
            "missing_30d_rainfall_count": result.missing_30d_rainfall_count,
            "input_daily_sha256": result.input_daily_sha256,
            "output_feature_sha256": result.output_feature_sha256,
            "feature_version": feature_version,
            "errors": result.errors,
            "warnings": result.warnings,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._save()


class MLFeaturePipeline:
    """
    End-to-end pipeline orchestrator for ML feature engineering from daily ERA5 records.
    """

    def __init__(
        self,
        config: FeaturePipelineConfig | None = None,
        spatial_service: SpatialEnrichmentService | None = None,
        daily_processor: DailyProcessor | None = None,
    ):
        self.config = config or FeaturePipelineConfig()
        self.manifest = FeaturePipelineManifest(self.config.manifest_path)
        self.spatial_service = spatial_service or SpatialEnrichmentService()
        self.generator = FeatureGenerator(
            spatial_service=self.spatial_service,
            feature_version=self.config.feature_version,
        )
        self.daily_processor = daily_processor or DailyProcessor(
            config=DailyProcessingConfig(
                raw_base_dir=self.config.raw_base_dir,
                processed_base_dir=self.config.daily_base_dir,
                manifest_path=self.config.daily_base_dir / "processing_manifest.json",
            )
        )

    def process_chunk(self, year: int, batch_id: int) -> FeatureGenerationResult:
        """
        Process a single batch chunk for a calendar year into partitioned ML features.

        Reuses existing daily Parquet if available, or invokes DailyProcessor to process raw chunk first.
        """
        chunk_id = f"ml_features_{year}_batch_{batch_id:03d}"
        daily_file = self.config.daily_base_dir / f"year={year}" / f"batch_{batch_id:03d}.parquet"

        # 1. Ensure daily Parquet dataset exists
        if not daily_file.exists() or daily_file.stat().st_size == 0:
            logger.info("Daily Parquet missing for year %d batch %d; invoking DailyProcessor...", year, batch_id)
            proc_res = self.daily_processor.process_chunk(year=year, batch_id=batch_id)
            if not proc_res.is_valid:
                err = f"DailyProcessor failed for year {year} batch {batch_id}: {'; '.join(proc_res.errors)}"
                return FeatureGenerationResult(
                    chunk_id=chunk_id,
                    year=year,
                    batch_id=batch_id,
                    output_path="",
                    is_valid=False,
                    record_count=0,
                    complete_samples_count=0,
                    incomplete_samples_count=0,
                    missing_30d_rainfall_count=0,
                    input_daily_sha256="",
                    output_feature_sha256="",
                    errors=[err],
                )

        # 2. Check input daily Parquet checksum for idempotency
        with open(daily_file, "rb") as f:
            daily_bytes = f.read()
        daily_sha256 = hashlib.sha256(daily_bytes).hexdigest()

        if self.manifest.is_chunk_processed(
            chunk_id=chunk_id,
            current_input_sha256=daily_sha256,
            feature_version=self.config.feature_version,
        ):
            cached_entry = self.manifest.data["chunks"][chunk_id]
            logger.info("Chunk %s already processed with matching SHA-256; returning cached result", chunk_id)
            return FeatureGenerationResult(
                chunk_id=chunk_id,
                year=year,
                batch_id=batch_id,
                output_path=cached_entry["output_path"],
                is_valid=True,
                record_count=cached_entry["record_count"],
                complete_samples_count=cached_entry["complete_samples_count"],
                incomplete_samples_count=cached_entry["incomplete_samples_count"],
                missing_30d_rainfall_count=cached_entry["missing_30d_rainfall_count"],
                input_daily_sha256=daily_sha256,
                output_feature_sha256=cached_entry["output_feature_sha256"],
                warnings=["Chunk already processed with matching SHA-256; skipped (cached)."],
            )

        # 3. Read daily records for target year
        target_records = self._read_daily_parquet(daily_file)

        # 4. Read lookback daily records from year - 1 if available
        lookback_records: list[DailyRecord] = []
        prior_daily_file = self.config.daily_base_dir / f"year={year - 1}" / f"batch_{batch_id:03d}.parquet"
        if prior_daily_file.exists():
            prior_records = self._read_daily_parquet(prior_daily_file)
            # Take trailing 30 days of prior year (Dec 2 to Dec 31)
            cutoff_date = f"{year - 1}-12-01"
            lookback_records = [r for r in prior_records if r.date >= cutoff_date]

        # 5. Generate ML features
        features = self.generator.generate_features(
            daily_records=target_records,
            lookback_records=lookback_records,
        )

        # 6. Validate generated features
        validation_errors: list[str] = []
        complete_count = 0
        incomplete_count = 0
        missing_30d_count = 0

        for f_rec in features:
            errs = FeatureQualityValidator.validate_record(f_rec)
            if errs:
                validation_errors.extend(errs[:3])
            if f_rec.is_complete:
                complete_count += 1
            else:
                incomplete_count += 1
            if f_rec.rainfall_30d is None:
                missing_30d_count += 1

        if validation_errors:
            logger.error("Feature validation failed with %d errors", len(validation_errors))
            res = FeatureGenerationResult(
                chunk_id=chunk_id,
                year=year,
                batch_id=batch_id,
                output_path="",
                is_valid=False,
                record_count=len(features),
                complete_samples_count=complete_count,
                incomplete_samples_count=incomplete_count,
                missing_30d_rainfall_count=missing_30d_count,
                input_daily_sha256=daily_sha256,
                output_feature_sha256="",
                errors=validation_errors[:10],
            )
            self.manifest.record_result(res, self.config.feature_version)
            return res

        # 7. Write partitioned Parquet
        target_dir = self.config.feature_base_dir / f"year={year}"
        output_parquet = target_dir / f"batch_{batch_id:03d}.parquet"

        if not self.config.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._write_feature_parquet(features, output_parquet)

        # Compute output SHA-256
        with open(output_parquet, "rb") as f:
            out_bytes = f.read()
        out_sha256 = hashlib.sha256(out_bytes).hexdigest()

        result = FeatureGenerationResult(
            chunk_id=chunk_id,
            year=year,
            batch_id=batch_id,
            output_path=str(output_parquet),
            is_valid=True,
            record_count=len(features),
            complete_samples_count=complete_count,
            incomplete_samples_count=incomplete_count,
            missing_30d_rainfall_count=missing_30d_count,
            input_daily_sha256=daily_sha256,
            output_feature_sha256=out_sha256,
        )

        self.manifest.record_result(result, self.config.feature_version)
        return result

    def process_year(self, year: int, total_batches: int = 33) -> list[FeatureGenerationResult]:
        """Process all spatial batches for a given year."""
        results: list[FeatureGenerationResult] = []
        for batch_id in range(1, total_batches + 1):
            res = self.process_chunk(year=year, batch_id=batch_id)
            results.append(res)
        return results

    def _read_daily_parquet(self, file_path: Path) -> list[DailyRecord]:
        """Read daily Parquet file into list of DailyRecord objects."""
        table = pq.read_table(str(file_path))
        records: list[DailyRecord] = []
        col_names = table.column_names

        for i in range(table.num_rows):
            row_dict = {col: table[col][i].as_py() for col in col_names}
            records.append(DailyRecord(**row_dict))
        return records

    def _write_feature_parquet(
        self,
        records: list[MLFeatureRecord],
        target_path: Path,
    ) -> None:
        """Write MLFeatureRecord objects to Parquet using PyArrow with Snappy compression."""
        arrays = [
            pa.array([r.date for r in records], type=pa.string()),
            pa.array([r.cell_id for r in records], type=pa.string()),
            pa.array([r.chunk_id for r in records], type=pa.string()),
            pa.array([r.latitude for r in records], type=pa.float64()),
            pa.array([r.longitude for r in records], type=pa.float64()),
            pa.array([r.rainfall_1d for r in records], type=pa.float64()),
            pa.array([r.rainfall_3d for r in records], type=pa.float64()),
            pa.array([r.rainfall_7d for r in records], type=pa.float64()),
            pa.array([r.rainfall_14d for r in records], type=pa.float64()),
            pa.array([r.rainfall_30d for r in records], type=pa.float64()),
            pa.array([r.temperature_mean_c for r in records], type=pa.float64()),
            pa.array([r.temperature_min_c for r in records], type=pa.float64()),
            pa.array([r.temperature_max_c for r in records], type=pa.float64()),
            pa.array([r.relative_humidity_mean_pct for r in records], type=pa.float64()),
            pa.array([r.surface_pressure_mean_hpa for r in records], type=pa.float64()),
            pa.array([r.elevation for r in records], type=pa.float64()),
            pa.array([r.slope for r in records], type=pa.float64()),
            pa.array([r.basin_id for r in records], type=pa.string()),
            pa.array([r.basin_name for r in records], type=pa.string()),
            pa.array([r.sub_basin_id for r in records], type=pa.string()),
            pa.array([r.sub_basin_name for r in records], type=pa.string()),
            pa.array([r.hybas_id for r in records], type=pa.int64()),
            pa.array([r.distance_to_river_m for r in records], type=pa.float64()),
            pa.array([r.nearest_river_id for r in records], type=pa.string()),
            pa.array([r.district_id for r in records], type=pa.string()),
            pa.array([r.district_name for r in records], type=pa.string()),
            pa.array([r.hour_count for r in records], type=pa.int32()),
            pa.array([r.quality_status for r in records], type=pa.string()),
            pa.array([r.window_30d_valid_days for r in records], type=pa.int32()),
            pa.array([r.is_complete for r in records], type=pa.bool_()),
            pa.array([r.raw_chunk_id for r in records], type=pa.string()),
            pa.array([r.raw_payload_sha256 for r in records], type=pa.string()),
            pa.array([r.feature_version for r in records], type=pa.string()),
        ]

        table = pa.Table.from_arrays(arrays, schema=ARROW_FEATURE_SCHEMA)

        temp_dir = target_path.parent
        with tempfile.NamedTemporaryFile("wb", dir=temp_dir, delete=False, suffix=".parquet") as tf:
            pq.write_table(table, tf, compression=self.config.compression)
            temp_name = tf.name

        Path(temp_name).replace(target_path)
