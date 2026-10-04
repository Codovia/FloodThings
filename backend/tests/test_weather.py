"""Invented response values are confined to isolated tests."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_weather
from app.weather import API_URL, PARAMS, OpenMeteoAdapter, WeatherUnavailable, parse_weather

NOW = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def payload():
    return {
        "latitude": 12.98, "longitude": 77.59, "utc_offset_seconds": 19800,
        "current_units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm"},
        "current": {"time": "2026-10-03T11:30", "interval": 900,
                    "temperature_2m": 24.5, "relative_humidity_2m": 80, "precipitation": 0},
        "daily_units": {"precipitation_sum": "mm", "temperature_2m_max": "°C", "temperature_2m_min": "°C"},
        "daily": {"time": ["2026-10-03", "2026-10-04", "2026-10-05"],
                  "precipitation_sum": [0, 2.4, None], "temperature_2m_max": [28, 29, 30],
                  "temperature_2m_min": [20, 21, 22]},
    }


def test_parse_preserves_null_zero_units_and_provenance(payload):
    result = parse_weather(payload, NOW)
    assert result["status"] == "partial"
    assert result["current"]["precipitation_mm"] == 0
    assert result["forecast"][2]["precipitation_mm"] is None
    assert result["current"]["valid_at"] == "2026-10-03T11:30:00+05:30"
    assert result["retrieved_at"] == NOW.isoformat()
    assert result["observation_time"] is None
    assert result["forecast_issued_at"] is None
    assert result["source"]["data_kind"] == "weather_model_output"
    assert result["grid_location"]["latitude"] == 12.98
    assert not result["current"]["stale"]


def test_complete_response(payload):
    payload["daily"]["precipitation_sum"][2] = 1
    assert parse_weather(payload, NOW)["status"] == "available"


def test_stale_current_estimate(payload):
    payload["current"]["time"] = "2026-10-03T09:00"
    assert parse_weather(payload, NOW)["current"]["stale"]


@pytest.mark.parametrize("section,field,bad", [
    ("current", "temperature_2m", "24"),
    ("current", "temperature_2m", float("nan")),
    ("current", "precipitation", -1),
    ("current", "relative_humidity_2m", 101),
    ("current", "temperature_2m", True),
    ("current", "interval", None),
    ("current", "time", "invalid"),
    ("current", "time", "2026-10-04T11:30"),
    ("current_units", "precipitation", "inch"),
    ("daily_units", "temperature_2m_max", "°F"),
    ("daily", "precipitation_sum", [1]),
    ("daily", "time", ["2026-10-03", "2026-10-03", "2026-10-05"]),
    ("daily", "temperature_2m_min", [40, 21, 22]),
])
def test_invalid_provider_fields(payload, section, field, bad):
    payload[section][field] = bad
    with pytest.raises((ValueError, TypeError)):
        parse_weather(payload, NOW)


def test_all_readings_unavailable(payload):
    for field in ("temperature_2m", "relative_humidity_2m", "precipitation"):
        payload["current"][field] = None
    for field in ("precipitation_sum", "temperature_2m_max", "temperature_2m_min"):
        payload["daily"][field] = [None] * 3
    with pytest.raises(ValueError, match="No weather values"):
        parse_weather(payload, NOW)


def test_adapter_uses_documented_request(payload, monkeypatch):
    # Fix the clock so this fixture cannot go stale as the test date changes.
    class Clock:
        @staticmethod
        def now(tz):
            return NOW

    monkeypatch.setattr("app.weather.datetime", type("Clock", (datetime,), {"now": Clock.now}))
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url).startswith(API_URL + "?")
        assert dict(request.url.params) == {k: str(v) for k, v in PARAMS.items()}
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OpenMeteoAdapter(client).fetch()

    assert asyncio.run(run())["current"]["temperature_c"] == 24.5
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["timeout", "429", "500", "malformed", "missing"])
def test_adapter_failure_has_no_fallback(mode):
    calls = []

    def handler(request):
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("test timeout", request=request)
        if mode in ("429", "500"):
            return httpx.Response(int(mode))
        if mode == "malformed":
            return httpx.Response(200, content=b"not json")
        return httpx.Response(200, json={})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await OpenMeteoAdapter(client).fetch()

    with pytest.raises(WeatherUnavailable):
        asyncio.run(run())
    assert len(calls) == 1


def test_health_and_weather_api(payload):
    result = parse_weather(deepcopy(payload), NOW)

    class StubAdapter:
        async def fetch(self):
            return result

    app.dependency_overrides[get_weather] = lambda: StubAdapter()
    try:
        with TestClient(app) as client:
            assert client.get("/api/health").json()["status"] == "ok"
            response = client.get("/api/weather")
            assert response.status_code == 200
            assert response.json() == result
    finally:
        app.dependency_overrides.clear()


def test_weather_api_unavailable():
    class StubAdapter:
        async def fetch(self):
            raise WeatherUnavailable("Provider unavailable")

    app.dependency_overrides[get_weather] = lambda: StubAdapter()
    try:
        with TestClient(app) as client:
            response = client.get("/api/weather")
            assert response.status_code == 503
            body = response.json()
            assert body["status"] == "unavailable"
            assert body["current"] is None
            assert body["forecast"] == []
            assert body["retrieved_at"] is None
            assert body["source"]["name"] == "Open-Meteo"
    finally:
        app.dependency_overrides.clear()
