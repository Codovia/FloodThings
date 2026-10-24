"""Administrator entrance lookup — TEST FIXTURES ONLY (invented polygon, places and addresses)."""
import asyncio

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import admin_place
from app.admin_place import PlaceLookup, compose_address
from app.official import OfficialService
from app.shelters import authorized

NOW = 1_760_000_000.0
UDUPI = {'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': [[[[74.5, 13.2], [75.0, 13.2], [75.0, 13.8], [74.5, 13.8], [74.5, 13.2]]]]},
         'properties': {'District': 'UDUPI', 'STATE': 'KARNATAKA', 'Date': '2026-10-16', 'UTC': '0800', 'Day_1': '1', 'Day1_Color': 4}}
HALL = {'category': 'amenity', 'type': 'community_centre', 'name': 'TEST Community Hall', 'lat': '13.35020', 'lon': '74.78010',
        'address': {'amenity': 'TEST Community Hall', 'road': 'Test Road', 'suburb': 'Indrali', 'town': 'Manipal',
                    'state_district': 'Udupi', 'state': 'Karnataka', 'postcode': '576101', 'country_code': 'in'}}
ROAD = {'category': 'highway', 'type': 'primary', 'name': 'Test Main Road', 'lat': '13.3501', 'lon': '74.7801', 'address': {'road': 'Test Main Road', 'town': 'Manipal', 'state_district': 'Udupi', 'state': 'Karnataka'}}


def make(place=HALL, nominatim_status=200, imd_status=200, authorize=True, address_place=None):
    seen = []

    def handler(request):
        if request.url.host == 'nominatim.openstreetmap.org':
            seen.append(request)
            body = place if request.url.params.get('layer') == 'poi' or address_place is None else address_place
            return httpx.Response(nominatim_status, json=body)
        if request.url.host == 'reactjs.imd.gov.in':
            return httpx.Response(imd_status, json={'type': 'FeatureCollection', 'features': [UDUPI]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    clock = {'t': NOW}
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds); clock['t'] += seconds

    app = FastAPI()
    app.include_router(admin_place.router)
    app.state.official = OfficialService(client, clock=lambda: clock['t'])
    app.state.place_lookup = PlaceLookup(client, clock=lambda: clock['t'], sleep=fake_sleep)
    if authorize:
        app.dependency_overrides[authorized] = lambda: {'id': 'test-admin'}
    return app, client, seen, sleeps


def test_requires_administrator_login():
    app, client, seen, _ = make(authorize=False)
    with TestClient(app) as http:
        response = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78})
        assert response.status_code in (401, 403, 503) and 'address' not in response.json()
    assert seen == []
    asyncio.run(client.aclose())


def test_fills_district_name_and_address_with_attribution_and_policy_headers():
    app, client, seen, _ = make()
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78}).json()
    assert body['status'] == 'available'
    assert body['district']['name'] == 'Udupi' and 'Udupi' in body['district']['aliases'] and body['district']['source'].startswith('IMD')
    assert body['name']['value'] == 'TEST Community Hall'
    assert body['address']['value'] == 'Test Road, Indrali, Manipal, Udupi, Karnataka 576101'
    assert 'OpenStreetMap contributors, ODbL' in body['attribution'] and body['policy_url'].startswith('https://operations.osmfoundation.org')
    request = seen[0]
    assert request.headers['user-agent'].startswith('FloodPulse/') and '@' not in request.headers['user-agent']
    assert request.url.params['zoom'] == '18' and request.url.params['format'] == 'jsonv2'
    asyncio.run(client.aclose())


def test_roads_are_not_offered_as_facility_names():
    app, client, _, _ = make(place=ROAD)
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78}).json()
    assert body['name'] is None and any('No named building' in m for m in body['messages'])
    assert body['address']['value'].startswith('Test Main Road')
    asyncio.run(client.aclose())


def test_cache_and_one_request_per_second():
    app, client, seen, sleeps = make()
    with TestClient(app) as http:
        for lon in (74.78, 74.78, 74.7801):
            assert http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': lon}).status_code == 200
    assert len(seen) == 2  # the repeated point is served from the cache; the hall is within 75 m, so one request each
    assert sleeps and sleeps[0] >= 1.0  # the second distinct lookup waited for the rate limit
    asyncio.run(client.aclose())


def test_outside_karnataka_makes_no_lookup():
    app, client, seen, _ = make()
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 19.07, 'longitude': 72.88}).json()
    assert body['status'] == 'outside' and seen == []
    asyncio.run(client.aclose())


def test_provider_outage_is_reported_and_district_still_found():
    app, client, _, _ = make(nominatim_status=503)
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78}).json()
    assert body['district']['name'] == 'Udupi' and body['name'] is None and body['address'] is None
    assert any('unavailable right now' in m for m in body['messages'])
    asyncio.run(client.aclose())


def test_imd_outage_falls_back_to_osm_district_label():
    app, client, _, _ = make(imd_status=503)
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78}).json()
    assert body['district']['source'] == 'OpenStreetMap address' and body['district']['name'] == 'Udupi'
    assert any('District boundaries are unavailable' in m for m in body['messages'])
    asyncio.run(client.aclose())


def test_address_composition_skips_duplicates_and_control_characters():
    assert compose_address({'road': 'A Road', 'suburb': 'Udupi', 'city': 'Udupi', 'state_district': 'udupi', 'state': 'Karnataka'}) == 'A Road, Udupi, Karnataka'
    assert compose_address({'road': 'Bad\x00Road', 'town': 'Manipal'}) == 'Manipal'
    assert compose_address({}) is None


def test_a_named_place_away_from_the_click_is_only_offered_never_filled():
    far = {**HALL, 'lat': '13.3510', 'lon': '74.7800'}  # about 110 m north of the click
    app, client, seen, _ = make(place=far, address_place=ROAD)
    with TestClient(app) as http:
        body = http.get('/api/admin/place', params={'latitude': 13.35, 'longitude': 74.78}).json()
    assert body['name'] is None and body['nearby']['value'] == 'TEST Community Hall' and 100 <= body['nearby']['distance_m'] <= 120
    assert body['address']['value'].startswith('Test Main Road')  # street address of the clicked point
    assert [r.url.params['layer'] for r in seen] == ['poi', 'address']
    asyncio.run(client.aclose())


def test_map_config_requires_login_and_reports_only_well_formed_keys(monkeypatch):
    import pytest
    for value, status in [(None, 'not_configured'), ('short', 'invalid_configuration'), ('bad key with spaces!!', 'invalid_configuration'),
                          ('TESTONLYmaptilerKey0123', 'available')]:  # TEST FIXTURE ONLY — key-shaped, not a credential
        if value is None:
            monkeypatch.delenv('MAPTILER_PUBLIC_KEY', raising=False)
        else:
            monkeypatch.setenv('MAPTILER_PUBLIC_KEY', value)
        app, client, _, _ = make()
        with TestClient(app) as http:
            body = http.get('/api/admin/map-config').json()
        assert body['status'] == status and (('public_key' in body) == (status == 'available'))
        if value and status != 'available':
            assert value not in str(body)
        asyncio.run(client.aclose())
    app, client, _, _ = make(authorize=False)
    with TestClient(app) as http:
        denied = http.get('/api/admin/map-config')
    assert denied.status_code in (401, 403, 503) and 'public_key' not in denied.text
    asyncio.run(client.aclose())
