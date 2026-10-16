"""In-app shelter routing via OpenRouteService, avoiding approved flood reports.

Routes are generic road/foot navigation. Avoiding approved citizen reports is a
best effort and never certifies a route as flood-safe. Without a configured key
the feature reports `not_configured` and the external Google Maps link remains.
"""
import asyncio
import json
import math
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from .shelters import get_store, mode
from .risk import inside, load_boundary

router = APIRouter()
ORS_URL = 'https://api.openrouteservice.org/v2/directions/{profile}/geojson'
AVOID_RADIUS_M = 150
AVOID_HOURS = 72
MAX_ORIGIN_ACCURACY_M = 1000
MAX_AVOID = 50
LIMIT = 2 * 1024 * 1024
LABEL = 'Route avoids {n} approved flooding/blocked-drain report area(s) from the last 72 hours. It is NOT certified flood-safe: check road closures and follow local authorities.'
BOUNDARY = load_boundary()


class Origin(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=MAX_ORIGIN_ACCURACY_M)


class RouteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    shelter_id: str = Field(pattern=r'^[0-9a-f-]{36}$')
    origin: Origin
    profile: Literal['foot-walking', 'driving-car'] = 'foot-walking'


def octagon(latitude, longitude, radius_m=AVOID_RADIUS_M):
    dlat = radius_m / 111320
    dlon = radius_m / (111320 * max(math.cos(math.radians(latitude)), 0.01))
    ring = [[round(longitude + dlon * math.cos(a), 6), round(latitude + dlat * math.sin(a), 6)]
            for a in (i * math.pi / 4 for i in range(8))]
    return [ring + [ring[0]]]


def report_points(engine, south, west, north, east):
    with engine.connect().execution_options(postgresql_readonly=True) as c:
        rows = c.execute(text(
            "SELECT latitude, longitude FROM citizen_reports WHERE state='APPROVED' AND demonstration=:demo "
            "AND event_type IN ('flooding','waterlogging','drainage_blockage') "
            "AND reviewed_at > now() - make_interval(hours => :hours) "
            "AND latitude BETWEEN :s AND :n AND longitude BETWEEN :w AND :e "
            "ORDER BY reviewed_at DESC LIMIT :limit"),
            {'demo': mode() == 'demonstration', 'hours': AVOID_HOURS, 's': south, 'n': north, 'w': west, 'e': east,
             'limit': MAX_AVOID}).all()
    return [(r[0], r[1]) for r in rows]


def parse_route(payload):
    feature = payload['features'][0]
    geometry = feature['geometry']
    if geometry['type'] != 'LineString' or len(geometry['coordinates']) < 2:
        raise ValueError('Route geometry missing')
    summary = feature['properties']['summary']
    steps = [{'instruction': s['instruction'][:200], 'distance_m': round(s['distance']), 'duration_s': round(s['duration'])}
             for seg in feature['properties'].get('segments', []) for s in seg.get('steps', [])][:60]
    return {'geometry': geometry, 'distance_m': round(summary['distance']), 'duration_s': round(summary['duration']), 'steps': steps}


async def post_json(client, url, body, key):
    async with asyncio.timeout(15):
        async with client.stream('POST', url, json=body, headers={'Authorization': key, 'Accept': 'application/geo+json'}) as response:
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw) + len(chunk) > LIMIT:
                    raise ValueError('Route response too large')
                raw.extend(chunk)
            return response.status_code, json.loads(raw)


@router.get('/api/route/status')
def route_status():
    return {'configured': bool(os.environ.get('OPENROUTESERVICE_API_KEY')), 'provider': 'openrouteservice'}


@router.post('/api/route')
async def route(payload: RouteInput, request: Request, store=Depends(get_store)):
    key = os.environ.get('OPENROUTESERVICE_API_KEY')
    if not key:
        return JSONResponse(status_code=503, content={'status': 'not_configured',
            'message': 'In-app routing is not configured. Use the external directions link.'})
    o = payload.origin
    if not inside(BOUNDARY, o.latitude, o.longitude):
        raise HTTPException(422, 'Origin must be inside Karnataka')
    from .notifications import available_shelter
    shelter = await run_in_threadpool(available_shelter, store, payload.shelter_id)
    if shelter['available_capacity'] <= 0:
        raise HTTPException(409, 'Shelter has no reported spare capacity')
    margin = 0.05
    south, north = sorted((o.latitude, shelter['latitude']))
    west, east = sorted((o.longitude, shelter['longitude']))
    points = await run_in_threadpool(report_points, store.engine, south - margin, west - margin, north + margin, east + margin)
    body = {'coordinates': [[o.longitude, o.latitude], [shelter['longitude'], shelter['latitude']]], 'units': 'm',
            'instructions': True}
    if points:
        body['options'] = {'avoid_polygons': {'type': 'MultiPolygon', 'coordinates': [octagon(*p) for p in points]}}
    try:
        status, result = await post_json(request.app.state.http, ORS_URL.format(profile=payload.profile), body, key)
    except (TimeoutError, httpx.HTTPError, ValueError):
        return JSONResponse(status_code=502, content={'status': 'provider_unavailable', 'message': 'Routing provider unavailable. Use the external directions link.'})
    if status == 429:
        return JSONResponse(status_code=503, content={'status': 'rate_limited', 'message': 'Routing quota reached. Use the external directions link.'})
    if status != 200:
        message = 'No route found that avoids the reported flood areas.' if points else 'Routing provider could not find a route.'
        return JSONResponse(status_code=502, content={'status': 'no_route', 'message': message + ' Use the external directions link and check local closures.'})
    try:
        parsed = parse_route(result)
    except (KeyError, IndexError, TypeError, ValueError):
        return JSONResponse(status_code=502, content={'status': 'invalid_response', 'message': 'Routing response could not be validated.'})
    return JSONResponse(content={'status': 'available', 'provider': 'openrouteservice', 'profile': payload.profile,
        **parsed, 'avoided_reports': len(points), 'flood_safe_certified': False, 'label': LABEL.format(n=len(points)),
        'shelter': {'id': shelter['id'], 'name': shelter['name']},
        'attribution': '© openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors'},
        headers={'Cache-Control': 'no-store'})
