"""Point weather tests use controlled HTTP fixtures only; no persistence or network."""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_weather
from app.location_weather import fetch_point_weather
from app.weather import PARAMS, WeatherUnavailable

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr('app.location_weather.datetime', type('Clock', (datetime,), {'now': staticmethod(lambda tz: NOW)}))
    return {'latitude': 13.35, 'longitude': 74.75, 'utc_offset_seconds': 19800,
            'current_units': {'temperature_2m': '°C', 'relative_humidity_2m': '%', 'precipitation': 'mm'},
            'current': {'time': '2026-10-08T11:30', 'interval': 900, 'temperature_2m': 27, 'relative_humidity_2m': 70, 'precipitation': 0},
            'daily_units': {'precipitation_sum': 'mm', 'temperature_2m_max': '°C', 'temperature_2m_min': '°C'},
            'daily': {'time': ['2026-10-08', '2026-10-09', '2026-10-10'], 'precipitation_sum': [1, None, 3],
                      'temperature_2m_max': [30, 31, 30], 'temperature_2m_min': [23, 22, 23]}}


def test_point_query_and_requested_vs_model_grid_positions(provider):
    before = dict(PARAMS); calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params['latitude'] == '13.34'
        assert request.url.params['longitude'] == '74.74'
        assert request.url.params['forecast_days'] == '3'
        return httpx.Response(200, json=provider)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_point_weather(client, 13.34, 74.74)
    body = asyncio.run(run())
    assert len(calls) == 1 and PARAMS == before
    assert body['location']['latitude'] == 13.34 and body['grid_location']['latitude'] == 13.35
    assert body['location']['administrative_identity_status'] == 'not_verified'
    assert body['prediction_status'] == 'not_available'
    assert body['forecast'][1]['precipitation_mm'] is None and body['current']['precipitation_mm'] == 0
    assert body['observation_time'] is None and body['forecast_issued_at'] is None


@pytest.mark.parametrize('latitude,longitude', [(None, 75), (13, None), (True, 75), (91, 75), (13, 181), (float('nan'), 75)])
def test_invalid_point_never_calls_provider(latitude, longitude):
    def handler(request): raise AssertionError('No provider call for invalid coordinates')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_point_weather(client, latitude, longitude)
    with pytest.raises(WeatherUnavailable): asyncio.run(run())


@pytest.mark.parametrize('field,bad', [('latitude', None), ('longitude', None), ('latitude', float('inf')), ('utc_offset_seconds', 0)])
def test_bad_provider_coordinate_or_timezone_fails(provider, field, bad):
    provider[field] = bad
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(provider).encode()))) as client:
            await fetch_point_weather(client, 13.34, 74.74)
    with pytest.raises(WeatherUnavailable): asyncio.run(run())


def request_api(query, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_weather] = lambda: SimpleNamespace(client=client)
    try:
        with TestClient(app) as http:
            return http.get('/api/weather' + query)
    finally:
        app.dependency_overrides.clear(); asyncio.run(client.aclose())


def test_api_point_contract(provider):
    response = request_api('?latitude=13.34&longitude=74.74', lambda r: httpx.Response(200, json=provider))
    assert response.status_code == 200
    body = response.json()
    assert body['location']['longitude'] == 74.74 and body['grid_location']['longitude'] == 74.75
    assert body['status'] == 'partial' and body['prediction_status'] == 'not_available'


@pytest.mark.parametrize('query', ['?latitude=13', '?longitude=75', '?latitude=nan&longitude=75', '?latitude=inf&longitude=75', '?latitude=91&longitude=75', '?latitude=13&longitude=181', '?latitude=invalid&longitude=75'])
def test_api_invalid_pairs_422_without_provider(query):
    response = request_api(query, lambda r: (_ for _ in ()).throw(AssertionError('Invalid input reached provider')))
    assert response.status_code == 422


@pytest.mark.parametrize('failure', ['timeout', '429', '500', 'malformed'])
def test_point_unavailable_keeps_requested_identity_and_no_fake_weather(failure):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('controlled timeout', request=request)
        return httpx.Response(int(failure)) if failure != 'malformed' else httpx.Response(200, content=b'not-json')
    response = request_api('?latitude=13.34&longitude=74.74', handler)
    assert response.status_code == 503 and len(calls) == 1
    body = response.json()
    assert body['location']['latitude'] == 13.34 and body['location']['longitude'] == 74.74
    assert body['status'] == 'unavailable' and body['current'] is None and body['forecast'] == []
    assert body['prediction_status'] == 'not_available' and body['retrieved_at'] is None
