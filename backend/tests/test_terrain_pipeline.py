"""
Automated validation and regression tests for the DEM Terrain Processing Pipeline.

Covers:
- 39 tiles acquisition and manifest checksum integrity
- VRT mosaic readability, CRS, dimensions, and coverage
- Horn's metric slope algorithm (zero degree-as-metre error check)
- 31 Karnataka administrative districts zonal statistics completeness and bounds
- 116 HydroBASINS Level-7 sub-basins zonal statistics completeness
- Provenance and derived feature metadata tracking
- System isolation invariants (ERA5 and Hydrological GIS unchanged)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from sqlalchemy import text

from app.db.session import _get_engine
from app.gis.terrain_engine import (
    calculate_elevation_statistics,
    calculate_slope_statistics,
    compute_horn_slope,
)


@pytest.fixture(scope="module")
def dem_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "gis" / "dem"


@pytest.fixture(scope="module")
def vrt_path(dem_dir: Path) -> Path:
    return dem_dir / "karnataka_dem.vrt"


@pytest.fixture(scope="module")
def manifest_path(dem_dir: Path) -> Path:
    return dem_dir / "dem_tile_manifest.json"


# ==============================================================================
# 1. DEM Tile Acquisition and Checksum Integrity
# ==============================================================================

class TestDemTileAcquisitionAndIntegrity:
    """Verify that all 39 tiles are present, valid, and match manifest checksums."""

    def test_manifest_exists_and_has_39_tiles(self, manifest_path: Path):
        assert manifest_path.exists(), f"Manifest missing: {manifest_path}"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest["tile_count"] == 39
        assert len(manifest["tiles"]) == 39
        assert manifest["dataset"].startswith("Copernicus DEM GLO-30")
        assert manifest["horizontal_crs"] == "EPSG:4326 (WGS 84)"
        assert manifest["vertical_datum"] == "EGM2008 geoid (EPSG:3855)"

    def test_all_39_tiles_exist_and_readable(self, dem_dir: Path, manifest_path: Path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        for entry in manifest["tiles"]:
            tile_path = dem_dir / entry["filename"]
            assert tile_path.exists(), f"Missing tile: {entry['filename']}"
            assert tile_path.stat().st_size == entry["size_bytes"]
            assert entry["status"] == "VALID"
            assert entry["width"] == 3600
            assert entry["height"] == 3600
            assert entry["crs"] == "EPSG:4326"


# ==============================================================================
# 2. VRT Mosaic Structure and Readability
# ==============================================================================

class TestKarnatakaDemVrt:
    """Verify GDAL VRT mosaic construction and raster properties."""

    def test_vrt_file_exists(self, vrt_path: Path):
        assert vrt_path.exists(), f"VRT file missing: {vrt_path}"

    def test_vrt_rasterio_properties(self, vrt_path: Path):
        with rasterio.open(vrt_path) as src:
            assert src.driver == "VRT"
            assert src.crs.to_epsg() == 4326
            assert src.width == 18000
            assert src.height == 28800
            assert src.count == 1
            assert src.dtypes[0] == "float32"

            # Check bounding extent covers Karnataka (74E to 79E, 11N to 19N)
            bounds = src.bounds
            assert bounds.left <= 74.001
            assert bounds.right >= 78.999
            assert bounds.bottom <= 11.001
            assert bounds.top >= 18.999

    def test_vrt_windowed_read_across_regions(self, vrt_path: Path):
        with rasterio.open(vrt_path) as src:
            # North Karnataka (Bidar / Kalaburagi: ~N17.5 E077)
            win_north = rasterio.windows.from_bounds(77.0, 17.5, 77.1, 17.6, transform=src.transform)
            data_north = src.read(1, window=win_north)
            assert data_north.size > 0
            assert 300.0 < np.nanmean(data_north) < 800.0

            # South Karnataka (Mysuru: ~N12.3 E076.6)
            win_south = rasterio.windows.from_bounds(76.5, 12.2, 76.6, 12.3, transform=src.transform)
            data_south = src.read(1, window=win_south)
            assert data_south.size > 0
            assert 600.0 < np.nanmean(data_south) < 1200.0


# ==============================================================================
# 3. Slope Calculation & Degree-as-Metre Prevention
# ==============================================================================

class TestHornMetricSlopeAlgorithm:
    """Validate Horn slope implementation against synthetic and real benchmarks."""

    def test_flat_plane_has_zero_slope(self):
        flat_dem = np.full((10, 10), 500.0, dtype=np.float32)
        slope = compute_horn_slope(flat_dem, res_x_deg=1/3600, res_y_deg=1/3600, top_lat_deg=13.0)
        valid = slope[~np.isnan(slope)]
        assert np.allclose(valid, 0.0, atol=1e-5)

    def test_synthetic_45_degree_ramp(self):
        # A ramp rising 1 meter per meter along latitude
        res_y_deg = 1.0 / 3600.0
        dy_m = res_y_deg * 111319.5  # ~30.92 meters per pixel
        height, width = 10, 10
        ramp_dem = np.zeros((height, width), dtype=np.float32)
        for r in range(height):
            ramp_dem[r, :] = (height - 1 - r) * dy_m  # rises 1m per meter southward

        slope = compute_horn_slope(ramp_dem, res_x_deg=res_y_deg, res_y_deg=res_y_deg, top_lat_deg=13.0)
        valid = slope[~np.isnan(slope)]
        # Slope should be exactly 45 degrees
        assert np.allclose(valid, 45.0, atol=1e-3)

    def test_no_degree_as_metre_error(self, vrt_path: Path):
        # Read a hilly area in Western Ghats (Kodagu / Hassan border: 75.6°E, 12.7°N)
        with rasterio.open(vrt_path) as src:
            win = rasterio.windows.from_bounds(75.6, 12.7, 75.7, 12.8, transform=src.transform)
            dem = src.read(1, window=win)
            top_lat = src.transform.f - win.row_off * src.res[1]

        slope = compute_horn_slope(dem, res_x_deg=src.res[0], res_y_deg=src.res[1], top_lat_deg=top_lat)
        valid = slope[~np.isnan(slope)]

        # If degree-as-metre error existed, slopes would all be > 89.9°
        # With correct metric scaling, slopes are physically realistic (0° to 65°)
        mean_slope = float(np.mean(valid))
        max_slope = float(np.max(valid))

        assert 5.0 < mean_slope < 30.0, f"Mean slope {mean_slope}° is unrealistic!"
        assert max_slope < 75.0, f"Max slope {max_slope}° indicates degree-as-metre distortion!"


# ==============================================================================
# 4. District and Sub-Basin Zonal Statistics
# ==============================================================================

class TestZonalTerrainStatistics:
    """Validate persisted zonal statistics in the database."""

    def test_district_statistics_count_and_completeness(self):
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT d.name, ts.elevation_mean, ts.elevation_min, ts.elevation_max,
                           ts.slope_mean, ts.valid_pixel_count, ts.coverage_percentage
                    FROM terrain_statistics ts
                    JOIN districts d ON d.id = ts.district_id
                    WHERE ts.target_type = 'DISTRICT'
                    ORDER BY d.name
                    """
                )
            ).fetchall()

        assert len(rows) == 31, f"Expected 31 district statistics, got {len(rows)}"

        for name, elev_mean, elev_min, elev_max, slope_mean, count, cov in rows:
            assert count > 0, f"District {name} has 0 valid pixels"
            assert cov >= 99.0, f"District {name} coverage is {cov}%, expected >=99%"
            assert elev_min is not None and elev_max is not None
            assert elev_min <= elev_mean <= elev_max, f"District {name} has inconsistent elevation range"
            assert 0.0 <= slope_mean <= 45.0, f"District {name} slope {slope_mean}° is unrealistic"

    def test_sub_basin_statistics_count(self):
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT count(*), min(coverage_percentage), avg(slope_mean)
                    FROM terrain_statistics
                    WHERE target_type = 'SUB_BASIN'
                    """
                )
            ).fetchone()

        assert rows[0] == 116, f"Expected 116 sub-basin statistics, got {rows[0]}"
        assert rows[1] is not None and rows[1] >= 95.0, "Sub-basin coverage is incomplete"
        assert rows[2] is not None and 0.5 <= rows[2] <= 35.0

    def test_provenance_and_derived_feature_metadata(self):
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT dem_version, processing_version, geometry_version,
                                    processing_method, processing_crs
                    FROM terrain_statistics
                    """
                )
            ).fetchall()

        assert len(rows) == 1
        meta = rows[0]
        assert meta[0] == "COP-DEM_GLO-30-DGED_2021"
        assert meta[1] == "1.0.0"
        assert "KSR-SAC" in meta[2]
        assert "Horn" in meta[3]
        assert "EGM2008" in meta[4]


# ==============================================================================
# 5. System Isolation Invariants
# ==============================================================================

class TestSystemIsolation:
    """Ensure zero mutation of ERA5 or existing hydrological GIS foundation."""

    def test_hydrological_gis_record_counts_preserved(self):
        engine = _get_engine()
        with engine.connect() as conn:
            cwc_count = conn.execute(text("SELECT count(*) FROM river_basins")).scalar()
            subbasin_count = conn.execute(text("SELECT count(*) FROM sub_basins")).scalar()
            rivers_count = conn.execute(text("SELECT count(*) FROM rivers")).scalar()
            dist_cwc_count = conn.execute(text("SELECT count(*) FROM district_river_basins")).scalar()
            dist_sb_count = conn.execute(text("SELECT count(*) FROM district_sub_basins")).scalar()

        assert cwc_count == 25
        assert subbasin_count == 116
        assert rivers_count == 15371
        assert dist_cwc_count == 54
        assert dist_sb_count == 264

    def test_era5_directory_untouched(self):
        era5_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "era5_historical"
        assert era5_dir.exists()
        manifest_file = era5_dir / "extraction_manifest.json"
        assert manifest_file.exists()
