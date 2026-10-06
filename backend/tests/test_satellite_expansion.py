"""Controlled offline second-batch fixtures; all output is cleaned temporary data."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

spec=importlib.util.spec_from_file_location('satellite_expansion',Path(__file__).resolve().parents[2]/'scripts/expand_karnataka_satellite.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def boundary(name='Fixture District',identity='fixture-shape'):
    return {'shapeName':name,'shapeID':identity,'shapeGroup':'IND','shapeType':'ADM2'}


def boundaries():
    return {'source':s.source.BOUNDARY,'window':s.source.WINDOW,'response':{'count':1,'features':[boundary()]}}


def candidate(eid=6001,ifi='fixture-ifi',year=2008):
    a,b=f'{year}-07-01',f'{year}-07-03'
    index=f"DFO_{eid}_From_{a.replace('-','')}_to_{b.replace('-','')}"
    return {'gfd_id':eid,'ifi_project_event_id':ifi,'ifi_source_event_id':ifi,'ifi_state_original':'Karnataka',
        'ifi_district_tokens_original':'Fixture District','ifi_start':a,'ifi_end_inclusive':b,
        'gfd_start':a,'gfd_end_inclusive':b,'image_id':s.source.SOURCE+'/'+index,
        'candidate_status':'strong_temporal_candidate','temporal_strength':'strong_temporal_candidate',
        'temporal_overlap':s.source.overlap(a,b,a,b),'association_status':'provisional_temporal_only',
        'original_properties':{'id':eid,'system:index':index,'dfo_country':'India','cc':'IND'}}


def geo(c):
    return {'gfd_id':c['gfd_id'],'shapeID':'fixture-shape','shapeName':'Fixture District','feature_count':1,
        'region_area_km2':100,'state_fraction':1,'footprint_intersection_km2':100,
        'bounds':[[[0,0],[10000,0],[10000,10000],[0,10000]]],'properties':c['original_properties']}


def geography(table):
    return {'state_source':s.STATE_SOURCE,'state_feature_count':1,
            'state_identity':{'shapeID':s.STATE_ID,'shapeName':s.STATE_NAME,'shapeGroup':'IND'},
            'rows':[geo(c) for c in table]}


def test_deterministic_selection_complete_rank_trace_and_source_values_preserved():
    table=[candidate(6002,'b',2009),candidate(6001,'a',2008)];before=deepcopy(table)
    result=s.selection(table,boundaries(),geography(table),[])
    assert result==s.selection(table,boundaries(),geography(table),[])
    assert [c['gfd_id'] for c in result['selected']]==[6001,6002]
    assert len(result['eligible_ranking_pool'])==2 and [len(r) for r in result['ranking_rounds']]==[2,1]
    assert table==before and 'No raster outcomes' in result['rule']
    assert [c['gfd_id'] for c in s.selection(table[::-1],boundaries(),geography(table),[])['selected']]==[6001,6002]


@pytest.mark.parametrize('eid',[3160,2690,4382,3652,4508,2728,3551])
def test_previously_reviewed_ids_cannot_be_selected(eid):
    pool,excluded=s.eligible([candidate(eid)],boundaries())
    assert pool==[] and excluded[0]['reason']=='previously_reviewed_gfd'


def test_ambiguous_candidates_excluded_even_if_one_would_be_preferred():
    a,b=candidate(6001),candidate(6002)
    a['candidate_status']=b['candidate_status']='ambiguous'
    pool,excluded=s.eligible([a,b],boundaries())
    assert not pool and all(r['reason']=='ambiguous' for r in excluded)
    a['candidate_status']=b['candidate_status']='strong_temporal_candidate'
    assert not s.eligible([a,b],boundaries())[0]  # Independent multiplicity check.


@pytest.mark.parametrize('field,value,reason',[
 ('ifi_state_original','Karnataka, Kerala','not_karnataka_only'),
 ('candidate_status','possible_temporal_candidate','not_strong_temporal'),
 ('ifi_district_tokens_original','Unverified alias','no_unique_exact_public_district_token'),
 ('ifi_start',None,'invalid_ifi_window')])
def test_unavailable_or_weak_associations_not_promoted(field,value,reason):
    c=candidate();c[field]=value
    assert s.eligible([c],boundaries())[1][0]['reason']==reason


def test_dfo_country_and_exact_public_name_are_required():
    c=candidate();c['original_properties']['dfo_country']='Bangladesh'
    assert s.eligible([c],boundaries())[1][0]['reason']=='primary_dfo_india_not_verified'
    b=boundaries();b['response']['features'].append(boundary(identity='duplicate'));b['response']['count']=2
    assert not s.eligible([candidate()],b)[0]


def test_actual_state_source_id_and_original_damaged_name_are_retained():
    c=candidate();g=geography([c])
    assert s.selection([c],boundaries(),g,[])['selected']
    assert g['state_identity']['shapeName']=='Karn?taka'
    for field,value in [('shapeID','guessed-id'),('shapeName','Karnataka')]:
        changed=deepcopy(g);changed['state_identity'][field]=value
        with pytest.raises(ValueError,match='state identity'):s.selection([c],boundaries(),changed,[])


def test_retained_original_code_checksum_validates_without_rewriting_manifest(monkeypatch):
    with TemporaryDirectory() as temporary:
        root=Path(temporary);monkeypatch.setattr(s,'ROOT',root)
        code=root/'source.py';code.write_text('# fixture initial source\n')
        expected=s.source.fingerprint(code);recorded={str(code):expected};before=deepcopy(recorded)
        s.verify_execution_code(recorded)
        snapshot=root/'data/recovery/stage3b2_execution_sources'/f"{expected['sha256']}.py"
        snapshot.parent.mkdir(parents=True);snapshot.write_bytes(code.read_bytes())
        code.write_text('# fixture changed source\n');saved=(snapshot.read_bytes(),snapshot.stat().st_mtime_ns)
        s.verify_execution_code(recorded)
        assert recorded==before and saved==(snapshot.read_bytes(),snapshot.stat().st_mtime_ns)
        snapshot.write_text('# fixture corrupted source\n')
        with pytest.raises(ValueError,match='extraction code'):s.verify_execution_code(recorded)


@pytest.mark.parametrize('field,value',[
 ('state_fraction',.5),('footprint_intersection_km2',0),('feature_count',2),('region_area_km2',25000)])
def test_geographic_metadata_rejects_mismatch_before_expensive_reduction(field,value):
    c=candidate();g=geography([c]);g['rows'][0][field]=value
    result=s.selection([c],boundaries(),g,[])
    assert not result['selected'] and len(result['exclusions'])==1


def test_fixed_multi_band_planner_and_duplicate_free_partitions_used():
    c=candidate();p=s.validate_geography(geo(c),{**c,'review_region':boundary()})
    assert p['band_count']==10 and p['safety_factor']==1.25 and p['maxPixels']==300000
    assert p['maximum_safe_workload']<=88200
    for col,row in [(0,-40),(20,-20),(39,-1)]:
        assert sum(s.source.owns(w['window'],col,row) for w in p['partitions'])==1
    changed=deepcopy(p);changed['partitions'][0]['safe_workload_bound']=300001
    with pytest.raises(ValueError):s.grid.guard(changed)


def test_limit_does_not_exceed_ten_and_status_vocabulary_is_exact():
    with pytest.raises(ValueError):s.selection([],boundaries(),geography([]),[],11)
    assert s.FINAL_STATUSES=={'satellite_positive','observed_no_qualifying_floodwater',
        'insufficient_observation','candidate_mismatch','incomplete_computation'}


def stat(positive=0,valid=0):
    return dict(zip(s.grid.METRICS,[100,valid,positive,positive,0,valid,valid,valid,positive,positive]))


def test_zero_water_requires_adequate_observation_and_incomplete_stays_incomplete():
    def result(positive,valid,n=1):return s.grid.outcome([{'statistics':stat(positive,valid)}],n)
    assert result(0,0)['evidence_status']=='insufficient_observation'
    assert result(0,94)['evidence_status']=='insufficient_observation'
    assert result(0,95)['evidence_status']=='observed_no_qualifying_floodwater'
    assert result(2,3)['evidence_status']=='satellite_positive'
    assert result(2,100,2)['evidence_status']=='incomplete_computation'


def test_timing_logs_monotonic_acceptance_and_deadline(monkeypatch):
    clock=[0.];monkeypatch.setattr(s.grid,'elapsed_clock',lambda:clock[0])
    monkeypatch.setattr(s.time,'monotonic',lambda:clock[0]);monkeypatch.setitem(sys.modules,'ee',MagicMock())
    with TemporaryDirectory() as temporary:
        session=s.TimedEE(Path(temporary),60,900)
        def fn():clock[0]+=2;return {'fixture_only':True}
        assert session.request(fn,'fixture')=={'fixture_only':True}
        row=json.loads((Path(temporary)/'timing.jsonl').read_text())
        assert row['accepted'] and row['accepted_at'] and row['deadline_status']=='within_budget'
        assert row['start_monotonic_seconds']==0 and row['end_monotonic_seconds']==2
        assert not row['suspension_detected']


def test_late_result_rejected_at_three_attempts(monkeypatch):
    clock=[0.];calls=[]
    monkeypatch.setattr(s.grid,'elapsed_clock',lambda:clock[0]);monkeypatch.setitem(sys.modules,'ee',MagicMock())
    monkeypatch.setattr(s.time,'sleep',lambda n:clock.__setitem__(0,clock[0]+n))
    with TemporaryDirectory() as temporary:
        session=s.TimedEE(Path(temporary),60,900)
        def late():calls.append(1);clock[0]+=61;return {'fixture_only':True}
        with pytest.raises(Exception,match='3 attempt'):session.request(late,'fixture_late')
        rows=[json.loads(line) for line in (Path(temporary)/'timing.jsonl').read_text().splitlines()]
        assert len(calls)==len(rows)==3 and all(not r['accepted'] for r in rows)


def test_suspend_aware_total_limit_prevents_retry_and_marks_pause(monkeypatch):
    clock=[0.];calls=[]
    monkeypatch.setattr(s.grid,'elapsed_clock',lambda:clock[0]);monkeypatch.setattr(s.time,'monotonic',lambda:0.)
    monkeypatch.setitem(sys.modules,'ee',MagicMock())
    with TemporaryDirectory() as temporary:
        session=s.TimedEE(Path(temporary),60,900)
        def pause():calls.append(1);clock[0]+=1404;return {'fixture_only':True}
        with pytest.raises(Exception,match='1 attempt'):session.request(pause,'fixture_pause')
        row=json.loads((Path(temporary)/'timing.jsonl').read_text())
        assert len(calls)==1 and not row['accepted'] and row['suspension_detected']


def test_cumulative_regression_counts_are_distinct_and_no_daily_labels():
    previous=[{'gfd_id':3652,'gfd_start':'2010-05-18','review_region':{'shapeName':'Chitradurga'},
               'evidence_status':'satellite_positive','statistics':{'qualifying_pixels':2}}]
    result=s.cumulative(previous,[])
    assert result['qualifying_pixels']==58 and result['status_counts']['satellite_positive']==3
    assert result['positive_years']==['2005','2009','2010']
    assert result['positive_regions']==['Chitradurga','Udupi'] and result['daily_labels_created']==0
    with pytest.raises(ValueError,match='Duplicate'):s.cumulative(previous,previous)


def test_prior_3652_gate_rejects_mutation_and_does_not_rewrite(monkeypatch):
    monkeypatch.setattr(s.grid,'validate',lambda path:None)
    monkeypatch.setattr(s.grid,'udupi_gate',lambda *args:{'qualified_pixels':{'2728':33,'3551':23}})
    with TemporaryDirectory() as temporary:
        path=Path(temporary);records=[{'gfd_id':i,'computation_complete':True,'evidence_status':'satellite_positive',
                                     'statistics':{'qualifying_pixels':2 if i==3652 else 0}} for i in s.grid.IDS]
        p=path/'event_evidence.json';p.write_text(json.dumps(records));before=(p.read_bytes(),p.stat().st_mtime_ns)
        assert s.prior_gate(path)['event_3652_qualifying_pixels']==2
        assert before==(p.read_bytes(),p.stat().st_mtime_ns)
        records[3]['statistics']['qualifying_pixels']=3;p.write_text(json.dumps(records))
        with pytest.raises(ValueError,match='3652'):s.prior_gate(path)


def test_failed_event_has_immutable_checkpoint_and_unknown_counts(monkeypatch):
    c=candidate();c.update(review_region=boundary(),association_evidence=geo(c))
    with TemporaryDirectory() as temporary:
        session=MagicMock();session.raw=Path(temporary)
        monkeypatch.setattr(s.grid,'projection_metadata',MagicMock(side_effect=RuntimeError('fixture failure')))
        record=s.review(session,c)
        assert record['evidence_status']=='incomplete_computation' and record['statistics'] is None
        p=session.raw/'event_6001_checkpoint.json';assert json.loads(p.read_text())==record
        before=(p.read_bytes(),p.stat().st_mtime_ns)
        with pytest.raises(FileExistsError):s.review(session,c)
        assert before==(p.read_bytes(),p.stat().st_mtime_ns)
