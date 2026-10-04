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
                    'source': {'collection': rain.SOURCE, 'version': 'fixture only'},
                    'geometry_provenance': {'identities': identities, 'current_lgd_reconciled': False},
                    'method': 'fixture daily means', 'download_parameters': {}, 'csv_fields': rain.FIELDS,
                    'raw_retrieval_log': {'sha256': 'fixture only', 'bytes': 0},
                    'images': [{'source_image_id': rain.SOURCE+'/'+day.replace('-', ''),
                                'download': {'retrieved_at': rows[0]['retrieved_at']}} for day in days],
                    'temporal_semantics': 'fixture historical estimates', 'geometry_temporal_limit': '2025 geometry only',
                    'identity_limit': 'pending current LGD', 'reuse': {'district_aggregate_publication': 'local only'}}
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
        assert all(snapshot(root)[key] == value for key, value in before.items())
        complete = snapshot(root)
        with pytest.raises(ValueError, match='never overwrite'):
            annual.assemble(output, metadata, partitions)
        assert snapshot(root) == complete
        assert 'total_mm' not in manifest['validation']
        def assert_metadata_only(node):
            if isinstance(node, dict):
                assert not set(node) & {'mean_mm_per_day', 'scalar_mean_mm_per_day', 'total_mm', 'coordinates'}
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
        calls = []
        monkeypatch.setattr(rain, 'validate_dataset', lambda directory, raw, boundaries: calls.append(raw))
        for partition in inputs:
            month = partition['month']
            directory = root/f'data/working/karnataka_chirps_soi2025_2025{month:02d}_v1'
            directory.mkdir(parents=True)
            manifest = deepcopy(partition['manifest'])
            manifest['validation'] = {'records': len(partition['rows'])}
            if month == 3:
                manifest['raw_directory'] = 'data/raw/chirps/karnataka_window_202503_recovered_v1'
            (directory/'manifest.json').write_text(json.dumps(manifest))
            shutil.copyfile(partition['directory']/'daily_rainfall.csv', directory/'daily_rainfall.csv')
        before = snapshot(root)
        loaded = annual.load_partitions()
        assert calls[2] == root/'data/raw/chirps/karnataka_window_202503_recovered_v1'
        assert calls[7] == root/'data/raw/chirps/karnataka_window_202508_verified_v1'
        assert loaded[2]['raw_directory'] == calls[2]
        assert snapshot(root) == before
        manifest_path = root/'data/working/karnataka_chirps_soi2025_202501_v1/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['raw_directory'] = '../../outside-fixture'
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match='outside local CHIRPS storage'):
            annual.load_partitions()
