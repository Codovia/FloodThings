"""Controlled temporary fixtures only; no Earth Engine/database/network access."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import nullcontext
import sys

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import box, mapping

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/build_event_comparison.py'
spec=importlib.util.spec_from_file_location('comparison',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.context


def anchor(eid=2698):
    return {'gfd_id':eid,'scope_id':f'controlled-{eid}',
        'image_id':c.history.event_asset(eid,'2005-09-14','2005-09-16'),
        'scope_name':m.COMPARISON[eid][0] if eid in m.COMPARISON else 'Controlled positive',
        'gfd_start':'2005-09-14','gfd_end_inclusive':'2005-09-16',
        'geometry':json.loads(json.dumps(mapping(box(74.55,13.1,74.65,13.2)))),
        'geometry_source':'controlled-fixture','geometry_vintage':'controlled-fixture',
        'geometry_sha256':'a'*64,'qualifying_floodwater_cells':m.EXPECTED_COUNTS[eid],
        'valid_gfd_observation_cells':m.COMPARISON[eid][1] if eid in m.COMPARISON else 1000,
        'original_observation_status':'observed_no_qualifying_floodwater' if eid in m.COMPARISON else 'satellite_positive',
        'ifi_association_status':'provisional','ifi_associations':[],
        'observation_quality':{'valid_fraction':.99,'absence_not_proven':True}}


def daily(a,value=1.):
    result=[]
    for d in c.dates(a):
        rel=(date.fromisoformat(d)-date.fromisoformat(a['gfd_start'])).days
        rain=value if rel<0 else 10000.
        result.append(c.summarize(a,d,np.array([[rain]]),np.array([[True]]),np.array([[True]]),
            {'source_image_id':f"{m.rain.SOURCE}/{d.replace('-','')}",'download':{'sha256':'a'*64,'retrieved_at':'fixture'},'file':'fixture'}))
    return result


def event_record(eid=2698):
    a=anchor(eid);f,d=c.derived(daily(a),[a])
    record={k:a[k] for k in ['gfd_id','scope_id','scope_name','gfd_start','gfd_end_inclusive',
         'qualifying_floodwater_cells','valid_gfd_observation_cells','original_observation_status','ifi_association_status','ifi_associations']}
    record.update(evidence_class='observed_zero_event' if eid in m.COMPARISON else 'satellite_positive',ml_binary_label=None,
        antecedent_features=f[0],descriptive_event_window_rainfall=d[0],observation_quality=a['observation_quality'],
        evidence_provenance={},rainfall_provenance={},gfd_processing_scale_m=250,gfd_processing_crs='EPSG:32643',
        gfd_observation_criteria=m.CRITERIA)
    return record


def raw_evidence(status='observed_no_qualifying_floodwater',valid=99,total=100,q=0):
    return {'evidence_status':status,'statistics':{'valid_pixels':valid,'region_pixels':total,'qualifying_pixels':q},
            'valid_fraction':valid/total,'computation_complete':True,'counts_are_lower_bounds':False}


def test_exact_vocabulary_and_observed_zero_is_not_binary():
    assert m.VOCABULARY=={'satellite_positive','observed_zero_event','unlabeled_background','insufficient_observation','candidate_mismatch'}
    assert m.evidence_class(raw_evidence(),.95)=='observed_zero_event'
    assert m.evidence_class(raw_evidence('satellite_positive',q=2),.95)=='satellite_positive'
    for records in [[event_record()],[],[{'evidence_class':'unlabeled_background'}]]:
        with pytest.raises(ValueError,match='not verified non-flood'):m.binary_targets(records)


@pytest.mark.parametrize('value',[0,1,False,True,'0','no','low'])
def test_non_null_binary_target_rejected(value):
    r=event_record();r['ml_binary_label']=value
    with pytest.raises(ValueError,match='Binary targets'):m.validate_evidence([r],{2698:0})


@pytest.mark.parametrize('field',['label','flood','risk','non_flood','daily_flood_label'])
def test_extra_binary_or_risk_fields_rejected(field):
    r=event_record();r[field]=0
    with pytest.raises(ValueError,match='binary/risk'):m.validate_evidence([r],{2698:0})


@pytest.mark.parametrize('status',['insufficient_observation','candidate_mismatch'])
def test_unusable_status_never_promoted_even_when_count_is_zero(status):
    assert m.evidence_class(raw_evidence(status,valid=0),.95)==status
    r=event_record();r['evidence_class']=status
    with pytest.raises(ValueError,match='excluded'):m.validate_evidence([r],{2698:0})


def test_unlabeled_background_cannot_become_pilot_negative():
    r=event_record();r['evidence_class']='unlabeled_background'
    with pytest.raises(ValueError,match='excluded'):m.validate_evidence([r],{2698:0})


@pytest.mark.parametrize('change',[
    lambda r:r.update(computation_complete=False),lambda r:r.update(counts_are_lower_bounds=True),
    lambda r:r.update(valid_fraction=.1),lambda r:r['statistics'].update(qualifying_pixels=1),
])
def test_observed_zero_requires_complete_quality_and_zero_counts(change):
    r=raw_evidence();change(r)
    with pytest.raises(ValueError):m.evidence_class(r,.95)


def test_existing_spatial_quality_gate_not_missing_or_absence_proof():
    with pytest.raises(ValueError,match='quality gate'):m.evidence_class(raw_evidence(valid=94),.95)
    with pytest.raises(ValueError,match='quality gate'):m.evidence_class(raw_evidence(valid=0),.95)
    assert m.evidence_class(raw_evidence(valid=95),.95)=='observed_zero_event'


def test_identical_feature_engineering_for_both_classes():
    a,b=anchor(2728),anchor(2698)
    f,d=c.derived(daily(a)+daily(b),[a,b])
    assert [{k:r[k] for k in m.FEATURES} for r in f]==[dict.fromkeys(m.FEATURES,1.)|{f'rain_{n}d_mm':float(n) for n in c.LENGTHS}]*2
    assert list(m.antecedent_predictors(event_record()).keys())==list(m.FEATURES)
    assert set(m.antecedent_predictors(event_record()))==set(m.FEATURES)
    assert 'event_window_total_mm' not in m.antecedent_predictors(event_record())


@pytest.mark.parametrize('relative',[0,1,2])
def test_event_start_and_future_rainfall_never_enter_comparison_features(relative):
    a=anchor();rows=daily(a);r=next(x for x in rows if x['days_relative_to_gfd_start']==relative)
    r.update(relationship='antecedent',use_class=c.ANTECEDENT)
    with pytest.raises(ValueError,match='Temporal leakage'):c.derived(rows,[a])


def test_descriptive_schema_cannot_be_mixed_with_predictors():
    r=event_record();r['antecedent_features']['event_window_total_mm']=r['descriptive_event_window_rainfall']['event_window_total_mm']
    with pytest.raises(ValueError,match='Descriptive/future'):m.antecedent_predictors(r)


def test_windows_deterministic_no_ifi_expansion_no_random_dates():
    a=anchor();b=deepcopy(a);b['ifi_associations']=[{'ifi_start':'2000-01-01','ifi_end_inclusive':'2030-01-01'}]
    assert c.dates(a)==c.dates(b) and len(c.dates(a))==33
    assert c.dates(a)[:30]==c.days('2005-08-15','2005-09-13')
    assert c.derived(daily(a),[a])==c.derived(daily(b),[b])
    assert m.COMPARISON=={2698:('Bijapur',166123),3107:('Raichur',132615)}
    text=SCRIPT.read_text();assert 'import random' not in text and 'np.random' not in text


@pytest.mark.parametrize('eid',[2728,3551,3652,2758,2698,3107])
def test_all_six_counts_and_event_identities_are_strict(eid):
    r=event_record(eid);m.validate_evidence([r],{eid:m.EXPECTED_COUNTS[eid]})
    r['qualifying_floodwater_cells']+=1
    with pytest.raises(ValueError,match='regression'):m.validate_evidence([r],{eid:m.EXPECTED_COUNTS[eid]})


@pytest.mark.parametrize('eid',[2698,3107])
def test_zero_valid_counts_cannot_be_weakened(eid):
    r=event_record(eid);r['valid_gfd_observation_cells']-=1
    with pytest.raises(ValueError,match='source identity/count'):m.validate_evidence([r],{eid:0})


def install_offline(monkeypatch,root,fail_day=None):
    positive=root/'positive';positive.mkdir(exist_ok=True);monkeypatch.setattr(m,'POSITIVE',positive)
    positive_anchors=[anchor(eid) for eid in c.COUNTS];all_positive=[r for a in positive_anchors for r in daily(a)]
    c.write_csv(positive/'daily_rainfall.csv',all_positive,c.DAILY_FIELDS)
    f,d=c.derived(all_positive,positive_anchors)
    source_data={'source':{'collection':m.rain.SOURCE,'version':'CHIRPS v2.0 Final','units':'mm/day'},'limitations':['Controlled fixture']}
    (positive/'manifest.json').write_text(json.dumps(source_data))
    inputs={'anchors':[anchor(eid) for eid in m.COMPARISON],'positive_anchors':positive_anchors,
            'positive_result':{'antecedent_features':f,'descriptive_event_rainfall':d},'inputs':{},
            'excluded_evidence':[{'gfd_id':9999,'evidence_class':'insufficient_observation','rainfall_extracted':False}]}
    monkeypatch.setattr(m,'retained_inputs',lambda:deepcopy(inputs))
    class Image:
        def __init__(self,identity):self.identity=identity
        def getInfo(self):
            t=datetime.strptime(self.identity.rsplit('/',1)[1],'%Y%m%d').replace(tzinfo=timezone.utc)
            return {'id':self.identity,'version':1,'bands':[{'id':'precipitation','data_type':{'precision':'float'},
                    'dimensions':[7200,2000],'crs':'EPSG:4326','crs_transform':m.rain.GRID}],
                    'properties':{'system:time_start':int(t.timestamp()*1000),'system:time_end':int((t+timedelta(days=1)).timestamp()*1000)}}
    class Session:
        def __init__(self,*args):self.ee=SimpleNamespace(Image=Image)
        def initialize(self):pass
        def request(self,fn,operation):
            if fail_day and fail_day in operation:raise TimeoutError('controlled timeout, not missing source rain')
            return fn()
    monkeypatch.setattr(c.satellite,'TimedEE',Session)
    monkeypatch.setitem(sys.modules,'requests',SimpleNamespace(Session=lambda:nullcontext(object())))
    monkeypatch.setattr(m.rain,'export_image',lambda image:SimpleNamespace(getDownloadURL=lambda params:'https://earthengine.googleapis.com/fixture'))
    def download(http,url,path):
        params=c.parameters(anchor()['geometry']);w,h=params['dimensions']
        with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=2,dtype='float32',crs='EPSG:4326',transform=Affine(*params['crs_transform'])) as stream:
            stream.write(np.ones((h,w),dtype='float32'),1);stream.write(np.ones((h,w),dtype='float32'),2)
        return {'retrieved_at':'2026-10-06T00:00:00+00:00',**m.source.fingerprint(path)}
    monkeypatch.setattr(m.rain,'download',download)


def snapshot(root):
    return {p:(p.read_bytes(),m.source.fingerprint(p),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def test_full_six_event_join_reproduces_and_preserves_sources_and_mtimes(monkeypatch):
    with TemporaryDirectory() as directory:
        root=Path(directory);install_offline(monkeypatch,root);original=snapshot(root/'positive')
        out,raw=root/'comparison_v1',root/'raw'
        result=m.extract(out,raw)
        assert result['new_daily_records']==66 and result['evidence_class_counts']=={'satellite_positive':4,'observed_zero_event':2}
        assert result['binary_targets_created']==result['background_windows_created']==0
        before=snapshot(root);assert m.validate(out)==result and snapshot(root)==before
        assert snapshot(root/'positive')==original
        with pytest.raises(ValueError,match='exists'):m.extract(out,raw,True)
        assert snapshot(root)==before
        records=c.read(out/'evidence.json');assert all(r['ml_binary_label'] is None for r in records)
        assert all(set(m.antecedent_predictors(r))==set(m.FEATURES) for r in records)
        records[0]['ml_binary_label']=0;(out/'evidence.json').write_text(json.dumps(records))
        with pytest.raises(ValueError,match='checksum'):m.validate(out)


def test_bounded_failure_preserves_partial_rasters_without_completed_dataset(monkeypatch):
    with TemporaryDirectory() as directory:
        root=Path(directory);install_offline(monkeypatch,root,fail_day='2005-08-17');out,raw=root/'comparison_v1',root/'raw'
        with pytest.raises(TimeoutError,match='not missing source'):m.extract(out,raw)
        assert not out.exists() and len(list(raw.rglob('*.tif')))==2
        log=c.read(raw/'access_attempt1.json');assert log['coverage'][0]['antecedent_days']==2
        assert len(log['coverage'][0]['not_retrieved_dates'])==31
        before=snapshot(raw);assert all(p.exists() for p in before)
