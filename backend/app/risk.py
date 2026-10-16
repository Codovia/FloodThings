"""Experimental, rule-based flood and drainage risk index for Karnataka.

Transparent factor scoring on real, timestamped inputs (Open-Meteo rainfall, GloFAS
river discharge, Copernicus elevation, Global Flood Database history, approved
citizen reports). It is not a trained flood-occurrence model, a calibrated
probability or an official warning (Phase 12G NO-GO stands). Missing inputs are
reported as unavailable and never scored as zero risk.
"""
import asyncio
import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .home_sources import SourceFailure, read_json
from .weather import number
from .shelters import authorized

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_FILE = ROOT / 'frontend/src/data/karnatakaHomeBoundary.json'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
FLOOD_URL = 'https://flood-api.open-meteo.com/v1/flood'
ELEVATION_URL = 'https://api.open-meteo.com/v1/elevation'
GRID_STEP = 0.25
GRID_CHUNK = 20  # ~5 s per provider request; 50 locations reach the shared 10 s timeout.
GRID_CONCURRENCY = 2  # Open-Meteo answers bursts of parallel multi-location calls with 503 "overloaded".
GRID_TTL = 3 * 3600
PARTIAL_TTL = 10 * 60  # A partly failed grid is retried soon instead of being served for three hours.
RETRY_DELAYS = (2, 5)  # Seconds before the second and third attempt of a transient provider failure.
TRANSIENT = {'provider_unavailable', 'rate_limited', 'timeout', 'network_failure'}
AREA_STEP = 0.05  # ~5.5 km; the area screen covers a 7 x 7 window (about 33 km across).
AREA_HALF = 3
AREA_REPORT_RADIUS_M = 2500
AREA_PLACE_RADIUS_M = 3000
POINT_TTL = 30 * 60
HISTORY_YEARS = (2015, 2024)  # Ten complete years keeps history at ~260 weighted API calls per cell.
LABEL = 'Experimental risk index — rule-based, not validated against flood outcomes. Not an official warning.'
RIVER_LABEL = 'Nearest GloFAS model grid cell (~5 km); river identity not verified.'
LEVELS = ((6, 'severe'), (4, 'high'), (2, 'moderate'), (0, 'low'))
IMD = ((204.5, 4, 'extremely heavy'), (115.6, 3, 'very heavy'), (64.5, 2, 'heavy'), (15.6, 1, 'moderate'), (0, 0, 'light or none'))
IMD_URL = 'https://rsmcnewdelhi.imd.gov.in/uploads/archive/8/8_f9822f_heavy%20rainfall%201506.pdf'
SOURCES = {
    'rain': {'name': 'Open-Meteo Forecast API', 'url': 'https://open-meteo.com/en/docs', 'license': 'CC BY 4.0'},
    'river': {'name': 'Open-Meteo Flood API (Copernicus GloFAS v4)', 'url': 'https://open-meteo.com/en/docs/flood-api', 'license': 'CC BY 4.0'},
    'elevation': {'name': 'Open-Meteo Elevation API (Copernicus GLO-90)', 'url': 'https://open-meteo.com/en/docs/elevation-api', 'license': 'Copernicus DEM licence; attribution required'},
    'history': {'name': 'Global Flood Database V1 (Udupi 2005, 2009)', 'url': 'https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1', 'license': 'CC BY-NC 4.0'},
    'reports': {'name': 'FloodPulse approved citizen reports', 'url': None, 'license': 'Private moderated evidence; counts only'},
    'thresholds': {'name': 'IMD rainfall intensity categories', 'url': IMD_URL, 'license': 'Official classification'},
}


# ---------- pure scoring ----------

def level(score):
    return next(name for minimum, name in LEVELS if score >= minimum)


def imd_category(mm):
    return next((points, name) for minimum, points, name in IMD if mm >= minimum)


def factor(key, name, value, unit, points, max_points, status='available', detail='', source=None):
    return {'id': key, 'name': name, 'value': value, 'unit': unit, 'points': points if status == 'available' else 0,
            'max_points': max_points, 'status': status, 'detail': detail, 'source': SOURCES.get(source or key)}


def rain_factors(rain):
    """rain: dict(next24_mm, past5d_mm, peak_mmh) or None when unavailable."""
    if rain is None:
        missing = 'Rainfall forecast unavailable; risk cannot be assessed.'
        return (factor('rain24', 'Forecast rain, next 24 h', None, 'mm', 0, 4, 'unavailable', missing, 'rain'),
                factor('rain5d', 'Rain in the past 5 days', None, 'mm', 0, 2, 'unavailable', missing, 'rain'),
                factor('intensity', 'Peak hourly rain, next 24 h', None, 'mm/h', 0, 2, 'unavailable', missing, 'rain'))
    points, category = imd_category(rain['next24_mm'])
    past = rain['past5d_mm']
    past_points = 2 if past >= 150 else 1 if past >= 50 else 0
    peak = rain['peak_mmh']
    peak_points = 2 if peak >= 20 else 1 if peak >= 10 else 0
    return (factor('rain24', 'Forecast rain, next 24 h', round(rain['next24_mm'], 1), 'mm', points, 4,
                   detail=f'IMD category: {category}.', source='rain'),
            factor('rain5d', 'Rain in the past 5 days', round(past, 1), 'mm', past_points, 2,
                   detail='Saturated ground floods sooner (project thresholds: 50 mm, 150 mm).', source='rain'),
            factor('intensity', 'Peak hourly rain, next 24 h', round(peak, 1), 'mm/h', peak_points, 2,
                   detail='Intense bursts overwhelm drains (project thresholds: 10, 20 mm/h).', source='rain'))


def river_factor(river):
    if river is None or river.get('status') != 'available':
        return factor('river', 'River flow, next 4 days', None, 'm³/s', 0, 3, 'unavailable',
                      (river or {}).get('message', 'River model unavailable.'))
    peak, rl2, rl5 = river['forecast_max'], river['rl2'], river['rl5']
    if rl2 < 1:
        return factor('river', 'River flow, next 4 days', round(peak, 1), 'm³/s', 0, 3, 'available',
                      f'No significant modelled river at this grid cell (2-year level {rl2:.1f} m³/s). {RIVER_LABEL}')
    points = 3 if peak >= rl5 else 2 if peak >= rl2 else 0
    return factor('river', 'River flow, next 4 days', round(peak, 1), 'm³/s', points, 3,
                  detail=f'2-year level {rl2:.0f} m³/s, 5-year level {rl5:.0f} m³/s (Gumbel fit, {HISTORY_YEARS[0]}–{HISTORY_YEARS[1]} annual maxima). {RIVER_LABEL}')


def elevation_factor(metres):
    if metres is None:
        return factor('elevation', 'Ground height', None, 'm', 0, 1, 'unavailable', 'Elevation unavailable.')
    return factor('elevation', 'Ground height', round(metres), 'm', 1 if metres < 10 else 0, 1,
                  detail='Below 10 m counts as low-lying (90 m terrain grid).')


def history_factor(history):
    if history is None:
        return factor('history', 'Mapped historical flood within 1 km', None, '', 0, 1, 'no_data',
                      'Historical flood maps are available for Udupi district only; no data here is not zero risk.')
    return factor('history', 'Mapped historical flood within 1 km', 'yes' if history else 'no', '', 1 if history else 0, 1,
                  detail='Satellite-mapped floodwater, September 2005 and September–October 2009.')


def reports_factor(count, radius_km=1):
    name = f'Approved flooding/drainage reports within {radius_km:g} km (72 h)'
    if count is None:
        return factor('reports', name, None, 'reports', 0, 2, 'unavailable', 'Report database unavailable.')
    return factor('reports', name, count, 'reports',
                  2 if count >= 3 else 1 if count >= 1 else 0, 2, detail='Only administrator-approved reports count.')


def summarise(factors):
    if any(f['id'] == 'rain24' and f['status'] != 'available' for f in factors):
        return {'level': 'unavailable', 'score': None, 'max_score': sum(f['max_points'] for f in factors),
                'partial': True, 'factors': factors}
    score = sum(f['points'] for f in factors)
    return {'level': level(score), 'score': score, 'max_score': sum(f['max_points'] for f in factors),
            'partial': any(f['status'] == 'unavailable' for f in factors), 'factors': factors}


def assess(rain, river=None, elevation=None, history=None, reports=None, point_detail=True, include_river=True, report_radius_km=1):
    rain24, rain5d, intensity = rain_factors(rain)
    flood = [rain24, rain5d]
    drainage = [{**rain24, 'points': min(rain24['points'], 2), 'max_points': 2}, intensity]
    if point_detail:
        flood += ([river_factor(river)] if include_river else []) + [elevation_factor(elevation), history_factor(history)]
        drainage += [reports_factor(reports, report_radius_km), elevation_factor(elevation)]
    return {'flood': summarise(flood), 'drainage': summarise(drainage)}


def gumbel_levels(annual_maxima):
    """Method-of-moments Gumbel fit; returns (2-year, 5-year) return levels."""
    mean, sd = statistics.mean(annual_maxima), statistics.stdev(annual_maxima)
    alpha = sd * math.sqrt(6) / math.pi
    mu = mean - 0.5772156649 * alpha
    rl = lambda years: mu - alpha * math.log(-math.log(1 - 1 / years))
    return rl(2), rl(5)


# ---------- input parsing ----------

def parse_rain(payload, now):
    """Hourly precipitation (sum over the hour ending at each timestamp), unixtime GMT."""
    hourly = payload['hourly']
    if payload.get('hourly_units', {}).get('precipitation') != 'mm':
        raise ValueError('Unexpected precipitation units')
    series = dict(zip(hourly['time'], hourly['precipitation']))
    now_s = int(now.timestamp())
    start = (now_s // 3600 + 1) * 3600  # next full hour
    future = [series.get(start + 3600 * i) for i in range(1, 25)]
    past = [series.get((now_s // 3600) * 3600 - 3600 * i) for i in range(0, 120)]
    if any(v is None for v in future + past):
        raise ValueError('Incomplete hourly rainfall window')
    future = [number(v, minimum=0) for v in future]
    past = [number(v, minimum=0) for v in past]
    return {'next24_mm': sum(future), 'past5d_mm': sum(past), 'peak_mmh': max(future),
            'window_start': datetime.fromtimestamp(start, timezone.utc).isoformat(),
            'window_end': datetime.fromtimestamp(start + 86400, timezone.utc).isoformat()}


def rain_params(latitudes, longitudes):
    return {'latitude': ','.join(f'{v:.4f}' for v in latitudes), 'longitude': ','.join(f'{v:.4f}' for v in longitudes),
            'hourly': 'precipitation', 'past_days': 6, 'forecast_days': 3, 'timezone': 'GMT', 'timeformat': 'unixtime'}


def annual_maxima(payload):
    daily = payload['daily']
    if payload.get('daily_units', {}).get('river_discharge') != 'm³/s':
        raise ValueError('Unexpected discharge units')
    years = {}
    for day, value in zip(daily['time'], daily['river_discharge']):
        if value is not None:
            years.setdefault(day[:4], []).append(number(value, minimum=0))
    complete = {y: max(v) for y, v in years.items() if len(v) >= 300}
    if len(complete) < 8:
        raise ValueError('Fewer than eight complete years of discharge')
    return complete


# ---------- geography ----------

def load_boundary(path=BOUNDARY_FILE):
    return json.loads(Path(path).read_text())['geometry']


def _in_ring(lon, lat, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def inside(geometry, latitude, longitude):
    """Point-in-polygon with holes (ray casting); no accuracy margin."""
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    return any(_in_ring(longitude, latitude, poly[0]) and not any(_in_ring(longitude, latitude, h) for h in poly[1:])
               for poly in polygons)


def statewide_grid(geometry, step=GRID_STEP):
    cells = []
    lat = 11.5 + step / 2
    while lat < 18.5:
        lon = 74.0 + step / 2
        while lon < 78.7:
            if inside(geometry, lat, lon):
                cells.append({'id': f'g{lat:.3f}_{lon:.3f}', 'latitude': round(lat, 3), 'longitude': round(lon, 3)})
            lon += step
        lat += step
    return cells


def distance_m(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def historical_context_many(points):
    """Per point: True/False within Udupi coverage, None outside it (no data, not zero risk)."""
    from .historical import HistoricalStore, HistoricalUnavailable
    try:
        catalogue, geometries = HistoricalStore().load()
    except HistoricalUnavailable:
        return [None] * len(points)
    centres = []
    for collection in geometries.values():
        for feature in collection['features']:
            polygons = feature['geometry']['coordinates']
            polygons = [polygons] if feature['geometry']['type'] == 'Polygon' else polygons
            for polygon in polygons:
                ring = polygon[0]
                centres.append((sum(p[1] for p in ring[:-1]) / (len(ring) - 1), sum(p[0] for p in ring[:-1]) / (len(ring) - 1)))
    boundary = catalogue['boundary']['geometry']
    return [None if not inside(boundary, lat, lon) else any(distance_m(lat, lon, a, b) <= 1000 for a, b in centres)
            for lat, lon in points]


def historical_context(latitude, longitude):
    return historical_context_many([(latitude, longitude)])[0]


def approved_report_counts(points, radius_m=1000, hours=72):
    """Counts only; never exposes report content. None when the database is unavailable."""
    from sqlalchemy import text
    from .shelters import shelter_engine, mode
    query = text("SELECT count(*) FROM citizen_reports WHERE state='APPROVED' AND demonstration=:demo "
                 "AND event_type IN ('flooding','waterlogging','drainage_blockage') "
                 "AND reviewed_at > now() - make_interval(hours => :hours) "
                 "AND ST_DWithin(position::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :radius)")
    try:
        engine = shelter_engine()
        with engine.connect().execution_options(postgresql_readonly=True) as c:
            return [c.execute(query, {'demo': mode() == 'demonstration', 'hours': hours, 'lon': lon, 'lat': lat,
                                      'radius': radius_m}).scalar_one() for lat, lon in points]
    except Exception:  # Database absence must not invent a zero count.
        return None


def approved_report_count(latitude, longitude, radius_m=1000, hours=72):
    counts = approved_report_counts([(latitude, longitude)], radius_m, hours)
    return None if counts is None else counts[0]


COMPASS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')


def direction(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    y = math.sin((lon2 - lon1) * p) * math.cos(lat2 * p)
    x = math.cos(lat1 * p) * math.sin(lat2 * p) - math.sin(lat1 * p) * math.cos(lat2 * p) * math.cos((lon2 - lon1) * p)
    return COMPASS[round((math.degrees(math.atan2(y, x)) % 360) / 45) % 8]


def area_points(geometry, latitude, longitude, step=AREA_STEP, half=AREA_HALF):
    """Fixed 0.05 degree lattice around the point (stable for caching); cells outside Karnataka are skipped."""
    lat0, lon0 = round(latitude / step) * step, round(longitude / step) * step
    cells = []
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            lat, lon = round(lat0 + i * step, 3), round(lon0 + j * step, 3)
            if inside(geometry, lat, lon):
                cells.append({'id': f'a{lat:.3f}_{lon:.3f}', 'latitude': lat, 'longitude': lon})
    return (round(lat0, 3), round(lon0, 3)), cells


def directory_places():
    """Selectable named localities from the active public directory; empty when unavailable."""
    from .locations import get_store, LocationsUnavailable
    try:
        data = get_store().load()
    except LocationsUnavailable:
        return []
    return [{'name': r['name'], 'latitude': r['coordinates']['latitude'], 'longitude': r['coordinates']['longitude']}
            for r in data['localities'] if r.get('selectable') and r.get('coordinates')]


def reasons(result):
    return [f['name'] for f in sorted(result['factors'], key=lambda f: -f['points']) if f['status'] == 'available' and f['points'] > 0]


# ---------- service ----------

class RiskService:
    def __init__(self, client, cache_dir=None, clock=time.time, geometry=None, sleep=asyncio.sleep):
        self.client, self.clock, self.sleep = client, clock, sleep
        self.geometry = geometry or load_boundary()
        self.cells = statewide_grid(self.geometry)
        self.cache_dir = Path(cache_dir or os.environ.get('FLOODPULSE_RISK_CACHE_DIR') or ROOT / 'data/tmp/risk_cache')
        self.grid_cache, self.point_cache, self.elevation_cache, self.river_history = None, {}, {}, {}
        self.grid_lock, self.point_locks = asyncio.Lock(), {}
        self.area_cache, self.area_locks = {}, {}

    def now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc)

    async def retrying(self, call):
        """Retry only transient provider failures, with bounded delays; other failures surface at once."""
        for delay in (*RETRY_DELAYS, None):
            try:
                return await call()
            except SourceFailure as exc:
                if delay is None or exc.kind not in TRANSIENT:
                    raise
                await self.sleep(max(delay, min(exc.retry_seconds or 0, 10)))

    async def rain_many(self, points):
        return await self.retrying(lambda: self._rain_many(points))

    async def _rain_many(self, points):
        payload, _ = await read_json(self.client, FORECAST_URL, rain_params([p['latitude'] for p in points],
                                     [p['longitude'] for p in points]), limit=8 * 1024 * 1024)
        payloads = payload if isinstance(payload, list) else [payload]
        if len(payloads) != len(points):
            raise ValueError('Provider returned a different number of locations')
        now = self.now()
        results = []
        for body in payloads:
            try:
                results.append(parse_rain(body, now))
            except (ValueError, KeyError, TypeError):
                results.append(None)
        return results

    async def grid(self):
        async with self.grid_lock:
            if self.grid_cache and self.grid_cache['expires'] > self.clock():
                return self.grid_cache['body']
            retrieved = self.now()
            chunks = [self.cells[i:i + GRID_CHUNK] for i in range(0, len(self.cells), GRID_CHUNK)]
            gate = asyncio.Semaphore(GRID_CONCURRENCY)

            async def fetch(chunk):
                async with gate:
                    try:
                        return await self.rain_many(chunk)
                    except (SourceFailure, ValueError, KeyError, TypeError):
                        return [None] * len(chunk)
            cells = []
            for chunk, rains in zip(chunks, await asyncio.gather(*(fetch(c) for c in chunks))):
                for cell, rain in zip(chunk, rains):
                    result = assess(rain, point_detail=False)['flood']
                    cells.append({**cell, 'level': result['level'], 'score': result['score'],
                                  'rain_24h_mm': rain and round(rain['next24_mm'], 1),
                                  'rain_5d_mm': rain and round(rain['past5d_mm'], 1),
                                  'peak_mmh': rain and round(rain['peak_mmh'], 1)})
            available = sum(c['level'] != 'unavailable' for c in cells)
            body = {'status': 'available' if available == len(cells) else 'partial' if available else 'unavailable',
                    'experimental': True, 'label': LABEL, 'kind': 'rain_only_grid',
                    'note': 'Statewide grid uses rainfall factors only; open a point for river, terrain, history and reports.',
                    'cell_size_degrees': GRID_STEP, 'cells': cells, 'retrieved_at': retrieved.isoformat(),
                    'fresh_until': (retrieved + timedelta(seconds=GRID_TTL if available else 60)).isoformat(),
                    'sources': [SOURCES['rain'], SOURCES['thresholds']]}
            ttl = GRID_TTL if available == len(cells) else PARTIAL_TTL if available else 60
            body['fresh_until'] = (retrieved + timedelta(seconds=ttl)).isoformat()
            self.grid_cache = {'expires': self.clock() + ttl, 'body': body}
            return body

    async def elevation(self, latitude, longitude):
        key = (round(latitude, 2), round(longitude, 2))
        if key not in self.elevation_cache:
            try:
                payload, _ = await read_json(self.client, ELEVATION_URL, {'latitude': latitude, 'longitude': longitude})
                self.elevation_cache[key] = number(payload['elevation'][0], minimum=-500, maximum=9000)
            except (SourceFailure, ValueError, KeyError, TypeError, IndexError):
                return None
        return self.elevation_cache[key]

    async def elevation_many(self, points):
        """Batch elevation lookup (provider maximum 100 coordinates); None entries when unavailable."""
        keys = [(round(lat, 2), round(lon, 2)) for lat, lon in points]
        missing = sorted({k for k in keys if k not in self.elevation_cache})
        for i in range(0, len(missing), 100):
            chunk = missing[i:i + 100]
            try:
                payload, _ = await self.retrying(lambda: read_json(self.client, ELEVATION_URL, {
                    'latitude': ','.join(f'{k[0]:.2f}' for k in chunk), 'longitude': ','.join(f'{k[1]:.2f}' for k in chunk)}))
                values = payload['elevation']
                if len(values) != len(chunk):
                    raise ValueError('Elevation count mismatch')
                for k, v in zip(chunk, values):
                    self.elevation_cache[k] = number(v, minimum=-500, maximum=9000)
            except (SourceFailure, ValueError, KeyError, TypeError, IndexError):
                continue
        return [self.elevation_cache.get(k) for k in keys]

    async def area(self, latitude, longitude):
        """Screen the ~33 km window around a point: rain, ground height, history and approved reports per cell.

        River flow is excluded here (one GloFAS history per cell is too costly); it is in the point assessment."""
        if not inside(self.geometry, latitude, longitude):
            raise HTTPException(422, 'Point is outside Karnataka')
        centre, cells = area_points(self.geometry, latitude, longitude)
        async with self.area_locks.setdefault(centre, asyncio.Lock()):
            cached = self.area_cache.get(centre)
            if not (cached and cached['expires'] > self.clock()):
                retrieved = self.now()
                rains = []
                for i in range(0, len(cells), 25):
                    chunk = cells[i:i + 25]
                    try:
                        rains += await self.rain_many(chunk)
                    except (SourceFailure, ValueError, KeyError, TypeError):
                        rains += [None] * len(chunk)
                coords = [(c['latitude'], c['longitude']) for c in cells]
                elevations = await self.elevation_many(coords)
                history = await run_in_threadpool(historical_context_many, coords)
                reports = await run_in_threadpool(approved_report_counts, coords, AREA_REPORT_RADIUS_M)
                places = await run_in_threadpool(directory_places)
                scored = []
                for n, cell in enumerate(cells):
                    rain = rains[n]
                    result = assess(rain, None, elevations[n], history[n], None if reports is None else reports[n],
                                    include_river=False, report_radius_km=AREA_REPORT_RADIUS_M / 1000)
                    near = min(((distance_m(cell['latitude'], cell['longitude'], p['latitude'], p['longitude']), p['name']) for p in places), default=None)
                    scored.append({**cell, 'place': near[1] if near and near[0] <= AREA_PLACE_RADIUS_M else None,
                                   'flood': {k: result['flood'][k] for k in ('level', 'score', 'max_score', 'partial')} | {'reasons': reasons(result['flood'])},
                                   'drainage': {k: result['drainage'][k] for k in ('level', 'score', 'max_score', 'partial')} | {'reasons': reasons(result['drainage'])},
                                   'inputs': {'rain_24h_mm': rain and round(rain['next24_mm'], 1), 'rain_5d_mm': rain and round(rain['past5d_mm'], 1),
                                              'peak_mmh': rain and round(rain['peak_mmh'], 1), 'elevation_m': None if elevations[n] is None else round(elevations[n]),
                                              'historical_flood': history[n], 'approved_reports': None if reports is None else reports[n]}})
                available = sum(c['flood']['level'] != 'unavailable' for c in scored)
                ttl = POINT_TTL if available == len(scored) else PARTIAL_TTL if available else 60
                window = next((r for r in rains if r), None)
                cached = {'expires': self.clock() + ttl, 'cells': scored, 'available': available, 'retrieved': retrieved, 'ttl': ttl,
                          'window': window and {'start': window['window_start'], 'end': window['window_end']}}
                self.area_cache[centre] = cached
        out = []
        for cell in cached['cells']:
            d = distance_m(latitude, longitude, cell['latitude'], cell['longitude'])
            out.append({**cell, 'distance_km': round(d / 1000, 1), 'direction': None if d < 500 else direction(latitude, longitude, cell['latitude'], cell['longitude'])})
        status = 'available' if cached['available'] == len(out) else 'partial' if cached['available'] else 'unavailable'
        return {'status': status, 'experimental': True, 'official_warning': False, 'label': LABEL, 'kind': 'area_screen',
                'note': 'Area screen uses rainfall, ground height, mapped historical floods and approved reports. '
                        'River flow is checked only in the full assessment of a chosen place.',
                'location': {'latitude': latitude, 'longitude': longitude}, 'cell_size_degrees': AREA_STEP,
                'rain_window': cached['window'], 'cells': out, 'retrieved_at': cached['retrieved'].isoformat(),
                'fresh_until': (cached['retrieved'] + timedelta(seconds=cached['ttl'])).isoformat(),
                'level_scale': '0–1 low · 2–3 moderate · 4–5 high · 6+ severe',
                'sources': [SOURCES['rain'], SOURCES['elevation'], SOURCES['history'], SOURCES['reports'], SOURCES['thresholds']]}

    def history_file(self, key):
        return self.cache_dir / f'glofas_{key[0]:.2f}_{key[1]:.2f}_{HISTORY_YEARS[0]}_{HISTORY_YEARS[1]}.json'

    async def river_levels(self, latitude, longitude):
        key = (round(latitude * 20) / 20, round(longitude * 20) / 20)  # GloFAS v4 0.05° cell
        if key in self.river_history:
            return self.river_history[key]
        path = self.history_file(key)
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            payload, sha = await read_json(self.client, FLOOD_URL, {'latitude': key[0], 'longitude': key[1],
                'daily': 'river_discharge', 'start_date': f'{HISTORY_YEARS[0]}-01-01',
                'end_date': f'{HISTORY_YEARS[1]}-12-31'}, limit=2 * 1024 * 1024)
            maxima = annual_maxima(payload)
            rl2, rl5 = gumbel_levels(list(maxima.values()))
            record = {'query': key, 'grid': [payload['latitude'], payload['longitude']], 'annual_maxima': maxima,
                      'rl2': rl2, 'rl5': rl5, 'response_sha256': sha, 'retrieved_at': self.now().isoformat()}
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        self.river_history[key] = record
        return record

    async def river(self, latitude, longitude):
        try:
            record = await self.river_levels(latitude, longitude)
            payload, _ = await read_json(self.client, FLOOD_URL, {'latitude': record['query'][0], 'longitude': record['query'][1],
                                         'daily': 'river_discharge', 'forecast_days': 4})
            values = [number(v, minimum=0) for v in payload['daily']['river_discharge'] if v is not None]
            if not values:
                raise ValueError('No forecast discharge')
            return {'status': 'available', 'forecast_max': max(values), 'rl2': record['rl2'], 'rl5': record['rl5'],
                    'grid': record['grid']}
        except (SourceFailure, ValueError, KeyError, TypeError) as exc:
            return {'status': 'unavailable', 'message': f'River model unavailable ({getattr(exc, "kind", "invalid data")}).'}

    async def point(self, latitude, longitude):
        if not inside(self.geometry, latitude, longitude):
            raise HTTPException(422, 'Point is outside Karnataka')
        key = (round(latitude, 2), round(longitude, 2))
        async with self.point_locks.setdefault(key, asyncio.Lock()):
            cached = self.point_cache.get(key)
            if cached and cached['expires'] > self.clock():
                return cached['body']
            retrieved = self.now()
            try:
                rain = (await self.rain_many([{'latitude': latitude, 'longitude': longitude}]))[0]
            except (SourceFailure, ValueError, KeyError, TypeError):
                rain = None
            river, elevation = await asyncio.gather(self.river(latitude, longitude), self.elevation(latitude, longitude))
            history = await run_in_threadpool(historical_context, latitude, longitude)
            reports = await run_in_threadpool(approved_report_count, latitude, longitude)
            result = assess(rain, river, elevation, history, reports)
            body = {'status': 'available' if rain else 'unavailable', 'experimental': True, 'label': LABEL,
                    'location': {'latitude': latitude, 'longitude': longitude},
                    'rain_window': rain and {'start': rain['window_start'], 'end': rain['window_end']},
                    **result, 'retrieved_at': retrieved.isoformat(),
                    'fresh_until': (retrieved + timedelta(seconds=POINT_TTL if rain else 60)).isoformat(),
                    'level_scale': '0–1 low · 2–3 moderate · 4–5 high · 6+ severe',
                    'official_warning': False}
            self.point_cache[key] = {'expires': self.clock() + (POINT_TTL if rain else 60), 'body': body}
            return body


def suggestions(grid, limit=10):
    """Draft alert suggestions from High/Severe grid cells. Never sends anything."""
    hot = sorted((c for c in grid['cells'] if c['level'] in ('high', 'severe')), key=lambda c: -(c['score'] or 0))[:limit]
    out = []
    for c in hot:
        message = (f"FloodPulse experimental risk notice ({c['level'].upper()}): about {c['rain_24h_mm']} mm of rain is forecast "
                   f"in the next 24 hours near {c['latitude']:.2f}°N, {c['longitude']:.2f}°E, after {c['rain_5d_mm']} mm in the past 5 days. "
                   "Avoid low-lying roads and drains, keep emergency supplies ready and follow official IMD/KSNDMC and district advice. "
                   "This is not an official warning.")
        out.append({'cell_id': c['id'], 'latitude': c['latitude'], 'longitude': c['longitude'], 'level': c['level'],
                    'score': c['score'], 'suggested_kind': 'informational', 'suggested_message': message})
    return {'status': grid['status'], 'retrieved_at': grid['retrieved_at'], 'suggestions': out,
            'note': 'Suggestions only. An administrator must edit, preview and explicitly approve before anything is sent.'}


def service(request: Request) -> RiskService:
    return request.app.state.risk


def no_store(body, status=200):
    return JSONResponse(status_code=status, content=body, headers={'Cache-Control': 'no-store'})


@router.get('/api/risk')
async def point_risk(latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
                     longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
                     risk: RiskService = Depends(service)):
    body = await risk.point(latitude, longitude)
    return no_store(body, 200 if body['status'] == 'available' else 503)


@router.get('/api/risk/area')
async def area_risk(latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
                    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
                    risk: RiskService = Depends(service)):
    body = await risk.area(latitude, longitude)
    return no_store(body, 503 if body['status'] == 'unavailable' else 200)


@router.get('/api/risk/grid')
async def grid_risk(risk: RiskService = Depends(service)):
    body = await risk.grid()
    return no_store(body, 503 if body['status'] == 'unavailable' else 200)


@router.get('/api/admin/risk/suggestions')
async def risk_suggestions(actor=Depends(authorized), risk: RiskService = Depends(service)):
    return no_store(suggestions(await risk.grid()))
