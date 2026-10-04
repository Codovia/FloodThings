"""Controlled shapefiles only, always in disposable directories; no live services."""
from copy import deepcopy
import importlib.util
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pytest
import shapefile
from pyproj import CRS
from shapely.geometry import Polygon, box

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_soi_karnataka.py"
spec = importlib.util.spec_from_file_location("soi_boundaries", SCRIPT)
soi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soi)


def fixture_source(directory, rows=None, state=False):
    path = Path(directory) / ("state.shp" if state else "source.shp")
    with shapefile.Writer(str(path), shapeType=shapefile.POLYGONZ) as writer:
        if state:
            writer.field("STATE", "C", size=50)
            writer.record("KARNATAKA")
            writer.polyz([[(0, 0, 3), (0, 100, 4), (200, 100, 5), (200, 0, 6), (0, 0, 3)]])
        else:
            for name in ("STATE_UT", "STATE_LGD", "DISTRICT", "DIST_LGD"):
                writer.field(name, "C", size=50)
            writer.field("OBJECTID", "N", size=10)
            rows = rows or [("OUTSIDE", "30", "Other", "900", 1),
                            ("KARNATAKA", "29", "Test A", "100", 2),
                            ("KARNATAKA", "29", "Test B", "101", 3)]
            for i, row in enumerate(rows):
                writer.record(*row)
                x = (i - 1) * 100
                writer.polyz([[(x, 0, 1), (x, 100, 2), (x+100, 100, 3), (x+100, 0, 4), (x, 0, 1)]])
    path.with_suffix(".prj").write_text(CRS.from_user_input(soi.AREA_CRS).to_wkt())
    path.with_suffix(".cpg").write_text("UTF-8")
    return path


def snapshot(directory):
    return {str(p): (p.read_bytes(), soi.digest(p), p.stat().st_mtime_ns)
            for p in Path(directory).rglob("*") if p.is_file()}


def working_fixture(directory):
    root = Path(directory)
    source_dir = root / "inputs"
    source_dir.mkdir()
    district = soi.read_source(fixture_source(source_dir), "STATE_UT", district=True)
    state = soi.read_source(fixture_source(source_dir, state=True), "STATE")
    report = {"stage_1_complete": False, "geometry_validation": soi.source_geometry_report(district, state),
              "district_records": [{"district_name_original": r["attributes"]["DISTRICT"],
                                    "district_lgd_code_as_supplied_by_soi": r["attributes"]["DIST_LGD"]}
                                   for r in district["records"]]}
    return district, state, report


def test_actual_state_field_filter_and_original_source_indices():
    with TemporaryDirectory() as directory:
        source = fixture_source(directory)
        before = snapshot(directory)
        result = soi.read_source(source, "STATE_UT", district=True)
        assert result["national_record_count"] == 3
        assert [r["source_record_index"] for r in result["records"]] == [1, 2]
        assert [r["attributes"]["DIST_LGD"] for r in result["records"]] == ["100", "101"]
        assert snapshot(directory) == before


@pytest.mark.parametrize("suffix", soi.COMPONENTS)
def test_missing_original_component_is_not_substituted(suffix):
    with TemporaryDirectory() as directory:
        path = fixture_source(directory)
        path.with_suffix(suffix).unlink()
        with pytest.raises(ValueError, match="Missing shapefile component"):
            soi.read_source(path, "STATE_UT", district=True)


@pytest.mark.parametrize("row,error", [
    (("KARNATAKA", "30", "Test A", "100", 1), "mismatched source identifiers"),
    (("KARNATAKA", "29", "Test A", "", 1), "Missing or mismatched"),
    (("KARNATAKA", "29", "Test A", "guessed", 1), "Missing or mismatched"),
    (("KARNATAKA", "29", "", "100", 1), "Missing or mismatched"),
])
def test_missing_or_wrong_source_identifiers(row, error):
    with TemporaryDirectory() as directory:
        with pytest.raises(ValueError, match=error):
            soi.read_source(fixture_source(directory, [row]), "STATE_UT", district=True)


@pytest.mark.parametrize("names,codes,error", [
    (["Test A", "Test B"], ["100", "100"], "Duplicate source district codes"),
    (["Test A", "test a"], ["100", "101"], "Duplicate source district names"),
])
def test_duplicate_identifiers_rejected(names, codes, error):
    with TemporaryDirectory() as directory:
        rows = [("KARNATAKA", "29", name, code, i) for i, (name, code) in enumerate(zip(names, codes))]
        with pytest.raises(ValueError, match=error):
            soi.read_source(fixture_source(directory, rows), "STATE_UT", district=True)


def test_prj_is_preserved_and_never_relabelled_to_metadata_epsg():
    with TemporaryDirectory() as directory:
        path = fixture_source(directory)
        result = soi.read_source(path, "STATE_UT", district=True)
        assert result["wkt"] == path.with_suffix(".prj").read_text()
        assert not result["crs"].equals(CRS.from_epsg(7755))
        path.with_suffix(".prj").write_text(CRS.from_epsg(4326).to_wkt())
        with pytest.raises(ValueError, match="projected metre"):
            soi.read_source(path, "STATE_UT", district=True)


def test_names_and_rename_are_not_guessed_current_lgd_identities():
    rows = [{"district_name_original": "Vijayanagara", "district_lgd_code_as_supplied_by_soi": "761"},
            {"district_name_original": "R<managara", "district_lgd_code_as_supplied_by_soi": "584"}]
    original = deepcopy(rows)
    result = soi.reconcile(rows, ["Vijayanagara", "Bengaluru South"])
    assert result[0]["nic_exact_name"] == "Vijayanagara"
    assert result[1]["nic_exact_name"] is None
    assert all(not r["current_lgd_export_verified"] for r in result)
    assert rows == original
    with pytest.raises(ValueError, match="ambiguous inventory"):
        soi.reconcile(rows, ["Vijayanagara", "vijayanagara"])


@pytest.mark.parametrize("geometry", [Polygon(), Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])])
def test_empty_or_invalid_geometry_is_rejected_without_repair(geometry):
    original = geometry.wkb
    with pytest.raises(ValueError, match="Invalid or empty polygon"):
        soi.geometry_checks([geometry], box(0, 0, 100, 100), soi.AREA_CRS)
    assert geometry.wkb == original


def test_overlap_gap_and_outside_state_are_measured_in_metres():
    checks = soi.geometry_checks([box(0, 0, 10, 10), box(5, 0, 15, 10)], box(0, 0, 12, 20), soi.AREA_CRS)
    assert checks["positive_area_overlaps"][0]["area_m2"] == 50
    assert checks["state_not_covered_m2"] == 120
    assert checks["districts_outside_state_m2"] == 30
    assert checks["union_area_km2"] == 150 / 1e6


def test_duplicate_geometry_and_state_count_are_rejected():
    with pytest.raises(ValueError, match="Duplicate district geometries"):
        soi.geometry_checks([box(0, 0, 1, 1)] * 2, box(0, 0, 1, 1), soi.AREA_CRS)
    with TemporaryDirectory() as directory:
        district, state, _ = working_fixture(directory)
        state["records"] *= 2
        with pytest.raises(ValueError, match="State count"):
            soi.source_geometry_report(district, state)


def test_local_subset_preserves_xyz_attributes_original_bytes_and_completed_version():
    with TemporaryDirectory() as directory:
        district, state, report = working_fixture(directory)
        sources_before = snapshot(Path(directory) / "inputs")
        output = Path(directory) / "working"
        soi.write_version(output, district, state, report)
        assert snapshot(Path(directory) / "inputs") == sources_before
        saved = soi.read_source(output / "districts.shp", "STATE_UT", district=True)
        assert saved["records"][0]["shape"].z == district["records"][0]["shape"].z
        before = snapshot(directory)
        assert soi.validate_version(output)["valid_polygons"] == 2
        assert snapshot(directory) == before
        with pytest.raises(FileExistsError, match="no overwrite"):
            soi.write_version(output, district, state, report)
        assert snapshot(directory) == before


def test_hash_mismatch_rejected_read_only():
    with TemporaryDirectory() as directory:
        district, state, report = working_fixture(directory)
        output = Path(directory) / "working"
        soi.write_version(output, district, state, report)
        with (output / "districts.dbf").open("ab") as stream:
            stream.write(b"corruption")
        before = snapshot(directory)
        with pytest.raises(ValueError, match="checksum mismatch"):
            soi.validate_version(output)
        assert snapshot(directory) == before


def test_identity_manifest_corruption_rejected():
    with TemporaryDirectory() as directory:
        district, state, report = working_fixture(directory)
        output = Path(directory) / "working"
        soi.write_version(output, district, state, report)
        path = output / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["district_records"][0]["district_lgd_code_as_supplied_by_soi"] = "999"
        path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="identities mismatch"):
            soi.validate_version(output)


def test_metadata_original_bytes_and_archive_dates_not_reference_dates():
    with TemporaryDirectory() as directory:
        inner = BytesIO()
        with ZipFile(inner, "w") as workbook:
            workbook.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="B31" t="inlineStr"><is><t>2025</t></is></c></row></sheetData></worksheet>')
        path = Path(directory) / "metadata.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("DISTRICT BOUNDARY.xlsx", inner.getvalue())
        before = snapshot(directory)
        result = soi.metadata_cells(path, "DISTRICT BOUNDARY.xlsx")
        assert result["cells"]["B31"] == "2025"
        assert result["sha256"] == __import__("hashlib").sha256(inner.getvalue()).hexdigest()
        assert "zip_entry_modification_time_not_reference_date" in result
        assert snapshot(directory) == before


def test_cli_refuses_existing_metadata_before_reading_or_writing(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        existing = root / "manifest.json"
        existing.write_text("completed version\n")
        argv = ["verify_soi_karnataka.py"]
        for option in ("district", "state", "metadata-zip", "archive", "nic-inventory"):
            argv.extend([f"--{option}", str(root / "unavailable")])
        argv.extend(["--working-output", str(root / "new-working"), "--metadata-output", str(existing)])
        monkeypatch.setattr("sys.argv", argv)
        before = snapshot(directory)
        with pytest.raises(FileExistsError, match="no overwrite"):
            soi.main()
        assert snapshot(directory) == before
        assert not (root / "new-working").exists()
