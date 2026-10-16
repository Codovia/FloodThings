import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import risk
from app.risk import (RiskService, annual_maxima, assess, gumbel_levels, imd_category, level, parse_rain,
                      statewide_grid, load_boundary, suggestions)

NOW = datetime(2026, 10, 16, 6, 30, tzinfo=timezone.utc)
HOUR = 3600


def hourly(past_mm=0.0, future_mm=0.0, peak=None, start=NOW):
    """Open-Meteo style unixtime series: 6 past days + 3 forecast days."""
    base = (int(start.timestamp()) // HOUR) * HOUR
    times = list(range(base - 144 * HOUR, base + 72 * HOUR + 1, HOUR))
    values = [past_mm if t <= base else future_mm for t in times]
    if peak is not None:
        values[times.index(base + 5 * HOUR)] = peak
    return {'latitude': 13.6, 'longitude': 74.7, 'hourly_units': {'precipitation': 'mm'},
            'hourly': {'time': times, 'precipitation': values}}


def test_imd_categories_use_official_boundaries():
    assert imd_category(15.5)[0] == 0 and imd_category(15.6)[0] == 1
    assert imd_category(64.4)[0] == 1 and imd_category(64.5) == (2, 'heavy')
    assert imd_category(115.6)[0] == 3 and imd_category(204.5) == (4, 'extremely heavy')


def test_levels():
    assert [level(s) for s in (0, 1, 2, 3, 4, 5, 6, 11)] == ['low', 'low', 'moderate', 'moderate', 'high', 'high', 'severe', 'severe']


def test_rain_window_is_next_24_full_hours_and_past_five_days():
    rain = parse_rain(hourly(past_mm=1.0, future_mm=2.0, peak=25.0), NOW)
    assert rain['next24_mm'] == pytest.approx(23 * 2.0 + 25.0)
    assert rain['past5d_mm'] == pytest.approx(120 * 1.0)
    assert rain['peak_mmh'] == 25.0
    assert rain['window_start'] == '2026-10-16T07:00:00+00:00'


def test_incomplete_rain_is_rejected_not_filled():
    body = hourly(future_mm=1.0)
    base = (int(NOW.timestamp()) // HOUR) * HOUR
    body['hourly']['precipitation'][body['hourly']['time'].index(base + 10 * HOUR)] = None
    with pytest.raises(ValueError):
        parse_rain(body, NOW)


def test_missing_rain_makes_level_unavailable_never_low():
    result = assess(None, point_detail=False)
    assert result['flood']['level'] == 'unavailable' and result['flood']['score'] is None
    assert result['drainage']['level'] == 'unavailable'


def test_full_point_scoring_and_partial_inputs():
    rain = {'next24_mm': 120.0, 'past5d_mm': 160.0, 'peak_mmh': 22.0}
    river = {'status': 'available', 'forecast_max': 300.0, 'rl2': 170.0, 'rl5': 210.0}
    result = assess(rain, river, elevation=5, history=True, reports=3)
    assert result['flood']['score'] == 3 + 2 + 3 + 1 + 1 and result['flood']['level'] == 'severe'
    assert result['drainage']['score'] == 2 + 2 + 2 + 1 and result['drainage']['level'] == 'severe'
    assert result['flood']['partial'] is False
    partial = assess(rain, {'status': 'unavailable', 'message': 'down'}, elevation=None, history=None, reports=None)
    assert partial['flood']['partial'] is True
    statuses = {f['id']: f['status'] for f in partial['flood']['factors']}
    assert statuses == {'rain24': 'available', 'rain5d': 'available', 'river': 'unavailable',
                        'elevation': 'unavailable', 'history': 'no_data'}


def test_negligible_river_scores_zero_with_explanation():
    rain = {'next24_mm': 0.0, 'past5d_mm': 0.0, 'peak_mmh': 0.0}
    river = assess(rain, {'status': 'available', 'forecast_max': 0.4, 'rl2': 0.2, 'rl5': 0.5})['flood']['factors'][2]
    assert river['points'] == 0 and 'No significant modelled river' in river['detail']


def test_gumbel_levels_and_annual_maxima():
    rl2, rl5 = gumbel_levels([100, 150, 200, 250, 300, 120, 180, 220])
    assert 150 < rl2 < rl5 < 330
    days = [f'{y}-{d:03d}' for y in range(2015, 2025) for d in range(1, 366)]
    payload = {'daily_units': {'river_discharge': 'm³/s'}, 'daily': {'time': days, 'river_discharge': [float(i % 365) for i in range(len(days))]}}
    maxima = annual_maxima(payload)
    assert len(maxima) == 10
    payload['daily']['river_discharge'] = [None] * len(days)
    with pytest.raises(ValueError):
        annual_maxima(payload)


def test_statewide_grid_covers_karnataka():
    cells = statewide_grid(load_boundary())
    assert len(cells) == 256
    assert all(11.5 < c['latitude'] < 18.5 and 74.0 < c['longitude'] < 78.7 for c in cells)


def fake_service(handler, cache_dir):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client, RiskService(client, cache_dir=cache_dir, clock=lambda: NOW.timestamp())


def forecast_handler(request):
    url = request.url
    if url.host == 'api.open-meteo.com' and url.path == '/v1/forecast':
        count = len(url.params['latitude'].split(','))
        body = [hourly(future_mm=4.0, past_mm=0.5) for _ in range(count)]
        return httpx.Response(200, json=body if count > 1 else body[0])
    if url.path == '/v1/elevation':
        return httpx.Response(200, json={'elevation': [4.0]})
    if url.host == 'flood-api.open-meteo.com':
        if 'start_date' in url.params:
            days = [f'{y}-{d:03d}' for y in range(2015, 2025) for d in range(1, 366)]
            return httpx.Response(200, json={'latitude': 13.6, 'longitude': 74.7, 'daily_units': {'river_discharge': 'm³/s'},
                                             'daily': {'time': days, 'river_discharge': [100.0 + (i % 365) for i in range(len(days))]}})
        return httpx.Response(200, json={'daily_units': {'river_discharge': 'm³/s'}, 'daily': {'time': ['a', 'b', 'c', 'd'], 'river_discharge': [500.0, 600.0, None, 450.0]}})
    return httpx.Response(404)


def test_grid_scores_every_cell_and_caches(tmp_path_factory):
    calls = []
    client, svc = fake_service(lambda r: calls.append(r) or forecast_handler(r), tmp_path_factory.mktemp('risk'))
    grid = asyncio.run(svc.grid())
    assert grid['status'] == 'available' and len(grid['cells']) == 256 and grid['experimental'] is True
    assert {c['level'] for c in grid['cells']} == {'moderate'}  # 96 mm heavy (2) + 60 mm past 5 days (1)
    first = len(calls)
    asyncio.run(svc.grid())
    assert len(calls) == first  # cached
    asyncio.run(client.aclose())


def test_grid_provider_outage_is_unavailable(tmp_path_factory):
    client, svc = fake_service(lambda r: httpx.Response(503), tmp_path_factory.mktemp('risk'))
    grid = asyncio.run(svc.grid())
    assert grid['status'] == 'unavailable' and all(c['level'] == 'unavailable' for c in grid['cells'])
    asyncio.run(client.aclose())


def test_point_uses_river_history_cache_and_reports_unavailable(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(risk, 'approved_report_count', lambda *a, **k: None)
    cache = tmp_path_factory.mktemp('risk')
    client, svc = fake_service(forecast_handler, cache)
    body = asyncio.run(svc.point(13.6250993, 74.6915722))
    assert body['status'] == 'available' and body['official_warning'] is False
    river = next(f for f in body['flood']['factors'] if f['id'] == 'river')
    assert river['status'] == 'available' and river['points'] == 3  # 600 m³/s exceeds the 5-year level
    assert next(f for f in body['drainage']['factors'] if f['id'] == 'reports')['status'] == 'unavailable'
    assert list(cache.glob('glofas_*.json'))
    asyncio.run(client.aclose())


def test_point_outside_karnataka_is_rejected(tmp_path_factory):
    client, svc = fake_service(forecast_handler, tmp_path_factory.mktemp('risk'))
    with pytest.raises(Exception) as caught:
        asyncio.run(svc.point(19.5, 73.0))
    assert getattr(caught.value, 'status_code', None) == 422
    asyncio.run(client.aclose())


def test_suggestions_are_drafts_only():
    grid = {'status': 'available', 'retrieved_at': NOW.isoformat(), 'cells': [
        {'id': 'a', 'latitude': 13.6, 'longitude': 74.7, 'level': 'severe', 'score': 6, 'rain_24h_mm': 210.0, 'rain_5d_mm': 160.0},
        {'id': 'b', 'latitude': 15.0, 'longitude': 76.0, 'level': 'low', 'score': 0, 'rain_24h_mm': 1.0, 'rain_5d_mm': 0.0}]}
    out = suggestions(grid)
    assert [s['cell_id'] for s in out['suggestions']] == ['a']
    assert 'not an official warning' in out['suggestions'][0]['suggested_message']
    assert 'explicitly approve' in out['note']


def test_api_routes(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(risk, 'approved_report_count', lambda *a, **k: 0)
    app = FastAPI()
    app.include_router(risk.router)
    client, svc = fake_service(forecast_handler, tmp_path_factory.mktemp('risk'))
    app.state.risk = svc
    with TestClient(app) as http:
        ok = http.get('/api/risk', params={'latitude': 13.6250993, 'longitude': 74.6915722})
        assert ok.status_code == 200 and ok.headers['cache-control'] == 'no-store'
        assert http.get('/api/risk', params={'latitude': 19.5, 'longitude': 73.0}).status_code == 422
        assert http.get('/api/risk/grid').status_code == 200
        denied = http.get('/api/admin/risk/suggestions')
        assert denied.status_code in (401, 403, 503) and 'suggestions' not in denied.json()
    asyncio.run(client.aclose())
