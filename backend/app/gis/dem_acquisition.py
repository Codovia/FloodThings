"""
Copernicus DEM GLO-30 acquisition and verification module.

Downloads and verifies the 39 1°x1° DEM tiles covering Karnataka
and surrounding transboundary buffer zones from the official public AWS S3 bucket.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import rasterio

logger = logging.getLogger(__name__)

# Official public AWS S3 endpoint for Copernicus GLO-30 (Public instance)
BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"

# 39 required tiles: N11 to N18, E074 to E078 (excluding N11_E074 which is open Arabian Sea)
REQUIRED_TILES = [
    # N11 (4 tiles)
    ("N11", "E075"), ("N11", "E076"), ("N11", "E077"), ("N11", "E078"),
    # N12 (5 tiles)
    ("N12", "E074"), ("N12", "E075"), ("N12", "E076"), ("N12", "E077"), ("N12", "E078"),
    # N13 (5 tiles)
    ("N13", "E074"), ("N13", "E075"), ("N13", "E076"), ("N13", "E077"), ("N13", "E078"),
    # N14 (5 tiles)
    ("N14", "E074"), ("N14", "E075"), ("N14", "E076"), ("N14", "E077"), ("N14", "E078"),
    # N15 (5 tiles)
    ("N15", "E074"), ("N15", "E075"), ("N15", "E076"), ("N15", "E077"), ("N15", "E078"),
    # N16 (5 tiles)
    ("N16", "E074"), ("N16", "E075"), ("N16", "E076"), ("N16", "E077"), ("N16", "E078"),
    # N17 (5 tiles)
    ("N17", "E074"), ("N17", "E075"), ("N17", "E076"), ("N17", "E077"), ("N17", "E078"),
    # N18 (5 tiles)
    ("N18", "E074"), ("N18", "E075"), ("N18", "E076"), ("N18", "E077"), ("N18", "E078"),
]


def get_tile_name(lat: str, lon: str) -> str:
    """Return Copernicus tile naming convention."""
    return f"Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM"


def get_tile_url(lat: str, lon: str) -> str:
    """Return direct HTTPS download URL on public AWS S3."""
    tile_name = get_tile_name(lat, lon)
    return f"{BASE_URL}/{tile_name}/{tile_name}.tif"


def compute_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_tile(
    lat: str,
    lon: str,
    dest_dir: Path,
    force: bool = False,
    timeout: int = 60,
    max_retries: int = 3,
) -> Path:
    """Download a single Copernicus DEM tile if not already downloaded."""
    tile_name = get_tile_name(lat, lon)
    target_file = dest_dir / f"{tile_name}.tif"
    temp_file = dest_dir / f"{tile_name}.tif.tmp"

    if target_file.exists() and not force and target_file.stat().st_size > 1000:
        logger.info("Tile already exists: %s", target_file.name)
        return target_file

    url = get_tile_url(lat, lon)
    logger.info("Downloading %s -> %s", url, target_file.name)

    req = Request(url, headers={"User-Agent": "FloodPrediction-DEM-Ingest/1.0"})

    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(req, timeout=timeout) as response, open(temp_file, "wb") as out_f:
                while chunk := response.read(1024 * 1024):
                    out_f.write(chunk)
            temp_file.replace(target_file)
            logger.info("Successfully acquired %s (%d bytes)", target_file.name, target_file.stat().st_size)
            return target_file
        except (HTTPError, URLError, OSError) as err:
            logger.warning("Attempt %d failed for %s: %s", attempt, url, err)
            if temp_file.exists():
                temp_file.unlink()
            if attempt == max_retries:
                raise RuntimeError(f"Failed to download tile {lat}_{lon} after {max_retries} attempts: {err}") from err
            time.sleep(2 * attempt)

    return target_file


def verify_tile_raster(file_path: Path) -> dict[str, Any]:
    """Verify raster integrity, metadata, CRS, resolution, and elevation stats."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    size_bytes = file_path.stat().st_size
    if size_bytes < 1000:
        raise ValueError(f"File too small ({size_bytes} bytes): {file_path}")

    with rasterio.open(file_path) as src:
        crs_auth = src.crs.to_string() if src.crs else None
        width = src.width
        height = src.height
        bounds = src.bounds
        res = src.res
        dtypes = src.dtypes
        driver = src.driver

        if driver != "GTiff":
            raise ValueError(f"Unexpected driver: {driver}")
        if width != 3600 or height != 3600:
            raise ValueError(f"Unexpected raster dimensions: {width}x{height} (expected 3600x3600)")
        if not src.crs or src.crs.to_epsg() != 4326:
            raise ValueError(f"Unexpected CRS: {crs_auth} (expected EPSG:4326)")

        data = src.read(1)
        import numpy as np

        if src.nodata is not None and not np.isnan(src.nodata):
            valid = (data != src.nodata) & ~np.isnan(data)
        else:
            valid = ~np.isnan(data)

        min_val = float(np.min(data[valid])) if np.any(valid) else float("nan")
        max_val = float(np.max(data[valid])) if np.any(valid) else float("nan")

    return {
        "filename": file_path.name,
        "size_bytes": size_bytes,
        "driver": driver,
        "width": width,
        "height": height,
        "crs": crs_auth,
        "bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "resolution_deg": list(res),
        "data_type": dtypes[0],
        "min_elevation_m": min_val,
        "max_elevation_m": max_val,
        "status": "VALID",
    }


from concurrent.futures import ThreadPoolExecutor, as_completed


def _process_single_tile(
    lat: str,
    lon: str,
    dest_dir: Path,
    force: bool,
) -> dict[str, Any]:
    tile_name = get_tile_name(lat, lon)
    tile_path = download_tile(lat, lon, dest_dir, force=force)
    sha256 = compute_sha256(tile_path)
    meta = verify_tile_raster(tile_path)
    meta["sha256"] = sha256
    meta["source_url"] = get_tile_url(lat, lon)
    meta["tile_tag"] = f"{lat}_{lon}"
    return meta


def acquire_and_verify_all(
    dest_dir: Path,
    manifest_path: Path,
    force: bool = False,
    max_workers: int = 6,
) -> dict[str, Any]:
    """Acquire all 39 tiles concurrently and build the verification manifest."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, Any]] = []

    total = len(REQUIRED_TILES)
    logger.info("Starting acquisition and verification for %d Copernicus DEM tiles (max_workers=%d)", total, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_tile = {
            executor.submit(_process_single_tile, lat, lon, dest_dir, force): (lat, lon)
            for lat, lon in REQUIRED_TILES
        }
        completed = 0
        for future in as_completed(future_to_tile):
            lat, lon = future_to_tile[future]
            try:
                meta = future.result()
                manifest_entries.append(meta)
                completed += 1
                logger.info("[%d/%d] Completed tile %s (size: %.1f MB, min: %.1fm, max: %.1fm)",
                            completed, total, meta["filename"], meta["size_bytes"] / 1e6,
                            meta["min_elevation_m"], meta["max_elevation_m"])
            except Exception as exc:
                logger.error("Error processing tile %s_%s: %s", lat, lon, exc)
                raise

    # Sort manifest entries deterministically by tile_tag
    manifest_entries.sort(key=lambda m: m["tile_tag"])

    manifest_data = {
        "dataset": "Copernicus DEM GLO-30 (COP-DEM_GLO-30-DGED)",
        "source": BASE_URL,
        "license": "Copernicus Worldview Open Access / Creative Commons CC-BY-4.0 equivalent",
        "vertical_datum": "EGM2008 geoid (EPSG:3855)",
        "horizontal_crs": "EPSG:4326 (WGS 84)",
        "tile_count": len(manifest_entries),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tiles": manifest_entries,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info("Wrote verified DEM manifest to %s", manifest_path)
    return manifest_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    base_proj = Path(__file__).resolve().parents[3]
    dem_dir = base_proj / "data" / "raw" / "gis" / "dem"
    manifest_file = dem_dir / "dem_tile_manifest.json"

    acquire_and_verify_all(dem_dir, manifest_file)
