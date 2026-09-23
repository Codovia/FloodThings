"""
Terrain analysis engine for Copernicus DEM.

Computes elevation statistics and metric slope using Horn's algorithm
with latitude-scaled geodesic longitudinal distances, preventing degree-as-metre errors.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# WGS 84 ellipsoid approximation: meters per degree of latitude
METERS_PER_DEG_LAT = 111319.5


def calculate_elevation_statistics(
    dem_array: np.ndarray,
    nodata_val: float | None = None,
) -> dict[str, Any]:
    """
    Calculate summary elevation statistics from a 2D DEM array.

    Missing or invalid values (NaN or nodata) are explicitly masked and counted.
    """
    if nodata_val is not None and not np.isnan(nodata_val):
        valid_mask = (dem_array != nodata_val) & ~np.isnan(dem_array)
    else:
        valid_mask = ~np.isnan(dem_array)

    total_pixels = dem_array.size
    valid_count = int(np.count_nonzero(valid_mask))
    nodata_count = int(total_pixels - valid_count)
    coverage_pct = float((valid_count / total_pixels) * 100.0) if total_pixels > 0 else 0.0

    if valid_count == 0:
        return {
            "elevation_mean": None,
            "elevation_median": None,
            "elevation_min": None,
            "elevation_max": None,
            "elevation_std": None,
            "valid_pixel_count": 0,
            "nodata_pixel_count": nodata_count,
            "coverage_percentage": 0.0,
        }

    valid_data = dem_array[valid_mask]
    return {
        "elevation_mean": float(np.mean(valid_data)),
        "elevation_median": float(np.median(valid_data)),
        "elevation_min": float(np.min(valid_data)),
        "elevation_max": float(np.max(valid_data)),
        "elevation_std": float(np.std(valid_data)),
        "valid_pixel_count": valid_count,
        "nodata_pixel_count": nodata_count,
        "coverage_percentage": coverage_pct,
    }


def compute_horn_slope(
    dem_array: np.ndarray,
    res_x_deg: float,
    res_y_deg: float,
    top_lat_deg: float,
) -> np.ndarray:
    """
    Compute slope in degrees using Horn's 8-neighbor algorithm.

    Explicitly scales dx by cos(latitude) in meters to ensure
    horizontal and vertical distances are in the exact same unit (meters),
    completely avoiding degree-as-metre distortion.

    Parameters
    ----------
    dem_array : np.ndarray
        2D float array of elevations in meters (EPSG:4326).
    res_x_deg : float
        Pixel width in decimal degrees (e.g. 1/3600).
    res_y_deg : float
        Pixel height in decimal degrees (positive, e.g. 1/3600).
    top_lat_deg : float
        Latitude of the top edge of dem_array in decimal degrees.

    Returns
    -------
    np.ndarray
        2D float array of slope values in degrees (0 to 90).
        Dimensions are identical to dem_array; boundary pixels are NaN.
    """
    height, width = dem_array.shape
    slope = np.full((height, width), np.nan, dtype=np.float32)

    if height < 3 or width < 3:
        return slope

    # Row latitudes (centers of rows 1 to height-2)
    row_indices = np.arange(1, height - 1)
    row_lats = top_lat_deg - (row_indices + 0.5) * res_y_deg
    row_lats_rad = np.radians(row_lats)[:, np.newaxis]

    dy = res_y_deg * METERS_PER_DEG_LAT
    dx = res_x_deg * METERS_PER_DEG_LAT * np.cos(row_lats_rad)

    # 3x3 Horn convolution (vectorized over interior [1:-1, 1:-1])
    # Neighbor naming:
    #   tl  t  tr
    #   l   c  r
    #   bl  b  br
    tl = dem_array[:-2, :-2]
    t  = dem_array[:-2, 1:-1]
    tr = dem_array[:-2, 2:]

    l  = dem_array[1:-1, :-2]
    r  = dem_array[1:-1, 2:]

    bl = dem_array[2:, :-2]
    b  = dem_array[2:, 1:-1]
    br = dem_array[2:, 2:]

    # Finite difference gradients in meters/meter
    dz_dx = ((tr + 2.0 * r + br) - (tl + 2.0 * l + bl)) / (8.0 * dx)
    dz_dy = ((bl + 2.0 * b + br) - (tl + 2.0 * t + tr)) / (8.0 * dy)

    rise_run = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_interior = np.degrees(np.arctan(rise_run))

    slope[1:-1, 1:-1] = slope_interior.astype(np.float32)
    return slope


def calculate_slope_statistics(
    slope_array: np.ndarray,
) -> dict[str, Any]:
    """Calculate summary statistics from a slope array in degrees."""
    valid_mask = ~np.isnan(slope_array)
    valid_count = int(np.count_nonzero(valid_mask))

    if valid_count == 0:
        return {
            "slope_mean": None,
            "slope_median": None,
            "slope_min": None,
            "slope_max": None,
        }

    valid_data = slope_array[valid_mask]
    return {
        "slope_mean": float(np.mean(valid_data)),
        "slope_median": float(np.median(valid_data)),
        "slope_min": float(np.min(valid_data)),
        "slope_max": float(np.max(valid_data)),
    }
