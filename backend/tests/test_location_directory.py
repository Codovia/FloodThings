"""Controlled directory fixtures in temporary storage; no external geocoder or DB."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import pytest

from app.locations import VERSION, LocationStore, LocationsUnavailable, get_store, validate_directory
from app.main import app


def directory():
    district = {'id': 'nic:udupi.nic.in', 'name': 'Udupi', 'source_name': 'Udupi', 'aliases': [], 'source_website': 'https://udupi.nic.in',
                'source_url': 'https://igod.gov.in/sg/KA/E042/organizations', 'identity_status': 'nic_name_current_lgd_unresolved',
                'current_lgd_code': None, 'representative_point': None, 'navigation_bounds': [[13, 74], [14, 75]],
                'navigation_source': {'license': 'CC BY 4.0', 'id': 'WM/geoLab/geoBoundaries/600/ADM2'}}
    other = {**district, 'id': 'nic:other.nic.in', 'name': 'Other fixture district', 'source_name': 'Other fixture district', 'source_website': 'https://other.nic.in', 'navigation_bounds': None, 'navigation_source': None}
    def locality(node, name):
        return {'id': f'osm:node:{node}', 'name': name, 'aliases': ['Controlled alias'], 'district_id': district['id'],
                'association_status': 'official_district_record_cross_checked', 'association_source_url': 'https://udupi.nic.in/en/municipal-administration/',
                'coordinate_status': 'verified_osm_place_point', 'selectable': True, 'coordinates': {'crs': 'EPSG:4326', 'latitude': 13.5, 'longitude': 74.5},
                'containment_status': 'within_public_geoboundaries_district', 'coordinate_source': {'source_type': 'OpenStreetMap', 'license': 'ODbL 1.0', 'node_id': node,
                    'url': f'https://www.openstreetmap.org/node/{node}', 'version': 1, 'retrieved_at': '2026-10-08T00:00:00Z', 'response_sha256': 'a' * 64}}
    missing = {**locality(3, 'Name-only fixture'), 'coordinates': None, 'coordinate_status': 'unavailable', 'selectable': False, 'coordinate_source': None}
    return {'version': VERSION, 'state_name': 'Karnataka', 'districts': [other, district], 'localities': [locality(1, 'Same name'), locality(2, 'Same name'), missing]}


def write(directory_path, data):
    raw = (json.dumps(data) + '\n').encode()
    (directory_path / 'directory.json').write_bytes(raw)
    (directory_path / 'manifest.json').write_text(json.dumps({'version': VERSION, 'district_count': len(data['districts']), 'locality_count': len(data['localities']),
          'files': {'directory.json': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}}))


@pytest.fixture
def api():
    with TemporaryDirectory() as temporary:
        path = Path(temporary); write(path, directory())
        app.dependency_overrides[get_store] = lambda: LocationStore(path)
        try:
            yield TestClient(app), path
        finally:
            app.dependency_overrides.pop(get_store, None)


def test_districts_deterministic_source_ids_no_weather_points(api):
    client, _ = api
    rows = client.get('/api/locations/districts').json()['items']
    assert [r['name'] for r in rows] == ['Other fixture district', 'Udupi']
    assert rows[1]['id'] == 'nic:udupi.nic.in'
    assert all(r['representative_point'] is None and r['current_lgd_code'] is None for r in rows)


def test_district_and_locality_search_with_alias_and_duplicate_names(api):
    client, _ = api
    assert client.get('/api/locations/districts?q=UDUPI').json()['total'] == 1
    body = client.get('/api/locations/search?q=Controlled%20alias').json()
    assert body['total'] == 3
    rows = client.get('/api/locations/localities?district_id=nic:udupi.nic.in&q=Same').json()['items']
    assert [r['id'] for r in rows] == ['osm:node:1', 'osm:node:2']
    assert all(r['district_id'] == 'nic:udupi.nic.in' for r in rows)


def test_district_filter_and_empty_search(api):
    client, _ = api
    assert client.get('/api/locations/localities?district_id=nic:other.nic.in').json()['items'] == []
    assert client.get('/api/locations/search?q=missing').json()['total'] == 0
    assert client.get('/api/locations/search?q=Same&district_id=nic:other.nic.in').json()['total'] == 0


def test_coordinates_are_source_verified_and_missing_not_selectable(api):
    client, _ = api
    row = client.get('/api/locations/localities/osm:node:1').json()
    assert row['coordinates'] == {'crs': 'EPSG:4326', 'latitude': 13.5, 'longitude': 74.5}
    assert row['coordinate_source']['license'] == 'ODbL 1.0'
    row = client.get('/api/locations/localities/osm:node:3').json()
    assert row['coordinates'] is None and row['selectable'] is False


@pytest.mark.parametrize('url,status', [('/api/locations/localities?district_id=bad',404),('/api/locations/localities/bad',404),
    ('/api/locations/search?q=Same&district_id=bad',404),('/api/locations/search?q=%20%20',422),('/api/locations/search',422),
    ('/api/locations/districts?limit=51',422),('/api/locations/districts?offset=-1',422),('/api/locations/localities',422),
    ('/api/locations/search?q=' + 'a' * 101,422)])
def test_input_validation_and_unknown_identity(api, url, status):
    assert api[0].get(url).status_code == status


def test_pagination_stable_and_bounded(api):
    client, _ = api
    a = client.get('/api/locations/search?q=Same&limit=1&offset=0').json()
    b = client.get('/api/locations/search?q=Same&limit=1&offset=1').json()
    assert a['total'] == b['total'] == 2 and a['items'][0]['id'] != b['items'][0]['id']


@pytest.mark.parametrize('mutation', ['restricted', 'unverified', 'nonfinite', 'outside', 'missing_selectable', 'conflict', 'guessed_lgd', 'guessed_district_point', 'unverified_association'])
def test_rejects_restricted_unverified_and_conflicting_records(mutation):
    data = directory(); row = data['localities'][0]
    if mutation == 'restricted': row['coordinate_source']['source_type'] = 'Survey of India'
    if mutation == 'unverified': row['coordinate_status'] = 'name_match_only'
    if mutation == 'nonfinite': row['coordinates']['latitude'] = float('nan')
    if mutation == 'outside': row['coordinates']['latitude'] = 20
    if mutation == 'missing_selectable': row['coordinates'] = None
    if mutation == 'conflict': data['localities'][1]['id'] = row['id']
    if mutation == 'guessed_lgd': data['districts'][0]['current_lgd_code'] = 123
    if mutation == 'guessed_district_point': data['districts'][0]['representative_point'] = {'latitude': 13, 'longitude': 74}
    if mutation == 'unverified_association': row['association_status'] = 'fuzzy_name_match'
    with pytest.raises(LocationsUnavailable): validate_directory(data)


def test_corrupt_or_missing_store_is_explicit_unavailable(api):
    client, path = api
    (path / 'directory.json').write_text('{}')
    assert client.get('/api/locations/districts').status_code == 503
    (path / 'manifest.json').unlink()
    assert client.get('/api/locations/search?q=Same').status_code == 503


def test_validation_and_search_preserve_exact_bytes_hashes_and_mtime(api):
    client, path = api
    snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.iterdir()}
    for url in ['/api/locations/districts', '/api/locations/search?q=Same', '/api/locations/localities?district_id=nic:udupi.nic.in']:
        assert client.get(url).status_code == 200
    assert LocationStore(path).load() == directory()
    assert snapshot == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.iterdir()}


def test_completed_version_is_never_overwritten(api):
    spec = importlib.util.spec_from_file_location('location_builder', Path(__file__).resolve().parents[2] / 'scripts/build_location_directory.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with pytest.raises(FileExistsError): module.build(api[1])
