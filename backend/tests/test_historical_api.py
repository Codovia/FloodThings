"""API contracts use controlled local fixtures only; network/socket guard remains active."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.historical import BOUNDARY_ID, EVENTS, SOURCE_ID, VERSION, HistoricalStore, get_historical_store
from app.main import app


@pytest.fixture
def isolated_api():
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        boundary = {"type": "Feature", "properties": {"shapeID": BOUNDARY_ID}, "geometry": {
            "type": "Polygon", "coordinates": [[[74,13],[75,13],[75,14],[74,14],[74,13]]]}}
        (directory / "udupi_boundary.geojson").write_text(json.dumps(boundary))
        event_records = []
        for eid, (start, end, count) in EVENTS.items():
            geometry = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {
                "type": "Polygon", "coordinates": [[[74.5,13.5],[74.501,13.5],[74.501,13.501],[74.5,13.5]]]},
                "properties": {"event_id": eid, "grid_row": -6000, "grid_col": 1900+i,
                               "flooded": 1, "jrc_perm_water": 0, "clear_views": 2,
                               "observation_valid": 1}} for i in range(count)]}
            (directory / f"event_{eid}.geojson").write_text(json.dumps(geometry))
            (directory / f"event_{eid}.tif").write_bytes(b"controlled-api-contract-fixture")
            event_records.append({"event_id": eid, "image_id": f"{SOURCE_ID}/DFO_{eid}_From_{start.replace('-','')}_to_{end.replace('-','')}",
                "start_date": start, "end_date_inclusive": end, "qualified_pixel_count": count,
                "processing_scale_m": 250, "geometry_file": f"event_{eid}.geojson", "raster_file": f"event_{eid}.tif",
                "download": {"retrieved_at": "2026-10-03T00:00:00+00:00"}})
        manifest = {"version": VERSION, "source_id": SOURCE_ID, "boundary_id": BOUNDARY_ID,
                    "extent_semantics": "historical_event_window_maximum_not_daily_occurrence",
                    "sources": {SOURCE_ID: {"license": "CC BY-NC 4.0; attribution and non-commercial use required"},
                                "WM/geoLab/geoBoundaries/600/ADM2": {"license": "CC BY 4.0"}},
                    "events": event_records,
                    "files": {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in directory.iterdir()}}
        (directory / "manifest.json").write_text(json.dumps(manifest))
        app.dependency_overrides[get_historical_store] = lambda: HistoricalStore(directory)
        try:
            yield TestClient(app), directory
        finally:
            app.dependency_overrides.pop(get_historical_store, None)


def test_catalogue_contract_attribution_dates_and_historical_semantics(isolated_api):
    client, _ = isolated_api
    response = client.get("/api/historical-floods")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available" and body["dataset_version"] == VERSION
    assert [e["event_id"] for e in body["events"]] == [2728,3551]
    assert body["events"][0]["start_date"] == "2005-09-14"
    assert body["events"][1]["end_date_inclusive"] == "2009-10-12"
    assert body["source"]["license"] == "CC BY-NC 4.0"
    assert "Not current flooding" in body["notice"]
    assert body["boundary"]["properties"]["shapeID"] == BOUNDARY_ID


@pytest.mark.parametrize("eid,count", [(2728,33),(3551,23)])
def test_event_returns_original_geojson_without_spatial_approximation(isolated_api, eid, count):
    client, directory = isolated_api
    response = client.get(f"/api/historical-floods/{eid}")
    assert response.status_code == 200
    body = response.json()
    assert body["floodwater"] == json.loads((directory / f"event_{eid}.geojson").read_text())
    assert len(body["floodwater"]["features"]) == count
    assert body["event"]["qualified_pixel_count"] == count
    assert body["event"]["processing_scale_m"] == 250
    assert "maximum_not_daily" in body["event"]["extent_semantics"]


@pytest.mark.parametrize("eid", [2049,9999])
def test_unreviewed_events_are_unavailable_and_not_negative_labels(isolated_api,eid):
    client, _ = isolated_api
    response = client.get(f"/api/historical-floods/{eid}")
    assert response.status_code == 404
    assert response.json()["status"] == "unavailable"
    assert "floodwater" not in response.json()


def test_missing_dataset_is_explicitly_unavailable(isolated_api):
    client, directory = isolated_api
    (directory / "manifest.json").unlink()
    response = client.get("/api/historical-floods")
    assert response.status_code == 503
    assert "No flood-absence conclusion" in response.json()["message"]
    assert response.json()["source"]["license"] == "CC BY-NC 4.0"


def test_corrupt_geometry_fails_closed_without_stale_map(isolated_api):
    client, directory = isolated_api
    (directory / "event_2728.geojson").write_text("{}")
    response = client.get("/api/historical-floods/2728")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "floodwater" not in response.json()


@pytest.mark.parametrize("field,value", [("qualified_pixel_count",34),("processing_scale_m",30),("start_date","2005-09-15")])
def test_metadata_disagreement_does_not_serve_a_map(isolated_api, field, value):
    client, directory = isolated_api
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["events"][0][field] = value
    path.write_text(json.dumps(manifest))
    assert client.get("/api/historical-floods/2728").status_code == 503
