import asyncio
import json
from datetime import date, timedelta

import httpx
import pytest

from app.river_flood_features import FEATURES, decision_score, river_flood_features
from app.river_flood_model import RiverFloodModel, load_model

DAY = date(2026, 8, 10)


def series(values_by_offset, days=37, start=DAY - timedelta(days=30)):
    """Daily rain {iso: mm} from start; values_by_offset maps day offset from DAY to mm (default 0)."""
    return {(start + timedelta(days=k)).isoformat(): values_by_offset.get((start + timedelta(days=k) - DAY).days, 0.0) for k in range(days)}


def test_features_use_only_rain_up_to_the_day_and_never_fill_gaps():
    cells = {(12.0, 75.0): series({0: 30, -1: 20, -2: 10, 1: 999}), (12.25, 75.0): series({0: 10})}
    x = river_flood_features(cells, DAY)
    assert x[:2] == [20.0, 35.0]            # catchment mean today; 3-day sum (tomorrow's 999 mm is not used)
    assert x[5] == 60.0                       # wettest cell's 3-day rain
    gap = {(12.0, 75.0): {k: v for k, v in series({}).items() if k != (DAY - timedelta(days=12)).isoformat()}}
    assert river_flood_features(gap, DAY) is None
    assert river_flood_features({(12.0, 75.0): series({-3: -1})}, DAY) is None


def model_record(**over):
    record = {'id': 'test_river', 'river': 'Test', 'place': 'Fixture', 'catchment_cells': [[12.0, 75.0], [12.25, 75.0]],
              'scaler': {'mean': [0.0] * 8, 'scale': [1.0] * 8}, 'coefficients': [0, 0.1, 0, 0, 0, 0, 0, 0], 'intercept': -10.0,
              'decision_threshold': 0.0, 'baseline_rule_rain_3d_mm': 80.0, 'live_rain_scale': {'factor': 1.0},
              'test': {'model': {'f1': 0.6, 'precision': 0.6, 'recall': 0.6}, 'baseline_rule': {'f1': 0.4}},
              'documented_floods_in_test_years': [{'event_date': '2019-08-09', 'model_flagged_1_to_4_days_before': True}]}
    record.update(over)
    return record


def write(tmp, rivers):
    path = tmp / 'model.json'
    path.write_text(json.dumps({'version': 'river_flood_v1', 'features': FEATURES, 'rivers': rivers}))
    return path


def test_decision_score_is_standardised_linear():
    assert decision_score(model_record(), [0, 120, 0, 0, 0, 0, 0, 0]) == pytest.approx(2.0)


def test_load_model_rejects_malformed_and_marks_rivers_where_the_rule_did_better(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('model')
    _, rivers = load_model(write(tmp, [model_record(), model_record(id='weak', test={'model': {'f1': .5, 'precision': .5, 'recall': .5}, 'baseline_rule': {'f1': .58}})]))
    assert rivers['test_river']['used'] is True and rivers['weak']['used'] is False
    with pytest.raises(ValueError):
        load_model(write(tmp, [model_record(live_rain_scale={'factor': 9})]))
    with pytest.raises(ValueError):
        load_model(write(tmp, [model_record(coefficients=[1, 2])]))


def forecast_reply(rain_today):
    rows = []
    for _ in range(2):
        times = [(DAY - timedelta(days=30) + timedelta(days=k)).isoformat() for k in range(37)]
        values = [rain_today if t == DAY.isoformat() else 0.0 for t in times]
        rows.append({'daily_units': {'precipitation_sum': 'mm'}, 'daily': {'time': times, 'precipitation_sum': values}})
    return httpx.Response(200, json=rows)


def run(tmp_path_factory, handler, **over):
    path = write(tmp_path_factory.mktemp('model'), [model_record(**over)])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await RiverFloodModel(client, path).assess(['test_river', 'unknown'], today=DAY)
    return asyncio.run(go())


def test_heavy_upstream_rain_flags_a_flood_and_reports_the_inputs(tmp_path_factory):
    calls = []
    out = run(tmp_path_factory, lambda r: (calls.append(r.url.params), forecast_reply(120))[1])
    result = out['test_river']
    assert result['status'] == 'available' and result['flood_likely'] is True and result['first_flagged_date'] == DAY.isoformat()
    assert result['peak_upstream_rain_3d_mm'] == 120.0 and len(result['days']) == 7
    assert calls[0]['past_days'] == '30' and out['unknown']['status'] == 'not_trained'


def test_live_rain_is_converted_to_the_training_scale(tmp_path_factory):
    out = run(tmp_path_factory, lambda r: forecast_reply(120), live_rain_scale={'factor': 0.5})
    assert out['test_river']['flood_likely'] is False and out['test_river']['peak_upstream_rain_3d_mm'] == 60.0


@pytest.mark.parametrize('response', [lambda: httpx.Response(503), lambda: httpx.Response(200, json=[{'daily_units': {'precipitation_sum': 'inch'}, 'daily': {}}] * 2)])
def test_rain_outage_is_unavailable_never_not_likely(tmp_path_factory, response):
    result = run(tmp_path_factory, lambda r: response())['test_river']
    assert result['status'] == 'unavailable' and 'flood_likely' not in result


def test_shipped_model_matches_its_documented_evaluation():
    meta, rivers = load_model()
    assert meta['train_years'] == [1997, 2015] and meta['test_years'] == [2016, 2021] and len(rivers) == 6
    assert [r['river'] for r in rivers.values() if not r['used']] == ['Ghataprabha']
    for r in rivers.values():
        assert r['parity_max_abs_difference'] < 1e-3 and len(r['catchment_cells']) >= 3
        assert all(e['model_flagged_1_to_4_days_before'] for e in r['documented_floods_in_test_years'])
