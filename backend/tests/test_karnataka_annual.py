"""Controlled annual fixtures remain exclusively in disposable directories."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import importlib.util
import io
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/assemble_karnataka_annual.py'
spec = importlib.util.spec_from_file_location('karnataka_annual', SCRIPT)
annual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(annual)
rain = annual.rain


def snapshot(root):
    return {str(p): (p.read_bytes(), rain.soi.digest(p), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def fixtures(root):
    identities = [{'district_lgd_code_as_supplied_by_soi': str(569+i),
                   'district_name_original': f'Fixture,{i}', 'nic_exact_name': None} for i in range(2)]
    partitions = []
    for month in range(1, 13):
        rows, days = [], rain.requested_dates('month', month)
        for day in days:
            start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000)
            for identity in identities:
                rows.append({'source_state_lgd_code': '29',
                             'source_district_lgd_code': identity['district_lgd_code_as_supplied_by_soi'],
                             'district_name_original': identity['district_name_original'], 'nic_exact_name': None,
                             'identity_status': 'soi_supplied_identifier_pending_current_lgd_verification',
                             'geometry_edition': '2025', 'geometry_source_id': rain.SOURCE_GEOMETRY,
                             'geometry_version': rain.soi.VERSION, 'date': day, 'source_collection': rain.SOURCE,
                             'source_image_id': rain.SOURCE+'/'+day.replace('-', ''),
                             'source_time_start_ms': start, 'source_time_end_ms': start+86400000,
                             'image_asset_version': 1, 'units': 'mm/day', 'mean_mm_per_day': 2.5,
                             'min_mm_per_day': 2.5, 'max_mm_per_day': 2.5,
                             'expected_pixel_count': 1, 'valid_pixel_count': 1, 'valid_fraction': 1.0,
                             'status': 'available', 'retrieved_at': '2026-10-04T00:00:00+00:00'})
        directory = root/f'month{month}'
        directory.mkdir()
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=rain.FIELDS)
        writer.writeheader(); writer.writerows(rows)
        body = stream.getvalue().encode()
        (directory/'daily_rainfall.csv').write_bytes(body)
        manifest = {'version': directory.name, 'mode': 'month', 'dates': days,
                    'source': {'collection': rain.SOURCE, 'version': 'fixture only', 'units': 'mm/day',
                               'native_resolution_degrees': 0.05},
                    'geometry_provenance': {'identities': identities, 'current_lgd_reconciled': False,
                                            'edition': '2025', 'source_id': rain.SOURCE_GEOMETRY},
                    'method': 'fixture daily means', 'download_parameters': {}, 'csv_fields': rain.FIELDS,
                    'raw_retrieval_log': {'sha256': 'fixture only', 'bytes': 0},
                    'images': [{'source_image_id': rain.SOURCE+'/'+day.replace('-', ''),
                                'download': {'retrieved_at': rows[0]['retrieved_at']}} for day in days],
                    'temporal_semantics': 'fixture historical estimates', 'geometry_temporal_limit': '2025 geometry only',
                    'identity_limit': 'pending current LGD', 'reuse': {'district_aggregate_publication': 'local only'},
                    'files': {'daily_rainfall.csv': rain.soi.fingerprint(directory/'daily_rainfall.csv')},
                    'validation': rain.validate_rows(rows, identities, days)}
        if month != 8:
            manifest['month'] = month  # Original August manifest has no month field.
        (directory/'manifest.json').write_text(json.dumps(manifest))
        partitions.append({'month': month, 'directory': directory, 'raw_directory': directory,
                           'manifest': manifest, 'rows': rows, 'csv_bytes': body})
    return partitions


def test_annual_assembly_preserves_month_bytes_hashes_times_and_august_rows(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root)
        before = snapshot(root)
        output, metadata = root/'annual', root/'metadata/manifest.json'
        result = annual.assemble(output, metadata, partitions)
        assert result['valid_records'] == 730
        assert result['complete_monthly_totals'] == 24
        assert result['complete_annual_totals'] == 2
        manifest = json.loads((output/'manifest.json').read_text())
        august = manifest['august_record_preservation']
        raw = (output/'daily_rainfall.csv').read_bytes()
        original = partitions[7]['csv_bytes'].split(b'\n', 1)[1]
        assert raw[august['offset_bytes']:august['offset_bytes']+august['bytes']] == original
        assert b'\r\n' in original
        assert annual.validate(output, partitions) == result
        assert len(manifest['monthly_equality_checks']) == 12
        assert all(c['statistics_equal'] and c['logical_equality'] for c in manifest['monthly_equality_checks'])
        assert all(c['observations'] == 365 for c in manifest['district_coverage_checks'])
        annual_before = snapshot(output)
        assert annual.validate(output, partitions) == result
        assert snapshot(output) == annual_before
        assert all(snapshot(root)[key] == value for key, value in before.items())
        complete = snapshot(root)
        with pytest.raises(ValueError, match='never overwrite'):
            annual.assemble(output, metadata, partitions)
        assert snapshot(root) == complete
        assert 'total_mm' not in manifest['validation']
        def assert_metadata_only(node):
            if isinstance(node, dict):
                assert not set(node) & {'mean_mm_per_day', 'scalar_mean_mm_per_day', 'total_mm', 'coordinates',
                                        'source_statistics', 'annual_statistics'}
                for value in node.values():
                    assert_metadata_only(value)
            elif isinstance(node, list):
                for value in node:
                    assert_metadata_only(value)
        assert_metadata_only(json.loads(metadata.read_text()))
        with (output/'annual_totals.csv').open(newline='') as stream:
            assert {r['total_mm'] for r in csv.DictReader(stream)} == {'912.5'}
        (output/'daily_rainfall.csv').write_bytes(raw.replace(b'Fixture', b'Changed', 1))
        with pytest.raises(ValueError, match='byte content/checksum'):
            annual.validate(output, partitions)


@pytest.mark.parametrize('fault', ['missing_month', 'duplicate_month', 'wrong_dates', 'duplicate_record', 'missing_record', 'wrong_source', 'wrong_grid'])
def test_invalid_partitions_fail_without_creating_outputs(monkeypatch, fault):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root)
        if fault == 'missing_month': partitions.pop()
        elif fault == 'duplicate_month': partitions[-1]['month'] = 11
        elif fault == 'wrong_dates': partitions[0]['manifest']['dates'].pop()
        elif fault == 'duplicate_record': partitions[0]['rows'].append(deepcopy(partitions[0]['rows'][0]))
        elif fault == 'missing_record': partitions[0]['rows'].pop()
        elif fault == 'wrong_source': partitions[0]['rows'][0]['source_image_id'] = 'incorrect'
        elif fault == 'wrong_grid': partitions[1]['manifest']['download_parameters'] = {'crs': 'incorrect'}
        with pytest.raises(ValueError):
            annual.assemble(root/'annual', root/'meta.json', partitions)
        assert not (root/'annual').exists()
        assert not (root/'meta.json').exists()


@pytest.mark.parametrize('state', ['no_valid_pixels', 'partial_pixel_coverage'])
def test_unavailable_or_partial_daily_observations_never_become_complete_totals(state):
    with TemporaryDirectory() as temporary:
        partitions = fixtures(Path(temporary))
        row = partitions[0]['rows'][0]
        row['status'] = state
        if state == 'no_valid_pixels':
            row['valid_pixel_count'] = 0
            row['mean_mm_per_day'] = row['min_mm_per_day'] = row['max_mm_per_day'] = None
            row['valid_fraction'] = 0.0
        else:
            row['expected_pixel_count'] = 2
            row['valid_fraction'] = .5
        result = annual.totals(partitions[0]['rows'], '2025-01-01', '2025-01-31')
        assert result[0]['total_mm'] is None
        assert result[0]['status'] == 'incomplete_observations'
        assert result[0]['complete_pixel_coverage_days'] == 30
        assert result[1]['total_mm'] == 77.5
        rows = [r for p in partitions for r in p['rows']]
        assert annual.totals(rows, '2025-01-01', '2025-12-31')[0]['total_mm'] is None


def test_missing_date_and_duplicate_date_are_not_filled_for_totals():
    with TemporaryDirectory() as temporary:
        rows = fixtures(Path(temporary))[0]['rows']
        with pytest.raises(ValueError, match='Missing date'):
            annual.totals(rows[:-1], '2025-01-01', '2025-01-31')
        with pytest.raises(ValueError, match='Duplicate'):
            annual.totals(rows+[rows[0]], '2025-01-01', '2025-01-31')


def test_absent_month_blocks_assembly_before_any_external_or_disk_write(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(annual, 'ROOT', root)
        with pytest.raises(ValueError, match='202501; annual assembly blocked'):
            annual.load_partitions()
        assert list(root.iterdir()) == []


def test_month_manifest_selects_recovered_raw_path_with_legacy_fallback(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(annual, 'ROOT', root)
        inputs = fixtures(root)
        def forbidden_raster_recalculation(*args):
            raise AssertionError('Annual assembly must not recalculate rainfall from rasters')
        monkeypatch.setattr(rain, 'validate_dataset', forbidden_raster_recalculation)
        for partition in inputs:
            month = partition['month']
            directory = root/f'data/working/karnataka_chirps_soi2025_2025{month:02d}_v1'
            directory.mkdir(parents=True)
            manifest = deepcopy(partition['manifest'])
            manifest['version'] = directory.name
            if month == 3:
                manifest['raw_directory'] = 'data/raw/chirps/karnataka_window_202503_recovered_v1'
            (directory/'manifest.json').write_text(json.dumps(manifest))
            shutil.copyfile(partition['directory']/'daily_rainfall.csv', directory/'daily_rainfall.csv')
        before = snapshot(root)
        loaded = annual.load_partitions()
        assert loaded[2]['raw_directory'] == root/'data/raw/chirps/karnataka_window_202503_recovered_v1'
        assert loaded[7]['raw_directory'] == root/'data/raw/chirps/karnataka_window_202508_verified_v1'
        assert snapshot(root) == before
        manifest_path = root/'data/working/karnataka_chirps_soi2025_202501_v1/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['raw_directory'] = '../../outside-fixture'
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match='outside local CHIRPS storage'):
            annual.load_partitions()


def save_fixture(partition, lexical_precision=False):
    """Modify controlled inputs only; never touch project research paths."""
    table = partition['directory']/'daily_rainfall.csv'
    with table.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rain.FIELDS)
        writer.writeheader()
        for row in partition['rows']:
            writer.writerow({**row, 'mean_mm_per_day': '2.5000000000000000'} if lexical_precision else row)
    partition['csv_bytes'] = table.read_bytes()
    manifest = partition['manifest']
    manifest['files'] = {'daily_rainfall.csv': rain.soi.fingerprint(table)}
    manifest['validation'] = rain.validate_rows(partition['rows'], manifest['geometry_provenance']['identities'], manifest['dates'])
    (partition['directory']/'manifest.json').write_text(json.dumps(manifest))


def test_sorted_union_preserves_every_original_record_precision_and_quoted_newline(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root)
        for p in partitions:
            for identity in p['manifest']['geometry_provenance']['identities']:
                identity['district_name_original'] = 'Fixture,\n'+identity['district_lgd_code_as_supplied_by_soi']
            names = {i['district_lgd_code_as_supplied_by_soi']: i['district_name_original']
                     for i in p['manifest']['geometry_provenance']['identities']}
            for row in p['rows']: row['district_name_original'] = names[row['source_district_lgd_code']]
            p['rows'].reverse()
            save_fixture(p, lexical_precision=True)
        before = snapshot(root)
        output = root/'annual'
        annual.assemble(output, root/'public.json', partitions)
        content = (output/'daily_rainfall.csv').read_bytes()
        assert content.count(b'2.5000000000000000') == 730
        _, records = annual.original_records(content)
        assert records[0][0]['date'] == '2025-01-01' and records[0][0]['source_district_lgd_code'] == '569'
        assert all('\n' in r['district_name_original'] for r, _ in records)
        result = annual.validate(output, partitions)
        assert result['duplicate_keys'] == result['missing_rainfall_values'] == 0
        manifest = json.loads((output/'manifest.json').read_text())
        assert not manifest['august_record_preservation']['source_order_preserved']
        assert manifest['august_record_preservation']['original_records_unchanged']
        assert all(snapshot(root)[name] == value for name, value in before.items())


@pytest.mark.parametrize('fault', ['source_version', 'method', 'geometry', 'schema', 'version'])
def test_mixed_provenance_is_rejected_before_any_output(monkeypatch, fault):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root);manifest = partitions[1]['manifest']
        if fault == 'source_version':manifest['source']['version'] = 'different controlled version'
        if fault == 'method':manifest['method'] = 'different controlled method'
        if fault == 'geometry':manifest['geometry_provenance']['source_id'] = 'different controlled geometry'
        if fault == 'schema':manifest['csv_fields'] = rain.FIELDS[:-1]
        if fault == 'version':manifest['version'] = 'ambiguous controlled version'
        (partitions[1]['directory']/'manifest.json').write_text(json.dumps(manifest))
        before = snapshot(root)
        with pytest.raises(ValueError):annual.assemble(root/'annual', root/'public.json', partitions)
        assert snapshot(root) == before


def test_monthly_checksum_is_checked_before_parsing_observations(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root)
        table = partitions[0]['directory']/'daily_rainfall.csv'
        table.write_bytes(table.read_bytes()+b'corrupt controlled fixture')
        before = snapshot(root)
        def forbidden(*args):raise AssertionError('Corrupted table must not be parsed')
        monkeypatch.setattr(rain, 'read_table', forbidden)
        with pytest.raises(ValueError, match='Monthly table checksum mismatch'):
            annual.assemble(root/'annual', root/'public.json', partitions)
        assert snapshot(root) == before


@pytest.mark.parametrize('state', ['no_valid_pixels', 'partial_pixel_coverage'])
def test_incomplete_month_cannot_be_published_as_annual(monkeypatch, state):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root);row = partitions[0]['rows'][0];row['status'] = state
        if state == 'no_valid_pixels':
            row['valid_pixel_count'] = 0;row['valid_fraction'] = 0.0
            row['mean_mm_per_day'] = row['min_mm_per_day'] = row['max_mm_per_day'] = None
        else:row['expected_pixel_count'] = 2;row['valid_fraction'] = .5
        save_fixture(partitions[0]);before = snapshot(root)
        with pytest.raises(ValueError, match='Incomplete monthly observations'):
            annual.assemble(root/'annual', root/'public.json', partitions)
        assert snapshot(root) == before


def test_failed_candidate_validation_does_not_publish_a_completed_version(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary);monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root);before = snapshot(root)
        def fail(*args):raise ValueError('Controlled candidate failure')
        monkeypatch.setattr(annual, 'validate', fail)
        with pytest.raises(ValueError, match='Controlled candidate failure'):
            annual.assemble(root/'annual', root/'public.json', partitions)
        assert snapshot(root) == before
        assert not list(root.glob('.annual-candidate-*'))


def test_validator_rejects_changed_values_even_with_updated_annual_checksum(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary);monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root);output = root/'annual'
        annual.assemble(output, root/'public.json', partitions)
        table = output/'daily_rainfall.csv';table.write_bytes(table.read_bytes().replace(b',2.5,', b',2.4,', 1))
        manifest = json.loads((output/'manifest.json').read_text())
        manifest['files']['daily_rainfall.csv'] = rain.soi.fingerprint(table)
        (output/'manifest.json').write_text(json.dumps(manifest));before = snapshot(root)
        with pytest.raises(ValueError, match='Annual byte content/checksum mismatch'):
            annual.validate(output, partitions)
        assert snapshot(root) == before


def test_validator_rejects_forged_monthly_statistics_without_writing(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary);monkeypatch.setattr(annual, 'ROOT', root)
        partitions = fixtures(root);output = root/'annual'
        annual.assemble(output, root/'public.json', partitions)
        manifest = json.loads((output/'manifest.json').read_text())
        manifest['monthly_equality_checks'][0]['annual_statistics']['mean_mm_per_day']['sum'] += 1
        (output/'manifest.json').write_text(json.dumps(manifest));before = snapshot(root)
        with pytest.raises(ValueError, match='Annual equality/coverage/assembly provenance mismatch'):
            annual.validate(output, partitions)
        assert snapshot(root) == before
