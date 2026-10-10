"""Bounded public GIS views over existing verified products, never research geometry.

No SOI/IFI working files, geocoders, weather services or databases writes are used.
An empty public collection is lack of eligible display evidence, not flood absence.
"""
from copy import deepcopy
import math

from fastapi import APIRouter, Depends, HTTPException, Query

from .historical import HistoricalStore, HistoricalUnavailable, get_historical_store, SOURCE, NOTICE
from .locations import LocationStore, get_store, load
from .drainage import DrainageStore, DrainageUnavailable, get_store as get_drainage_store

VERSION = 'karnataka_flood_intelligence_v1'
UDUPI = 'nic:udupi.nic.in'
EMPTY = {'type': 'FeatureCollection', 'features': []}
HAZARD_NOTICE = 'No verified potential flood-prone zone dataset is available for this district.'
UNKNOWN_MECHANISM = {'mechanisms': ['unknown'], 'status': 'unverified', 'supporting_source': None,
                     'method': 'No reviewed source establishes a flood mechanism for this mapped cell.'}
router = APIRouter(prefix='/api/flood-map', tags=['public flood intelligence'])


def district_rows(store, district_id=None):
    data = load(store)
    if district_id is not None and district_id not in {r['id'] for r in data['districts']}:
        raise HTTPException(404, 'Unknown district identifier')
    return sorted(data['districts'], key=lambda r: (r['name'].casefold(), r['id']))


def validate_geometry(geometry):
    """Validate CRS84 ranges/rings without inventing or changing source vertices."""
    kind = geometry.get('type')
    if kind not in ('Polygon', 'MultiPolygon'):
        raise HistoricalUnavailable('Unsupported public flood geometry')
    polygons = [geometry.get('coordinates')] if kind == 'Polygon' else geometry.get('coordinates')
    if not isinstance(polygons, list) or not polygons:
        raise HistoricalUnavailable('Missing polygon coordinates')
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise HistoricalUnavailable('Missing polygon rings')
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise HistoricalUnavailable('Invalid closed polygon ring')
            for point in ring:
                if not isinstance(point, list) or len(point) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in point) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                    raise HistoricalUnavailable('Invalid CRS84 coordinates')


def historical_collection(store):
    try:
        catalogue, geometries = store.load()
        if catalogue['source']['license'] != 'CC BY-NC 4.0' or catalogue['boundary_source'].get('license') != 'CC BY 4.0':
            raise HistoricalUnavailable('Display licence missing')
        features = []
        for event in catalogue['events']:
            for original in geometries[event['event_id']]['features']:
                validate_geometry(original['geometry'])
                p = original['properties']
                fid = f"gfd:{event['event_id']}:r{p['grid_row']}:c{p['grid_col']}"
                features.append({'type': 'Feature', 'id': fid, 'geometry': deepcopy(original['geometry']),
                    'properties': {**deepcopy(p), 'feature_id': fid, 'district_id': UDUPI, 'district': 'Udupi',
                        'place_name': None, 'category': 'historical_observed_floodwater',
                        'geometry_meaning': 'Source-exported observation-qualified raster cell; event-window maximum, not an exact flood boundary or settlement point',
                        'geometry_crs': 'OGC:CRS84', 'processing_grid_m': 250,
                        'start_date': event['start_date'], 'end_date_inclusive': event['end_date_inclusive'],
                        'observation_quality': 'qualified_source_mask_and_clear_views',
                        'source': SOURCE, 'image_id': event['image_id'], 'retrieved_at': event['retrieved_at'],
                        'source_geometry_sha256': event['geometry_sha256'],
                        'dataset_version': catalogue['dataset_version'], 'mechanism': deepcopy(UNKNOWN_MECHANISM),
                        'limitations': NOTICE, 'district_identity_status': 'nic_name_current_lgd_unresolved'}})
        features.sort(key=lambda f: (f['properties']['event_id'], f['properties']['grid_row'], f['properties']['grid_col']))
        if len({f['id'] for f in features}) != len(features):
            raise HistoricalUnavailable('Duplicate map identifiers')
        return catalogue, features
    except (HistoricalUnavailable, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(503, 'Public historical geometry unavailable or invalid; no flood-absence conclusion can be drawn') from exc


def coverage(count=0, events=0):
    return {'eligible_geometry_features': count, 'historical_events': events,
            'hazard_features': 0, 'absence_interpretation': 'unknown_not_verified_non_flood',
            'scope': 'Public reviewed products only; statewide selection is not statewide hazard coverage'}


@router.get('/districts')
def districts(store: LocationStore = Depends(get_store), historical: HistoricalStore = Depends(get_historical_store)):
    rows = district_rows(store)
    try:
        catalogue, features = historical_collection(historical)
        public_status, count = 'available', len(features)
    except HTTPException:
        public_status, count = 'unavailable', None
    items = []
    for row in rows:
        is_udupi = row['id'] == UDUPI
        items.append({**row, 'historical_geometry_status': public_status if is_udupi else 'no_eligible_geometry',
                      'historical_features': count if is_udupi else 0, 'historical_events': 2 if is_udupi and count is not None else 0,
                      'hazard_status': 'no_verified_dataset', 'hazard_features': 0,
                      'drainage_context_status': 'bounded_udupi_study_available_on_request' if is_udupi else 'no_reviewed_context'})
    return {'status': 'available', 'dataset_version': VERSION, 'items': items, 'total': len(items),
            'historical_status': public_status, 'coverage': coverage(count, 2 if count is not None else 0)}


@router.get('/historical')
def historical(district_id: str | None = Query(None, min_length=1, max_length=100),
               event_id: int | None = Query(None, ge=1), limit: int = Query(200, ge=1, le=200),
               offset: int = Query(0, ge=0, le=10000), store: LocationStore = Depends(get_store),
               historical_store: HistoricalStore = Depends(get_historical_store)):
    district_rows(store, district_id)
    if event_id is not None and event_id not in (2728, 3551):
        raise HTTPException(404, 'No reviewed public spatial product for this event')
    catalogue, features = historical_collection(historical_store) if district_id in (None, UDUPI) else (None, [])
    if event_id is not None:
        features = [f for f in features if f['properties']['event_id'] == event_id]
    return {'status': 'available', 'dataset_version': VERSION, 'category': 'historical_observed_floodwater',
            'district_id': district_id, 'notice': NOTICE, 'source': SOURCE,
            'boundary': catalogue['boundary'] if catalogue and district_id == UDUPI else None,
            'boundary_source': catalogue['boundary_source'] if catalogue else None,
            'events': catalogue['events'] if catalogue else [],
            'geojson': {'type': 'FeatureCollection', 'features': features[offset:offset + limit]},
            'total': len(features), 'limit': limit, 'offset': offset,
            'coverage': coverage(len(features), len({f['properties']['event_id'] for f in features}))}


@router.get('/hazards')
def hazards(district_id: str | None = Query(None, min_length=1, max_length=100), store: LocationStore = Depends(get_store)):
    district_rows(store, district_id)
    return {'status': 'unavailable', 'dataset_version': VERSION, 'category': 'potential_hazard',
            'district_id': district_id, 'geojson': deepcopy(EMPTY), 'total': 0,
            'message': HAZARD_NOTICE, 'coverage': coverage(), 'source': None,
            'reason': 'No reviewed, reusable hazard geometry is registered. Historical water, terrain and waterways are not substituted.'}


@router.get('/drainage')
def drainage(district_id: str | None = Query(None, min_length=1, max_length=100), store: LocationStore = Depends(get_store),
             drainage_store: DrainageStore = Depends(get_drainage_store)):
    district_rows(store, district_id)
    if district_id not in (None, UDUPI):
        return {'status': 'unavailable', 'category': 'drainage_context', 'district_id': district_id,
                'message': 'No reviewed drainage context is available for this district.', 'mapped_drains': deepcopy(EMPTY)}
    try:
        data = drainage_store.load()[0]
        return {**data, 'category': 'drainage_context', 'district_id': UDUPI,
                'overflow_assessment': 'not_validated',
                'geometry_notice': 'Mapped drainage feature — overflow risk not established.',
                'coverage_notice': 'Only a 3 km × 3 km Udupi study window; no mapped drains returned does not mean no drains exist.'}
    except DrainageUnavailable as exc:
        raise HTTPException(503, 'Drainage context unavailable or failed source validation') from exc


@router.get('/features/{feature_id}')
def feature(feature_id: str, store: LocationStore = Depends(get_store), historical: HistoricalStore = Depends(get_historical_store)):
    if len(feature_id) > 120 or not feature_id.startswith('gfd:'):
        raise HTTPException(404, 'Unknown public map feature')
    district_rows(store)
    _, features = historical_collection(historical)
    found = next((f for f in features if f['id'] == feature_id), None)
    if found is None:
        raise HTTPException(404, 'Unknown public map feature')
    return {'status': 'available', 'dataset_version': VERSION, 'feature': found,
            'drainage_context': {'coverage': 'limited_separate_udupi_study_not_cell_specific', 'overflow_assessment': 'not_validated'},
            'environmental_context': 'Use a verified locality or independently selected point on Weather & AI. A raster cell is not a verified locality or supported AI location.'}
