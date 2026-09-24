"""
Spatial, terrain, and hydrological feature enrichment service for ERA5 grid cells.

Extracts real static spatial attributes from:
1. Copernicus DEM GLO-30 (~30m VRT mosaic): zonal elevation mean and Horn metric slope.
2. CWC statutory river basins: basin_id, basin_name.
3. HydroBASINS Level-7 catchments: sub_basin_id, sub_basin_name, hybas_id.
4. HydroRIVERS reach segments: distance_to_river_m, nearest_river_id.
5. KSR-SAC administrative districts: district_id, district_name.

Results are deterministically cached to JSON on disk for instant reloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _find_project_root() -> Path:
    """Resolve repository project root directory."""
    curr = Path(__file__).resolve().parent
    for parent in [curr] + list(curr.parents):
        if (parent / "data").exists() and (parent / "backend").exists():
            return parent
    # Default fallback
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _find_project_root()
DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "processed" / "gis_cache" / "cell_spatial_features.json"
DEFAULT_DEM_VRT_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "dem" / "karnataka_dem.vrt"


@dataclass(frozen=True)
class CellSpatialAttributes:
    """Static spatial, terrain, and hydrological attributes for a single ERA5 grid cell."""

    cell_id: str
    latitude: float
    longitude: float

    # Terrain
    elevation_mean: float | None
    slope_mean: float | None

    # Hydrology
    basin_id: str | None
    basin_name: str | None
    sub_basin_id: str | None
    sub_basin_name: str | None
    hybas_id: int | None
    distance_to_river_m: float | None
    nearest_river_id: str | None

    # Administrative
    district_id: str | None
    district_name: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert attributes to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CellSpatialAttributes:
        """Instantiate from dictionary."""
        return cls(**data)


class SpatialEnrichmentService:
    """
    Provides static terrain, hydrological, and administrative attributes for ERA5 grid cells.

    Uses a disk-backed JSON cache for ultra-fast, deterministic lookups.
    Extracts real data from PostGIS and the Copernicus DEM VRT when building the cache.
    """

    def __init__(
        self,
        cache_path: Path | str | None = None,
        dem_vrt_path: Path | str | None = None,
        auto_load: bool = True,
    ):
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.dem_vrt_path = Path(dem_vrt_path) if dem_vrt_path else DEFAULT_DEM_VRT_PATH
        self._cache: dict[str, CellSpatialAttributes] = {}

        if auto_load and self.cache_path.exists():
            self.load_cache()

    def load_cache(self) -> None:
        """Load precomputed spatial features from disk cache."""
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = {
                cell_id: CellSpatialAttributes.from_dict(attrs)
                for cell_id, attrs in data.items()
            }
            logger.info("Loaded %d cell spatial features from %s", len(self._cache), self.cache_path)
        except Exception as e:
            logger.warning("Failed to load spatial cache from %s: %e", self.cache_path, e)
            self._cache = {}

    def save_cache(self) -> None:
        """Save spatial attributes in-memory to disk cache."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            cell_id: attrs.to_dict() for cell_id, attrs in self._cache.items()
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, sort_keys=True)
        logger.info("Saved %d cell spatial features to %s", len(self._cache), self.cache_path)

    def get_cell_attributes(
        self,
        cell_id: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> CellSpatialAttributes:
        """
        Retrieve spatial attributes for a cell.

        If missing from cache and coordinates are provided, generates attributes on-demand.
        """
        if cell_id in self._cache:
            return self._cache[cell_id]

        if latitude is not None and longitude is not None:
            attrs = self._extract_cell_attributes(cell_id, latitude, longitude)
            self._cache[cell_id] = attrs
            return attrs

        raise KeyError(f"Cell '{cell_id}' not found in spatial cache and coordinates not provided")

    def build_cache_for_cells(
        self,
        cells: list[Any],
        force: bool = False,
    ) -> dict[str, CellSpatialAttributes]:
        """
        Build or update the spatial attributes cache for a list of GridCell objects.

        If force=False and cached values exist, reuses existing entries.
        """
        if not force and self._cache and all(c.cell_id in self._cache for c in cells):
            logger.info("All %d cells already present in spatial cache", len(cells))
            return self._cache

        import rasterio
        from rasterio.windows import from_bounds
        from sqlalchemy import text
        from app.db.session import _get_engine
        from app.gis.terrain_engine import (
            calculate_elevation_statistics,
            calculate_slope_statistics,
            compute_horn_slope,
        )

        engine = _get_engine()

        logger.info("Opening DEM VRT mosaic: %s", self.dem_vrt_path)
        with rasterio.open(str(self.dem_vrt_path)) as dem_src, engine.connect() as conn:
            res_x_deg = dem_src.res[0]
            res_y_deg = dem_src.res[1]

            for c in cells:
                cell_id = c.cell_id
                lat = float(c.lat)
                lon = float(c.lon)

                if not force and cell_id in self._cache:
                    continue

                # 1. Terrain: elevation & slope from Copernicus DEM VRT
                minx, miny, maxx, maxy = lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125
                window = from_bounds(minx, miny, maxx, maxy, dem_src.transform)
                dem_arr = dem_src.read(1, window=window)

                elev_stats = calculate_elevation_statistics(dem_arr, nodata_val=dem_src.nodata)
                elev_mean = (
                    round(float(elev_stats["elevation_mean"]), 2)
                    if elev_stats["elevation_mean"] is not None
                    else None
                )

                slope_arr = compute_horn_slope(dem_arr, res_x_deg, res_y_deg, maxy)
                slope_stats = calculate_slope_statistics(slope_arr)
                slope_mean = (
                    round(float(slope_stats["slope_mean"]), 2)
                    if slope_stats["slope_mean"] is not None
                    else None
                )

                # 2. Administrative District (point contains, else largest intersecting area)
                dist_row = conn.execute(
                    text(
                        """
                        SELECT id, name FROM districts
                        WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))
                        LIMIT 1
                        """
                    ),
                    {"lat": lat, "lon": lon},
                ).fetchone()

                if dist_row is None:
                    dist_row = conn.execute(
                        text(
                            """
                            SELECT id, name FROM districts
                            WHERE ST_Intersects(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
                            ORDER BY ST_Area(ST_Intersection(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))) DESC
                            LIMIT 1
                            """
                        ),
                        {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
                    ).fetchone()

                district_id = str(dist_row[0]) if dist_row else None
                district_name = str(dist_row[1]) if dist_row else None

                # 3. Sub-basin (HydroBASINS Level-7)
                sb_row = conn.execute(
                    text(
                        """
                        SELECT id, name, hybas_id FROM sub_basins
                        WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))
                        LIMIT 1
                        """
                    ),
                    {"lat": lat, "lon": lon},
                ).fetchone()

                if sb_row is None:
                    sb_row = conn.execute(
                        text(
                            """
                            SELECT id, name, hybas_id FROM sub_basins
                            WHERE ST_Intersects(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
                            ORDER BY ST_Area(ST_Intersection(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))) DESC
                            LIMIT 1
                            """
                        ),
                        {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
                    ).fetchone()

                sub_basin_id = str(sb_row[0]) if sb_row else None
                sub_basin_name = str(sb_row[1]) if sb_row else None
                hybas_id = int(sb_row[2]) if sb_row and sb_row[2] is not None else None

                # 4. River basin (CWC statutory)
                rb_row = conn.execute(
                    text(
                        """
                        SELECT id, name FROM river_basins
                        WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))
                        LIMIT 1
                        """
                    ),
                    {"lat": lat, "lon": lon},
                ).fetchone()

                if rb_row is None:
                    rb_row = conn.execute(
                        text(
                            """
                            SELECT id, name FROM river_basins
                            WHERE ST_Intersects(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
                            ORDER BY ST_Area(ST_Intersection(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))) DESC
                            LIMIT 1
                            """
                        ),
                        {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
                    ).fetchone()

                basin_id = str(rb_row[0]) if rb_row else None
                basin_name = str(rb_row[1]) if rb_row else None

                # 5. Nearest river and geodesic distance
                riv_row = conn.execute(
                    text(
                        """
                        SELECT id, name, ST_Distance(geometry::geography, ST_SetSRID(ST_Point(:lon, :lat), 4326)::geography) as dist_m
                        FROM rivers
                        ORDER BY geometry <-> ST_SetSRID(ST_Point(:lon, :lat), 4326)
                        LIMIT 1
                        """
                    ),
                    {"lat": lat, "lon": lon},
                ).fetchone()

                nearest_river_id = str(riv_row[1]) if riv_row else None
                distance_to_river_m = (
                    round(float(riv_row[2]), 2) if riv_row and riv_row[2] is not None else None
                )

                attrs = CellSpatialAttributes(
                    cell_id=cell_id,
                    latitude=lat,
                    longitude=lon,
                    elevation_mean=elev_mean,
                    slope_mean=slope_mean,
                    basin_id=basin_id,
                    basin_name=basin_name,
                    sub_basin_id=sub_basin_id,
                    sub_basin_name=sub_basin_name,
                    hybas_id=hybas_id,
                    distance_to_river_m=distance_to_river_m,
                    nearest_river_id=nearest_river_id,
                    district_id=district_id,
                    district_name=district_name,
                )
                self._cache[cell_id] = attrs

        self.save_cache()
        return self._cache

    def set_mock_attributes(self, cell_id: str, attrs: CellSpatialAttributes) -> None:
        """Inject mock spatial attributes for testing."""
        self._cache[cell_id] = attrs
