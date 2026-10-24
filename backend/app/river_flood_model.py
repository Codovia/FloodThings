"""Live inference of the FloodPulse river flood model (backend/models/river_flood_v1).

Trained by scripts/train_river_flood_model.py on ERA5 rain over each river's upstream catchment (1997-2015) to
predict GloFAS reanalysis flow above the 2-year flood level within 3 days; tested on 2016-2021. Live inputs are
Open-Meteo's recent and forecast rain for the same catchment cells, converted to the ERA5 scale with a per-catchment
factor fitted on 2023-2025 (after the training years), because the two rain sources differ.
A river where the model did not beat the simple rain rule in the test years is not served by the model.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .home_sources import SourceFailure, read_json
from .river_flood_features import FEATURES, WINDOW_DAYS, decision_score, river_flood_features

ARTIFACT = Path(__file__).resolve().parents[1] / 'models' / 'river_flood_v1' / 'model.json'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
DAYS = 7


def load_model(path=ARTIFACT):
    data = json.loads(Path(path).read_text())
    if data.get('version') != 'river_flood_v1' or data.get('features') != FEATURES:
        raise ValueError('Unexpected river flood model artifact')
    rivers = {}
    for r in data['rivers']:
        if not (len(r['coefficients']) == len(FEATURES) == len(r['scaler']['mean']) == len(r['scaler']['scale'])
                and all(s > 0 for s in r['scaler']['scale']) and len(r['catchment_cells']) >= 2
                and 0.3 <= r['live_rain_scale']['factor'] <= 3):
            raise ValueError(f"{r['id']}: malformed model")
        rivers[r['id']] = {**r, 'catchment_cells': [tuple(c) for c in r['catchment_cells']],
                           'used': r['test']['model']['f1'] > r['test']['baseline_rule']['f1']}
    return data, rivers


def summary(r):
    t = r['test']
    return {'test_years': '2016–2021', 'model_f1': t['model']['f1'], 'model_precision': t['model']['precision'], 'model_recall': t['model']['recall'],
            'rain_rule_f1': t['baseline_rule']['f1'], 'rain_rule_mm_3d': r['baseline_rule_rain_3d_mm'],
            'documented_floods_flagged': [e['event_date'] for e in r['documented_floods_in_test_years'] if e['model_flagged_1_to_4_days_before']]}


class RiverFloodModel:
    def __init__(self, client, path=ARTIFACT):
        self.client = client
        self.meta, self.rivers = load_model(path)

    async def assess(self, ids, today=None):
        """{river id: result} for the requested river points; failures are 'unavailable', never 'not likely'."""
        today = today or datetime.now(timezone.utc).date()
        out = {}
        for i in ids:
            r = self.rivers.get(i)
            if r is None:
                out[i] = {'status': 'not_trained'}
            elif not r['used']:
                out[i] = {'status': 'not_used', 'evaluation': summary(r),
                          'message': 'AI model not used here: a simple rain rule did better in the test years (2016–2021).'}
        wanted = [i for i in ids if i in self.rivers and self.rivers[i]['used']]
        cells = sorted({c for i in wanted for c in self.rivers[i]['catchment_cells']})
        if not cells:
            return out
        try:
            params = {'latitude': ','.join(f'{c[0]:.2f}' for c in cells), 'longitude': ','.join(f'{c[1]:.2f}' for c in cells),
                      'daily': 'precipitation_sum', 'past_days': WINDOW_DAYS, 'forecast_days': DAYS, 'timezone': 'GMT'}
            payload, sha = await read_json(self.client, FORECAST_URL, params, limit=2 * 1024 * 1024)
            rows = payload if isinstance(payload, list) else [payload]
            if len(rows) != len(cells):
                raise ValueError('Unexpected number of rain locations')
            rain = {}
            for cell, row in zip(cells, rows):
                if row.get('daily_units', {}).get('precipitation_sum') != 'mm':
                    raise ValueError('Unexpected rain units')
                rain[cell] = dict(zip(row['daily']['time'], row['daily']['precipitation_sum']))
        except (SourceFailure, ValueError, KeyError, TypeError) as exc:
            reason = exc.kind if isinstance(exc, SourceFailure) else 'invalid response'
            for i in wanted:
                out[i] = {'status': 'unavailable', 'message': f'Rain data for the AI model unavailable ({reason}).'}
            return out
        for i in wanted:
            r = self.rivers[i]
            factor = r['live_rain_scale']['factor']  # live forecast-model rain -> ERA5 scale used in training
            series = {c: {d: (v * factor if isinstance(v, (int, float)) else v) for d, v in rain[c].items()} for c in r['catchment_cells']}
            days = []
            for k in range(DAYS):
                day = today + timedelta(days=k)
                x = river_flood_features(series, day)
                if x is None:
                    days = None
                    break
                score = decision_score(r, x)
                days.append({'date': day.isoformat(), 'flood_likely': score >= r['decision_threshold'], 'score': round(score, 3),
                             'upstream_rain_3d_mm': round(x[1], 1), 'upstream_rain_10d_mm': round(x[3], 1)})
            if days is None:
                out[i] = {'status': 'unavailable', 'message': 'Rain data for the AI model was incomplete; no prediction made.'}
                continue
            first = next((d for d in days if d['flood_likely']), None)
            wettest = max(days, key=lambda d: d['upstream_rain_3d_mm'])
            out[i] = {'status': 'available', 'flood_likely': first is not None,
                      'first_flagged_date': first['date'] if first else None,
                      # A flag on day d means: river above its 2-year flood level expected on one of days d+1..d+3.
                      'meaning': 'River above its 2-year flood level expected within 3 days of the flagged date' if first else
                                 'River not expected above its 2-year flood level in the next 7–10 days',
                      'peak_upstream_rain_3d_mm': wettest['upstream_rain_3d_mm'], 'peak_rain_date': wettest['date'],
                      'days': days, 'evaluation': summary(r), 'rain_source': 'Open-Meteo forecast (recent and next 7 days)',
                      'rain_scale_factor': factor,
                      'rain_response_sha256': sha}
        return out
