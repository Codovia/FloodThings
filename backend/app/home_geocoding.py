"""MapTiler reverse geocoding: disabled without reviewed server access and quota.

GPS is POSTed, never written to disk. No public Nominatim fallback exists.
Names require the provider's locality polygon to cover the accuracy circle.
"""
import asyncio
from collections import OrderedDict, deque
from copy import deepcopy
import hmac
import json
import os
import re
import secrets
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .home_geography import GPSPoint, covers_accuracy
from .home_sources import SourceFailure, read_json

router = APIRouter()
CREDIT = {'provider': 'MapTiler', 'url': 'https://www.maptiler.com/copyright/',
          'data_credit_url': 'https://www.openstreetmap.org/copyright',
          'rights': 'MapTiler Cloud account terms; not a blanket open-data licence'}


def safe_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid place label')
    return value.strip()


def validate_name(feature, full_geometry, point):
    if feature.get('type') != 'Feature' or not set(feature.get('place_type', [])).intersection({'municipality', 'locality'}):
        raise ValueError('No supported locality')
    context = feature.get('context', [])
    country = next((r for r in context if r.get('id', '').startswith('country.')), {})
    region = next((r for r in context if r.get('id', '').startswith('region.')), {})
    if country.get('country_code', '').lower() != 'in' or region.get('text', '').casefold() != 'karnataka':
        raise ValueError('Supported state/country context unavailable')
    if full_geometry.get('id') != feature.get('id') or full_geometry.get('type') != 'Feature' or not covers_accuracy(full_geometry.get('geometry', {}), point.latitude, point.longitude, point.accuracy_m):
        raise ValueError('Locality geometry cannot resolve the accuracy area')
    locality = safe_name(feature.get('text'))
    subregion = next((r for r in context if r.get('id', '').startswith('subregion.')), {})
    label = safe_name(subregion['text']) if subregion.get('text') else None
    return {'status': 'available', 'locality_name': locality, 'context_label': label,
            'name': locality + (', ' + label if label else ''), 'source': CREDIT,
            'feature_id': feature['id'], 'accuracy_supported': True,
            'geometry_verification': 'provider_locality_polygon_covers_accuracy',
            'administrative_identity_status': 'provider_context_not_canonical_directory_join'}


class ReverseGeocoder:
    def __init__(self, client, environment=None, clock=time.monotonic):
        env = os.environ if environment is None else environment
        self.client, self.clock = client, clock
        self.key = env.get('MAPTILER_GEOCODING_KEY')
        try:
            self.quota = int(env.get('MAPTILER_GEOCODING_HOURLY_BUDGET', '0'))
        except ValueError:
            self.quota = 0
        self.enabled = bool(env.get('MAPTILER_REVERSE_ENABLED') == 'true' and env.get('MAPTILER_GEOCODING_RIGHTS_REVIEWED') == 'true' and self.key and 0 < self.quota <= 600)
        self.cache, self.calls, self.lock = OrderedDict(), deque(), asyncio.Lock()
        self.cooldown_until = 0
        self._cache_salt = secrets.token_bytes(32)

    async def resolve(self, point):
        if point.accuracy_m > 5000:
            return {'status': 'unsupported', 'message': 'Approximate location — select your town.', 'source': CREDIT}
        if not self.enabled:
            return {'status': 'disabled', 'message': 'Automatic place naming is not configured. Select your town to show a reviewed locality name.', 'source': CREDIT}
        async with self.lock:
            # Opaque process-local cache keys avoid retaining raw GPS coordinates.
            key = hmac.digest(self._cache_salt, json.dumps(point.model_dump(), sort_keys=True).encode(), 'sha256')
            now = self.clock()
            for k in list(self.cache):
                if self.cache[k][0] <= now: del self.cache[k]
            if key in self.cache: return deepcopy(self.cache[key][1])
            while self.calls and self.calls[0] <= now - 3600: self.calls.popleft()
            # Reserve two calls (reverse + full geometry), at most one job every 2s.
            if now < self.cooldown_until or len(self.calls) + 2 > self.quota or self.calls and now - self.calls[-1] < 2:
                return {'status': 'unavailable', 'message': 'Place-naming request budget reached. Select your town.', 'source': CREDIT}
            self.calls.extend([now, now])
            try:
                async with asyncio.timeout(10):
                    data, _ = await read_json(self.client, f'https://api.maptiler.com/geocoding/{point.longitude},{point.latitude}.json',
                                              {'key': self.key, 'types': 'municipality,locality', 'language': 'en'}, limit=65536)
                    if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list) or len(data['features']) > 10:
                        raise ValueError('Invalid reverse response')
                    candidates = [f for f in data['features'] if set(f.get('place_type', [])).intersection({'municipality', 'locality'})]
                    # More than one candidate requires review, not a nearest/first guess.
                    if len(candidates) != 1: raise ValueError('Ambiguous locality result')
                    feature = candidates[0]
                    if not isinstance(feature.get('id'), str) or not re.fullmatch(r'(?:municipality|locality)\.[A-Za-z0-9_-]+', feature['id']):
                        raise ValueError('Unsupported feature identifier')
                    geometry, _ = await read_json(self.client, f"https://api.maptiler.com/geocoding/{feature['id']}.json", {'key': self.key}, limit=1048576)
                    if geometry.get('type') == 'FeatureCollection' and len(geometry.get('features', [])) == 1:
                        geometry = geometry['features'][0]
                    result = validate_name(feature, geometry, point)
            except SourceFailure as exc:
                self.cooldown_until = self.clock() + max(60, exc.retry_seconds or 0)
                result = {'status': 'unavailable', 'message': 'Place-naming provider is unavailable. Select your town; your accepted GPS weather point is unchanged.', 'source': CREDIT}
            except (ValueError, TypeError, KeyError, AttributeError, TimeoutError):
                result = {'status': 'unavailable', 'message': 'A locality name could not be verified. Select your town; your accepted GPS weather point is unchanged.', 'source': CREDIT}
            self.cache[key] = (self.clock() + 60, result)
            while len(self.cache) > 64: self.cache.popitem(last=False)
            return deepcopy(result)


@router.post('/api/location/reverse')
async def reverse_location(point: GPSPoint, request: Request):
    result = await request.app.state.reverse_geocoder.resolve(point)
    return JSONResponse(content=result, headers={'Cache-Control': 'no-store'})


@router.get('/api/location/provider')
async def location_provider(request: Request):
    return JSONResponse({'provider': 'MapTiler' if request.app.state.reverse_geocoder.enabled else 'BigDataCloud'}, headers={'Cache-Control': 'no-store'})
