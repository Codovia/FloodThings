"""Create-only v2 public directory from retained independent settlement evidence.

Original v1, government documents, OSM responses and public containment polygons
remain unchanged. No geocoder runs here or in the application. No SOI input.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import build_location_directory as previous
from app.locations import LocationStore, VERSION, validate_directory

ROOT = previous.ROOT
RAW = ROOT / 'data/raw/reference/mvp_sprint5_live_v1'
OUTPUT = ROOT / 'data/reference' / VERSION
read, digest = previous.read, previous.digest


def receipt(name, raw=RAW):
    rows = read(raw / 'retrieval.json')
    row = next(r for r in rows if r['path'] == name)
    assert row['status'] == 200
    assert digest(raw / name) == {k: row[k] for k in ('sha256', 'bytes')}
    return row


def settlement(filename, district, boundary, official_name, association_url, raw=RAW, stable_id=None):
    from shapely.geometry import Point
    evidence = receipt(filename, raw)
    original = read(raw / filename)
    assert original['license'] == 'http://opendatacommons.org/licenses/odbl/1-0/'
    assert len(original['elements']) == 1
    node = original['elements'][0]
    assert evidence['url'] == f"https://api.openstreetmap.org/api/0.6/node/{node['id']}.json"
    assert node['type'] == 'node' and node['tags']['place'] in ('city', 'town', 'village')
    assert boundary.is_valid and boundary.covers(Point(node['lon'], node['lat']))
    aliases = {v for k, v in node['tags'].items() if k.startswith('name:') or k in ('name', 'alt_name', 'int_name', 'old_name')}
    canonical = stable_id or f"osm:node:{node['id']}"
    return {'id': canonical, 'identifier_aliases': [f"osm:node:{node['id']}"] if stable_id else [],
            'name': official_name, 'source_name': node['tags']['name'], 'aliases': sorted(aliases - {official_name}),
            'district_id': district, 'association_status': 'official_district_record_cross_checked',
            'association_source_url': association_url, 'coordinate_status': 'verified_osm_place_point', 'selectable': True,
            'coordinate_meaning': 'OpenStreetMap mapped settlement point; not a surveyed municipal centre or district weather station',
            'source_place_type': node['tags']['place'],
            'coordinates': {'latitude': node['lat'], 'longitude': node['lon'], 'crs': 'EPSG:4326'},
            'containment_status': 'within_public_geoboundaries_district',
            'coordinate_source': {'source_type': 'OpenStreetMap', 'node_id': node['id'], 'version': node['version'],
                 'modified_at': node['timestamp'], 'retrieved_at': evidence['retrieved_at'], 'response_sha256': evidence['sha256'],
                 'url': f"https://www.openstreetmap.org/node/{node['id']}", 'license': 'ODbL 1.0'}}


def derive(raw=RAW):
    from shapely.geometry import shape
    previous.validate()
    data = deepcopy(LocationStore(previous.OUTPUT).load())
    data['version'] = VERSION
    for name in ('udupi-municipal.html', 'udupi-voters.html', 'dk-municipal.html', 'dk-policy.html', 'osm-copyright.html'):
        receipt(name, raw)
    municipal = (raw / 'udupi-municipal.html').read_text()
    voters = (raw / 'udupi-voters.html').read_text()
    dk_page = (raw / 'dk-municipal.html').read_text()
    assert 'Kundapur Town Municipal Council' in municipal and 'Kaup Town Municipal Council' in municipal
    assert all(s in voters for s in ('KUNDAPURA TMC', 'SALIGRAMA TOWN PANCHAYAT'))
    assert 'Mangaluru City was upgraded as City Corporation' in dk_page
    metadata = read(raw / 'gbopen-verified-metadata.json')
    assert metadata['boundaryID'] == 'IND-ADM2-76128533'
    assert metadata['boundaryLicense'] == 'Open Data Commons Open Database License 1.0'
    for filename, provenance in [('gbopen-verified-metadata.json', 'gbopen-metadata.provenance.json'), ('gbopen-adm2-actual.geojson', 'gbopen-actual.provenance.json')]:
        assert digest(raw / filename) == {k: read(raw / provenance)[k] for k in ('sha256', 'bytes')}
    geometry = read(raw / 'gbopen-adm2-actual.geojson')
    assert geometry['crs']['properties']['name'] == 'urn:ogc:def:crs:OGC:1.3:CRS84'
    candidates = [f for f in geometry['features'] if f['properties']['shapeName'] == 'Dakshina Kannada']
    assert len(candidates) == 1
    feature = candidates[0]
    assert feature['properties']['shapeID'] == '76128533B54396396829952' and feature['properties']['shapeGroup'] == 'IND'
    boundary = shape(feature['geometry'])
    assert boundary.is_valid and not boundary.is_empty
    district = next(d for d in data['districts'] if d['id'] == 'nic:dk.nic.in')
    assert district['name'] == feature['properties']['shapeName']
    w, s, e, n = boundary.bounds
    district['navigation_bounds'] = [[s, w], [n, e]]
    district['navigation_source'] = {'id': 'geoBoundaries:gbOpen:IND:ADM2:76128533', 'version': '2021 represented; 2023-12-12 build; repository 9469f09',
        'shape_id': feature['properties']['shapeID'], 'license': 'ODbL 1.0', 'url': 'https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/',
        'producer': metadata['boundarySource'], **digest(raw / 'gbopen-adm2-actual.geojson')}
    udupi = shape(read(previous.SPATIAL / 'udupi_boundary.geojson')['geometry'])
    kundapur = settlement('kundapur-node.json', 'nic:udupi.nic.in', udupi, 'Kundapur',
        'https://udupi.nic.in/en/final-voters-list/', raw, 'udupi-admin:municipality:kundapur')
    assert kundapur['source_name'] == 'Kundapura' and kundapur['source_place_type'] == 'town'
    assert kundapur['coordinate_source']['node_id'] == 245623778
    data['localities'] = [kundapur if r['id'] == kundapur['id'] else r for r in data['localities']]
    saligrama = settlement('saligrama-node.json', 'nic:udupi.nic.in', udupi, 'Saligrama', 'https://udupi.nic.in/en/final-voters-list/', raw)
    assert saligrama['coordinate_source']['node_id'] == 245622058 and saligrama['source_name'] == 'Saligrama'
    mangaluru = settlement('mangaluru-node.json', district['id'], boundary, 'Mangaluru', 'https://dk.nic.in/en/municipal-administration/', raw)
    assert mangaluru['coordinate_source']['node_id'] == 245612641 and mangaluru['source_name'] == 'Mangaluru'
    data['localities'] += [saligrama, mangaluru,
        {'id': 'udupi-admin:municipality:kaup', 'name': 'Kaup', 'source_name': 'Kaup', 'aliases': [], 'district_id': 'nic:udupi.nic.in',
         'association_status': 'official_district_record_cross_checked', 'association_source_url': 'https://udupi.nic.in/en/municipal-administration/',
         'coordinate_status': 'unavailable', 'selectable': False, 'coordinates': None, 'coordinate_source': None, 'containment_status': 'not_evaluated',
         'unavailable_reason': 'Official municipal identity verified; settlement-node coordinate was not reviewed in this bounded sprint. Use map, GPS or coordinates.'}]
    data['localities'].sort(key=lambda r: (r['name'].casefold(), r['id']))
    data['coverage'] = {'district_names': len(data['districts']), 'districts_with_selectable_localities': 2, 'selectable_localities': 5, 'name_only_localities': 1}
    return validate_directory(data)


def build(output=OUTPUT):
    if output.exists():
        raise FileExistsError('Completed version exists; never overwrite it')
    data = derive()
    inputs = [previous.OUTPUT / 'directory.json', previous.OUTPUT / 'manifest.json', *sorted(RAW.iterdir())]
    manifest = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(), 'previous_version': previous.VERSION,
        'district_count': 31, 'locality_count': 6, 'selectable_locality_count': 5, 'districts_with_selectable_localities': 2,
        'current_lgd_independently_verified': False, 'soi_used': False,
        'inputs': [{'path': str(p.relative_to(ROOT)), **digest(p)} for p in inputs],
        'licensing': {'coordinates': '© OpenStreetMap contributors; ODbL 1.0. Extracted point database offered under ODbL 1.0 with attribution and share-alike.',
          'license_url': 'https://opendatacommons.org/licenses/odbl/1.0/', 'udupi_navigation': 'Existing geoBoundaries CGAZ CC BY 4.0; unchanged.',
          'dakshina_kannada_navigation': 'geoBoundaries gbOpen IND ADM2; Pathways Data Pvt. Ltd., lgdirectory.gov.in; ODbL 1.0. Only factual navigation bounds published.',
          'government_evidence': 'Small factual identities/links only. Original website material requires permission and remains local.',
          'policy_urls': ['https://udupi.nic.in/en/website-policies/', 'https://dk.nic.in/en/website-policies/', 'https://www.openstreetmap.org/copyright']},
        'method': 'Independent official municipal identity and district association, original OSM settlement-node coordinates, actual public polygon containment; no centroid or geocoder substitution.',
        'limitations': ['Current LGD unresolved; historical public navigation polygons are not authoritative current municipal/district boundaries.',
          'Saligrama OSM place=village is preserved; municipal status from official evidence is separate from mapped point type.',
          'Kundapur and Kundapura are independently linked by official municipality and voters-list records; stable v1 ID retained, OSM node ID is an alias.',
          'Kaup remains disabled. Remaining 29 districts have no reviewed points. All weather is point-specific, not district/locality-wide.',
          'Initial boundary download was an LFS pointer, preserved; actual geometry verified against its exact declared SHA-256 and byte size.',
          'Runtime has no external geocoder. No SOI geometry, restricted derivatives or personal OSM contributor fields published.'], 'files': {}}
    output.mkdir(parents=True)
    (output / 'directory.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    manifest['files']['directory.json'] = digest(output / 'directory.json')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return validate(output)


def validate(output=OUTPUT):
    data = LocationStore(output).load()
    manifest = read(output / 'manifest.json')
    for source in manifest['inputs']:
        assert digest(ROOT / source['path']) == {k: source[k] for k in ('sha256', 'bytes')}
    assert data == derive(), 'Directory must reproduce exactly from source evidence'
    assert len(data['districts']) == 31 and len(data['localities']) == 6 and sum(r['selectable'] for r in data['localities']) == 5
    return {**data['coverage'], 'version': VERSION, 'source_reproduction': 'passed', 'previous_version_preserved': True, 'current_lgd': 'unresolved', 'soi_used': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'], default='validate', nargs='?')
    args = parser.parse_args()
    print(json.dumps(build() if args.command == 'build' else validate(), indent=2))
