"""Controlled arrays and temporary archives only; no live EE/network/database."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import box, mapping

SPEC=importlib.util.spec_from_file_location('jrc',Path(__file__).resolve().parents[2]/'scripts/verify_jrc_auxiliary.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


def fixture():
    names=[f's{i}_{b}' for i in range(2) for b in ['VV','VH','angle']]+['water_valid']
    sar=np.ones((len(names),2,3),dtype='float32');sar[-1]=0
    scope=np.ones((2,3),bool)
    jrc={}
    for b in ['occurrence','seasonality','max_extent','yearly','month_5']:
        jrc[b]=np.full((2,3),m.pilot.NODATA,dtype='float32');jrc[b+'_mask']=np.zeros((2,3),dtype='float32')
    jrc['max_extent'][:]=0;jrc['max_extent_mask'][:]=1
    jrc['month_5'][:]=1;jrc['month_5_mask'][:]=1
    return sar,names,scope,jrc


def test_masked_global_land_does_not_invalidate_sar():
    a,n,s,j=fixture();d=m.diagnostics(a,n,s,j,'month_5')
    assert d['sar_valid_cells']==6 and d['legacy_occurrence_seasonality_intersection_cells']==0
    assert d['global']['occurrence']['masked_cells']==6
    assert d['global']['max_extent']['unmasked_cells']==6
    assert d['monthly']['month_5']['not_water_class_1_cells']==6
    assert d['permanent_water_status_unknown_cells']==6


def test_occurrence_fractional_mask_is_support_not_weight_or_twice_occurrence():
    v=np.array([[50.,100.,m.pilot.NODATA]]);mask=np.array([[.5,1.,0.]])
    r=m.global_band_diagnostic(v,mask,np.ones_like(mask,dtype=bool))
    assert r['sar_valid_intersection_cells']==2 and r['fractional_mask_cells']==1
    assert r['value_range_on_unmasked_sar_cells']==[50.,100.]


def test_monthly_classes_and_masks_remain_distinct():
    c=m.classification(np.array([[0.,1.,2.,m.pilot.NODATA]]),np.array([[1.,1.,1.,0.]]),2)
    assert c.tolist()==[[0,1,2,-1]]


def test_yearly_classes_permanent_only_and_unknown_status():
    v=np.array([[0.,1.,2.,3.,m.pilot.NODATA]]);mask=np.array([[1.,1.,1.,1.,0.]])
    f=m.auxiliary_flags(np.zeros_like(v),mask,v,mask)
    assert f['jrc_yearly_water_class'].tolist()==[[0,1,2,3,-1]]
    assert f['jrc_permanent_water'].tolist()==[[False,False,False,True,False]]
    assert f['jrc_permanent_water_status_known'].tolist()==[[False,True,True,True,False]]
    assert m.permanent_water_exclusion(np.ones_like(v,bool),f).sum()==1


def test_no_auxiliary_data_is_not_invalid_sar_or_permanent_water():
    a,n,s,j=fixture();j['month_5_mask'][:]=0
    d=m.diagnostics(a,n,s,j,'month_5')
    assert d['sar_valid_cells']==6 and d['cells_without_event_month_or_year_auxiliary_information']==6
    assert d['permanent_water_excluded_cells']==0
    assert d['monthly']['month_5']['masked_cells']==6
    assert d['monthly']['month_5']['no_data_class_0_cells']==0


def test_explicit_monthly_no_data_is_unavailable_not_dry():
    a,n,s,j=fixture();j['month_5'][:]=0
    d=m.diagnostics(a,n,s,j,'month_5')
    assert d['monthly']['month_5']['no_data_class_0_cells']==6
    assert d['monthly']['month_5']['not_water_class_1_cells']==0
    assert d['cells_without_event_month_or_year_auxiliary_information']==6


def test_sar_masks_and_scope_independent_of_monthly_context():
    a,n,s,j=fixture();a[0,0,0]=m.pilot.NODATA;a[1,0,1]=np.nan;s[1,2]=False
    assert m.diagnostics(a,n,s,j,'month_5')['sar_valid_cells']==3


@pytest.mark.parametrize('value,maximum',[(3,2),(4,3),(-1,2),(1.5,3),(np.nan,2)])
def test_invalid_unmasked_class_rejected(value,maximum):
    with pytest.raises(ValueError):m.classification(np.array([value]),np.ones(1),maximum)


@pytest.mark.parametrize('mask',[-1,1.1,np.nan])
def test_invalid_masks_rejected(mask):
    with pytest.raises(ValueError):m.classification(np.ones(1),np.array([mask]),2)


@pytest.mark.parametrize('corroboration,usable,status',[
 ('exact_date_and_spatial_scope',True,'supported'),
 ('exact_date_and_spatial_scope',False,'unresolved'),
 ('date_supported_spatially_broad',True,'spatially_weak'),
 ('year_event_supported_only',True,'temporally_weak'),
 ('unresolved',True,'unresolved')])
def test_calibration_suitability_vocabulary(corroboration,usable,status):
    assert m.suitability(corroboration,usable)=='calibration_candidate_'+status


def test_unrecognised_corroboration_not_promoted():
    with pytest.raises(ValueError):m.suitability('probably flooded',True)


def test_public_inventory_is_catalogue_only_and_preserves_dates():
    html='<input onclick=\'loadfloodmap("layer224","https://example.invalid/wms","ka_2019_09_08_18")\'>09/08/2019-18Hr&nbsp;<br>'
    r=m.bhuvan_inventory(html);row=r['dated_karnataka_products'][0]
    assert row['original_date_label']=='09/08/2019-18Hr' and row['district_intersection']=='not_verified'
    assert row['access_status']=='public_catalogue_only_layer_data_not_requested'
    assert r['karnataka_2018_dated_entry_found'] is False


def test_conflicting_public_layer_metadata_rejected():
    s='<input onclick=\'loadfloodmap("layer224","https://example.invalid/wms","ka_2019_09_08_18")\'>'
    with pytest.raises(ValueError):m.bhuvan_inventory(s+'9 Aug<br>'+s+'10 Aug<br>')


def test_suitability_never_promotes_existing_evidence():
    prior={'status':'sentinel1_ambiguous','ml_binary_label':None,'promoted_beyond_candidate':False}
    for status in m.SUITABILITY:
        preserved=m.preserve_status(prior,status)
        assert preserved==prior and preserved is not prior
    with pytest.raises(ValueError):m.preserve_status(prior,'verified flood')


def test_no_labels_or_thresholds_in_diagnostics_and_deterministic_inputs():
    a,n,s,j=fixture();before=deepcopy(j);copy=a.copy()
    r=m.diagnostics(a,n,s,j,'month_5')
    assert r==m.diagnostics(a,n,s,j,'month_5')
    assert not {'sensitivity','candidate_cells','ml_binary_label','daily_flood_label'}&r.keys()
    assert np.array_equal(a,copy)
    assert all(np.array_equal(before[k],j[k]) for k in j)


@pytest.mark.parametrize('collection,returned,expected',[
 (m.MONTHLY,'2018_05',m.MONTHLY+'/2018_05'),
 (m.YEARLY,'2019',m.YEARLY+'/2019'),
 (m.MONTHLY,m.MONTHLY+'/2018_06',m.MONTHLY+'/2018_06')])
def test_returned_temporal_basename_preserved_and_normalised(collection,returned,expected):
    assert m.temporal_asset(collection,returned)==expected


def test_wrong_asset_collection_not_silently_rewritten():
    with pytest.raises(ValueError):m.temporal_asset(m.MONTHLY,'OTHER/2018_05')


def test_source_temporal_identity_checked_independently_of_class_values():
    md={'year_count':1,'year':{'year':2018},'year_id':'2018',
        'months':{'5':{'count':1,'id':'2018_05','properties':{'year':2018,'month':5}}}}
    assert m.source_assets(md,2018,[5])['monthly']['5']==m.MONTHLY+'/2018_05'
    md['months']['5']['id']='2018_06'
    with pytest.raises(ValueError):m.source_assets(md,2018,[5])


def test_retired_old_extraction_cannot_run_even_with_arbitrary_new_paths():
    with pytest.raises(ValueError,match='extraction retired'):m.pilot.extract()


def test_offline_raster_diagnostics_preserve_failed_v1_completed_v2_and_raw(monkeypatch):
    with TemporaryDirectory() as tmp:
        root=Path(tmp);prior=root/'v2';prior.mkdir();raw=root/'jrc';folder=raw/'fixture';folder.mkdir(parents=True)
        v1=root/'v1';v1.mkdir();(v1/'failed.json').write_bytes(b'{"status":"incomplete"}\r\n')
        plan=m.pilot.plan_window(mapping(box(74.5,13,74.8,13.5)),7)
        sn=[f's{i}_{b}' for i in range(2) for b in ['VV','VH','angle']]+['water_valid']
        jn=[n for b in ['occurrence','seasonality','max_extent','month_5','yearly'] for n in [b,b+'_mask']]
        def write(path,names,part,is_jrc):
            a=np.ones((len(names),100,100),dtype='float32')
            if is_jrc:
                for i,name in enumerate(names):
                    if name in ['occurrence','seasonality','yearly']:a[i]=m.pilot.NODATA
                    if name in ['occurrence_mask','seasonality_mask','yearly_mask','max_extent']:a[i]=0
            with rasterio.open(path,'w',driver='GTiff',width=100,height=100,count=len(names),dtype='float32',crs=m.pilot.CRS,transform=Affine(*part['crs_transform'])) as ds:ds.write(a)
        tiles=[]
        for part in plan['partitions']:
            p=root/f'sar{part["index"]}.tif';write(p,sn,part,False)
            tiles.append({'file':p.name,'download':m.pilot.source.fingerprint(p)})
            p=folder/f'tile{part["index"]}.tif';write(p,jn,part,True)
            p.with_suffix('.json').write_text(json.dumps({'download':m.pilot.source.fingerprint(p)}))
        record={'event':{'ifi_source_event_id':'fixture','source_districts':'fixture','start':'2018-05-29','end_inclusive':'2018-05-29'},
          'result':{'sensitivity':[],'status':'sentinel1_ambiguous'},'plan':plan,'bands':sn,'tiles':tiles}
        (prior/'evidence.json').write_text(json.dumps([record]));(prior/'scene_inventory.json').write_text(json.dumps({'events':[{'event':record['event'],'public_geometry':mapping(box(74.5,13,74.8,13.5))}]}))
        (folder/'plan.json').write_text(json.dumps({'partitions':plan['partitions'],'crs':m.pilot.CRS,'names':jn}))
        (folder/'source_metadata.json').write_text(json.dumps({'year_count':1,'year':{'year':2018},'year_id':'2018',
          'months':{str(month):{'count':1,'id':f'2018_{month:02}','properties':{'year':2018,'month':month}} for month in [5,6]}}))
        def snapshot():return {str(p):{**m.pilot.source.fingerprint(p),'mtime_ns':p.stat().st_mtime_ns} for p in root.rglob('*') if p.is_file()}
        before=snapshot();monkeypatch.setattr(m.pilot,'ROOT',root)
        assert m.raster_counts(raw,prior)==m.raster_counts(raw,prior)
        assert snapshot()==before
