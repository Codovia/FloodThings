"""One calibration anchor; controlled fixtures, no live Earth Engine/database."""
from copy import deepcopy
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location('belagavi',Path(__file__).resolve().parents[2]/'scripts/calibrate_belagavi_sentinel1.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


def claims():
    return {'event_id':m.EVENT,'primary_spatial_calibration_observation_date':'2019-08-09',
       'spatial_source':{'reviewed_evidence':{'observation_date':'2019-08-09','machine_readable_flood_extent_available':False}},
       'official_hydrological_event_window':[
         {'station':'Sadalga','start':'2019-08-07','end_inclusive':'2019-08-14'},
         {'station':'Gokak Falls','start':'2019-08-06','end_inclusive':'2019-08-12'}],
       'official_district_flood_corroboration':{'source':{'reviewed_evidence':{'survey_date':'2019-08-11'}}},
       'scope_origin':{'reviewed_evidence':{'site_code':'CW1KRU000083','source_name':'Sadalga','longitude_degrees_east':74.5,'latitude_degrees_north':16.5}}}


def scene(day,orbit=63,platform='A',pass_='DESCENDING',coverage=1):
    return {'id':m.p.SOURCE+'/'+day+str(orbit)+platform,'scope_coverage_fraction':coverage,
      'properties':{'system:time_start':int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000),
       'instrumentMode':'IW','transmitterReceiverPolarisation':['VV','VH'],'orbitProperties_pass':pass_,
       'relativeOrbitNumber_start':orbit,'resolution_meters':10,'platform_number':platform}}


def arrays():
    pair={'baseline':[scene('2019-07-15'),scene('2019-07-27')],'event_scene':scene('2019-08-09')}
    ids,names=m.band_names(pair);a=np.ones((len(names),200,200),dtype='float32');d=dict(zip(names,a))
    for i in range(3):
        d[f's{i}_VV'][:]=-12 if i<2 else -20
        d[f's{i}_VH'][:]=-17 if i<2 else -26
        d[f's{i}_angle'][:]=35
    d['yearly'][:]=m.p.NODATA;d['yearly_mask'][:]=0
    d['monthly'][:]=0;d['slope_degrees'][:]=1
    return a,names,d


def ifi():
    return {'ifi_source_event_id':'fixture','source_row_ordinal':1,'source_start_date':'08-05-2019 00:00',
      'source_end_date':'08-08-2019 00:00','parsed_start_date':'2019-05-08','parsed_end_date_inclusive':'2019-08-08',
      'source_duration_days':'4','source_districts':'Belagavi, Udupi','source_district_lgd_codes':'527,549'}


def test_official_date_anchor_and_source_windows_preserved():
    c=claims();before=deepcopy(c);out=m.anchor(c)
    assert c==before and out['official_hydrological_event_window']==c['official_hydrological_event_window']
    assert out['primary_spatial_calibration_observation_date']=='2019-08-09'
    assert out['derived_contextual_union']=={'start':'2019-08-06','end_inclusive':'2019-08-14','type':'project_derived_union_not_original_station_value'}


@pytest.mark.parametrize('field',['primary_spatial_calibration_observation_date','event_id'])
def test_wrong_official_anchor_rejected(field):
    c=claims();c[field]='wrong'
    with pytest.raises(ValueError):m.anchor(c)


def test_source_intervals_cannot_be_collapsed_into_union():
    c=claims();c['official_hydrological_event_window'][0]['start']='2019-08-06'
    with pytest.raises(ValueError):m.anchor(c)


def test_ifi_duration_ambiguity_not_repaired_or_forced():
    row=ifi();before=deepcopy(row);out=m.associate_ifi([row])
    assert row==before and out['status']=='ambiguous' and out['primary_anchor_changed'] is False
    assert out['records'][0]['derived_duration_from_retained_parser']==93
    assert out['records'][0]['source_start']=='08-05-2019 00:00'
    assert out['records'][0]['source_lgd_token']=='527,549'


def test_no_ifi_match_does_not_invalidate_official_event():
    row=ifi();row['source_districts']='Different district'
    assert m.associate_ifi([row])['status']=='none'
    assert m.anchor(claims())['primary_spatial_calibration_observation_date']=='2019-08-09'


def test_ifi_unverified_fuzzy_alias_is_not_forced():
    row=ifi();row['source_districts']='Belagam'
    assert not m.associate_ifi([row])['records']


@pytest.mark.parametrize('day,role',[
 ('2019-08-09','exact_nrsc_calibration_date'),('2019-08-06','within_cwc_extreme_flood_window'),
 ('2019-08-14','within_cwc_extreme_flood_window'),('2019-08-15','immediately_after_verified_interval'),
 ('2019-08-18','immediately_after_verified_interval'),('2019-08-19','unsuitable_temporal_distance')])
def test_acquisition_temporal_vocabulary(day,role):
    assert m.temporal_role(scene(day),claims())==role


@pytest.mark.parametrize('field,value',[
 ('instrumentMode','EW'),('resolution_meters',40),('transmitterReceiverPolarisation',['VV']),
 ('orbitProperties_pass','unknown'),('relativeOrbitNumber_start',None),('platform_number',None)])
def test_unsupported_metadata_not_used(field,value):
    event=scene('2019-08-09');event['properties'][field]=value
    assert m.groups([scene('2019-07-27'),event],claims())['selected'] is None


@pytest.mark.parametrize('kwargs',[{'orbit':92},{'platform':'B'},{'pass_':'ASCENDING'},{'coverage':.5}])
def test_heterogeneous_pairs_or_partial_footprints_rejected(kwargs):
    assert m.groups([scene('2019-07-27'),scene('2019-08-09',**kwargs)],claims())['selected'] is None


def test_exact_date_priority_multiple_baselines_and_determinism():
    scenes=[scene('2019-07-03'),scene('2019-07-15'),scene('2019-07-27'),scene('2019-08-08'),scene('2019-08-09')]
    out=m.groups(scenes,claims());assert out==m.groups(list(reversed(scenes)),claims())
    assert out['selected']['temporal_role']=='exact_nrsc_calibration_date'
    assert len(out['selected']['baseline'])==3


def test_august6_broader_station_record_not_sadalga_event_pair():
    g=m.groups([scene('2019-07-27'),scene('2019-08-06')],claims())
    assert g['candidate_acquisitions'][0]['source_station_intervals_containing_acquisition']==['Gokak Falls']
    assert g['selected'] is None


def test_after_interval_and_future_baseline_not_used_for_rasters():
    g=m.groups([scene('2019-08-15'),scene('2019-08-18')],claims())
    assert g['selected'] is None and not any(r['baseline'] for r in g['candidate_acquisitions'])


def test_empty_inventory_explicit_pair_unavailable():
    assert m.groups([],claims())['pair_status']=='sentinel1_pair_unavailable'
    out=m.unavailable_result();m.ensure_no_binary_labels(out)
    assert out['continuous_analysis_status']=='not_performed_pair_unavailable'
    assert out['calibration_status']=='calibration_inconclusive'


def test_sar_continuous_values_survive_missing_jrc_and_unknown_permanent():
    a,n,d=arrays();before=a.copy();result,values,valid,flags=m.continuous(a,n)
    assert result['sar_valid_cells']==40000 and result['permanent_water_status_unknown_cells']==40000
    assert result['auxiliary_unknown_cells']==40000 and not flags['jrc_permanent_water'].any()
    assert result['continuous_statistics']['change_VV']['min']==-8 and result['continuous_statistics']['change_VH']['min']==-9
    assert valid.all() and np.array_equal(a,before)


def test_permanent_seasonal_and_no_data_separate_from_sar():
    a,n,d=arrays();d['yearly_mask'][:]=1;d['yearly'][:100]=3;d['yearly'][100:150]=2;d['yearly'][150:]=0
    r,_,_,_=m.continuous(a,n)
    assert r['sar_valid_cells']==40000 and r['permanent_water_cells_eligible_for_future_exclusion']==20000
    assert r['yearly_counts']['2']==10000 and r['permanent_water_status_unknown_cells']==10000


def test_sar_nodata_not_water_and_diagnostics_deterministic():
    a,n,d=arrays();d['s2_VV'][:100]=m.p.NODATA
    r=m.continuous(a,n)[0];assert r['sar_valid_cells']==20000 and r==m.continuous(a,n)[0]


@pytest.mark.parametrize('field',['manual_flood_polygon','flood_polygon','digitized_pdf_extent','pixel_ground_truth'])
def test_no_manual_pdf_polygon_generation(field):
    c=claims();c[field]={'coordinates':[]}
    with pytest.raises(ValueError):m.anchor(c)


def test_no_thresholds_without_spatial_reference_and_no_legacy_grid_mutation():
    method=deepcopy(m.p.METHOD);a,n,d=arrays();r=m.continuous(a,n)[0]
    assert m.p.METHOD==method and len(method['change_thresholds_db'])*len(method['event_vv_thresholds_db'])*len(method['slope_percent_limits'])==27
    assert r['threshold_sensitivity']==[] and r['threshold_analysis_performed'] is False
    r['threshold_sensitivity']=[{'candidate_cells':1}]
    with pytest.raises(ValueError):m.ensure_no_binary_labels(r)


@pytest.mark.parametrize('change',[{'flood_label':1},{'flood':0},{'daily_flood_label':1},{'probability':.8}])
def test_binary_and_risk_label_prevention(change):
    r=m.unavailable_result();r.update(change)
    with pytest.raises(ValueError):m.ensure_no_binary_labels(r)


def test_retrieval_window_ownership_and_no_claim_of_official_boundary():
    plan=m.plan(claims());assert plan['scope_type']=='retrieval_window_not_official_flood_boundary'
    own=np.zeros((200,200),int)
    for part in plan['partitions']:
        x0,x1,y0,y1=part['window'];own[y0:y1,x0:x1]+=1
    assert (own==1).all() and plan['administrative_clip'] is False


def test_continuous_product_temporary_outputs_preserve_original_bytes(monkeypatch):
    with TemporaryDirectory() as tmp:
        path=Path(tmp);source=path/'source.bin';source.write_bytes(b'original\r\n')
        before={**m.p.source.fingerprint(source),'mtime_ns':source.stat().st_mtime_ns}
        a,n,d=arrays();r=m.write_products(path/'continuous.tif',a,n,m.plan(claims()))
        assert r['threshold_analysis_performed'] is False
        assert {**m.p.source.fingerprint(source),'mtime_ns':source.stat().st_mtime_ns}==before
        with pytest.raises(ValueError):m.write_products(path/'continuous.tif',a,n,m.plan(claims()))


def test_offline_unavailable_validation_and_manifest_determinism_preserve_files(monkeypatch):
    with TemporaryDirectory() as tmp:
        root=Path(tmp);raw=root/'raw';out=root/'out';raw.mkdir();out.mkdir()
        c=claims();md={'claims':m.anchor(c),'grid':m.plan(c),'ifi_association':m.associate_ifi([]),
                      'response':{'count':0,'scenes':[]},'groups':m.groups([],c)}
        values={raw/'official_claims.json':c,raw/'metadata.json':md,root/'ifi.json':[],
         raw/'geographic_query_check.json':{'response':{'count':0},'comparison':'matches_empty_utm_query'},out/'event_evidence.json':m.unavailable_result()}
        for p,v in values.items():m.p.source.write_new(p,v)
        manifest={'method':m.METHOD,'code':m.p.source.fingerprint(Path(m.__file__)),
          'inputs':{str(p.relative_to(root)):m.p.source.fingerprint(p) for p in values if p.parent!=out},
          'files':{'event_evidence.json':m.p.source.fingerprint(out/'event_evidence.json')}}
        assert m.p.source.packed(manifest)==m.p.source.packed(dict(reversed(list(manifest.items()))))
        m.p.source.write_new(out/'manifest.json',manifest)
        def snapshot():return {str(p):{**m.p.source.fingerprint(p),'mtime_ns':p.stat().st_mtime_ns} for p in root.rglob('*') if p.is_file()}
        before=snapshot();monkeypatch.setattr(m,'RAW',raw);monkeypatch.setattr(m.p,'ROOT',root);monkeypatch.setattr(m.p,'IFI',root/'ifi.json')
        assert m.validate(out)==m.validate(out) and snapshot()==before


def test_no_live_raster_request_without_pair(monkeypatch):
    with TemporaryDirectory() as tmp:
        raw=Path(tmp);m.p.source.write_new(raw/'metadata.json',{'groups':{'selected':None}})
        with pytest.raises(ValueError,match='No defensible event pair'):m.extract(raw)
        assert not list(raw.glob('*.tif'))


def test_freeze_refuses_completed_version_before_reading_inputs():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);out=root/'out';out.mkdir();original=out/'original';original.write_bytes(b'protected')
        before={**m.p.source.fingerprint(original),'mtime_ns':original.stat().st_mtime_ns}
        with pytest.raises(ValueError,match='immutable'):m.freeze(out,root/'reference')
        assert before=={**m.p.source.fingerprint(original),'mtime_ns':original.stat().st_mtime_ns}


def test_freeze_offline_checkpoint_contains_no_geometry_or_pixel_truth(monkeypatch):
    with TemporaryDirectory() as tmp:
        root=Path(tmp);raw=root/'raw';raw.mkdir();c=claims()
        for source in [c['spatial_source'],c['official_district_flood_corroboration']['source'],c['scope_origin']]:
            source.update(pdf_page=1,source={'source_url':'https://example.invalid/fixture.pdf',
                          'retrieved_at':'2026-01-01T00:00:00+00:00','sha256':'0'*64,'bytes':1})
        c['hydrological_source']=deepcopy(c['spatial_source'])
        c['public_spatial_layer_access']={'source_file':'portal.txt','source_layer_id':'fixture',
         'original_date_label':'09/08/2019-18Hr','capabilities_attempt':{'source_url':'https://example.invalid/wms'}}
        for path in [root/'portal.txt',root/'pilot.py',root/'jrc.py']:path.write_bytes(b'isolated fixture')
        m.p.source.write_new(root/'ifi.json',[])
        md={'claims':m.anchor(c),'grid':m.plan(c),'ifi_association':m.associate_ifi([]),
            'response':{'count':0,'scenes':[]},'groups':m.groups([],c)}
        for name,value in [('official_claims.json',c),('metadata.json',md),('geographic_query_check.json',
                           {'response':{'count':0},'comparison':'matches_empty_utm_query'})]:
            m.p.source.write_new(raw/name,value)
        monkeypatch.setattr(m,'RAW',raw);monkeypatch.setattr(m.p,'ROOT',root);monkeypatch.setattr(m.p,'IFI',root/'ifi.json')
        monkeypatch.setattr(m.p,'__file__',str(root/'pilot.py'));monkeypatch.setattr(m.jrc,'__file__',str(root/'jrc.py'))
        out=root/'out';ref=root/'reference';assert m.freeze(out,ref)['pair_status']=='sentinel1_pair_unavailable'
        published=m.p.read(ref/'manifest.json')
        assert published['result']['flood_label'] is None and published['query']['scene_count']==0
        assert not {'transform','geometry','bounds','coordinates','flood_polygon'}&published.keys()
        assert not list(root.rglob('*.tif'))
        assert m.validate(out)['source_and_metadata_reproducibility'] is True
        with pytest.raises(ValueError,match='immutable'):m.freeze(out,ref)
