"""Public "Show address" lookup — TEST FIXTURES ONLY (invented addresses; Nominatim is mocked)."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import location_address
from app.admin_place import PlaceLookup

UDUPI = {'latitude': 13.340912, 'longitude': 74.742134}
PLACE = {'category': 'place', 'type': 'house', 'lat': '13.3409', 'lon': '74.7421',
         'address': {'house_number': '12', 'road': 'TEST Temple Road', 'suburb': 'TEST Ward', 'town': 'Udupi',
                     'state_district': 'Udupi', 'state': 'Karnataka', 'postcode': '576101', 'country_code': 'in'}}


def make(status=200, body=PLACE):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    clock = {'t': 1_760_000_000.0}

    async def fake_sleep(seconds):
        clock['t'] += seconds

    app = FastAPI()
    app.include_router(location_address.router)
    app.state.place_lookup = PlaceLookup(client, clock=lambda: clock['t'], sleep=fake_sleep)
    return app, client, seen


def post(app, **point):
    with TestClient(app) as http:
        return http.post('/api/location/address', json=point)


@pytest.fixture
def lookup():
    made = []

    def build(**kwargs):
        made.append(make(**kwargs))
        return made[-1]
    yield build
    for _, client, _ in made:
        asyncio.run(client.aclose())


def test_precise_fix_gets_a_street_address_with_attribution_and_a_rounded_point(lookup):
    app, _, seen = lookup()
    response = post(app, **UDUPI, accuracy_m=8)
    body = response.json()
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert body['status'] == 'available' and body['precision'] == 'street' and body['accuracy_m'] == 8
    assert body['address'] == '12 TEST Temple Road, TEST Ward, Udupi, Udupi district, Karnataka 576101'
    assert 'OpenStreetMap' in body['attribution'] and body['policy_url'].startswith('https://operations.osmfoundation.org/')
    params = seen[0].url.params
    assert (params['lat'], params['lon'], params['zoom'], params['layer']) == ('13.340900', '74.742100', '18', 'address')
    assert 'FloodPulse' in seen[0].headers['user-agent']


@pytest.mark.parametrize('accuracy, zoom, precision, address', [
    (100, '17', 'street', 'TEST Temple Road, TEST Ward, Udupi, Udupi district, Karnataka 576101'),
    (600, '14', 'area', 'TEST Ward, Udupi, Udupi district, Karnataka 576101'),
    (None, '18', 'street', '12 TEST Temple Road, TEST Ward, Udupi, Udupi district, Karnataka 576101'),   # spot tapped on the map
])
def test_address_is_never_more_precise_than_the_location(lookup, accuracy, zoom, precision, address):
    app, _, seen = lookup()
    body = post(app, **UDUPI, **({} if accuracy is None else {'accuracy_m': accuracy})).json()
    assert (body['precision'], body['address'], seen[0].url.params['zoom']) == (precision, address, zoom)


@pytest.mark.parametrize('point, status', [
    ({**UDUPI, 'accuracy_m': 2500}, 'too_imprecise'),
    ({'latitude': 15.0, 'longitude': 73.0, 'accuracy_m': 10}, 'outside'),
])
def test_rough_or_outside_points_are_not_sent_anywhere(lookup, point, status):
    app, _, seen = lookup()
    assert post(app, **point).json()['status'] == status and seen == []


def test_can_be_switched_off(lookup, monkeypatch):
    monkeypatch.setenv('FLOODPULSE_ADDRESS_LOOKUP', 'off')
    app, _, seen = lookup()
    assert post(app, **UDUPI, accuracy_m=8).json()['status'] == 'disabled' and seen == []


def test_repeated_lookups_are_cached(lookup):
    app, _, seen = lookup()
    for _ in range(3):
        assert post(app, **UDUPI, accuracy_m=8).json()['status'] == 'available'
    assert len(seen) == 1


@pytest.mark.parametrize('status, body, expected, code', [
    (503, {}, 'unavailable', 503),
    (200, {'error': 'Unable to geocode'}, 'not_found', 200),
    (200, {**PLACE, 'address': {**PLACE['address'], 'country_code': 'np'}}, 'not_found', 200),
])
def test_provider_failures_are_reported_not_guessed(lookup, status, body, expected, code):
    app, _, _ = lookup(status=status, body=body)
    response = post(app, **UDUPI, accuracy_m=8)
    assert response.status_code == code and response.json()['status'] == expected and 'address' not in response.json()


def test_a_long_queue_is_refused_instead_of_exceeding_the_limit(lookup):
    app, _, seen = lookup()
    app.state.place_lookup.waiting = location_address.MAX_WAITING
    response = post(app, **UDUPI, accuracy_m=8)
    assert response.status_code == 503 and 'try again' in response.json()['message'] and seen == []


def test_only_coordinates_and_accuracy_are_accepted(lookup):
    app, _, seen = lookup()
    assert post(app, **UDUPI, accuracy_m=8, name='Home').status_code == 422
    assert post(app, **UDUPI, accuracy_m=-1).status_code == 422
    assert seen == []


VILLAGE_ROAD = {'category': 'highway', 'type': 'residential', 'lat': '13.3500', 'lon': '74.7421',   # about 1 km away
                'address': {'road': 'TEST Lane', 'city_district': 'TEST Village (76)', 'county': 'TEST Taluk', 'state_district': 'Udupi',
                            'state': 'Karnataka', 'postcode': '576279', 'country_code': 'in'}}


def test_village_address_keeps_village_and_taluk_and_drops_a_distant_street(lookup):
    app, _, _ = lookup(body=VILLAGE_ROAD)
    body = post(app, **UDUPI, accuracy_m=8).json()
    assert body['address'] == 'TEST Village, TEST Taluk, Udupi district, Karnataka 576279' and body['precision'] == 'area'


def test_an_unnamed_road_gives_an_area_not_a_street(lookup):
    app, _, _ = lookup(body={**VILLAGE_ROAD, 'lat': '13.3409', 'address': {k: v for k, v in VILLAGE_ROAD['address'].items() if k != 'road'}})
    body = post(app, **UDUPI, accuracy_m=8).json()
    assert body['precision'] == 'area' and body['address'].startswith('TEST Village, ')


def test_taluk_and_district_words_are_not_repeated(lookup):
    app, _, _ = lookup(body={**VILLAGE_ROAD, 'address': {**VILLAGE_ROAD['address'], 'county': 'Udupi taluku', 'state_district': 'Udupi District'}})
    assert post(app, **UDUPI, accuracy_m=8).json()['address'] == 'TEST Village, Udupi taluku, Udupi District, Karnataka 576279'


def test_short_place_name_with_pin_code(lookup):
    app, _, _ = lookup()
    body = post(app, **UDUPI, accuracy_m=8).json()
    assert (body['place'], body['postcode']) == ('TEST Ward, Udupi 576101', '576101')
    app, _, _ = lookup(body=VILLAGE_ROAD)
    assert post(app, **UDUPI, accuracy_m=8).json()['place'] == 'TEST Village, TEST Taluk 576279'   # no town: taluk


@pytest.mark.parametrize('postcode, expected', [('576 101', '576101'), ('110001', None), ('57610', None), ('PIN 576101', None), (None, None)])
def test_only_valid_karnataka_pin_codes_are_shown(lookup, postcode, expected):
    app, _, _ = lookup(body={**PLACE, 'address': {**PLACE['address'], 'postcode': postcode}})
    body = post(app, **UDUPI, accuracy_m=8).json()
    assert body['postcode'] == expected
    assert body['place'] == 'TEST Ward, Udupi' + (f' {expected}' if expected else '')
    assert body['address'].endswith(f'Karnataka {expected}' if expected else 'Karnataka')
