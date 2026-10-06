"""Controlled fixtures only; source archives, EE and completed datasets stay untouched."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock
import sys

import pytest

spec = importlib.util.spec_from_file_location("satellite_verification", Path(__file__).resolve().parents[2] / "scripts/verify_karnataka_satellite.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def row(a="2007-08-01", b="2007-08-03", identifier="fixture-only"):
    return {"project_event_id": identifier, "ifi_source_event_id": identifier, "source_start_date": "original start",
            "source_end_date": "original end", "parsed_start_date": a, "parsed_end_date_inclusive": b,
            "source_districts": "Fixture Region", "source_state": "Karnataka"}


def image(a="2007-08-01", b="2007-08-03", identifier=99901):
    stamp = lambda value: int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {"id": identifier, "system:index": f"DFO_{identifier}_From_{a.replace('-', '')}_to_{b.replace('-', '')}",
            "system:time_start": stamp(a), "system:time_end": stamp(b), "cc": "IND", "dfo_country": "India"}


def inventory(images=None):
    images = [image()] if images is None else images
    return {"source": s.SOURCE, "window": s.WINDOW, "limit": 128, "response": {"count": len(images), "images": images}}


def boundaries():
    return {"source": s.BOUNDARY, "window": s.WINDOW, "limit": 80, "response": {"count": 1, "features": [
        {"shapeName": "Fixture Region", "shapeID": "fixture-shape", "shapeGroup": "IND", "shapeType": "ADM2"}]}}


def statistics(positive=2, valid=100):
    return {"region_pixels": 100, "valid_pixels": valid, "qualifying_pixels": positive,
            "mapped_water_pixels": positive + 4, "permanent_water_pixels": 4,
            "clear_views_sum": valid * 3, "clear_perc_sum": valid * 70, "clear_perc_count": valid,
            "duration_sum": positive * 2, "duration_count": positive}


@pytest.mark.parametrize("a,b,expected", [("1999-01-01", "1999-01-04", "outside_gfd_coverage"),
    ("2000-02-16", "2000-02-17", "within_gfd_coverage"), ("2018-12-10", "2018-12-11", "within_gfd_coverage"),
    ("2018-12-11", "2018-12-12", "outside_gfd_coverage"), (None, None, "undated"),
    ("2018-12-06", "2018-06-14", "invalid_reversed")])
def test_coverage_preserves_original_windows(a, b, expected):
    value = row(a, b); before = deepcopy(value)
    assert s.window_status(value) == expected and value == before
    result = s.candidates([value], inventory())[0]
    assert result["ifi_original_start"] == "original start" and not result["satellite_confirmation"]


def test_inclusive_overlap_and_reversed_rejection():
    assert s.overlap("2007-08-01", "2007-08-03", "2007-08-03", "2007-08-05") == {
        "days": 1, "ifi_fraction": 1 / 3, "jaccard": 1 / 5}
    assert s.overlap("2007-08-01", "2007-08-03", "2007-08-04", "2007-08-05")["days"] == 0
    with pytest.raises(ValueError, match="Reversed"):
        s.overlap("2007-08-03", "2007-08-01", "2007-08-03", "2007-08-05")


def test_temporal_candidates_and_ambiguity_do_not_confirm_ifi():
    result = s.candidates([row()], inventory([image(), image(identifier=99902)]))
    assert len(result) == 2 and all(r["candidate_status"] == "ambiguous" for r in result)
    assert all(r["satellite_confirmation"] is False and r["association_status"] == "provisional_temporal_only" for r in result)
    assert all("evidence_status" not in r and "flood" not in r for r in result)


def test_no_candidate_is_not_a_negative_and_foreign_metadata_is_not_india():
    im = image(); im["cc"] = "CHN"
    result = s.candidates([row()], inventory([im]))[0]
    assert result["candidate_status"] == "no_candidate" and result["gfd_id"] is None
    assert not result["satellite_confirmation"]


def test_deterministic_selection_never_uses_outcomes_or_reference_events():
    rows = [row(f"{2001+i}-08-01", f"{2001+i}-08-03", str(i)) for i in range(5)]
    images = [image(r["parsed_start_date"], r["parsed_end_date_inclusive"], 99901 + i) for i, r in enumerate(rows)]
    original = deepcopy(rows); table = s.candidates(rows, inventory(images)); selected = s.select_batch(table, boundaries())
    assert len(selected) == 5 and selected == s.select_batch(list(reversed(table)), boundaries())
    assert rows == original and all(r["gfd_id"] not in {2728, 3551} for r in selected)
    reference = s.candidates([row()], inventory([image(identifier=2728), image(identifier=3551)]))
    assert s.select_batch(reference, boundaries()) == []
    with pytest.raises(ValueError, match="ten"):
        s.select_batch(table, boundaries(), 11)


def test_unknown_or_duplicate_public_names_are_not_guessed():
    table = s.candidates([row()], inventory()); meta = boundaries()
    meta["response"]["features"].append(deepcopy(meta["response"]["features"][0])); meta["response"]["count"] = 2
    assert s.select_batch(table, meta) == []
    table[0]["ifi_district_tokens_original"] = "Fixture Region typo"
    assert s.select_batch(table, boundaries()) == []


@pytest.mark.parametrize("change", ["duplicate", "timestamp", "truncated", "wrong_source"])
def test_metadata_identity_and_bounded_inventory(change):
    meta = inventory()
    if change == "duplicate": meta["response"]["images"] *= 2; meta["response"]["count"] = 2
    if change == "timestamp": meta["response"]["images"][0]["system:time_end"] += 86400000
    if change == "truncated": meta["response"]["count"] = 129
    if change == "wrong_source": meta["source"] = "unverified"
    with pytest.raises(ValueError): s.metadata_events(meta)


def test_partitions_cover_every_grid_cell_once_including_seams():
    windows = s.partition_windows([[0, 1000], [1000, 1000], [1000, 0], [0, 0]], chunk=2)
    assert len(windows) == 4
    for col in range(4):
        for row_index in range(-4, 0):
            assert sum(s.owns(w, col, row_index) for w in windows) == 1
    assert all((w[1] - w[0]) * (w[3] - w[2]) <= 90000 for w in windows)
    assert sum(s.owns(w, 4, -1) for w in windows) == 0
    assert sum(s.owns(w, 0, 0) for w in windows) == 0


@pytest.mark.parametrize("bounds", [[], [[0, 0]] * 4, [[float('nan'), 0]] * 4,
    [[0, 0], [500000, 0], [500000, 500000], [0, 500000]]])
def test_invalid_or_oversized_region_stops_without_coarsening(bounds):
    with pytest.raises(ValueError): s.partition_windows(bounds)


@pytest.mark.parametrize("flooded,permanent,clear,masks,expected", [
    (1, 0, 2, [True] * 3, True), (1, 1, 2, [True] * 3, False), (0, 0, 2, [True] * 3, False),
    (1, 0, 0, [True] * 3, False), (1, 0, None, [True] * 3, False),
    (1, 0, float('nan'), [True] * 3, False), (1, 0, 2, [True, False, True], False)])
def test_permanent_water_and_invalid_observation_exclusion(flooded, permanent, clear, masks, expected):
    assert s.qualifies(flooded, permanent, clear, masks) is expected


@pytest.mark.parametrize("positive,valid,status", [(2, 100, "satellite_positive"),
    (0, 100, "observed_no_qualifying_floodwater"), (0, 0, "insufficient_observation"),
    (0, 94, "insufficient_observation")])
def test_observation_gate_and_evidence_vocabulary(positive, valid, status):
    result = s.finding([{"statistics": statistics(positive, valid)}], 1)
    assert result["evidence_status"] == status and result["evidence_status"] in s.EVIDENCE
    assert "flood" not in result and result["computation_complete"]
    assert result["clear_views_mean_valid"] == (3 if valid else None)


def test_partial_results_preserve_positives_but_never_claim_observed_zero():
    positive = s.finding([{"statistics": statistics()}, {"error": "pixel limit"}], 2)
    assert positive["evidence_status"] == "satellite_positive" and positive["counts_are_lower_bounds"]
    assert not positive["computation_complete"] and positive["statistics"]["qualifying_pixels"] == 2
    zero = s.finding([{"statistics": statistics(0)}], 2)
    assert zero["evidence_status"] == "insufficient_observation" and zero["counts_are_lower_bounds"]


def test_invalid_counts_fail_instead_of_becoming_evidence():
    with pytest.raises(ValueError): s.finding([{"statistics": statistics(101)}], 1)


def test_precise_pixel_limit_error_is_retained_and_sensitive_fields_withheld():
    error = s.provider_error(ValueError("Found 561368, maxPixels allows 300000; https://example.test/?access_token=secret Bearer private refresh_token=secret"))
    assert "561368" in error["message"] and "300000" in error["message"]
    assert "secret" not in error["message"] and "private" not in error["message"]
    assert "https://" not in error["message"]


def test_pixel_limit_stops_batch_and_preserves_pending_events(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import extract_karnataka_rainfall as requests
    ee = MagicMock(); monkeypatch.setitem(sys.modules, "ee", ee)
    def controlled(fn, operation, log, **kwargs):
        if operation == "batch_minimal_metadata": return {"id": 99901}
        if operation.startswith("region:"): return {"count": 1, "area_km2": 1, "bounds": [[[0, 0], [250, 0], [250, 250], [0, 250]]]}
        if operation.startswith("reduce:"): raise ValueError("Found 300001, maxPixels allows 300000")
    monkeypatch.setattr(requests, "bounded_request", controlled)
    selected = s.select_batch(s.candidates([row()], inventory([image(), image(identifier=99902)])), boundaries())
    with TemporaryDirectory() as temporary:
        evidence, access = s.live_review(selected, Path(temporary) / "raw")
        assert evidence[0]["evidence_status"] == "insufficient_observation" and not evidence[0]["computation_complete"]
        assert evidence[1]["evidence_status"] == "not_reviewed" and evidence[1]["partitions"] == []
        assert "300001" in access["stopped_error"]["message"]
        assert "300000" in access["stopped_error"]["message"]
        assert (Path(temporary) / "raw/progress.jsonl").exists()


def test_live_contract_uses_fixed_scale_and_pixel_ceiling_in_temporary_journal(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import extract_karnataka_rainfall as requests
    ee = MagicMock(); monkeypatch.setitem(sys.modules, "ee", ee)
    def controlled(fn, operation, log, **kwargs):
        fn()  # Only the mocked EE expression; sockets are forbidden by conftest.
        if operation == "batch_minimal_metadata": return {"id": 99901}
        if operation.startswith("region:"): return {"count": 1, "area_km2": 1, "bounds": [[[0, 0], [250, 0], [250, 250], [0, 250]]]}
        if operation.startswith("reduce:"): return statistics()
    monkeypatch.setattr(requests, "bounded_request", controlled)
    selected = s.select_batch(s.candidates([row()], inventory()), boundaries())
    with TemporaryDirectory() as temporary:
        evidence, access = s.live_review(selected, Path(temporary) / "raw")
        assert evidence[0]["statistics"]["qualifying_pixels"] == 2 and access["metadata_succeeded"]
        calls = [c for c in ee.mock_calls if c[0].endswith("reduceRegion")]
        assert len(calls) == 1
        assert calls[0].kwargs["scale"] == 250 and calls[0].kwargs["maxPixels"] == 300000
        assert calls[0].kwargs["bestEffort"] is False


def test_offline_validation_and_completed_version_preserve_bytes_hashes_mtimes(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); meta = root / "metadata"; meta.mkdir()
        rows = [row(f"{2001+i}-08-01", f"{2001+i}-08-03", str(i)) for i in range(5)]
        images = [image(r["parsed_start_date"], r["parsed_end_date_inclusive"], 99901+i) for i, r in enumerate(rows)]
        for path, value in [(root / "events.json", rows), (meta / "gfd_inventory.json", inventory(images)),
                            (meta / "public_boundary_inventory.json", boundaries()),
                            (meta / "access.json", {"initialization_succeeded": True, "metadata_succeeded": True})]:
            s.write_new(path, value)
        monkeypatch.setattr(s, "regression", lambda path: {"2728": 33, "3551": 23})
        def controlled(selected, raw, *limits):
            raw.mkdir(); s.write_new(raw / "requests.json", {"fixture": True})
            records = []
            for selection in selected:
                records.append({**selection, "ifi_confirmation": False, "evidence_status": "not_reviewed", "partitions": []})
            return records, {"fixture": True}
        monkeypatch.setattr(s, "live_review", controlled)
        output = root / "version"; raw = root / "raw"
        args = (root / "events.json", meta / "gfd_inventory.json", meta / "public_boundary_inventory.json", meta / "access.json", output, raw)
        s.create(*args)
        def snapshot():
            return {str(p): (p.read_bytes(), s.fingerprint(p), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        before = snapshot(); s.validate(output); assert before == snapshot()
        with pytest.raises(ValueError, match="Version exists"): s.create(*args)
        assert before == snapshot()
        with pytest.raises(ValueError, match="completed"): s.write_new(output / "other.json", {})
        assert before == snapshot()
        assert s.packed(json.loads((output / "manifest.json").read_text())) == (output / "manifest.json").read_bytes()


def test_udupi_regression_scalar_counts_and_original_fixture_bytes(monkeypatch):
    import numpy as np
    import rasterio
    from affine import Affine
    from pyproj import Transformer
    from shapely.geometry import Polygon, mapping
    with TemporaryDirectory() as temporary:
        root = Path(temporary); transform = Transformer.from_crs(s.CRS, "EPSG:4326", always_xy=True)
        ring = [transform.transform(x, y) for x, y in [(475000, 1500000), (484000, 1500000), (484000, 1499750), (475000, 1499750)]]
        s.write_new(root / "udupi_boundary.geojson", {"geometry": mapping(Polygon(ring))})
        events, files = [], {}
        for identifier, count in [(2728, 33), (3551, 23)]:
            path = root / f"fixture_{identifier}.tif"; values = np.full((3, 1, 36), -9999, dtype="float32")
            values[0, 0, :count] = 1; values[1, 0, :count] = 0; values[2, 0, :count] = 2
            with rasterio.open(path, "w", driver="GTiff", height=1, width=36, count=3, dtype="float32", crs=s.CRS,
                               transform=Affine(250, 0, 475000, 0, -250, 1500000)) as handle:
                handle.write(values)
            events.append({"event_id": identifier, "raster_file": path.name}); files[path.name] = s.fingerprint(path)
        s.write_new(root / "manifest.json", {"events": events, "files": files})
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
        assert s.regression(root) == {"2728": 33, "3551": 23}
        assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}


def test_blocked_live_checkpoint_exits_nonzero_even_when_files_validate(monkeypatch):
    with TemporaryDirectory() as temporary:
        output = Path(temporary) / "version"; output.mkdir()
        s.write_new(output / "manifest.json", {"access": {"stopped_error": {"type": "fixture-only-error"}}})
        monkeypatch.setattr(sys, "argv", ["script", "--output", str(output)])
        monkeypatch.setattr(s, "create", lambda *args: {"fixture_only": True})
        with pytest.raises(SystemExit) as exc:
            s.main()
        assert exc.value.code == 2
