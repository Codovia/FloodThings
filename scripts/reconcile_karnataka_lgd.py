#!/usr/bin/env python3
"""Offline LGD reconciliation; never rewrites SOI attributes or frozen datasets.

Column names and any status vocabulary must be supplied from inspected originals.
No fuzzy matching, automatic aliases, network access or geometry publication.
"""
import argparse
from collections import Counter
from datetime import datetime
import csv
from io import StringIO
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_URL = 'https://data.gov.in/resource/local-government-directory-lgd-districts'
VERSION = 'karnataka_identity_policy_20261005_v1'
OUTPUT = ROOT / 'data/reference' / VERSION
LABEL = 'SOI source-supplied LGD identifiers, not independently current-LGD verified'
POLICY = {
    'original_soi_geometry': 'withhold',
    'transformed_soi_geometry': 'withhold',
    'rasterised_soi_geometry': 'withhold',
    'soi_derived_rainfall_statistics': 'withhold',
    'project_authored_non_spatial_metadata_checksums_code': 'allow',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(path):
    path = Path(path)
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


def normalized(name):
    return ' '.join(name.split()).casefold()


def code(value):
    require(isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,7}', value), 'Malformed source code')
    return value  # No coercion or invented identifiers.


def unique(values, label):
    require(all(count == 1 for count in Counter(values).values()), 'Duplicate/conflicting ' + label)


def validate_current(rows):
    require(bool(rows), 'No Karnataka district records')
    for row in rows:
        code(row['state_code']); code(row['district_code'])
        require(row['state_code'] == '29', 'Conflicting Karnataka state code')
        require(isinstance(row['district_name'], str) and row['district_name'].strip(), 'Missing current name')
        require(row.get('active') is None or type(row['active']) is bool, 'Ambiguous active status')
    unique([r['district_code'] for r in rows], 'current LGD codes/rows')
    unique([normalized(r['district_name']) for r in rows if r.get('active') is not False], 'active district names')


def parse_current_csv(body, columns, active_values=None, inactive_values=None):
    """Retain original names/codes and rows; filter using explicitly mapped state field."""
    reader = csv.DictReader(StringIO(body.decode('utf-8-sig'), newline=''))
    fields = reader.fieldnames
    require(fields and len(fields) == len(set(fields)), 'Missing/duplicate original columns')
    require({'state_code', 'district_code', 'district_name'} <= set(columns), 'Explicit column mapping required')
    require(set(columns) <= {'state_code', 'district_code', 'district_name', 'state_name', 'status'}, 'Unknown mapping role')
    require(set(columns.values()) <= set(fields), 'Mapped original column missing')
    require(len(set(columns.values())) == len(columns), 'Conflicting column mappings')
    if 'status' in columns:
        require(active_values and inactive_values and not set(active_values) & set(inactive_values), 'Explicit disjoint status vocabulary required')
    rows = []
    for original in reader:
        require(None not in original and all(v is not None for v in original.values()), 'Malformed CSV row')
        state = code(original[columns['state_code']])
        if state != '29':
            continue
        if 'state_name' in columns:
            require(normalized(original[columns['state_name']]) == 'karnataka', 'Karnataka code/name disagreement')
        active = None
        if 'status' in columns:
            status = original[columns['status']]
            require(status in set(active_values) | set(inactive_values), 'Unknown source status')
            active = status in active_values
        rows.append({'state_code': state, 'district_code': code(original[columns['district_code']]),
                     'district_name': original[columns['district_name']], 'active': active, 'original_row': original})
    validate_current(rows)
    return {'original_columns': fields, 'records': rows, 'active_status_supplied': 'status' in columns,
            'current_record_count': sum(r['active'] is not False for r in rows)}


def load_official_csv(path, retrieval, columns, **status):
    require(retrieval.get('http_status') == 200, 'Official download failed; cannot parse district records')
    require(retrieval.get('catalogue_url') == CATALOGUE_URL, 'Unverified official catalogue provenance')
    url = urlparse(retrieval['source_url'])
    require(url.scheme == 'https' and url.hostname in {'data.gov.in', 'www.data.gov.in', 'api.data.gov.in'}, 'Non-OGD source')
    require('csv' in retrieval.get('content_type', '').lower(), 'Official CSV content type required')
    require(datetime.fromisoformat(retrieval['retrieved_at']).tzinfo is not None, 'Timezone required')
    datetime.fromisoformat(retrieval['dataset_update_date'])
    require(fingerprint(path) == {k: retrieval[k] for k in ('sha256', 'bytes')}, 'Official response checksum mismatch')
    return parse_current_csv(Path(path).read_bytes(), columns, **status)


def reconcile(soi_rows, current_rows=None, documented_names=()):
    """Code + exact name, or explicit government evidence; preserve every source field."""
    unique([code(r['district_lgd_code_as_supplied_by_soi']) for r in soi_rows], 'SOI district codes')
    for row in soi_rows:
        require(row['state_lgd_code_as_supplied_by_soi'] == '29', 'Conflicting SOI state identity')
        require(row['district_name_original'].strip(), 'Missing SOI original name')
    if current_rows is not None:
        validate_current(current_rows)
    current = {r['district_code']: r for r in current_rows or [] if r.get('active') is not False}
    evidence = {}
    for item in documented_names:
        key = (code(item['state_code']), code(item['district_code']), item['source_name'], item['current_name'])
        require(key not in evidence, 'Ambiguous documented aliases')
        parsed = urlparse(item['source_url'])
        require(parsed.scheme == 'https' and parsed.hostname and
                (parsed.hostname.endswith('.gov.in') or parsed.hostname.endswith('.nic.in')), 'Government name evidence required')
        require(item.get('kind') in {'rename', 'spelling_difference', 'independently_verified_alias'} and item.get('evidence_date'), 'Incomplete name evidence')
        datetime.fromisoformat(item['evidence_date'])
        evidence[key] = item
    results = []
    for source in sorted(soi_rows, key=lambda r: int(r['district_lgd_code_as_supplied_by_soi'])):
        district = source['district_lgd_code_as_supplied_by_soi']
        candidate = current.get(district)
        name = source['district_name_original']
        classification, proof = 'unresolved', None
        if candidate:
            proof = evidence.get(('29', district, name, candidate['district_name']))
            if name == candidate['district_name']:
                classification = 'exact_code_name_match'
            elif proof:
                classification = ('independently_verified_alias' if proof['kind'] == 'independently_verified_alias'
                                  else 'code_match_documented_name_difference')
        # Never infer a new code from a same-name record with a conflicting code.
        conflicts = [r for r in current.values() if normalized(r['district_name']) == normalized(name) and r['district_code'] != district]
        require(not conflicts, 'Conflicting source/current district codes')
        verified = classification != 'unresolved'
        results.append({'soi_state_code': source['state_lgd_code_as_supplied_by_soi'], 'soi_district_code': district,
                        'soi_name_original': name, 'source_identifier_status':
                        ('SOI source-supplied identifier; current identity verified in separate mapping' if verified else LABEL),
                        'nic_exact_name_candidate': source.get('nic_exact_name'),
                        'current_lgd_verified': verified, 'classification': classification,
                        'current_state_code': candidate['state_code'] if verified else None,
                        'current_district_code': candidate['district_code'] if verified else None,
                        'current_name': candidate['district_name'] if verified else None,
                        'code_match_name_unresolved_candidate': candidate['district_name'] if candidate and not verified else None,
                        'name_evidence': proof if verified else None})
    return results


def assert_publishable(kind):
    require(POLICY.get(kind) == 'allow', 'Publication withheld or artifact scope unknown: ' + kind)


def validate_output(directory):
    """Read-only reproducibility check for the retained fallback mapping and metadata."""
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    require(set(p.name for p in directory.iterdir()) == {'manifest.json', 'mapping.json', 'publication_policy.json'}, 'Unexpected dependency-version files')
    require(manifest['version'] == directory.name, 'Dependency version mismatch')
    for name, expected in manifest['files'].items():
        require(fingerprint(directory / name) == expected, 'Dependency output checksum mismatch')
    for name, expected in manifest['inputs'].items():
        require(fingerprint(ROOT / name) == expected, 'Retained source checksum mismatch')
    source = json.loads((ROOT / manifest['soi_manifest_path']).read_text())
    require(manifest['lgd']['status'] == 'unavailable_http_403', 'This fallback version has no verified LGD input')
    require(json.loads((directory / 'mapping.json').read_text()) == reconcile(source['district_records']), 'Fallback mapping differs from retained SOI identities')
    require(manifest['coverage']['reconciled_polygons'] == 0 and manifest['coverage']['unresolved_polygons'] == len(source['district_records']), 'Fallback coverage mismatch')
    policy = json.loads((directory / 'publication_policy.json').read_text())
    require(policy['repository_decisions'] == POLICY, 'Publication handling changed; separate review required')
    require(manifest['stage_1_current_lgd_complete'] is False and manifest['later_flood_evidence_research_blocked_by_lgd_outage'] is False, 'Fallback acceptance status mismatch')
    return manifest['coverage']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(validate_output(args.validate_only), indent=2))
