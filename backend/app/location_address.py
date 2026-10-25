"""Street address for a point, only when the person taps "Show address" (OpenStreetMap Nominatim).

The point is sent in the request body (never in a URL or log), rounded to about 11 m before it leaves the
server, and not stored; the lookup shares the administrator lookup's application-wide limit and cache
(at most one Nominatim request per second, https://operations.osmfoundation.org/policies/nominatim/).
The address is only as precise as the location: no house number unless the fix is within 20 m, and only
the area (no street) when it is within 1 km. It is OpenStreetMap's nearest mapped address, not a verified
postal address. FLOODPULSE_ADDRESS_LOOKUP=off switches it off (for example at OSMF's request).
"""
import json
import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .admin_place import ATTRIBUTION, POLICY_URL, clean, metres
from .official import OfficialUnavailable
from .risk import inside, load_boundary

router = APIRouter()
HOUSE_NUMBER_M, STREET_M, AREA_M = 20, 250, 1000
MAX_WAITING = 3  # requests queued behind the 1-per-second limit; more are told to try again


class AddressPoint(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # GPS radius; None for a spot tapped on the map.
    accuracy_m: float | None = Field(default=None, ge=0, le=10000000)


def compose(address):
    """Readable address, most specific first: street, locality, village, town, taluk, district, state, PIN."""
    village = re.sub(r'\s*\(\d+\)$', '', clean(address.get('city_district')) or '') or None   # 'Haladi (76)': census code
    street = ' '.join(p for p in (clean(address.get('house_number'), 20), clean(address.get('road'))) if p)
    taluk, district = clean(address.get('county')), clean(address.get('state_district'))
    parts = [street, *(clean(address.get(k)) for k in ('neighbourhood', 'quarter', 'suburb', 'hamlet', 'village')), village,
             next((v for k in ('city', 'town', 'municipality') if (v := clean(address.get(k)))), None),
             taluk and (taluk if re.search(r'\b(taluk|taluka|taluku|tehsil)$', taluk, re.I) else f'{taluk} taluk'),
             district and (district if district.lower().endswith('district') else f'{district} district'), clean(address.get('state'))]
    seen, out = set(), []
    for part in parts:
        if part and part.casefold() not in seen:
            seen.add(part.casefold()); out.append(part)
    postcode = clean(address.get('postcode'), 12)
    return (', '.join(out) + (f' {postcode}' if postcode else ''))[:1000] or None


def precision(accuracy_m):
    """(Nominatim zoom, precision label, address parts to drop) for a location's uncertainty."""
    if accuracy_m is None or accuracy_m <= HOUSE_NUMBER_M:
        return 18, 'street', ()
    if accuracy_m <= STREET_M:
        return 17, 'street', ('house_number',)
    return 14, 'area', ('house_number', 'road')


@router.post('/api/location/address')
async def location_address(point: AddressPoint, request: Request):
    headers = {'Cache-Control': 'no-store'}
    base = {'attribution': ATTRIBUTION, 'policy_url': POLICY_URL}
    if os.environ.get('FLOODPULSE_ADDRESS_LOOKUP', '').strip().lower() == 'off':
        return JSONResponse({**base, 'status': 'disabled', 'message': 'Address lookup is switched off on this server.'}, headers=headers)
    if point.accuracy_m is not None and point.accuracy_m > AREA_M:
        return JSONResponse({**base, 'status': 'too_imprecise', 'message': f'Your location is only known to ±{round(point.accuracy_m)} m, too rough for an address.'}, headers=headers)
    if not inside(load_boundary(), point.latitude, point.longitude):
        return JSONResponse({**base, 'status': 'outside', 'message': 'This point is outside Karnataka.'}, headers=headers)
    zoom, label, drop = precision(point.accuracy_m)
    try:
        body = await request.app.state.place_lookup.nominatim(round(point.latitude, 4), round(point.longitude, 4), 'address',
                                                              zoom=zoom, max_waiting=MAX_WAITING)
    except OfficialUnavailable as exc:
        if str(exc) == 'no place found here':
            return JSONResponse({**base, 'status': 'not_found', 'message': 'No address is mapped near this point.'}, headers=headers)
        busy = str(exc) == 'busy'
        return JSONResponse({**base, 'status': 'unavailable', 'message': 'Many people are looking up addresses; try again in a few seconds.' if busy else
                             'Address lookup is unavailable right now.'}, status_code=503, headers=headers)
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({**base, 'status': 'unavailable', 'message': 'Address lookup is unavailable right now.'}, status_code=503, headers=headers)
    address = body.get('address') if isinstance(body.get('address'), dict) else {}
    try:  # the nearest mapped street can be far away in villages; then only the area is meaningful
        if metres(point.latitude, point.longitude, float(body['lat']), float(body['lon'])) > STREET_M:
            drop = ('house_number', 'road')
    except (KeyError, TypeError, ValueError):
        drop = ('house_number', 'road')
    if 'road' in drop or not clean(address.get('road')):
        label = 'area'
    text = compose({k: v for k, v in address.items() if k not in drop})
    if not text or str(address.get('country_code', '')).lower() != 'in':
        return JSONResponse({**base, 'status': 'not_found', 'message': 'No address is mapped near this point.'}, headers=headers)
    return JSONResponse({**base, 'status': 'available', 'address': text, 'precision': label,
                         'accuracy_m': None if point.accuracy_m is None else round(point.accuracy_m)}, headers=headers)
