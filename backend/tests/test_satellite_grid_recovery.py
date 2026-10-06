"""Offline projection/planner fixtures; no source data or persistent output writes."""
from copy import deepcopy
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

spec = importlib.util.spec_from_file_location("satellite_grid_recovery", Path(__file__).resolve().parents[2] / "scripts/recover_karnataka_satellite.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


def projection(crs="EPSG:32643", transform=None, scale=250):
    return {"projection": {"crs": crs, "transform": transform or [250, 0, 0, 0, -250, 0]}, "nominal_scale_m": scale}


def source():
    native = projection("EPSG:4326", [0.002, 0, 70, 0, -0.002, 30])
    return {"flooded_at_scale_250": deepcopy(native), "analysis": projection(),
            "bands": {b: deepcopy(native) for b in s.BANDS}}


def grid():
    return s.analysis_grid(source())


def bounds(width=400, height=400):
    return [[0, 0], [width * 250, 0], [width * 250, height * 250], [0, height * 250]]


def statistics(positive=2, valid=100):
    return {"region_pixels": 100, "valid_pixels": valid, "qualifying_pixels": positive,
            "mapped_water_pixels": positive, "permanent_water_pixels": 0,
            "clear_views_sum": valid * 2, "clear_perc_sum": valid * 70, "clear_perc_count": valid,
            "duration_sum": positive * 3, "duration_count": positive}


def test_live_projection_fields_are_parsed_without_catalogue_resolution_assumptions():
    value = projection("EPSG:4326", [0.002, 0, 70, 0, -0.002, 30])
    assert s.parse_projection(value) == {"crs": "EPSG:4326", "transform": value["projection"]["transform"], "nominal_scale_m": 250}
    value["nominal_scale_m"] = 30
    assert s.parse_projection(value)["nominal_scale_m"] == 30  # Metadata is preserved; never guessed from prose.


@pytest.mark.parametrize("bad", [projection(scale=0), projection(scale=float('nan')),
    projection(transform=[0, 0, 0, 0, 0, 0]), projection(transform=[1, 0, 0])])
def test_invalid_projection_metadata_rejected(bad):
    with pytest.raises(ValueError): s.parse_projection(bad)


def test_analysis_grid_uses_source_scale_and_preserves_udupi_origin():
    value = source(); before = deepcopy(value); actual = s.analysis_grid(value)
    assert actual["crs"] == "EPSG:32643" and actual["transform"] == [250, 0, 0, 0, -250, 0]
    assert actual["source_flooded_at_scale_250"]["crs"] == "EPSG:4326"
    assert actual["nominal_scale_m"] == 250 and value == before
    value["analysis"]["projection"]["transform"][2] = 125
    with pytest.raises(ValueError, match="compatibility"): s.analysis_grid(value)


def test_mixed_band_projection_is_explicit_and_not_silently_overwritten():
    value = source(); value["bands"]["jrc_perm_water"] = projection("EPSG:3857", [30, 0, 0, 0, -30, 0], 30)
    result = s.analysis_grid(value)
    assert result["mixed_source_projections"]
    assert result["source_band_projections"]["jrc_perm_water"]["nominal_scale_m"] == 30
    assert "nearest" in result["alignment"] and "no bilinear" in result["alignment"]


def test_band_pixel_budget_quantitatively_explains_old_planner_failure():
    plan = s.planner(bounds(), grid())
    assert plan["band_count"] == 10 and plan["chunk_cells"] == 84
    assert plan["maximum_expected_partition_cells"] == 7056
    assert plan["maximum_safe_workload"] == 88200 < 90000 < 300000
    assert 300 * 300 * 10 == 900000  # Old 90k spatial-cell target omitted ten bands.
    assert abs(561368 / 10 - 56140) < 4  # Server estimate versus centre-owned cell count, not flood evidence.


def test_band_count_affects_partition_planning():
    one = s.planner(bounds(), grid(), band_count=1)
    ten = s.planner(bounds(), grid(), band_count=10)
    assert one["chunk_cells"] > ten["chunk_cells"]
    assert ten["partition_count"] > one["partition_count"]
    assert all(p["safe_workload_bound"] <= 90000 for p in one["partitions"] + ten["partitions"])


def test_half_open_partitions_cover_bbox_once_and_conserve_area():
    from shapely.geometry import box
    from shapely.ops import unary_union
    from itertools import combinations
    plan = s.planner(bounds(180, 180), grid()); polygons = []
    for p in plan["partitions"]:
        x0, x1, y0, y1 = p["window"]; polygons.append(box(x0, y0, x1, y1))
    assert sum(p.area for p in polygons) == 180 * 180
    assert unary_union(polygons).area == 180 * 180
    assert all(a.intersection(b).area == 0 for a, b in combinations(polygons, 2))
    for col, row in [(0, -180), (83, -97), (84, -96), (179, -1)]:
        assert sum(s.legacy.owns(p["window"], col, row) for p in plan["partitions"]) == 1


@pytest.mark.parametrize("change", ["workload", "count", "ceiling", "margin"])
def test_preflight_rejects_unsafe_or_inconsistent_estimates(change):
    plan = s.planner(bounds(20, 20), grid())
    if change == "workload": plan["partitions"][0]["safe_workload_bound"] = 300001
    if change == "count": plan["partitions"][0]["spatial_cell_bound"] += 1
    if change == "ceiling": plan["maxPixels"] = 600000
    if change == "margin": plan["safety_factor"] = 1
    with pytest.raises(ValueError): s.guard(plan)


def test_geometry_preflight_checks_actual_clipped_parts_gaps_and_overlaps():
    plan = s.planner(bounds(10, 10), grid())
    plan.update(region={"area_km2": 6.25}, geometry_check={"partitions": [
        {"index": 0, "area_m2": 6250000, "outside_area_m2": 0}],
        "gap_area_m2": 0, "excess_area_m2": 0, "touching_pair_overlaps": []})
    s.check_geometry(plan)
    for key in ["gap_area_m2", "excess_area_m2"]:
        changed = deepcopy(plan); changed["geometry_check"][key] = 2
        with pytest.raises(ValueError, match="overlap/gap"): s.check_geometry(changed)
    changed = deepcopy(plan); changed["geometry_check"]["touching_pair_overlaps"] = [{"area_m2": 2}]
    with pytest.raises(ValueError): s.check_geometry(changed)
    changed = deepcopy(plan); changed["geometry_check"]["partitions"][0]["area_m2"] = 6000000
    with pytest.raises(ValueError, match="conservation"): s.check_geometry(changed)


def test_explicit_reducer_grid_and_fixed_parameters():
    params = s.reducer_parameters(grid())
    assert params == {"crs": "EPSG:32643", "crsTransform": [250, 0, 0, 0, -250, 0],
                      "maxPixels": 300000, "bestEffort": False, "tileScale": 2}
    assert "scale" not in params  # Mutually exclusive with explicit affine; affine is 250 m.


def test_all_flags_quality_bands_and_first_constant_are_explicitly_aligned():
    ee, image, projection_value = MagicMock(), MagicMock(), object()
    s.evidence_image(ee, image, projection_value)
    assert [c.args[0] for c in image.mock_calls if c[0] == "select"] == s.BANDS
    calls = [c for c in image.mock_calls if c[0].endswith("reproject")]
    assert len(calls) >= 5 and all(c.kwargs["crs"] is projection_value for c in calls)
    assert not any("resample" in c[0] for c in image.mock_calls)
    assert any(c[0].endswith("reproject") for c in ee.mock_calls)


def test_actual_load_guard_does_not_accept_projection_or_count_discrepancy():
    plan = {"spatial_cell_bound": 100, "band_pixel_bound": 1000}
    s.validate_part({"statistics": statistics()}, plan)
    value = statistics(); value["region_pixels"] = 101
    with pytest.raises(ValueError, match="preflight"): s.validate_part({"statistics": value}, plan)
    value = statistics(); value["qualifying_pixels"] = 101
    with pytest.raises(ValueError): s.validate_part({"statistics": value}, plan)


def test_incomplete_is_distinct_from_observation_quality_and_positive():
    assert s.outcome([], 2)["statistics"] is None
    assert s.outcome([], 2)["evidence_status"] == "incomplete_computation"
    partial = s.outcome([{"statistics": statistics()}], 2)
    assert partial["statistics"]["qualifying_pixels"] == 2 and partial["evidence_status"] == "incomplete_computation"
    assert partial["counts_are_lower_bounds"]
    assert s.outcome([{"statistics": statistics()}], 1)["evidence_status"] == "satellite_positive"
    assert s.outcome([{"statistics": statistics(0, 0)}], 1)["evidence_status"] == "insufficient_observation"
    assert s.outcome([{"statistics": statistics(0, 100)}], 1)["evidence_status"] == "observed_no_qualifying_floodwater"


def test_readonly_nearest_alignment_reproduces_udupi_fixture_counts_and_mtimes():
    import numpy as np
    import rasterio
    from affine import Affine
    from pyproj import Transformer
    from shapely.geometry import Polygon, mapping
    with TemporaryDirectory() as temporary:
        root = Path(temporary); transform = Transformer.from_crs(s.legacy.CRS, "EPSG:4326", always_xy=True)
        ring = [transform.transform(x, y) for x, y in [(475000, 1500000), (484000, 1500000), (484000, 1499750), (475000, 1499750)]]
        s.legacy.write_new(root / "udupi_boundary.geojson", {"geometry": mapping(Polygon(ring))})
        events, files = [], {}
        for eid, count in [(2728, 33), (3551, 23)]:
            path = root / f"fixture_{eid}.tif"; values = np.full((3, 1, 36), -9999, dtype="float32")
            values[0, 0, :count] = 1; values[1, 0, :count] = 0; values[2, 0, :count] = 2
            with rasterio.open(path, "w", driver="GTiff", height=1, width=36, count=3, dtype="float32", crs=s.legacy.CRS,
                               transform=Affine(250, 0, 475000, 0, -250, 1500000)) as handle: handle.write(values)
            events.append({"event_id": eid, "raster_file": path.name}); files[path.name] = s.legacy.fingerprint(path)
        s.legacy.write_new(root / "manifest.json", {"events": events, "files": files})
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
        result = s.udupi_gate(root, grid())
        assert result["qualified_pixels"] == {"2728": 33, "3551": 23} and result["files_modified"] == 0
        assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
        changed = grid(); changed["transform"][2] = 125
        with pytest.raises(ValueError, match="origin"): s.udupi_gate(root, changed)


def test_deterministic_manifest_and_failed_versions_are_not_overwritten():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "manifest.json"; value = {"grid": grid(), "plan": s.planner(bounds(10, 10), grid())}
        s.legacy.write_new(path, value)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        assert s.legacy.packed(json.loads(path.read_text())) == before[0]
        with pytest.raises(ValueError, match="completed"): s.legacy.write_new(path, value)
        assert before == (path.read_bytes(), path.stat().st_mtime_ns)


def test_suspend_aware_total_budget_stops_without_accepting_late_result_or_retry(monkeypatch):
    clock = [0.0]; calls = []
    monkeypatch.setattr(s, "elapsed_clock", lambda: clock[0])
    monkeypatch.setitem(sys.modules, "ee", MagicMock())
    with TemporaryDirectory() as temporary:
        session = s.BoundedEE(Path(temporary), 60, 900)
        def late():
            calls.append(1); clock[0] += 1404
            return {"fixture_only": True}
        with pytest.raises(Exception, match="1 attempt.*non_retryable_error"):
            session.request(late, "fixture_suspend")
        assert len(calls) == 1
        error = json.loads((Path(temporary) / "provider_errors.jsonl").read_text())
        assert "Total recovery deadline" in error["message"]


def test_request_deadline_rejects_late_results_with_bounded_retry_count(monkeypatch):
    clock = [0.0]; calls = []
    monkeypatch.setattr(s, "elapsed_clock", lambda: clock[0])
    monkeypatch.setattr(s.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setitem(sys.modules, "ee", MagicMock())
    with TemporaryDirectory() as temporary:
        session = s.BoundedEE(Path(temporary), 60, 900)
        def late():
            calls.append(1); clock[0] += 61
            return {"fixture_only": True}
        with pytest.raises(Exception, match="3 attempt"):
            session.request(late, "fixture_late")
        assert len(calls) == 3
