"""
Zonal terrain statistics extraction for Karnataka administrative districts
and HydroBASINS Level-7 sub-basins.

Extracts real elevation and Horn metric slope statistics from karnataka_dem.vrt
using exact polygon intersections, and persists derived features with full provenance.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
import shapely.wkb
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.models.geography import District
from app.db.models.hydrology import SubBasin
from app.db.models.terrain import TerrainDataset, TerrainStatistic
from app.db.session import _get_engine, _get_session_factory
from app.gis.terrain_engine import (
    calculate_elevation_statistics,
    calculate_slope_statistics,
    compute_horn_slope,
)

logger = logging.getLogger(__name__)

PROCESSING_VERSION = "1.0.0"
GEOMETRY_VERSION = "KSR-SAC_2024 / HydroSHEDS_v1.0"
PROCESSING_METHOD = "Horn 1981 metric slope + exact polygon rasterization"
PROCESSING_CRS = "EPSG:4326 (Horizontal) / EGM2008 (Vertical) with geodesic metric scaling"
DEM_VERSION = "COP-DEM_GLO-30-DGED_2021"


def register_copernicus_dem_dataset(vrt_path: Path) -> uuid.UUID:
    """Register or retrieve the Copernicus DEM GLO-30 dataset entry in terrain_datasets."""
    session_factory = _get_session_factory()
    with session_factory() as session:
        # Check if already registered
        stmt = select(TerrainDataset).where(
            TerrainDataset.name == "Copernicus DEM GLO-30"
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing.id

        # Insert new dataset record
        dataset_id = uuid.uuid4()
        with rasterio.open(vrt_path) as src:
            bounds = src.bounds
            res_str = f"{src.res[0]*3600:.1f} arc-sec (~30m)"

        coverage_wkt = (
            f"MULTIPOLYGON((({bounds.left} {bounds.bottom}, {bounds.right} {bounds.bottom}, "
            f"{bounds.right} {bounds.top}, {bounds.left} {bounds.top}, {bounds.left} {bounds.bottom})))"
        )

        insert_stmt = text(
            """
            INSERT INTO terrain_datasets (id, name, resolution, file_reference, coverage)
            VALUES (:id, :name, :resolution, :file_ref, ST_Multi(ST_GeomFromText(:wkt, 4326)))
            ON CONFLICT (id) DO NOTHING
            """
        )
        session.execute(
            insert_stmt,
            {
                "id": dataset_id,
                "name": "Copernicus DEM GLO-30",
                "resolution": res_str,
                "file_ref": str(vrt_path),
                "wkt": coverage_wkt,
            },
        )
        session.commit()
        logger.info("Registered Copernicus DEM GLO-30 in terrain_datasets (ID: %s)", dataset_id)
        return dataset_id


def extract_zonal_terrain(
    geom: BaseGeometry,
    vrt_src: rasterio.DatasetReader,
) -> dict[str, Any]:
    """
    Extract elevation and slope statistics for a single shapely polygon from VRT.

    Uses a 2-pixel buffer around polygon bounds to ensure the 3x3 Horn slope
    filter has valid boundary pixels for calculating slope within the polygon.
    """
    minx, miny, maxx, maxy = geom.bounds
    res_x = vrt_src.res[0]
    res_y = vrt_src.res[1]

    # Buffer by 2 pixels
    buf_minx = max(vrt_src.bounds.left, minx - 2 * res_x)
    buf_maxx = min(vrt_src.bounds.right, maxx + 2 * res_x)
    buf_miny = max(vrt_src.bounds.bottom, miny - 2 * res_y)
    buf_maxy = min(vrt_src.bounds.top, maxy + 2 * res_y)

    window = rasterio.windows.from_bounds(buf_minx, buf_miny, buf_maxx, buf_maxy, transform=vrt_src.transform)
    window = window.round_offsets().round_lengths()

    dem_window = vrt_src.read(1, window=window)
    if dem_window.size == 0:
        raise ValueError(f"Empty raster window for geometry bounds: {geom.bounds}")

    top_lat = vrt_src.transform.f - window.row_off * res_y
    slope_window = compute_horn_slope(
        dem_window,
        res_x_deg=res_x,
        res_y_deg=res_y,
        top_lat_deg=top_lat,
    )

    window_transform = rasterio.windows.transform(window, vrt_src.transform)
    mask = geometry_mask([geom], out_shape=dem_window.shape, transform=window_transform, invert=True)

    dem_pixels = dem_window[mask]
    slope_pixels = slope_window[mask]

    elev_stats = calculate_elevation_statistics(dem_pixels, nodata_val=vrt_src.nodata)
    slope_stats = calculate_slope_statistics(slope_pixels)

    return {**elev_stats, **slope_stats}


def process_district_terrain_statistics(
    vrt_path: Path,
    dataset_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Compute and persist zonal terrain statistics for all 31 districts."""
    engine = _get_engine()
    results: list[dict[str, Any]] = []

    with engine.connect() as conn:
        districts = conn.execute(
            text("SELECT id, name, code, ST_AsBinary(geometry) FROM districts ORDER BY name")
        ).fetchall()

    logger.info("Starting zonal terrain processing for %d districts", len(districts))

    with rasterio.open(vrt_path) as vrt_src:
        session_factory = _get_session_factory()
        with session_factory() as session:
            for dist_id, name, code, wkb_bytes in districts:
                if not wkb_bytes:
                    logger.warning("District %s has no geometry, skipping", name)
                    continue

                geom = shapely.wkb.loads(bytes(wkb_bytes))
                stats = extract_zonal_terrain(geom, vrt_src)

                record = {
                    "id": uuid.uuid4(),
                    "terrain_dataset_id": dataset_id,
                    "target_type": "DISTRICT",
                    "district_id": dist_id,
                    "sub_basin_id": None,
                    "elevation_mean": stats["elevation_mean"],
                    "elevation_median": stats["elevation_median"],
                    "elevation_min": stats["elevation_min"],
                    "elevation_max": stats["elevation_max"],
                    "elevation_std": stats["elevation_std"],
                    "slope_mean": stats["slope_mean"],
                    "slope_median": stats["slope_median"],
                    "slope_min": stats["slope_min"],
                    "slope_max": stats["slope_max"],
                    "valid_pixel_count": stats["valid_pixel_count"],
                    "nodata_pixel_count": stats["nodata_pixel_count"],
                    "coverage_percentage": stats["coverage_percentage"],
                    "dem_version": DEM_VERSION,
                    "processing_version": PROCESSING_VERSION,
                    "geometry_version": GEOMETRY_VERSION,
                    "processing_method": PROCESSING_METHOD,
                    "processing_crs": PROCESSING_CRS,
                }

                # Upsert into terrain_statistics
                stmt = insert(TerrainStatistic).values(**record)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_terrain_stats_district",
                    set_={
                        "elevation_mean": record["elevation_mean"],
                        "elevation_median": record["elevation_median"],
                        "elevation_min": record["elevation_min"],
                        "elevation_max": record["elevation_max"],
                        "elevation_std": record["elevation_std"],
                        "slope_mean": record["slope_mean"],
                        "slope_median": record["slope_median"],
                        "slope_min": record["slope_min"],
                        "slope_max": record["slope_max"],
                        "valid_pixel_count": record["valid_pixel_count"],
                        "nodata_pixel_count": record["nodata_pixel_count"],
                        "coverage_percentage": record["coverage_percentage"],
                        "calculated_at": datetime.now(timezone.utc),
                    },
                )
                session.execute(stmt)
                results.append({"name": name, "code": code, **stats})
                logger.info(
                    "District %-20s: Elev [%.1f - %.1f m, mean: %.1f m], Slope [mean: %.2f°, max: %.2f°]",
                    name, stats["elevation_min"], stats["elevation_max"], stats["elevation_mean"],
                    stats["slope_mean"], stats["slope_max"]
                )

            session.commit()

    logger.info("Successfully persisted terrain statistics for %d districts", len(results))
    return results


def process_sub_basin_terrain_statistics(
    vrt_path: Path,
    dataset_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Compute and persist zonal terrain statistics for all 116 sub-basins."""
    engine = _get_engine()
    results: list[dict[str, Any]] = []

    with engine.connect() as conn:
        sub_basins = conn.execute(
            text("SELECT id, hybas_id, name, ST_AsBinary(geometry) FROM sub_basins ORDER BY hybas_id")
        ).fetchall()

    logger.info("Starting zonal terrain processing for %d sub-basins", len(sub_basins))

    with rasterio.open(vrt_path) as vrt_src:
        session_factory = _get_session_factory()
        with session_factory() as session:
            for sb_id, hybas_id, name, wkb_bytes in sub_basins:
                if not wkb_bytes:
                    logger.warning("SubBasin %s has no geometry, skipping", hybas_id)
                    continue

                geom = shapely.wkb.loads(bytes(wkb_bytes))
                stats = extract_zonal_terrain(geom, vrt_src)

                record = {
                    "id": uuid.uuid4(),
                    "terrain_dataset_id": dataset_id,
                    "target_type": "SUB_BASIN",
                    "district_id": None,
                    "sub_basin_id": sb_id,
                    "elevation_mean": stats["elevation_mean"],
                    "elevation_median": stats["elevation_median"],
                    "elevation_min": stats["elevation_min"],
                    "elevation_max": stats["elevation_max"],
                    "elevation_std": stats["elevation_std"],
                    "slope_mean": stats["slope_mean"],
                    "slope_median": stats["slope_median"],
                    "slope_min": stats["slope_min"],
                    "slope_max": stats["slope_max"],
                    "valid_pixel_count": stats["valid_pixel_count"],
                    "nodata_pixel_count": stats["nodata_pixel_count"],
                    "coverage_percentage": stats["coverage_percentage"],
                    "dem_version": DEM_VERSION,
                    "processing_version": PROCESSING_VERSION,
                    "geometry_version": GEOMETRY_VERSION,
                    "processing_method": PROCESSING_METHOD,
                    "processing_crs": PROCESSING_CRS,
                }

                stmt = insert(TerrainStatistic).values(**record)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_terrain_stats_sub_basin",
                    set_={
                        "elevation_mean": record["elevation_mean"],
                        "elevation_median": record["elevation_median"],
                        "elevation_min": record["elevation_min"],
                        "elevation_max": record["elevation_max"],
                        "elevation_std": record["elevation_std"],
                        "slope_mean": record["slope_mean"],
                        "slope_median": record["slope_median"],
                        "slope_min": record["slope_min"],
                        "slope_max": record["slope_max"],
                        "valid_pixel_count": record["valid_pixel_count"],
                        "nodata_pixel_count": record["nodata_pixel_count"],
                        "coverage_percentage": record["coverage_percentage"],
                        "calculated_at": datetime.now(timezone.utc),
                    },
                )
                session.execute(stmt)
                results.append({"hybas_id": hybas_id, "name": name, **stats})

            session.commit()

    logger.info("Successfully persisted terrain statistics for %d sub-basins", len(results))
    return results
