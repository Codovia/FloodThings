"""Controlled fixtures only in temporary directories; inherited socket guard blocks live data."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
from affine import Affine
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.drainage import DrainageStore, get_store
from app.main import app

SCRIPT = Path(__file__).resolve().parents[2]/"scripts/extract_udupi_drainage.py"
spec = importlib.util.spec_from_file_location("drainage_extraction", SCRIPT)
gis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gis)


def discovery():
    return {"endpoint": gis.OVERPASS, "query": gis.PLACE_QUERY, "retrieved_at": "2026-10-03T00:00:00Z",
            "response": {"elements": [{"type": "node", "id": gis.PLACE_ID, "lat": 13.3419169, "lon": 74.7473232,
                                       "version": 1, "timestamp": "2026-01-01T00:00:00Z", "tags": {"name": "Udupi", "place": "city"}}]}}


def fixture_download(ee, session, staged, study, source):
    dem = source == gis.DEM
    params = gis.grid(study, 30 if dem else 10, 1 if dem else 0)
    width, height = params["dimensions"]
    bands = gis.DEM_BANDS if dem else ["Map"]
    values = np.ones((len(bands), height, width), dtype="float32")
    if dem:
        rows, cols = np.indices((height, width))
        values[0] = 3 + rows*0.1 + cols*0.2
        values[0, 10, 10] = gis.NODATA
        values[1, 20, 20] = 0  # Source quality void must invalidate the DSM, not become zero elevation.
        values[2] = 2
        values[3] = 0.5
        values[4] = 0
    else:
        values[0] = 10
        values[0, 0, 0] = 0  # Undefined land cover is unknown.
        values[0, 0, 1] = gis.NODATA
        values[0, 0, 2] = 50
    name = "dem_source.tif" if dem else "landcover_source.tif"
    with rasterio.open(staged/name, "w", driver="GTiff", height=height, width=width, count=len(bands), dtype="float32",
                       crs=gis.CRS, transform=Affine(*params["crs_transform"])) as dst:
        dst.write(values)
    index = "N13_00_E074_00" if dem else "2021"
    return {"source_id": source, "image_ids": [f"{source}/{index}"], "source_properties": {"system:index": index},
            "native_projection": {"crs": "EPSG:4326"}, "download_parameters": {**params, "bands": bands},
            "download": {"retrieved_at": "2026-10-03T00:00:00Z"}}


@pytest.fixture
def local_gis(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        boundary_dir = root/"data/processed/udupi_flood_spatial_v1"
        boundary_dir.mkdir(parents=True)
        # A controlled containment fixture, never a production geographic boundary.
        gis.write_json(boundary_dir/"udupi_boundary.geojson", {"type": "Feature", "properties": {"shapeID": gis.history.BOUNDARY_SHAPE_ID},
            "geometry": {"type": "Polygon", "coordinates": [[[74.6,13.2],[74.9,13.2],[74.9,13.5],[74.6,13.5],[74.6,13.2]]]}})
        monkeypatch.setattr(gis, "ROOT", root)
        monkeypatch.setattr(gis.verification, "probe_access", lambda *args: {"initialization": "controlled_fixture"})
        monkeypatch.setattr(gis, "source_download", fixture_download)
        monkeypatch.setattr(gis, "overpass", lambda session, query: {
            "endpoint": gis.OVERPASS, "query": query, "retrieved_at": "2026-10-03T00:00:00Z",
            "response": {"osm3s": {"timestamp_osm_base": "2026-10-02T23:00:00Z"}, "elements": []}})
        directory = root/gis.VERSION
        directory.mkdir()
        gis.extract(MagicMock(), MagicMock(), directory, discovery())
        app.dependency_overrides[get_store] = lambda: DrainageStore(directory)
        try:
            yield directory
        finally:
            app.dependency_overrides.pop(get_store, None)


def file_snapshot(directory):
    return {p.name: (p.read_bytes(), gis.history.checksum(p), p.stat().st_mtime_ns) for p in directory.iterdir() if p.is_file()}


def edit_manifest(directory, edit):
    path = directory/"manifest.json"
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))


def test_study_window_geometry_crs_and_real_point_definition(local_gis):
    study = gis.study_area(discovery())
    assert study["properties"]["official_municipal_boundary"] is False
    assert study["properties"]["definition_crs"] == "EPSG:32643"
    assert study["properties"]["anchor_osm_node_id"] == gis.PLACE_ID
    bounds = study["properties"]["projected_bounds"]
    assert bounds[2]-bounds[0] == bounds[3]-bounds[1] == 3000
    assert shape(study["geometry"]).is_valid
    assert len(study["geometry"]["coordinates"][0]) == 65
    wrong = discovery()
    wrong["response"]["elements"][0]["id"] = 1
    with pytest.raises(ValueError, match="anchor unavailable"):
        gis.study_area(wrong)


def test_horn_slope_uses_metric_neighbours_and_propagates_unknowns():
    _, x = np.indices((5, 5))
    heights = x.astype("float32")*30
    assert np.allclose(gis.horn_slope(heights), 45)
    heights[2, 2] = gis.NODATA
    assert np.all(gis.horn_slope(heights) == gis.NODATA)
    heights[2, 2] = np.nan
    assert np.all(gis.horn_slope(heights) == gis.NODATA)
    assert np.array_equal(gis.horn_slope(np.zeros((3, 3))), [[0]])  # Genuine flat zero height is valid.


def test_raster_nodata_quality_masks_classes_and_reproducible_previews(local_gis):
    result = gis.validate_version(local_gis)
    assert result["layers"]["elevation"]["missing_pixels"] == 2
    assert result["layers"]["slope"]["missing_pixels"] == 18
    assert result["layers"]["land_cover"]["missing_pixels"] == 2
    with rasterio.open(local_gis/"elevation.tif") as src:
        assert src.crs.to_epsg() == 32643 and src.nodata == -9999
        assert src.read(1)[9, 9] == -9999
    rgba, meta = gis.preview_data(local_gis/"land_cover.tif", "land_cover")
    assert np.any(rgba[3] == 0) and np.any(rgba[3] == 255)
    assert meta["preview_crs"] == "EPSG:3857"
    assert {v["value"] for v in meta["legend"]} == {10, 50}


def test_validation_and_api_preserve_exact_bytes_hashes_and_mtimes(local_gis):
    before = file_snapshot(local_gis)
    gis.validate_version(local_gis)
    store = DrainageStore(local_gis)
    assert store.load()[0]["status"] == "available"
    client = TestClient(app)
    assert client.get('/api/drainage-research').status_code == 200
    assert client.get('/api/drainage-research/layers/elevation.png').status_code == 200
    assert file_snapshot(local_gis) == before
    assert gis.main(["--output", str(local_gis)]) == 2
    with pytest.raises(FileExistsError):
        gis.write_raster(local_gis/"extra.tif", np.zeros((2, 2)), {}, "fixture")
    assert file_snapshot(local_gis) == before


@pytest.mark.parametrize('kind', ['checksum', 'source', 'image_id', 'crs', 'bounds', 'nodata', 'geometry', 'parameters', 'class_counts'])
def test_validation_rejects_corrupt_identity_geometry_and_parameters(local_gis, kind):
    if kind == 'checksum':
        (local_gis/"elevation.tif").write_bytes(b"corrupt fixture")
    else:
        def change(m):
            if kind == 'source': m['sources'][gis.LAND]['license'] = 'unverified'
            elif kind == 'image_id': m['landcover']['image_ids'] = [gis.LAND+'/2020']
            elif kind == 'crs': m['layers']['slope']['crs'] = 'EPSG:4326'
            elif kind == 'bounds': m['layers']['slope']['preview_bounds'] = [[0,0],[1,1]]
            elif kind == 'nodata': m['layers']['elevation']['nodata'] = 0
            elif kind == 'geometry': m['study']['official_municipal_boundary'] = True
            elif kind == 'parameters': m['dem']['download_parameters']['crs_transform'][0] = 10
            elif kind == 'class_counts': m['layers']['land_cover']['class_counts']['50'] = 99
        edit_manifest(local_gis, change)
    with pytest.raises(ValueError):
        gis.validate_version(local_gis)


def test_osm_geometry_clips_actual_line_and_retains_identity(local_gis):
    study = gis.study_area(discovery())
    y = study['properties']['anchor_lon_lat'][1]
    item = {"endpoint": gis.OVERPASS, "query": gis.drain_query(study), "retrieved_at": "2026-10-03T00:00:00Z",
            "response": {"osm3s": {"timestamp_osm_base": "2026-10-03T00:00:00Z"}, "elements": [{
                "type": "way", "id": 123, "version": 2, "timestamp": "2026-01-01T00:00:00Z", "tags": {"waterway": "ditch"},
                "geometry": [{"lon": 74.70, "lat": y}, {"lon": 74.80, "lat": y}]}]}}
    geometry, details = gis.mapped_drains(item, study)
    assert details['feature_count'] == 1 and details['ditch_count'] == 1 and details['drain_count'] == 0
    assert 2990 < details['clipped_length_m'] < 3010
    line = shape(geometry['features'][0]['geometry'])
    assert line.difference(shape(study['geometry'])).length < 1e-12
    assert geometry['features'][0]['properties']['osm_id'] == 123
    assert geometry['features'][0]['properties']['capacity_status'] == 'unknown'
    item['response']['elements'][0].pop('geometry')
    with pytest.raises(ValueError, match='geometry missing'):
        gis.mapped_drains(item, study)


def test_overpass_server_remark_never_becomes_empty_coverage():
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.iter_content.return_value = [json.dumps({'elements': [], 'remark': 'runtime error: timeout'}).encode()]
    with pytest.raises(ValueError, match='Incomplete Overpass'):
        gis.overpass(session, 'controlled-query')
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs['timeout'] == (5,15)


def test_api_contract_source_attribution_unknown_drains_and_actual_png(local_gis):
    client = TestClient(app)
    body = client.get('/api/drainage-research').json()
    assert body['dataset_version'] == gis.VERSION
    assert body['study_area']['properties']['official_municipal_boundary'] is False
    assert body['osm']['status'] == 'no_mapped_features'
    assert body['mapped_drains']['features'] == []
    assert 'unknown' in body['notice'] and 'risk' in body['notice']
    assert body['sources'][gis.LAND]['license'] == 'CC BY 4.0'
    assert body['sources']['OpenStreetMap']['license'] == 'ODbL 1.0'
    assert 'do not incur any liability' in body['sources'][gis.DEM]['liability_notice']
    response = client.get('/api/drainage-research/layers/land_cover.png')
    assert response.headers['content-type'] == 'image/png'
    assert response.content == (local_gis/'land_cover.png').read_bytes()
    assert client.get('/api/drainage-research/layers/risk.png').status_code == 404


@pytest.mark.parametrize('failure', ['missing', 'checksum', 'bounds'])
def test_api_unavailable_instead_of_replacement_layers(local_gis, failure):
    if failure == 'missing': (local_gis/'manifest.json').unlink()
    elif failure == 'checksum': (local_gis/'slope.png').write_bytes(b'broken')
    else: edit_manifest(local_gis, lambda m: m['layers']['slope'].update(preview_bounds=[[0,0],[1,1]]))
    client = TestClient(app)
    for url in ('/api/drainage-research', '/api/drainage-research/layers/slope.png'):
        response = client.get(url)
        assert response.status_code == 503 and response.json()['status'] == 'unavailable'
        assert 'unknown' in response.json()['notice']


def test_dem_query_filters_geometry_and_real_tile_id_before_mosaicking(local_gis, monkeypatch):
    # Inspect the real adapter graph with mocks; download only into this disposable directory.
    ee, session = MagicMock(), MagicMock()
    collection = ee.ImageCollection.return_value.filterBounds.return_value.filter.return_value
    collection.size.return_value.getInfo.return_value = 1
    sorted_collection = collection.sort.return_value
    sorted_collection.aggregate_array.return_value.getInfo.return_value = [gis.DEM+'/N13_00_E074_00']
    first = ee.Image.return_value.select.return_value
    first.select.return_value.projection.return_value.getInfo.return_value = {'crs': 'EPSG:4326'}
    first.toDictionary.return_value.getInfo.return_value = {'system:index': 'N13_00_E074_00'}
    product = sorted_collection.mosaic.return_value.setDefaultProjection.return_value.select.return_value.toFloat.return_value.reproject.return_value.clip.return_value.unmask.return_value
    product.getDownloadURL.return_value = 'https://earthengine.googleapis.com/controlled-test'
    # Recover the actual function, since the extraction fixture replaces it.
    fresh_spec = importlib.util.spec_from_file_location('controlled_adapter', SCRIPT)
    adapter = importlib.util.module_from_spec(fresh_spec)
    fresh_spec.loader.exec_module(adapter)
    monkeypatch.setattr(adapter.spatial, 'bounded_download', lambda *args: {'retrieved_at': 'controlled'})
    result = adapter.source_download(ee, session, local_gis, gis.study_area(discovery()), gis.DEM)
    ee.ImageCollection.return_value.filterBounds.assert_called_once()
    ee.Filter.inList.assert_called_once_with('system:index', ['N13_00_E074_00'])
    sorted_collection.mosaic.assert_called_once()
    assert result['download_parameters']['dimensions'] == [102,102]
    assert result['download_parameters']['bands'] == gis.DEM_BANDS
