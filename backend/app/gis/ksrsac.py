"""
KSR-SAC Administrative GIS Normalization Foundation.

Reads and deterministically normalizes authoritative Karnataka administrative
boundary shapefiles from the Karnataka State Remote Sensing Applications Centre
(KSR-SAC) / KGIS:
- State.shp (1 state)
- District.shp (31 districts)
- Taluk.shp (240 taluks)

Design Principles:
1. Pure read-only operation: Raw source files under data/raw/gis/ksrsac/ are
   NEVER modified, repaired in-place, or overwritten.
2. Deterministic topological normalization: Any invalid source geometry
   (e.g., ring self-intersections) is detected, logged, and repaired using
   shapely.make_valid() exclusively in memory during normalization.
   Never use buffer(0).
3. Coordinate reference system: Source EPSG:32643 (UTM Zone 43N, metres) is
   validated and transformed to EPSG:4326 (WGS 84 degrees) for PostGIS storage.
4. Identifiers preserved: KGIS codes, LGD codes, district/taluk names, and
   parent-child relationships are strictly validated and preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
from pyproj import CRS
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.validation import explain_validity

# Default relative overlap tolerance for topological sanity checks
# (handles floating-point edge-coincidence artifacts between adjacent survey vectors)
DEFAULT_RELATIVE_OVERLAP_TOLERANCE: float = 1e-10

EXPECTED_SOURCE_CRS_EPSG: int = 32643
TARGET_STORAGE_CRS: str = "EPSG:4326"

REQUIRED_DISTRICT_COLUMNS: frozenset[str] = frozenset(
    {"KGISDistri", "LGD_Distri", "KGISDist_1", "geometry"}
)

REQUIRED_TALUK_COLUMNS: frozenset[str] = frozenset(
    {"KGISTalukC", "LGD_TalukC", "KGISTalukN", "KGISDistri", "geometry"}
)

REQUIRED_STATE_COLUMNS: frozenset[str] = frozenset(
    {"KGISStateI", "KGISStateC", "KGISStateN", "geometry"}
)

EXPECTED_STATE_COUNT: int = 1
EXPECTED_DISTRICT_COUNT: int = 31
EXPECTED_TALUK_COUNT: int = 240
EXPECTED_VIJAYANAGARA_TALUK_COUNT: int = 6
VIJAYANAGARA_KGIS_CODE: str = "31"
VIJAYANAGARA_LGD_CODE: str = "738"


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class KsrsacValidationError(Exception):
    """Base exception for KSR-SAC validation and normalization errors."""


class KsrsacFileNotFoundError(KsrsacValidationError):
    """Raised when expected KSR-SAC shapefile does not exist."""


class KsrsacCrsError(KsrsacValidationError):
    """Raised when source shapefile CRS is not the expected EPSG:32643."""


class KsrsacSchemaError(KsrsacValidationError):
    """Raised when required source attribute columns are missing."""


class KsrsacTopologyError(KsrsacValidationError):
    """Raised when spatial relationships or overlap tolerances are violated."""


# -----------------------------------------------------------------------------
# Data Containers
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class GeometryRepairRecord:
    """Audit record for a source geometry that required deterministic repair."""

    feature_type: str  # 'district' or 'taluk'
    kgis_code: str
    lgd_code: str
    name: str
    issue_description: str
    repair_operation: str
    valid_before: bool
    valid_after: bool
    area_before_m2: float
    area_after_m2: float
    area_diff_m2: float
    relative_area_diff: float


@dataclass(frozen=True)
class NormalizedState:
    """Normalized administrative state record in EPSG:4326."""

    kgis_state_id: int
    state_code: str
    state_name: str
    area_sq_m: float
    perimeter_m: float
    geometry: MultiPolygon
    centroid: Point
    was_repaired: bool = False
    repair_record: GeometryRepairRecord | None = None

    @property
    def wkt(self) -> str:
        """EWKT string formatted for PostGIS EPSG:4326 insertion."""
        return f"SRID=4326;{self.geometry.wkt}"

    @property
    def raw_wkt(self) -> str:
        """Standard WKT string."""
        return self.geometry.wkt

    @property
    def centroid_wkt(self) -> str:
        """EWKT string for state centroid in EPSG:4326."""
        return f"SRID=4326;{self.centroid.wkt}"


@dataclass(frozen=True)
class NormalizedDistrict:
    """Normalized administrative district record in EPSG:4326."""

    kgis_district_code: str
    lgd_district_code: str
    district_name: str
    bhu_code: str | None
    area_sq_m: float
    perimeter_m: float
    geometry: MultiPolygon
    centroid: Point
    was_repaired: bool = False
    repair_record: GeometryRepairRecord | None = None

    @property
    def wkt(self) -> str:
        """EWKT string formatted for PostGIS EPSG:4326 insertion."""
        return f"SRID=4326;{self.geometry.wkt}"

    @property
    def raw_wkt(self) -> str:
        """Standard WKT string."""
        return self.geometry.wkt

    @property
    def centroid_wkt(self) -> str:
        """EWKT string for district centroid in EPSG:4326."""
        return f"SRID=4326;{self.centroid.wkt}"


@dataclass(frozen=True)
class NormalizedTaluk:
    """Normalized administrative taluk record in EPSG:4326."""

    kgis_taluk_code: str
    lgd_taluk_code: str
    taluk_name: str
    parent_kgis_district_code: str
    parent_lgd_district_code: str
    area_sq_m: float
    perimeter_m: float
    geometry: MultiPolygon
    centroid: Point
    was_repaired: bool = False
    repair_record: GeometryRepairRecord | None = None

    @property
    def wkt(self) -> str:
        """EWKT string formatted for PostGIS EPSG:4326 insertion."""
        return f"SRID=4326;{self.geometry.wkt}"

    @property
    def raw_wkt(self) -> str:
        """Standard WKT string."""
        return self.geometry.wkt

    @property
    def centroid_wkt(self) -> str:
        """EWKT string for taluk centroid in EPSG:4326."""
        return f"SRID=4326;{self.centroid.wkt}"


@dataclass
class KsrsacNormalizationResult:
    """Complete result of KSR-SAC administrative boundary normalization."""

    districts: list[NormalizedDistrict]
    taluks: list[NormalizedTaluk]
    repairs: list[GeometryRepairRecord] = field(default_factory=list)
    source_district_crs: str = "EPSG:32643"
    source_taluk_crs: str = "EPSG:32643"
    target_crs: str = TARGET_STORAGE_CRS
    relative_overlap_tolerance: float = DEFAULT_RELATIVE_OVERLAP_TOLERANCE

    @property
    def district_count(self) -> int:
        return len(self.districts)

    @property
    def taluk_count(self) -> int:
        return len(self.taluks)

    @property
    def repair_count(self) -> int:
        return len(self.repairs)

    def get_district_by_kgis(self, code: str) -> NormalizedDistrict | None:
        norm = code.strip().zfill(2)
        for d in self.districts:
            if d.kgis_district_code == norm:
                return d
        return None

    def get_district_by_lgd(self, code: str) -> NormalizedDistrict | None:
        norm = str(code).strip()
        for d in self.districts:
            if d.lgd_district_code == norm:
                return d
        return None

    def get_taluks_for_district(self, kgis_district_code: str) -> list[NormalizedTaluk]:
        norm = kgis_district_code.strip().zfill(2)
        return [t for t in self.taluks if t.parent_kgis_district_code == norm]


# -----------------------------------------------------------------------------
# Geometry Helpers
# -----------------------------------------------------------------------------


def to_multipolygon(geom: Any) -> MultiPolygon:
    """
    Ensure geometry is strictly a shapely MultiPolygon.

    PostGIS columns for districts and taluks are defined as MULTIPOLYGON (SRID 4326).
    Single Polygon instances are wrapped into MultiPolygon([polygon]) without alteration.
    """
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if getattr(geom, "geom_type", "") == "GeometryCollection":
        polys: list[Polygon] = []
        for g in geom.geoms:
            if isinstance(g, Polygon):
                polys.append(g)
            elif isinstance(g, MultiPolygon):
                polys.extend(g.geoms)
        if polys:
            return MultiPolygon(polys)
    raise KsrsacValidationError(
        f"Cannot coerce geometry of type '{getattr(geom, 'geom_type', type(geom))}' to MultiPolygon"
    )


def _resolve_default_source_dir() -> Path:
    """Find data/raw/gis/ksrsac/ whether running from repo root or backend/."""
    candidates = [
        Path("data/raw/gis/ksrsac"),
        Path("../data/raw/gis/ksrsac"),
    ]
    for c in candidates:
        if c.is_dir():
            return c.resolve()

    # Search upwards from current file location
    current = Path(__file__).resolve().parent
    for _ in range(6):
        cand = current / "data" / "raw" / "gis" / "ksrsac"
        if cand.is_dir():
            return cand.resolve()
        current = current.parent

    return Path("data/raw/gis/ksrsac").resolve()


# -----------------------------------------------------------------------------
# Normalizer Engine
# -----------------------------------------------------------------------------


class KsrsacAdminNormalizer:
    """
    Reusable normalizer and validator for KSR-SAC administrative GIS data.

    Validates source shapefiles, applies deterministic repair to invalid geometries,
    verifies parent-child topology, and produces normalized EPSG:4326 records.
    """

    def __init__(
        self,
        district_path: str | Path | None = None,
        taluk_path: str | Path | None = None,
        state_path: str | Path | None = None,
        relative_overlap_tolerance: float = DEFAULT_RELATIVE_OVERLAP_TOLERANCE,
    ):
        base_dir = _resolve_default_source_dir()
        self.district_path = (
            Path(district_path).resolve()
            if district_path
            else (base_dir / "District.shp")
        )
        self.taluk_path = (
            Path(taluk_path).resolve()
            if taluk_path
            else (base_dir / "Taluk.shp")
        )
        self.state_path = (
            Path(state_path).resolve()
            if state_path
            else (base_dir / "State.shp")
        )
        self.relative_overlap_tolerance = relative_overlap_tolerance

    def normalize(self) -> KsrsacNormalizationResult:
        """
        Execute full normalization and validation pipeline.

        Returns:
            KsrsacNormalizationResult containing 31 normalized districts,
            240 normalized taluks, and audit records of any repairs.
        """
        # 1. Source existence check
        self._check_file_exists(self.district_path, "District shapefile")
        self._check_file_exists(self.taluk_path, "Taluk shapefile")

        # 2. Ingest into GeoDataFrames (in-memory read-only)
        districts_gdf = gpd.read_file(self.district_path)
        taluks_gdf = gpd.read_file(self.taluk_path)

        # 3. Validate CRS
        self._validate_crs(districts_gdf, "District.shp")
        self._validate_crs(taluks_gdf, "Taluk.shp")

        # 4. Validate schema / required columns
        self._validate_columns(districts_gdf, REQUIRED_DISTRICT_COLUMNS, "District.shp")
        self._validate_columns(taluks_gdf, REQUIRED_TALUK_COLUMNS, "Taluk.shp")

        # 5. Validate feature counts and unique identifiers
        self._validate_district_identifiers(districts_gdf)
        self._validate_taluk_identifiers(taluks_gdf)

        # 6. Check for empty or null geometries
        self._validate_non_empty_geometries(districts_gdf, "District")
        self._validate_non_empty_geometries(taluks_gdf, "Taluk")

        # 7. Deterministic repair in source metric coordinates (EPSG:32643)
        district_repairs = self._repair_geometries(districts_gdf, "district", "KGISDistri", "LGD_Distri", "KGISDist_1")
        taluk_repairs = self._repair_geometries(taluks_gdf, "taluk", "KGISTalukC", "LGD_TalukC", "KGISTalukN")
        all_repairs = district_repairs + taluk_repairs

        # Verify all geometries are valid post-repair
        if not districts_gdf.geometry.is_valid.all():
            raise KsrsacTopologyError("District geometries contain invalid polygons even after repair")
        if not taluks_gdf.geometry.is_valid.all():
            raise KsrsacTopologyError("Taluk geometries contain invalid polygons even after repair")

        # 8. Validate parent-child relationship and Vijayanagara condition
        self._validate_parent_relationships(districts_gdf, taluks_gdf)

        # 9. Validate topological non-overlap under relative tolerance
        self._validate_non_overlapping(districts_gdf, taluks_gdf)

        # 10. Transform to EPSG:4326 for storage
        districts_4326 = districts_gdf.to_crs(TARGET_STORAGE_CRS)
        taluks_4326 = taluks_gdf.to_crs(TARGET_STORAGE_CRS)

        # Ensure all transformed geometries remain valid in EPSG:4326
        if not districts_4326.geometry.is_valid.all():
            raise KsrsacTopologyError("District geometries failed validity check after EPSG:4326 reprojection")
        if not taluks_4326.geometry.is_valid.all():
            raise KsrsacTopologyError("Taluk geometries failed validity check after EPSG:4326 reprojection")

        # 11. Build deterministic normalized records
        repairs_by_taluk = {r.kgis_code: r for r in taluk_repairs}
        repairs_by_district = {r.kgis_code: r for r in district_repairs}

        normalized_districts = self._build_normalized_districts(
            districts_gdf, districts_4326, repairs_by_district
        )
        kgis_to_lgd_district = {d.kgis_district_code: d.lgd_district_code for d in normalized_districts}

        normalized_taluks = self._build_normalized_taluks(
            taluks_gdf, taluks_4326, repairs_by_taluk, kgis_to_lgd_district
        )

        return KsrsacNormalizationResult(
            districts=normalized_districts,
            taluks=normalized_taluks,
            repairs=all_repairs,
            source_district_crs="EPSG:32643",
            source_taluk_crs="EPSG:32643",
            target_crs=TARGET_STORAGE_CRS,
            relative_overlap_tolerance=self.relative_overlap_tolerance,
        )

    def normalize_state(self) -> NormalizedState:
        """
        Execute normalization and validation for State.shp.

        Returns:
            NormalizedState in EPSG:4326.
        """
        # 1. Source existence check
        self._check_file_exists(self.state_path, "State shapefile")

        # 2. Ingest into GeoDataFrame (in-memory read-only)
        state_gdf = gpd.read_file(self.state_path)

        # 3. Validate CRS
        self._validate_crs(state_gdf, "State.shp")

        # 4. Validate schema / required columns
        self._validate_columns(state_gdf, REQUIRED_STATE_COLUMNS, "State.shp")

        # 5. Validate exactly one feature
        if len(state_gdf) != EXPECTED_STATE_COUNT:
            raise KsrsacSchemaError(
                f"State shapefile must contain exactly {EXPECTED_STATE_COUNT} feature, found {len(state_gdf)}"
            )

        # 6. Check for empty or null geometries
        self._validate_non_empty_geometries(state_gdf, "State")

        # 7. Check / repair geometry in source CRS (EPSG:32643)
        row = state_gdf.iloc[0]
        geom = row.geometry
        area_m2 = float(geom.area)
        perimeter_m = float(geom.length)

        was_repaired = False
        repair_record = None

        if not geom.is_valid:
            issue = explain_validity(geom)
            repaired_geom = shapely.make_valid(geom)
            if not repaired_geom.is_valid:
                raise KsrsacTopologyError(
                    f"State geometry could not be repaired: {issue}"
                )
            repaired_area = float(repaired_geom.area)
            diff_m2 = abs(repaired_area - area_m2)
            rel_diff = diff_m2 / area_m2 if area_m2 > 0 else 0.0
            was_repaired = True
            repair_record = GeometryRepairRecord(
                feature_type="state",
                kgis_code=str(row["KGISStateI"]),
                lgd_code=str(row["KGISStateC"]).strip(),
                name=str(row["KGISStateN"]).strip(),
                issue_description=issue,
                repair_operation="shapely.make_valid()",
                valid_before=False,
                valid_after=True,
                area_before_m2=area_m2,
                area_after_m2=repaired_area,
                area_diff_m2=diff_m2,
                relative_area_diff=rel_diff,
            )
            state_gdf.at[0, "geometry"] = repaired_geom

        # 8. Transform to EPSG:4326 for storage
        state_4326 = state_gdf.to_crs(TARGET_STORAGE_CRS)
        geom_4326 = state_4326.geometry.iloc[0]

        if not geom_4326.is_valid:
            raise KsrsacTopologyError("State geometry failed validity check after EPSG:4326 reprojection")

        mp_4326 = to_multipolygon(geom_4326)
        centroid_4326 = mp_4326.centroid

        kgis_state_id = int(row["KGISStateI"])
        state_code = str(row["KGISStateC"]).strip()
        state_name = str(row["KGISStateN"]).strip()

        return NormalizedState(
            kgis_state_id=kgis_state_id,
            state_code=state_code,
            state_name=state_name,
            area_sq_m=area_m2,
            perimeter_m=perimeter_m,
            geometry=mp_4326,
            centroid=centroid_4326,
            was_repaired=was_repaired,
            repair_record=repair_record,
        )

    def validate_state_containment(
        self,
        state: NormalizedState,
        districts: list[NormalizedDistrict],
        taluks: list[NormalizedTaluk] | None = None,
    ) -> None:
        """
        Validate that all districts and taluks topologically intersect the state
        and that their representative points fall within the state boundary.
        """
        for d in districts:
            if not state.geometry.intersects(d.geometry):
                raise KsrsacTopologyError(
                    f"District {d.district_name} (KGIS {d.kgis_district_code}) does not intersect State {state.state_name}"
                )
            if not state.geometry.contains(d.geometry.representative_point()):
                raise KsrsacTopologyError(
                    f"District {d.district_name} representative point not contained in State {state.state_name}"
                )
        if taluks:
            for t in taluks:
                if not state.geometry.intersects(t.geometry):
                    raise KsrsacTopologyError(
                        f"Taluk {t.taluk_name} (KGIS {t.kgis_taluk_code}) does not intersect State {state.state_name}"
                    )
                if not state.geometry.contains(t.geometry.representative_point()):
                    raise KsrsacTopologyError(
                        f"Taluk {t.taluk_name} representative point not contained in State {state.state_name}"
                    )

    # -------------------------------------------------------------------------
    # Internal Validation Steps
    # -------------------------------------------------------------------------

    @staticmethod
    def _check_file_exists(path: Path, label: str) -> None:
        if not path.is_file():
            raise KsrsacFileNotFoundError(f"{label} not found at expected path: {path}")

    @staticmethod
    def _validate_crs(gdf: gpd.GeoDataFrame, filename: str) -> None:
        if gdf.crs is None:
            raise KsrsacCrsError(f"{filename} has no CRS defined; expected EPSG:{EXPECTED_SOURCE_CRS_EPSG}")
        crs_obj = CRS(gdf.crs)
        epsg = crs_obj.to_epsg()
        if epsg != EXPECTED_SOURCE_CRS_EPSG:
            raise KsrsacCrsError(
                f"{filename} CRS is {gdf.crs} (EPSG:{epsg}); expected EPSG:{EXPECTED_SOURCE_CRS_EPSG}"
            )

    @staticmethod
    def _validate_columns(gdf: gpd.GeoDataFrame, required: frozenset[str], filename: str) -> None:
        actual = frozenset(gdf.columns)
        missing = required - actual
        if missing:
            raise KsrsacSchemaError(
                f"{filename} missing required attribute columns: {sorted(missing)}. Found: {sorted(actual)}"
            )

    @staticmethod
    def _validate_district_identifiers(districts: gpd.GeoDataFrame) -> None:
        count = len(districts)
        if count != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError(
                f"Expected exactly {EXPECTED_DISTRICT_COUNT} districts, found {count}"
            )
        unique_kgis = districts["KGISDistri"].nunique()
        if unique_kgis != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError(
                f"Expected {EXPECTED_DISTRICT_COUNT} unique KGIS district codes, found {unique_kgis}"
            )
        unique_lgd = districts["LGD_Distri"].nunique()
        if unique_lgd != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError(
                f"Expected {EXPECTED_DISTRICT_COUNT} unique LGD district codes, found {unique_lgd}"
            )

    @staticmethod
    def _validate_taluk_identifiers(taluks: gpd.GeoDataFrame) -> None:
        count = len(taluks)
        if count != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError(
                f"Expected exactly {EXPECTED_TALUK_COUNT} taluks, found {count}"
            )
        unique_kgis = taluks["KGISTalukC"].nunique()
        if unique_kgis != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError(
                f"Expected {EXPECTED_TALUK_COUNT} unique KGIS taluk codes, found {unique_kgis}"
            )
        unique_lgd = taluks["LGD_TalukC"].nunique()
        if unique_lgd != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError(
                f"Expected {EXPECTED_TALUK_COUNT} unique LGD taluk codes, found {unique_lgd}"
            )

    @staticmethod
    def _validate_non_empty_geometries(gdf: gpd.GeoDataFrame, label: str) -> None:
        null_count = gdf.geometry.isna().sum()
        if null_count > 0:
            raise KsrsacValidationError(f"{label} contains {null_count} null geometries")
        empty_count = gdf.geometry.is_empty.sum()
        if empty_count > 0:
            raise KsrsacValidationError(f"{label} contains {empty_count} empty geometries")

    @staticmethod
    def _repair_geometries(
        gdf: gpd.GeoDataFrame,
        feature_type: str,
        kgis_col: str,
        lgd_col: str,
        name_col: str,
    ) -> list[GeometryRepairRecord]:
        repairs: list[GeometryRepairRecord] = []
        invalid_mask = ~gdf.geometry.is_valid

        for idx in gdf[invalid_mask].index:
            orig_geom = gdf.loc[idx, "geometry"]
            issue = explain_validity(orig_geom)
            area_before = float(orig_geom.area)

            # Deterministic repair using shapely.make_valid
            repaired_geom = shapely.make_valid(orig_geom)
            area_after = float(repaired_geom.area)
            area_diff = abs(area_after - area_before)
            rel_diff = area_diff / area_before if area_before > 0 else 0.0

            gdf.loc[idx, "geometry"] = repaired_geom

            record = GeometryRepairRecord(
                feature_type=feature_type,
                kgis_code=str(gdf.loc[idx, kgis_col]).strip().zfill(2 if feature_type == "district" else 4),
                lgd_code=str(gdf.loc[idx, lgd_col]).strip(),
                name=str(gdf.loc[idx, name_col]).strip(),
                issue_description=issue,
                repair_operation="shapely.make_valid",
                valid_before=False,
                valid_after=bool(repaired_geom.is_valid),
                area_before_m2=area_before,
                area_after_m2=area_after,
                area_diff_m2=area_diff,
                relative_area_diff=rel_diff,
            )
            repairs.append(record)

        return repairs

    @staticmethod
    def _validate_parent_relationships(districts: gpd.GeoDataFrame, taluks: gpd.GeoDataFrame) -> None:
        district_codes = set(districts["KGISDistri"].astype(str).str.strip().str.zfill(2))
        taluk_parent_codes = set(taluks["KGISDistri"].astype(str).str.strip().str.zfill(2))

        missing_parents = taluk_parent_codes - district_codes
        if missing_parents:
            raise KsrsacTopologyError(
                f"Taluks reference non-existent parent KGIS district codes: {sorted(missing_parents)}"
            )

        # Spatial consistency: each taluk must intersect its declared parent district
        # and its representative point must lie inside parent district geometry
        district_geom_map = {
            str(row["KGISDistri"]).strip().zfill(2): row.geometry for _, row in districts.iterrows()
        }

        for idx, row in taluks.iterrows():
            parent_code = str(row["KGISDistri"]).strip().zfill(2)
            parent_geom = district_geom_map[parent_code]
            t_geom = row.geometry

            if not t_geom.intersects(parent_geom):
                raise KsrsacTopologyError(
                    f"Taluk {row['KGISTalukN']} (KGIS:{row['KGISTalukC']}) does not intersect parent district {parent_code}"
                )

            rep_pt = t_geom.representative_point()
            if not rep_pt.within(parent_geom):
                raise KsrsacTopologyError(
                    f"Taluk {row['KGISTalukN']} representative point does not fall within parent district {parent_code}"
                )

        # Vijayanagara 6-taluk validation
        vij_taluks = taluks[taluks["KGISDistri"].astype(str).str.strip().str.zfill(2) == VIJAYANAGARA_KGIS_CODE]
        if len(vij_taluks) != EXPECTED_VIJAYANAGARA_TALUK_COUNT:
            raise KsrsacTopologyError(
                f"Vijayanagara (KGIS {VIJAYANAGARA_KGIS_CODE}) must have exactly "
                f"{EXPECTED_VIJAYANAGARA_TALUK_COUNT} taluks, found {len(vij_taluks)}"
            )

    def _validate_non_overlapping(self, districts: gpd.GeoDataFrame, taluks: gpd.GeoDataFrame) -> None:
        # District non-overlap
        for i in range(len(districts)):
            a = districts.geometry.iloc[i]
            a_area = a.area
            for j in range(i + 1, len(districts)):
                b = districts.geometry.iloc[j]
                b_area = b.area
                intersection_area = a.intersection(b).area
                smaller_area = min(a_area, b_area)
                ratio = intersection_area / smaller_area if smaller_area > 0 else 0.0
                if ratio > self.relative_overlap_tolerance:
                    name_a = districts["KGISDist_1"].iloc[i]
                    name_b = districts["KGISDist_1"].iloc[j]
                    raise KsrsacTopologyError(
                        f"Substantive district overlap detected between {name_a} and {name_b}: "
                        f"overlap={intersection_area:.2f}m², ratio={ratio:.2e} > {self.relative_overlap_tolerance}"
                    )

        # Same-district taluk non-overlap
        for district_code, group in taluks.groupby("KGISDistri"):
            group = group.reset_index(drop=True)
            for i in range(len(group)):
                a = group.geometry.iloc[i]
                a_area = a.area
                for j in range(i + 1, len(group)):
                    b = group.geometry.iloc[j]
                    b_area = b.area
                    intersection_area = a.intersection(b).area
                    smaller_area = min(a_area, b_area)
                    ratio = intersection_area / smaller_area if smaller_area > 0 else 0.0
                    if ratio > self.relative_overlap_tolerance:
                        name_a = group["KGISTalukN"].iloc[i]
                        name_b = group["KGISTalukN"].iloc[j]
                        raise KsrsacTopologyError(
                            f"Substantive taluk overlap detected in district {district_code} "
                            f"between {name_a} and {name_b}: overlap={intersection_area:.2f}m², "
                            f"ratio={ratio:.2e} > {self.relative_overlap_tolerance}"
                        )

    # -------------------------------------------------------------------------
    # Record Construction
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_normalized_districts(
        districts_utm: gpd.GeoDataFrame,
        districts_4326: gpd.GeoDataFrame,
        repairs_by_district: dict[str, GeometryRepairRecord],
    ) -> list[NormalizedDistrict]:
        result: list[NormalizedDistrict] = []

        for idx in range(len(districts_4326)):
            row_utm = districts_utm.iloc[idx]
            row_4326 = districts_4326.iloc[idx]

            kgis_code = str(row_4326["KGISDistri"]).strip().zfill(2)
            lgd_code = str(row_4326["LGD_Distri"]).strip()
            name = str(row_4326["KGISDist_1"]).strip()
            bhu_code = str(row_4326.get("BhuCodeDis", "")).strip() or None

            area_sq_m = float(row_utm.get("SHAPE_STAr", row_utm.geometry.area))
            perimeter_m = float(row_utm.get("SHAPE_STLe", row_utm.geometry.length))

            geom_4326 = to_multipolygon(row_4326.geometry)
            centroid_4326 = geom_4326.centroid

            repair = repairs_by_district.get(kgis_code)

            dist_obj = NormalizedDistrict(
                kgis_district_code=kgis_code,
                lgd_district_code=lgd_code,
                district_name=name,
                bhu_code=bhu_code,
                area_sq_m=area_sq_m,
                perimeter_m=perimeter_m,
                geometry=geom_4326,
                centroid=centroid_4326,
                was_repaired=repair is not None,
                repair_record=repair,
            )
            result.append(dist_obj)

        # Deterministic sorting by KGIS district code
        result.sort(key=lambda d: d.kgis_district_code)
        return result

    @staticmethod
    def _build_normalized_taluks(
        taluks_utm: gpd.GeoDataFrame,
        taluks_4326: gpd.GeoDataFrame,
        repairs_by_taluk: dict[str, GeometryRepairRecord],
        kgis_to_lgd_district: dict[str, str],
    ) -> list[NormalizedTaluk]:
        result: list[NormalizedTaluk] = []

        for idx in range(len(taluks_4326)):
            row_utm = taluks_utm.iloc[idx]
            row_4326 = taluks_4326.iloc[idx]

            kgis_code = str(row_4326["KGISTalukC"]).strip().zfill(4)
            lgd_code = str(row_4326["LGD_TalukC"]).strip()
            name = str(row_4326["KGISTalukN"]).strip()
            parent_kgis = str(row_4326["KGISDistri"]).strip().zfill(2)
            parent_lgd = kgis_to_lgd_district.get(parent_kgis, "")

            area_sq_m = float(row_utm.get("SHAPE_STAr", row_utm.geometry.area))
            perimeter_m = float(row_utm.get("SHAPE_STLe", row_utm.geometry.length))

            geom_4326 = to_multipolygon(row_4326.geometry)
            centroid_4326 = geom_4326.centroid

            repair = repairs_by_taluk.get(kgis_code)

            taluk_obj = NormalizedTaluk(
                kgis_taluk_code=kgis_code,
                lgd_taluk_code=lgd_code,
                taluk_name=name,
                parent_kgis_district_code=parent_kgis,
                parent_lgd_district_code=parent_lgd,
                area_sq_m=area_sq_m,
                perimeter_m=perimeter_m,
                geometry=geom_4326,
                centroid=centroid_4326,
                was_repaired=repair is not None,
                repair_record=repair,
            )
            result.append(taluk_obj)

        # Deterministic sorting by KGIS taluk code
        result.sort(key=lambda t: t.kgis_taluk_code)
        return result
