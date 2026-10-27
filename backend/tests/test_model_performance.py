"""The model performance view only repeats recorded test results from the validated artifacts."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.model_performance import performance, router
from app.rainfall_outlook import ARTIFACT as RAINFALL
from app.river_flood_model import ARTIFACT as RIVER


def client():
    app = FastAPI(); app.include_router(router)
    return TestClient(app)


def test_river_results_are_the_artifact_numbers_and_matrices_add_up():
    raw = {r['id']: r for r in json.loads(RIVER.read_text())['rivers']}
    body = client().get('/api/models/performance').json()['river_flood']
    assert body['test_years'] == [2016, 2021] and body['train_years'] == [1997, 2015] and len(body['rivers']) == len(raw) == 6
    for r in body['rivers']:
        test = raw[r['id']]['test']
        for mine, theirs in ((r['model'], test['model']), (r['rain_rule'], test['baseline_rule'])):
            assert {k: mine[k] for k in theirs} == theirs
            assert mine['tp'] + mine['fp'] + mine['fn'] + mine['tn'] == test['days'] and mine['tn'] >= 0
            assert mine['tp'] + mine['fn'] == test['positives']
        assert r['served'] == (test['model']['f1'] > test['baseline_rule']['f1'])
    assert body['summary'] == {'rivers': 6, 'beat_rain_rule': sum(r['served'] for r in body['rivers']),
                               'documented_floods': sum(len(r['documented_floods']) for r in body['rivers']),
                               'documented_floods_flagged': sum(f['model_flagged'] for r in body['rivers'] for f in r['documented_floods'])}


def test_rainfall_results_are_the_holdout_and_baseline_matrices():
    meta = json.loads((RAINFALL / 'metadata.json').read_text())
    body = performance()['rainfall']
    (tn, fp), (fn, tp) = meta['holdout_metrics']['confusion_matrix_tn_fp_fn_tp']
    assert {k: body['model'][k] for k in ('tn', 'fp', 'fn', 'tp')} == {'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp}
    assert body['model']['recall'] == meta['holdout_metrics']['recall'] and body['baseline']['f1'] == 0.0
    assert tn + fp + fn + tp == meta['testing']['samples']
    assert meta['deployment_scope'] in body['limitations']
