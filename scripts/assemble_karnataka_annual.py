#!/usr/bin/env python3
"""Offline, immutable 2025 assembly from twelve validated local monthly partitions.

No Earth Engine requests. SOI-derived rainfall values remain local; only provenance
and checksums are publication candidates. August records are concatenated verbatim.
"""
import argparse
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_karnataka_rainfall as rain

ROOT = rain.ROOT
DEFAULT_OUTPUT = ROOT / 'data/working/karnataka_chirps_soi2025_2025_v1'
DEFAULT_METADATA = ROOT / 'data/reference/karnataka_chirps_2025_v1/manifest.json'
TOTAL_FIELDS = ['source_district_lgd_code', 'district_name_original', 'nic_exact_name',
                'identity_status', 'geometry_edition', 'period_start', 'period_end',
                'units', 'expected_days', 'valid_days', 'complete_pixel_coverage_days',
                'total_mm', 'status']
METHOD = 'sum of native-cell-centre district daily means; not station measurements; total unavailable unless all days have complete pixel coverage'


def load_partitions(boundaries=rain.BOUNDARIES):
    partitions = []
    for month in range(1, 13):
        suffix = f'2025{month:02d}'
        directory = ROOT / f'data/working/karnataka_chirps_soi2025_{suffix}_v1'
        raw = ROOT / f'data/raw/chirps/karnataka_window_{suffix}_verified_v1'
        rain.require((directory / 'manifest.json').is_file(),
                     f'Required completed monthly partition unavailable: {suffix}; annual assembly blocked')
        rain.validate_dataset(directory, raw, boundaries)
        manifest = json.loads((directory / 'manifest.json').read_text())
        rain.require(manifest['mode'] == 'month' and manifest.get('month', 8) == month,
                     'Monthly partition identity mismatch')
        if partitions:
            previous = partitions[0]['manifest']
            for field in ['source', 'geometry_provenance', 'method', 'download_parameters', 'csv_fields']:
                rain.require(previous[field] == manifest[field], f'Partition {field} mismatch')
        partitions.append({'month': month, 'directory': directory, 'raw_directory': raw,
                           'manifest': manifest, 'rows': rain.read_table(directory / 'daily_rainfall.csv'),
                           'csv_bytes': (directory / 'daily_rainfall.csv').read_bytes()})
        print(json.dumps({'validated_month': month, 'records': manifest['validation']['records']}), flush=True)
    return partitions


def totals(rows, start, end):
    days = [(date.fromisoformat(start) + rain.timedelta(days=i)).isoformat()
            for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
    groups = {}
    keys = set()
    for row in rows:
        key = (row['source_district_lgd_code'], row['date'])
        rain.require(key not in keys and row['date'] in days, 'Duplicate or out-of-period total input')
        keys.add(key)
        groups.setdefault(key[0], []).append(row)
    results = []
    for code, records in groups.items():
        rain.require(set(r['date'] for r in records) == set(days), 'Missing date in total input')
        first = records[0]
        valid = sum(r['valid_pixel_count'] > 0 for r in records)
        complete = sum(r['status'] == 'available' for r in records)
        total = math.fsum(r['mean_mm_per_day'] for r in records) if complete == len(days) else None
        rain.require(total is None or math.isfinite(total) and total >= 0, 'Invalid derived rainfall total')
        results.append({**{k: first[k] for k in TOTAL_FIELDS[:5]}, 'period_start': start, 'period_end': end,
                        'units': 'mm', 'expected_days': len(days), 'valid_days': valid,
                        'complete_pixel_coverage_days': complete, 'total_mm': total,
                        'status': 'complete' if total is not None else 'incomplete_observations'})
    return results


def joined_content(partitions):
    rain.require([p['month'] for p in partitions] == list(range(1, 13)), 'Require twelve chronological 2025 partitions')
    result, rows, header, august = bytearray(), [], None, None
    for partition in partitions:
        manifest = partition['manifest']
        for field in ['source', 'geometry_provenance', 'method', 'download_parameters', 'csv_fields']:
            rain.require(manifest[field] == partitions[0]['manifest'][field], f'Partition {field} mismatch')
        days = rain.requested_dates('month', partition['month'])
        rain.require(manifest['dates'] == days, 'Partition date coverage mismatch')
        rain.validate_rows(partition['rows'], manifest['geometry_provenance']['identities'], days)
        lines = partition['csv_bytes'].splitlines(keepends=True)
        rain.require(lines and lines[0].endswith(b'\n'), 'Invalid CSV header')
        if header is None:
            header = lines[0]
            result.extend(header)
        rain.require(lines[0] == header, 'Monthly CSV headers differ')
        body = b''.join(lines[1:])
        if partition['month'] == 8:
            august = {'records': len(partition['rows']), 'offset_bytes': len(result), 'bytes': len(body),
                      'original_record_bytes_sha256': hashlib.sha256(body).hexdigest(),
                      'original_table': rain.soi.fingerprint(partition['directory'] / 'daily_rainfall.csv'),
                      'unchanged': True}
        result.extend(body)
        rows.extend(partition['rows'])
    identities = partitions[0]['manifest']['geometry_provenance']['identities']
    dates = [day for month in range(1, 13) for day in rain.requested_dates('month', month)]
    validation = rain.validate_rows(rows, identities, dates)
    return bytes(result), rows, august, validation


def table_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=TOTAL_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def products(partitions):
    content, rows, august, validation = joined_content(partitions)
    monthly = [record for p in partitions for record in totals(p['rows'], p['manifest']['dates'][0], p['manifest']['dates'][-1])]
    annual = totals(rows, '2025-01-01', '2025-12-31')
    return {'daily_rainfall.csv': content, 'monthly_totals.csv': table_bytes(monthly),
            'annual_totals.csv': table_bytes(annual)}, august, {**validation, 'monthly_total_records': len(monthly),
            'complete_monthly_totals': sum(r['status'] == 'complete' for r in monthly),
            'annual_total_records': len(annual), 'complete_annual_totals': sum(r['status'] == 'complete' for r in annual)}


def partition_provenance(partitions):
    return [{'month': p['month'], 'version': p['manifest']['version'],
             'local_directory': str(p['directory'].relative_to(ROOT)),
             'raw_directory': str(p['raw_directory'].relative_to(ROOT)),
             'manifest': rain.soi.fingerprint(p['directory'] / 'manifest.json'),
             'table': rain.soi.fingerprint(p['directory'] / 'daily_rainfall.csv'),
             'raw_retrieval_log': p['manifest']['raw_retrieval_log'],
             'retrieval_start': min(i['download']['retrieved_at'] for i in p['manifest']['images']),
             'retrieval_end': max(i['download']['retrieved_at'] for i in p['manifest']['images']),
             'source_image_ids': [i['source_image_id'] for i in p['manifest']['images']]} for p in partitions]


def assemble(output, metadata_output, partitions):
    rain.require_new_output(output)
    rain.require_new_output(metadata_output)
    files, august, validation = products(partitions)
    first = partitions[0]['manifest']
    manifest = {'version': output.name, 'created_at': rain.now(), 'year': 2025, 'stage_1_complete': False,
                'source': first['source'], 'geometry_provenance': first['geometry_provenance'],
                'download_parameters': first['download_parameters'], 'daily_method': first['method'],
                'totals_method': METHOD, 'temporal_semantics': first['temporal_semantics'],
                'geometry_temporal_limit': first['geometry_temporal_limit'], 'identity_limit': first['identity_limit'],
                'reuse': first['reuse'], 'monthly_partitions': partition_provenance(partitions),
                'august_record_preservation': august, 'validation': validation,
                'schemas': {'daily_rainfall.csv': rain.FIELDS, 'monthly_totals.csv': TOTAL_FIELDS, 'annual_totals.csv': TOTAL_FIELDS},
                'processing_code': rain.soi.fingerprint(Path(__file__))}
    output.mkdir(parents=True)
    for name, content in files.items():
        with (output / name).open('xb') as stream:
            stream.write(content)
    manifest['files'] = {name: rain.soi.fingerprint(output / name) for name in files}
    rain.write_json(output / 'manifest.json', manifest)
    validate(output, partitions)
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    rain.write_json(metadata_output, {**manifest, 'published_content': 'provenance, coverage and checksums only; rainfall tables and SOI geometry local only'})
    return validation


def validate(output, partitions):
    manifest = json.loads((output / 'manifest.json').read_text())
    rain.require(set(p.name for p in output.iterdir()) == {'manifest.json', 'daily_rainfall.csv', 'monthly_totals.csv', 'annual_totals.csv'}, 'Unexpected annual files')
    expected, august, validation = products(partitions)
    for name, content in expected.items():
        rain.require((output / name).read_bytes() == content and rain.soi.fingerprint(output / name) == manifest['files'][name], 'Annual byte content/checksum mismatch')
    rain.require(manifest['monthly_partitions'] == partition_provenance(partitions), 'Monthly provenance changed')
    first = partitions[0]['manifest']
    rain.require(manifest['year'] == 2025 and manifest['stage_1_complete'] is False
                 and manifest['august_record_preservation'] == august and manifest['validation'] == validation,
                 'Annual coverage/August preservation mismatch')
    for annual, monthly in [('source', 'source'), ('geometry_provenance', 'geometry_provenance'),
                            ('download_parameters', 'download_parameters'), ('daily_method', 'method'),
                            ('reuse', 'reuse'), ('temporal_semantics', 'temporal_semantics'),
                            ('geometry_temporal_limit', 'geometry_temporal_limit'), ('identity_limit', 'identity_limit')]:
        rain.require(manifest[annual] == first[monthly], 'Annual source/method provenance mismatch')
    rain.require(manifest['totals_method'] == METHOD and manifest['schemas'] ==
                 {'daily_rainfall.csv': rain.FIELDS, 'monthly_totals.csv': TOTAL_FIELDS, 'annual_totals.csv': TOTAL_FIELDS},
                 'Annual schema/totals method mismatch')
    # Explicitly parse the resulting daily table, in addition to exact byte checks.
    rain.require(rain.read_table(output / 'daily_rainfall.csv') == [r for p in partitions for r in p['rows']], 'Annual parsed records differ')
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--metadata-output', type=Path, default=DEFAULT_METADATA)
    parser.add_argument('--boundaries', type=Path, default=rain.BOUNDARIES)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if not args.validate_only:
        rain.require_new_output(args.output)
        rain.require_new_output(args.metadata_output)
    partitions = load_partitions(args.boundaries)
    result = validate(args.output, partitions) if args.validate_only else assemble(args.output, args.metadata_output, partitions)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
