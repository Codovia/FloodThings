"""Read-only public place directory. No geocoding, SOI access or guessed points."""
import hashlib
import json
import math
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

DATASET = Path(__file__).resolve().parents[2] / 'data/reference/karnataka_location_directory_v2'
VERSION = 'karnataka_location_directory_v2'


class LocationsUnavailable(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LocationsUnavailable(message)


def validate_directory(data, version=VERSION):
    require(data['version'] == version and version in ('karnataka_location_directory_v1', VERSION) and data['state_name'] == 'Karnataka', 'Directory identity mismatch')
    ids = set()
    districts = {}
    require(isinstance(data['districts'], list) and isinstance(data['localities'], list), 'Invalid directory collections')
    for row in data['districts']:
        require(row['id'] not in ids and row['id'] == 'nic:' + row['source_website'].split('/')[2], 'Duplicate or unsupported district identifier')
        require(row['name'] and row['source_name'] == row['name'] and row['current_lgd_code'] is None and row['identity_status'] == 'nic_name_current_lgd_unresolved', 'District identity must retain unresolved LGD status')
        require(row['representative_point'] is None and row['source_url'].startswith('https://igod.gov.in/'), 'No verified district weather point')
        bounds = row['navigation_bounds']
        if bounds is not None:
            require((row['navigation_source']['license'], row['navigation_source']['id']) in {('CC BY 4.0', 'WM/geoLab/geoBoundaries/600/ADM2'), ('ODbL 1.0', 'geoBoundaries:gbOpen:IND:ADM2:76128533')}, 'Restricted navigation source')
            require(len(bounds) == 2 and all(len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p) for p in bounds) and -90 <= bounds[0][0] < bounds[1][0] <= 90 and -180 <= bounds[0][1] < bounds[1][1] <= 180, 'Invalid navigation bounds')
        ids.add(row['id']); districts[row['id']] = row
    for row in data['localities']:
        require(row['id'] not in ids and row['district_id'] in districts and row['name'], 'Invalid locality identity or association')
        require(isinstance(row.get('identifier_aliases', []), list) and all(isinstance(a, str) and a for a in row.get('identifier_aliases', [])), 'Invalid identifier aliases')
        require(row['association_status'] == 'official_district_record_cross_checked' and row['association_source_url'].startswith('https://' + districts[row['district_id']]['source_website'].split('/')[2] + '/'), 'Unverified district relationship')
        for alias in row.get('identifier_aliases', []):
            require(alias not in ids and alias != row['id'], 'Conflicting identifier alias')
            ids.add(alias)
        ids.add(row['id'])
        point = row['coordinates']
        # Name-only records are allowed; they can never become weather query points.
        if point is None:
            require(row['coordinate_status'] == 'unavailable' and row['selectable'] is False, 'Missing coordinates cannot be selectable')
            continue
        source = row['coordinate_source']
        require(row['selectable'] is True and row['coordinate_status'] == 'verified_osm_place_point', 'Unverified coordinates')
        require(source['source_type'] == 'OpenStreetMap' and source['license'] == 'ODbL 1.0' and source['url'] == f"https://www.openstreetmap.org/node/{source['node_id']}" and (row['id'] == f"osm:node:{source['node_id']}" or (row['id'] == 'udupi-admin:municipality:kundapur' and source['node_id'] == 245623778 and row['district_id'] == 'nic:udupi.nic.in')), 'Restricted or unsupported coordinate source')
        require(source['version'] > 0 and source['retrieved_at'] and len(source['response_sha256']) == 64, 'Coordinate provenance missing')
        require(point['crs'] == 'EPSG:4326' and all(isinstance(point[k], (int, float)) and not isinstance(point[k], bool) and math.isfinite(point[k]) for k in ('latitude', 'longitude')) and -90 <= point['latitude'] <= 90 and -180 <= point['longitude'] <= 180, 'Invalid coordinate')
        bounds = districts[row['district_id']]['navigation_bounds']
        require(bounds is not None and bounds[0][0] <= point['latitude'] <= bounds[1][0] and bounds[0][1] <= point['longitude'] <= bounds[1][1] and row['containment_status'] == 'within_public_geoboundaries_district', 'Coordinate lacks reviewed district containment')
    if 'coverage' in data:
        require(data['coverage'] == {'district_names': len(data['districts']),
            'districts_with_selectable_localities': len({r['district_id'] for r in data['localities'] if r['selectable']}),
            'selectable_localities': sum(r['selectable'] for r in data['localities']),
            'name_only_localities': sum(not r['selectable'] for r in data['localities'])}, 'Directory coverage mismatch')
    return data


class LocationStore:
    def __init__(self, directory=DATASET):
        self.directory = Path(directory)

    def load(self):
        try:
            path = self.directory / 'directory.json'
            manifest_path = self.directory / 'manifest.json'
            require(path.stat().st_size < 512000 and manifest_path.stat().st_size < 128000, 'Directory exceeds size bound')
            manifest = json.loads(manifest_path.read_bytes())
            raw = path.read_bytes()
            require(manifest['version'] in ('karnataka_location_directory_v1', VERSION) and manifest['files']['directory.json'] == {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}, 'Directory checksum mismatch')
            data = validate_directory(json.loads(raw), manifest['version'])
            require(manifest['district_count'] == len(data['districts']) and manifest['locality_count'] == len(data['localities']), 'Directory coverage mismatch')
            return data
        except LocationsUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            raise LocationsUnavailable('Public place directory is missing or invalid') from exc


router = APIRouter(prefix='/api/locations', tags=['locations'])


def get_store():
    return LocationStore()


def load(store):
    try:
        return store.load()
    except LocationsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def matching(rows, q):
    query = q.strip().casefold()
    def names(row):
        return [row['name'].casefold()] + [n.casefold() for n in row['aliases']]
    found = [row for row in rows if any(query in n for n in names(row))]
    return sorted(found, key=lambda row: (0 if query in names(row) else 1 if any(n.startswith(query) for n in names(row)) else 2, row['name'].casefold(), row.get('district_id', ''), row['id']))


def page(rows, offset, limit, data):
    return {'status': 'available', 'dataset_version': data['version'], 'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
            'coverage': data.get('coverage', {'district_names': len(data['districts']),
                'districts_with_selectable_localities': len({r['district_id'] for r in data['localities'] if r['selectable']}),
                'selectable_localities': sum(r['selectable'] for r in data['localities']), 'name_only_localities': sum(not r['selectable'] for r in data['localities'])})}


@router.get('/districts')
def districts(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0, le=10000), store: LocationStore = Depends(get_store)):
    data = load(store)
    return page(matching(data['districts'], q), offset, limit, data)


@router.get('/localities')
def localities(district_id: str = Query(..., min_length=1, max_length=100), q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0, le=10000), store: LocationStore = Depends(get_store)):
    data = load(store)
    if not any(r['id'] == district_id for r in data['districts']):
        raise HTTPException(status_code=404, detail='Unknown district identifier')
    return page(matching([r for r in data['localities'] if r['district_id'] == district_id], q), offset, limit, data)


@router.get('/search')
def search(q: str = Query(..., min_length=1, max_length=100), district_id: str | None = Query(None, min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000), store: LocationStore = Depends(get_store)):
    if not q.strip():
        raise HTTPException(status_code=422, detail='Enter a non-blank search')
    data = load(store)
    if district_id is not None and not any(r['id'] == district_id for r in data['districts']):
        raise HTTPException(status_code=404, detail='Unknown district identifier')
    rows = [{**r, 'kind': 'district'} for r in data['districts'] if district_id is None or r['id'] == district_id]
    rows += [{**r, 'kind': 'locality'} for r in data['localities'] if district_id is None or r['district_id'] == district_id]
    return page(matching(rows, q), offset, limit, data)


@router.get('/localities/{locality_id}')
def locality(locality_id: str, store: LocationStore = Depends(get_store)):
    if len(locality_id) > 100:
        raise HTTPException(status_code=422, detail='Identifier exceeds bound')
    row = next((r for r in load(store)['localities'] if r['id'] == locality_id or locality_id in r.get('identifier_aliases', [])), None)
    if row is None:
        raise HTTPException(status_code=404, detail='Unknown locality identifier')
    return row
