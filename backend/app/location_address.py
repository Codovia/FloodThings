"""Place name with PIN code, and street address, for a located or tapped point (OpenStreetMap Nominatim).

Requested by the browser once the person has allowed location or tapped the map. The point is sent in the request body (never in a URL or log), rounded to about 11 m before it leaves the
server, and not stored; the lookup shares the administrator lookup's application-wide limit and cache
(at most one Nominatim request per second, https://operations.osmfoundation.org/policies/nominatim/).
The address is only as precise as the location: no house number unless the fix is within 20 m, and only
the area (no street) when it is within 1 km. It is OpenStreetMap's nearest mapped address, not a verified
postal address; the PIN code is OpenStreetMap's, not India Post's, and is accepted only in the Karnataka
range (56xxxx-59xxxx). FLOODPULSE_ADDRESS_LOOKUP=off switches it off (for example at OSMF's request).
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
PLACE_ZOOM = 14  # Nominatim's village/suburb level: names the place when the detailed answer does not
LOCALITY_KEYS = ('neighbourhood', 'quarter', 'suburb', 'hamlet', 'village', 'city_district', 'city', 'town', 'municipality')


class AddressPoint(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # GPS radius; None for a spot tapped on the map.
    accuracy_m: float | None = Field(default=None, ge=0, le=10000000)


KARNATAKA_PIN = re.compile(r'5[6-9]\d{4}')


def pin(address):
    """Six-digit Karnataka PIN code from OpenStreetMap ('576 101' accepted), else None."""
    value = re.sub(r'\s', '', str(address.get('postcode') or ''))
    return value if KARNATAKA_PIN.fullmatch(value) else None


def village_name(address):
    return re.sub(r'\s*\(\d+\)$', '', clean(address.get('city_district')) or '') or None   # 'Haladi (76)': census code


def taluk_name(address):
    taluk = clean(address.get('county'))
    return taluk and (taluk if re.search(r'\b(taluk|taluka|taluku|tehsil)$', taluk, re.I) else f'{taluk} taluk')


def unique(parts):
    seen, out = set(), []
    for part in parts:
        if part and part.casefold() not in seen:
            seen.add(part.casefold()); out.append(part)
    return out


def place_label(address):
    """Short name like 'Brahmagiri, Udupi 576101': locality, town (or taluk) and PIN code."""
    local = next((v for k in ('neighbourhood', 'quarter', 'suburb', 'hamlet', 'village') if (v := clean(address.get(k)))), None) or village_name(address)
    town = next((v for k in ('city', 'town', 'municipality') if (v := clean(address.get(k)))), None) or taluk_name(address)
    code = pin(address)
    names = ', '.join(unique([local, town]))
    return ' '.join(p for p in (names, code) if p)[:200] or None


def compose(address):
    """Readable address, most specific first: street, locality, village, town, taluk, district, state, PIN."""
    village = village_name(address)
    street = ' '.join(p for p in (clean(address.get('house_number'), 20), clean(address.get('road'))) if p)
    district = clean(address.get('state_district'))
    out = unique([street, *(clean(address.get(k)) for k in ('neighbourhood', 'quarter', 'suburb', 'hamlet', 'village')), village,
                  next((v for k in ('city', 'town', 'municipality') if (v := clean(address.get(k)))), None), taluk_name(address),
                  district and (district if district.lower().endswith('district') else f'{district} district'), clean(address.get('state'))])
    code = pin(address)
    return (', '.join(out) + (f' {code}' if code else ''))[:1000] or None


def precision(accuracy_m):
    """(Nominatim zoom, precision label, address parts to drop) for a location's uncertainty."""
    if accuracy_m is None or accuracy_m <= HOUSE_NUMBER_M:
        return 18, 'street', ()
    if accuracy_m <= STREET_M:
        return 17, 'street', ('house_number',)
    return 14, 'area', ('house_number', 'road')


async def fill_place(lookup, point, address):
    """Village/locality and PIN from the place-level answer where the detailed one has none; failures change nothing."""
    try:
        body = await lookup.nominatim(round(point.latitude, 4), round(point.longitude, 4), 'address', zoom=PLACE_ZOOM, max_waiting=MAX_WAITING)
    except (OfficialUnavailable, ValueError, json.JSONDecodeError):
        return address
    place = body.get('address') if isinstance(body.get('address'), dict) else {}
    if str(place.get('country_code', '')).lower() != 'in':
        return address
    filled = dict(address)
    if not any(clean(address.get(k)) for k in LOCALITY_KEYS):
        filled.update({k: place[k] for k in LOCALITY_KEYS if clean(place.get(k))})
    if not pin(address) and pin(place):
        filled['postcode'] = place['postcode']
    return filled


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
    zoom, level, drop = precision(point.accuracy_m)
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
        level = 'area'
    if zoom != PLACE_ZOOM and (not any(clean(address.get(k)) for k in LOCALITY_KEYS) or not pin(address)):
        # The detailed answer is often an unnamed road with only the taluk; the village-level answer names the place.
        address = await fill_place(request.app.state.place_lookup, point, address)
    text = compose({k: v for k, v in address.items() if k not in drop})
    if not text or str(address.get('country_code', '')).lower() != 'in':
        return JSONResponse({**base, 'status': 'not_found', 'message': 'No address is mapped near this point.'}, headers=headers)
    return JSONResponse({**base, 'status': 'available', 'address': text, 'precision': level,
                         'place': place_label(address), 'postcode': pin(address),
                         'accuracy_m': None if point.accuracy_m is None else round(point.accuracy_m)}, headers=headers)
