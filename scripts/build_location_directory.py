"""Offline public selector derivation; original sources stay local and immutable.

No SOI data, external geocoding or district-centroid weather requests. Rebuilding
requires retained NIC, OSM and official district evidence. Completed versions
are create-only; validation never writes them.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.locations import LocationStore, VERSION, validate_directory

OUTPUT = ROOT / 'data/reference' / VERSION
RAW = ROOT / 'data/raw/reference/mvp_sprint4_live_v1'
NIC = ROOT / 'data/reference/karnataka_nic_provisional_v1'
GIS = ROOT / 'data/processed/udupi_drainage_gis_v1'
SPATIAL = ROOT / 'data/processed/udupi_flood_spatial_v1'


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    raw = path.read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def derive(nic=NIC, raw=RAW, gis=GIS, spatial=SPATIAL):
    from shapely.geometry import Point, shape
    inventory = read(nic / 'district_names.json')
    nic_manifest = read(nic / 'manifest.json')
    assert digest(nic / 'district_names.json') == nic_manifest['files']['district_names.json']
    municipal = (raw / 'municipal.html').read_text()
    assert all(text in municipal for text in ('Udupi City Municipal Council', 'Kundapur Town Municipal Council', 'Karkala Town Municipal Council'))
    boundary = shape(read(spatial / 'udupi_boundary.geojson')['geometry'])
    assert boundary.is_valid and not boundary.is_empty
    assert digest(spatial / 'udupi_boundary.geojson')['sha256'] == '4f977a68cce0c55ceedad9c2d30c2d774a79ba10243816d14069ea84ea4a43df'
    west, south, east, north = boundary.bounds
    districts = []
    for original in inventory['records']:
        row = {'id': 'nic:' + original['district_website'].split('/')[2], 'name': original['district_name'], 'source_name': original['district_name'],
               'aliases': [], 'source_website': original['district_website'], 'source_url': nic_manifest['sources']['nic']['url'],
               'source_retrieved_at': nic_manifest['sources']['nic']['retrieved_at'], 'current_lgd_code': None,
               'identity_status': 'nic_name_current_lgd_unresolved', 'representative_point': None,
               'navigation_bounds': None, 'navigation_source': None}
        if row['name'] == 'Udupi':
            row['navigation_bounds'] = [[south, west], [north, east]]
            row['navigation_source'] = {'id': 'WM/geoLab/geoBoundaries/600/ADM2', 'version': '6.0.0 CGAZ; 2023-09-13 composite',
                'shape_id': '76128533B4839184447445', 'license': 'CC BY 4.0',
                'url': 'https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2', **digest(spatial / 'udupi_boundary.geojson')}
        districts.append(row)
    ud = read(gis / 'place_query.json')
    node = next(r for r in ud['response']['elements'] if r['type'] == 'node' and r['id'] == 245620117)
    kr = read(raw / 'karkala-node.json')['elements'][0]
    kp = read(raw / 'karkala-node.provenance.json')
    entries = []
    for node, timestamp, checksum in [(node, ud['retrieved_at'], digest(gis / 'place_query.json')['sha256']), (kr, kp['retrieved_at'], kp['sha256'])]:
        assert node['type'] == 'node' and node['tags']['place'] in ('city', 'town') and node['tags']['name'] in ('Udupi', 'Karkala')
        assert boundary.covers(Point(node['lon'], node['lat']))
        assert node['id'] in (245620117, 245619070)
        entries.append({'id': f"osm:node:{node['id']}", 'name': node['tags']['name'], 'source_name': node['tags']['name'],
                       'aliases': sorted({value for key, value in node['tags'].items() if key.startswith('name:') and value != node['tags']['name']}),
                       'district_id': 'nic:udupi.nic.in', 'association_status': 'official_district_record_cross_checked',
                       'association_source_url': 'https://udupi.nic.in/en/municipal-administration/',
                       'coordinate_status': 'verified_osm_place_point', 'selectable': True,
                       'coordinates': {'latitude': node['lat'], 'longitude': node['lon'], 'crs': 'EPSG:4326'},
                       'containment_status': 'within_public_geoboundaries_district',
                       'coordinate_source': {'source_type': 'OpenStreetMap', 'node_id': node['id'], 'version': node['version'],
                                             'modified_at': node['timestamp'], 'retrieved_at': timestamp, 'response_sha256': checksum,
                                             'url': f"https://www.openstreetmap.org/node/{node['id']}", 'license': 'ODbL 1.0'}})
    # The lookup returned a railway station and a taluk relation, not a town point.
    # Retain the official town name without borrowing either coordinate.
    entries.append({'id': 'udupi-admin:municipality:kundapur', 'name': 'Kundapur', 'source_name': 'Kundapur', 'aliases': [],
                    'district_id': 'nic:udupi.nic.in', 'association_status': 'official_district_record_cross_checked',
                    'association_source_url': 'https://udupi.nic.in/en/municipal-administration/', 'coordinate_status': 'unavailable',
                    'selectable': False, 'coordinates': None, 'coordinate_source': None, 'containment_status': 'not_evaluated',
                    'unavailable_reason': 'Retrieved Kundapura results identify a railway station and a taluk boundary, not a verified settlement node. Neither is substituted.'})
    return validate_directory({'version': VERSION, 'state_name': 'Karnataka', 'districts': sorted(districts, key=lambda r: r['name'].casefold()),
                               'localities': sorted(entries, key=lambda r: (r['name'].casefold(), r['id']))})


def build(output=OUTPUT):
    if output.exists():
        raise FileExistsError('Completed directory exists; validate it or create a separately reviewed version.')
    data = derive()
    inputs = [NIC / 'district_names.json', NIC / 'manifest.json', GIS / 'place_query.json', SPATIAL / 'udupi_boundary.geojson',
              RAW / 'municipal.html', RAW / 'policy.html', RAW / 'karkala-node.json', RAW / 'karkala-node.provenance.json', RAW / 'nominatim-provenance.json', RAW / 'Kundapura.json', RAW / 'Karkala.json']
    manifest = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(), 'district_count': len(data['districts']),
                'locality_count': len(data['localities']), 'selectable_locality_count': sum(r['selectable'] for r in data['localities']),
                'current_lgd_independently_verified': False, 'soi_used': False,
                'inputs': [{'path': str(p.relative_to(ROOT)), **digest(p)} for p in inputs],
                'retrievals': read(RAW / 'retrieval.json') + read(RAW / 'nominatim-provenance.json') + [read(RAW / 'karkala-node.provenance.json')],
                'licensing': {'coordinates': 'ODbL 1.0; © OpenStreetMap contributors. This small extracted place-point database is offered under ODbL 1.0; share-alike and attribution apply.',
                              'district_navigation': 'geoBoundaries CC BY 4.0; bounds only for navigation, not a representative weather point.',
                              'official_names': 'Small factual name/URL/association inventory; no original government page text, maps or HTML redistributed. No blanket document reuse licence asserted.',
                              'udupi_document_policy_url': 'https://udupi.nic.in/en/website-policies/',
                              'udupi_document_policy': 'The policy requires permission for reproduction of website material; original documents remain local. Only factual identities cross-checked here.',
                              'osm_license_url': 'https://opendatacommons.org/licenses/odbl/1.0/',
                              'nominatim_usage_policy': 'https://operations.osmfoundation.org/policies/nominatim/'},
                'limitations': ['31 source names; current LGD codes unresolved. No SOI source identifiers or geometry used.',
                               'Only Udupi has reviewed public navigation geometry. No district representative weather points.',
                               'Udupi and Karkala coordinates are volunteer-mapped settlement points, not surveyed municipal boundaries or weather gauges.',
                               'Kundapur is name-only. Remaining 30 districts have no verified localities in this version.',
                               'Runtime searches only retained local data; no live geocoder or external directory dependency.'], 'files': {}}
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
    assert data == derive(), 'Directory does not reproduce from retained sources'
    assert len(data['districts']) == 31 and len(data['localities']) == 3 and sum(r['selectable'] for r in data['localities']) == 2
    return {'district_names': 31, 'districts_with_public_navigation_geometry': 1, 'selectable_localities': 2, 'name_only_localities': 1,
            'source_reproduction': 'passed', 'current_lgd': 'unresolved', 'soi_used': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'], default='validate', nargs='?')
    args = parser.parse_args()
    print(json.dumps(build() if args.command == 'build' else validate(), indent=2))
