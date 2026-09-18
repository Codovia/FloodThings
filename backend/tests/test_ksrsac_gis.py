"""
Unit and integration tests for KSR-SAC administrative GIS normalization.

Verifies:
1. Source CRS validation (EPSG:32643 required).
2. Required-column validation.
3. Feature counts (31 districts, 240 taluks).
4. Unique KGIS and LGD identifiers.
5. Invalid geometry detection and deterministic make_valid() repair.
6. Zero invalid geometries after normalization.
7. EPSG:4326 output with strictly MultiPolygon geometries.
8. Parent district resolution and representative-point spatial containment.
9. No substantive overlaps under documented relative tolerance (1e-10).
10. Vijayanagara 6-taluk condition.
11. Preservation of source identifiers and attributes.
12. Raw source files remain untouched (SHA-256 checksum verification).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from app.gis.ksrsac import (
    DEFAULT_RELATIVE_OVERLAP_TOLERANCE,
    EXPECTED_DISTRICT_COUNT,
    EXPECTED_TALUK_COUNT,
    EXPECTED_VIJAYANAGARA_TALUK_COUNT,
    REQUIRED_DISTRICT_COLUMNS,
    REQUIRED_TALUK_COLUMNS,
    VIJAYANAGARA_KGIS_CODE,
    VIJAYANAGARA_LGD_CODE,
    KsrsacAdminNormalizer,
    KsrsacCrsError,
    KsrsacFileNotFoundError,
    KsrsacSchemaError,
    KsrsacTopologyError,
    KsrsacValidationError,
    to_multipolygon,
)


def _compute_dir_checksums(directory: Path) -> dict[str, str]:
    """Compute SHA-256 checksums for all files in a directory."""
    checksums: dict[str, str] = {}
    for p in sorted(directory.glob("*")):
        if p.is_file():
            checksums[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return checksums


class TestKsrsacAdminNormalization:
    """Test suite for KSR-SAC administrative boundaries normalization."""

    @pytest.fixture(scope="class")
    def normalized_result(self):
        """Run normalization once for the test class."""
        normalizer = KsrsacAdminNormalizer()
        return normalizer.normalize()

    def test_feature_counts(self, normalized_result):
        """Verify exactly 31 districts and 240 taluks are loaded."""
        assert normalized_result.district_count == EXPECTED_DISTRICT_COUNT
        assert normalized_result.taluk_count == EXPECTED_TALUK_COUNT

    def test_unique_identifiers(self, normalized_result):
        """Verify unique KGIS and LGD codes for all districts and taluks."""
        kgis_districts = [d.kgis_district_code for d in normalized_result.districts]
        lgd_districts = [d.lgd_district_code for d in normalized_result.districts]
        assert len(set(kgis_districts)) == EXPECTED_DISTRICT_COUNT
        assert len(set(lgd_districts)) == EXPECTED_DISTRICT_COUNT

        kgis_taluks = [t.kgis_taluk_code for t in normalized_result.taluks]
        lgd_taluks = [t.lgd_taluk_code for t in normalized_result.taluks]
        assert len(set(kgis_taluks)) == EXPECTED_TALUK_COUNT
        assert len(set(lgd_taluks)) == EXPECTED_TALUK_COUNT

    def test_known_identifier_preservation(self, normalized_result):
        """Verify canonical district identifiers are accurately mapped."""
        # Belagavi: KGIS 01, LGD 527
        belagavi = normalized_result.get_district_by_kgis("01")
        assert belagavi is not None
        assert belagavi.district_name == "Belagavi"
        assert belagavi.lgd_district_code == "527"

        # Bagalkote: KGIS 02, LGD 524
        bagalkote = normalized_result.get_district_by_kgis("02")
        assert bagalkote is not None
        assert bagalkote.district_name == "Bagalkote"
        assert bagalkote.lgd_district_code == "524"

        # Vijayanagara: KGIS 31, source LGD_Distri is 738
        vijayanagara = normalized_result.get_district_by_kgis("31")
        assert vijayanagara is not None
        assert vijayanagara.district_name == "Vijayanagara"
        assert vijayanagara.lgd_district_code == VIJAYANAGARA_LGD_CODE

    def test_geometry_repairs_detected_and_deterministic(self, normalized_result):
        """Verify exactly the 3 known invalid taluk geometries are repaired."""
        assert normalized_result.repair_count == 3

        repaired_kgis = {r.kgis_code for r in normalized_result.repairs}
        expected_repaired_kgis = {"1506", "1701", "1504"}
        assert repaired_kgis == expected_repaired_kgis

        repaired_names = {r.name for r in normalized_result.repairs}
        expected_repaired_names = {"Shivamogga", "Sringeri", "Hosanagar"}
        assert repaired_names == expected_repaired_names

        for r in normalized_result.repairs:
            assert r.feature_type == "taluk"
            assert r.repair_operation == "shapely.make_valid"
            assert r.valid_before is False
            assert r.valid_after is True
            # Area difference is floating-point noise (< 1e-12 relative difference)
            assert r.relative_area_diff < 1e-12

    def test_zero_invalid_geometries_after_normalization(self, normalized_result):
        """Verify all 31 districts and 240 taluks have strictly valid geometries."""
        for d in normalized_result.districts:
            assert d.geometry.is_valid, f"District {d.district_name} geometry is invalid"
            assert not d.geometry.is_empty, f"District {d.district_name} geometry is empty"

        for t in normalized_result.taluks:
            assert t.geometry.is_valid, f"Taluk {t.taluk_name} geometry is invalid"
            assert not t.geometry.is_empty, f"Taluk {t.taluk_name} geometry is empty"

    def test_epsg_4326_output_specifications(self, normalized_result):
        """Verify geometries are transformed to EPSG:4326 within Karnataka bounds."""
        assert normalized_result.target_crs == "EPSG:4326"

        for d in normalized_result.districts:
            assert isinstance(d.geometry, MultiPolygon)
            assert isinstance(d.centroid, Point)
            assert d.wkt.startswith("SRID=4326;MULTIPOLYGON")
            assert d.centroid_wkt.startswith("SRID=4326;POINT")
            # Karnataka bounds: 11.5°N - 18.5°N, 74.0°E - 78.6°E
            assert 74.0 <= d.centroid.x <= 78.6
            assert 11.5 <= d.centroid.y <= 18.5

        for t in normalized_result.taluks:
            assert isinstance(t.geometry, MultiPolygon)
            assert isinstance(t.centroid, Point)
            assert t.wkt.startswith("SRID=4326;MULTIPOLYGON")
            assert t.centroid_wkt.startswith("SRID=4326;POINT")
            assert 74.0 <= t.centroid.x <= 78.6
            assert 11.5 <= t.centroid.y <= 18.5

    def test_parent_district_resolution_and_containment(self, normalized_result):
        """Verify every taluk resolves its parent district and is topologically inside it."""
        districts_by_kgis = {d.kgis_district_code: d for d in normalized_result.districts}

        for t in normalized_result.taluks:
            assert t.parent_kgis_district_code in districts_by_kgis
            parent = districts_by_kgis[t.parent_kgis_district_code]
            assert t.parent_lgd_district_code == parent.lgd_district_code

            # Spatial intersection in EPSG:4326
            assert t.geometry.intersects(parent.geometry), (
                f"Taluk {t.taluk_name} does not intersect parent district {parent.district_name}"
            )

            # Representative point within parent district
            rep_pt = t.geometry.representative_point()
            assert rep_pt.within(parent.geometry), (
                f"Taluk {t.taluk_name} representative point not inside parent district {parent.district_name}"
            )

    def test_vijayanagara_condition(self, normalized_result):
        """Verify Vijayanagara (KGIS 31, LGD 738) has exactly 6 taluks."""
        vij_taluks = normalized_result.get_taluks_for_district(VIJAYANAGARA_KGIS_CODE)
        assert len(vij_taluks) == EXPECTED_VIJAYANAGARA_TALUK_COUNT

        vij_names = {t.taluk_name for t in vij_taluks}
        expected_names = {
            "Hadagali",
            "Hagaribommanahalli",
            "Harapanahalli",
            "Hosapete",
            "Kotturu",
            "Kudligi",
        }
        assert vij_names == expected_names

        vij_district = normalized_result.get_district_by_kgis(VIJAYANAGARA_KGIS_CODE)
        assert vij_district is not None
        assert vij_district.lgd_district_code == VIJAYANAGARA_LGD_CODE

    def test_no_substantive_overlaps(self, normalized_result):
        """Verify no substantive overlaps exceed the relative tolerance (1e-10)."""
        tol = normalized_result.relative_overlap_tolerance
        assert tol == DEFAULT_RELATIVE_OVERLAP_TOLERANCE

        # Check district pairs in EPSG:4326
        for i in range(len(normalized_result.districts)):
            a = normalized_result.districts[i].geometry
            a_area = a.area
            for j in range(i + 1, len(normalized_result.districts)):
                b = normalized_result.districts[j].geometry
                b_area = b.area
                inter_area = a.intersection(b).area
                ratio = inter_area / min(a_area, b_area) if min(a_area, b_area) > 0 else 0.0
                assert ratio <= tol, (
                    f"Substantive overlap between districts "
                    f"{normalized_result.districts[i].district_name} and "
                    f"{normalized_result.districts[j].district_name}: ratio={ratio:.2e}"
                )

    def test_deterministic_reproducibility(self):
        """Verify multiple normalization executions produce identical output."""
        normalizer1 = KsrsacAdminNormalizer()
        normalizer2 = KsrsacAdminNormalizer()

        res1 = normalizer1.normalize()
        res2 = normalizer2.normalize()

        assert res1.district_count == res2.district_count
        assert res1.taluk_count == res2.taluk_count
        assert res1.repair_count == res2.repair_count

        for d1, d2 in zip(res1.districts, res2.districts):
            assert d1.kgis_district_code == d2.kgis_district_code
            assert d1.lgd_district_code == d2.lgd_district_code
            assert d1.district_name == d2.district_name
            assert d1.area_sq_m == d2.area_sq_m
            assert d1.geometry.equals(d2.geometry)

        for t1, t2 in zip(res1.taluks, res2.taluks):
            assert t1.kgis_taluk_code == t2.kgis_taluk_code
            assert t1.lgd_taluk_code == t2.lgd_taluk_code
            assert t1.taluk_name == t2.taluk_name
            assert t1.geometry.equals(t2.geometry)

    def test_raw_source_files_unmodified(self):
        """Verify that reading and normalizing raw KSR-SAC data leaves raw files untouched."""
        normalizer = KsrsacAdminNormalizer()
        source_dir = normalizer.district_path.parent

        before_checksums = _compute_dir_checksums(source_dir)
        normalizer.normalize()
        after_checksums = _compute_dir_checksums(source_dir)

        assert before_checksums == after_checksums, "Raw KSR-SAC source files were modified!"


class TestKsrsacValidationErrors:
    """Test suite for error conditions and input validation."""

    def test_missing_file_raises_error(self, tmp_path):
        """Missing shapefile raises KsrsacFileNotFoundError."""
        normalizer = KsrsacAdminNormalizer(
            district_path=tmp_path / "NonexistentDistrict.shp",
            taluk_path=tmp_path / "NonexistentTaluk.shp",
        )
        with pytest.raises(KsrsacFileNotFoundError):
            normalizer.normalize()

    def test_crs_validation_failure(self):
        """Invalid CRS raises KsrsacCrsError."""
        p = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf_invalid_crs = gpd.GeoDataFrame({"geometry": [p]}, crs="EPSG:4326")
        with pytest.raises(KsrsacCrsError, match="expected EPSG:32643"):
            KsrsacAdminNormalizer._validate_crs(gdf_invalid_crs, "test.shp")

    def test_missing_columns_raises_schema_error(self):
        """Missing required columns raises KsrsacSchemaError."""
        p = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf_missing_col = gpd.GeoDataFrame({"KGISDistri": ["01"], "geometry": [p]}, crs="EPSG:32643")
        with pytest.raises(KsrsacSchemaError, match="missing required attribute columns"):
            KsrsacAdminNormalizer._validate_columns(gdf_missing_col, REQUIRED_DISTRICT_COLUMNS, "District.shp")

    def test_to_multipolygon_helper(self):
        """Polygon converts to MultiPolygon, MultiPolygon is preserved."""
        p = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        mp = MultiPolygon([p])

        converted = to_multipolygon(p)
        assert isinstance(converted, MultiPolygon)
        assert len(converted.geoms) == 1

        preserved = to_multipolygon(mp)
        assert preserved is mp

        with pytest.raises(KsrsacValidationError, match="Cannot coerce geometry"):
            to_multipolygon(Point(0, 0))
