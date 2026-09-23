"""
HydroSHEDS / CWC Hydrological GIS Normalization Foundation.

Reads and deterministically normalizes three source shapefiles from ZIP archives:
  1. basin_cwc_shp.zip — CWC/NWDP major basins (EPSG:7755 → 4326)
  2. hybas_as_lev07_v1c.zip — HydroBASINS Level-7 Asia (EPSG:4326)
  3. HydroRIVERS_v10_as_shp.zip — HydroRIVERS v1.0 Asia (EPSG:4326)

Design Principles:
  1. Pure read-only: Raw ZIP archives are NEVER modified or extracted to disk.
  2. Geometry validation with tracked repairs: ST_MakeValid only where needed,
     repair records are returned for audit.
  3. CRS validated and transformed (CWC only: EPSG:7755 → EPSG:4326).
  4. All source identifiers preserved verbatim.
  5. Spatial filtering uses actual polygon/line intersection, NOT centroid.

CWC major basins = authoritative statutory reference layer.
HydroBASINS Level-7 = detailed hydrological topology (NOT CWC hierarchy).
HydroRIVERS = river reach network with topology attributes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import CRS
from shapely.geometry import MultiLineString, MultiPolygon, Polygon, LineString
from shapely.validation import explain_validity
import shapely

logger = logging.getLogger(__name__)


def _is_nan(val) -> bool:
    """Check if a value is NaN, None, or 'nan' string."""
    if val is None:
        return True
    try:
        return np.isnan(val)
    except (TypeError, ValueError):
        return str(val).strip().lower() == "nan"

# CRS constants
CWC_SOURCE_CRS_EPSG = 7755  # Indian - Everest 1830 / India NSF LCC
TARGET_STORAGE_CRS = "EPSG:4326"
HYDROBASINS_CRS_EPSG = 4326
HYDRORIVERS_CRS_EPSG = 4326

# Expected counts from source audit
EXPECTED_CWC_BASIN_COUNT = 25
EXPECTED_CWC_KARNATAKA_INTERSECT = 7
EXPECTED_HYDROBASINS_KARNATAKA_MIN = 100  # At least 100 features expected

# Default archive paths relative to project root
DEFAULT_CWC_PATH = "data/raw/gis/hydrosheds/basin_cwc_shp.zip"
DEFAULT_HYDROBASINS_PATH = "data/raw/gis/hydrosheds/hybas_as_lev07_v1c.zip"
DEFAULT_HYDRORIVERS_PATH = "data/raw/gis/hydrosheds/HydroRIVERS_v10_as_shp.zip"


# ─── Exceptions ──────────────────────────────────────────────────────────────

class HydroGisValidationError(Exception):
    """Base exception for hydrological GIS validation errors."""


class HydroGisCrsError(HydroGisValidationError):
    """Raised when source CRS does not match expected."""


class HydroGisSchemaError(HydroGisValidationError):
    """Raised when required attribute columns are missing."""


class HydroGisCountError(HydroGisValidationError):
    """Raised when feature count does not match expected."""


# ─── Data Containers ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GeometryRepairRecord:
    """Audit record for a source geometry that required repair."""
    feature_type: str  # 'cwc_basin', 'hydrobasins', 'hydrorivers'
    source_id: str     # original feature identifier
    issue: str         # explanation of validity issue
    repair_method: str  # 'shapely.make_valid'


@dataclass(frozen=True)
class NormalizedCwcBasin:
    """CWC major basin normalized for PostGIS ingestion."""
    basin_name: str
    basin_code: str | None
    source_feature_id: str
    geometry: MultiPolygon  # EPSG:4326
    area_km2: float | None
    source_agency: str = "CWC/NWDP"
    source_dataset: str = "basin_cwc_shp"
    source_version: str = "2024"


@dataclass(frozen=True)
class NormalizedHydroBasin:
    """HydroBASINS Level-7 feature normalized for PostGIS ingestion."""
    hybas_id: int
    next_down: int
    next_sink: int
    main_bas: int
    sub_area: float
    up_area: float
    pfaf_id: int
    endo: int
    coast: int
    dist_sink: float
    dist_main: float
    order: int
    sort: int
    geometry: MultiPolygon  # EPSG:4326
    geometry_repaired: bool = False
    source_dataset: str = "hybas_as_lev07_v1c"
    source_version: str = "1c"


@dataclass(frozen=True)
class NormalizedHydroRiver:
    """HydroRIVERS reach segment normalized for PostGIS ingestion."""
    hyriv_id: int
    next_down: int
    main_riv: int
    length_km: float
    dist_dn_km: float
    dist_up_km: float
    catch_skm: float
    upland_skm: float
    dis_av_cms: float
    ord_stra: int
    ord_clas: int
    ord_flow: int
    hybas_l12: int
    geometry: MultiLineString  # EPSG:4326
    source_dataset: str = "HydroRIVERS_v10_as"
    source_version: str = "1.0"


@dataclass
class HydroNormalizationResult:
    """Result of a hydrological dataset normalization."""
    dataset_name: str
    total_source_features: int
    features_after_filter: int
    features_valid: int
    features_repaired: int
    repair_records: list[GeometryRepairRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Geometry Helpers ─────────────────────────────────────────────────────────

def _to_multipolygon(geom) -> MultiPolygon:
    """Coerce a Polygon to MultiPolygon if needed."""
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise HydroGisValidationError(
        f"Expected Polygon or MultiPolygon, got {type(geom).__name__}"
    )


def _to_multilinestring(geom) -> MultiLineString:
    """Coerce a LineString to MultiLineString if needed."""
    if isinstance(geom, MultiLineString):
        return geom
    if isinstance(geom, LineString):
        return MultiLineString([geom])
    raise HydroGisValidationError(
        f"Expected LineString or MultiLineString, got {type(geom).__name__}"
    )


def _validate_and_repair_polygon(
    geom, feature_type: str, source_id: str
) -> tuple[MultiPolygon, GeometryRepairRecord | None]:
    """Validate polygon geometry; repair with make_valid if invalid."""
    if geom is None or geom.is_empty:
        raise HydroGisValidationError(
            f"{feature_type} {source_id}: geometry is null/empty"
        )

    mp = _to_multipolygon(geom)
    if mp.is_valid:
        return mp, None

    issue = explain_validity(mp)
    repaired = shapely.make_valid(mp)
    repaired = _to_multipolygon(repaired)

    if not repaired.is_valid:
        raise HydroGisValidationError(
            f"{feature_type} {source_id}: geometry still invalid after repair: {explain_validity(repaired)}"
        )

    record = GeometryRepairRecord(
        feature_type=feature_type,
        source_id=source_id,
        issue=issue,
        repair_method="shapely.make_valid",
    )
    logger.warning(
        "Repaired %s %s: %s", feature_type, source_id, issue
    )
    return repaired, record


def _validate_and_repair_line(
    geom, feature_type: str, source_id: str
) -> tuple[MultiLineString, GeometryRepairRecord | None]:
    """Validate linestring geometry; repair with make_valid if invalid."""
    if geom is None or geom.is_empty:
        raise HydroGisValidationError(
            f"{feature_type} {source_id}: geometry is null/empty"
        )

    ml = _to_multilinestring(geom)
    if ml.is_valid:
        return ml, None

    issue = explain_validity(ml)
    repaired = shapely.make_valid(ml)
    # make_valid on lines may return GeometryCollection; extract lines
    if hasattr(repaired, 'geoms'):
        lines = [g for g in repaired.geoms if isinstance(g, (LineString, MultiLineString))]
        if not lines:
            raise HydroGisValidationError(
                f"{feature_type} {source_id}: no valid line geometry after repair"
            )
        all_lines = []
        for l in lines:
            if isinstance(l, MultiLineString):
                all_lines.extend(l.geoms)
            else:
                all_lines.append(l)
        repaired = MultiLineString(all_lines)
    else:
        repaired = _to_multilinestring(repaired)

    record = GeometryRepairRecord(
        feature_type=feature_type,
        source_id=source_id,
        issue=issue,
        repair_method="shapely.make_valid",
    )
    return repaired, record


# ─── CWC Basin Normalizer ────────────────────────────────────────────────────

class CwcBasinNormalizer:
    """Reads and normalizes CWC major basin shapefile from ZIP archive.

    Source CRS: EPSG:7755 (Indian - Everest 1830 / India NSF LCC)
    Target CRS: EPSG:4326 (WGS 84)
    Expected: 25 national basins
    """

    def __init__(self, zip_path: str | Path):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"CWC basin archive not found: {self.zip_path}")

    def normalize(self) -> tuple[list[NormalizedCwcBasin], HydroNormalizationResult]:
        """Read, validate, transform and return normalized CWC basins."""
        logger.info("Reading CWC basin shapefile from %s", self.zip_path)

        # Read from zip — geopandas handles this natively
        gdf = gpd.read_file(f"zip://{self.zip_path}")
        logger.info("CWC basins: %d features, CRS: %s", len(gdf), gdf.crs)

        result = HydroNormalizationResult(
            dataset_name="CWC Major Basins",
            total_source_features=len(gdf),
            features_after_filter=len(gdf),  # no filter for CWC — load all 25
            features_valid=0,
            features_repaired=0,
        )

        # Validate CRS
        if gdf.crs is None:
            raise HydroGisCrsError("CWC basin shapefile has no CRS defined")
        source_epsg = gdf.crs.to_epsg()
        if source_epsg != CWC_SOURCE_CRS_EPSG:
            raise HydroGisCrsError(
                f"CWC CRS expected EPSG:{CWC_SOURCE_CRS_EPSG}, got EPSG:{source_epsg}"
            )

        # Validate expected count
        if len(gdf) != EXPECTED_CWC_BASIN_COUNT:
            raise HydroGisCountError(
                f"CWC expected {EXPECTED_CWC_BASIN_COUNT} basins, got {len(gdf)}"
            )

        # Identify attribute columns — verified from source inspection
        columns = set(gdf.columns)
        logger.info("CWC basin columns: %s", sorted(columns))

        # CWC basin_cwc_shp uses: ba_name (basin name), bacode (basin code), area_sqkm
        name_col = "ba_name"
        code_col = "bacode"
        area_col = "area_sqkm"

        if name_col not in columns:
            raise HydroGisSchemaError(
                f"CWC: expected column '{name_col}' not found. Available: {sorted(columns)}"
            )
        if code_col not in columns:
            raise HydroGisSchemaError(
                f"CWC: expected column '{code_col}' not found. Available: {sorted(columns)}"
            )

        # Transform to EPSG:4326
        logger.info("Transforming CWC basins from EPSG:%d to EPSG:4326", CWC_SOURCE_CRS_EPSG)
        gdf_4326 = gdf.to_crs(TARGET_STORAGE_CRS)

        # Compute areas in source metric CRS for accurate area computation
        area_series = gdf[area_col] if area_col in columns else gdf.geometry.area / 1e6

        basins: list[NormalizedCwcBasin] = []
        for idx in range(len(gdf_4326)):
            row = gdf_4326.iloc[idx]
            raw_name = str(row[name_col]).strip() if not _is_nan(row[name_col]) else None
            raw_code = str(row[code_col]).strip() if not _is_nan(row[code_col]) else None
            source_fid = raw_code if raw_code else f"CWC_{idx}"

            # Use ba_code column (which contains the basin name again) as fallback
            if raw_name is None or raw_name == "nan":
                # Try ba_code column which has basin names
                if "ba_code" in columns and not _is_nan(row.get("ba_code")):
                    raw_name = str(row["ba_code"]).strip()
                else:
                    raw_name = f"Basin_{source_fid}"

            geom = row.geometry
            mp, repair_rec = _validate_and_repair_polygon(
                geom, "cwc_basin", source_fid
            )
            if repair_rec:
                result.features_repaired += 1
                result.repair_records.append(repair_rec)

            result.features_valid += 1

            area_val = float(area_series.iloc[idx]) if not _is_nan(area_series.iloc[idx]) else None

            basin = NormalizedCwcBasin(
                basin_name=raw_name,
                basin_code=raw_code,
                source_feature_id=source_fid,
                geometry=mp,
                area_km2=area_val,
            )
            basins.append(basin)

        logger.info(
            "CWC normalization complete: %d basins, %d repaired",
            len(basins), result.features_repaired
        )
        return basins, result


# ─── HydroBASINS Level-7 Normalizer ──────────────────────────────────────────

class HydroBasinsNormalizer:
    """Reads and normalizes HydroBASINS Level-7 Asia from ZIP archive.

    CRS: EPSG:4326 (no transformation needed)
    Filters to features intersecting Karnataka state boundary.
    Preserves border-crossing catchments.
    """

    REQUIRED_COLUMNS = frozenset({
        "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS",
        "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST",
        "DIST_SINK", "DIST_MAIN", "ORDER", "SORT", "geometry",
    })

    def __init__(self, zip_path: str | Path):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"HydroBASINS archive not found: {self.zip_path}")

    def normalize(
        self,
        state_boundary: MultiPolygon | Polygon,
    ) -> tuple[list[NormalizedHydroBasin], HydroNormalizationResult]:
        """Read, validate, filter by Karnataka intersection, return normalized features."""
        logger.info("Reading HydroBASINS Level-7 from %s", self.zip_path)

        gdf = gpd.read_file(f"zip://{self.zip_path}")
        logger.info("HydroBASINS: %d features, CRS: %s", len(gdf), gdf.crs)

        result = HydroNormalizationResult(
            dataset_name="HydroBASINS Level-7",
            total_source_features=len(gdf),
            features_after_filter=0,
            features_valid=0,
            features_repaired=0,
        )

        # Validate CRS
        if gdf.crs is None or gdf.crs.to_epsg() != HYDROBASINS_CRS_EPSG:
            raise HydroGisCrsError(
                f"HydroBASINS CRS expected EPSG:{HYDROBASINS_CRS_EPSG}, got {gdf.crs}"
            )

        # Validate required columns
        missing = self.REQUIRED_COLUMNS - set(gdf.columns)
        if missing:
            raise HydroGisSchemaError(
                f"HydroBASINS missing columns: {sorted(missing)}"
            )

        # Filter by spatial intersection with Karnataka boundary
        # Use actual polygon intersection, NOT centroid
        logger.info("Filtering HydroBASINS by Karnataka intersection...")
        state_geom = gpd.GeoSeries([state_boundary], crs="EPSG:4326")
        state_gdf = gpd.GeoDataFrame(geometry=state_geom, crs="EPSG:4326")

        # Spatial join: keep features that intersect Karnataka
        filtered = gpd.sjoin(gdf, state_gdf, how="inner", predicate="intersects")
        # Remove duplicate rows from sjoin (same feature can intersect multiple state parts)
        filtered = filtered.drop_duplicates(subset="HYBAS_ID")

        result.features_after_filter = len(filtered)
        logger.info(
            "HydroBASINS: %d of %d features intersect Karnataka",
            len(filtered), len(gdf)
        )

        if len(filtered) < EXPECTED_HYDROBASINS_KARNATAKA_MIN:
            result.warnings.append(
                f"Fewer than expected features: {len(filtered)} < {EXPECTED_HYDROBASINS_KARNATAKA_MIN}"
            )

        features: list[NormalizedHydroBasin] = []
        for _, row in filtered.iterrows():
            hybas_id = int(row["HYBAS_ID"])
            geom = row.geometry
            mp, repair_rec = _validate_and_repair_polygon(
                geom, "hydrobasins", str(hybas_id)
            )
            repaired = False
            if repair_rec:
                result.features_repaired += 1
                result.repair_records.append(repair_rec)
                repaired = True

            result.features_valid += 1

            feat = NormalizedHydroBasin(
                hybas_id=hybas_id,
                next_down=int(row["NEXT_DOWN"]),
                next_sink=int(row["NEXT_SINK"]),
                main_bas=int(row["MAIN_BAS"]),
                sub_area=float(row["SUB_AREA"]),
                up_area=float(row["UP_AREA"]),
                pfaf_id=int(row["PFAF_ID"]),
                endo=int(row["ENDO"]),
                coast=int(row["COAST"]),
                dist_sink=float(row["DIST_SINK"]),
                dist_main=float(row["DIST_MAIN"]),
                order=int(row["ORDER"]),
                sort=int(row["SORT"]),
                geometry=mp,
                geometry_repaired=repaired,
            )
            features.append(feat)

        logger.info(
            "HydroBASINS normalization complete: %d features, %d repaired",
            len(features), result.features_repaired
        )
        return features, result


# ─── HydroRIVERS Normalizer ──────────────────────────────────────────────────

class HydroRiversNormalizer:
    """Reads and normalizes HydroRIVERS v1.0 Asia from ZIP archive.

    CRS: EPSG:4326 (no transformation needed)
    Filters to reaches intersecting Karnataka state boundary.
    Preserves cross-boundary reaches.
    """

    REQUIRED_COLUMNS = frozenset({
        "HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM",
        "DIST_DN_KM", "DIST_UP_KM", "CATCH_SKM", "UPLAND_SKM",
        "DIS_AV_CMS", "ORD_STRA", "ORD_CLAS", "ORD_FLOW",
        "HYBAS_L12", "geometry",
    })

    def __init__(self, zip_path: str | Path):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"HydroRIVERS archive not found: {self.zip_path}")

    def normalize(
        self,
        state_boundary: MultiPolygon | Polygon,
    ) -> tuple[list[NormalizedHydroRiver], HydroNormalizationResult]:
        """Read, validate, filter by Karnataka intersection, return normalized features."""
        logger.info("Reading HydroRIVERS from %s", self.zip_path)

        # HydroRIVERS ZIP contains files in a subdirectory:
        # HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as.shp
        gdf = gpd.read_file(
            f"zip://{self.zip_path}!HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as.shp"
        )
        logger.info("HydroRIVERS: %d features, CRS: %s", len(gdf), gdf.crs)

        result = HydroNormalizationResult(
            dataset_name="HydroRIVERS v1.0",
            total_source_features=len(gdf),
            features_after_filter=0,
            features_valid=0,
            features_repaired=0,
        )

        # Validate CRS
        if gdf.crs is None or gdf.crs.to_epsg() != HYDRORIVERS_CRS_EPSG:
            raise HydroGisCrsError(
                f"HydroRIVERS CRS expected EPSG:{HYDRORIVERS_CRS_EPSG}, got {gdf.crs}"
            )

        # Validate required columns
        missing = self.REQUIRED_COLUMNS - set(gdf.columns)
        if missing:
            raise HydroGisSchemaError(
                f"HydroRIVERS missing columns: {sorted(missing)}"
            )

        # Filter by spatial intersection with Karnataka boundary
        logger.info("Filtering HydroRIVERS by Karnataka intersection...")
        state_geom = gpd.GeoSeries([state_boundary], crs="EPSG:4326")
        state_gdf = gpd.GeoDataFrame(geometry=state_geom, crs="EPSG:4326")

        filtered = gpd.sjoin(gdf, state_gdf, how="inner", predicate="intersects")
        filtered = filtered.drop_duplicates(subset="HYRIV_ID")

        result.features_after_filter = len(filtered)
        logger.info(
            "HydroRIVERS: %d of %d features intersect Karnataka",
            len(filtered), len(gdf)
        )

        features: list[NormalizedHydroRiver] = []
        for _, row in filtered.iterrows():
            hyriv_id = int(row["HYRIV_ID"])
            geom = row.geometry
            ml, repair_rec = _validate_and_repair_line(
                geom, "hydrorivers", str(hyriv_id)
            )
            if repair_rec:
                result.features_repaired += 1
                result.repair_records.append(repair_rec)

            result.features_valid += 1

            feat = NormalizedHydroRiver(
                hyriv_id=hyriv_id,
                next_down=int(row["NEXT_DOWN"]),
                main_riv=int(row["MAIN_RIV"]),
                length_km=float(row["LENGTH_KM"]),
                dist_dn_km=float(row["DIST_DN_KM"]),
                dist_up_km=float(row["DIST_UP_KM"]),
                catch_skm=float(row["CATCH_SKM"]),
                upland_skm=float(row["UPLAND_SKM"]),
                dis_av_cms=float(row["DIS_AV_CMS"]),
                ord_stra=int(row["ORD_STRA"]),
                ord_clas=int(row["ORD_CLAS"]),
                ord_flow=int(row["ORD_FLOW"]),
                hybas_l12=int(row["HYBAS_L12"]),
                geometry=ml,
            )
            features.append(feat)

        logger.info(
            "HydroRIVERS normalization complete: %d features, %d repaired",
            len(features), result.features_repaired
        )
        return features, result
