"""Model performance (research view): the recorded test results of FloodPulse's two trained models.

Everything is read from the model artifacts themselves (both are validated by their own loaders first), so the page
can only show what training measured on held-out years. Nothing is recomputed, estimated or fetched. The one derived
number is each confusion matrix's true negatives: test days minus true positives, false positives and false negatives.
"""
from functools import lru_cache

from fastapi import APIRouter

from .rainfall_outlook import get_model as rainfall_model
from .river_flood_model import load_model as river_model

router = APIRouter()


def counts(metrics, days):
    tp, fp, fn = metrics['tp'], metrics['fp'], metrics['fn']
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': days - tp - fp - fn,
            'precision': metrics['precision'], 'recall': metrics['recall'], 'f1': metrics['f1']}


def matrix(cm, metrics=None):
    (tn, fp), (fn, tp) = cm
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, **({k: metrics[k] for k in ('precision', 'recall', 'f1')} if metrics else {})}


@lru_cache(maxsize=1)
def performance():
    data, served = river_model()
    rivers = []
    for r in data['rivers']:
        test = r['test']
        rivers.append({
            'id': r['id'], 'river': r['river'], 'place': r['place'],
            'flood_level_2_year_m3s': r['flood_level_2_year_m3s'], 'rain_rule_3d_mm': r['baseline_rule_rain_3d_mm'],
            'train': r['train'], 'test': {'days': test['days'], 'positives': test['positives']},
            'model': counts(test['model'], test['days']), 'rain_rule': counts(test['baseline_rule'], test['days']),
            'served': served[r['id']]['used'],
            'documented_floods': [{'date': e['event_date'], 'model_flagged': e['model_flagged_1_to_4_days_before'],
                                   'rule_flagged': e['rule_flagged_1_to_4_days_before']} for e in r['documented_floods_in_test_years']],
        })
    floods = [f for r in rivers for f in r['documented_floods']]
    meta = rainfall_model().metadata
    holdout, baseline = meta['holdout_metrics'], meta['always_below_threshold_baseline']
    return {
        'river_flood': {
            'version': data['version'], 'target': data['target'], 'features': data['features'],
            'train_years': data['train_years'], 'test_years': data['test_years'], 'rivers': rivers,
            'summary': {'rivers': len(rivers), 'beat_rain_rule': sum(r['served'] for r in rivers),
                        'documented_floods': len(floods), 'documented_floods_flagged': sum(f['model_flagged'] for f in floods)},
            'limitations': [
                'Targets are GloFAS v4 reanalysis river flow above the 2-year flood level, not measured water levels: measured Karnataka gauge data are not available, so the model cannot be more accurate than GloFAS.',
                'Test days are consecutive and flood days cluster, so the days are not independent events.',
                'Live inputs are Open-Meteo rain converted to the ERA5 scale with a per-catchment factor fitted on 2023–2025.',
                'A river where the model did not beat the rain rule in the test years is not served by the model.',
            ],
        },
        'rainfall': {
            'version': meta['version'], 'algorithm': meta['algorithm'], 'target': meta['target'], 'features': list(meta['features']),
            'training': meta['training'], 'testing': meta['testing'], 'temporal_split': meta['temporal_split'],
            'model': matrix(holdout['confusion_matrix_tn_fp_fn_tp'], holdout),
            'baseline': matrix(baseline['confusion_matrix_tn_fp_fn_tp'], baseline),
            'locations': [p['name'] for p in meta['locations']],
            'limitations': [meta['deployment_scope'], meta['sample_dependence'], meta['historical_availability']],
        },
    }


@router.get('/api/models/performance')
def model_performance():
    return performance()
