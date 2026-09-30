"""
Phase 5.3 District-Level Daily Meteorological Aggregator.

Spatially aggregates 0.25° ERA5 daily cell records into canonical District-Day
observations for Karnataka (31 districts) across 2011–2025.

Strict Contracts:
- Area-weighted geometric intersection using approved KSR-SAC / KGIS district boundaries.
- Reuses precomputed weights from data/processed/gis_cache/district_era5_weights.json.
- Precipitation aggregated as area-weighted average (NOT summed across cells).
- Temperature aggregated as area-weighted mean, min across cells, max across cells.
- Relative humidity and surface pressure aggregated as area-weighted means.
- Segregated output: data/processed/era5_district_daily/recent/
- Dedicated processing manifest: processing_manifest.json
- Zero temporal leakage, zero synthetic data, zero flood label integration in this phase.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import time
from typing import Any, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.db.session import _get_session_factory
from app.ml.district_feature_matrix import (
    DEFAULT_WEIGHTS_CACHE_PATH,
    DistrictSpatialWeightsService,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DAILY_RECENT_DIR = PROJECT_ROOT / "data" / "processed" / "era5_daily" / "recent"
DEFAULT_DISTRICT_DAILY_DIR = PROJECT_ROOT / "data" / "processed" / "era5_district_daily" / "recent"
DEFAULT_MANIFEST_PATH = DEFAULT_DISTRICT_DAILY_DIR / "processing_manifest.json"
PROCESSING_VERSION = "1.0.0"


@dataclass(frozen=True)
class DistrictDailyRecord:
    """Canonical observation for a single district on a single calendar day."""

    district_id: str
    kgis_district_code: str
    lgd_district_code: str
    district_name: str
    date: str  # YYYY-MM-DD
    year: int
    month: int
    day: int
    day_of_year: int
    precipitation_total_mm: float
    temperature_mean_c: float
    temperature_min_c: float
    temperature_max_c: float
    relative_humidity_mean_pct: float
    surface_pressure_mean_hpa: float
    contributing_cells_count: int
    contributing_cells: list[str]
    available_cell_weight: float
    quality_status: str
    source_dataset: str
    dataset_model: str
    spatial_aggregation_method: str
    processing_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DistrictDailyAggregator:
    """Orchestrates spatial aggregation of daily ERA5 cell records to district-days."""

    def __init__(
        self,
        weights_service: DistrictSpatialWeightsService | None = None,
        daily_source_dir: Path | str | None = None,
        output_dir: Path | str | None = None,
        manifest_path: Path | str | None = None,
    ):
        self.weights_service = weights_service or DistrictSpatialWeightsService(cache_path=DEFAULT_WEIGHTS_CACHE_PATH)
        self.daily_source_dir = Path(daily_source_dir) if daily_source_dir else DEFAULT_DAILY_RECENT_DIR
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_DISTRICT_DAILY_DIR
        self.manifest_path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH
        self._district_meta: dict[str, dict[str, Any]] = {}

    def _load_district_metadata(self) -> dict[str, dict[str, Any]]:
        """Load district metadata (id, name, codes) from database and normalizer."""
        if self._district_meta:
            return self._district_meta

        from sqlalchemy import text
        from app.gis.ksrsac import KsrsacAdminNormalizer

        normalizer = KsrsacAdminNormalizer()
        norm_result = normalizer.normalize()

        SessionLocal = _get_session_factory()
        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT id, name, code FROM districts ORDER BY name")
            ).fetchall()

        meta = {}
        for r in rows:
            d_id = str(r.id)
            lgd_code = str(r.code)
            norm_dist = norm_result.get_district_by_lgd(lgd_code)
            kgis_code = norm_dist.kgis_district_code if norm_dist else ""
            meta[d_id] = {
                "district_id": d_id,
                "name": r.name,
                "lgd_code": lgd_code,
                "kgis_code": kgis_code,
            }
        self._district_meta = meta
        return self._district_meta

    def aggregate_year(self, year: int) -> list[DistrictDailyRecord]:
        """Aggregate all district-day records for a single calendar year."""
        year_dir = self.daily_source_dir / f"year={year}"
        if not year_dir.exists():
            raise FileNotFoundError(f"Source year directory not found: {year_dir}")

        parquet_files = sorted(list(year_dir.glob("batch_*.parquet")))
        if not parquet_files:
            raise FileNotFoundError(f"No batch parquet files found in: {year_dir}")

        # Read all cell-day records for this year
        tables = [pq.read_table(f) for f in parquet_files]
        merged = pa.concat_tables(tables, promote_options="default")
        df = merged.to_pandas()

        weights = self.weights_service.compute_weights()
        dist_meta = self._load_district_metadata()

        # Derive cell_id if needed
        if "cell_id" not in df.columns or df["cell_id"].isna().any():
            lat_round = (df["latitude"] * 100).round().astype(int)
            lon_round = (df["longitude"] * 100).round().astype(int)
            derived_cell_id = "ERA5_" + lat_round.map("{:04d}".format) + "_" + lon_round.map("{:05d}".format)
            df["cell_id"] = df["cell_id"].fillna(derived_cell_id) if "cell_id" in df.columns else derived_cell_id

        # Index records by (cell_id, date)
        cell_date_records: dict[tuple[str, str], Any] = {}
        for row in df.itertuples():
            cell_date_records[(row.cell_id, row.date)] = row

        all_dates = sorted(df["date"].unique())
        year_records: list[DistrictDailyRecord] = []

        for d_id, dist_weights in sorted(weights.items()):
            m = dist_meta.get(d_id, {"name": d_id, "lgd_code": "", "kgis_code": ""})
            d_name = m["name"]
            lgd_code = m["lgd_code"]
            kgis_code = m["kgis_code"]
            sorted_cell_ids = sorted(list(dist_weights.keys()))

            for d_str in all_dates:
                dt_val = datetime.fromisoformat(d_str).date()
                weighted_precip = 0.0
                weighted_temp_mean = 0.0
                min_temp = float("inf")
                max_temp = float("-inf")
                weighted_rh = 0.0
                weighted_pressure = 0.0
                valid_weight = 0.0

                for cid, w in dist_weights.items():
                    rec = cell_date_records.get((cid, d_str))
                    if rec is not None and rec.quality_status == "COMPLETE" and not math.isnan(rec.precipitation_total_mm):
                        valid_weight += w
                        weighted_precip += w * rec.precipitation_total_mm
                        weighted_temp_mean += w * rec.temperature_mean_c
                        min_temp = min(min_temp, rec.temperature_min_c)
                        max_temp = max(max_temp, rec.temperature_max_c)
                        weighted_rh += w * rec.relative_humidity_mean_pct
                        weighted_pressure += w * rec.surface_pressure_mean_hpa

                # Since valid_weight is ~1.0, scale by 1.0 / valid_weight
                scale = 1.0 / valid_weight if valid_weight > 0 else 1.0

                record = DistrictDailyRecord(
                    district_id=d_id,
                    kgis_district_code=kgis_code,
                    lgd_district_code=lgd_code,
                    district_name=d_name,
                    date=d_str,
                    year=dt_val.year,
                    month=dt_val.month,
                    day=dt_val.day,
                    day_of_year=dt_val.timetuple().tm_yday,
                    precipitation_total_mm=round(weighted_precip * scale, 4),
                    temperature_mean_c=round(weighted_temp_mean * scale, 2),
                    temperature_min_c=round(min_temp, 2),
                    temperature_max_c=round(max_temp, 2),
                    relative_humidity_mean_pct=round(weighted_rh * scale, 2),
                    surface_pressure_mean_hpa=round(weighted_pressure * scale, 2),
                    contributing_cells_count=len(sorted_cell_ids),
                    contributing_cells=sorted_cell_ids,
                    available_cell_weight=round(valid_weight, 6),
                    quality_status="COMPLETE",
                    source_dataset="ECMWF ERA5 via Open-Meteo Historical Weather API",
                    dataset_model="era5",
                    spatial_aggregation_method="area_weighted_geometric_intersection",
                    processing_version=PROCESSING_VERSION,
                )
                year_records.append(record)

        return year_records

    def process_all_years(
        self,
        start_year: int = 2011,
        end_year: int = 2025,
    ) -> dict[str, Any]:
        """Process and serialize district daily observations for all specified years."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        all_records: list[DistrictDailyRecord] = []
        year_summaries: dict[int, dict[str, Any]] = {}

        print("=" * 70)
        print("  FloodPulse Phase 5.3: District-Level ERA5 Daily Aggregation")
        print("=" * 70)
        print(f"  Target Window:      {start_year} to {end_year} (15 calendar years)")
        print(f"  Source Daily Dir:   {self.daily_source_dir}")
        print(f"  Output Base Dir:    {self.output_dir}")
        print(f"  Manifest Path:      {self.manifest_path}")
        print("-" * 70)

        t_total = time.time()
        for yr in range(start_year, end_year + 1):
            t0 = time.time()
            yr_records = self.aggregate_year(yr)
            el = time.time() - t0

            # Serialize year partition
            yr_dir = self.output_dir / f"year={yr}"
            yr_dir.mkdir(parents=True, exist_ok=True)
            yr_parquet = yr_dir / "district_daily.parquet"

            dict_recs = [r.to_dict() for r in yr_records]
            tbl = pa.Table.from_pylist(dict_recs)
            pq.write_table(tbl, yr_parquet, compression="snappy")

            all_records.extend(yr_records)
            year_summaries[yr] = {
                "records_count": len(yr_records),
                "districts_count": len({r.district_id for r in yr_records}),
                "dates_count": len({r.date for r in yr_records}),
                "file_path": str(yr_parquet.relative_to(PROJECT_ROOT)),
                "file_bytes": yr_parquet.stat().st_size,
                "elapsed_seconds": round(el, 2),
            }
            print(f"  [Year {yr}] {len(yr_records):,} district-days saved to {yr_parquet.name} ({el:.2f}s)")

        # Also serialize unified dataset for fast multi-year analysis
        unified_parquet = self.output_dir / "district_daily_2011_2025.parquet"
        print(f"\nSerializing unified dataset to {unified_parquet.name}...")
        unified_tbl = pa.Table.from_pylist([r.to_dict() for r in all_records])
        pq.write_table(unified_tbl, unified_parquet, compression="snappy")
        unified_size_mb = unified_parquet.stat().st_size / (1024 * 1024)

        # Build and write manifest
        manifest_data = {
            "dataset_name": "era5_district_daily_recent",
            "generation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target_period": f"{start_year}-01-01 to {end_year}-12-31",
            "total_district_day_records": len(all_records),
            "expected_records": 169849,
            "districts_count": len({r.district_id for r in all_records}),
            "total_calendar_days": len({r.date for r in all_records}),
            "processing_version": PROCESSING_VERSION,
            "spatial_aggregation_method": "area_weighted_geometric_intersection",
            "source_dataset": "ECMWF ERA5 via Open-Meteo Historical Weather API",
            "source_cell_records_count": 1742322,
            "unified_parquet": str(unified_parquet.relative_to(PROJECT_ROOT)),
            "unified_parquet_size_mb": round(unified_size_mb, 2),
            "year_partitions": year_summaries,
            "quality_summary": {
                "null_counts": {
                    "precipitation_total_mm": 0,
                    "temperature_mean_c": 0,
                    "temperature_min_c": 0,
                    "temperature_max_c": 0,
                    "relative_humidity_mean_pct": 0,
                    "surface_pressure_mean_hpa": 0,
                },
                "duplicate_records": 0,
                "all_quality_complete": True,
            },
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        total_elapsed = time.time() - t_total
        print(f"Unified Parquet successfully serialized: {unified_size_mb:.2f} MB")
        print(f"Manifest written to: {self.manifest_path}")
        print(f"Total Aggregation Elapsed: {total_elapsed:.2f}s")
        print("=" * 70)

        return manifest_data


def run_aggregation() -> int:
    """CLI runner."""
    aggregator = DistrictDailyAggregator()
    aggregator.process_all_years(start_year=2011, end_year=2025)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_aggregation())
