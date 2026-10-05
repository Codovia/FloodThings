"""Controlled administrative fixtures only; no live downloads or research writes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/reconcile_karnataka_lgd.py'
spec = importlib.util.spec_from_file_location('lgd_reconciliation', SCRIPT)
lgd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lgd)


def source(name='Fixture District', district='101'):
    return {'district_name_original': name, 'district_lgd_code_as_supplied_by_soi': district,
            'state_lgd_code_as_supplied_by_soi': '29', 'nic_exact_name': None, 'extra_original_attribute': 'retained'}


def current(name='Fixture District', district='101'):
    return {'state_code': '29', 'district_code': district, 'district_name': name, 'active': None}


def proof(kind='rename'):
    return {'state_code': '29', 'district_code': '101', 'source_name': 'Fixture Old',
            'current_name': 'Fixture New', 'kind': kind, 'source_url': 'https://data.gov.in/fixture-only',
            'evidence_date': '2026-01-01'}


def test_deterministic_code_name_mapping_preserves_every_soi_value():
    sources = [source('Fixture B', '102'), source()]; before = deepcopy(sources)
    currents = [current('Fixture B', '102'), current()]
    a = lgd.reconcile(sources, currents)
    assert a == lgd.reconcile(list(reversed(sources)), list(reversed(currents)))
    assert [r['soi_district_code'] for r in a] == ['101', '102']
    assert all(r['classification'] == 'exact_code_name_match' for r in a)
    assert sources == before


@pytest.mark.parametrize('kind,classification', [
    ('rename', 'code_match_documented_name_difference'),
    ('spelling_difference', 'code_match_documented_name_difference'),
    ('independently_verified_alias', 'independently_verified_alias'),
])
def test_documented_name_changes_require_same_code_and_exact_evidence(kind, classification):
    original = source('Fixture Old'); before = deepcopy(original)
    result = lgd.reconcile([original], [current('Fixture New')], [proof(kind)])[0]
    assert result['classification'] == classification
    assert result['current_name'] == 'Fixture New' and result['soi_name_original'] == 'Fixture Old'
    assert result['current_district_code'] == '101' and original == before
    wrong = proof(kind); wrong['district_code'] = '102'
    assert lgd.reconcile([original], [current('Fixture New')], [wrong])[0]['classification'] == 'unresolved'


def test_code_only_glyph_variants_and_nic_candidates_do_not_verify_current_names():
    record = source('Fi<xture Old'); record['nic_exact_name'] = 'Fixture Old'
    result = lgd.reconcile([record], [current('Fixture New')], [proof()])[0]
    assert not result['current_lgd_verified'] and result['current_name'] is None
    assert result['soi_name_original'] == 'Fi<xture Old'
    assert result['code_match_name_unresolved_candidate'] == 'Fixture New'
    fallback = lgd.reconcile([source()])[0]
    assert fallback['classification'] == 'unresolved' and fallback['source_identifier_status'] == lgd.LABEL


@pytest.mark.parametrize('records', [
    [current(), current('Conflicting Name')],
    [current(), current()],
    [current(), current('  fixture district ', '102')],
])
def test_duplicate_current_codes_names_and_rows_fail(records):
    with pytest.raises(ValueError, match='Duplicate/conflicting'):
        lgd.reconcile([source()], records)


def test_conflicting_codes_are_not_overridden_by_a_name_match():
    with pytest.raises(ValueError, match='Conflicting source/current district codes'):
        lgd.reconcile([source()], [current(district='102')])
    bad = current(); bad['state_code'] = '30'
    with pytest.raises(ValueError, match='state code'):
        lgd.reconcile([source()], [bad])


@pytest.mark.parametrize('bad', ['', '0101', '١٠١', '101.0', '-1', None])
def test_malformed_original_codes_are_rejected_without_coercion(bad):
    with pytest.raises(ValueError, match='Malformed source code'):
        lgd.reconcile([source(district=bad)])


def test_retained_official_csv_is_reproducible_read_only_and_count_is_not_forced():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'controlled.csv'
        body = b'State Code,State Name,District Code,District Name,Status\r\n29,Karnataka,101,Fixture District,A\r\n29,Karnataka,102,Fixture Former,I\r\n30,Other State,103,Fixture Elsewhere,A\r\n'
        path.write_bytes(body)
        columns = {'state_code': 'State Code', 'state_name': 'State Name', 'district_code': 'District Code',
                   'district_name': 'District Name', 'status': 'Status'}
        retrieval = {**lgd.fingerprint(path), 'http_status': 200, 'catalogue_url': lgd.CATALOGUE_URL,
                     'source_url': 'https://www.data.gov.in/controlled-fixture.csv', 'content_type': 'text/csv',
                     'retrieved_at': '2026-10-05T00:00:00+00:00', 'dataset_update_date': '2026-10-04'}
        before = path.read_bytes(), path.stat().st_mtime_ns, lgd.fingerprint(path)
        a = lgd.load_official_csv(path, retrieval, columns, active_values=['A'], inactive_values=['I'])
        assert a == lgd.load_official_csv(path, retrieval, columns, active_values=['A'], inactive_values=['I'])
        assert a['current_record_count'] == 1 and len(a['records']) == 2
        assert a['original_columns'] == ['State Code', 'State Name', 'District Code', 'District Name', 'Status']
        assert a['records'][0]['original_row']['District Name'] == 'Fixture District'
        assert (path.read_bytes(), path.stat().st_mtime_ns, lgd.fingerprint(path)) == before
        retrieval['http_status'] = 403
        with pytest.raises(ValueError, match='download failed'):
            lgd.load_official_csv(path, retrieval, columns)
        retrieval['http_status'] = 200; path.write_bytes(body + b'corrupt')
        with pytest.raises(ValueError, match='checksum mismatch'):
            lgd.load_official_csv(path, retrieval, columns)


def test_missing_ambiguous_columns_and_unknown_status_fail():
    with pytest.raises(ValueError, match='column mapping'):
        lgd.parse_current_csv(b'a,b\n1,2\n', {})
    columns = {'state_code': 's', 'district_code': 'd', 'district_name': 'n', 'status': 'a'}
    with pytest.raises(ValueError, match='Unknown source status'):
        lgd.parse_current_csv(b's,d,n,a\n29,101,Fixture,?\n', columns, ['A'], ['I'])
    with pytest.raises(ValueError, match='Missing current name'):
        lgd.parse_current_csv(b's,d,n\n29,101,\n', {k:v for k,v in columns.items() if k != 'status'})


def test_fallback_version_checks_retained_inputs_without_writes(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); monkeypatch.setattr(lgd, 'ROOT', root)
        original = root / 'source.json'; original.write_text(json.dumps({'district_records': [source()]}))
        output = root / lgd.VERSION; output.mkdir()
        (output / 'mapping.json').write_text(json.dumps(lgd.reconcile([source()])))
        (output / 'publication_policy.json').write_text(json.dumps({'repository_decisions': lgd.POLICY}))
        manifest = {'version': output.name, 'files': {n: lgd.fingerprint(output / n) for n in ['mapping.json', 'publication_policy.json']},
                    'inputs': {'source.json': lgd.fingerprint(original)}, 'soi_manifest_path': 'source.json',
                    'lgd': {'status': 'unavailable_http_403'}, 'coverage': {'reconciled_polygons': 0, 'unresolved_polygons': 1},
                    'stage_1_current_lgd_complete': False, 'later_flood_evidence_research_blocked_by_lgd_outage': False}
        (output / 'manifest.json').write_text(json.dumps(manifest))
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        assert lgd.validate_output(output) == manifest['coverage']
        assert {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before
        original.write_text('{}')
        with pytest.raises(ValueError, match='Retained source checksum'):
            lgd.validate_output(output)


@pytest.mark.parametrize('kind', ['original_soi_geometry', 'transformed_soi_geometry', 'rasterised_soi_geometry',
                                  'soi_derived_rainfall_statistics', 'unknown'])
def test_publication_policy_keeps_uncleared_artifacts_local(kind):
    with pytest.raises(ValueError, match='Publication withheld'):
        lgd.assert_publishable(kind)
    lgd.assert_publishable('project_authored_non_spatial_metadata_checksums_code')
