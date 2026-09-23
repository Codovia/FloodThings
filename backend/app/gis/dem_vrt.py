"""
GDAL Virtual Raster (VRT) mosaic builder for Karnataka Copernicus DEM.

Constructs a seamless karnataka_dem.vrt referencing all 39 COG tiles
without duplicating raster data on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import rasterio

logger = logging.getLogger(__name__)

# Bounding grid specifications
MIN_LON = 74
MAX_LON = 79  # 5 columns (E074, E075, E076, E077, E078)
MIN_LAT = 11
MAX_LAT = 19  # 8 rows (N11, N12, N13, N14, N15, N16, N17, N18)

TILE_PIXELS = 3600
RES = 1.0 / TILE_PIXELS  # 0.0002777777777777778 degrees
HALF_RES = RES / 2.0


def build_karnataka_dem_vrt(
    dem_dir: Path,
    vrt_path: Path,
    manifest: dict[str, Any] | None = None,
) -> Path:
    """Construct a GDAL VRT XML mosaic from available 1°x1° tiles."""
    total_cols = MAX_LON - MIN_LON  # 5
    total_rows = MAX_LAT - MIN_LAT  # 8

    raster_x_size = total_cols * TILE_PIXELS  # 18,000
    raster_y_size = total_rows * TILE_PIXELS  # 28,800

    origin_x = MIN_LON - HALF_RES  # 73.99986111111112
    origin_y = MAX_LAT + HALF_RES  # 19.00013888888889

    # Root VRT dataset element
    vrt = ET.Element(
        "VRTDataset",
        rasterXSize=str(raster_x_size),
        rasterYSize=str(raster_y_size),
    )

    srs = ET.SubElement(vrt, "SRS", dataAxisToSRSAxisMapping="2,1")
    srs.text = "EPSG:4326"

    geo_transform = ET.SubElement(vrt, "GeoTransform")
    geo_transform.text = f"{origin_x:.14f}, {RES:.16f}, 0.0, {origin_y:.14f}, 0.0, {-RES:.16f}"

    raster_band = ET.SubElement(
        vrt,
        "VRTRasterBand",
        dataType="Float32",
        band="1",
    )
    no_data = ET.SubElement(raster_band, "NoDataValue")
    no_data.text = "nan"

    # Find tiles
    tile_files = list(dem_dir.glob("Copernicus_DSM_COG_10_*_DEM.tif"))
    if not tile_files:
        raise FileNotFoundError(f"No DEM GeoTIFF files found in {dem_dir}")

    tiles_added = 0
    for tile_path in sorted(tile_files):
        # Extract lat/lon from filename: Copernicus_DSM_COG_10_N12_00_E076_00_DEM.tif
        parts = tile_path.stem.split("_")
        # parts: ['Copernicus', 'DSM', 'COG', '10', 'N12', '00', 'E076', '00', 'DEM']
        if len(parts) < 8:
            continue
        lat_str = parts[4]  # e.g. N12
        lon_str = parts[6]  # e.g. E076

        lat_val = int(lat_str[1:])
        lon_val = int(lon_str[1:])

        if not (MIN_LAT <= lat_val < MAX_LAT and MIN_LON <= lon_val < MAX_LON):
            logger.warning("Tile %s is outside expected bounding grid, skipping", tile_path.name)
            continue

        col_idx = lon_val - MIN_LON
        row_idx = (MAX_LAT - 1) - lat_val

        dst_x = col_idx * TILE_PIXELS
        dst_y = row_idx * TILE_PIXELS

        source = ET.SubElement(raster_band, "SimpleSource")
        source_filename = ET.SubElement(source, "SourceFilename", relativeToVRT="1")
        source_filename.text = tile_path.name

        source_band = ET.SubElement(source, "SourceBand")
        source_band.text = "1"

        ET.SubElement(
            source,
            "SourceProperties",
            RasterXSize=str(TILE_PIXELS),
            RasterYSize=str(TILE_PIXELS),
            DataType="Float32",
            BlockXSize="1024",
            BlockYSize="1024",
        )
        ET.SubElement(
            source,
            "SrcRect",
            xOff="0",
            yOff="0",
            xSize=str(TILE_PIXELS),
            ySize=str(TILE_PIXELS),
        )
        ET.SubElement(
            source,
            "DstRect",
            xOff=str(dst_x),
            yOff=str(dst_y),
            xSize=str(TILE_PIXELS),
            ySize=str(TILE_PIXELS),
        )
        source_nodata = ET.SubElement(source, "NODATA")
        source_nodata.text = "nan"

        tiles_added += 1

    tree = ET.ElementTree(vrt)
    ET.indent(tree, space="  ", level=0)
    with open(vrt_path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)

    logger.info("Successfully wrote VRT mosaic %s with %d tiles", vrt_path.name, tiles_added)
    return vrt_path


def verify_vrt(vrt_path: Path) -> dict[str, Any]:
    """Verify that VRT can be opened by rasterio and reports correct geometry."""
    if not vrt_path.exists():
        raise FileNotFoundError(f"VRT not found: {vrt_path}")

    with rasterio.open(vrt_path) as src:
        driver = src.driver
        width = src.width
        height = src.height
        bounds = src.bounds
        crs = src.crs.to_string() if src.crs else None
        res = src.res

        if driver != "VRT":
            raise ValueError(f"Expected driver VRT, got {driver}")
        if not src.crs or src.crs.to_epsg() != 4326:
            raise ValueError(f"Expected CRS EPSG:4326, got {crs}")
        if width != 18000 or height != 28800:
            raise ValueError(f"Expected 18000x28800, got {width}x{height}")

        # Test windowed read of sample region (Mysuru / Cauvery valley)
        # N12 E076 is at col 2 (76-74), row 6 (18-12) -> xOff: 7200, yOff: 21600
        window = rasterio.windows.Window(7200, 21600, 100, 100)
        sample_data = src.read(1, window=window)
        min_elev = float(sample_data.min())
        max_elev = float(sample_data.max())

    return {
        "vrt_filename": vrt_path.name,
        "driver": driver,
        "width": width,
        "height": height,
        "crs": crs,
        "bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "resolution_deg": list(res),
        "sample_min_elev": min_elev,
        "sample_max_elev": max_elev,
        "status": "VALID",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    base_proj = Path(__file__).resolve().parents[3]
    dem_dir = base_proj / "data" / "raw" / "gis" / "dem"
    vrt_file = dem_dir / "karnataka_dem.vrt"

    build_karnataka_dem_vrt(dem_dir, vrt_file)
    res = verify_vrt(vrt_file)
    print("VRT verification:", res)
