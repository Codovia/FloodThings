"""
Command-Line Interface (CLI) for historical meteorological extraction.

Enforces strict safety guards to prevent accidental full 26-year statewide extractions.

Usage Examples:
    # Dry run 1 batch for 1994
    python -m app.ingestion.historical.cli --year 1994 --batch 1 --limit 1 --dry-run

    # Extract single chunk (1994 batch 1)
    python -m app.ingestion.historical.cli --year 1994 --batch 1 --limit 1

    # Resume incomplete chunks for 1994
    python -m app.ingestion.historical.cli --year 1994 --resume
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import generate_chunks
from app.ingestion.historical.manifest import HistoricalExtractionManifest
from app.ingestion.historical.models import ExtractionChunk, ExtractionConfig


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with explicit scope requirements."""
    parser = argparse.ArgumentParser(
        description="FloodPulse Historical Meteorological Extraction CLI (Open-Meteo ERA5 Reanalysis)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    scope_group = parser.add_argument_group("Extraction Scope (At least one required)")
    scope_group.add_argument("--year", type=int, help="Single calendar year to extract (1969–1994)")
    scope_group.add_argument("--start-year", type=int, help="Start year of range (1969–1994)")
    scope_group.add_argument("--end-year", type=int, help="End year of range (1969–1994)")
    scope_group.add_argument("--resume", action="store_true", help="Resume pending/failed chunks in manifest")

    filter_group = parser.add_argument_group("Chunk Filters & Controls")
    filter_group.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    filter_group.add_argument("--batch-size", type=int, default=10, help="Grid cells per batch")
    filter_group.add_argument("--limit", type=int, help="Maximum number of chunks to process in this run")
    filter_group.add_argument("--dry-run", action="store_true", help="Execute without persisting raw files to disk")
    filter_group.add_argument("--pacing", type=float, default=10.0, help="Minimum request interval between HTTP requests (seconds)")
    filter_group.add_argument(
        "--force-full-range",
        action="store_true",
        help="Explicit confirmation required to target the complete 26-year range (1969–1994)",
    )

    path_group = parser.add_argument_group("Storage Paths")
    path_group.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/era5_historical"),
        help="Base directory for raw compressed payloads",
    )
    path_group.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("data/raw/era5_historical/extraction_manifest.json"),
        help="Path to persistent JSON extraction manifest",
    )

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point with strict safety guard validation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Safety Guard: Require explicit scope
    has_year = args.year is not None
    has_range = args.start_year is not None and args.end_year is not None
    has_resume = args.resume

    if not (has_year or has_range or has_resume):
        print(
            "ERROR: Explicit scope is required. You must specify either --year, "
            "both --start-year and --end-year, or --resume.\n"
            "Accidental unconstrained 26-year extraction is prohibited.",
            file=sys.stderr,
        )
        return 1

    # Determine year bounds
    if has_year:
        start_year = args.year
        end_year = args.year
    elif has_range:
        start_year = args.start_year
        end_year = args.end_year
    else:
        # Resume mode without explicit years: default to 1969-1994 but check manifest
        start_year = 1969
        end_year = 1994

    if start_year > end_year:
        print(f"ERROR: --start-year ({start_year}) cannot exceed --end-year ({end_year})", file=sys.stderr)
        return 1

    # 2. Safety Guard: Full 26-year extraction protection
    if start_year == 1969 and end_year == 1994 and not args.limit and not args.dry_run and not args.force_full_range:
        print(
            "SAFETY GUARD: Target scope covers the complete 26-year historical period (858 chunks) "
            "without a --limit or --dry-run.\n"
            "To execute full bulk extraction, you must explicitly pass --force-full-range.",
            file=sys.stderr,
        )
        return 1

    # Initialize configuration
    config = ExtractionConfig(
        raw_base_dir=args.output_dir,
        manifest_path=args.manifest_path,
        batch_size=args.batch_size,
        min_request_interval_seconds=args.pacing,
        pacing_delay_seconds=args.pacing,
        dry_run=args.dry_run,
    )

    manifest = HistoricalExtractionManifest(config.manifest_path)
    manifest.recover_stale_running_chunks(raw_base_dir=config.raw_base_dir)
    extractor = HistoricalExtractor(config=config, manifest=manifest)

    # Generate candidate chunks
    all_chunks = generate_chunks(start_year=start_year, end_year=end_year, batch_size=config.batch_size)

    # Apply batch filter if specified
    if args.batch is not None:
        all_chunks = [c for c in all_chunks if c.batch_id == args.batch]

    manifest.register_chunks(all_chunks)

    # Apply resume filter if requested
    if args.resume:
        target_chunks = manifest.get_pending_or_retryable_chunks(all_chunks)
    else:
        target_chunks = all_chunks

    print("=" * 70)
    print("  FloodPulse Historical ERA5 Meteorological Extraction")
    print("=" * 70)
    print(f"  Target Period:   {start_year} to {end_year}")
    print(f"  Batch Filter:    {args.batch if args.batch else 'All batches (1–33)'}")
    print(f"  Candidate Chunks:{len(all_chunks)}")
    print(f"  Pending/Target:  {len(target_chunks)}")
    print(f"  Limit:           {args.limit if args.limit else 'No limit'}")
    print(f"  Dry Run:         {args.dry_run}")
    print(f"  Pacing Delay:    {args.pacing}s")
    print(f"  Output Dir:      {config.raw_base_dir}")
    print(f"  Manifest:        {config.manifest_path}")
    print("-" * 70)

    if not target_chunks:
        print("No pending chunks to extract. All candidate chunks are already completed.")
        return 0

    results = extractor.extract_chunks(target_chunks, limit=args.limit)

    print("\nExtraction Summary:")
    print(f"  Total Processed: {results['total_processed']}")
    print(f"  Succeeded:       {results['succeeded']}")
    print(f"  Skipped (Cached):{results['skipped']}")
    print(f"  Failed:          {results['failed']}")
    print("  Manifest Statuses:")
    for status, count in results["manifest_summary"].items():
        print(f"    - {status}: {count}")
    print("=" * 70)

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run_cli())
