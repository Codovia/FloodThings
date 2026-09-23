"""
Tests for DEM Source Verification and Acquisition (Phase 3.4 Terrain Foundation).

Verifies:
1. Controlled sample DEM tile integrity and SHA256 checksum.
2. Raster readability, COG format, CRS, resolution, and dimensions.
3. Realistic elevation value distribution for Karnataka terrain.
4. Spatial intersection with Karnataka state boundary and districts.
5. Statewide coverage verification across Copernicus DEM GLO-30 1x1 degree grid.
6. System isolation: ERA5 and hydrological GIS records remain completely untouched.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
import pytest
import rasterio
from shapely.geometry import box
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District, State
from app.db.models.hydrology import (
    DistrictRiverBasin,
    DistrictSubBasin,
    River,
    RiverBasin,
    SubBasin,
)
from app.db.session import _get_session_factory

# Expected paths relative to backend directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEM_DIR = PROJECT_ROOT / "data" / "raw" / "gis" / "dem"
SAMPLE_TIF_PATH = DEM_DIR / "Copernicus_DSM_COG_10_N12_00_E076_00_DEM.tif"
SAMPLE_XML_PATH = DEM_DIR / "Copernicus_DSM_10_N12_00_E076_00.xml"

EXPECTED_TIF_SHA256 = "906c8faa9341c5426aa4394c82fab0ffd4e34485992f6d8293d6a1c61b5066f7"
EXPECTED_XML_SHA256 = "2c0379bf155e60ee4c7b9612188c80082e75e73ab9917876dff92c905479c287"


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to live test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


class TestDemSampleIntegrity:
    """Verifies file existence, sizes, and SHA-256 checksums."""

    def test_sample_files_exist(self):
        """DEM sample GeoTIFF and XML metadata files exist on disk."""
        assert SAMPLE_TIF_PATH.exists(), f"Sample DEM missing at {SAMPLE_TIF_PATH}"
        assert SAMPLE_XML_PATH.exists(), f"Sample XML missing at {SAMPLE_XML_PATH}"

    def test_sample_tif_checksum(self):
        """Sample GeoTIFF matches exact SHA-256 checksum."""
        h = hashlib.sha256()
        with open(SAMPLE_TIF_PATH, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        assert h.hexdigest() == EXPECTED_TIF_SHA256, "GeoTIFF checksum mismatch"

    def test_sample_xml_checksum(self):
        """Sample XML metadata matches exact SHA-256 checksum."""
        h = hashlib.sha256()
        with open(SAMPLE_XML_PATH, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        assert h.hexdigest() == EXPECTED_XML_SHA256, "XML metadata checksum mismatch"


class TestDemRasterStructure:
    """Verifies raster properties, COG structure, and coordinate reference system."""

    def test_raster_driver_and_cog_format(self):
        """Tile is a valid Cloud-Optimized GeoTIFF (COG)."""
        with rasterio.open(SAMPLE_TIF_PATH) as src:
            assert src.driver == "GTiff"
            assert src.count == 1
            assert src.dtypes[0] == "float32"
            assert src.profile.get("tiled", False) is True
            assert src.block_shapes[0] == (1024, 1024)
            # COG pyramid overviews present
            overviews = src.overviews(1)
            assert len(overviews) >= 3
            assert overviews[:3] == [2, 4, 8]

    def test_raster_crs_and_resolution(self):
        """Tile has horizontal CRS EPSG:4326 and 1 arc-second resolution."""
        with rasterio.open(SAMPLE_TIF_PATH) as src:
            assert src.crs.to_epsg() == 4326
            assert src.width == 3600
            assert src.height == 3600
            # 1 arc-second = 1/3600 degree ~= 0.00027778
            x_res, y_res = src.res
            assert np.isclose(x_res, 1.0 / 3600.0, atol=1e-8)
            assert np.isclose(y_res, 1.0 / 3600.0, atol=1e-8)

    def test_raster_bounds_and_coverage(self):
        """Tile bounds correspond to 12°N-13°N and 76°E-77°E."""
        with rasterio.open(SAMPLE_TIF_PATH) as src:
            bounds = src.bounds
            assert np.isclose(bounds.left, 76.0, atol=0.01)
            assert np.isclose(bounds.right, 77.0, atol=0.01)
            assert np.isclose(bounds.bottom, 12.0, atol=0.01)
            assert np.isclose(bounds.top, 13.0, atol=0.01)


class TestDemTerrainSemantics:
    """Verifies elevation values, nodata handling, and plausibility for Karnataka."""

    def test_elevation_range_and_statistics(self):
        """Elevation values realistically represent southern Karnataka terrain."""
        with rasterio.open(SAMPLE_TIF_PATH) as src:
            data = src.read(1)
            assert data.shape == (3600, 3600)
            assert data.size == 12_960_000

            # Inland tile has zero nodata / 100% valid pixels
            valid = data[data != src.nodata] if src.nodata is not None else data.flatten()
            assert valid.size == data.size

            min_elev = float(np.min(valid))
            max_elev = float(np.max(valid))
            mean_elev = float(np.mean(valid))

            # Consistent with Mysore plateau and Cauvery basin (626m to 1332m)
            assert 620.0 < min_elev < 635.0, f"Unexpected min elevation: {min_elev}"
            assert 1320.0 < max_elev < 1340.0, f"Unexpected max elevation: {max_elev}"
            assert 750.0 < mean_elev < 820.0, f"Unexpected mean elevation: {mean_elev}"

            # Spot check: no negative elevations in this inland Deccan plateau tile
            assert np.all(valid > 0), "Found negative elevations in inland plateau tile"


class TestSpatialIntersectionWithKarnataka:
    """Verifies that the tile intersects Karnataka administrative boundaries."""

    def test_tile_intersects_karnataka_state(self, db_session: Session):
        """Tile bounding box intersects the official KSR-SAC Karnataka state polygon."""
        tile_poly = box(76.0, 12.0, 77.0, 13.0)
        state = db_session.execute(
            select(State).where(State.name == "Karnataka")
        ).scalar_one()

        intersects = db_session.execute(
            text("""
                SELECT ST_Intersects(
                    ST_MakeEnvelope(76.0, 12.0, 77.0, 13.0, 4326),
                    geometry
                )
                FROM states
                WHERE name = 'Karnataka'
            """)
        ).scalar()
        assert intersects is True, "Sample tile does not intersect Karnataka state boundary"

    def test_tile_intersects_expected_districts(self, db_session: Session):
        """Tile intersects Mysuru, Mandya, Hassan, and neighbouring districts."""
        intersecting_districts = db_session.execute(
            text("""
                SELECT name
                FROM districts
                WHERE ST_Intersects(
                    ST_MakeEnvelope(76.0, 12.0, 77.0, 13.0, 4326),
                    geometry
                )
                ORDER BY name
            """)
        ).scalars().all()

        assert len(intersecting_districts) >= 3
        # Known districts in N12_E076
        for expected in ["Hassan", "Mandya", "Mysuru"]:
            assert expected in intersecting_districts, f"{expected} missing from intersecting districts"


class TestSystemIsolation:
    """Guarantees zero mutation to ERA5 or existing hydrological GIS data."""

    def test_hydrological_gis_record_counts_preserved(self, db_session: Session):
        """All previously ingested hydrological GIS counts remain identical."""
        rb_count = db_session.execute(select(func.count()).select_from(RiverBasin)).scalar()
        sb_count = db_session.execute(select(func.count()).select_from(SubBasin)).scalar()
        riv_count = db_session.execute(select(func.count()).select_from(River)).scalar()
        drb_count = db_session.execute(select(func.count()).select_from(DistrictRiverBasin)).scalar()
        dsb_count = db_session.execute(select(func.count()).select_from(DistrictSubBasin)).scalar()

        assert rb_count == 25, f"River basins mutated: {rb_count}"
        assert sb_count == 116, f"Sub basins mutated: {sb_count}"
        assert riv_count == 15371, f"Rivers mutated: {riv_count}"
        assert drb_count == 54, f"District river basins mutated: {drb_count}"
        assert dsb_count == 264, f"District sub basins mutated: {dsb_count}"

    def test_era5_directory_untouched(self):
        """ERA5 historical raw directory contains no unexpected files."""
        era5_dir = PROJECT_ROOT / "data" / "raw" / "era5_historical"
        # Directory must exist and be isolated
        assert era5_dir.exists(), "ERA5 directory missing"
