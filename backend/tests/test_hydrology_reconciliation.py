"""Offline Stage4C tests. All controlled observations confined to tmp_path."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec=importlib.util.spec_from_file_location('reconciliation',Path(__file__).resolve().parents[2]/'scripts/reconcile_karnataka_hydrology.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


@pytest.mark.parametrize('marker,value,status',[('*','4','computed'),('#','4','discarded_or_rating_curve_changed'),
    ('','4','unmarked_observed_or_estimated'),('','0.000','unmarked_observed_or_estimated'),('','-','missing'),('*',None,'missing')])
def test_literal_markers_missing_not_zero(marker,value,status):
    assert r.marker_status(marker,value)==status


def test_unknown_marker_not_inferred():
    with pytest.raises(ValueError,match='Unknown'):r.marker_status('!', '5')


@pytest.mark.parametrize('a,b,flag,expected',[('2','2','*','exact'),('12978.274','12978','','rounding_equivalent'),
    ('853.34','853.3','','rounding_equivalent'),('12.341','12.34','','rounding_equivalent'),('1.2344','1.234','','rounding_equivalent'),
    ('1800','1671','*','yearbook_computed_vs_nwdp'),('4','5','#','yearbook_discarded_or_rating_curve_changed'),
    ('4','5','','source_value_conflict'),(None,'5','*','source_missing'),('5',None,'','source_missing'),
    ('9.995','10','','unit_or_precision_issue'),('1000.4','1000','','unit_or_precision_issue')])
def test_evidence_categories_without_preference(a,b,flag,expected):
    assert r.classify_case(a,b,flag)==expected


def test_incompatible_units_and_numeric_validation():
    assert r.compare('5','5','meter','cumec')=='comparison_not_valid'
    for a in ['NaN','Infinity','-1']:
        with pytest.raises(ValueError):r.compare(a,'2')


def test_signed_relative_difference_and_zero_denominator():
    assert r.differences('2','4')==('-2','-0.5')
    assert r.differences('2','0')==('2',None)
    assert r.differences(None,'4')==(None,None)


@pytest.mark.parametrize('kwargs,expected',[
    ({'source_id':'id','expected_id':'id','direct_code_link':True},'identity_verified'),
    ({'source_id':'other','expected_id':'id','name':True},'identity_conflict'),
    ({'name':True,'agency':True,'river':True,'opening':True},'identity_strongly_supported'),
    ({'name':True,'agency':True,'river':True},'identity_ambiguous'),
    ({'name':True,'conflict':True},'identity_conflict')])
def test_identity_not_name_only_or_guessed_id(kwargs,expected):assert r.identity_status(**kwargs)==expected


def test_coordinate_distance_precision_and_no_averaging():
    first=[0,0];second=[0,1];before=deepcopy((first,second))
    assert r.distance_m(first,second)==pytest.approx(111195.0802335)
    assert r.distance_m(first,first)==0
    assert r.distance_m(first,second)==r.distance_m(second,first)
    assert (first,second)==before
    with pytest.raises(ValueError):r.distance_m([91,0],second)
    with pytest.raises(ValueError):r.distance_m([float('nan'),0],second)


@pytest.mark.parametrize('status,allowed',[('datum_compatible',True),('datum_probably_compatible_but_unverified',False),('datum_incompatible',False),('datum_unresolved',False)])
def test_threshold_guard(status,allowed):assert r.threshold_allowed(status)==allowed


def test_unknown_datum_vocabulary_fails():
    with pytest.raises(ValueError):r.threshold_allowed('probably fine')


@pytest.mark.parametrize('variable,identity,datum,cross,book,expected',[
    ('water_level','identity_strongly_supported','datum_unresolved',None,None,'retain_not_use_for_features'),
    ('water_level','identity_ambiguous','datum_unresolved',None,None,'unresolved'),
    ('discharge','identity_strongly_supported','datum_compatible','exact','unmarked_observed_or_estimated','eligible_with_quality_caveat'),
    ('discharge','identity_strongly_supported','datum_compatible','rounding_equivalent','computed','retain_not_use_for_features'),
    ('discharge','identity_strongly_supported','datum_compatible','source_value_conflict','unmarked_observed_or_estimated','retain_not_use_for_features'),
    ('discharge','identity_strongly_supported','datum_compatible','yearbook_discarded_or_rating_curve_changed','discarded_or_rating_curve_changed','retain_not_use_for_features')])
def test_observation_eligibility_conservative(variable,identity,datum,cross,book,expected):
    assert r.eligibility(variable,identity,datum,cross,book)==expected


def test_missing_hours_remain_missing_no_expected_grid_or_mean():
    observations=[{'canonical_cwc_station_id':'fixture','variable':'water_level','observation_time':'2019-08-01T08:30:00'},
        {'canonical_cwc_station_id':'fixture','variable':'water_level','observation_time':'2019-08-01T12:00:00'}]
    before=deepcopy(observations);out=r.hourly_coverage(observations,['fixture'],'2019-08-01','2019-08-02')
    assert [x['actual_count'] for x in out]==[2,0] and observations==before
    assert all(x['expected_hourly_count'] is None and x['coverage_fraction'] is None for x in out)
    assert out[1]['missing_day'] and not out[1]['values_interpolated']
    assert all('water_level_mean' not in x for x in out)


@pytest.mark.parametrize('artifact,kwargs,expected',[
    ('yearbook',{},'internal_research_only'),('portal_observations',{},'publication_terms_unresolved'),
    ('portal_observations',{'explicit_resource_rights':True},'publishable_with_source_acknowledgement'),
    ('portal_observations',{'explicit_resource_rights':True,'third_party_notice':True},'publication_terms_unresolved'),
    ('derived_detail',{},'publication_terms_unresolved'),('code',{},'publishable_with_source_acknowledgement')])
def test_publication_not_inferred_from_other_open_or_similar_data(artifact,kwargs,expected):
    assert r.publication_class(artifact,**kwargs)==expected


def fixture_book():
    text='Fixture OLD\n*:Computed Discharge\n'
    for day in range(1,32):
        groups=['100 2 *','101 3','102 4 #','103 5','104 6','105 7']
        if day==31:groups=[groups[i] for i in [1,2,4]]
        text+=str(day)+' '+' '.join(groups)+'\n'
    return text


def test_alternative_scalar_parser_correct_month_and_marker(monkeypatch):
    monkeypatch.setattr(r.b,'pdf_text',lambda *args:fixture_book())
    out,_=r.independent_book('controlled.pdf',1,'OLD')
    assert len(out)==27 and out['2019-07-31']==('101','3','') and out['2019-08-01']==('102','4','#')
    assert min(out)=='2019-07-25' and max(out)=='2019-08-20'
    with pytest.raises(ValueError,match='identity'):r.independent_book('controlled.pdf',1,'OTHER')


def test_immutable_manifest_deterministic_readonly_and_all_1697_values(monkeypatch,tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        root=Path(d);original=[{'original_value':str(Decimal(i)/10),'source_record':{'value':str(i)}} for i in range(1697)]
        before=deepcopy(original);body=r.b.table_bytes(original)
        monkeypatch.setattr(r,'ROOT',root);monkeypatch.setattr(r.b,'ROOT',root)
        code=root/'code.py';code.write_text('# controlled code')
        actual=r.b.file_record;monkeypatch.setattr(r.b,'file_record',lambda p:actual(code))
        monkeypatch.setattr(r,'inputs',lambda:[])
        monkeypatch.setattr(r,'assemble',lambda:({'observation_quality.csv':body},{'observations':1697}))
        output=root/'version';r.freeze(output)
        snapshot=lambda:{str(p):(p.read_bytes(),p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        frozen=snapshot();assert r.validate(output)=={'observations':1697} and snapshot()==frozen and original==before
        assert r.b.table_bytes(original)==body
        with pytest.raises(ValueError,match='Immutable'):r.freeze(output)
        assert snapshot()==frozen
        (output/'observation_quality.csv').write_bytes(body+b'corrupt')
        with pytest.raises(ValueError,match='reproduction'):r.validate(output)


def test_real_quality_derivation_preserves_all_1697_source_values():
    observations=[{'canonical_cwc_station_id':'fixture','variable':'water_level','observation_time':'2019-08-01T08:00:00',
        'original_value':f'{i:05d}.000','units':'meter','quality_flags':'{}','source_record':json.dumps({'original':str(i)})} for i in range(1697)]
    before=deepcopy(observations);out=r.quality_rows(observations,{}, {'fixture':'identity_strongly_supported'})
    assert len(out)==1697 and observations==before
    for original,derived in zip(observations,out):
        assert all(derived[k]==v for k,v in original.items())
        assert derived['preferred_for_analysis'] is None and derived['preference_basis'] is None
        assert derived['analysis_eligibility']=='retain_not_use_for_features'


def test_source_quality_flags_and_conflicts_retained_not_preferred():
    row={'canonical_cwc_station_id':'fixture','variable':'discharge','observation_time':'2019-08-01T08:00:00',
        'original_value':'2.000','quality_flags':'{"flag":"provisional"}'}
    cases={('fixture','2019-08-01'):{'classification':'source_value_conflict','yearbook_status':'unmarked_observed_or_estimated'}}
    out=r.quality_rows([row],cases,{'fixture':'identity_strongly_supported'})[0]
    assert out['original_value']=='2.000' and out['quality_flags']==row['quality_flags']
    assert out['analysis_eligibility']=='retain_not_use_for_features' and out['preferred_for_analysis'] is None
    assert out['source_quality_status']=='original_quality_flags_supplied_uninterpreted'
