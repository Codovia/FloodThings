"""Controlled fixtures only; socket guard inherited, all output in disposable directories."""
import importlib.util
import csv
import io
import json
import os
import stat
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "extract_udupi_history.py"
spec = importlib.util.spec_from_file_location("historical_extraction", SCRIPT)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
STAMP = "2026-10-03T00:00:00+00:00"


def millis(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture
def controlled_data():
    rows, events, details = [], [], []
    for eid, start, end in history.EVENTS:
        for index, day in enumerate(history.requested_dates(start, end), 1):
            rows.append({"event_id": eid, "district": "Udupi", "boundary_id": history.BOUNDARY_SHAPE_ID,
                         "date": day, "source_id": history.CHIRPS, "image_id": day.replace("-", ""),
                         "source_time_start_ms": millis(day), "units": "mm/day", "mean_mm": float(index),
                         "min_mm": 0.0, "max_mm": 100.0, "valid_pixel_count": 10, "expected_pixel_count": 10,
                         "status": "available", "retrieved_at": STAMP})
        events.append({"event_id": eid, "district": "Udupi", "boundary_id": history.BOUNDARY_SHAPE_ID,
                       "source_id": history.verification.FLOOD_ID, "image_id": history.event_asset(eid, start, end),
                       "start_date": start, "end_date_inclusive": end, "source_time_start_ms": millis(start),
                       "source_time_end_ms": millis(end), "extent_semantics": "event_window_maximum_not_daily_occurrence",
                       "processing_scale_m": 250, "partitions_completed": 4, "valid_observed_pixels": 40,
                       "mapped_nonpermanent_pixels": 8, "positive_observed_pixels": 4, "clear_views_sum": 80,
                       "clear_views_count": 40, "finding": "confirmed_mapped_nonpermanent_floodwater", "retrieved_at": STAMP})
        details.append({"image_id": events[-1]["image_id"], "partitions": [{"statistics": {
            "observed_nonpermanent_flood_sum": 1, "observed_nonpermanent_flood_count": 10}} for _ in range(4)]})
    history.add_lags(rows)
    manifest = {"version": history.VERSION, "query_parameters": history.plan(), "sources": deepcopy(history.SOURCES),
                "boundary": {"properties": {"shapeID": history.BOUNDARY_SHAPE_ID}}, "flood_queries": details}
    return rows, events, manifest


def test_plan_is_offline_exact_and_bounded(monkeypatch, capsys):
    def forbidden(*args):
        raise AssertionError("Plan must not import Earth Engine")
    monkeypatch.setattr(history.importlib, "import_module", forbidden)
    assert history.main(["--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [e["requested_daily_images"] for e in plan["events"]] == [31, 32]
    assert [e["rainfall_start_inclusive"] for e in plan["events"]] == ["2005-08-31", "2009-09-11"]
    assert [e["rainfall_end_exclusive"] for e in plan["events"]] == ["2005-10-01", "2009-10-13"]
    assert plan["full_flood_collection_scan"] is False
    assert plan["bestEffort"] is False
    assert plan["flood_max_pixels_per_partition"] == 300000
    assert plan["wall_seconds"] == 120


def test_complete_coverage_and_past_only_lags(controlled_data):
    rows, events, _ = controlled_data
    result = history.validate(rows, events)
    assert result["complete_requested_rainfall"] is True
    assert result["rainfall_rows"] == 63 and result["event_rows"] == 2
    assert result["preceding_3d_totals_available"] == 57
    assert result["preceding_7d_totals_available"] == 49
    start_row = next(r for r in rows if r["date"] == "2005-09-14")
    assert start_row["preceding_3d_mm"] == 12 + 13 + 14
    assert start_row["preceding_7d_mm"] == sum(range(8, 15))
    # A huge current/future observation cannot influence this row's preceding totals.
    start_row["mean_mm"] = 10000
    history.add_lags(rows)
    assert start_row["preceding_3d_mm"] == 39
    assert start_row["preceding_7d_mm"] == 77


def test_missing_date_is_not_filled_and_invalidates_lags(controlled_data):
    rows, events, _ = controlled_data
    del rows[14]
    history.add_lags(rows)
    result = history.validate(rows, events)
    assert result["missing_image_dates"] == ["2005-09-14"]
    assert result["complete_requested_rainfall"] is False
    assert rows[14]["preceding_3d_mm"] is None and rows[14]["preceding_7d_mm"] is None
    assert len(rows) == 62


@pytest.mark.parametrize("status,count", [("unavailable", 0), ("partial_spatial_coverage", 9)])
def test_null_or_incomplete_spatial_data_never_becomes_zero(controlled_data, status, count):
    rows, events, _ = controlled_data
    rows[14].update(status=status, valid_pixel_count=count)
    if count == 0:
        rows[14].update(mean_mm=None, min_mm=None, max_mm=None)
    history.add_lags(rows)
    assert rows[15]["preceding_3d_mm"] is None
    result = history.validate(rows, events)
    assert result["unavailable_or_partial_dates"] == ["2005-09-14"]


@pytest.mark.parametrize("field,value,error", [
    ("mean_mm", -1.0, "finite and non-negative"), ("mean_mm", float("nan"), "finite and non-negative"),
    ("max_mm", float("inf"), "finite and non-negative"), ("image_id", "invented", "image ID"),
    ("units", "mm/hour", "image ID/units"), ("boundary_id", "invented", "provenance"),
    ("source_time_start_ms", 0, "source date"), ("preceding_3d_mm", 0, "preceding rainfall"),
])
def test_invalid_rainfall_or_provenance_is_rejected(controlled_data, field, value, error):
    rows, events, _ = controlled_data
    rows[0][field] = value
    with pytest.raises(ValueError, match=error):
        history.validate(rows, events)


def test_duplicate_date_district_source_is_rejected(controlled_data):
    rows, events, _ = controlled_data
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        history.validate(rows, events)


@pytest.mark.parametrize("field,value,error", [
    ("event_id", 2049, "Unapproved"), ("end_date_inclusive", "2005-10-01", "dates"),
    ("processing_scale_m", 30, "incompatible"), ("partitions_completed", 3, "Incomplete"),
    ("extent_semantics", "daily_flood", "incompatible"), ("positive_observed_pixels", 41, "eligible"),
    ("clear_views_sum", 0, "clear-view"),
])
def test_event_identity_quality_and_extent_are_checked(controlled_data, field, value, error):
    rows, events, _ = controlled_data
    events[0][field] = value
    with pytest.raises(ValueError, match=error):
        history.validate(rows, events)


def test_zero_mapped_water_is_not_a_negative_label(controlled_data):
    rows, events, _ = controlled_data
    events[0].update(positive_observed_pixels=0, finding="no_positive_pixels_in_reviewed_map_not_a_nonflood_label")
    history.validate(rows, events)
    events[0]["finding"] = "verified_nonflood"
    with pytest.raises(ValueError, match="finding"):
        history.validate(rows, events)


def test_roundtrip_checksums_and_overwrite_refusal(controlled_data):
    rows, events, manifest = controlled_data
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        result = history.publish(directory, rows, events, manifest)
        assert history.validate_version(directory) == result
        original = {p.name: p.read_bytes() for p in directory.iterdir()}
        with pytest.raises(FileExistsError):
            history.publish(directory, rows, events, manifest)
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == original
        # Deliberate corruption of a disposable fixture; completed versions are read-only by default.
        (directory / "daily_rainfall.csv").chmod(0o600)
        with (directory / "daily_rainfall.csv").open("a") as handle:
            handle.write("corruption\n")
        with pytest.raises(ValueError, match="Checksum"):
            history.validate_version(directory)


def test_invalid_data_never_publishes_a_version(controlled_data):
    rows, events, manifest = controlled_data
    events[0]["partitions_completed"] = 3
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        with pytest.raises(ValueError, match="Incomplete"):
            history.publish(directory, rows, events, manifest)
        assert not directory.exists()


def test_existing_version_refused_before_client_import(monkeypatch, capsys):
    def forbidden(*args):
        raise AssertionError("Existing version must be refused before network access")
    monkeypatch.setattr(history.importlib, "import_module", forbidden)
    with TemporaryDirectory() as temporary:
        assert history.main(["--output", temporary]) == 2
        assert "Version already exists" in capsys.readouterr().out
        assert list(Path(temporary).iterdir()) == []


def test_live_adapter_uses_only_original_event_assets_and_partition_budget(monkeypatch):
    ee = MagicMock()
    geometry = object()
    regions, owners = [object() for _ in range(4)], [object() for _ in range(4)]
    monkeypatch.setattr(history.verification, "district_partitions", lambda client, geom: list(zip(regions, owners, [[i] for i in range(4)])))
    image = ee.Image.return_value
    image.toDictionary.return_value.getInfo.side_effect = [
        {"id": eid, "system:time_start": millis(start), "system:time_end": millis(end)} for eid, start, end in history.EVENTS]
    reduction = image.select.return_value.eq.return_value.And.return_value.rename.return_value.addBands.return_value.addBands.return_value.updateMask.return_value.reduceRegion
    reduction.return_value.getInfo.return_value = {"observed_nonpermanent_flood_sum": 1,
        "observed_nonpermanent_flood_count": 10, "mapped_nonpermanent_flood_sum": 2,
        "clear_views_sum": 20, "clear_views_count": 10}
    rows, details = [], []
    history.extract_events(ee, geometry, {"properties": {"shapeID": history.BOUNDARY_SHAPE_ID}}, rows, details)
    assert [call.args[0] for call in ee.Image.call_args_list] == [history.event_asset(*event) for event in history.EVENTS]
    ee.ImageCollection.assert_not_called()
    assert len(reduction.call_args_list) == 8
    for call in reduction.call_args_list:
        assert call.kwargs["geometry"] in regions
        assert call.kwargs["scale"] == 250 and call.kwargs["maxPixels"] == 300000
        assert call.kwargs["bestEffort"] is False
    image.select.assert_any_call("clear_views")
    image.select.assert_any_call("jrc_perm_water")
    assert [row["positive_observed_pixels"] for row in rows] == [4, 4]


def test_total_deadline_never_publishes(monkeypatch, capsys):
    monkeypatch.setattr(history.importlib, "import_module", lambda name: object())
    def expired(*args):
        raise history.verification.VerificationDeadlineExceeded("120 second bound")
    monkeypatch.setattr(history, "extract", expired)
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        assert history.main(["--output", str(directory)]) == 2
        assert "VerificationDeadlineExceeded" in capsys.readouterr().out
        assert not directory.exists()


def test_rainfall_adapter_preserves_native_grid_original_ids_and_nulls():
    ee = MagicMock()
    geometry = object()
    collection = ee.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value.sort.return_value
    collection.size.return_value.getInfo.return_value = 2
    projection = ee.Image.return_value.select.return_value.projection.return_value
    grid = {"crs": "EPSG:4326", "transform": [0.05, 0, -180, 0, -0.05, 50]}
    projection.getInfo.return_value = grid
    projection.nominalScale.return_value.getInfo.return_value = 5565.97454
    ee.Image.constant.return_value.rename.return_value.reduceRegion.return_value.getInfo.return_value = {"pixels": 10}
    batches = []
    for _, start, end in history.EVENTS:
        days = history.requested_dates(start, end)
        batches.append({"features": [{"properties": {"date": day, "image_id": day.replace("-", ""),
            "source_time_start_ms": millis(day), "precipitation_mean": 5 if i == 0 else None,
            "precipitation_min": 1 if i == 0 else None, "precipitation_max": 10 if i == 0 else None,
            "precipitation_count": 10 if i == 0 else 0}} for i, day in enumerate(days[:2])]})
    ee.FeatureCollection.return_value.getInfo.side_effect = batches
    rows, details = [], []
    history.extract_rainfall(ee, geometry, {"properties": {"shapeID": history.BOUNDARY_SHAPE_ID}}, rows, details)
    assert len(rows) == 4
    assert rows[1]["mean_mm"] is None and rows[1]["status"] == "unavailable"
    assert rows[1]["preceding_3d_mm"] is None
    assert details[0]["nominal_scale_m"] == 5565.97454
    assert details[0]["native_projection"] == grid
    filtered = ee.ImageCollection.return_value.filterBounds.return_value.filterDate
    assert [call.args for call in filtered.call_args_list] == [("2005-08-31", "2005-10-01"), ("2009-09-11", "2009-10-13")]
    # Execute the captured server-side mapper once to inspect actual reduction arguments.
    mapper = collection.toList.return_value.slice.return_value.map.call_args_list[0].args[0]
    mapper(object())
    args = ee.Image.return_value.select.return_value.reduceRegion.call_args.kwargs
    assert args["geometry"] is geometry
    assert args["crs"] == grid["crs"] and args["crsTransform"] == grid["transform"]
    assert "scale" not in args
    assert args["maxPixels"] == 10000 and args["bestEffort"] is False


def test_manifest_license_and_partition_evidence_are_validated(controlled_data):
    rows, events, manifest = controlled_data
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        history.publish(directory, rows, events, manifest)
        original = json.loads((directory / "manifest.json").read_text())
        (directory / "manifest.json").chmod(0o600)  # Explicit tampering inside this temporary fixture only.
        corrupted = deepcopy(original)
        corrupted["sources"][history.verification.FLOOD_ID]["license"] = "unrestricted"
        (directory / "manifest.json").write_text(json.dumps(corrupted))
        with pytest.raises(ValueError, match="source/boundary"):
            history.validate_version(directory)
        original["flood_queries"][0]["partitions"][0]["statistics"]["observed_nonpermanent_flood_sum"] = 999
        (directory / "manifest.json").write_text(json.dumps(original))
        with pytest.raises(ValueError, match="Partition evidence/table"):
            history.validate_version(directory)


def load_spatial():
    spec = importlib.util.spec_from_file_location("spatial_integrity_regression", SCRIPT.with_name("extract_udupi_spatial.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def byte_state(directory):
    return (directory.stat().st_mtime_ns,
            {p.name: (p.read_bytes(), history.checksum(p), p.stat().st_mtime_ns) for p in directory.iterdir()})


@pytest.mark.parametrize("reformatted", [False, True])
def test_validation_and_map_processing_preserve_exact_bytes_hashes_and_mtimes(controlled_data, monkeypatch, capsys, reformatted):
    rows, events, manifest = controlled_data
    spatial = load_spatial()
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        history.publish(directory, rows, events, manifest)
        if reformatted:
            source = directory / "event_evidence.csv"
            records = list(csv.reader(io.StringIO(source.read_text())))
            buffer = io.StringIO(newline="")
            csv.writer(buffer).writerows([[f" {value} " for value in record] for record in records])
            source.chmod(0o600)  # Deliberate fixture mutation, never production data.
            source.write_bytes(buffer.getvalue().encode())
        for index, path in enumerate(directory.iterdir()):
            os.utime(path, ns=(1700000000000000000 + index, 1700000000000000000 + index))
        monkeypatch.setattr(spatial, "HISTORY", directory)
        monkeypatch.setattr(spatial, "EXPECTED", {2728: 4, 3551: 4})
        before = byte_state(directory)
        real_open = Path.open

        def read_only_open(path, mode="r", *args, **kwargs):
            if path.resolve().is_relative_to(directory.resolve()):
                assert not any(flag in mode for flag in "wax+"), "Processing attempted a dataset write"
            return real_open(path, mode, *args, **kwargs)

        with monkeypatch.context() as guard:
            guard.setattr(Path, "open", read_only_open)
            if reformatted:
                with pytest.raises(ValueError, match="Checksum mismatch"):
                    history.validate_version(directory)
                with pytest.raises(ValueError, match="Checksum mismatch"):
                    spatial.read_history()
                assert history.main(["--validate-only", "--output", str(directory)]) == 2
            else:
                assert history.validate_version(directory)["rainfall_rows"] == 63
                evidence, validation = spatial.read_history()
                assert len(evidence) == 2
                assert validation["event_csv_formatting_changed"] is False
                assert history.main(["--validate-only", "--output", str(directory)]) == 0
        capsys.readouterr()
        assert byte_state(directory) == before


@pytest.mark.parametrize("alias", [False, True])
def test_completed_version_cannot_be_reused_as_output_or_staging(controlled_data, monkeypatch, capsys, alias):
    rows, events, manifest = controlled_data
    spatial = load_spatial()
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        history.publish(directory, rows, events, manifest)
        output = directory
        if alias:
            output = Path(temporary) / "symlink"
            output.symlink_to(directory, target_is_directory=True)
        before = byte_state(directory)
        with pytest.raises(FileExistsError, match="completed dataset"):
            history.write_table(output / "unwanted.csv", [], [])
        with pytest.raises(FileExistsError, match="completed dataset"):
            spatial.write_json(output / "unwanted.geojson", {})
        with pytest.raises(FileExistsError, match="completed dataset"):
            spatial.extract(object(), object(), output)
        with pytest.raises(FileExistsError, match="already exists"):
            history.publish(output, rows, events, manifest)
        def forbidden(*args):
            raise AssertionError("Output rejection must precede any client import")
        monkeypatch.setattr(history.importlib, "import_module", forbidden)
        assert history.main(["--output", str(output / "child")]) == 2
        assert spatial.main(["--output", str(output / "child")]) == 2
        assert "completed dataset" in capsys.readouterr().out
        assert byte_state(directory) == before


def test_new_completed_version_is_write_protected(controlled_data):
    rows, events, manifest = controlled_data
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / history.VERSION
        history.publish(directory, rows, events, manifest)
        assert stat.S_IMODE(directory.stat().st_mode) & 0o222 == 0
        assert all(stat.S_IMODE(p.stat().st_mode) & 0o222 == 0 for p in directory.iterdir())
