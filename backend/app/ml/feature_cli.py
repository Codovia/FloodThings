"""
Command-Line Interface (CLI) for ML historical feature engineering and dataset generation.

Step 3 of the ML Feature Engineering Pipeline.
Enforces strict safety guards to prevent unconstrained execution.

Usage Examples:
    # Process single batch chunk (1969 batch 1)
    python -m app.ml.feature_cli --year 1969 --batch 1

    # Dry-run for complete year 1969
    python -m app.ml.feature_cli --year 1969 --dry-run

    # Process all 33 batches for year 1969
    python -m app.ml.feature_cli --year 1969
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
from typing import Sequence

from app.ingestion.historical.grid import get_spatial_batches
from app.ml.feature_pipeline import FeaturePipelineConfig, MLFeaturePipeline, PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.ml.feature_cli")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for ML feature pipeline."""
    parser = argparse.ArgumentParser(
        description="FloodPulse ML Historical Feature Pipeline (ERA5 + DEM + Hydrology + PostGIS)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    scope_group = parser.add_argument_group("Processing Scope (At least one required)")
    scope_group.add_argument("--year", type=int, help="Single calendar year to process (1969–1994)")
    scope_group.add_argument("--start-year", type=int, help="Start year of range (1969–1994)")
    scope_group.add_argument("--end-year", type=int, help="End year of range (1969–1994)")

    filter_group = parser.add_argument_group("Chunk Filters & Controls")
    filter_group.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    filter_group.add_argument("--limit", type=int, help="Maximum number of chunks to process in this run")
    filter_group.add_argument("--dry-run", action="store_true", help="Execute feature generation without writing Parquet")
    filter_group.add_argument(
        "--force-full-range",
        action="store_true",
        help="Explicit confirmation required to target the full multi-year range",
    )

    path_group = parser.add_argument_group("Storage Paths")
    path_group.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "era5_historical",
        help="Base directory containing raw compressed payloads",
    )
    path_group.add_argument(
        "--daily-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "era5_daily",
        help="Base directory for daily aggregated Parquet datasets",
    )
    path_group.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "ml_features",
        help="Base directory for partitioned ML feature Parquet output",
    )
    path_group.add_argument(
        "--manifest-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "ml_features" / "feature_manifest.json",
        help="Path to persistent JSON feature manifest",
    )

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point with strict safety guard validation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Safety Guard: Require explicit scope
    has_year = args.year is not None
    has_range = args.start_year is not None and args.end_year is not None

    if not (has_year or has_range):
        print(
            "ERROR: Explicit scope is required. You must specify either --year or "
            "both --start-year and --end-year.\n"
            "Unconstrained processing is prohibited.",
            file=sys.stderr,
        )
        return 1

    if has_year:
        start_year = args.year
        end_year = args.year
    else:
        start_year = args.start_year
        end_year = args.end_year

    if start_year > end_year:
        print(
            f"ERROR: --start-year ({start_year}) cannot exceed --end-year ({end_year})",
            file=sys.stderr,
        )
        return 1

    # Full range safety guard
    if (end_year - start_year + 1) >= 20 and not args.force_full_range:
        print(
            f"ERROR: Processing {end_year - start_year + 1} years requires --force-full-range confirmation.",
            file=sys.stderr,
        )
        return 1

    # 2. Configure pipeline
    config = FeaturePipelineConfig(
        raw_base_dir=args.raw_dir,
        daily_base_dir=args.daily_dir,
        feature_base_dir=args.output_dir,
        manifest_path=args.manifest_path,
        dry_run=args.dry_run,
    )

    pipeline = MLFeaturePipeline(config=config)
    batches = get_spatial_batches(batch_size=10, eligible_only=True)
    batch_ids = [args.batch] if args.batch is not None else list(range(1, len(batches) + 1))

    total_chunks = len(range(start_year, end_year + 1)) * len(batch_ids)
    if args.limit:
        total_chunks = min(total_chunks, args.limit)

    logger.info(
        "Starting ML feature generation: years %d–%d, %d batches, total %d chunks (dry_run=%s)",
        start_year,
        end_year,
        len(batch_ids),
        total_chunks,
        args.dry_run,
    )

    processed_count = 0
    succeeded_count = 0
    failed_count = 0
    total_records = 0
    total_complete_samples = 0
    total_incomplete_samples = 0

    for yr in range(start_year, end_year + 1):
        for b_id in batch_ids:
            if args.limit and processed_count >= args.limit:
                break

            processed_count += 1
            logger.info("[%d/%d] Processing year %d batch %d...", processed_count, total_chunks, yr, b_id)

            res = pipeline.process_chunk(year=yr, batch_id=b_id)
            if res.is_valid:
                succeeded_count += 1
                total_records += res.record_count
                total_complete_samples += res.complete_samples_count
                total_incomplete_samples += res.incomplete_samples_count
                logger.info(
                    "Year %d batch %d SUCCEEDED: %d records (%d complete, %d incomplete)",
                    yr,
                    b_id,
                    res.record_count,
                    res.complete_samples_count,
                    res.incomplete_samples_count,
                )
            else:
                failed_count += 1
                logger.error(
                    "Year %d batch %d FAILED: %s",
                    yr,
                    b_id,
                    "; ".join(res.errors),
                )

        if args.limit and processed_count >= args.limit:
            break

    logger.info(
        "Feature generation complete: %d succeeded, %d failed out of %d processed. "
        "Total real records: %d (Complete: %d, Incomplete: %d)",
        succeeded_count,
        failed_count,
        processed_count,
        total_records,
        total_complete_samples,
        total_incomplete_samples,
    )

    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    sys.exit(run_cli())
