"""Sprint 11 only serves previously reviewed public spatial products, offline."""
import copy
import json
import math
from pathlib import Path
import pytest

from app.main import app
from app.locations import get_store, LocationStore
from app.flood_map import validate_geometry, UDUPI, get_drainage_store
from app.historical import HistoricalUnavailable
from test_historical_api import isolated_api


@pytest.fixture
def map_api(isolated_api):
    client, directory = isolated_api
    # Public committed directory is read-only; all writes go to isolated fixture.
    store = LocationStore()
    app.dependency_overrides[get_store] = lambda: store
    try:
        yield client, directory
    finally:
        app.dependency_overrides.pop(get_store, None)
        app.dependency_overrides.pop(get_drainage_store, None)


def test_all_31_district_names_stable_identifiers_and_bounds(map_api):
    client, _ = map_api
    body = client.get('/api/flood-map/districts').json()
    expected = LocationStore().load()['districts']
    assert body['total'] == 31
    assert {r['id']: r['name'] for r in body['items']} == {r['id']: r['name'] for r in expected}
    assert all(r['current_lgd_code'] is None for r in body['items'])
    assert sum(r['navigation_bounds'] is not None for r in body['items']) == 2
    assert [r['name'] for r in body['items'] if r['historical_features']] == ['Udupi']


def test_original_polygons_provenance_stable_ids_and_unknown_mechanism(map_api):
    client, directory = map_api
    body = client.get('/api/flood-map/historical').json()
    assert body['total'] == 56 and body['coverage']['historical_events'] == 2
    assert len({f['id'] for f in body['geojson']['features']}) == 56
    for event_id in (2728, 3551):
        originals = json.loads((directory / f'event_{event_id}.geojson').read_text())['features']
        features = [f for f in body['geojson']['features'] if f['properties']['event_id'] == event_id]
        assert [f['geometry'] for f in features] == [f['geometry'] for f in originals]
        for f, original in zip(features, originals):
            assert all(f['properties'][k] == v for k,v in original['properties'].items())
            p = f['properties']
            assert p['place_name'] is None and p['mechanism']['mechanisms'] == ['unknown']
            assert p['mechanism']['supporting_source'] is None
            assert p['source']['license'] == 'CC BY-NC 4.0'
            assert len(p['source_geometry_sha256']) == 64
            assert p['geometry_crs'] == 'OGC:CRS84' and p['processing_grid_m'] == 250
            assert p['category'] == 'historical_observed_floodwater'
            assert 'not_daily_occurrence' in p['limitations'] or 'Does not establish flooding on every event date' in p['limitations']


def test_district_filter_and_statewide_reset_without_false_negative(map_api):
    client,_ = map_api
    assert client.get('/api/flood-map/historical', params={'district_id':UDUPI}).json()['total'] == 56
    empty = client.get('/api/flood-map/historical',params={'district_id':'nic:kolar.nic.in'}).json()
    assert empty['geojson']['features'] == [] and empty['boundary'] is None
    assert empty['coverage']['absence_interpretation'] == 'unknown_not_verified_non_flood'
    assert client.get('/api/flood-map/historical').json()['total'] == 56


@pytest.mark.parametrize('route',['historical','hazards','drainage'])
def test_unknown_district_rejected_without_name_substitution(map_api,route):
    assert map_api[0].get('/api/flood-map/'+route,params={'district_id':'unknown'}).status_code == 404


@pytest.mark.parametrize('params',[{'limit':201},{'limit':0},{'offset':-1},{'district_id':''},{'event_id':0}])
def test_request_bounds(map_api,params):
    assert map_api[0].get('/api/flood-map/historical',params=params).status_code == 422


def test_event_filter_and_bounded_pagination(map_api):
    client,_=map_api
    body=client.get('/api/flood-map/historical',params={'event_id':3551,'offset':1,'limit':2}).json()
    assert body['total']==23 and len(body['geojson']['features'])==2
    assert all(f['properties']['event_id']==3551 for f in body['geojson']['features'])
    assert client.get('/api/flood-map/historical',params={'event_id':2698}).status_code==404


def test_hazard_layer_never_duplicates_historical_or_context_geometry(map_api):
    body=map_api[0].get('/api/flood-map/hazards',params={'district_id':UDUPI}).json()
    assert body['category']=='potential_hazard' and body['status']=='unavailable'
    assert body['total']==0 and body['geojson']['features']==[] and body['source'] is None
    assert 'No verified potential' in body['message']


def test_details_exact_feature_and_separate_environmental_context(map_api):
    client,_=map_api
    feature=client.get('/api/flood-map/historical').json()['geojson']['features'][0]
    body=client.get('/api/flood-map/features/'+feature['id']).json()
    assert body['feature']==feature
    assert body['drainage_context']['overflow_assessment']=='not_validated'
    assert 'not a verified locality' in body['environmental_context']
    assert client.get('/api/flood-map/features/gfd:9999:r0:c0').status_code==404
    assert client.get('/api/flood-map/features/soi:geometry').status_code==404


def test_corruption_fails_closed_and_coverage_does_not_claim_zero(map_api):
    client,directory=map_api
    (directory/'event_2728.geojson').write_text('{}')
    assert client.get('/api/flood-map/historical').status_code==503
    coverage=client.get('/api/flood-map/districts').json()
    assert coverage['historical_status']=='unavailable'
    assert next(r for r in coverage['items'] if r['id']==UDUPI)['historical_features'] is None


def test_drainage_is_bounded_context_only(map_api):
    class Context:
        def load(self):
            return {'status':'available','mapped_drains':{'type':'FeatureCollection','features':[]},'osm':{'feature_count':0}}, {}
    app.dependency_overrides[get_drainage_store]=lambda:Context()
    client,_=map_api
    body=client.get('/api/flood-map/drainage',params={'district_id':UDUPI}).json()
    assert body['overflow_assessment']=='not_validated' and body['category']=='drainage_context'
    assert 'does not mean no drains' in body['coverage_notice']
    assert client.get('/api/flood-map/drainage',params={'district_id':'nic:kolar.nic.in'}).json()['status']=='unavailable'


@pytest.mark.parametrize('value',[math.nan,math.inf,181,True])
def test_invalid_crs84_longitude_excluded(value):
    with pytest.raises(HistoricalUnavailable):
        validate_geometry({'type':'Polygon','coordinates':[[[value,13],[75,13],[75,14],[value,13]]]})


@pytest.mark.parametrize('geometry',[{'type':'Point','coordinates':[74,13]}, {'type':'Polygon','coordinates':[]}, {'type':'Polygon','coordinates':[[[74,13],[75,13],[75,14],[74,14]]]}])
def test_points_empty_or_unclosed_rings_are_not_substituted(geometry):
    with pytest.raises(HistoricalUnavailable):validate_geometry(geometry)


def test_license_and_restricted_boundary_fail_closed(map_api):
    client,directory=map_api
    manifest=directory/'manifest.json'
    body=json.loads(manifest.read_text());body['sources']['WM/geoLab/geoBoundaries/600/ADM2']['license']='SOI unresolved'
    manifest.write_text(json.dumps(body))
    assert client.get('/api/flood-map/historical').status_code==503


def test_location_backend_outage_has_no_hidden_file_fallback(map_api):
    from app.locations import LocationsUnavailable
    class Broken:
        def load(self):raise LocationsUnavailable('Database unavailable')
    app.dependency_overrides[get_store]=lambda:Broken()
    assert map_api[0].get('/api/flood-map/districts').status_code==503
