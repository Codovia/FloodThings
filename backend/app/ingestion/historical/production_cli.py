"""
Command-Line Interface (CLI) for full historical ERA5 production extraction and processing.

Enforces strict safety controls:
- Requires explicit scope flags (--start-year and --end-year, or --production).
- Defaults to --dry-run.
- Prohibits live execution without explicit --confirm.
- Preflight audit printed before any execution.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from app.ingestion.historical.daily_models import DailyProcessingConfig
from app.ingestion.historical.models import ExtractionConfig
from app.ingestion.historical.production_runner import ProductionHistoricalRunner


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for production historical runner."""
    parser = argparse.ArgumentParser(
        description="FloodPulse Historical ERA5 Production Extraction & Processing CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    scope_group = parser.add_argument_group("Production Scope")
    scope_group.add_argument(
        "--production",
        action="store_true",
        help="Explicitly target the complete 26-year historical period (1969–1994)",
    )
    scope_group.add_argument("--start-year", type=int, help="Start year of historical range (1969–1994)")
    scope_group.add_argument("--end-year", type=int, help="End year of historical range (1969–1994)")
    scope_group.add_argument("--year", type=int, help="Single year to run (1969–1994)")

    filter_group = parser.add_argument_group("Execution Controls")
    filter_group.add_argument("--batch", type=int, help="Filter to a single spatial batch ID (1–33)")
    filter_group.add_argument("--limit", type=int, help="Limit number of chunks to process")
    filter_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Execute preflight audit only (default: True, zero API requests, zero disk writes)",
    )
    filter_group.add_argument(
        "--live",
        action="store_true",
        help="Execute live extraction/processing (requires --confirm)",
    )
    filter_group.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required to execute live production runs",
    )
    filter_group.add_argument(
        "--pacing",
        type=float,
        default=10.0,
        help="Minimum request interval between HTTP requests (seconds)",
    )

    path_group = parser.add_argument_group("Storage Configuration")
    path_group.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw/era5_historical"),
        help="Base directory for raw compressed payloads",
    )
    path_group.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed/era5_daily"),
        help="Base directory for daily Parquet datasets",
    )

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point with strict safety guard validation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Resolve Scope
    if args.production:
        start_year = 1969
        end_year = 1994
    elif args.year is not None:
        start_year = args.year
        end_year = args.year
    elif args.start_year is not None and args.end_year is not None:
        start_year = args.start_year
        end_year = args.end_year
    else:
        print(
            "ERROR: Explicit production scope is required.\n"
            "Specify either --production, --year <YYYY>, or both --start-year <YYYY> and --end-year <YYYY>.\n"
            "Unbounded execution is prohibited.",
            file=sys.stderr,
        )
        return 1

    if start_year > end_year:
        print(f"ERROR: --start-year ({start_year}) cannot exceed --end-year ({end_year})", file=sys.stderr)
        return 1

    # 2. Safety Guard: Live execution confirmation
    is_live = args.live
    is_dry_run = not is_live

    if is_live and not args.confirm:
        print(
            "SAFETY GUARD: Live execution requested without --confirm.\n"
            "Live bulk extraction will issue real API requests and persist files.\n"
            "To proceed with live execution, you must explicitly pass --confirm.",
            file=sys.stderr,
        )
        return 1

    # Initialize runner
    extraction_config = ExtractionConfig(
        raw_base_dir=args.raw_dir,
        manifest_path=args.raw_dir / "extraction_manifest.json",
        min_request_interval_seconds=args.pacing,
        pacing_delay_seconds=args.pacing,
    )
    daily_config = DailyProcessingConfig(
        raw_base_dir=args.raw_dir,
        processed_base_dir=args.processed_dir,
        manifest_path=args.processed_dir / "processing_manifest.json",
    )

    runner = ProductionHistoricalRunner(
        extraction_config=extraction_config,
        daily_config=daily_config,
    )

    # 3. Preflight Audit
    audit = runner.audit_inventory(start_year, end_year)

    print("=" * 75)
    print("  FloodPulse Historical ERA5 Production Preflight & Runner")
    print("=" * 75)
    print(f"  Target Scope:              {start_year} to {end_year}")
    print(f"  Authoritative Grid Cells:  {audit.authoritative_cells_count}")
    print(f"  Extraction-Eligible Cells: {audit.eligible_cells_count}")
    print(f"  Source-Excluded Cells:     {audit.excluded_cells_count}")
    print(f"  Spatial Batches:           {audit.total_batches}")
    print(f"  Total Chunks:              {audit.total_chunks}")
    print(f"  Pacing Interval:           {args.pacing}s")
    print(f"  Execution Mode:            {'DRY RUN ONLY' if is_dry_run else 'LIVE EXECUTION'}")
    print("-" * 75)
    print("  Raw Extraction State:")
    print(f"    - Valid Cached Chunks:   {len(audit.valid_raw_chunks)}")
    print(f"    - Remaining Chunks:      {len(audit.missing_raw_chunks)}")
    print(f"    - Invalid Chunks:        {len(audit.invalid_raw_chunks)}")
    print("  Daily Processing State:")
    print(f"    - Valid Cached Chunks:   {len(audit.valid_processed_chunks)}")
    print(f"    - Remaining Chunks:      {len(audit.missing_processed_chunks)}")
    print(f"    - Invalid Chunks:        {len(audit.invalid_processed_chunks)}")
    print("-" * 75)
    print("  Storage Metrics & Estimates:")
    print(f"    - Observed Raw Compressed:   min={audit.observed_raw_compressed_min:,} B, max={audit.observed_raw_compressed_max:,} B, mean={audit.observed_raw_compressed_mean:,.0f} B")
    print(f"    - Estimated {audit.total_chunks} Raw Compressed: {audit.estimated_total_raw_compressed_bytes / (1024*1024):.2f} MB")
    print(f"    - Observed Raw Uncompressed: min={audit.observed_raw_uncompressed_min:,} B, max={audit.observed_raw_uncompressed_max:,} B, mean={audit.observed_raw_uncompressed_mean:,.0f} B")
    print(f"    - Estimated {audit.total_chunks} Raw Uncomp.: {audit.estimated_total_raw_uncompressed_bytes / (1024*1024*1024):.3f} GB")
    print(f"    - Observed Daily Parquet:    {audit.observed_daily_parquet_bytes:,} B (test chunk)")
    print(f"    - Estimated Daily Parquet:   {audit.estimated_total_daily_parquet_bytes / (1024*1024):.2f} MB ({audit.estimated_total_daily_rows:,} rows)")
    print(f"    - Available Disk Space:      {audit.available_disk_bytes / (1024*1024*1024):.2f} GB")
    print("=" * 75)

    if is_dry_run:
        print("\n  DRY-RUN COMPLETE: Zero API requests made, zero database writes made.")
        print("  All existing files and manifests remain untouched.")
        print("=" * 75)
        return 0

    # Live run
    res = runner.run_production(
        start_year=start_year,
        end_year=end_year,
        batch_filter=args.batch,
        limit=args.limit,
        dry_run=False,
    )
    print(f"\nLive Execution Summary: {res}")
    return 0 if res["failed_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run_cli())
