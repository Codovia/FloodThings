"""Administrator entrance lookup: district from IMD boundaries, place/address suggestion from OSM Nominatim.

The lookup below is shared with the public address button (location_address.py), so both stay within
one application-wide limit.
Nominatim usage policy (https://operations.osmfoundation.org/policies/nominatim/): at most one
request per second for the whole application, an identifying User-Agent, cached results,
visible OpenStreetMap attribution, no automatic/bulk/grid lookups. Results are suggestions the
administrator must confirm; nothing here verifies a facility.
"""
import asyncio
import os
import re
import json
import math
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from .official import DISTRICT_NAMES, OfficialUnavailable, read_bounded, statewide
from .risk import inside, load_boundary
from .shelters import authorized

router = APIRouter()
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
POLICY_URL = 'https://operations.osmfoundation.org/policies/nominatim/'
USER_AGENT = 'FloodPulse/2 (college project; Karnataka flood app; place and address lookup on user request)'
ATTRIBUTION = 'Place and address suggestion: © OpenStreetMap contributors, ODbL 1.0 (via Nominatim).'
NAMED_CATEGORIES = {'amenity', 'building', 'tourism', 'leisure', 'historic', 'office', 'healthcare', 'religion', 'education'}
CACHE_SIZE, CACHE_SECONDS, MIN_INTERVAL = 512, 24 * 3600, 1.1
NAME_RADIUS_M, NEARBY_RADIUS_M = 75, 300  # auto-fill a name only when the mapped place is at the click


def metres(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    return 6371000 * math.hypot((lon2 - lon1) * r * math.cos((lat1 + lat2) / 2 * r), (lat2 - lat1) * r)


def clean(value, limit=200):
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())
    return value[:limit] if value and not any(ord(c) < 32 for c in value) else None


def compose_address(address):
    """Readable address from Nominatim parts, most specific first, without duplicates."""
    street = ' '.join(p for p in (clean(address.get('house_number'), 20), clean(address.get('road'))) if p)
    parts = [street, *(clean(address.get(k)) for k in ('neighbourhood', 'suburb', 'hamlet', 'village')),
             next((v for k in ('city', 'town', 'municipality') if (v := clean(address.get(k)))), None),
             clean(address.get('state_district')), clean(address.get('state'))]
    seen, out = set(), []
    for part in parts:
        if part and part.casefold() not in seen:
            seen.add(part.casefold()); out.append(part)
    postcode = clean(address.get('postcode'), 12)
    text = ', '.join(out) + (f' {postcode}' if postcode else '')
    return text[:1000] or None


def district_names(display_name):
    for aliases in DISTRICT_NAMES.values():
        if display_name.casefold() in (a.casefold() for a in aliases):
            return aliases
    return [display_name]


class PlaceLookup:
    def __init__(self, client, clock=time.monotonic, sleep=asyncio.sleep):
        self.client, self.clock, self.sleep = client, clock, sleep
        self.cache, self.lock, self.last, self.waiting = OrderedDict(), asyncio.Lock(), None, 0

    async def nominatim(self, latitude, longitude, layer, zoom=18, max_waiting=None):
        key = (round(latitude, 5), round(longitude, 5), layer, zoom)
        hit = self.cache.get(key)
        if hit and self.clock() - hit[0] < CACHE_SECONDS:
            self.cache.move_to_end(key)
            return hit[1]
        if max_waiting is not None and self.waiting >= max_waiting:
            raise OfficialUnavailable('busy')
        self.waiting += 1
        try:
            async with self.lock:  # one request at a time, at most one per ~second, application-wide
                if self.last is not None and (wait := MIN_INTERVAL - (self.clock() - self.last)) > 0:
                    await self.sleep(wait)
                self.last = self.clock()
                raw = await read_bounded(self.client, NOMINATIM_URL, params={
                    'format': 'jsonv2', 'lat': f'{latitude:.6f}', 'lon': f'{longitude:.6f}', 'zoom': zoom,
                    'addressdetails': 1, 'accept-language': 'en', 'layer': layer}, limit=256 * 1024, timeout=10,
                    headers={'User-Agent': USER_AGENT})
        finally:
            self.waiting -= 1
        body = json.loads(raw)
        if not isinstance(body, dict) or body.get('error'):
            raise OfficialUnavailable('no place found here')
        self.cache[key] = (self.clock(), body)
        if len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)
        return body


@router.get('/api/admin/place')
async def admin_place(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                      actor=Depends(authorized)):
    headers = {'Cache-Control': 'no-store'}
    if not inside(load_boundary(), latitude, longitude):
        return JSONResponse({'status': 'outside', 'message': 'This point is outside Karnataka. Choose the entrance inside the state.'}, headers=headers)
    result = {'status': 'available', 'district': None, 'name': None, 'address': None, 'messages': [],
              'attribution': ATTRIBUTION, 'policy_url': POLICY_URL}
    districts, raw = await statewide(request.app.state.official)
    match = next((d for d in districts or [] if inside(d['geometry'], latitude, longitude)), None)
    if match:
        result['district'] = {'name': match['district'], 'aliases': district_names(match['district']),
                              'source': 'IMD district boundary (map service)'}
    elif districts is None:
        result['messages'].append(f'District boundaries are unavailable ({raw["error"]}); choose the district manually.')
    lookup = request.app.state.place_lookup
    try:
        # Nearest named place first; use it only when it is at the clicked entrance.
        poi = await lookup.nominatim(latitude, longitude, 'poi')
        name = clean(poi.get('name'))
        try:
            distance = metres(latitude, longitude, float(poi['lat']), float(poi['lon']))
        except (KeyError, TypeError, ValueError):
            distance = math.inf
        address = poi.get('address') if isinstance(poi.get('address'), dict) else {}
        if name and poi.get('category') in NAMED_CATEGORIES and distance <= NAME_RADIUS_M:
            result['name'] = {'value': name, 'kind': clean(poi.get('type'), 40), 'distance_m': round(distance), 'source': 'OpenStreetMap'}
        else:
            if name and poi.get('category') in NAMED_CATEGORIES and distance <= NEARBY_RADIUS_M:
                result['nearby'] = {'value': name, 'kind': clean(poi.get('type'), 40), 'distance_m': round(distance), 'source': 'OpenStreetMap'}
            near = await lookup.nominatim(latitude, longitude, 'address')
            address = near.get('address') if isinstance(near.get('address'), dict) else {}
        text = compose_address(address)
        result['address'] = {'value': text, 'source': 'OpenStreetMap'} if text else None
        if not result['district'] and (osm := clean(address.get('state_district'))):
            result['district'] = {'name': osm, 'aliases': district_names(osm), 'source': 'OpenStreetMap address'}
    except (OfficialUnavailable, ValueError):
        result['messages'].append('Place name and address lookup is unavailable right now; type them manually.')
    if not result['name'] and not any('unavailable right now' in m for m in result['messages']):
        result['messages'].append('No named building is mapped at this exact point; type the facility name.')
    return JSONResponse(result, headers=headers)


MAPTILER_KEY = re.compile(r'^[A-Za-z0-9]{16,64}$')


@router.get('/api/admin/map-config')
def admin_map_config(actor=Depends(authorized)):
    """Satellite/Hybrid imagery and building search for signed-in administrators. A MapTiler key is
    a public browser key (restrict it to this site's address in MapTiler); never reported unless well formed."""
    headers = {'Cache-Control': 'no-store'}
    key = os.environ.get('MAPTILER_PUBLIC_KEY', '').strip()
    if not key:
        return JSONResponse({'status': 'not_configured'}, headers=headers)
    if not MAPTILER_KEY.match(key):
        return JSONResponse({'status': 'invalid_configuration'}, headers=headers)
    return JSONResponse({'status': 'available', 'provider': 'maptiler', 'public_key': key}, headers=headers)
