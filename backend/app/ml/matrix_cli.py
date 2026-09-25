"""
Command-line interface for District x Day Historical ML Feature Matrix (Phase 4).

Usage:
  python -m app.ml.matrix_cli build --start-date 1969-07-14 --end-date 1975-12-31 --output data/processed/ml_matrix/district_day_feature_matrix.parquet
  python -m app.ml.matrix_cli audit --parquet-path data/processed/ml_matrix/district_day_feature_matrix.parquet
  python -m app.ml.matrix_cli verify-weights
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq

from app.ml.district_feature_matrix import (
    DEFAULT_PARQUET_OUTPUT_PATH,
    DistrictFeatureMatrixBuilder,
    DistrictSpatialWeightsService,
    TemporalLeakageAuditor,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("matrix_cli")


def cmd_build(args: argparse.Namespace) -> int:
    """Build canonical District x Day feature matrix."""
    builder = DistrictFeatureMatrixBuilder(lead_time_days=args.lead_time)
    obs_win = (args.obs_start, args.obs_end) if args.obs_start and args.obs_end else None

    logger.info(
        "Building feature matrix: %s to %s (lead_time=%d, obs_window=%s)",
        args.start_date,
        args.end_date,
        args.lead_time,
        obs_win,
    )

    out_p = Path(args.output) if args.output else DEFAULT_PARQUET_OUTPUT_PATH
    records = builder.build_matrix(
        start_date=args.start_date,
        end_date=args.end_date,
        observation_window=obs_win,
        output_parquet_path=out_p,
    )

    audit = builder.generate_quality_audit(records)
    print("\n" + "=" * 60)
    print("HISTORICAL DISTRICT x DAY ML FEATURE MATRIX AUDIT")
    print("=" * 60)
    print(json.dumps(audit, indent=2))
    print("=" * 60)
    print(f"Dataset successfully serialized to: {out_p}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Run quality audit on an existing Parquet feature matrix."""
    p_path = Path(args.parquet_path)
    if not p_path.exists():
        logger.error("Parquet file does not exist: %s", p_path)
        return 1

    table = pq.read_table(p_path)
    df = table.to_pandas()
    print("\n" + "=" * 60)
    print(f"AUDITING DATASET: {p_path} ({len(df)} rows, {len(df.columns)} columns)")
    print("=" * 60)
    print(f"Total Rows: {len(df)}")
    print(f"Date Range: {df['target_date'].min()} to {df['target_date'].max()}")
    print(f"Unique Districts: {df['district_id'].nunique()}")
    print(f"Label Distribution:\n{df['label_state'].value_counts().to_string()}")
    print(f"Complete 30d Weather Count: {df['is_weather_complete_30d'].sum()} / {len(df)}")
    print(f"Terrain Coverage: {(df['elevation_mean_m'].notna().sum() / len(df) * 100):.2f}%")
    print(f"Hydrology Coverage: {(df['major_basin_count'].notna().sum() / len(df) * 100):.2f}%")
    print("=" * 60)
    return 0


def cmd_verify_weights(args: argparse.Namespace) -> int:
    """Verify and print summary of district area weights."""
    service = DistrictSpatialWeightsService()
    weights = service.compute_weights(force=args.force)

    print("\n" + "=" * 60)
    print(f"DISTRICT SPATIAL AREA WEIGHTS ({len(weights)} districts)")
    print("=" * 60)
    for d_id, w_map in sorted(weights.items(), key=lambda x: len(x[1]), reverse=True):
        sum_w = sum(w_map.values())
        print(f"District {d_id[:8]}...: {len(w_map):2d} cells, sum(weights) = {sum_w:.6f}")
    print("=" * 60)
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    """Export a deterministic validation sample from real data for manual inspection."""
    src_p = Path(args.source_parquet)
    if not src_p.exists():
        logger.error("Source parquet does not exist: %s", src_p)
        return 1

    table = pq.read_table(src_p)
    df = table.to_pandas()

    # Filter deterministically
    mask = (df["target_year"] == args.year) & (df["district_name"].isin(args.districts))
    sample_df = df[mask].sort_values(by=["district_name", "target_date"]).reset_index(drop=True)

    if sample_df.empty:
        logger.error("No records matched filter: year=%s, districts=%s", args.year, args.districts)
        return 1

    out_p = Path(args.output_parquet)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_table = pa.Table.from_pandas(sample_df)
    pq.write_table(out_table, out_p, compression="snappy")
    logger.info("Saved %d sample rows to %s", len(sample_df), out_p)

    out_json = Path(args.output_json)
    flood_cnt = int((sample_df["label_state"] == "FLOOD").sum())
    unknown_cnt = int((sample_df["label_state"] == "UNKNOWN").sum())

    sample_summary = {
        "sample_description": "Deterministic validation sample from real historical data for manual alignment inspection",
        "year": args.year,
        "districts": sorted(args.districts),
        "total_rows": len(sample_df),
        "flood_rows": flood_cnt,
        "unknown_rows": unknown_cnt,
        "columns_count": len(sample_df.columns),
        "date_range": [str(sample_df["target_date"].min()), str(sample_df["target_date"].max())],
        "sample_positive_events": sample_df[sample_df["label_state"] == "FLOOD"][
            ["district_name", "target_date", "source_event_ids", "precip_1d_mm", "precip_3d_sum_mm", "precip_7d_sum_mm", "elevation_mean_m"]
        ].to_dict(orient="records"),
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(sample_summary, f, indent=2, default=str)
    logger.info("Saved validation sample summary JSON to %s", out_json)

    print("\n" + "=" * 60)
    print("REAL DATA DETERMINISTIC VALIDATION SAMPLE EXPORT")
    print("=" * 60)
    print(f"Sample Rows: {len(sample_df)}")
    print(f"Districts: {sorted(args.districts)}")
    print(f"Date Range: {sample_df['target_date'].min()} to {sample_df['target_date'].max()}")
    print(f"FLOOD Labels: {flood_cnt}")
    print(f"UNKNOWN Labels: {unknown_cnt}")
    print(f"Parquet Output: {out_p}")
    print(f"JSON Audit: {out_json}")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="District x Day ML Feature Matrix CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    p_build = subparsers.add_parser("build", help="Build and serialize feature matrix")
    p_build.add_argument("--start-date", type=str, default="1969-01-01", help="Target start date (YYYY-MM-DD)")
    p_build.add_argument("--end-date", type=str, default="1994-12-31", help="Target end date (YYYY-MM-DD)")
    p_build.add_argument("--lead-time", type=int, default=1, help="Lead time in days (default: 1)")
    p_build.add_argument("--obs-start", type=str, default=None, help="Observation window start date")
    p_build.add_argument("--obs-end", type=str, default=None, help="Observation window end date")
    p_build.add_argument("--output", type=str, default=str(DEFAULT_PARQUET_OUTPUT_PATH), help="Output parquet path")
    p_build.set_defaults(func=cmd_build)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit existing parquet matrix")
    p_audit.add_argument("--parquet-path", type=str, default=str(DEFAULT_PARQUET_OUTPUT_PATH), help="Parquet path")
    p_audit.set_defaults(func=cmd_audit)

    # verify-weights
    p_weights = subparsers.add_parser("verify-weights", help="Verify district-cell area weights")
    p_weights.add_argument("--force", action="store_true", help="Force recomputation")
    p_weights.set_defaults(func=cmd_verify_weights)

    # sample
    p_sample = subparsers.add_parser("sample", help="Export deterministic validation sample from real data")
    p_sample.add_argument("--source-parquet", type=str, default=str(DEFAULT_PARQUET_OUTPUT_PATH), help="Source parquet")
    p_sample.add_argument("--output-parquet", type=str, default="data/processed/ml_matrix/validation_sample_district_day.parquet", help="Output parquet")
    p_sample.add_argument("--output-json", type=str, default="data/processed/ml_matrix/validation_sample_district_day.json", help="Output JSON")
    p_sample.add_argument("--year", type=int, default=1974, help="Target year")
    p_sample.add_argument("--districts", nargs="+", default=["Belagavi", "Kodagu", "Raichur"], help="Sample districts")
    p_sample.set_defaults(func=cmd_sample)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
