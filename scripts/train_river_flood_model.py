"""Train and evaluate the FloodPulse river flood model (rain upstream -> river above its flood level).

For each checked river point (data/reference/karnataka_river_points_v1) the model predicts whether the
river will exceed its 2-year flood level within the next 3 days, from rain over its upstream catchment.

- Catchment: the river network upstream of the point, traced backwards along OpenStreetMap river lines
  (drawn in flow direction), including named tributaries; rain is sampled on the ERA5 0.25° cells it crosses.
- Inputs (day t, rain up to and including t): catchment-mean rain over 1, 3, 5, 10 and 30 days, the wettest
  cell's 3-day rain, and season. No river flow is used, so the model is not simply persistence.
- Target: GloFAS v4 reanalysis flow (consolidated_v4) above the point's 2-year level on any of days t+1..t+3.
  This is modelled flow, not measured water level: measured Karnataka gauge data are not available.
- Split by time: train 1997-2015, test 2016-2021 (never used for fitting or threshold choice).
- Baseline: the best single "3-day catchment rain above X mm" rule, chosen on training years.
- Real-world check: documented floods in the test years (2018 Kabini, 2019 Krishna/Ghataprabha/Netravati/Kali).

Run: backend/.venv/bin/python scripts/train_river_flood_model.py   (network; caches in data/tmp/river_flood_model_v1)
"""
import hashlib, json, math, time, collections, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

import sys
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.river_flood_features import FEATURES, decision_score, river_flood_features  # shared with the live service
CACHE = ROOT / 'data/tmp/river_flood_model_v1'
POINTS = ROOT / 'data/reference/karnataka_river_points_v1/points.json'
OUT = ROOT / 'backend/models/river_flood_v1/model.json'
START, END = date(1997, 1, 1), date(2021, 12, 31)
TRAIN_END = date(2015, 12, 31)
HORIZON = 3
UA = {'User-Agent': 'FloodPulse-river-flood-model/1.0'}

# Upstream tracing: river and tributary names as written in OpenStreetMap, and a box covering the basin.
CATCHMENTS = {
    'krishna_kudachi': (['Krishna', 'Koyna', 'Warna', 'Panchganga', 'Venna', 'Urmodi'], '15.5,73.3,18.3,76.5'),
    'ghataprabha_gokak': (['Ghataprabha', 'Hiranyakeshi', 'Markandeya'], '15.6,73.8,16.6,75.2'),
    'kabini_nanjangud': (['Kabini', 'Kapila', 'Nugu', 'Gundal', 'Taraka', 'Panamaram'], '11.4,75.6,12.4,76.9'),
    'netravati_bantwal': (['Netravati', 'Nethravathi', 'Kumaradhara'], '12.4,74.8,13.3,75.8'),
    'tungabhadra_hampi': (['Tungabhadra', 'Tunga', 'Bhadra', 'Varada', 'Kumudvathi'], '13.0,75.0,15.5,76.6'),
    'kali_dandeli': (['Kali', 'Kalinadi', 'Kali Nadi'], '14.9,74.2,15.6,74.8'),
}
# Documented floods (sources in data/reference/karnataka_river_points_v1/points.json).
EVENTS = {'kabini_nanjangud': ['2018-08-18'], 'krishna_kudachi': ['2019-08-08'], 'ghataprabha_gokak': ['2019-08-09'],
          'netravati_bantwal': ['2019-08-10'], 'kali_dandeli': ['2019-08-06']}


def fetch(url, params=None, data=None, tries=8):
    for attempt in range(tries):
        try:
            full = url + ('?' + urllib.parse.urlencode(params) if params else '')
            request = urllib.request.Request(full, data=data, headers=UA)
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code in (429, 502, 503, 504) and attempt < tries - 1:
                time.sleep(60 if error.code == 429 else 30)
                continue
            raise


def cached(name, producer):
    path = CACHE / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(producer())
    return path.read_bytes()


def catchment_cells(point):
    names, bbox = CATCHMENTS[point['id']]
    pattern = '|'.join(names)
    query = f'[out:json][timeout:240];way["waterway"="river"]["name"~"^({pattern})( River| Nadi)?$",i]({bbox});out body geom;'
    raw = cached(f"osm_{point['id']}.json", lambda: fetch('https://overpass-api.de/api/interpreter', data=urllib.parse.urlencode({'data': query}).encode()))
    reverse, coord = collections.defaultdict(set), {}
    for way in json.loads(raw)['elements']:
        for node, g in zip(way['nodes'], way['geometry']):
            coord[node] = (g['lat'], g['lon'])
        for a, b in zip(way['nodes'], way['nodes'][1:]):
            reverse[b].add(a)  # water flows a -> b; walking b -> a goes upstream
    lat, lon = point['grid']['latitude'], point['grid']['longitude']
    start = min(coord, key=lambda n: (coord[n][0] - lat) ** 2 + ((coord[n][1] - lon) * math.cos(math.radians(lat))) ** 2)
    seen, todo = {start}, [start]
    while todo:
        for m in reverse[todo.pop()]:
            if m not in seen:
                seen.add(m); todo.append(m)
    cells = sorted({(round(coord[n][0] * 4) / 4, round(coord[n][1] * 4) / 4) for n in seen})
    if len(cells) < 2:
        raise ValueError(f"{point['id']}: upstream network not found")
    return cells, raw


def era5_rain(cells):
    out = {}
    for i in range(0, len(cells), 8):
        batch = cells[i:i + 8]
        params = {'latitude': ','.join(f'{c[0]:.2f}' for c in batch), 'longitude': ','.join(f'{c[1]:.2f}' for c in batch),
                  'daily': 'precipitation_sum', 'models': 'era5', 'timezone': 'GMT', 'start_date': START.isoformat(), 'end_date': (END + timedelta(days=HORIZON)).isoformat()}
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        body = json.loads(cached(f'era5_{key}.json', lambda: fetch('https://archive-api.open-meteo.com/v1/archive', params)))
        for cell, row in zip(batch, body if isinstance(body, list) else [body]):
            out[cell] = dict(zip(row['daily']['time'], row['daily']['precipitation_sum']))
        time.sleep(5)
    return out


CALIBRATION = (date(2023, 1, 1), date(2025, 12, 31))  # after the training years; three monsoons


def live_rain_scale(cells, era5_series):
    """Factor converting live forecast-model rain to the ERA5 scale the model was trained on.

    The app reads Open-Meteo forecast-model rain; its archive (Historical Forecast API) is compared with ERA5
    over 2023-2025 for the same catchment cells: factor = ERA5 total / forecast-model total (catchment mean).
    """
    params = {'latitude': ','.join(f'{c[0]:.2f}' for c in cells), 'longitude': ','.join(f'{c[1]:.2f}' for c in cells),
              'daily': 'precipitation_sum', 'timezone': 'GMT', 'start_date': CALIBRATION[0].isoformat(), 'end_date': CALIBRATION[1].isoformat()}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    body = json.loads(cached(f'histforecast_{key}.json', lambda: fetch('https://historical-forecast-api.open-meteo.com/v1/forecast', params)))
    live = {cell: dict(zip(row['daily']['time'], row['daily']['precipitation_sum'])) for cell, row in zip(cells, body if isinstance(body, list) else [body])}
    era_total = live_total = 0.0
    day = CALIBRATION[0]
    while day <= CALIBRATION[1]:
        d = day.isoformat()
        e = [era5_series[c].get(d) for c in cells]; f = [live[c].get(d) for c in cells]
        if None not in e and None not in f:
            era_total += sum(e) / len(e); live_total += sum(f) / len(f)
        day += timedelta(days=1)
    if live_total <= 0:
        raise ValueError('No overlapping calibration rain')
    return round(era_total / live_total, 4), round(era_total, 1), round(live_total, 1)


def era5_calibration(cells):
    params = {'latitude': ','.join(f'{c[0]:.2f}' for c in cells), 'longitude': ','.join(f'{c[1]:.2f}' for c in cells),
              'daily': 'precipitation_sum', 'models': 'era5', 'timezone': 'GMT', 'start_date': CALIBRATION[0].isoformat(), 'end_date': CALIBRATION[1].isoformat()}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    body = json.loads(cached(f'era5cal_{key}.json', lambda: fetch('https://archive-api.open-meteo.com/v1/archive', params)))
    return {cell: dict(zip(row['daily']['time'], row['daily']['precipitation_sum'])) for cell, row in zip(cells, body if isinstance(body, list) else [body])}


def glofas_flow(point):
    params = {'latitude': point['grid']['latitude'], 'longitude': point['grid']['longitude'], 'daily': 'river_discharge',
              'models': 'consolidated_v4', 'start_date': START.isoformat(), 'end_date': (END + timedelta(days=HORIZON)).isoformat()}
    body = json.loads(cached(f"glofas_{point['id']}.json", lambda: fetch('https://flood-api.open-meteo.com/v1/flood', params)))
    return dict(zip(body['daily']['time'], body['daily']['river_discharge']))


def scores(y, p):
    tp = int(((p == 1) & (y == 1)).sum()); fp = int(((p == 1) & (y == 0)).sum()); fn = int(((p == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0; recall = tp / (tp + fn) if tp + fn else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0}


def best_threshold(values, y):
    best = (0, None)
    for t in np.unique(np.quantile(values, np.linspace(.5, .999, 300))):
        f1 = scores(y, (values >= t).astype(int))['f1']
        if f1 > best[0]: best = (f1, float(t))
    return best[1]


def main():
    points = [p for p in json.loads(POINTS.read_text())['points'] if p['accepted']]
    artifact = {'version': 'river_flood_v1', 'target': 'GloFAS v4 reanalysis flow above the 2-year flood level within 3 days',
                'features': FEATURES, 'train_years': [1997, 2015], 'test_years': [2016, 2021], 'rivers': []}
    report = []
    for point in points:
        cells, osm_raw = catchment_cells(point)
        rain = era5_rain(cells)
        flow = glofas_flow(point)
        level = point['flood_levels_m3s']['2_year']
        rows, labels, days = [], [], []
        day = START + timedelta(days=29)
        while day <= END:
            x = river_flood_features(rain, day)
            future = [flow.get((day + timedelta(days=k)).isoformat()) for k in range(1, HORIZON + 1)]
            if x is not None and None not in future:
                rows.append(x); labels.append(int(max(future) > level)); days.append(day)
            day += timedelta(days=1)
        X, y, days = np.array(rows), np.array(labels), np.array(days)
        train = days <= TRAIN_END; test = ~train
        scaler = StandardScaler().fit(X[train])
        model = LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000, random_state=7).fit(scaler.transform(X[train]), y[train])
        score = model.decision_function(scaler.transform(X))
        threshold = best_threshold(score[train], y[train])            # chosen on training years only
        rain3 = X[:, 1]; rule = best_threshold(rain3[train], y[train])  # baseline rule, training years only
        model_test = scores(y[test], (score[test] >= threshold).astype(int))
        rule_test = scores(y[test], (rain3[test] >= rule).astype(int))
        events = []
        for when in EVENTS.get(point['id'], []):
            target = date.fromisoformat(when)
            window = (days >= target - timedelta(days=4)) & (days <= target - timedelta(days=1))  # 1-4 days before the documented date
            events.append({'event_date': when, 'model_flagged_1_to_4_days_before': bool((score[window] >= threshold).any()),
                           'rule_flagged_1_to_4_days_before': bool((rain3[window] >= rule).any())})
        record = {'id': point['id'], 'river': point['river'], 'place': point['place'], 'flood_level_2_year_m3s': level,
                  'catchment_cells': [list(c) for c in cells], 'osm_sha256': hashlib.sha256(osm_raw).hexdigest(),
                  'scaler': {'mean': scaler.mean_.round(6).tolist(), 'scale': scaler.scale_.round(6).tolist()},
                  'coefficients': model.coef_[0].round(6).tolist(), 'intercept': round(float(model.intercept_[0]), 6),
                  'decision_threshold': round(threshold, 6), 'baseline_rule_rain_3d_mm': round(rule, 1),
                  'train': {'days': int(train.sum()), 'positives': int(y[train].sum())},
                  'test': {'days': int(test.sum()), 'positives': int(y[test].sum()), 'model': model_test, 'baseline_rule': rule_test},
                  'documented_floods_in_test_years': events}
        # The saved numbers must reproduce scikit-learn's scores exactly (portable inference in the app).
        portable = np.array([decision_score(record, row) for row in X])
        if np.max(np.abs(portable - score)) > 1e-3:
            raise ValueError(f"{point['id']}: portable inference differs from the fitted model")
        record['parity_max_abs_difference'] = float(np.max(np.abs(portable - score)))
        factor, era_mm, live_mm = live_rain_scale(cells, era5_calibration(cells))
        record['live_rain_scale'] = {'factor': factor, 'period': [CALIBRATION[0].isoformat(), CALIBRATION[1].isoformat()],
                                     'era5_catchment_total_mm': era_mm, 'forecast_model_catchment_total_mm': live_mm,
                                     'method': 'ERA5 total / Open-Meteo forecast-model total over the same catchment cells and days'}
        artifact['rivers'].append(record)
        report.append(record)
        print(f"{point['river']:12s} cells={len(cells):2d} test positives={record['test']['positives']:4d} | "
              f"MODEL P={model_test['precision']:.2f} R={model_test['recall']:.2f} F1={model_test['f1']:.2f} | "
              f"RULE(3d≥{rule:.0f}mm) P={rule_test['precision']:.2f} R={rule_test['recall']:.2f} F1={rule_test['f1']:.2f} | live-rain factor {factor} ({era_mm:.0f}/{live_mm:.0f} mm)", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (CACHE / 'evaluation.json').write_text(json.dumps(report, indent=1))
    OUT.write_text(json.dumps(artifact, indent=1) + '\n')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
