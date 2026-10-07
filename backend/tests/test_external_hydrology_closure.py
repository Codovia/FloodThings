"""Offline Stage4F guards. Fixture products only in cleaned temporary directories."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec=importlib.util.spec_from_file_location('external',Path(__file__).resolve().parents[2]/'scripts/close_external_hydrology.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def source():
    return dict(url='https://cwc.gov.in/controlled-fixture',title='Controlled fixture',publisher='CWC',
                version='fixture',section='fixture section',retrieved_at='2026-10-07T00:00:00+00:00',
                classification='conclusive_reach_anchor',sha256='a'*64)


def candidates():
    return [dict(side='west',upstream_area_km2=2811.724288,source='official upstream fixture'),
            dict(side='east',upstream_area_km2=3907.502592,source='official upstream fixture')]


def attributes():
    return {name:dict(status='unresolved',reason='Exact field dictionary absent') for name in c.ATTRIBUTES}


def anchor():
    return {**source(), 'station_id':c.STATION,'side':'west','model_version':'5.0',
            'basis':'independent_official_gauge_to_model_junction_link'}


def test_both_candidates_and_unresolved_success():
    rows=candidates(); original=deepcopy(rows); d=c.reach_decision(rows)
    assert d['status']=='gokak_reach_externally_unresolved' and d['selected_cell'] is None
    assert rows==original
    assert c.closure_status(d['status'],c.temporal_decision(attributes())['status'],True)=='external_hydrology_closure_complete_with_unresolved_items'


@pytest.mark.parametrize('score',['magnitude_similarity','peak_timing','distance','catchment_match'])
def test_scoring_not_independent_reach_evidence(score):
    rows=candidates();rows[0][score]=1e12
    assert c.reach_decision(rows)['selected_cell'] is None
    a=anchor();a[score]=0
    with pytest.raises(ValueError):c.reach_decision(rows,a)


@pytest.mark.parametrize('bad',[[],[candidates()[0]],[candidates()[0]]*2])
def test_candidates_cannot_be_silently_dropped(bad):
    with pytest.raises(ValueError):c.reach_decision(bad)


def test_model_match_does_not_resolve_coordinate_conflict():
    d=c.reach_decision(candidates(),anchor())
    assert d['status']=='gokak_reach_resolved_west' and d['selected_cell']['upstream_area_km2']==2811.724288
    assert d['station_coordinate_status']=='coordinate_conflict_unresolved'
    assert not d['coordinate_conflict_resolved'] and not d['selection_uses_discharge']


@pytest.mark.parametrize('field,value',[('basis','nearest_cell'),('model_version','4.0'),('station_id','OTHER'),
                                      ('side','elsewhere'),('classification','broad_spatial_context')])
def test_invalid_anchor_cannot_promote(field,value):
    a=anchor();a[field]=value
    with pytest.raises(ValueError):c.reach_decision(candidates(),a)


@pytest.mark.parametrize('field',['url','title','publisher','version','section','retrieved_at','sha256','classification'])
def test_provenance_required(field):
    s=source();s[field]=''
    with pytest.raises((ValueError,AttributeError)):c.provenance(s)


def test_secondary_url_rejected():
    s=source();s['url']='https://example.org/map'
    with pytest.raises(ValueError):c.provenance(s)


@pytest.mark.parametrize('name',c.ATTRIBUTES)
def test_exact_field_evidence_required_for_every_resolution(name):
    a=attributes();a[name].update(status='resolved',definition='claimed meaning',source=source())
    with pytest.raises(ValueError):c.temporal_decision(a)
    a[name].update(resource_id=c.RESOURCE,exact_field_documented=True)
    d=c.temporal_decision(a)
    assert d['status']=='nwdp_temporal_semantics_partially_resolved'
    assert not d['pointwise_comparison_allowed'] and d['aligned_quantitative_pairs']==0


@pytest.mark.parametrize('label',['daily','manual','08:00','IST display clock','Data Acquisition Time','period-end'])
def test_labels_do_not_define_statistic_timezone_or_window(label):
    a=attributes();a['value_semantics']['reason']=label
    d=c.temporal_decision(a)
    assert all(v['status']=='unresolved' for v in d['attributes'].values())
    assert d['status']=='nwdp_temporal_semantics_externally_unresolved'
    assert not d['pointwise_comparison_allowed']


def test_script_clock_not_field_metadata():
    text='<script>// IST offset\n const clock = 5.5;</script><p>Data Acquisition Time</p>'
    assert c.visible(text)=='Data Acquisition Time'


def test_invalid_temporal_and_missing_attribute():
    a=attributes();a['timezone']['status']='partially_resolved'
    with pytest.raises(ValueError):c.temporal_decision(a)
    a=attributes();del a['aggregation_window']
    with pytest.raises(ValueError):c.temporal_decision(a)


def test_even_resolved_dictionary_does_not_create_pairs_without_alignment():
    a=attributes()
    for x in a.values():x.update(status='resolved',resource_id=c.RESOURCE,exact_field_documented=True,
                               source=source(),definition='Controlled exact-field fixture')
    d=c.temporal_decision(a)
    assert d['status']=='nwdp_temporal_semantics_resolved'
    assert not d['pointwise_comparison_allowed'] and d['aligned_quantitative_pairs']==0


def test_search_must_close_before_success():
    with pytest.raises(ValueError):c.closure_status('gokak_reach_externally_unresolved','nwdp_temporal_semantics_externally_unresolved',False)


@pytest.mark.parametrize('g,t,status',[
    ('gokak_reach_resolved_west','nwdp_temporal_semantics_resolved','external_hydrology_closure_complete'),
    ('gokak_reach_resolved_east','nwdp_temporal_semantics_externally_unresolved','external_hydrology_closure_partial'),
    ('gokak_reach_externally_unresolved','nwdp_temporal_semantics_resolved','external_hydrology_closure_partial')])
def test_closure_classes(g,t,status):
    assert c.closure_status(g,t,True)==status


@pytest.mark.parametrize('use',['gokak_canonical_discharge','time_aligned_measured_modelled_pairs',
    'model_skill_metrics_or_calibration_claims','water_level_threshold_features','within_station_water_level_change',
    'missing_observation_as_flood_negative','modelled_replacement_of_measured_values','instant_historical_prediction_availability'])
def test_usage_matrix_blocks_unsafe_features(use):
    row=next(x for x in c.usage_matrix() if x['use']==use)
    assert row['permission']=='not_allowed' and row['conditions']


def test_supported_model_context_separate_from_measurements():
    rows=c.usage_matrix()
    for use in ['sadalga_modelled_discharge','huvinhedgi_modelled_discharge']:
        r=next(x for x in rows if x['use']==use)
        assert r['permission']=='allowed_with_conditions' and r['source_type']=='modelled_glofas'
    assert len({x['use'] for x in rows})==len(rows)
    assert {c.check_source_type(x) for x in c.SOURCE_TYPES}==c.SOURCE_TYPES
    with pytest.raises(ValueError):c.check_source_type('observed_glofas')


def fixture_assembly():
    return {'summary.json':c.encode({'status':'controlled_fixture','features_created':0,'labels_created':0})}, {'status':'controlled_fixture','features_created':0,'labels_created':0}


def test_immutable_deterministic_reproduction_and_readonly_validation(tmp_path,monkeypatch):
    # No fixture observation ever reaches research directories.
    with TemporaryDirectory(dir=tmp_path) as tmp:
        root=Path(tmp); inp=root/'input.json';inp.write_bytes(b'{"fixture":true}\n')
        monkeypatch.setattr(c,'ROOT',root)
        monkeypatch.setattr(c,'assemble',fixture_assembly)
        monkeypatch.setattr(c,'input_records',lambda:[c.record(inp)])
        monkeypatch.setattr(c,'record',lambda p:{'path':'fixture' if Path(p)!=inp else 'input.json','bytes':Path(p).stat().st_size,'sha256':c.sha(p)})
        out=root/'output';c.build(out)
        paths=[inp,*out.iterdir()]
        before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        assert c.validate(out)['features_created']==0
        assert before=={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        with pytest.raises(ValueError,match='Immutable'):c.build(out)
        (out/'summary.json').write_bytes(b'{}')
        with pytest.raises(ValueError,match='reproduction'):c.validate(out)


def test_manifest_encoding_deterministic():
    assert c.encode({'b':2,'a':1})==c.encode({'a':1,'b':2})
    assert hashlib.sha256(c.encode(attributes())).hexdigest()==hashlib.sha256(c.encode(attributes())).hexdigest()
