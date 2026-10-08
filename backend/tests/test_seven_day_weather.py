"""Seven-day provider contracts; all observations are controlled test fixtures."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_weather
from app.location_weather import fetch_point_weather
from app.weather import LOCATION, OpenMeteoAdapter, WeatherUnavailable, parse_weather

NOW = datetime(2026, 10, 8, 6, tzinfo=timezone.utc)


@pytest.fixture
def seven(monkeypatch):
    clock = type('Clock', (datetime,), {'now': staticmethod(lambda tz: NOW)})
    monkeypatch.setattr('app.weather.datetime', clock)
    monkeypatch.setattr('app.location_weather.datetime', clock)
    return {
        'latitude': 13.35, 'longitude': 74.75, 'utc_offset_seconds': 19800,
        'current_units': {'temperature_2m': '°C', 'relative_humidity_2m': '%', 'precipitation': 'mm'},
        'current': {'time': '2026-10-08T11:30', 'interval': 900, 'temperature_2m': 27, 'relative_humidity_2m': 70, 'precipitation': 0},
        'daily_units': {'temperature_2m_min': '°C', 'temperature_2m_max': '°C', 'precipitation_sum': 'mm', 'weather_code': 'wmo code'},
        'daily': {'time': [(NOW.date() + timedelta(days=i)).isoformat() for i in range(7)],
                  'temperature_2m_min': [20] * 7, 'temperature_2m_max': [30] * 7,
                  'precipitation_sum': [0, 1, 2, 3, 4, 5, 6], 'weather_code': [0, 2, 3, 61, 63, 95, 80]},
    }


def test_seven_days_metadata_units_and_correct_calendar_order(seven):
    body = parse_weather(seven, NOW)
    assert body['status'] == 'available' and len(body['forecast']) == 7
    assert [d['date'] for d in body['forecast']] == seven['daily']['time']
    assert body['forecast'][0]['precipitation_mm'] == 0 and body['forecast'][5]['weather_code'] == 95
    assert body['forecast_units'] == {'precipitation_mm': 'mm', 'temperature_min_c': '°C', 'temperature_max_c': '°C', 'weather_code': 'wmo code'}
    assert body['forecast_coverage'] == {'requested_days': 7, 'returned_days': 7, 'valid_days': 7, 'missing_dates': [], 'complete': True,
                                       'start_date': '2026-10-08', 'end_date': '2026-10-14', 'timezone': 'Asia/Kolkata', 'day_definition': 'local_calendar_day'}
    assert body['observation_time'] is None and body['forecast_issued_at'] is None
    assert body['current']['valid_at'].endswith('+05:30') and body['retrieved_at'] == NOW.isoformat()


@pytest.mark.parametrize('count', [0, 1, 3, 6])
def test_short_or_empty_forecasts_keep_only_actual_dates(seven, count):
    seven['daily'] = {k: v[:count] for k, v in seven['daily'].items()}
    body = parse_weather(seven, NOW)
    assert body['status'] == 'partial' and len(body['forecast']) == count
    assert body['forecast_coverage']['returned_days'] == count
    assert body['forecast_coverage']['valid_days'] == count
    assert len(body['forecast_coverage']['missing_dates']) == 7 - count
    assert body['current']['temperature_c'] == 27


def test_missing_middle_date_is_reported_without_inserting_a_forecast_row(seven):
    for values in seven['daily'].values(): del values[2]
    body = parse_weather(seven, NOW)
    assert body['forecast_coverage']['missing_dates'] == ['2026-10-10']
    assert len(body['forecast']) == 6 and '2026-10-10' not in [d['date'] for d in body['forecast']]


@pytest.mark.parametrize('field', ['temperature_2m_min', 'temperature_2m_max', 'precipitation_sum', 'weather_code'])
def test_missing_daily_values_remain_null(seven, field):
    seven['daily'][field][2] = None
    row = parse_weather(seven, NOW)['forecast'][2]
    output = {'temperature_2m_min': 'temperature_min_c', 'temperature_2m_max': 'temperature_max_c', 'precipitation_sum': 'precipitation_mm', 'weather_code': 'weather_code'}[field]
    assert row[output] is None and row['date'] == '2026-10-10'
    assert parse_weather(seven, NOW)['status'] == 'partial'


def test_omitted_optional_weather_code_is_unavailable_not_clear_sky(seven):
    del seven['daily']['weather_code']; del seven['daily_units']['weather_code']
    body = parse_weather(seven, NOW)
    assert body['status'] == 'partial' and all(d['weather_code'] is None for d in body['forecast'])


def test_all_missing_values_for_one_supplied_date_are_not_valid_coverage(seven):
    for field, values in seven['daily'].items():
        if field != 'time': values[1] = None
    body = parse_weather(seven, NOW)
    assert len(body['forecast']) == 7 and body['forecast_coverage']['valid_days'] == 6
    assert body['forecast_coverage']['missing_dates'] == ['2026-10-09']


@pytest.mark.parametrize('field,unit', [('temperature_2m_min', '°F'), ('temperature_2m_max', 'K'), ('precipitation_sum', 'inch'), ('weather_code', '%')])
def test_wrong_daily_units_rejected(seven, field, unit):
    seven['daily_units'][field] = unit
    with pytest.raises(ValueError, match='units'): parse_weather(seven, NOW)


@pytest.mark.parametrize('mutation', ['duplicate', 'reverse', 'future', 'past', 'noncanonical', 'eight_days', 'short_values', 'bad_code', 'fractional_code'])
def test_bad_dates_or_daily_contract_rejected(seven, mutation):
    if mutation == 'duplicate': seven['daily']['time'][1] = seven['daily']['time'][0]
    elif mutation == 'reverse': seven['daily']['time'].reverse()
    elif mutation == 'future': seven['daily']['time'][-1] = '2026-10-15'
    elif mutation == 'past': seven['daily']['time'][0] = '2026-10-07'
    elif mutation == 'noncanonical': seven['daily']['time'][0] = '20261008'
    elif mutation == 'eight_days': seven['daily']['time'].append('2026-10-15')
    elif mutation == 'short_values': seven['daily']['temperature_2m_min'].pop()
    elif mutation == 'bad_code': seven['daily']['weather_code'][0] = '61'
    else: seven['daily']['weather_code'][0] = 61.5
    with pytest.raises((ValueError, TypeError)): parse_weather(seven, NOW)


@pytest.mark.parametrize('query', ['', '?latitude=13.34&longitude=74.74'])
def test_default_and_selected_point_use_seven_day_provider_request(seven, query):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params['forecast_days'] == '7'
        assert 'weather_code' in request.url.params['daily']
        assert request.url.params['timezone'] == 'Asia/Kolkata'
        assert request.url.params['precipitation_unit'] == 'mm'
        assert request.url.params['temperature_unit'] == 'celsius'
        assert float(request.url.params['latitude']) == (13.34 if query else LOCATION['latitude'])
        return httpx.Response(200, json=seven)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_weather] = lambda: OpenMeteoAdapter(upstream)
    try:
        with TestClient(app) as client: response = client.get('/api/weather' + query)
        assert response.status_code == 200 and len(calls) == 1
        body = response.json()
        assert len(body['forecast']) == 7 and body['grid_location'] == {'latitude': 13.35, 'longitude': 74.75}
        assert body['location']['latitude'] == (13.34 if query else LOCATION['latitude'])
    finally:
        app.dependency_overrides.clear(); asyncio.run(upstream.aclose())


@pytest.mark.parametrize('selected', [False, True])
def test_absolute_deadline_has_no_fallback(monkeypatch, selected):
    original_timeout = asyncio.timeout
    monkeypatch.setattr('app.weather.asyncio.timeout', lambda seconds: original_timeout(0.001))
    async def handler(request): await asyncio.Event().wait()
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_point_weather(client, 13, 75) if selected else await OpenMeteoAdapter(client).fetch()
    with pytest.raises(WeatherUnavailable, match='could not be reached'): asyncio.run(run())

@pytest.mark.parametrize('field', ['latitude', 'longitude'])
def test_missing_provider_grid_position_is_rejected(seven, field):
    seven[field] = None
    with pytest.raises(ValueError, match='grid coordinates'): parse_weather(seven, NOW)


def test_calendar_window_uses_ist_even_before_utc_date_rollover(seven):
    retrieval = datetime(2026, 10, 7, 23, 30, tzinfo=timezone.utc)
    seven['current']['time'] = '2026-10-08T05:00'
    body = parse_weather(seven, retrieval)
    assert body['forecast_coverage']['start_date'] == '2026-10-08'
    assert body['forecast'][0]['date'] == '2026-10-08'


@pytest.mark.parametrize('mode', ['length', 'missing_units'])
def test_present_condition_codes_need_consistent_shape_and_units(seven, mode):
    if mode == 'length': seven['daily']['weather_code'].pop()
    else: del seven['daily_units']['weather_code']
    with pytest.raises(ValueError): parse_weather(seven, NOW)
