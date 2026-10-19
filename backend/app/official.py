"""Official warnings, displayed as issued: IMD district warnings and NDMA SACHET CAP alerts.

FloodPulse does not create, rewrite or re-score these. It locates the user's IMD
district by point-in-polygon, decodes IMD's published warning and colour codes,
and lists active Karnataka CAP alerts. Failures are reported as unavailable;
missing data never means "no warning".
"""
import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .risk import inside, load_boundary
from .shelters import authorized

router = APIRouter()
IMD_WFS = 'https://reactjs.imd.gov.in/geoserver/wfs'
IMD_PARAMS = {'service': 'WFS', 'version': '1.0.0', 'request': 'GetFeature', 'typename': 'imd:district_warnings_india',
              'srsname': 'EPSG:4326', 'outputFormat': 'application/json', 'bbox': '74.0,11.5,78.6,18.5'}  # lon/lat order
IMD_PAGE = 'https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php'
IMD_CODES_URL = 'https://api.imd.gov.in/public/api_reference.html'
SACHET_RSS = 'https://sachet.ndma.gov.in/cap_public_website/rss/rss_karnataka.xml'
SACHET_PAGE = 'https://sachet.ndma.gov.in/'
CAP_NS = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
IMD_TTL, RSS_TTL, FAIL_TTL = 30 * 60, 10 * 60, 60
MAX_ALERTS = 15
LABEL = 'Official warnings as issued by IMD and NDMA SACHET. FloodPulse only displays them and does not change their content.'

# IMD API reference, "District-wise Warnings": warning codes and the Day colour table.
WARNING_CODES = {1: 'No warning', 2: 'Heavy rain', 3: 'Heavy snow', 4: 'Thunderstorm & lightning, squall etc', 5: 'Hailstorm',
                 6: 'Dust storm', 7: 'Dust raising winds', 8: 'Strong surface winds', 9: 'Heat wave', 10: 'Hot day',
                 11: 'Warm night', 12: 'Cold wave', 13: 'Cold day', 14: 'Ground frost', 15: 'Fog', 16: 'Very heavy rain',
                 17: 'Extremely heavy rain'}
RAIN_CODES = {2, 16, 17}
DAY_COLOURS = {1: 'red', 2: 'orange', 3: 'yellow', 4: 'green'}
COLOUR_MEANING = {'red': 'Warning (take action)', 'orange': 'Alert (be prepared)', 'yellow': 'Watch (be updated)', 'green': 'No warning'}

# Spellings used by IMD, SACHET and the FloodPulse directory for the same Karnataka district.
DISTRICT_NAMES = {
    'BAGALKOT': ['Bagalkot', 'Bagalkote'], 'BANGLORE RURAL': ['Bengaluru Rural', 'Bangalore Rural'],
    'BANGLORE URBAN': ['Bengaluru Urban', 'Bangalore Urban', 'Bengaluru', 'Bangalore'], 'BELGAUM': ['Belagavi', 'Belgaum'],
    'BELLARY': ['Ballari', 'Bellary'], 'BIDAR': ['Bidar'], 'BIJAAPUR': ['Vijayapura', 'Bijapur'],
    'CHAMARAJANAGAR': ['Chamarajanagar', 'Chamarajanagara'], 'CHIKBALLAPUR': ['Chikkaballapura', 'Chikkaballapur', 'Chikballapur'],
    'CHIKMAGALUR': ['Chikkamagaluru', 'Chikmagalur'], 'CHITRADURGA': ['Chitradurga'], 'DAKSHIN KANNADA': ['Dakshina Kannada'],
    'DAVANGERE': ['Davanagere', 'Davangere'], 'DHARWAD': ['Dharwad'], 'GADAG': ['Gadag'], 'GULBARGA': ['Kalaburagi', 'Gulbarga'],
    'HASSAN': ['Hassan'], 'HAVERI': ['Haveri'], 'KODAGU': ['Kodagu', 'Coorg'], 'KOLAR': ['Kolar'], 'KOPPAL': ['Koppal'],
    'MANDHYA': ['Mandya'], 'MYSORE': ['Mysuru', 'Mysore'], 'RAICHUR': ['Raichur'],
    'RAMNAGAR': ['Bengaluru South', 'Ramanagara', 'Ramanagar'], 'SHIMOGA': ['Shivamogga', 'Shimoga'],
    'TUMKUR': ['Tumakuru', 'Tumkur'], 'UDUPI': ['Udupi'], 'UTTAR KANNADA': ['Uttara Kannada'],
    'VIJAYANAGARA': ['Vijayanagara'], 'YADGIR': ['Yadgir'],
}


class OfficialUnavailable(Exception):
    pass


async def read_bounded(client, url, params=None, limit=4 * 1024 * 1024, timeout=20, headers=None):
    try:
        async with asyncio.timeout(timeout):
            async with client.stream('GET', url, params=params, headers=headers) as response:
                if not response.is_success:
                    raise OfficialUnavailable(f'HTTP {response.status_code}')
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > limit:
                        raise OfficialUnavailable('response too large')
                    raw.extend(chunk)
                return bytes(raw)
    except (TimeoutError, httpx.TimeoutException):
        raise OfficialUnavailable('timeout') from None
    except httpx.HTTPError:
        raise OfficialUnavailable('network failure') from None


def safe_xml(raw):
    # CAP and RSS need no DTDs; refusing them blocks entity-expansion and external-entity tricks.
    head = raw[:4096].upper()
    if b'<!DOCTYPE' in head or b'<!ENTITY' in raw.upper():
        raise OfficialUnavailable('XML with DTD or entities refused')
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise OfficialUnavailable('invalid XML') from None


# ---------- IMD district warnings ----------

def decode_day(codes, colour, day):
    numbers = []
    for part in str(codes or '').split(','):
        part = part.strip()
        if part.isdigit() and int(part) in WARNING_CODES:
            numbers.append(int(part))
    level = DAY_COLOURS.get(colour)
    if level is None or not numbers:
        return {'date': day.isoformat(), 'status': 'unavailable', 'level': None, 'warnings': []}
    warnings = [WARNING_CODES[n] for n in numbers if n != 1]
    return {'date': day.isoformat(), 'status': 'available', 'level': level, 'meaning': COLOUR_MEANING[level],
            'warnings': warnings, 'rain_warning': any(n in RAIN_CODES for n in numbers)}


IST = timezone(timedelta(hours=5, minutes=30))
STALE_DAYS = 2  # IMD issues district warnings daily; older bulletins are reported, not presented as current.


def imd_district(features, latitude, longitude, today=None):
    today = today or datetime.now(IST).date()
    for feature in features:
        geometry = feature.get('geometry')
        if geometry and geometry.get('type') in ('Polygon', 'MultiPolygon') and inside(geometry, latitude, longitude):
            p = feature['properties']
            issued = date.fromisoformat(p['Date'])
            name = str(p['District']).strip().upper()
            days = [decode_day(p.get(f'Day_{i}'), p.get(f'Day{i}_Color'), issued + timedelta(days=i - 1)) for i in range(1, 6)]
            days = [d for d in days if d['date'] >= today.isoformat()]  # past days of the bulletin are not "today"
            stale = (today - issued).days >= STALE_DAYS or not days
            return {'status': 'stale' if stale else 'available', **({'message': f'The latest IMD district bulletin found is from {issued.isoformat()}; it is not shown as current. Check mausam.imd.gov.in.'} if stale else {}), 'district': DISTRICT_NAMES.get(name, [name.title()])[0], 'imd_name': name,
                    'issued_date': issued.isoformat(), 'issued_utc_hour': p.get('UTC'), 'updated_at': p.get('updated_at'),
                    'days': days, 'source': {'name': 'India Meteorological Department — district-wise warnings', 'url': IMD_PAGE,
                                              'codes': IMD_CODES_URL}}
    return {'status': 'no_district', 'message': 'No IMD warning district contains this point.'}


def rounded(coordinates):
    # ~110 m precision is ample for district shading and keeps the statewide payload small.
    if isinstance(coordinates[0], (int, float)):
        return [round(coordinates[0], 3), round(coordinates[1], 3)]
    return [rounded(c) for c in coordinates]


def karnataka_districts(features, today):
    out = []
    for feature in features:
        p = feature.get('properties') or {}
        name = str(p.get('District', '')).strip().upper()
        geometry = feature.get('geometry')
        if name not in DISTRICT_NAMES or not geometry or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            continue
        centre = feature_centre(geometry)
        record = imd_district([feature], centre[1], centre[0], today) if centre else {'status': 'unavailable'}
        if record.get('status') not in ('available', 'stale'):
            continue
        out.append({'district': DISTRICT_NAMES[name][0], 'imd_name': name, 'status': record['status'],
                    'issued_date': record['issued_date'], 'days': record['days'][:2] if record['status'] == 'available' else [],
                    'geometry': {'type': geometry['type'], 'coordinates': rounded(geometry['coordinates'])}})
    return sorted(out, key=lambda d: d['district'])


def feature_centre(geometry):
    # A vertex-average point is not always inside a concave district, so try it, then each ring vertex pair midpoint.
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    ring = max((poly[0] for poly in polygons), key=len)
    candidates = [(sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring))]
    candidates += [((a[0] + b[0]) / 2 * 0.98 + candidates[0][0] * 0.02, (a[1] + b[1]) / 2 * 0.98 + candidates[0][1] * 0.02)
                   for a, b in zip(ring[::7], ring[3::7])]
    return next((c for c in candidates if inside(geometry, c[1], c[0])), None)


def official_suggestions(districts, generated_at):
    """Draft notices that relay official IMD Orange/Red district warnings. Never sends anything."""
    out = []
    for d in districts:
        for day in d['days']:
            if day.get('level') in ('orange', 'red') and day['warnings']:
                when = 'today' if day is d['days'][0] else 'tomorrow'
                message = (f"Official IMD {day['level'].upper()} warning for {d['district']} district {when} ({day['date']}): "
                           f"{', '.join(day['warnings'])}. {COLOUR_MEANING[day['level']]}. Source: India Meteorological Department "
                           f"district warning issued {d['issued_date']}. Follow IMD, KSNDMC and district administration advice. "
                           "Relayed by FloodPulse (project notice, not a government channel).")
                out.append({'id': f"imd-{d['imd_name']}-{day['date']}", 'district': d['district'], 'date': day['date'], 'level': day['level'],
                            'warnings': day['warnings'], 'source': 'OFFICIAL_WARNING', 'suggested_kind': 'emergency' if day['level'] == 'red' else 'informational',
                            'suggested_message': message})
    rank = {'red': 0, 'orange': 1}
    return {'generated_at': generated_at, 'suggestions': sorted(out, key=lambda s: (s['date'], rank[s['level']], s['district'])),
            'note': 'Drafts relaying official IMD warnings. An administrator must edit, preview and explicitly approve before anything is sent.'}


# ---------- NDMA SACHET CAP alerts ----------

def text(element, path):
    found = element.find(path, CAP_NS)
    return (found.text or '').strip() if found is not None and found.text else ''


def parse_cap(raw):
    root = safe_xml(raw)
    if root.tag != '{urn:oasis:names:tc:emergency:cap:1.2}alert':
        raise OfficialUnavailable('not a CAP 1.2 alert')
    infos = root.findall('cap:info', CAP_NS)
    info = next((i for i in infos if text(i, 'cap:language').lower().startswith('en')), infos[0] if infos else None)
    if info is None:
        raise OfficialUnavailable('CAP alert without info')
    areas = info.findall('cap:area', CAP_NS)
    return {'identifier': text(root, 'cap:identifier'), 'sender': text(root, 'cap:sender'), 'sent': text(root, 'cap:sent'),
            'status': text(root, 'cap:status'), 'msg_type': text(root, 'cap:msgType'), 'references': text(root, 'cap:references'),
            'event': text(info, 'cap:event'), 'category': text(info, 'cap:category'), 'urgency': text(info, 'cap:urgency'),
            'severity': text(info, 'cap:severity'), 'certainty': text(info, 'cap:certainty'), 'headline': text(info, 'cap:headline'),
            'description': text(info, 'cap:description'), 'instruction': text(info, 'cap:instruction'),
            'effective': text(info, 'cap:effective'), 'expires': text(info, 'cap:expires'),
            'area': '; '.join(text(a, 'cap:areaDesc') for a in areas if text(a, 'cap:areaDesc')),
            'lgd_district_codes': [text(g, 'cap:value') for a in areas for g in a.findall('cap:geocode', CAP_NS)
                                   if text(g, 'cap:valueName') == 'LGD District Code']}


def rss_items(raw):
    root = safe_xml(raw)
    items = []
    for item in root.iter('item'):
        link = (item.findtext('link') or '').strip()
        if link.startswith('https://sachet.ndma.gov.in/'):
            items.append({'link': link, 'title': (item.findtext('title') or '').strip(), 'author': (item.findtext('author') or '').strip()})
    return items


def names_district(alert, district):
    if not district:
        return False
    body = ' '.join((alert['headline'], alert['description'], alert['area'])).lower()
    return any(re.search(r'\b' + re.escape(name.lower()) + r'\b', body) for name in DISTRICT_NAMES.get(district, []))


def active(alerts, now):
    cancelled = {ref for a in alerts if a['msg_type'] == 'Cancel' for ref in re.findall(r'IN-\d+_\d+', a['references'])}
    out = []
    for a in alerts:
        try:
            expires = datetime.fromisoformat(a['expires'])
        except ValueError:
            continue
        if a['status'] == 'Actual' and a['msg_type'] != 'Cancel' and expires > now and a['identifier'] not in cancelled:
            out.append({**a, 'expires_in_minutes': int((expires - now).total_seconds() // 60)})
    return sorted(out, key=lambda a: a['sent'], reverse=True)


# ---------- service ----------

class OfficialService:
    def __init__(self, client, clock=time.time, geometry=None):
        self.client, self.clock = client, clock
        self.geometry = geometry or load_boundary()
        self.imd_cache = self.rss_cache = None
        self.cap_cache = {}
        self.lock = asyncio.Lock()

    def now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc)

    async def imd_features(self):
        if self.imd_cache and self.imd_cache['expires'] > self.clock():
            return self.imd_cache['value']
        try:
            payload = await read_bounded(self.client, IMD_WFS, IMD_PARAMS)
            features = json.loads(payload)['features']
            if not isinstance(features, list):
                raise ValueError
            value = {'features': features, 'retrieved_at': self.now().isoformat(), 'error': None}
            ttl = IMD_TTL
        except (OfficialUnavailable, ValueError, KeyError, TypeError) as exc:
            value, ttl = {'features': None, 'retrieved_at': self.now().isoformat(), 'error': str(exc) if isinstance(exc, OfficialUnavailable) else 'invalid response'}, FAIL_TTL
        self.imd_cache = {'expires': self.clock() + ttl, 'value': value}
        return value

    async def cap(self, link):
        if link not in self.cap_cache:  # A CAP message is immutable once issued.
            self.cap_cache[link] = parse_cap(await read_bounded(self.client, link, limit=512 * 1024))
        return self.cap_cache[link]

    async def sachet(self):
        if self.rss_cache and self.rss_cache['expires'] > self.clock():
            return self.rss_cache['value']
        try:
            items = rss_items(await read_bounded(self.client, SACHET_RSS, limit=1024 * 1024))[:MAX_ALERTS]
            alerts, failed = [], 0
            for item in items:
                try:
                    alerts.append(await self.cap(item['link']))
                except OfficialUnavailable:
                    failed += 1
            value = {'alerts': alerts, 'failed': failed, 'retrieved_at': self.now().isoformat(), 'error': None}
            ttl = RSS_TTL
        except OfficialUnavailable as exc:
            value, ttl = {'alerts': None, 'failed': 0, 'retrieved_at': self.now().isoformat(), 'error': str(exc)}, FAIL_TTL
        self.rss_cache = {'expires': self.clock() + ttl, 'value': value}
        return value

    async def warnings(self, latitude=None, longitude=None):
        point = latitude is not None and longitude is not None
        if point and not inside(self.geometry, latitude, longitude):
            raise HTTPException(422, 'Point is outside Karnataka')
        async with self.lock:
            imd_raw, sachet_raw = await asyncio.gather(self.imd_features(), self.sachet())
        now = self.now()
        if not point:
            imd = {'status': 'not_requested', 'message': 'Choose a place to see its IMD district warning.'}
        elif imd_raw['features'] is None:
            imd = {'status': 'unavailable', 'message': f'IMD district warnings could not be retrieved ({imd_raw["error"]}). This does not mean there is no warning.'}
        else:
            imd = imd_district(imd_raw['features'], latitude, longitude, now.astimezone(IST).date())
        imd['retrieved_at'] = imd_raw['retrieved_at']
        district = imd.get('imd_name')
        if sachet_raw['alerts'] is None:
            sachet = {'status': 'unavailable', 'message': f'NDMA SACHET alerts could not be retrieved ({sachet_raw["error"]}). This does not mean there is no alert.', 'alerts': []}
        else:
            alerts = [{**a, 'names_your_district': names_district(a, district)} for a in active(sachet_raw['alerts'], now)]
            sachet = {'status': 'partial' if sachet_raw['failed'] else 'available', 'alerts': alerts, 'checked_messages': len(sachet_raw['alerts']),
                      'unreadable_messages': sachet_raw['failed']}
        sachet.update(retrieved_at=sachet_raw['retrieved_at'], source={'name': 'NDMA SACHET (Common Alerting Protocol) — Karnataka feed', 'url': SACHET_PAGE, 'feed': SACHET_RSS})
        return {'label': LABEL, 'official': True, 'imd': imd, 'sachet': sachet, 'generated_at': now.isoformat()}


async def statewide(svc):
    async with svc.lock:
        raw = await svc.imd_features()
    if raw['features'] is None:
        return None, raw
    return karnataka_districts(raw['features'], svc.now().astimezone(IST).date()), raw


@router.get('/api/official/districts')
async def official_districts(request: Request):
    districts, raw = await statewide(request.app.state.official)
    if districts is None:
        return JSONResponse({'status': 'unavailable', 'official': True, 'districts': [], 'retrieved_at': raw['retrieved_at'],
                             'message': f'IMD district warnings could not be retrieved ({raw["error"]}). This does not mean there is no warning.'},
                            status_code=503, headers={'Cache-Control': 'no-store'})
    return JSONResponse({'status': 'available', 'official': True, 'label': LABEL, 'districts': districts, 'retrieved_at': raw['retrieved_at'],
                         'source': {'name': 'India Meteorological Department — district-wise warnings', 'url': IMD_PAGE, 'codes': IMD_CODES_URL}},
                        headers={'Cache-Control': 'no-store'})


@router.get('/api/admin/official/suggestions')
async def admin_official_suggestions(request: Request, actor=Depends(authorized)):
    districts, raw = await statewide(request.app.state.official)
    if districts is None:
        return JSONResponse({'status': 'unavailable', 'suggestions': [], 'message': f'IMD district warnings could not be retrieved ({raw["error"]}).'},
                            status_code=503, headers={'Cache-Control': 'no-store'})
    return JSONResponse({'status': 'available', **official_suggestions(districts, raw['retrieved_at'])}, headers={'Cache-Control': 'no-store'})


@router.get('/api/official/warnings')
async def official_warnings(request: Request,
                            latitude: float | None = Query(None, ge=-90, le=90, allow_inf_nan=False),
                            longitude: float | None = Query(None, ge=-180, le=180, allow_inf_nan=False)):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Give both latitude and longitude, or neither')
    body = await request.app.state.official.warnings(latitude, longitude)
    return JSONResponse(body, headers={'Cache-Control': 'no-store'})
