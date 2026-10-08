"""Stage 5A contracts: controlled fixtures only; no network, labels or research writes."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec = importlib.util.spec_from_file_location('target_review', Path(__file__).resolve().parents[2] / 'scripts/review_target_archives.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def value():
    return {'initialized_at': '2021-07-23T00:00:00+00:00', 'available_at': '2021-07-25T00:00:00+00:00',
            'valid_start': '2021-07-26T00:00:00+00:00', 'valid_end': '2021-07-27T00:00:00+00:00',
            'availability_documented': True, 'availability_source_url': 'https://www.ecmwf.int/fixture',
            'availability_source_sha256': 'a' * 64}


def source(sid):
    return next(x for x in c.forecast_sources() if x['source'] == sid)


def smoke():
    body = {'utc_offset_seconds': 0, 'hourly_units': {'precipitation': 'mm', 'temperature_2m': '°C'},
            'hourly': {'time': [f'2026-10-01T{h:02d}:00' for h in range(24)],
                       'precipitation': [None] + [1.] * 23, 'temperature_2m': [20.] * 24}}
    receipt = {'status': 'retrieved', 'http_status': '200', 'parameters': {'models': 'ecmwf_ifs',
               'forecast_days': '1', 'timezone': 'UTC', 'run': '2026-10-01T00:00'},
               'url': 'https://single-runs-api.open-meteo.com/v1/forecast', 'retrieved_at': '2026-10-08T04:06:00+00:00',
               'sha256': 'a' * 64, 'bytes': 1000}
    return body, receipt


def test_risk_cutoffs_and_alert_decision_not_invented():
    mapping = c.risk_mapping()
    assert mapping['status'] == 'user_facing_risk_class_mapping_not_defined'
    assert mapping['probability_cutoffs'] is None and mapping['severity_cutoffs'] is None
    assert mapping['alert_mapping'] is None


def test_target_geography_and_temporal_semantics_every_candidate():
    rows = c.targets()
    assert len({r['target_id'] for r in rows}) == 9
    assert all(c.validate_target(r) == r and r['geographic_unit'] and r['temporal_unit'] for r in rows)
    assert not any(r['primary_adopted'] for r in rows)


def test_measurement_supported_does_not_adopt_deployable_target():
    row = c.targets()[0]
    assert row['status'] == 'SUPPORTED' and row['sample_support']['positive_scopes'] == 4
    assert row['forecast_horizon'] is None and row['negative_definition'] is None
    row['primary_adopted'] = True
    with pytest.raises(ValueError, match='independent'): c.validate_target(row)


@pytest.mark.parametrize('field', ['geographic_unit', 'temporal_unit'])
def test_target_missing_spacetime_rejected(field):
    row = c.targets()[0]; row[field] = None
    with pytest.raises(ValueError): c.validate_target(row)


@pytest.mark.parametrize('kind', ['no_ifi_record', 'no_gfd_record', 'random_day', 'unmentioned_district', 'missing_scene', 'observed_zero_event'])
def test_invalid_negative_evidence_rejected(kind):
    with pytest.raises(ValueError): c.negative_review({'type': kind})


@pytest.mark.parametrize('kind', ['unknown', 'unobserved', 'insufficient_observation', 'unlabeled', 'monitored_noninundation'])
def test_unknown_or_protocol_candidate_never_creates_negative(kind):
    result = c.negative_review({'type': kind})
    assert result['binary_label'] is None and not result['negative_created']


def test_complete_proposed_negative_protocol_still_needs_separate_validation():
    evidence = {k: True for k in ['precise_spatial_unit', 'explicit_observation_interval', 'valid_sensor_masks',
               'detection_sensitivity_audited', 'adequate_temporal_coverage', 'independent_reference', 'selection_protocol', 'prediction_time_parity']}
    result = c.negative_review(evidence)
    assert result['protocol_prerequisites_met'] and result['binary_label'] is None


@pytest.mark.parametrize('kind', ['REFORECAST_HINDCAST', 'REANALYSIS_RETROSPECTIVE', 'HISTORICAL_CONSOLIDATED', 'STITCHED_RETROSPECTIVE'])
def test_retrospective_products_never_masquerade_as_issued(kind):
    with pytest.raises(ValueError): c.asof_forecast(kind, value(), datetime(2021, 7, 25, tzinfo=timezone.utc))


@pytest.mark.parametrize('feature', sorted(c.FORBIDDEN_INPUTS))
def test_event_outcomes_future_observations_and_gokak_not_inputs(feature):
    with pytest.raises(ValueError): c.asof_forecast('archived_operational_forecast', value(), datetime(2021, 7, 25, tzinfo=timezone.utc), feature)


@pytest.mark.parametrize('field', ['initialized_at', 'available_at'])
def test_future_initialization_or_delivery_rejected(field):
    v = value(); v[field] = '2021-07-26T00:00:00+00:00'
    with pytest.raises(ValueError): c.asof_forecast('archived_operational_forecast', v, datetime(2021, 7, 25, tzinfo=timezone.utc))


@pytest.mark.parametrize('field', ['initialized_at', 'available_at', 'valid_start', 'valid_end'])
def test_timezone_cannot_default(field):
    v = value(); v[field] = v[field].replace('+00:00', '')
    with pytest.raises(ValueError, match='timezone'): c.asof_forecast('archived_operational_forecast', v, datetime(2021, 7, 25, tzinfo=timezone.utc))


@pytest.mark.parametrize('field', ['availability_documented', 'availability_source_url', 'availability_source_sha256'])
def test_explicit_availability_evidence_required(field):
    v = value(); v.pop(field)
    with pytest.raises(ValueError): c.asof_forecast('archived_operational_forecast', v, datetime(2021, 7, 25, tzinfo=timezone.utc))


def test_forecast_future_valid_period_allowed_with_documented_past_delivery():
    v = value(); before = deepcopy(v)
    assert c.asof_forecast('archived_operational_forecast', v, datetime(2021, 7, 25, tzinfo=timezone.utc))
    assert v == before


def test_application_clock_and_forecast_day_boundaries_remain_unset():
    issue = c.issuance_definition()
    assert issue['schedule_status'] == 'exact_issuance_schedule_unspecified'
    assert issue['clock_times'] is None and issue['forecast_day_boundaries'] is None
    assert issue['forecast_days'] == 7 and not issue['production_schedule_adopted']


def test_hindcast_archive_and_operational_archive_remain_distinct():
    assert source('om_single_early')['historical_product'] == 'REFORECAST_HINDCAST'
    assert source('om_single_early')['status'] == 'NOT_ISSUANCE_PRESERVING'
    assert source('om_single_recent')['historical_product'] == 'OPERATIONAL_FORECAST_ARCHIVE'
    assert source('ecmwf_tigge')['issuance_preserved']
    assert not source('glofas_reforecast')['issuance_preserved']
    assert not source('glofas_history')['issuance_preserved']


def test_tigge_public_delay_not_issuance_at_initialization():
    assert '48-hour' in source('ecmwf_tigge')['caveat']
    assert 'kg/m2' in source('ecmwf_tigge')['units']
    assert not source('ecmwf_tigge')['actual_selected_event_runs_retrieved']


def test_every_source_has_semantics_parity_terms_and_geographic_coverage():
    rows = c.forecast_sources()
    assert all(r['status'] in c.ARCHIVE_STATUSES and r['licence'] and r['caveat'] and r['geographic_coverage'] for r in rows)
    assert not any(r['approved_training_source'] for r in rows)


def test_glofas_history_is_not_forecast_and_no_measured_conflation():
    assert source('glofas_history')['historical_product'] == 'HISTORICAL_CONSOLIDATED'
    assert 'modelled' in source('glofas_reforecast')['units']
    assert 'Gokak excluded' in source('glofas_forecast')['caveat']


def test_requirements_original_statements_and_roles_preserved():
    text = '# Intent\nSeven-day flood risk by district every six hours.\n\n# Old experiment\nProxy High score is unvalidated.\n'
    rows = c.requirements_from_text(text, 'fixture.md', 'obsolete fixture')
    assert len(rows) == 2 and rows[0]['line_start'] == 1
    assert rows[0]['original_requirement'] == '# Intent\nSeven-day flood risk by district every six hours.\n'
    assert rows[0]['source_role'] == 'obsolete fixture'
    assert rows[0]['risk_class_definition'] is None


def test_smoke_missing_data_not_filled_and_run_echo_not_manufactured():
    body, receipt = smoke(); before = deepcopy(body)
    result = c.inspect_smoke(body, receipt)
    assert result['counts']['precipitation'] == {'finite': 23, 'missing': 1}
    assert result['counts']['temperature_2m'] == {'finite': 24, 'missing': 0}
    assert not result['server_run_version_echo'] and not result['original_delivery_clock_verified']
    assert body == before


@pytest.mark.parametrize('error', ['date', 'unit', 'negative', 'nonfinite', 'length'])
def test_bad_smoke_contract_rejected(error):
    body, receipt = smoke()
    if error == 'date': body['hourly']['time'][0] = '2026-10-02T00:00'
    if error == 'unit': body['hourly_units']['precipitation'] = 'mm/day'
    if error == 'negative': body['hourly']['precipitation'][1] = -1
    if error == 'nonfinite': body['hourly']['temperature_2m'][1] = float('nan')
    if error == 'length': body['hourly']['precipitation'].pop()
    with pytest.raises(ValueError): c.inspect_smoke(body, receipt)


def test_readiness_remains_no_training_no_primary_no_risk_mapping():
    result = c.readiness()
    assert result['NEGATIVE_LABEL_READINESS'] == 'NOT_READY' and result['SAMPLE_SIZE'] == 'NOT_READY'
    assert not result['model_training_allowed'] and result['primary_horizon'] is None
    assert result['primary_target_status'] == 'primary_target_not_yet_adopted'
    assert not c.next_plan()['training_authorized']


def test_next_plan_gates_no_viewport_as_flood_shape_or_automatic_hydrology():
    plan = c.next_plan()
    assert 'viewport is not flood geometry' in plan['label_gate']
    assert 'Omit' in plan['hydrology'] and 'exclude Gokak' in plan['hydrology']
    assert plan['candidate_initializations_not_retrieved'] and not plan['production_target_or_clock_adopted']


def test_immutable_build_readonly_validation_and_exact_hash_mtime(tmp_path, monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as directory:
        root = Path(directory); source_file = root / 'fixture.json'; source_file.write_bytes(b'{"fixture":true}\n')
        monkeypatch.setattr(c, 'ROOT', root)
        monkeypatch.setattr(c, 'assemble', lambda: ({'decision.json': c.encode({'no_training': True})}, {'status': 'fixture'}))
        monkeypatch.setattr(c, 'input_records', lambda: [c.record(source_file)])
        monkeypatch.setattr(c, 'record', lambda p: {'path': Path(p).name, 'sha256': c.sha(p), 'bytes': Path(p).stat().st_size})
        output = root / 'review'; c.build(output)
        paths = [source_file, *output.iterdir()]
        snapshot = {p: (p.read_bytes(), c.sha(p), p.stat().st_mtime_ns) for p in paths}
        assert c.validate(output) == {'status': 'fixture'}
        assert snapshot == {p: (p.read_bytes(), c.sha(p), p.stat().st_mtime_ns) for p in paths}
        with pytest.raises(ValueError, match='Immutable'): c.build(output)
        (output / 'decision.json').write_bytes(b'{}')
        with pytest.raises(ValueError, match='reproduction'): c.validate(output)


def test_deterministic_encoding_and_no_serialized_nan():
    assert c.encode({'b': 1, 'a': 2}) == c.encode({'a': 2, 'b': 1})
    with pytest.raises(ValueError): c.encode({'x': float('nan')})


def test_missing_official_source_provenance_rejected(tmp_path, monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as directory:
        raw = Path(directory); monkeypatch.setattr(c, 'RAW', raw)
        (raw / 'review_findings.json').write_bytes(c.encode([{'id': 'fixture'}]))
        (raw / 'fixture.html.json').write_bytes(c.encode({'url': 'https://official.invalid/fixture'}))
        with pytest.raises(ValueError, match='Incomplete reviewed source'): c.source_register()


def test_changed_original_source_hash_rejected(tmp_path, monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as directory:
        raw = Path(directory); monkeypatch.setattr(c, 'RAW', raw)
        finding = {'id': 'fixture', **{key: 'fixture' for key in ['title', 'publisher', 'version', 'section', 'finding', 'confidence']}}
        (raw / 'review_findings.json').write_bytes(c.encode([finding])); (raw / 'fixture.html').write_bytes(b'original')
        receipt = {'url': 'https://official.invalid/fixture', 'status': 'retrieved', 'http_status': '200', 'sha256': 'a' * 64, 'bytes': 8}
        (raw / 'fixture.html.json').write_bytes(c.encode(receipt))
        with pytest.raises(ValueError, match='Source bytes changed'): c.source_register()


def test_assembled_outputs_are_review_metadata_not_training_artifacts(tmp_path, monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as directory:
        raw = Path(directory); monkeypatch.setattr(c, 'RAW', raw)
        body, receipt = smoke(); data = c.encode(body)
        (raw / 'om_pinned_smoke.json').write_bytes(data)
        receipt.update(sha256=c.sha(raw / 'om_pinned_smoke.json'), bytes=len(data))
        (raw / 'om_pinned_smoke.json.receipt.json').write_bytes(c.encode(receipt))
        monkeypatch.setattr(c, 'prior_gate', lambda: {'status': 'ml_training_not_ready'})
        monkeypatch.setattr(c, 'source_register', lambda: [{'id': 'controlled_fixture'}])
        monkeypatch.setattr(c, 'requirements', lambda: [])
        monkeypatch.setattr(c, 'positive_overlap', lambda: [{'tigge_catalogue_period_overlap': True}])
        artifacts, summary = c.assemble()
        assert len(artifacts) == 16 and all(name.endswith('.json') for name in artifacts)
        assert not any(name.endswith(('.csv', '.pkl', '.joblib', '.onnx')) for name in artifacts)
        assert summary['training_records_created'] == 0 and not summary['model_training_allowed']
        assert summary['quantitative_hydrology_comparisons'] == 0
