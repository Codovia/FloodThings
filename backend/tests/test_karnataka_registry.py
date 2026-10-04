"""Controlled records only; network blocked and every output disposable."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_karnataka_registry.py"
spec = importlib.util.spec_from_file_location("karnataka_registry", SCRIPT)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def row(name="Test District", code="123", state="29"):
    return {"district_name": name, "lgd_district_code": code, "lgd_state_code": state}


def provisional(name="Test District"):
    return row(name, None, None)


def html(names=("Test District",)):
    links = "".join(f'<div class="search-result-row"><a class="search-title" href="https://test.nic.in">{name}<span></span></a></div>'
                    for name in names)
    return f'<h2>Districts - Karnataka</h2><div>{len(names)} Results</div>{links}'.encode()


def retrieval(body):
    return {"url": registry.NIC_URL, "http_status": 200, "bytes": len(body),
            "sha256": registry.sha256(body), "retrieved_at": "2026-10-04T00:00:00+00:00"}


def candidate(name="Test District", shape_id="source-1", inside=True):
    return {"shapeName": name, "shapeID": shape_id, "centroid_within_state": inside}


def test_duplicate_codes_rejected():
    with pytest.raises(ValueError, match="Duplicate LGD codes"):
        registry.validate_registry([row(), row("Other District")])


def test_duplicate_names_ignore_case_and_whitespace_only():
    with pytest.raises(ValueError, match="Duplicate district names"):
        registry.validate_registry([row(), row("  test   DISTRICT ", "124")])


@pytest.mark.parametrize("field,value", [("lgd_district_code", None), ("lgd_state_code", None),
                                         ("lgd_district_code", "unknown"), ("lgd_state_code", "")])
def test_missing_identifiers_rejected(field, value):
    record = row()
    record[field] = value
    with pytest.raises(ValueError, match="official LGD identifiers"):
        registry.validate_registry([record])


def test_state_mismatch_rejected():
    with pytest.raises(ValueError, match="Mismatched state"):
        registry.validate_registry([row(), row("Other District", "124", "30")])


def test_provisional_allows_null_but_never_assigned_codes():
    registry.validate_registry([provisional()], require_lgd=False)
    with pytest.raises(ValueError, match="must not assign"):
        registry.validate_registry([row()], require_lgd=False)


def test_ambiguous_match_stays_unresolved():
    result = registry.assess_matches([provisional()], [candidate(), candidate(shape_id="source-2")])[0]
    assert result["boundary_match_status"] == "ambiguous"
    assert len(result["boundary_candidates"]) == 2
    assert result["verified_boundary_id"] is None


def test_name_match_and_centroid_containment_are_not_official_reconciliation():
    result = registry.assess_matches([provisional()], [candidate()])[0]
    assert result["boundary_match_status"] == "name_candidate_not_officially_reconciled"
    assert result["verified_boundary_id"] is None
    outside = registry.assess_matches([provisional()], [candidate(inside=False)])[0]
    assert outside["boundary_match_status"] == "unmatched"


def test_renaming_and_corrupt_source_spelling_are_not_silently_substituted():
    result = registry.assess_matches([provisional("Bengaluru South")], [candidate("Ramanagara")])[0]
    assert result["boundary_match_status"] == "unmatched"
    result = registry.assess_matches([provisional("Ballari")], [candidate("Ball?ri")])[0]
    assert result["boundary_match_status"] == "unmatched"


@pytest.mark.parametrize("geometry", [
    {"type": "Polygon", "coordinates": []},
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
    {"type": "Point", "coordinates": [1, 1]},
    {"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]},
])
def test_invalid_geometry_is_rejected_without_repair(geometry):
    original = deepcopy(geometry)
    with pytest.raises(ValueError, match="Invalid"):
        registry.validate_geometry(geometry)
    assert geometry == original


def test_valid_geometry_and_explicit_crs():
    square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    assert registry.validate_geometry(square).area == 1
    with pytest.raises(ValueError, match="EPSG:4326"):
        registry.validate_geometry(square, "EPSG:3857")


def test_mismatched_district_coverage_rejected():
    with pytest.raises(ValueError, match="Mismatched district coverage"):
        registry.validate_coverage(["Test A", "Test B"], ["Test A", "Test C"])
    registry.validate_coverage(["Test A", "Test B"], ["test b", "Test A"])


def test_nic_original_names_and_links_are_retained():
    rows = registry.parse_nic(html(("Test A", "Test B")))
    assert [r["district_name"] for r in rows] == ["Test A", "Test B"]
    assert all(r["lgd_district_code"] is None and r["lgd_state_code"] is None for r in rows)


def test_nic_pagination_and_sidebar_are_scoped():
    body = html().replace(b"1 Results", b"2 Results")
    body += b'<aside><a class="search-title" href="https://unreviewed.example">Sidebar</a></aside>'
    page = b'<div class="search-result-row"><a class="search-title" href="https://other.nic.in">Other District</a></div>'
    meta = retrieval(body)
    meta["pages"] = [{**retrieval(page), "url": registry.NIC_URL.replace(
        "/organizations", "/organizations_more/1/1")}]
    inventory = registry.build_inventory(body, meta, {}, [page])
    assert [r["district_name"] for r in inventory["records"]] == ["Test District", "Other District"]
    with pytest.raises(ValueError, match="pagination response provenance"):
        registry.build_inventory(body, meta, {})
    with pytest.raises(ValueError, match="pagination source/checksum"):
        registry.build_inventory(body, meta, {}, [page + b" "])


@pytest.mark.parametrize("body", [
    html().replace(b"1 Results", b"31 Results"),
    html().replace(b"Districts - Karnataka", b"Districts - Other State"),
    html().replace(b"https://test.nic.in", b"https://unreviewed.example"),
    html(("Test A", "test a")),
])
def test_mismatched_nic_document_rejected(body):
    with pytest.raises(ValueError):
        registry.parse_nic(body)


def test_raw_checksum_mismatch_rejected():
    body = html()
    metadata = retrieval(body)
    metadata["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        registry.build_inventory(body, metadata, {})


def test_live_access_failure_retains_precise_error_without_queries():
    ee = MagicMock()
    ee.Initialize.side_effect = RuntimeError("Access unavailable")
    result = registry.inspect_boundaries(ee)
    assert result["status"] == "unavailable"
    assert result["error"] == {"type": "RuntimeError", "message": "Access unavailable"}
    assert result["query_parameters"]["max_features"] == 80
    assert result["query_parameters"]["wall_seconds"] == 90
    assert result["geometry_validation"] == "not_run_metadata_only"
    ee.FeatureCollection.assert_not_called()


def test_unavailable_boundaries_do_not_publish_partial_candidates():
    body = html()
    inventory = registry.build_inventory(body, retrieval(body), {
        "status": "unavailable", "boundary_candidates": [candidate()]})
    assert inventory["records"][0]["boundary_candidates"] == []
    assert inventory["stage_1_complete"] is False


def test_version_validation_is_read_only_and_recreation_refused():
    body = html()
    metadata = retrieval(body)
    inventory = registry.build_inventory(body, metadata, {"status": "available_metadata_only",
                                                         "boundary_candidates": [candidate()]})
    with TemporaryDirectory() as temp:
        root = Path(temp)
        original = root / "nic-original.html"
        original.write_bytes(body)
        output = root / "provisional_v1"
        registry.write_version(output, inventory, metadata)
        def snapshot():
            return {str(p): (p.read_bytes(), registry.sha256(p.read_bytes()), p.stat().st_mtime_ns)
                    for p in root.rglob("*") if p.is_file()}
        before = snapshot()
        result = registry.validate_version(output)
        assert result == {"status": "valid_provisional_inventory", "name_count": 1,
                          "lgd_codes": 0, "verified_polygons": 0, "stage_1_complete": False}
        assert registry.main(["--validate-only", str(output)]) == 0
        with pytest.raises(FileExistsError):
            registry.write_version(output, inventory, metadata)
        with pytest.raises(ValueError, match="existing manifested dataset"):
            registry.write_version(output / "nested-version", inventory, metadata)
        assert snapshot() == before
        payload = output / "district_names.json"
        payload.write_bytes(payload.read_bytes() + b" ")
        with pytest.raises(ValueError, match="checksum"):
            registry.validate_version(output)
