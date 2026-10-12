#!/usr/bin/env python3
"""Bounded streaming inventory of four already retained NWDP files. No download.

Exact reviewed aliases nominate candidate histories, not a dated station-code
crosswalk. No row is promoted to training evidence. Only aggregate counts leave
the protected research structure; coordinates and measurement values stay local.
"""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RAW = Path('data/raw/reference/stage4b_v1')
OUTPUT = Path('data/working/riverine_series_inventory_phase12f_v1')
REGISTRY = Path('data/working/karnataka_hydrology_2019_pilot_v1/raw_source_registry.json')
ALIASES = {'sadalga (seasonal)': 'CW1KRU000083', 'sadalga': 'CW1KRU000083',
           'huvinhedigi': 'CW1KRU000339', 'huvinhedgi': 'CW1KRU000339',
           'huvinahedgi': 'CW1KRU000339', 'gokak falls': 'CW1KRU000212',
           'gokakfalls': 'CW1KRU000212'}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def candidate_alias(value):
    return ALIASES.get(value.strip().casefold())


def parse_source_time(value):
    for fmt in ('%d-%m-%Y %H:%M', '%d-%m-%Y'):
        try:
            return dt.datetime.strptime(value, fmt).isoformat()
        except ValueError:
            pass
    raise ValueError('Unreviewed source timestamp format')


def value_class(value, variable):
    from decimal import Decimal, InvalidOperation
    if value.strip() in {'', '-', 'NA', 'N/A'}:
        return 'MISSING', value
    try:
        v = Decimal(value)
        if not v.is_finite() or (variable == 'discharge' and v < 0):
            return 'INVALID', value
        return 'FINITE_SOURCE_VALUE_NOT_QC_APPROVED', str(v.normalize())
    except InvalidOperation:
        return 'INVALID', value


def scan(path, variable, db, source_id):
    groups = defaultdict(Counter); years = defaultdict(Counter); bounds = {}; dates = defaultdict(set)
    total = 0; field = None; name_field = None
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        field = next((k for k in reader.fieldnames if k in {
            'River Water Level Manual Hourly (meter)', 'Manual Daily River Water Discharge (m3/sec)',
            'Telemetry Hourly River Water Discharge (m3/sec)', 'Water Discharge'}), None)
        name_field = 'Station' if 'Station' in reader.fieldnames else 'Location Name'
        time_field = 'Data Acquisition Time' if 'Data Acquisition Time' in reader.fieldnames else 'Monitoring Date'
        if field is None or name_field not in reader.fieldnames or time_field not in reader.fieldnames:
            raise ValueError('Unreviewed archive schema')
        for row in reader:
            total += 1
            if total > 5000000:
                raise ValueError('Full archive scan row budget exceeded')
            station = candidate_alias(row[name_field])
            if not station:
                continue
            group = groups[station]; group['rows'] += 1
            classification, numeric = value_class(row[field], variable); group[classification] += 1
            try:
                when = parse_source_time(row[time_field])
            except ValueError:
                group['malformed_timestamps'] += 1
                continue
            years[(station, when[:4])]['rows'] += 1
            years[(station, when[:4])][classification] += 1
            dates[(station, when[:4])].add(when[:10])
            bounds[station] = (min(bounds.get(station, (when, when))[0], when),
                               max(bounds.get(station, (when, when))[1], when))
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?)', (source_id, station, when, numeric, classification))
            if total % 10000 == 0:
                db.commit()
    db.commit()
    station_records = []
    for station, counts in sorted(groups.items()):
        duplicated = db.execute('SELECT SUM(n-1) FROM (SELECT COUNT(*) n FROM observations WHERE source=? AND station=? GROUP BY time HAVING COUNT(*)>1)', (source_id, station)).fetchone()[0] or 0
        conflicting = db.execute('SELECT COUNT(*) FROM (SELECT time FROM observations WHERE source=? AND station=? GROUP BY time HAVING COUNT(DISTINCT value)>1)', (source_id, station)).fetchone()[0]
        unique = db.execute('SELECT COUNT(DISTINCT time) FROM observations WHERE source=? AND station=?', (source_id, station)).fetchone()[0]
        station_records.append({'station_id_candidate': station, 'source_resource_id': source_id,
            'variable': variable, 'counts': dict(sorted(counts.items())), 'unique_source_times': unique,
            'duplicate_timestamp_extra_rows': duplicated, 'conflicting_timestamp_groups': conflicting,
            'source_time_min': bounds.get(station, (None, None))[0], 'source_time_max': bounds.get(station, (None, None))[1],
            'timestamp_timezone': 'UNDOCUMENTED', 'historical_station_identity': 'EXACT_ALIAS_CANDIDATE_NOT_DATED_CODE_CROSSWALK',
            'quality_fields': 'ABSENT_FROM_INSPECTED_EXPORT_SCHEMA', 'eligible_training_rows': 0})
    year_records = [{'station_id_candidate': s, 'source_resource_id': source_id, 'variable': variable,
                     'year': int(y), 'source_date_count': len(dates[(s,y)]), 'counts': dict(sorted(c.items())),
                     'scheduled_completeness': 'UNKNOWN_NO_VALIDATED_EXPECTED_SCHEDULE', 'eligible_training_rows': 0}
                    for (s,y), c in sorted(years.items())]
    return {'total_archive_rows_scanned': total, 'original_columns': reader.fieldnames,
            'selected_value_field': field, 'station_records': station_records, 'year_records': year_records}


def assemble(root=ROOT, scratch=None):
    root = Path(root)
    registry = json.loads((root/REGISTRY).read_text())
    files, records, years = [], [], []
    scratch = Path(scratch or root/'data/recovery/phase12f_v1')
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='station_inventory_', dir=scratch) as temp:
        db = sqlite3.connect(str(Path(temp)/'inventory.sqlite'))
        try:
            db.execute('PRAGMA cache_size=-32768'); db.execute('PRAGMA temp_store=FILE')
            db.execute('CREATE TABLE observations (source TEXT, station TEXT, time TEXT, value TEXT, quality TEXT)')
            db.execute('CREATE INDEX station_time ON observations(source, station, time)')
            for source in registry:
                path = root/RAW/source['original_filename']; digest = sha(path)
                if digest != source['download']['sha256'] or path.stat().st_size != source['download']['bytes']:
                    raise ValueError('Retained NWDP source fingerprint mismatch')
                variable = 'water_level' if 'rwl_' in path.name else 'discharge'
                result = scan(path, variable, db, source['resource_id'])
                records.extend(result['station_records']); years.extend(result['year_records'])
                files.append({'filename': path.name, 'source_resource_id': source['resource_id'],
                    'source_url': source['download']['source_url'], 'source_sha256': digest,
                    'source_bytes': path.stat().st_size, 'source_class': 'CWC_NWDP_EXPORT_NOT_QC_CERTIFIED',
                    'global_rows_streamed': result['total_archive_rows_scanned'],
                    'candidate_station_rows': sum(x['counts']['rows'] for x in result['station_records']),
                    'quality_columns': source['schema_and_census'].get('quality_columns', []),
                    'access': 'ALREADY_RETAINED_NO_REDOWNLOAD', 'rights': 'DETAILED_DATA_LOCAL_ONLY'})
        finally:
            db.close()
    inventory = {'phase': '12F', 'scope': 'Four existing NWDP archives; exact alias screen for three retained station candidates only',
                 'alias_rule': ALIASES, 'files': files, 'candidate_series': records,
                 'global_rows_streamed': sum(x['global_rows_streamed'] for x in files),
                 'candidate_rows': sum(x['counts']['rows'] for x in records), 'eligible_training_rows': 0,
                 'all_candidate_rows_need_historical_identity_time_method_QC_review': True,
                 'no_match_meaning': 'No exact reviewed alias in this export; not proof of station data absence',
                 'memory_policy': 'Streaming CSV; SQLite32MiB cache and file temp store; only candidate date sets and aggregate counts in Python',
                 'no_observations_modified': True, 'no_features_labels_or_metrics': True}
    return {'measured_series_inventory.json': inventory, 'measured_station_year_coverage.json': years}


def build():
    output = ROOT/OUTPUT; public = ROOT/'docs/phase12f'
    if output.exists() or any((public/n).exists() for n in ('measured_series_inventory.json','measured_station_year_coverage.json')):
        raise ValueError('Version exists; validate instead')
    products = assemble(); output.mkdir(parents=True); public.mkdir(parents=True, exist_ok=True)
    for name, value in products.items():
        (output/name).open('xb').write(encoded(value)); (public/name).open('xb').write(encoded(value))
    (output/'manifest.json').open('xb').write(encoded({'code_sha256':sha(Path(__file__)),
        'registry_sha256':sha(ROOT/REGISTRY), 'products':{n:sha(output/n) for n in products}}))
    return {k:products['measured_series_inventory.json'][k] for k in ['global_rows_streamed','candidate_rows','eligible_training_rows']}


def validate():
    output = ROOT/OUTPUT; manifest=json.loads((output/'manifest.json').read_text())
    if sha(Path(__file__)) != manifest['code_sha256'] or sha(ROOT/REGISTRY) != manifest['registry_sha256']:
        raise ValueError('Inventory code/source registry changed')
    products=assemble()
    for name,value in products.items():
        if sha(output/name) != manifest['products'][name] or (output/name).read_bytes()!=encoded(value) or (ROOT/'docs/phase12f'/name).read_bytes()!=encoded(value):
            raise ValueError('Aggregate inventory reproduction mismatch')
    return {'status':'VALIDATED','products':len(products),'eligible_training_rows':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=['build','validate'])
    print(json.dumps((build if parser.parse_args().command=='build' else validate)(),indent=2))
