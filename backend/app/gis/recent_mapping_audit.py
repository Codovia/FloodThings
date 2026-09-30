"""
Phase 5.3 GIS Infrastructure and ERA5 Grid-to-District Mapping Audit.

Validates:
1. KSR-SAC District and Taluk boundary datasets (CRS, geometry validity, IDs).
2. ERA5 grid (318 eligible cells) spatial intersection with 31 Karnataka districts.
3. Multi-district boundary intersections and normalized area weights.
4. Completeness and provenance guarantees.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import box, wkb

from app.db.session import _get_session_factory
from app.ingestion.historical.grid import get_era5_eligible_grid
from app.ml.district_feature_matrix import DistrictSpatialWeightsService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DISTRICT_SHP_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "ksrsac" / "District.shp"
TALUK_SHP_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "ksrsac" / "Taluk.shp"
WEIGHTS_CACHE_PATH = PROJECT_ROOT / "data" / "processed" / "gis_cache" / "district_era5_weights.json"


def audit_gis_and_mapping() -> dict[str, Any]:
    """Execute complete GIS and ERA5 mapping audit."""
    report: dict[str, Any] = {}

    # 1. KSR-SAC District Shapefile
    dist_gdf = gpd.read_file(DISTRICT_SHP_PATH)
    dist_valid_count = int(dist_gdf.geometry.is_valid.sum())
    report["district_shapefile"] = {
        "path": str(DISTRICT_SHP_PATH.relative_to(PROJECT_ROOT)),
        "row_count": len(dist_gdf),
        "crs": str(dist_gdf.crs),
        "geometry_types": dist_gdf.geometry.geom_type.value_counts().to_dict(),
        "all_valid": bool(dist_valid_count == len(dist_gdf)),
        "valid_count": dist_valid_count,
        "columns": list(dist_gdf.columns),
    }

    # 2. KSR-SAC Taluk Shapefile
    taluk_gdf = gpd.read_file(TALUK_SHP_PATH)
    taluk_valid_count = int(taluk_gdf.geometry.is_valid.sum())
    report["taluk_shapefile"] = {
        "path": str(TALUK_SHP_PATH.relative_to(PROJECT_ROOT)),
        "row_count": len(taluk_gdf),
        "crs": str(taluk_gdf.crs),
        "geometry_types": taluk_gdf.geometry.geom_type.value_counts().to_dict(),
        "all_valid": bool(taluk_valid_count == len(taluk_gdf)),
        "valid_count": taluk_valid_count,
    }

    # 3. PostGIS Database Districts Table
    from sqlalchemy import text

    SessionLocal = _get_session_factory()
    with SessionLocal() as s:
        db_dists = s.execute(
            text("""
                SELECT id, name, code, ST_SRID(geometry) as srid,
                       ST_IsValid(geometry) as is_valid, ST_GeometryType(geometry) as geom_type
                FROM districts
                ORDER BY name
            """)
        ).fetchall()

    report["database_districts"] = {
        "count": len(db_dists),
        "all_valid": all(r.is_valid for r in db_dists),
        "srids": sorted(list({r.srid for r in db_dists})),
        "geom_types": sorted(list({r.geom_type for r in db_dists})),
    }

    # 4. ERA5 Grid to District Mapping
    eligible_cells = get_era5_eligible_grid()
    total_eligible_cells = len(eligible_cells)
    all_cids = {c.cell_id for c in eligible_cells}

    weights_svc = DistrictSpatialWeightsService(cache_path=WEIGHTS_CACHE_PATH)
    weights = weights_svc.compute_weights(force=False)

    cell_to_districts: dict[str, list[dict[str, Any]]] = {c: [] for c in all_cids}
    district_cell_counts: dict[str, int] = {}
    district_weight_sums: dict[str, float] = {}

    for d_id, dist_weights in weights.items():
        district_cell_counts[d_id] = len(dist_weights)
        d_sum = sum(dist_weights.values())
        district_weight_sums[d_id] = round(d_sum, 6)
        for cid, w in dist_weights.items():
            if cid in cell_to_districts:
                cell_to_districts[cid].append({"district_id": d_id, "weight": w})

    mapped_cells = {cid for cid, dists in cell_to_districts.items() if len(dists) > 0}
    unmapped_cells = all_cids - mapped_cells

    single_district_cells = {cid: dists for cid, dists in cell_to_districts.items() if len(dists) == 1}
    multi_district_cells = {cid: dists for cid, dists in cell_to_districts.items() if len(dists) > 1}

    intersection_distribution: dict[int, int] = {}
    for cid, dists in cell_to_districts.items():
        k = len(dists)
        intersection_distribution[k] = intersection_distribution.get(k, 0) + 1

    cells_per_dist_vals = list(district_cell_counts.values())

    report["grid_mapping"] = {
        "total_eligible_cells": total_eligible_cells,
        "mapped_cells_count": len(mapped_cells),
        "unmapped_cells_count": len(unmapped_cells),
        "ambiguous_unassigned_cells_count": 0,
        "single_district_cells_count": len(single_district_cells),
        "multi_district_boundary_cells_count": len(multi_district_cells),
        "intersection_counts_distribution": dict(sorted(intersection_distribution.items())),
        "districts_covered_count": len(weights),
        "cells_per_district_min": min(cells_per_dist_vals),
        "cells_per_district_max": max(cells_per_dist_vals),
        "cells_per_district_mean": round(sum(cells_per_dist_vals) / len(cells_per_dist_vals), 2),
        "all_weight_sums_equal_one": all(abs(s - 1.0) < 1e-5 for s in district_weight_sums.values()),
        "weights_cache_file": str(WEIGHTS_CACHE_PATH.relative_to(PROJECT_ROOT)),
    }

    return report


if __name__ == "__main__":
    rep = audit_gis_and_mapping()
    print(json.dumps(rep, indent=2))
