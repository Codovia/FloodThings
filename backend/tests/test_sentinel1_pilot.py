"""Temporary controlled arrays/metadata only. No Earth Engine or database calls."""
from copy import deepcopy
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest
from shapely.geometry import box,mapping

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/verify_sentinel1_pilot.py'
spec=importlib.util.spec_from_file_location('sentinel',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def ms(day):return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000)


def event(day='2018-05-29'):
    return {'start':day,'end_inclusive':day,'ifi_source_event_id':'fixture'}


def scene(day,orbit=63,pols=None,coverage=1):
    return {'id':m.SOURCE+'/'+day,'scope_coverage_fraction':coverage,'properties':{
      'system:time_start':ms(day),'instrumentMode':'IW','orbitProperties_pass':'DESCENDING',
      'relativeOrbitNumber_start':orbit,'resolution_meters':10,'platform_number':'A',
      'transmitterReceiverPolarisation':pols or ['VV','VH']}}


def input_row(day='2018-05-29',name='Fixture'):
    return {'ifi_source_event_id':day,'source_row_ordinal':1,'parsed_start_date':day,'parsed_end_date_inclusive':day,
      'source_start_date':day,'source_end_date':day,'date_status':{'window':'usable'},'source_districts':name,
      'source_state':'Karnataka','source_state_codes':'29','source_district_lgd_codes':'source-only',
      'identifier_status':'unverified'}


def inv(events):
    c={'response':{'earliest_ms':ms('2015-02-24'),'latest_ms':ms('2026-10-04')}}
    b={'response':{'features':[{'shapeName':'Fixture','shapeGroup':'IND','shapeID':'public-fixture'}]}}
    return m.inventory(events,c,b)


def arrays():
    pair={'baseline':[scene('2018-05-01'),scene('2018-05-13')],'event_scene':scene('2018-05-29')}
    ids,names=m.band_names(pair);a=np.zeros((len(names),200,200),dtype='float32');d=dict(zip(names,a))
    for i in range(3):
        d[f's{i}_VV'][:]=-12 if i<2 else -18
        d[f's{i}_VH'][:]=-17 if i<2 else -24
        d[f's{i}_angle'][:]=35
    d['water_valid'][:]=1;d['dem_valid'][:]=1
    return a,names,d


def test_candidate_period_uses_live_dates_and_rejects_reversed_or_undated():
    rows=[input_row('2014-12-01'),input_row(),input_row('2027-01-01')]
    r=input_row();r['parsed_end_date_inclusive']='2017-01-01';rows.append(r)
    r=input_row();r['parsed_start_date']=None;rows.append(r)
    out=inv(rows);assert out['counts']['within_live_coverage_valid']==1
    assert sum(r['eligible'] for r in out['rows'])==1


def test_no_guessed_location_alias_or_lgd_replacement():
    r=input_row(name='Unverified alias');out=inv([r]);assert not out['rows'][0]['eligible']
    assert out['rows'][0]['source_district_lgd_codes']=='source-only'
    assert r==input_row(name='Unverified alias')


def test_duplicate_public_name_is_not_exact_identity():
    c={'response':{'earliest_ms':ms('2015-02-24'),'latest_ms':ms('2026-10-04')}}
    b={'response':{'features':[{'shapeName':'Fixture','shapeGroup':'IND','shapeID':x} for x in ['a','b']]}}
    assert not m.inventory([input_row()],c,b)['rows'][0]['eligible']


def test_deterministic_selection_ignores_input_order_and_outcomes():
    rows=[input_row(f'{y}-06-01') for y in range(2016,2022)]
    out=inv(rows);assert m.shortlist(out)==m.shortlist(inv(list(reversed(rows))))
    assert len(m.shortlist(out))==3


@pytest.mark.parametrize('field,value',[('instrumentMode','EW'),('orbitProperties_pass','ASCENDING'),
 ('relativeOrbitNumber_start',165),('resolution_meters',40),('platform_number','B'),
 ('transmitterReceiverPolarisation',['VV'])])
def test_heterogeneous_scene_pair_unavailable(field,value):
    a,b=scene('2018-05-10'),scene('2018-05-29');b['properties'][field]=value
    assert m.group_scenes([a,b],event())['selected'] is None


def test_missing_band_is_not_fabricated():
    scenes=[scene('2018-05-10',pols=['VV']),scene('2018-05-29',pols=['VV'])]
    assert m.group_scenes(scenes,event())['selected'] is None


def test_same_orbit_dual_pol_pair_uses_several_pre_start_scenes():
    rows=[scene('2018-05-10'),scene('2018-05-22'),scene('2018-05-29')]
    g=m.group_scenes(rows,event())['selected'];assert len(g['baseline'])==2
    assert all(m.scene_role(s,event())=='baseline' for s in g['baseline'])
    assert g['configuration'][2]==63


def test_duplicate_slices_do_not_inflate_baseline():
    rows=[scene('2018-05-10'),scene('2018-05-10'),scene('2018-05-29')]
    assert len(m.group_scenes(rows,event())['selected']['baseline'])==1


@pytest.mark.parametrize('day,role',[('2018-05-28','baseline'),('2018-05-29','during_documented_event'),
 ('2018-05-30','immediately_after_event'),('2018-06-05','immediately_after_event'),
 ('2018-06-06','outside_event'),('2018-04-01','outside_event')])
def test_temporal_rules_and_no_future_baseline(day,role):
    assert m.scene_role(scene(day),event())==role
    assert (role=='baseline')==(ms('2018-04-14')<=ms(day)<ms('2018-05-29'))


def test_partial_footprint_rejected():
    assert m.group_scenes([scene('2018-05-10',coverage=.5),scene('2018-05-29')],event())['selected'] is None


def test_workload_and_half_open_partitions_cover_each_cell_once():
    plan=m.plan_window(mapping(box(74.5,13,74.8,13.5)),19)
    assert plan['spatial_pixels']==40000 and plan['band_pixels']==760000
    assert plan['per_partition_band_pixels']==190000<plan['maxPixels']==300000
    ownership=np.zeros((200,200),int)
    for p in plan['partitions']:
        x0,x1,y0,y1=p['window'];ownership[y0:y1,x0:x1]+=1
    assert (ownership==1).all() and not plan['bestEffort']
    with pytest.raises(ValueError):m.plan_window(mapping(box(74.5,13,74.8,13.5)),21)


def test_permanent_water_and_unknown_masks_not_changed_water():
    a,n,d=arrays();mask=np.ones((200,200),bool)
    d['water_seasonality'][:100]=12;d['water_valid'][100:150]=0
    r=m.analyze(a,n,mask)
    assert r['permanent_water_cells']==20000 and r['auxiliary_missing_cells']==10000
    assert r['nominal']['candidate_cells']==10000 and r['status']=='sentinel1_ambiguous'
    m.validate_result(r)


def test_sar_nodata_never_becomes_dark_flood_signal():
    a,n,d=arrays();d['s2_VV'][:]=m.NODATA
    r=m.analyze(a,n,np.ones((200,200),bool));assert r['sar_valid_cells']==0
    assert r['nominal']['candidate_cells']==0 and r['status']=='sentinel1_ambiguous'


def test_incidence_and_percent_slope_masks():
    a,n,d=arrays();d['s2_angle'][:100]=50;d['slope_degrees'][100:]=10
    r=m.analyze(a,n,np.ones((200,200),bool));assert r['incidence_rejected_cells']==20000
    assert r['steep_cells_at_5_percent']==20000 and r['nominal']['valid_analysis_cells']==0


def test_sensitivity_is_predeclared_not_tuned_and_monotonic():
    a,n,d=arrays();d['s2_VV'][:]=-15.5
    r=m.analyze(a,n,np.ones((200,200),bool));assert len(r['sensitivity'])==27
    assert r['candidate_range_cells']==[0,40000]
    assert r['nominal']['candidate_cells']==0 and r['ml_binary_label'] is None
    for sl in [3,5,7]:
        for ab in [-14,-16,-18]:
            counts=[x['candidate_cells'] for x in r['sensitivity'] if x['slope_percent_limit']==sl and x['event_vv_threshold_db']==ab]
            assert counts==sorted(counts,reverse=True)


@pytest.mark.parametrize('change',[lambda r:r.update(status='flood_negative'),lambda r:r.update(ml_binary_label=0),
 lambda r:r.update(flood=0),lambda r:r.update(daily_flood_label=1),lambda r:r.update(promoted_beyond_candidate=True),
 lambda r:r.update(status='sentinel1_supported_flood_candidate')])
def test_no_binary_label_or_unvalidated_promotion(change):
    a,n,d=arrays();r=m.analyze(a,n,np.ones((200,200),bool));change(r)
    with pytest.raises(ValueError):m.validate_result(r)


def test_valid_zero_signal_is_not_negative_and_empty_valid_is_ambiguous():
    a,n,d=arrays();d['s2_VV'][:]=-12;d['s2_VH'][:]=-17
    r=m.analyze(a,n,np.ones((200,200),bool));assert r['status']=='sentinel1_no_clear_flood_signal' and r['ml_binary_label'] is None
    d['water_valid'][:]=0;assert m.analyze(a,n,np.ones((200,200),bool))['status']=='sentinel1_ambiguous'


def test_manifest_bytes_deterministic_and_no_overwrite():
    assert m.source.packed({'b':2,'a':1})==m.source.packed({'a':1,'b':2})
    with TemporaryDirectory() as folder:
        path=Path(folder)/'manifest.json';m.source.write_new(path,{'b':2,'a':1});before=(path.read_bytes(),path.stat().st_mtime_ns)
        with pytest.raises((FileExistsError,ValueError)):m.source.write_new(path,{'a':3})
        assert before==(path.read_bytes(),path.stat().st_mtime_ns)


def test_late_results_rejected_with_bounded_attempts(monkeypatch):
    clock=[0.];calls=[];b=m.bounded
    monkeypatch.setattr(b.grid,'elapsed_clock',lambda:clock[0]);monkeypatch.setitem(sys.modules,'ee',MagicMock())
    monkeypatch.setattr(b.time,'sleep',lambda n:clock.__setitem__(0,clock[0]+n))
    with TemporaryDirectory() as folder:
        s=b.TimedEE(Path(folder),60,900)
        def late():calls.append(1);clock[0]+=61;return {'controlled':True}
        with pytest.raises(Exception,match='3 attempt'):s.request(late,'controlled')
        rows=[json.loads(x) for x in (Path(folder)/'timing.jsonl').read_text().splitlines()]
        assert len(calls)==3 and all(not x['accepted'] for x in rows)


def test_products_georeferenced_and_source_bytes_preserved():
    import rasterio
    a,n,d=arrays();plan=m.plan_window(mapping(box(74.5,13,74.8,13.5)),len(n))
    before=a.copy()
    with TemporaryDirectory() as folder:
        path=Path(folder)/'products.tif';m.write_products(path,a,n,plan)
        with rasterio.open(path) as r:
            assert r.crs.to_string()==m.CRS and r.nodata==m.NODATA and r.count==6
            assert np.all(r.read(3)==-6) and np.all(r.read(6)==-7)
        snapshot=(path.read_bytes(),path.stat().st_mtime_ns)
        with pytest.raises(ValueError):m.write_products(path,a,n,plan)
        assert snapshot==(path.read_bytes(),path.stat().st_mtime_ns)
    assert np.array_equal(a,before)


def test_offline_partial_manifest_rebuild_read_only(monkeypatch):
    # Five controlled metadata-only candidates, three completed unavailable pairs.
    # All fixture observations/checkpoints stay in a cleaned temporary directory.
    with TemporaryDirectory() as folder:
        root=Path(folder);raw=root/'raw';raw.mkdir();out=root/'working'
        ifi=root/'ifi.json';bounds=root/'bounds.json'
        rows=[input_row(f'{y}-06-01') for y in range(2016,2021)]
        c={'response':{'earliest_ms':ms('2015-02-24'),'latest_ms':ms('2026-10-04')}}
        b={'response':{'features':[{'shapeName':'Fixture','shapeGroup':'IND','shapeID':'public-fixture'}]}}
        ifi.write_text(json.dumps(rows));bounds.write_text(json.dumps(b))
        monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'RAW',raw);monkeypatch.setattr(m,'OUTPUT',out);monkeypatch.setattr(m,'IFI',ifi)
        monkeypatch.setattr(m.bounded,'BOUNDARIES',bounds)
        inventory=m.inventory(rows,c,b);selected=m.shortlist(inventory,5)
        metadata={'method':m.METHOD,'events':[{'event':e,'scenes':[],'pair':m.group_scenes([],e)} for e in selected]}
        for name,value in [('coverage.json',c),('candidate_inventory.json',inventory),('metadata.json',metadata)]:m.source.write_new(raw/name,value)
        for name in ['data/working/karnataka_event_comparison_v1/evidence.json',
                     'data/working/karnataka_positive_event_rainfall_v1/manifest.json',
                     'data/working/karnataka_chirps_soi2025_2025_v1/daily_rainfall.csv']:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('controlled source checksum fixture')
        records=[{'evidence_source':'Sentinel-1','event':e,'method':m.METHOD,'scene_selection':m.group_scenes([],e),
             'result':{'status':'sentinel1_pair_unavailable','ml_binary_label':None,'promoted_beyond_candidate':False}} for e in selected[:3]]
        m.finish(records,metadata,complete=False)
        paths=[p for p in root.rglob('*') if p.is_file()]
        before={str(p):(m.source.fingerprint(p),p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
        result=m.validate(out);assert result['records']==3 and not result['computation_complete']
        assert len(m.read(out/'manifest.json')['unreviewed_event_ids'])==2
        assert before=={str(p):(m.source.fingerprint(p),p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
        with pytest.raises(FileExistsError):m.finish(records,metadata,False)


def test_sdk_download_url_mutation_cannot_corrupt_journal_parameters():
    parameters={'crs':m.CRS,'dimensions':[100,100],'crs_transform':[10,0,0,0,-10,0]}
    before=deepcopy(parameters)
    class SDK:
        def getDownloadURL(self,p):
            p['image']=object();p['dimensions'][0]=999
            return 'controlled-no-network'
    assert m.download_url(SDK(),parameters)=='controlled-no-network'
    assert parameters==before and json.loads(json.dumps(parameters))==before
