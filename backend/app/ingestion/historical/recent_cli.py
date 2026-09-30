"""
Dedicated Command-Line Interface (CLI) for recent-period ERA5 extraction and daily processing (2011–2026).

Enforces strict physical separation from historical baseline datasets.
Default target period: 2011-01-01 to 2026-09-21 (latest verified upstream ERA5 timestamp).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from app.ingestion.historical.daily_models import DailyProcessingConfig, DailyProcessingStatus
from app.ingestion.historical.daily_processor import DailyProcessor
from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import generate_chunks
from app.ingestion.historical.manifest import HistoricalExtractionManifest
from app.ingestion.historical.models import ExtractionChunk, ExtractionConfig

DEFAULT_START_YEAR = 2011
DEFAULT_END_YEAR = 2026
DEFAULT_FINAL_END_DATE = "2026-09-21"

DEFAULT_RAW_DIR = Path("data/raw/era5_recent")
DEFAULT_PROCESSED_DIR = Path("data/processed/era5_daily/recent")
DEFAULT_EXTRACTION_MANIFEST = Path("data/raw/era5_recent/extraction_manifest.json")
DEFAULT_PROCESSING_MANIFEST = Path("data/processed/era5_daily/recent/processing_manifest.json")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for recent ERA5 pipeline."""
    parser = argparse.ArgumentParser(
        description="FloodPulse Recent-Period ERA5 Meteorological Pipeline (2011–2026)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # 1. Extract subcommand
    extract_parser = subparsers.add_parser("extract", help="Extract raw hourly ERA5 data from Open-Meteo archive")
    extract_parser.add_argument("--year", type=int, help="Single calendar year to extract (2011–2026)")
    extract_parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR, help="Start year of range")
    extract_parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR, help="End year of range")
    extract_parser.add_argument("--final-end-date", type=str, default=DEFAULT_FINAL_END_DATE, help="Terminal date for final year")
    extract_parser.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    extract_parser.add_argument("--batch-size", type=int, default=10, help="Grid cells per batch")
    extract_parser.add_argument("--limit", type=int, help="Maximum number of chunks to extract in this run")
    extract_parser.add_argument("--resume", action="store_true", help="Resume pending or retryable chunks in manifest")
    extract_parser.add_argument("--dry-run", action="store_true", help="Execute without persisting to disk")
    extract_parser.add_argument("--pacing", type=float, default=10.0, help="Pacing interval between requests (seconds)")
    extract_parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Base directory for raw recent data")
    extract_parser.add_argument("--manifest-path", type=Path, default=DEFAULT_EXTRACTION_MANIFEST, help="Recent extraction manifest path")

    # 2. Process subcommand
    process_parser = subparsers.add_parser("process", help="Process raw recent ERA5 hourly chunks into daily Parquet")
    process_parser.add_argument("--year", type=int, help="Single calendar year to process (2011–2026)")
    process_parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR, help="Start year of range")
    process_parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR, help="End year of range")
    process_parser.add_argument("--final-end-date", type=str, default=DEFAULT_FINAL_END_DATE, help="Terminal date for final year")
    process_parser.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    process_parser.add_argument("--limit", type=int, help="Maximum number of chunks to process in this run")
    process_parser.add_argument("--dry-run", action="store_true", help="Execute without writing Parquet to disk")
    process_parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Base directory containing raw recent data")
    process_parser.add_argument("--output-dir", type=Path, default=DEFAULT_PROCESSED_DIR, help="Base directory for daily recent Parquet")
    process_parser.add_argument("--manifest-path", type=Path, default=DEFAULT_PROCESSING_MANIFEST, help="Recent daily processing manifest path")

    # 3. Status subcommand
    status_parser = subparsers.add_parser("status", help="Inspect status of recent extraction and daily processing manifests")
    status_parser.add_argument("--raw-manifest", type=Path, default=DEFAULT_EXTRACTION_MANIFEST, help="Path to extraction manifest")
    status_parser.add_argument("--proc-manifest", type=Path, default=DEFAULT_PROCESSING_MANIFEST, help="Path to processing manifest")

    return parser


def run_extract(args: argparse.Namespace) -> int:
    """Execute recent extraction with boundary safety guards."""
    start_year = args.year if args.year is not None else args.start_year
    end_year = args.year if args.year is not None else args.end_year

    if start_year < 2011:
        print(f"ERROR: start_year ({start_year}) cannot be before 2011 for recent pipeline.", file=sys.stderr)
        return 1
    if end_year > 2026:
        print(f"ERROR: end_year ({end_year}) cannot exceed 2026.", file=sys.stderr)
        return 1
    if start_year > end_year:
        print(f"ERROR: start_year ({start_year}) cannot exceed end_year ({end_year})", file=sys.stderr)
        return 1

    # Safety Guard: Ensure historical directories are never targeted
    if "era5_historical" in str(args.raw_dir) or "era5_historical" in str(args.manifest_path):
        print("ERROR: Target paths must be segregated from historical baseline.", file=sys.stderr)
        return 1

    config = ExtractionConfig(
        raw_base_dir=args.raw_dir,
        manifest_path=args.manifest_path,
        batch_size=args.batch_size,
        min_request_interval_seconds=args.pacing,
        pacing_delay_seconds=args.pacing,
        dry_run=args.dry_run,
    )

    manifest = HistoricalExtractionManifest(config.manifest_path)
    manifest.recover_stale_running_chunks(raw_base_dir=config.raw_base_dir)
    extractor = HistoricalExtractor(config=config, manifest=manifest)

    final_end = args.final_end_date if end_year == 2026 else None
    all_chunks = generate_chunks(
        start_year=start_year,
        end_year=end_year,
        batch_size=config.batch_size,
        eligible_only=True,
        final_end_date=final_end,
    )

    if args.batch is not None:
        all_chunks = [c for c in all_chunks if c.batch_id == args.batch]

    manifest.register_chunks(all_chunks)

    if args.resume:
        target_chunks = manifest.get_pending_or_retryable_chunks(all_chunks)
    else:
        target_chunks = all_chunks

    print("=" * 70)
    print("  FloodPulse Recent-Period ERA5 Meteorological Extraction")
    print("=" * 70)
    print(f"  Target Period:    {start_year} to {end_year} (final_end_date: {final_end or '12-31'})")
    print(f"  Batch Filter:     {args.batch if args.batch else 'All batches (1–33)'}")
    print(f"  Candidate Chunks: {len(all_chunks)}")
    print(f"  Target Chunks:    {len(target_chunks)}")
    print(f"  Limit:            {args.limit if args.limit else 'No limit'}")
    print(f"  Dry Run:          {args.dry_run}")
    print(f"  Pacing Interval:  {args.pacing}s")
    print(f"  Raw Directory:    {config.raw_base_dir}")
    print(f"  Manifest:         {config.manifest_path}")
    print("-" * 70)

    if not target_chunks:
        print("No pending chunks to extract. All candidate chunks are already completed.")
        return 0

    results = extractor.extract_chunks(target_chunks, limit=args.limit)

    print("\nExtraction Summary:")
    print(f"  Total Processed:  {results['total_processed']}")
    print(f"  Succeeded:        {results['succeeded']}")
    print(f"  Skipped (Cached): {results['skipped']}")
    print(f"  Failed:           {results['failed']}")
    print("  Manifest Statuses:")
    for status, count in results["manifest_summary"].items():
        print(f"    - {status}: {count}")
    print("=" * 70)

    return 0 if results["failed"] == 0 else 1


def run_process(args: argparse.Namespace) -> int:
    """Execute recent daily processing with boundary safety guards."""
    start_year = args.year if args.year is not None else args.start_year
    end_year = args.year if args.year is not None else args.end_year

    if start_year < 2011:
        print(f"ERROR: start_year ({start_year}) cannot be before 2011 for recent pipeline.", file=sys.stderr)
        return 1
    if end_year > 2026:
        print(f"ERROR: end_year ({end_year}) cannot exceed 2026.", file=sys.stderr)
        return 1
    if start_year > end_year:
        print(f"ERROR: start_year ({start_year}) cannot exceed end_year ({end_year})", file=sys.stderr)
        return 1

    # Safety Guard
    if str(args.output_dir) == "data/processed/era5_daily" or "era5_historical" in str(args.raw_dir):
        print("ERROR: Target paths must be segregated from historical baseline.", file=sys.stderr)
        return 1

    config = DailyProcessingConfig(
        raw_base_dir=args.raw_dir,
        processed_base_dir=args.output_dir,
        manifest_path=args.manifest_path,
        dry_run=args.dry_run,
    )

    processor = DailyProcessor(config=config)
    final_end = args.final_end_date if end_year == 2026 else None
    all_chunks = generate_chunks(
        start_year=start_year,
        end_year=end_year,
        batch_size=10,
        eligible_only=True,
        final_end_date=final_end,
    )

    if args.batch is not None:
        all_chunks = [c for c in all_chunks if c.batch_id == args.batch]

    target_chunks = all_chunks[: args.limit] if args.limit is not None else all_chunks

    print("=" * 70)
    print("  FloodPulse Recent-Period ERA5 Daily Processing & Aggregation")
    print("=" * 70)
    print(f"  Target Period:    {start_year} to {end_year} (final_end_date: {final_end or '12-31'})")
    print(f"  Batch Filter:     {args.batch if args.batch else 'All batches (1–33)'}")
    print(f"  Target Chunks:    {len(target_chunks)}")
    print(f"  Limit:            {args.limit if args.limit else 'No limit'}")
    print(f"  Dry Run:          {args.dry_run}")
    print(f"  Raw Directory:    {config.raw_base_dir}")
    print(f"  Output Parquet:   {config.processed_base_dir}")
    print(f"  Manifest:         {config.manifest_path}")
    print("-" * 70)

    succeeded = 0
    failed = 0
    skipped = 0

    for idx, chunk in enumerate(target_chunks, start=1):
        import time
        t_proc = time.time()
        res = processor.process_chunk(
            year=chunk.year,
            batch_id=chunk.batch_id,
            cells=chunk.cells,
            start_date=chunk.start_date,
            end_date=chunk.end_date,
        )
        elapsed = time.time() - t_proc
        if res.is_valid:
            if res.warnings and "already processed" in res.warnings[0]:
                skipped += 1
                status_str = "CACHED"
            else:
                succeeded += 1
                status_str = "SUCCEEDED"
        else:
            failed += 1
            status_str = f"FAILED ({'; '.join(res.errors[:1])})"

        print(f"  [{idx:03d}/{len(target_chunks):03d}] {chunk.chunk_id} -> {status_str} ({elapsed:.2f}s)", flush=True)

    print("\nDaily Processing Summary:")
    print(f"  Total Processed:  {len(target_chunks)}")
    print(f"  Succeeded:        {succeeded}")
    print(f"  Skipped (Cached): {skipped}")
    print(f"  Failed:           {failed}")
    print("  Manifest Statuses:")
    for status, count in processor.manifest.summary().items():
        print(f"    - {status}: {count}")
    print("=" * 70)

    return 0 if failed == 0 else 1


def run_status(args: argparse.Namespace) -> int:
    """Print status of recent manifests."""
    import json

    print("=" * 70)
    print("  FloodPulse Recent-Period Pipeline Status")
    print("=" * 70)

    print(f"Raw Manifest: {args.raw_manifest}")
    if args.raw_manifest.exists():
        with open(args.raw_manifest, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        chunks = raw_data.get("chunks", {})
        counts: dict[str, int] = {}
        for c in chunks.values():
            st = c.get("status", "UNKNOWN")
            counts[st] = counts.get(st, 0) + 1
        print(f"  Total Tracked Chunks: {len(chunks)}")
        for st, n in sorted(counts.items()):
            print(f"    - {st}: {n}")
    else:
        print("  (Not created yet)")

    print(f"\nProcessing Manifest: {args.proc_manifest}")
    if args.proc_manifest.exists():
        with open(args.proc_manifest, "r", encoding="utf-8") as f:
            proc_data = json.load(f)
        chunks = proc_data.get("chunks", {})
        counts = {}
        for c in chunks.values():
            st = c.get("status", "UNKNOWN")
            counts[st] = counts.get(st, 0) + 1
        print(f"  Total Tracked Chunks: {len(chunks)}")
        for st, n in sorted(counts.items()):
            print(f"    - {st}: {n}")
    else:
        print("  (Not created yet)")
    print("=" * 70)
    return 0


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract":
        return run_extract(args)
    elif args.command == "process":
        return run_process(args)
    elif args.command == "status":
        return run_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
