#!/usr/bin/env python3
"""Offline, immutable 2025 assembly from twelve validated local monthly partitions.

No Earth Engine requests. SOI-derived rainfall values remain local; only provenance
and checksums are publication candidates. Original CSV records are copied verbatim,
ordered by observation date and numeric SOI-supplied district identifier.
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
from tempfile import TemporaryDirectory

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
ASSEMBLY_METHOD = 'copy each original CSV record once, without serialization or value changes; order by observation date and numeric SOI-supplied district identifier; no raster recalculation or external requests'
STAT_FIELDS = ['mean_mm_per_day', 'min_mm_per_day', 'max_mm_per_day']


def original_records(content):
    """Pair parsed string fields with original bytes, including quoted newlines."""
    lines = io.BytesIO(content).readlines()
    reader = csv.reader(line.decode('utf-8') for line in lines)
    rain.require(next(reader, None) == rain.FIELDS, 'Unexpected monthly CSV schema')
    header_end = reader.line_num
    rain.require(header_end == 1 and lines[0].endswith(b'\n'), 'Invalid CSV header')
    previous, records = header_end, []
    for fields in reader:
        rain.require(len(fields) == len(rain.FIELDS), 'Unexpected monthly CSV record schema')
        record = b''.join(lines[previous:reader.line_num])
        rain.require(record.endswith(b'\n'), 'Unterminated CSV record')
        records.append((dict(zip(rain.FIELDS, fields)), record))
        previous = reader.line_num
    rain.require(previous == len(lines), 'Unparsed monthly CSV bytes')
    return lines[0], records


def check_partition(partition):
    """Validate completed manifests/tables offline; never rebuild rain from rasters."""
    directory, manifest = partition['directory'], partition['manifest']
    rain.require(set(p.name for p in directory.iterdir()) == {'manifest.json', 'daily_rainfall.csv'},
                 'Unexpected or incomplete monthly partition files')
    rain.require(json.loads((directory / 'manifest.json').read_text()) == manifest, 'Monthly manifest changed')
    rain.require(manifest['version'] == directory.name, 'Monthly version/directory mismatch')
    table = directory / 'daily_rainfall.csv'
    # Check the recorded checksum BEFORE reading or parsing observations.
    rain.require(rain.soi.fingerprint(table) == manifest['files']['daily_rainfall.csv'], 'Monthly table checksum mismatch')
    rain.require(manifest['mode'] == 'month' and manifest.get('month', 8) == partition['month'], 'Monthly partition identity mismatch')
    days = rain.requested_dates('month', partition['month'])
    rain.require(manifest['dates'] == days and manifest['csv_fields'] == rain.FIELDS, 'Monthly dates/schema mismatch')
    rain.require(manifest['source']['collection'] == rain.SOURCE and manifest['source']['units'] == 'mm/day'
                 and manifest['source']['native_resolution_degrees'] == 0.05, 'Monthly source units/resolution mismatch')
    rain.require(manifest['geometry_provenance']['edition'] == '2025'
                 and manifest['geometry_provenance']['source_id'] == rain.SOURCE_GEOMETRY
                 and manifest['geometry_provenance']['current_lgd_reconciled'] is False,
                 'Monthly geometry identity/vintage mismatch')
    rain.require([i['source_image_id'] for i in manifest['images']] ==
                 [rain.SOURCE + '/' + day.replace('-', '') for day in days], 'Monthly source image coverage mismatch')
    content = table.read_bytes()
    rain.require(content == partition['csv_bytes'] and rain.read_table(table) == partition['rows'], 'Monthly records changed')
    original_records(content)
    result = rain.validate_rows(partition['rows'], manifest['geometry_provenance']['identities'], days)
    rain.require(result == manifest['validation'], 'Monthly coverage validation mismatch')
    rain.require(result['complete_pixel_coverage_records'] == result['requested_records']
                 and not result['missing_observations'] and result['partial_pixel_coverage_records'] == 0,
                 'Incomplete monthly observations; annual assembly blocked')
    return result


def load_partitions(boundaries=rain.BOUNDARIES):
    partitions = []
    for month in range(1, 13):
        suffix = f'2025{month:02d}'
        directory = ROOT / f'data/working/karnataka_chirps_soi2025_{suffix}_v1'
        rain.require((directory / 'manifest.json').is_file(),
                     f'Required completed monthly partition unavailable: {suffix}; annual assembly blocked')
        manifest = json.loads((directory / 'manifest.json').read_text())
        raw = ROOT / manifest.get('raw_directory', f'data/raw/chirps/karnataka_window_{suffix}_verified_v1')
        rain.require(raw.resolve().is_relative_to((ROOT / 'data/raw/chirps').resolve()), 'Raw partition path outside local CHIRPS storage')
        # The existing raster validators run separately. Assembly uses ONLY source
        # CSV observations and validates their manifest, checksum, schema and keys.
        rain.require(rain.soi.fingerprint(directory / 'daily_rainfall.csv') == manifest['files']['daily_rainfall.csv'],
                     'Monthly table checksum mismatch')
        rain.require(manifest['mode'] == 'month' and manifest.get('month', 8) == month,
                     'Monthly partition identity mismatch')
        if partitions:
            previous = partitions[0]['manifest']
            for field in ['source', 'geometry_provenance', 'method', 'download_parameters', 'csv_fields']:
                rain.require(previous[field] == manifest[field], f'Partition {field} mismatch')
        partition = {'month': month, 'directory': directory, 'raw_directory': raw,
                     'manifest': manifest, 'rows': rain.read_table(directory / 'daily_rainfall.csv'),
                     'csv_bytes': (directory / 'daily_rainfall.csv').read_bytes()}
        check_partition(partition)
        partitions.append(partition)
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
        check_partition(partition)
        manifest = partition['manifest']
        for field in ['source', 'geometry_provenance', 'method', 'download_parameters', 'csv_fields']:
            rain.require(manifest[field] == partitions[0]['manifest'][field], f'Partition {field} mismatch')
        days = rain.requested_dates('month', partition['month'])
        rain.require(manifest['dates'] == days, 'Partition date coverage mismatch')
        rain.validate_rows(partition['rows'], manifest['geometry_provenance']['identities'], days)
        source_header, originals = original_records(partition['csv_bytes'])
        if header is None:
            header = source_header
            result.extend(header)
        rain.require(source_header == header, 'Monthly CSV headers differ')
        order = sorted(range(len(originals)), key=lambda i: (originals[i][0]['date'], int(originals[i][0]['source_district_lgd_code'])))
        body = b''.join(originals[i][1] for i in order)
        source_body = b''.join(record for _, record in originals)
        if partition['month'] == 8:
            august = {'records': len(partition['rows']), 'offset_bytes': len(result), 'bytes': len(body),
                      'original_record_bytes_sha256': hashlib.sha256(source_body).hexdigest(),
                      'annual_ordered_record_bytes_sha256': hashlib.sha256(body).hexdigest(),
                      'source_order_preserved': body == source_body,
                      'original_table': rain.soi.fingerprint(partition['directory'] / 'daily_rainfall.csv'),
                      'original_records_unchanged': True}
        result.extend(body)
        rows.extend(partition['rows'][i] for i in order)
    identities = partitions[0]['manifest']['geometry_provenance']['identities']
    dates = [day for month in range(1, 13) for day in rain.requested_dates('month', month)]
    validation = rain.validate_rows(rows, identities, dates)
    return bytes(result), rows, august, validation


def statistics(rows):
    """Equality diagnostics, not regional precipitation or new scientific features."""
    result = {}
    for field in STAT_FIELDS:
        values = [r[field] for r in rows]
        rain.require(values and all(v is not None and math.isfinite(v) for v in values), 'Missing/nonfinite rainfall in statistics')
        total = math.fsum(values)
        result[field] = {'sum': total, 'minimum': min(values), 'maximum': max(values), 'mean': total / len(values)}
    return result


def equality_checks(content, partitions, annual_rows=None):
    """Prove one-to-one origin, every month's values/bytes/statistics and 365 dates."""
    _, annual_records = original_records(content)
    expected_rows = [r for p in partitions for r in p['rows']]
    annual_strings = [r for r, _ in annual_records]
    sources, original_bytes = {}, {}
    for p in partitions:
        _, records = original_records(p['csv_bytes'])
        for (strings, raw), parsed in zip(records, p['rows']):
            key = (strings['source_district_lgd_code'], strings['date'])
            rain.require(key not in sources, 'Duplicate source district-date key')
            sources[key], original_bytes[key] = parsed, raw
    keys = [(r['source_district_lgd_code'], r['date']) for r in annual_strings]
    rain.require(len(keys) == len(set(keys)) and set(keys) == set(sources), 'Annual/source district-date keys differ')
    rain.require(keys == sorted(keys, key=lambda k: (k[1], int(k[0]))), 'Annual deterministic ordering mismatch')
    rain.require(all(raw == original_bytes[key] for key, (_, raw) in zip(keys, annual_records)), 'Annual original record bytes differ')
    expected = [sources[key] for key in keys]
    rows = annual_rows if annual_rows is not None else expected
    rain.require(rows == expected, 'Annual parsed observations differ from monthly inputs')
    checks = []
    for p in partitions:
        subset = [r for r in rows if int(r['date'][5:7]) == p['month']]
        source = sorted(p['rows'], key=lambda r: (r['date'], int(r['source_district_lgd_code'])))
        rain.require(subset == source, 'Monthly/annual observations differ')
        source_stats, annual_stats = statistics(source), statistics(subset)
        rain.require(source_stats == annual_stats, 'Monthly/annual statistics differ')
        checks.append({'month': p['month'], 'records': len(source), 'logical_equality': True,
                       'original_record_bytes_preserved': True, 'statistics_equal': True,
                       'source_statistics': source_stats, 'annual_statistics': annual_stats})
    days = {d for month in range(1, 13) for d in rain.requested_dates('month', month)}
    district_checks = []
    for code in sorted({r['source_district_lgd_code'] for r in expected_rows}, key=int):
        observed = [r['date'] for r in rows if r['source_district_lgd_code'] == code]
        rain.require(len(observed) == 365 and set(observed) == days, 'District annual date coverage mismatch')
        district_checks.append({'source_district_lgd_code': code, 'observations': len(observed),
                                'unique_dates': len(set(observed)), 'missing_dates': 0, 'duplicate_dates': 0})
    return checks, district_checks


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
    checks, district_checks = equality_checks(files['daily_rainfall.csv'], partitions)
    validation = {**validation, 'contributing_months': 12, 'unique_dates': 365, 'unique_districts': len(district_checks),
                  'duplicate_keys': 0, 'missing_rainfall_values': 0, 'coverage_status': 'complete'}
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
    manifest.update(assembly_method=ASSEMBLY_METHOD, record_order=['date', 'numeric source_district_lgd_code'],
                    boundary_identifier_fields=['source_state_lgd_code', 'source_district_lgd_code'],
                    monthly_equality_checks=checks, district_coverage_checks=district_checks)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate a disposable candidate before publishing any completed version.
    with TemporaryDirectory(prefix='.annual-candidate-', dir=output.parent) as temporary:
        candidate = Path(temporary) / output.name
        candidate.mkdir()
        for name, content in files.items():
            with (candidate / name).open('xb') as stream:
                stream.write(content)
        manifest['files'] = {name: rain.soi.fingerprint(candidate / name) for name in files}
        rain.write_json(candidate / 'manifest.json', manifest)
        validate(candidate, partitions)
        rain.require_new_output(output)
        candidate.rename(output)
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    public = {**manifest, 'monthly_equality_checks': [{k: v for k, v in check.items()
              if k not in {'source_statistics', 'annual_statistics'}} for check in checks],
              'local_manifest': rain.soi.fingerprint(output / 'manifest.json'),
              'published_content': 'provenance, coverage and checksums only; rainfall tables, statistics and SOI geometry local only'}
    rain.write_json(metadata_output, public)
    return validation


def validate(output, partitions):
    manifest = json.loads((output / 'manifest.json').read_text())
    rain.require(set(p.name for p in output.iterdir()) == {'manifest.json', 'daily_rainfall.csv', 'monthly_totals.csv', 'annual_totals.csv'}, 'Unexpected annual files')
    expected, august, validation = products(partitions)
    for name, content in expected.items():
        rain.require((output / name).read_bytes() == content and rain.soi.fingerprint(output / name) == manifest['files'][name], 'Annual byte content/checksum mismatch')
    rain.require(manifest['monthly_partitions'] == partition_provenance(partitions), 'Monthly provenance changed')
    first = partitions[0]['manifest']
    actual_rows = rain.read_table(output / 'daily_rainfall.csv')
    checks, district_checks = equality_checks((output / 'daily_rainfall.csv').read_bytes(), partitions, actual_rows)
    validation = {**validation, 'contributing_months': 12, 'unique_dates': 365, 'unique_districts': len(district_checks),
                  'duplicate_keys': 0, 'missing_rainfall_values': 0, 'coverage_status': 'complete'}
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
    rain.require(actual_rows == sorted([r for p in partitions for r in p['rows']],
                 key=lambda r: (r['date'], int(r['source_district_lgd_code']))), 'Annual parsed records differ')
    rain.require(manifest['version'] == output.name and manifest['assembly_method'] == ASSEMBLY_METHOD
                 and manifest['record_order'] == ['date', 'numeric source_district_lgd_code']
                 and manifest['boundary_identifier_fields'] == ['source_state_lgd_code', 'source_district_lgd_code']
                 and manifest['monthly_equality_checks'] == checks and manifest['district_coverage_checks'] == district_checks,
                 'Annual equality/coverage/assembly provenance mismatch')
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
