"""Recorded API-shaped fixtures: test evidence, never operational observations."""
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.weather import parse_weather, retry_after
from test_weather_freshness import request_api

RECORD = json.loads((Path(__file__).parent / 'fixtures/open_meteo_kundapur.json').read_text())
NOW = datetime.fromisoformat(RECORD['reference_time'])


@pytest.fixture
def recorded():
    return deepcopy(RECORD['payload'])


def test_recorded_documented_current_and_hourly_format(recorded):
    body = parse_weather(recorded, NOW)
    current, hourly = body['current'], body['hourly_precipitation']
    assert current['temperature_c'] == 35.5
    assert current['humidity_percent'] == 35 and current['weather_code'] == 0
    assert current['wind_speed'] == 13.3 and current['wind_speed_unit'] == 'km/h'
    assert current['precipitation_mm'] == 0 and current['interval_seconds'] == 900
    assert current['precipitation_window_start'] == '2026-10-13T11:15:00+05:30'
    assert current['precipitation_window_end'] == '2026-10-13T11:30:00+05:30'
    assert all(v == 'available' for v in current['field_status'].values())
    assert len(body['forecast']) == 7 and len(hourly['intervals']) == 168
    assert hourly['intervals'][0] == {'start': '2026-10-12T23:00:00+05:30', 'end': '2026-10-13T00:00:00+05:30', 'precipitation_mm': 0.0, 'unit': 'mm'}
    assert hourly['interval_semantics'] == 'preceding_hour'
    assert hourly['source']['data_kind'] == 'weather_model_output'
    assert body['observation_time'] is None and body['forecast_issued_at'] is None


@pytest.mark.parametrize('field', ['temperature_2m', 'relative_humidity_2m', 'precipitation', 'weather_code', 'wind_speed_10m'])
@pytest.mark.parametrize('missing', [True, False])
def test_optional_current_missing_keeps_other_valid_fields(recorded, field, missing):
    if missing:
        del recorded['current'][field]; del recorded['current_units'][field]
    else:
        recorded['current'][field] = None
    result = parse_weather(recorded, NOW)
    assert result['current']['field_status'][field] == 'missing'
    assert result['hourly_precipitation']['status'] == 'available'
    assert len(result['forecast']) == 7
    if field != 'temperature_2m': assert result['current']['temperature_c'] == 35.5
    else: assert result['current']['humidity_percent'] == 35


@pytest.mark.parametrize('problem', ['missing', 'null', 'nan', 'negative', 'duplicate', 'reverse', 'units', 'time_units', 'short_array', 'bad_timestamp', 'misaligned'])
def test_hourly_problems_never_substitute_daily_or_hide_current(recorded, problem):
    h = recorded['hourly']
    if problem == 'missing': del recorded['hourly']
    elif problem == 'null': h['precipitation'][15] = None
    elif problem == 'nan': h['precipitation'][15] = float('nan')
    elif problem == 'negative': h['precipitation'][15] = -1
    elif problem == 'duplicate': h['time'][15] = h['time'][14]
    elif problem == 'reverse': h['time'][14], h['time'][15] = h['time'][15], h['time'][14]
    elif problem == 'units': recorded['hourly_units']['precipitation'] = 'inch'
    elif problem == 'time_units': recorded['hourly_units']['time'] = 'unixtime'
    elif problem == 'short_array': h['precipitation'].pop()
    elif problem == 'bad_timestamp': h['time'][15] = 'unknown'
    else: h['time'][15] = '2026-10-13T15:20'
    result = parse_weather(recorded, NOW)
    assert result['current']['temperature_c'] == 35.5 and len(result['forecast']) == 7
    hourly = result['hourly_precipitation']
    if problem == 'null': assert hourly['intervals'][15]['precipitation_mm'] is None
    else:
        assert hourly['status'] == ('missing' if problem == 'missing' else 'invalid')
        assert hourly['intervals'] == [] and hourly['message']


@pytest.mark.parametrize('problem', ['wind_units', 'code_units', 'fractional_code', 'negative_wind', 'time_units'])
def test_invalid_current_supported_values_rejected(recorded, problem):
    if problem == 'wind_units': recorded['current_units']['wind_speed_10m'] = 'bananas'
    elif problem == 'code_units': recorded['current_units']['weather_code'] = '%'
    elif problem == 'fractional_code': recorded['current']['weather_code'] = 1.5
    elif problem == 'negative_wind': recorded['current']['wind_speed_10m'] = -1
    else: recorded['current_units']['time'] = 'unixtime'
    with pytest.raises(ValueError): parse_weather(recorded, NOW)


@pytest.mark.parametrize('mode,kind,status', [('503', 'provider_unavailable', 503), ('429', 'rate_limited', 429), ('400', 'provider_http_error', 400), ('timeout', 'timeout', None), ('network', 'network_failure', None), ('schema', 'invalid_response', 200)])
def test_distinct_failure_receipts_keep_one_provider_call(mode, kind, status):
    calls = []
    def handler(request):
        calls.append(request)
        if mode == 'timeout': raise httpx.ReadTimeout('fixture timeout', request=request)
        if mode == 'network': raise httpx.ConnectError('fixture network failure', request=request)
        if mode == 'schema': return httpx.Response(200, json={})
        return httpx.Response(int(mode), headers={'Retry-After': '3600'})
    response = request_api('?latitude=13.34&longitude=74.74', handler)
    assert response.status_code == 503 and len(calls) == 1
    body = response.json()
    assert body['failure_kind'] == kind and body['upstream_status'] == status
    assert body['current'] is None and body['retrieved_at'] is None
    if mode in ('429', '503'):
        assert body['retry_after_seconds'] == 3600 and int(response.headers['Retry-After']) >= 3600
    if mode == '503': assert 'HTTP 503' in body['message'] and 'invalid data' not in body['message']
    if mode == 'schema': assert 'utc_offset_seconds' in body['message']


def test_retry_after_http_date_and_invalid_guidance():
    assert retry_after('Tue, 13 Oct 2026 07:15:00 GMT', NOW) == 3600
    assert retry_after('nonsense', NOW) is None
    assert retry_after('0', NOW) == 0
