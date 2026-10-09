"""Public v2 contracts, with temporary stores and no network/database access."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import pytest
from app.locations import DATASET, LocationStore, LocationsUnavailable, get_store, validate_directory
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


def records():
    return json.loads((DATASET / 'directory.json').read_bytes())


@pytest.fixture
def api_v2():
    with TemporaryDirectory() as temporary:
        path = Path(temporary)
        for name in ('directory.json', 'manifest.json'):
            (path / name).write_bytes((DATASET / name).read_bytes())
        app.dependency_overrides[get_store] = lambda: LocationStore(path)
        try:
            yield TestClient(app), path
        finally:
            app.dependency_overrides.pop(get_store, None)


def test_version_coverage_and_provenance(api_v2):
    client, _ = api_v2
    body = client.get('/api/locations/districts').json()
    assert body['dataset_version'] == 'karnataka_location_directory_v2'
    assert body['total'] == 31
    assert body['coverage'] == {'district_names': 31, 'districts_with_selectable_localities': 2, 'selectable_localities': 5, 'name_only_localities': 1}
    data = records()
    assert all(d['current_lgd_code'] is None and d['representative_point'] is None for d in data['districts'])
    for row in data['localities']:
        assert row['association_source_url'].startswith('https://')
        if row['selectable']:
            assert row['coordinate_source']['license'] == 'ODbL 1.0'
            assert len(row['coordinate_source']['response_sha256']) == 64
    manifest = json.loads((DATASET / 'manifest.json').read_bytes())
    assert manifest['soi_used'] is False and manifest['previous_version'] == 'karnataka_location_directory_v1'
    assert all(len(r['sha256']) == 64 for r in manifest['inputs'])


@pytest.mark.parametrize('identity,name,district,point', [
    ('udupi-admin:municipality:kundapur', 'Kundapur', 'nic:udupi.nic.in', (13.6250993, 74.6915722)),
    ('osm:node:245622058', 'Saligrama', 'nic:udupi.nic.in', (13.4977795, 74.7112560)),
    ('osm:node:245612641', 'Mangaluru', 'nic:dk.nic.in', (12.8698101, 74.8430082))])
def test_new_points_exact_source_coordinates(api_v2, identity, name, district, point):
    row = api_v2[0].get('/api/locations/localities/' + identity).json()
    assert row['name'] == name and row['district_id'] == district and row['selectable'] is True
    assert (row['coordinates']['latitude'], row['coordinates']['longitude']) == point
    assert row['coordinates']['crs'] == 'EPSG:4326' and 'mapped settlement point' in row['coordinate_meaning']


def test_kundapur_preserves_identity_and_verified_alias(api_v2):
    client, _ = api_v2
    canonical = client.get('/api/locations/localities/udupi-admin:municipality:kundapur').json()
    assert client.get('/api/locations/localities/osm:node:245623778').json() == canonical
    assert canonical['source_name'] == 'Kundapura' and canonical['source_place_type'] == 'town'
    assert client.get('/api/locations/search?q=Kundapura').json()['items'][0]['id'] == canonical['id']


def test_alias_search_and_district_filter(api_v2):
    client, _ = api_v2
    assert client.get('/api/locations/search?q=Mangalore').json()['items'][0]['id'] == 'osm:node:245612641'
    assert client.get('/api/locations/search?q=Mangalore&district_id=nic:udupi.nic.in').json()['total'] == 0
    body = client.get('/api/locations/localities?district_id=nic:dk.nic.in').json()
    assert [r['name'] for r in body['items']] == ['Mangaluru']
    assert [r['name'] for r in client.get('/api/locations/localities?district_id=nic:udupi.nic.in').json()['items']] == ['Karkala', 'Kaup', 'Kundapur', 'Saligrama', 'Udupi']


def test_disabled_kaup_never_supplies_a_point(api_v2):
    row = api_v2[0].get('/api/locations/localities/udupi-admin:municipality:kaup').json()
    assert row['selectable'] is False and row['coordinates'] is None
    assert 'not reviewed' in row['unavailable_reason']


@pytest.mark.parametrize('mutation', ['alias_conflict', 'coverage', 'restricted', 'missing', 'wrong_district'])
def test_v2_rejects_conflicts_and_unverified_data(mutation):
    data = records()
    row = next(r for r in data['localities'] if r['name'] == 'Mangaluru')
    if mutation == 'alias_conflict': row['identifier_aliases'] = ['udupi-admin:municipality:kundapur']
    if mutation == 'coverage': data['coverage']['selectable_localities'] = 999
    if mutation == 'restricted': row['coordinate_source']['license'] = 'SOI permission unresolved'
    if mutation == 'missing': row['coordinates'] = None
    if mutation == 'wrong_district': row['district_id'] = 'nic:udupi.nic.in'
    with pytest.raises(LocationsUnavailable): validate_directory(data)


def test_duplicate_names_remain_distinct_by_id_and_district(api_v2):
    data = records()
    first = next(r for r in data['localities'] if r['name'] == 'Saligrama')
    other = next(r for r in data['localities'] if r['name'] == 'Mangaluru')
    other['name'] = first['name']
    assert validate_directory(data)
    from app.locations import matching
    rows = matching(data['localities'], 'Saligrama')
    assert len(rows) == 2 and len({r['id'] for r in rows}) == 2 and len({r['district_id'] for r in rows}) == 2


def test_v1_readability_original_kundapur_and_byte_preservation():
    folder = ROOT / 'data/reference/karnataka_location_directory_v1'
    snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    data = LocationStore(folder).load()
    assert sum(r['selectable'] for r in data['localities']) == 2
    assert next(r for r in data['localities'] if r['name'] == 'Kundapur')['coordinates'] is None
    assert hashlib.sha256((folder / 'directory.json').read_bytes()).hexdigest() == '991026f0ef8f6d7370984609f84466b532d27b529e4cf3362e1c401e2cb5e274'
    assert snapshot == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}


def test_read_only_v2_search_and_immutable_builder(api_v2):
    client, path = api_v2
    snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.iterdir()}
    for url in ('/api/locations/search?q=Kundapura', '/api/locations/districts', '/api/locations/localities?district_id=nic:dk.nic.in'):
        assert client.get(url).status_code == 200
    assert snapshot == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.iterdir()}
    spec = importlib.util.spec_from_file_location('expand_locations', ROOT / 'scripts/expand_location_directory.py')
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    try:
        spec.loader.exec_module(module)
        with pytest.raises(FileExistsError): module.build(path)
    finally:
        sys.path.remove(str(ROOT / 'scripts'))
