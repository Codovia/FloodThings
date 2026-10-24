import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import river_forecast
from app.river_forecast import RiverForecast, assess_point, load_points

# TEST FIXTURES ONLY: shapes follow the Open-Meteo flood API; the values are invented.
POINT = {'id': 'test_river', 'river': 'Test', 'place': 'Fixture', 'district': 'Udupi', 'accepted': True,
         'grid': {'latitude': 13.025, 'longitude': 74.825},
         'checks': {'geography_ok': True, 'history_ok': True, 'osm_named_rivers_within_3km': ['Test'],
                    'documented_flood_matches': [{'event_date': '2019-08-09'}]},
         'flood_levels_m3s': {'2_year': 100.0, '5_year': 200.0, '10_year': 300.0}}


def daily(per_day):
    """per_day: list of (values for 50 members) per day."""
    body = {'time': [f'2026-10-{24 + i}' for i in range(len(per_day))]}
    for m in range(50):
        body[f'river_discharge_member{m + 1:02d}'] = [day[m] for day in per_day]
    body['river_discharge'] = [day[0] for day in per_day]
    return body


def flat(value, days=7):
    return [[value] * 50 for _ in range(days)]


@pytest.mark.parametrize('members, level', [
    ([50] * 50, 'low'),
    ([150] * 15 + [50] * 35, 'moderate'),   # 30% of runs above the 2-year level
    ([150] * 30 + [50] * 20, 'high'),       # 60% above the 2-year level
    ([250] * 30 + [150] * 20, 'severe'),    # 60% above the 5-year level
])
def test_level_follows_share_of_runs_above_flood_levels(members, level):
    result = assess_point(POINT, daily([[50] * 50] * 3 + [members] + [[50] * 50] * 3))
    assert result['level'] == level
    assert result['peak']['date'] == '2026-10-27' or level == 'low'
    assert result['members'] == 50 and len(result['days']) == 7


def test_rejects_short_ensembles_and_negative_values():
    body = daily(flat(50))
    for m in range(15, 51):
        del body[f'river_discharge_member{m:02d}']
    with pytest.raises(ValueError):
        assess_point(POINT, body)
    bad = daily([[-1] * 50] + flat(50, 6))
    with pytest.raises(ValueError):
        assess_point(POINT, bad)


def test_load_points_keeps_only_points_that_passed_both_checks(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('river_points')  # outside the per-test directory the suite keeps empty
    rejected = {**POINT, 'id': 'rejected', 'accepted': False}
    unchecked = {**POINT, 'id': 'unchecked', 'checks': {**POINT['checks'], 'history_ok': False}}
    path = tmp_path / 'points.json'
    path.write_text(json.dumps({'points': [POINT, rejected, unchecked]}))
    assert [p['id'] for p in load_points(path)] == ['test_river']
    path.write_text(json.dumps({'points': [{**POINT, 'flood_levels_m3s': {'2_year': 300, '5_year': 200, '10_year': 100}}]}))
    with pytest.raises(ValueError):
        load_points(path)


def test_shipped_points_passed_both_checks_and_have_ordered_levels():
    points = load_points()
    assert len(points) == 6
    assert {p['river'] for p in points} == {'Krishna', 'Ghataprabha', 'Kabini', 'Netravati', 'Tungabhadra', 'Kali'}
    for p in points:
        assert p['river'].lower() in ' '.join(p['checks']['osm_named_rivers_within_3km']).lower()
        assert p['checks']['documented_flood_matches'] and all(m['source'].startswith('https://') for m in p['checks']['documented_flood_matches'])
        assert p['history']['model'] == 'consolidated_v4' and p['history']['annual_maxima'] == 25


def service(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client, RiverForecast(client, points=[POINT], clock=lambda: 1000.0)


def reply(grid=POINT['grid'], days=7, value=150):
    return httpx.Response(200, json={'latitude': grid['latitude'], 'longitude': grid['longitude'],
                                     'daily_units': {'river_discharge_member01': 'm³/s'}, 'daily': daily(flat(value, days))})


def test_service_validates_the_checked_cell_and_caches():
    calls = []
    def handler(request):
        calls.append(request.url.params)
        return reply()
    client, svc = service(handler)
    body = asyncio.run(svc.forecast())
    assert body['status'] == 'available' and body['points'][0]['level'] == 'high'
    assert calls[0]['ensemble'] == 'true' and calls[0]['models'] == 'forecast_v4'
    asyncio.run(svc.forecast())
    assert len(calls) == 1
    asyncio.run(client.aclose())


@pytest.mark.parametrize('response', [
    lambda: reply(grid={'latitude': 13.4, 'longitude': 74.825}),  # a different model cell
    lambda: reply(days=3),
    lambda: httpx.Response(503),
])
def test_wrong_cell_short_forecast_or_outage_is_unavailable_never_low(response):
    client, svc = service(lambda request: response())
    body = asyncio.run(svc.forecast())
    assert body['status'] == 'unavailable' and body['points'] == []
    asyncio.run(client.aclose())


def test_route_returns_503_when_unavailable():
    app = FastAPI(); app.include_router(river_forecast.router)
    class Stub:
        async def forecast(self): return {'status': 'unavailable', 'points': [], 'label': 'x'}
    app.state.river_forecast = Stub()
    response = TestClient(app).get('/api/river-forecast')
    assert response.status_code == 503 and response.headers['cache-control'] == 'no-store'
