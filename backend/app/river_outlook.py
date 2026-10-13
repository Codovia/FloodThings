"""Read-only, reach-gated Open-Meteo GloFAS pilot. No operational reach is approved.

Retained v5 screening is not a v4 channel review. Arbitrary user coordinates
never become river query points; only independently approved reach records do.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .home_geography import HomePoint, MAX_GPS_ACCURACY_M, covers_accuracy
from .home_sources import SourceFailure, read_json
from .weather import number

router = APIRouter()
FLOOD_URL = 'https://flood-api.open-meteo.com/v1/flood'
MODEL = 'forecast_v4'
PARAMS = {'daily': 'river_discharge,river_discharge_mean,river_discharge_p25,river_discharge_p75',
          'models': MODEL, 'forecast_days': 7, 'timezone': 'GMT'}
SOURCE = {'name': 'Open-Meteo / Copernicus GloFAS', 'url': 'https://open-meteo.com/en/docs/flood-api',
          'data_kind': 'external_modelled_river_forecast', 'requested_model': MODEL,
          'data_license': 'CC BY 4.0', 'terms_url': 'https://open-meteo.com/en/terms'}
NEARBY_UNAVAILABLE = 'Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.'
# Deliberately empty: no verified v4 reach/native-channel/viewing-area review.
APPROVED_REACHES = ()


def reviewed_reach(reach):
    try:
        if not (reach['review_status'] == 'independently_verified' and reach['public_display_rights'] is True and
                reach['model'] == MODEL and reach['grid_source']['model'] == MODEL and
                reach['grid_source']['review_status'] == 'verified_channel_and_topology' and
                re.fullmatch(r'[0-9a-f]{64}', reach['grid_source']['sha256']) and
                reach['grid_source']['url'].startswith('https://') and reach['geographic_source']['url'].startswith('https://') and
                reach['id'] and reach['name'] and reach['coverage_description']):
            return False
        geometry = reach['reach_geometry']
        if geometry['type'] != 'LineString' or len(geometry['coordinates']) < 2:
            return False
        for lon, lat in geometry['coordinates']:
            if number(lon, minimum=-180, maximum=180) is None or number(lat, minimum=-90, maximum=90) is None: return False
        for field in ('query_point', 'expected_grid'):
            if set(reach[field]) != {'latitude', 'longitude'}: return False
            HomePoint(**reach[field])
        return datetime.fromisoformat(reach['reviewed_at']).tzinfo is not None
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def parse_discharge(payload, retrieved_at):
    """Validate the requested model contract; native initialization metadata is unknown."""
    if isinstance(payload['utc_offset_seconds'], bool) or payload['utc_offset_seconds'] != 0 or payload['timezone'] not in {'GMT', 'UTC'}:
        raise ValueError('Original GMT model dates required')
    if payload.get('model', MODEL) != MODEL:
        raise ValueError('Unexpected echoed model')
    if payload.get('model_version') is not None and not re.fullmatch(r'4(?:\.\d+)*', str(payload['model_version'])):
        raise ValueError('Unexpected native model version')
    daily, units = payload['daily'], payload['daily_units']
    days = daily['time']
    expected = [(retrieved_at.astimezone(timezone.utc).date()+timedelta(days=i)).isoformat() for i in range(7)]
    if not isinstance(days, list) or days != expected or units.get('time') != 'iso8601':
        raise ValueError('Exactly seven ordered original GMT forecast dates required')
    grid = {'latitude': number(payload['latitude'], minimum=-90, maximum=90),
            'longitude': number(payload['longitude'], minimum=-180, maximum=180)}
    if None in grid.values(): raise ValueError('Missing river model grid')
    values, quality = {}, {}
    for variable in ('river_discharge', 'river_discharge_mean', 'river_discharge_p25', 'river_discharge_p75'):
        if variable not in daily:
            if variable == 'river_discharge': raise ValueError('Missing river discharge')
            values[variable], quality[variable] = [None]*7, 'unsupported_or_omitted'
            continue
        if units.get(variable) != 'm³/s' or not isinstance(daily[variable], list) or len(daily[variable]) != 7:
            raise ValueError('Incompatible discharge arrays or units')
        values[variable] = [number(v, minimum=0) for v in daily[variable]]
        quality[variable] = 'missing_values' if None in values[variable] else 'available'
    if all(v is None for v in values['river_discharge']): raise ValueError('No discharge values')
    rows = []
    for i, day in enumerate(days):
        row = {'date': day, **{k: v[i] for k, v in values.items()}}
        low, high = row['river_discharge_p25'], row['river_discharge_p75']
        if low is not None and high is not None and low > high: raise ValueError('Inverted ensemble interquartile range')
        # Ensemble mean can legitimately lie outside p25-p75; these are not bounds.
        rows.append(row)
    return {'status': 'partial' if any(v != 'available' for v in quality.values()) else 'available',
            'source': SOURCE, 'grid_location': grid, 'forecast': rows, 'units': 'm³/s',
            'timezone': 'GMT', 'date_semantics': 'original_model_daily_date_not_local_day',
            'retrieved_at': retrieved_at.isoformat(), 'forecast_issued_at': None,
            'observation_time': None, 'requested_model': MODEL,
            'model_metadata_status': 'request_pinned_native_version_and_issue_not_echoed',
            'field_quality': quality}


def validate_grid(body, reach):
    if not reviewed_reach(reach): raise ValueError('Reach review missing or incompatible model')
    # Serialization tolerance only; this is not a proximity-based river match.
    if any(abs(body['grid_location'][k]-reach['expected_grid'][k]) > .0001 for k in ('latitude', 'longitude')):
        raise ValueError('Provider grid differs from the independently reviewed cell')
    return {'id': reach['id'], 'name': reach['name'], 'verified_grid': True,
            'query_point': reach['query_point'], 'expected_grid': reach['expected_grid'],
            'coverage_description': reach['coverage_description'], 'reviewed_at': reach['reviewed_at'],
            'geographic_source': reach['geographic_source'], 'grid_source': reach['grid_source']}


class RiverOutlook:
    def __init__(self, client, reaches=APPROVED_REACHES, clock=time.monotonic):
        self.client, self.reaches, self.clock = client, tuple(reaches), clock
        if len(self.reaches) > 10: raise ValueError('Pilot reach bound exceeded')
        self.cache, self.locks = {}, {}

    async def outlook(self, point):
        base = {'source': SOURCE, 'nearby_flood_possibility': NEARBY_UNAVAILABLE,
                'official_warning_status': 'not_connected', 'forecast': [], 'reach': None,
                'retrieved_at': None, 'forecast_issued_at': None, 'observation_time': None}
        matches = [r for r in self.reaches if reviewed_reach(r) and covers_accuracy(r.get('viewing_geometry', {}), point.latitude, point.longitude, point.accuracy_m)]
        if point.accuracy_m > MAX_GPS_ACCURACY_M or len(matches) != 1:
            return {**base, 'status': 'unsupported', 'message': 'No uniquely verified GloFAS v4 river/reach and viewing-area association is available for this point.'}
        reach = matches[0]
        async with self.locks.setdefault(reach['id'], asyncio.Lock()):
            now = self.clock()
            if reach['id'] in self.cache and self.cache[reach['id']][0] > now:
                result = deepcopy(self.cache[reach['id']][1]); result['cache_status'] = 'fresh_cache'
            else:
                try:
                    async with asyncio.timeout(10):
                        for attempt in range(2):
                            try:
                                payload, sha = await read_json(self.client, FLOOD_URL, {**PARAMS, **reach['query_point']})
                                break
                            except SourceFailure as exc:
                                if attempt or exc.kind not in {'network_failure', 'timeout', 'provider_unavailable'} or (exc.retry_seconds or 0) > 1:
                                    raise
                                await asyncio.sleep(max(.25, exc.retry_seconds or 0))
                        retrieved = datetime.now(timezone.utc)
                        body = parse_discharge(payload, retrieved)
                        result = {**base, **body, 'reach': validate_grid(body, reach), 'response_sha256': sha,
                                  'cache_status': 'fresh_fetch', 'message': 'Modelled river discharge, not observed water level or a flood warning.'}
                        expires = min(3600, ((retrieved+timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)-retrieved).total_seconds())
                        result['fresh_until'] = (retrieved+timedelta(seconds=expires)).isoformat()
                except SourceFailure as exc:
                    result = {**base, 'status': 'unavailable', 'message': 'River forecast provider is unavailable.',
                              'failure_kind': exc.kind, 'upstream_status': exc.status, 'retry_after_seconds': exc.retry_seconds}
                    expires = max(30, exc.retry_seconds or 0)
                except TimeoutError:
                    result = {**base, 'status': 'unavailable', 'message': 'River forecast request timed out.', 'failure_kind': 'timeout'}
                    expires = 30
                except (ValueError, TypeError, KeyError, AttributeError):
                    result = {**base, 'status': 'unavailable', 'message': 'River forecast data or geographic association could not be validated.', 'failure_kind': 'invalid_or_unverified_response'}
                    expires = 30
                self.cache[reach['id']] = (self.clock()+expires, deepcopy(result))
        return {**result, 'viewing_point': point.model_dump()}


@router.post('/api/river-outlook')
async def river_outlook(point: HomePoint, request: Request):
    result = await request.app.state.river_outlook.outlook(point)
    return JSONResponse(content=result, headers={'Cache-Control': 'no-store'})
