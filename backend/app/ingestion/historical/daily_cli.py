"""
Command-Line Interface (CLI) for historical meteorological daily aggregation and processing.

Enforces strict safety guards to prevent accidental unconstrained processing.

Usage Examples:
    # Process single chunk (1994 batch 1)
    python -m app.ingestion.historical.daily_cli --year 1994 --batch 1

    # Dry run for 1994 batch 1
    python -m app.ingestion.historical.daily_cli --year 1994 --batch 1 --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyProcessingStatus
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.grid import generate_chunks


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for daily meteorological aggregation."""
    parser = argparse.ArgumentParser(
        description="FloodPulse Historical Meteorological Daily Processing CLI (ERA5 Reanalysis)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    scope_group = parser.add_argument_group("Processing Scope (At least one required)")
    scope_group.add_argument("--year", type=int, help="Single calendar year to process (1969–1994)")
    scope_group.add_argument("--start-year", type=int, help="Start year of range (1969–1994)")
    scope_group.add_argument("--end-year", type=int, help="End year of range (1969–1994)")

    filter_group = parser.add_argument_group("Chunk Filters & Controls")
    filter_group.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    filter_group.add_argument("--limit", type=int, help="Maximum number of chunks to process in this run")
    filter_group.add_argument("--dry-run", action="store_true", help="Execute aggregation without writing Parquet to disk")
    filter_group.add_argument(
        "--force-full-range",
        action="store_true",
        help="Explicit confirmation required to target the complete 26-year range (1969–1994)",
    )

    path_group = parser.add_argument_group("Storage Paths")
    path_group.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw/era5_historical"),
        help="Base directory containing raw compressed payloads",
    )
    path_group.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/era5_daily"),
        help="Base directory for partitioned Parquet output",
    )
    path_group.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("data/processed/era5_daily/processing_manifest.json"),
        help="Path to persistent JSON processing manifest",
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
        print(f"ERROR: --start-year ({start_year}) cannot exceed --end-year ({end_year})", file=sys.stderr)
        return 1

    # 2. Safety Guard: Full 26-year protection
    if start_year == 1969 and end_year == 1994 and not args.limit and not args.dry_run and not args.force_full_range:
        print(
            "SAFETY GUARD: Target scope covers the complete 26-year historical period (858 chunks) "
            "without a --limit or --dry-run.\n"
            "To execute full processing, you must explicitly pass --force-full-range.",
            file=sys.stderr,
        )
        return 1

    config = DailyProcessingConfig(
        raw_base_dir=args.raw_dir,
        processed_base_dir=args.output_dir,
        manifest_path=args.manifest_path,
        dry_run=args.dry_run,
    )

    processor = DailyProcessor(config=config)
    processor.manifest.recover_stale_running_chunks(
        processed_base_dir=config.processed_base_dir,
        raw_base_dir=config.raw_base_dir,
    )

    # Generate candidate chunks to process
    candidate_chunks = generate_chunks(start_year=start_year, end_year=end_year, batch_size=10)
    if args.batch is not None:
        candidate_chunks = [c for c in candidate_chunks if c.batch_id == args.batch]

    if args.limit is not None:
        candidate_chunks = candidate_chunks[: args.limit]

    print("=" * 70)
    print("  FloodPulse Historical ERA5 Daily Processing & Aggregation")
    print("=" * 70)
    print(f"  Target Period:    {start_year} to {end_year}")
    print(f"  Batch Filter:     {args.batch if args.batch else 'All batches (1–33)'}")
    print(f"  Target Chunks:    {len(candidate_chunks)}")
    print(f"  Dry Run:          {args.dry_run}")
    print(f"  Raw Base Dir:     {config.raw_base_dir}")
    print(f"  Output Base Dir:  {config.processed_base_dir}")
    print(f"  Manifest:         {config.manifest_path}")
    print("-" * 70)

    succeeded = 0
    skipped = 0
    failed = 0

    for chunk in candidate_chunks:
        res = processor.process_chunk(
            year=chunk.year,
            batch_id=chunk.batch_id,
            cells=chunk.cells,
        )
        if res.is_valid:
            if res.warnings and "already processed" in res.warnings[0]:
                print(f"  [{chunk.chunk_id}] Skipped (Cached)")
                skipped += 1
            else:
                print(
                    f"  [{chunk.chunk_id}] Succeeded: {res.records_validated} records "
                    f"({res.complete_days} complete, {res.incomplete_days} incomplete)"
                )
                succeeded += 1
        else:
            print(f"  [{chunk.chunk_id}] Failed: {'; '.join(res.errors[:2])}")
            failed += 1

    print("-" * 70)
    print("Processing Summary:")
    print(f"  Total Attempted: {len(candidate_chunks)}")
    print(f"  Succeeded:       {succeeded}")
    print(f"  Skipped (Cached):{skipped}")
    print(f"  Failed:          {failed}")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_cli())
