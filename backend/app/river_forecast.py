"""River flood forecast for verified Karnataka river points (Copernicus GloFAS v4 via Open-Meteo).

Each point passed two checks when it was built (scripts/build_karnataka_river_points.py): the model
cell lies on the named river in OpenStreetMap, and its largest past flows coincide with documented
floods. The 50-run GloFAS ensemble forecast is compared with the cell's own 2-, 5- and 10-year flood
levels from the GloFAS reanalysis, as GloFAS does. Modelled river flow, not observed water levels and
not an official warning; dam operations are only approximated by the model.
"""
import asyncio
import json
import statistics
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .home_sources import SourceFailure, read_json

router = APIRouter()
POINTS_FILE = Path(__file__).resolve().parents[2] / 'data/reference/karnataka_river_points_v1/points.json'
FLOOD_URL = 'https://flood-api.open-meteo.com/v1/flood'
MODEL = 'forecast_v4'
DAYS = 7
CACHE_SECONDS, FAILURE_SECONDS = 3600, 60  # GloFAS issues one forecast a day
LABEL = ('Experimental river flood forecast: modelled river flow from Copernicus GloFAS for checked river points. '
         'Not observed water levels and not an official warning; follow CWC, KSNDMC and district advice.')
# Project-chosen reading of the ensemble (share of the 50 forecast runs above a flood level).
LEVEL_RULES = (('severe', '5_year', .5, 'Above the 5-year flood level in most forecast runs'),
               ('high', '2_year', .5, 'Above the 2-year flood level in most forecast runs'),
               ('moderate', '2_year', .2, 'Above the 2-year flood level in some forecast runs'))
SOURCE = {'name': 'Copernicus GloFAS v4 via Open-Meteo Flood API', 'url': 'https://open-meteo.com/en/docs/flood-api', 'license': 'CC BY 4.0'}


def load_points(path=POINTS_FILE):
    data = json.loads(Path(path).read_text())
    points = []
    for p in data['points']:
        if p.get('accepted') is not True or not (p['checks']['geography_ok'] and p['checks']['history_ok']):
            continue
        levels = p['flood_levels_m3s']
        if not 0 < levels['2_year'] < levels['5_year'] < levels['10_year']:
            raise ValueError(f"{p['id']}: flood levels out of order")
        points.append(p)
    if not 1 <= len(points) <= 20:
        raise ValueError('Unexpected number of verified river points')
    return points


def assess_point(point, daily):
    """Turn one point's 50 ensemble members into daily flood-level exceedance and a level."""
    members = [k for k in daily if k.startswith('river_discharge_member')]
    if len(members) < 40:
        raise ValueError('Ensemble members missing')
    levels = point['flood_levels_m3s']
    days = []
    for i, day in enumerate(daily['time']):
        values = [daily[m][i] for m in members if isinstance(daily[m][i], (int, float)) and daily[m][i] >= 0]
        if len(values) < 40:
            raise ValueError('Too few valid ensemble values')
        share = lambda key: round(sum(v > levels[key] for v in values) / len(values), 2)
        days.append({'date': day, 'median_m3s': round(statistics.median(values), 1), 'max_m3s': round(max(values), 1),
                     'share_above': {'2_year': share('2_year'), '5_year': share('5_year'), '10_year': share('10_year')}})
    peak = max(days, key=lambda d: (d['share_above']['5_year'], d['share_above']['2_year'], d['median_m3s']))
    level, meaning = 'low', 'Below the 2-year flood level in almost all forecast runs'
    for name, key, minimum, text in LEVEL_RULES:
        if peak['share_above'][key] >= minimum:
            level, meaning = name, text
            break
    return {'id': point['id'], 'river': point['river'], 'place': point['place'], 'district': point['district'],
            'grid': point['grid'], 'flood_levels_m3s': levels, 'level': level, 'meaning': meaning,
            'peak': peak, 'days': days, 'members': len(members),
            'evidence': {'osm_rivers': point['checks']['osm_named_rivers_within_3km'],
                         'documented_floods': point['checks']['documented_flood_matches']}}


class RiverForecast:
    def __init__(self, client, points=None, clock=time.monotonic):
        self.client, self.clock = client, clock
        self.points = points if points is not None else load_points()
        self.cache, self.lock = None, asyncio.Lock()

    async def forecast(self):
        async with self.lock:
            if self.cache and self.cache[0] > self.clock():
                return deepcopy(self.cache[1])
            params = {'latitude': ','.join(str(p['grid']['latitude']) for p in self.points),
                      'longitude': ','.join(str(p['grid']['longitude']) for p in self.points),
                      'daily': 'river_discharge', 'models': MODEL, 'ensemble': 'true', 'forecast_days': DAYS, 'timezone': 'GMT'}
            try:
                payload, sha = await read_json(self.client, FLOOD_URL, params, limit=2 * 1024 * 1024)
                rows = payload if isinstance(payload, list) else [payload]
                if len(rows) != len(self.points):
                    raise ValueError('Unexpected number of locations')
                results = []
                for point, row in zip(self.points, rows):
                    # The provider must answer for the exact checked model cell.
                    if any(abs(row[k] - point['grid'][k]) > .01 for k in ('latitude', 'longitude')):
                        raise ValueError('Provider grid differs from the checked river cell')
                    if row.get('daily_units', {}).get('river_discharge_member01') not in (None, 'm³/s') or len(row['daily']['time']) != DAYS:
                        raise ValueError('Unexpected units or forecast length')
                    results.append(assess_point(point, row['daily']))
                body = {'status': 'available', 'label': LABEL, 'source': SOURCE, 'model': MODEL, 'forecast_days': DAYS,
                        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'response_sha256': sha,
                        'date_semantics': 'GloFAS daily dates (UTC days)', 'points': results}
                expires = CACHE_SECONDS
            except SourceFailure as exc:
                body, expires = {'status': 'unavailable', 'label': LABEL, 'source': SOURCE, 'points': [],
                                 'message': f'River forecast provider unavailable ({exc.kind}).'}, FAILURE_SECONDS
            except (ValueError, KeyError, TypeError, IndexError):
                body, expires = {'status': 'unavailable', 'label': LABEL, 'source': SOURCE, 'points': [],
                                 'message': 'River forecast data could not be validated.'}, FAILURE_SECONDS
            self.cache = (self.clock() + expires, deepcopy(body))
            return body


@router.get('/api/river-forecast')
async def river_forecast(request: Request):
    body = await request.app.state.river_forecast.forecast()
    return JSONResponse(body, status_code=200 if body['status'] == 'available' else 503, headers={'Cache-Control': 'no-store'})
