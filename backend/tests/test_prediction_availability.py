"""Offline Stage5 taxonomy, release-time, leakage, parity and immutable-review fixtures."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec=importlib.util.spec_from_file_location('method',Path(__file__).resolve().parents[2]/'scripts/review_prediction_availability.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def row(name):return next(x for x in c.matrix() if x['feature_id']==name)


def value():
    return {'documented_availability':True,'availability_evidence_url':'https://open-meteo.com/fixture',
        'availability_evidence_sha256':'a'*64,'available_at':'2026-10-01T06:00:00+00:00',
        'initialized_at':'2026-10-01T00:00:00+00:00','interval_start':'2026-10-01T00:00:00+00:00',
        'interval_end':'2026-10-01T01:00:00+00:00','vintage_available_at':'2024-01-01T00:00:00+00:00'}


def test_complete_taxonomy_canonical_keys_and_no_training():
    rows=c.matrix();assert len({x['feature_id'] for x in rows})==len(rows)
    assert all(c.validate_candidate(x)==x and not x['allowed_for_training'] for x in rows)
    assert c.readiness()['model_training_allowed'] is False
    assert c.readiness()['status']=='ml_training_not_ready'
    assert c.readiness()['LABEL_READINESS']=='NOT_READY'


@pytest.mark.parametrize('name',sorted(c.FORBIDDEN))
def test_leakage_and_invalid_evidence_cannot_be_predictors(name):
    r=row(name);before=deepcopy(r)
    assert r['safe_set']=='PROHIBITED' and not r['allowed_for_training'] and not r['allowed_for_deployment']
    with pytest.raises(ValueError):c.asof_input(r,value(),datetime(2026,10,2,tzinfo=timezone.utc))
    r['allowed_for_training']=True
    with pytest.raises(ValueError):c.validate_candidate(r)
    assert not before['allowed_for_training']


@pytest.mark.parametrize('name',['event_rainfall','gfd_extent','reported_ifi_event','post_event_sar','future_discharge_peak'])
def test_outcome_and_full_event_fields_explicit_leakage(name):
    assert row(name)['leakage_status']=='leakage_prohibited'


@pytest.mark.parametrize('status',['observed_zero_event','unlabeled_background','insufficient_observation','unknown'])
def test_unknown_or_zero_cannot_be_nonflood_labels(status):
    r=c.flood_target(status)
    assert not r['event_window_positive'] and r['daily_label'] is None and r['binary_training_target'] is None


def test_positive_extent_is_not_daily_label():
    r=c.flood_target('satellite_positive')
    assert r['event_window_positive'] and r['daily_label'] is None and r['binary_training_target'] is None


def test_gokak_and_quantitative_comparison_prohibitions_separate():
    assert row('gokak_discharge')['safe_set']=='PROHIBITED'
    assert row('cwc_model_skill')['safe_set']=='PROHIBITED'
    assert row('water_level_threshold')['safe_set']=='PROHIBITED'
    assert row('cwc_daily_discharge')['source_type']=='measured_cwc_nwdp'
    assert row('sadalga_glofas_history')['source_type']=='modelled_glofas_historical'


@pytest.mark.parametrize('name',['sadalga_glofas_history','huvinhedgi_glofas_history'])
def test_historical_glofas_not_forecast_or_deployable(name):
    r=row(name);assert r['feature_class']=='RETROSPECTIVE_ONLY'
    assert r['prediction_time_availability']=='retrospectively_available'
    r.update(feature_class='FORECAST',prediction_time_availability='forecast_available')
    with pytest.raises(ValueError):c.validate_candidate(r)


def test_chirps_final_latency_and_preliminary_are_distinct():
    r=row('chirps_final_daily')
    assert 'Third week of following month' in r['latency']
    assert 'preliminary2days after pentad, not Final' in r['latency']
    assert r['feature_class']=='RETROSPECTIVE_ONLY' and r['safe_set']=='RESEARCH_ONLY'
    r['allowed_for_deployment']=True
    with pytest.raises(ValueError):c.validate_candidate(r)
    assert row('antecedent_rainfall')['prediction_time_availability']=='retrospectively_available'


@pytest.mark.parametrize('field',['feature_class','prediction_time_availability','operational_source','latency','training_serving_parity'])
def test_missing_availability_fields_fail(field):
    r=row('om_forecast_precip');del r[field]
    with pytest.raises(ValueError):c.validate_candidate(r)


@pytest.mark.parametrize('name',['om_ifs_history','om_previous_runs','om_single_runs','cwc_daily_discharge','osm_drain_context'])
def test_unresolved_not_silently_usable(name):
    r=row(name)
    with pytest.raises(ValueError):c.asof_input(r,value(),datetime(2026,10,2,tzinfo=timezone.utc))
    r['allowed_for_deployment']=True
    with pytest.raises(ValueError):c.validate_candidate(r)


def test_research_deployment_only_static_with_operational_source():
    rows=[r for r in c.matrix() if r['allowed_for_deployment']]
    assert {x['feature_id'] for x in rows}=={'surface_elevation','surface_slope','landcover_2021'}
    assert all(x['operational_source'] and x['deployment_scope']=='dated_research_context_only' for x in rows)
    r=deepcopy(rows[0]);r['operational_source']=None
    with pytest.raises(ValueError):c.validate_candidate(r)


def test_soi_restrictions_no_operation_and_local_only():
    r=row('soi_district_geometry');assert r['source']=='soi_2025'
    assert r['training_serving_parity']=='NO_OPERATIONAL_EQUIVALENT' and 'local' in r['reason']
    assert not r['allowed_for_deployment']


def test_daily_forecast_temperature_not_elapsed_model_observation():
    assert row('om_forecast_temperature')['feature_class']=='FORECAST'
    assert row('om_current_temperature_humidity')['feature_class']=='MODELLED_PAST'


@pytest.mark.parametrize('field',['available_at','initialized_at'])
def test_future_delivery_or_initialization_leaks(field):
    v=value();v[field]='2026-10-03T00:00:00+00:00'
    with pytest.raises(ValueError):c.asof_input(row('om_forecast_precip'),v,datetime(2026,10,2,tzinfo=timezone.utc))


def test_forecast_future_valid_time_allowed_if_delivered_before_T():
    v=value();v['interval_start']='2026-10-03T00:00:00+00:00';v['interval_end']='2026-10-04T00:00:00+00:00'
    before=deepcopy(v);assert c.asof_input(row('om_forecast_precip'),v,datetime(2026,10,2,tzinfo=timezone.utc))
    assert v==before


def test_observation_after_T_not_permitted():
    v=value();v['interval_end']='2026-10-03T00:00:00+00:00'
    with pytest.raises(ValueError):c.asof_input(row('om_current_precip'),v,datetime(2026,10,2,tzinfo=timezone.utc))


def test_postevent_static_version_not_timeless():
    v=value();v['available_at']='2004-01-01T00:00:00+00:00'
    with pytest.raises(ValueError,match='vintage'):c.asof_input(row('surface_elevation'),v,datetime(2005,9,14,tzinfo=timezone.utc))


@pytest.mark.parametrize('field',['documented_availability','availability_evidence_url','availability_evidence_sha256'])
def test_evidence_backed_availability_required(field):
    v=value();v.pop(field)
    with pytest.raises(ValueError):c.asof_input(row('om_forecast_precip'),v,datetime(2026,10,2,tzinfo=timezone.utc))


def test_timezone_required_no_IST_default():
    v=value();v['available_at']='2026-10-01T06:00:00'
    with pytest.raises(ValueError):c.asof_input(row('om_forecast_precip'),v,datetime(2026,10,2,tzinfo=timezone.utc))


def test_empty_observed_past_category_not_invented():
    assert not any(r['feature_class']=='OBSERVED_PAST' for r in c.matrix())


def test_deterministic_manifest_and_readonly_immutable_review(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as temporary:
        root=Path(temporary);p=root/'fixture.json';p.write_bytes(b'{"fixture":true}\n')
        monkeypatch.setattr(c,'ROOT',root)
        monkeypatch.setattr(c,'input_records',lambda:[{'path':'fixture.json','sha256':c.sha(p),'bytes':p.stat().st_size}])
        monkeypatch.setattr(c,'record',lambda q:{'path':Path(q).name,'sha256':c.sha(q),'bytes':Path(q).stat().st_size})
        artifacts={'fixture.json':c.encode({'only_controlled_metadata':True,'models_trained':0})}
        summary={'models_trained':0};monkeypatch.setattr(c,'assemble',lambda:(artifacts,summary))
        out=root/'review';c.build(out)
        before={str(x):(x.read_bytes(),x.stat().st_mtime_ns) for x in [p,*out.iterdir()]}
        assert c.validate(out)==summary
        assert before=={str(x):(x.read_bytes(),x.stat().st_mtime_ns) for x in [p,*out.iterdir()]}
        with pytest.raises(ValueError,match='Immutable'):c.build(out)
        (out/'fixture.json').write_bytes(b'{}')
        with pytest.raises(ValueError,match='reproduction'):c.validate(out)


def test_canonical_encoding_and_no_network():
    assert c.encode({'a':1,'b':2})==c.encode({'b':2,'a':1})
    assert c.plain('<script>futuresecret</script><p>Published data</p>').strip()=='Published data'
