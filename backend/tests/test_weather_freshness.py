"""Existing API retrieval clocks: isolated provider fixtures, no scheduler/data writes."""
import asyncio
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_weather
from app.weather import OpenMeteoAdapter

from test_seven_day_weather import seven, NOW

def request_api(query, handler):
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_weather] = lambda: OpenMeteoAdapter(upstream)
    try:
        with TestClient(app) as client:
            return client.get('/api/weather' + query)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(upstream.aclose())



@pytest.mark.parametrize('query', ['', '?latitude=13.34&longitude=74.74'])
def test_successful_retrieval_is_backend_utc_not_provider_valid_or_issuance_time(seven, query):
    response = request_api(query, lambda request: httpx.Response(200, json=seven))
    assert response.status_code == 200
    body = response.json()
    assert body['retrieved_at'] == NOW.isoformat()
    assert datetime.fromisoformat(body['retrieved_at']).utcoffset().total_seconds() == 0
    assert body['current']['valid_at'] == '2026-10-08T11:30:00+05:30'
    assert body['observation_time'] is None and body['forecast_issued_at'] is None
    assert body['forecast_coverage']['timezone'] == 'Asia/Kolkata'
    assert body['forecast'][0]['date'] == '2026-10-08' and len(body['forecast']) == 7


@pytest.mark.parametrize('query', ['', '?latitude=13.34&longitude=74.74'])
@pytest.mark.parametrize('failure', ['timeout', '503', 'invalid_payload'])
def test_failed_retrieval_never_receives_success_clock_or_substitute_readings(query, failure):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('Controlled timeout', request=request)
        if failure == '503': return httpx.Response(503)
        return httpx.Response(200, json={})
    response = request_api(query, handler)
    assert response.status_code == 503 and len(calls) == 1
    body = response.json()
    assert body['retrieved_at'] is None and body['forecast_issued_at'] is None
    assert body['current'] is None and body['forecast'] == []
