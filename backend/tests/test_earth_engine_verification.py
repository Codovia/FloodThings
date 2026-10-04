"""No Earth Engine dependency/credentials needed; inherited socket guard applies."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_earth_engine.py"
spec = importlib.util.spec_from_file_location("verify_earth_engine", SCRIPT)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def test_plan_is_offline_and_bounded(monkeypatch, capsys):
    def forbidden(*args):
        raise AssertionError("Offline plan must not import the authenticated client")
    monkeypatch.setattr(verification.importlib, "import_module", forbidden)
    assert verification.main(["--plan", "--day", "2020-12-31"]) == 0
    query = json.loads(capsys.readouterr().out)
    assert query["rainfall_end_exclusive"] == "2021-01-01"
    assert query["event_limit_per_pilot"] == 20
    assert query["max_pixels_per_reduction"] == 300000
    assert query["wall_seconds"] == 120
    assert set(query["collections"]) == set(verification.COLLECTIONS)


def test_invalid_day_is_rejected_without_client_import():
    with pytest.raises(SystemExit) as exc:
        verification.main(["--plan", "--day", "2018-02-30"])
    assert exc.value.code == 2


def test_access_failure_stops_all_dataset_queries():
    ee = MagicMock()
    ee.Initialize.side_effect = RuntimeError("Authentication unavailable")
    report = verification.verify(ee, "authorized-test-project", verification.plan("2018-08-15"))
    assert report["status"] == "stopped"
    assert report["error"] == {"stage": "access", "type": "RuntimeError", "message": "Authentication unavailable"}
    assert report["pilots"] == {}
    assert report["training_dataset_ready"] is False
    ee.Number.assert_not_called()
    ee.ImageCollection.assert_not_called()
    ee.FeatureCollection.assert_not_called()


def test_smallest_access_probe_and_project_are_explicit():
    ee = MagicMock()
    ee.Number.return_value.getInfo.return_value = 1
    result = verification.probe_access(ee, "authorized-test-project")
    ee.Initialize.assert_called_once_with(project="authorized-test-project")
    ee.data.setDeadline.assert_called_once_with(10000)
    ee.data.setMaxRetries.assert_called_once_with(0)
    ee.Number.assert_called_once_with(1)
    assert result["initialization"] == "succeeded"


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_boundary_has_no_fabricated_fallback(count):
    ee = MagicMock()
    features = ee.FeatureCollection.return_value.filter.return_value.filter.return_value.filter.return_value
    features.size.return_value.getInfo.return_value = count
    with pytest.raises(ValueError, match="require exactly one genuine"):
        verification.find_boundary(ee, ["Udupi"])
    ee.Feature.assert_not_called()
    ee.Geometry.assert_not_called()


@pytest.mark.parametrize("stats,expected", [
    ({}, "unknown_no_valid_pixels"),
    ({"nonpermanent_flood_max": None, "nonpermanent_flood_count": 0}, "unknown_no_valid_pixels"),
    ({"nonpermanent_flood_max": 0, "nonpermanent_flood_count": 10}, "no_positive_pixel_in_this_event_map_not_a_nonflood_label"),
    ({"nonpermanent_flood_max": 1, "nonpermanent_flood_count": 10}, "satellite_mapped_nonpermanent_water_present"),
])
def test_flood_evidence_never_invents_negative_labels(stats, expected):
    assert verification.flood_finding(stats) == expected


def test_empty_collection_is_unknown_not_a_nonflood_label():
    ee = MagicMock()
    collection = ee.ImageCollection.return_value.filterBounds.return_value
    collection.size.return_value.getInfo.return_value = 0
    result = verification.inspect_collection(ee, verification.FLOOD_ID, object(), verification.plan("2018-08-15"))
    assert result["footprint_image_count"] == 0
    assert result["finding"] == "no_matching_images_not_evidence_of_no_flood"
    ee.Image.assert_not_called()


def test_flood_review_cap_quality_and_dates_are_preserved():
    ee = MagicMock()
    collection = ee.ImageCollection.return_value.filterBounds.return_value
    collection.size.return_value.getInfo.return_value = 21
    dictionary = ee.Dictionary.return_value
    dictionary.getInfo.return_value = {"bands": ["flooded"]}
    ee.Image.return_value.toDictionary.return_value.getInfo.side_effect = [
        {"system:time_start": 1534291200000, "id": i} for i in range(20)
    ]
    reduction = ee.Image.return_value.select.return_value.addBands.return_value.addBands.return_value.reduceRegion
    reduction.return_value.getInfo.return_value = {
        "clear_views_mean": 2, "clear_perc_mean": 10,
        "nonpermanent_flood_max": 0, "nonpermanent_flood_count": 8,
    }
    result = verification.inspect_collection(ee, verification.FLOOD_ID, object(), verification.plan("2018-08-15"))
    assert result["truncated"] is True
    assert len(result["events"]) == 20
    assert result["finding"] == "bounded_event_review_not_complete"
    assert result["events"][0]["properties"]["system:time_start"] == 1534291200000
    assert result["events"][0]["statistics"]["clear_perc_mean"] == 10
    collection.filterDate.assert_not_called()
    collection.sort.return_value.limit.assert_called_once_with(20)


def test_missing_client_returns_install_guidance(monkeypatch, capsys):
    def unavailable(*args):
        raise ModuleNotFoundError("No module named 'ee'")
    monkeypatch.setattr(verification.importlib, "import_module", unavailable)
    assert verification.main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "stopped"


def test_flood_pixel_error_preserves_partial_events_and_exact_geometry():
    ee = MagicMock()
    geometry = object()
    collection = ee.ImageCollection.return_value.filterBounds.return_value
    collection.size.return_value.getInfo.return_value = 3
    ee.Dictionary.return_value.getInfo.return_value = {"bands": ["flooded"]}
    image = ee.Image.return_value
    image.toDictionary.return_value.getInfo.side_effect = [{"id": 1}, {"id": 2}]
    reduction = image.select.return_value.addBands.return_value.addBands.return_value.reduceRegion
    reduction.return_value.getInfo.side_effect = [
        {"nonpermanent_flood_max": 1, "nonpermanent_flood_count": 3,
         "observed_nonpermanent_flood_max": 1, "clear_views_mean": 2},
        RuntimeError("Too many pixels: 300001 exceeds maxPixels 300000"),
    ]
    result = verification.inspect_collection(ee, verification.FLOOD_ID, geometry, verification.plan("2018-08-15"))
    assert result["status"] == "partial"
    assert result["footprint_image_count"] == 3
    assert result["error"]["message"] == "Too many pixels: 300001 exceeds maxPixels 300000"
    assert result["events"][0]["finding"] == "satellite_mapped_nonpermanent_water_present"
    assert result["events"][0]["observation_assessment"] == "mapped_nonpermanent_water_has_clear_view_support"
    assert result["events"][1] == {"properties": {"id": 2}, "statistics": None}
    assert reduction.call_count == 2  # No escalation or retry after the pixel error.
    for call in reduction.call_args_list:
        assert call.kwargs["geometry"] is geometry
        assert call.kwargs["maxPixels"] == 300000
        assert call.kwargs["scale"] == 250
        assert call.kwargs["bestEffort"] is False


def test_collection_failure_continues_dem_and_udupi(monkeypatch):
    ee = MagicMock()
    ee.Number.return_value.getInfo.return_value = 1
    geometry = object()
    monkeypatch.setattr(verification, "find_boundary", lambda *_: (geometry, {"source_id": verification.BOUNDARY_ID}))
    results = []

    def inspect(_ee, source_id, _geometry, _query):
        result = {"source_id": source_id, "status": "available"}
        if source_id == verification.FLOOD_ID:
            result.update(status="partial", footprint_image_count=2,
                          error={"type": "RuntimeError", "message": "Pixel limit exceeded"})
        results.append(source_id)
        return result

    monkeypatch.setattr(verification, "inspect_collection", inspect)
    report = verification.verify(ee, "floodpulse", verification.plan("2018-08-15"))
    assert report["status"] == "partial"
    assert report["training_dataset_ready"] is False
    assert results == list(verification.COLLECTIONS) * 2
    for pilot in verification.PILOTS:
        assert report["pilots"][pilot]["collections"]["COPERNICUS/DEM/GLO30_2024_1"]["status"] == "available"
        assert "error" in report["pilots"][pilot]["collections"][verification.FLOOD_ID]


def test_request_timeout_is_collection_error_not_global_deadline(monkeypatch):
    ee = MagicMock()
    monkeypatch.setattr(verification, "_inspect_collection", lambda *_: (_ for _ in ()).throw(TimeoutError("Request timed out")))
    result = verification.inspect_collection(ee, verification.FLOOD_ID, object(), verification.plan("2018-08-15"))
    assert result["status"] == "unavailable"
    assert result["error"]["type"] == "TimeoutError"


def test_total_deadline_stops_queries_and_preserves_completed_results(monkeypatch):
    ee = MagicMock()
    ee.Number.return_value.getInfo.return_value = 1
    monkeypatch.setattr(verification, "find_boundary", lambda *_: (object(), {}))
    completed = {"source_id": "UCSB-CHG/CHIRPS/DAILY", "status": "available"}
    def inspect(_ee, source_id, *_):
        if source_id == "UCSB-CHG/CHIRPS/DAILY":
            return completed
        raise verification.VerificationDeadlineExceeded("Verification exceeded 120 seconds")
    monkeypatch.setattr(verification, "_inspect_collection", inspect)
    report = verification.verify(ee, "floodpulse", verification.plan("2018-08-15"))
    assert report["status"] == "stopped"
    assert report["error"]["type"] == "VerificationDeadlineExceeded"
    assert report["pilots"]["Bengaluru Urban"]["collections"]["UCSB-CHG/CHIRPS/DAILY"] == completed
    assert "Udupi" not in report["pilots"]


@pytest.mark.parametrize('elevation,mask,expected', [(112.5, 1, 'available'), (0, 1, 'available'),
                                                   (None, 0, 'unavailable'), (None, 1, 'unavailable')])
def test_dem_mosaics_tiles_and_checks_unmasked_centroid(elevation, mask, expected):
    ee, collection, geometry = MagicMock(), MagicMock(), MagicMock()
    tiles = collection.sort.return_value
    tiles.aggregate_array.return_value.getInfo.return_value = ['N12_00_E077_00', 'N13_00_E077_00']
    geometry.centroid.return_value.coordinates.return_value.getInfo.return_value = [77.5, 12.9]
    mosaic = ee.ImageCollection.fromImages.return_value.mosaic.return_value.setDefaultProjection.return_value
    reduction = mosaic.addBands.return_value.reduceRegion
    reduction.return_value.getInfo.return_value = {'DEM': elevation, 'dem_valid_mask': mask,
                                                 'tile_index': 0 if elevation is not None else None}
    result = verification.inspect_dem(ee, collection, geometry, {}, 2)
    collection.sort.assert_called_once_with('system:index')
    ee.ImageCollection.fromImages.return_value.mosaic.assert_called_once()
    assert result['tile_ids_used'] == ['N12_00_E077_00', 'N13_00_E077_00']
    assert result['sampling_point'] == [77.5, 12.9]
    assert result['sample_status'] == expected
    assert result['centroid_sample']['DEM'] is elevation
    assert reduction.call_args.kwargs['geometry'] is geometry.centroid.return_value
    assert reduction.call_args.kwargs['scale'] == 30
    assert reduction.call_args.kwargs['bestEffort'] is False
    if elevation is None:
        assert result['sample_tile_id'] is None
        assert 'No elevation was substituted' in result['diagnostic']
    else:
        assert result['sample_tile_id'] == 'N12_00_E077_00'


def test_dem_dispatch_keeps_actual_district_filter(monkeypatch):
    ee, geometry = MagicMock(), object()
    collection = ee.ImageCollection.return_value.filterBounds.return_value
    collection.size.return_value.getInfo.return_value = 2
    received = []
    monkeypatch.setattr(verification, 'inspect_dem', lambda *args: received.append(args) or args[3])
    verification.inspect_collection(ee, verification.DEM_ID, geometry, verification.plan('2018-08-15'))
    ee.ImageCollection.return_value.filterBounds.assert_called_once_with(geometry)
    assert received[0][1] is collection
    assert received[0][2] is geometry
    ee.Image.assert_not_called()  # DEM dispatch does not pick the first tile as its sample.


def test_half_open_partition_windows_cover_once_including_edges():
    windows = verification.partition_windows([(0, -1000), (1000, -1000), (1000, 0), (0, 0), (0, -1000)])
    assert len(windows) == 4
    for x in range(4):
        for y in range(4):
            assert sum(x0 <= x < x1 and y0 <= y < y1 for x0, x1, y0, y1 in windows) == 1
    assert sum(x0 <= 4 < x1 for x0, x1, _, _ in windows) == 0


def test_partition_regions_are_clipped_to_genuine_district_geometry():
    ee, geometry = MagicMock(), MagicMock()
    geometry.bounds.return_value.coordinates.return_value.getInfo.return_value = [
        [(0, -1000), (1000, -1000), (1000, 0), (0, 0), (0, -1000)]]
    rectangles = [object() for _ in range(4)]
    ee.Geometry.Rectangle.side_effect = rectangles
    parts = verification.district_partitions(ee, geometry)
    assert len(parts) == 4
    assert [call.args[0] for call in geometry.intersection.call_args_list] == rectangles
    assert all(call.kwargs['maxError'] == 1 for call in geometry.intersection.call_args_list)
    assert all(part[0] is geometry.intersection.return_value for part in parts)
    ee.Image.pixelCoordinates.assert_called_once()


@pytest.mark.parametrize('parts,expected,complete', [
    ([{'observed_nonpermanent_flood_sum': 1, 'observed_nonpermanent_flood_count': 5}] * 4,
     'confirmed_mapped_nonpermanent_floodwater', True),
    ([{'observed_nonpermanent_flood_sum': 0, 'observed_nonpermanent_flood_count': 5}] * 4,
     'no_positive_pixels_in_reviewed_map_not_a_nonflood_label', True),
    ([{'observed_nonpermanent_flood_sum': None, 'observed_nonpermanent_flood_count': 0}] * 4,
     'no_valid_observed_pixels', True),
    ([{'observed_nonpermanent_flood_sum': 0, 'observed_nonpermanent_flood_count': 5}],
     'incomplete_computation', False),
    ([{'observed_nonpermanent_flood_sum': 1, 'observed_nonpermanent_flood_count': 5}],
     'confirmed_mapped_nonpermanent_floodwater', False),
])
def test_partitioned_event_evidence_and_incomplete_computations(parts, expected, complete):
    result = verification.partitioned_finding({'partitions': [{'statistics': stats} for stats in parts]})
    assert result['finding'] == expected
    assert result['computation_complete'] is complete


def test_udupi_deadline_preserves_completed_event_and_unreviewed_ids(monkeypatch):
    ee, geometry = MagicMock(), MagicMock()
    collection = ee.ImageCollection.return_value.filterBounds.return_value.sort.return_value
    collection.size.return_value.getInfo.return_value = 3
    inventory = [{'id': i, 'system:time_start': 1534291200000, 'system:time_end': 1534377600000}
                 for i in (2049, 2758, 3551)]
    collection.toList.return_value.map.return_value.getInfo.return_value = inventory
    regions = [object() for _ in range(4)]
    monkeypatch.setattr(verification, 'district_partitions', lambda *_: [(r, object(), [0, 1, 0, 1]) for r in regions])
    image = ee.Image.return_value
    reduction = image.select.return_value.eq.return_value.And.return_value.rename.return_value.addBands.return_value.addBands.return_value.updateMask.return_value.reduceRegion
    # Raw and observed share a mocked select chain but actual masks are exercised live.
    reduction.return_value.getInfo.side_effect = [
        {'observed_nonpermanent_flood_sum': 0, 'observed_nonpermanent_flood_count': 5}] * 4 + [
        verification.VerificationDeadlineExceeded('Verification exceeded 120 seconds')]
    result = {}
    with pytest.raises(verification.VerificationDeadlineExceeded):
        verification.review_udupi_batch(ee, geometry, result, [2049, 2758, 3551])
    assert result['events'][0]['computation_complete'] is True
    assert result['events'][0]['properties']['id'] == 2049
    assert result['events'][0]['properties']['system:time_end'] == 1534377600000
    assert result['events'][1]['finding'] == 'incomplete_computation'
    assert result['unreviewed_event_ids'] == [2758, 3551]
    for call in reduction.call_args_list:
        assert call.kwargs['geometry'] in regions
        assert call.kwargs['scale'] == 250
        assert call.kwargs['maxPixels'] == 300000
        assert call.kwargs['bestEffort'] is False


def test_correction_report_keeps_shared_result_when_total_budget_expires(monkeypatch):
    ee = MagicMock()
    ee.Number.return_value.getInfo.return_value = 1
    monkeypatch.setattr(verification, 'find_boundary', lambda *_: (object(), {}))
    monkeypatch.setattr(verification, '_inspect_collection', lambda _ee, _id, _geom, _query, result:
                        result.update(sample_status='available', centroid_sample={'DEM': 10}))
    def interrupted(_ee, _geom, result, _requested):
        result.update(events=[{'properties': {'id': 2049}, 'computation_complete': True}],
                      unreviewed_event_ids=[2758, 3551])
        raise verification.VerificationDeadlineExceeded('Verification exceeded 120 seconds')
    monkeypatch.setattr(verification, 'review_udupi_batch', interrupted)
    report = verification.verify_corrections(ee, 'floodpulse', verification.plan('2018-08-15'), [2049, 2758, 3551])
    assert report['status'] == 'stopped'
    flood = report['pilots']['Udupi']['collections'][verification.FLOOD_ID]
    assert flood['events'][0]['properties']['id'] == 2049
    assert flood['unreviewed_event_ids'] == [2758, 3551]
    assert report['pilots']['Bengaluru Urban']['collections'][verification.DEM_ID]['sample_status'] == 'available'


def test_corrections_reject_unbounded_event_batch():
    with pytest.raises(SystemExit) as exc:
        verification.main(['--pilot-corrections', '--udupi-event-ids', '1,2,3,4', '--plan'])
    assert exc.value.code == 2


def test_dem_with_no_intersecting_tiles_is_explicitly_missing():
    ee = MagicMock()
    collection = ee.ImageCollection.return_value.filterBounds.return_value
    collection.size.return_value.getInfo.return_value = 0
    result = verification.inspect_collection(ee, verification.DEM_ID, object(), verification.plan('2018-08-15'))
    assert result['sample_status'] == 'unavailable'
    assert result['centroid_sample'] is None
    assert result['tile_ids_used'] == []
    assert 'No DEM tile' in result['diagnostic']
