#!/usr/bin/env python3
"""Offline GloFAS catalogue checkpoint. No authentication or extraction code."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage4d_v1'
OUTPUT = ROOT / 'data/reference/karnataka_glofas_access_checkpoint_v1/manifest.json'
DATASET = 'cems-glofas-historical'
VERSION = '5.0'
SOURCE_TYPES = {'measured_cwc_nwdp', 'published_cwc_yearbook', 'modelled_glofas'}
HOSTS = {'ewds.climate.copernicus.eu', 'cds.climate.copernicus.eu',
         'confluence.ecmwf.int', 'data.jrc.ec.europa.eu', 'jeodpp.jrc.ec.europa.eu',
         'global-flood.emergency.copernicus.eu'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def parse_catalogue(content):
    parser = Text()
    parser.feed(content.decode('utf-8'))
    text = ' '.join(parser.parts)
    require('/collections/' + DATASET + '"' in text, 'Exact dataset identity missing')
    require('Operational version - GloFAS v5.0 released' in text, 'Current v5.0 not verified')
    require('0.05° x 0.05°' in text and 'Daily data' in text, 'Grid/frequency not verified')
    return {'dataset_id': DATASET, 'version': VERSION,
            'hydrology_source_type': 'modelled_glofas',
            'verification_level': 'catalogue_only', 'grid_degrees': 0.05,
            'frequency': 'daily', 'native_files_verified': False}


def check_blocked(manifest):
    require(manifest['product']['dataset_id'] == DATASET and
            manifest['product']['version'] == VERSION, 'Product/version changed')
    require(manifest['product']['hydrology_source_type'] == 'modelled_glofas',
            'Measured/modelled conflation')
    require(manifest['readiness'] == 'glofas_access_blocked', 'Blocked readiness changed')
    require(manifest['access'] == {
        'credentials_configured': False, 'client_installed': False,
        'terms_acceptance': 'unverified', 'authenticated_request_attempted': False,
        'reason': 'local_access_configuration_absent_not_source_data_absence'},
        'Access snapshot changed; this checkpoint does not support retrieval')
    require(manifest['results'] == {
        'station_grid_matches': None, 'upstream_areas': None,
        'modelled_discharge': None, 'maxima': None,
        'measured_modelled_comparisons': None, 'calibration_relationships': None},
        'Extraction/calibration results prohibited in access-blocked checkpoint')
    require(manifest['product']['native_files_verified'] is False, 'Native files not acquired')


def assemble(raw=RAW):
    raw = Path(raw)
    originals = sorted(p for p in raw.iterdir() if p.suffix != '.json')
    require(len(originals) == 16 and len(list(raw.iterdir())) == 32, 'Source inventory changed')
    sources = []
    for path in originals:
        sidecar = path.with_name(path.name + '.json')
        metadata = json.loads(sidecar.read_bytes())
        source = urlparse(metadata['source_url'])
        final = urlparse(metadata['final_url'])
        require(source.scheme == final.scheme == 'https' and
                source.hostname in HOSTS and final.hostname in HOSTS and
                not source.username and not final.username, 'Unofficial/credential URL')
        require(metadata['status'] == 'retrieved' and str(metadata['http_status']) == '200',
                'Source metadata unavailable')
        require(sha(path.read_bytes()) == metadata['sha256'] and
                path.stat().st_size == metadata['bytes'], 'Original source checksum mismatch')
        sources.append({k: metadata[k] for k in ['source_url', 'final_url', 'retrieved_at',
            'content_type', 'bytes', 'sha256', 'deadline_seconds', 'byte_ceiling', 'attempts']})
        sources[-1].update(filename=path.name, sidecar_sha256=sha(sidecar.read_bytes()),
            content_status='javascript_shell_only' if path.name == 'glofas_reanalysis_release.html'
            else 'retrieved_document')
    result = {'version': 'karnataka_glofas_access_checkpoint_v1',
        'product': parse_catalogue((raw / 'glofas_catalogue.html').read_bytes()),
        'readiness': 'glofas_access_blocked',
        'access': {'credentials_configured': False, 'client_installed': False,
            'terms_acceptance': 'unverified', 'authenticated_request_attempted': False,
            'reason': 'local_access_configuration_absent_not_source_data_absence'},
        'access_evidence': 'Stage 4D local inspection on 2026-10-07; user chose blocked checkpoint',
        'results': {k: None for k in ['station_grid_matches', 'upstream_areas',
            'modelled_discharge', 'maxima', 'measured_modelled_comparisons', 'calibration_relationships']},
        'sources': sources, 'original_metadata_files': 32,
        'original_metadata_bytes': sum(p.stat().st_size for p in raw.iterdir()),
        'auxiliary_metadata': {'version': 'v2.1.1_OS-LISFLOOD-v5.x',
            'version_compatible_documentation': True, 'binary_grids_retrieved': False},
        'licences': {'historical': 'CEMS-FLOODS rev.1', 'static_maps': 'CC BY 4.0',
            'cwc_soi_redistribution': 'unresolved; detailed data retained locally'},
        'next_requirement': 'Legitimate local EWDS setup/terms acceptance before separate recovery',
        'processing_code_sha256': sha(Path(__file__).read_bytes())}
    check_blocked(result)
    return result


def build(output=OUTPUT, raw=RAW):
    output = Path(output)
    payload = encode(assemble(raw))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(payload)
    return {'readiness': 'glofas_access_blocked', 'manifest_sha256': sha(payload)}


def validate(output=OUTPUT, raw=RAW):
    payload = Path(output).read_bytes()
    check_blocked(json.loads(payload))
    require(payload == encode(assemble(raw)), 'Checkpoint reproduction mismatch')
    return {'readiness': 'glofas_access_blocked', 'manifest_sha256': sha(payload)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'])
    parser.add_argument('--raw', type=Path, default=RAW)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps((build if args.command == 'build' else validate)(args.output, args.raw), indent=2))
