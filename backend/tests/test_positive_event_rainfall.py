"""Controlled rainfall fixtures only; no source requests or research-dataset writes."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import box, mapping

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/extract_positive_event_rainfall.py'
spec=importlib.util.spec_from_file_location('positive_rainfall',SCRIPT)
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def anchor(eid=2728):
    return {'gfd_id':eid,'scope_id':'controlled-scope','scope_name':'Controlled test scope',
            'gfd_start':'2005-09-14','gfd_end_inclusive':'2005-09-16',
            'geometry':json.loads(json.dumps(mapping(box(74.55,13.1,74.65,13.2)))),
            'qualifying_floodwater_cells':33,
            'ifi_associations':[{'ifi_start':'2005-08-01','ifi_end_inclusive':'2005-11-01'}]}


def rows(a=None):
    a=a or anchor();result=[]
    for day in r.dates(a):
        delta=(date.fromisoformat(day)-date.fromisoformat(a['gfd_start'])).days
        # Event-window sentinel is intentionally much larger than antecedent values.
        v=float(-delta) if delta<0 else 10000.+delta
        record={'source_image_id':f"{r.rain.SOURCE}/{day.replace('-','')}",
                'download':{'sha256':'a'*64,'retrieved_at':'2026-10-06T00:00:00+00:00'},'file':'fixture.tif'}
        result.append(r.summarize(a,day,np.array([[v]],dtype='float64'),np.array([[True]]),np.array([[True]]),record))
    return result


def test_exact_30_day_gfd_anchor_ignores_ifi_window():
    a=anchor();daily=rows(a);f,d=r.derived(daily,[a])
    assert len(daily)==33 and r.dates(a)[0]=='2005-08-15'
    assert f[0]['last_allowed_date']=='2005-09-13'
    assert [f[0][f'rain_{n}d_mm'] for n in r.LENGTHS]==[1.,6.,28.,105.,465.]
    assert f[0]['max_daily_previous_7d_mm']==7.
    assert f[0]['max_daily_previous_14d_mm']==14.
    assert d[0]['event_window_total_mm']==30003.
    assert d[0]['event_window_daily_mean_mm']==10001.
    assert d[0]['event_window_max_daily_mm']==10002.
    b=deepcopy(a);b['ifi_associations'][0]['ifi_end_inclusive']='2006-12-31'
    assert r.dates(a)==r.dates(b) and r.derived(daily,[b])==(f,d)


@pytest.mark.parametrize('relative',[0,1,2])
def test_start_day_and_future_rainfall_cannot_enter_antecedents(relative):
    a=anchor();daily=rows(a);row=next(x for x in daily if x['days_relative_to_gfd_start']==relative)
    row.update(relationship='antecedent',use_class=r.ANTECEDENT)
    with pytest.raises(ValueError,match='Temporal leakage'):r.derived(daily,[a])


def test_descriptive_changes_never_change_antecedent_features():
    a=anchor();daily=rows(a);before=r.derived(daily,[a])[0]
    for row in daily:
        if row['relationship']=='event_window':
            for key in ['regional_min_mm_per_day','regional_mean_mm_per_day','regional_max_mm_per_day']:row[key]=999999.
    assert r.derived(daily,[a])[0]==before


def test_descriptive_fields_cannot_be_moved_into_predictor_schema():
    f,d=r.derived(rows(),[anchor()]);f[0]['event_window_total_mm']=d[0]['event_window_total_mm']
    with pytest.raises(ValueError,match='Descriptive/future'):r.validate_feature_sets(f,d)


@pytest.mark.parametrize('field',['flood_label','confirmed_flood_day','daily_flood_occurrence'])
def test_maximum_event_extent_cannot_become_daily_labels(field):
    daily=rows();daily[0][field]=1
    with pytest.raises(ValueError,match='flood labels'):r.validate_daily(daily,[anchor()])


def test_missing_date_has_null_affected_totals_not_zero_or_neighbour():
    daily=rows();daily=[x for x in daily if x['days_relative_to_gfd_start']!=-1]
    f,d=r.derived(daily,[anchor()])
    assert all(f[0][f'rain_{n}d_mm'] is None for n in r.LENGTHS)
    assert f[0]['status']=='incomplete_antecedent_data' and d[0]['status']=='complete'
    with pytest.raises(ValueError,match='coverage incomplete'):r.validate_daily(daily,[anchor()])


def test_missing_event_day_only_invalidates_descriptive_results():
    daily=[x for x in rows() if x['days_relative_to_gfd_start']!=0]
    f,d=r.derived(daily,[anchor()])
    assert f[0]['rain_30d_mm']==465. and d[0]['event_window_total_mm'] is None


def test_duplicate_dates_and_control_events_are_rejected():
    daily=rows()
    with pytest.raises(ValueError,match='Duplicate'):r.validate_daily(daily+[daily[0]],[anchor()])
    daily[0]['gfd_id']=2698
    with pytest.raises(ValueError,match='control'):r.validate_daily(daily,[anchor()])


def test_udupi_events_remain_separate_without_normalization():
    a,b=anchor(),anchor(3551);daily=rows(a)+rows(b)
    f,d=r.derived(daily,[a,b])
    assert len(f)==len(d)==2 and {x['gfd_id'] for x in f}=={2728,3551}
    assert f[0]['rain_30d_mm']==f[1]['rain_30d_mm']==465.


def test_geometry_window_sends_grid_only_and_scalar_masks_preserve_unknown():
    a=anchor();params=r.parameters(a['geometry']);mask,centres=r.membership(a['geometry'],params)
    assert 'region' not in params and 'geometry' not in params
    assert params['crs']=='EPSG:4326' and params['crs_transform'][0]==.05 and params['crs_transform'][4]==-.05
    h,w=mask.shape;values=np.arange(h*w,dtype='float32').reshape(h,w);valid=np.ones_like(mask)
    i,j=np.argwhere(mask)[0];valid[i,j]=False;values[i,j]=r.rain.NODATA
    rec={'source_image_id':r.rain.SOURCE+'/20050913','download':{'sha256':'a'*64,'retrieved_at':'fixture'},'file':'fixture'}
    row=r.summarize(a,'2005-09-13',values,valid,mask,rec)
    assert row['status']=='partial_spatial_coverage'
    assert r.scalar_check(a,row,values,valid,centres)['matches']
    f,_=r.derived([row],[a]);assert f[0]['rain_1d_mm'] is None
    empty=r.summarize(a,'2005-09-13',values,np.zeros_like(mask),mask,rec)
    assert empty['regional_mean_mm_per_day'] is None and empty['status']=='no_valid_pixels'


def test_csv_is_deterministic_exclusive_and_read_only():
    with TemporaryDirectory() as directory:
        root=Path(directory);a,b=root/'a.csv',root/'b.csv';daily=rows()
        r.write_csv(a,daily,r.DAILY_FIELDS);r.write_csv(b,daily,r.DAILY_FIELDS)
        before=(a.read_bytes(),r.rain.soi.fingerprint(a),a.stat().st_mtime_ns)
        assert r.csv_rows(a,r.DAILY_FIELDS)==daily and a.read_bytes()==b.read_bytes()
        with pytest.raises(FileExistsError):r.write_csv(a,daily,r.DAILY_FIELDS)
        assert (a.read_bytes(),r.rain.soi.fingerprint(a),a.stat().st_mtime_ns)==before


def test_native_raster_nodata_and_zero_are_distinct():
    with TemporaryDirectory() as directory:
        path=Path(directory)/'fixture.tif';params=r.parameters(anchor()['geometry']);w,h=params['dimensions']
        values=np.zeros((h,w),dtype='float32');valid=np.ones_like(values)
        values[0,0]=r.rain.NODATA;valid[0,0]=0
        with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=2,dtype='float32',crs='EPSG:4326',
                           transform=Affine(*params['crs_transform'])) as stream:
            stream.write(values,1);stream.write(valid,2)
        before=(path.read_bytes(),path.stat().st_mtime_ns)
        v,m,metadata=r.rain.read_raster(path,params)
        assert not m[0,0] and m[0,1] and v[0,1]==0 and v[0,0]==r.rain.NODATA
        assert (path.read_bytes(),path.stat().st_mtime_ns)==before
        wrong=deepcopy(params);wrong['crs_transform'][0]=.1
        with pytest.raises(ValueError):r.rain.read_raster(path,wrong)


def install_offline_pipeline(monkeypatch,fail_day=None):
    from contextlib import nullcontext
    from datetime import datetime, timezone
    from types import SimpleNamespace
    import sys
    monkeypatch.setitem(sys.modules,'requests',SimpleNamespace(Session=lambda:nullcontext(object())))
    a=anchor();monkeypatch.setattr(r,'load_anchors',lambda:[deepcopy(a)])
    monkeypatch.setattr(r,'input_files',lambda:{})
    class Image:
        def __init__(self,identity):self.identity=identity
        def getInfo(self):
            day=datetime.strptime(self.identity.rsplit('/',1)[1],'%Y%m%d').replace(tzinfo=timezone.utc)
            return {'id':self.identity,'version':1,'bands':[{'id':'precipitation','data_type':{'precision':'float'},
                    'dimensions':[7200,2000],'crs':'EPSG:4326','crs_transform':r.rain.GRID}],
                    'properties':{'system:time_start':int(day.timestamp()*1000),
                                  'system:time_end':int((day+timedelta(days=1)).timestamp()*1000)}}
    class Session:
        def __init__(self,*args):self.ee=SimpleNamespace(Image=Image)
        def initialize(self):pass
        def request(self,fn,operation):
            if fail_day and fail_day in operation:raise RuntimeError('controlled unavailable date')
            return fn()
    monkeypatch.setattr(r.satellite,'TimedEE',Session)
    monkeypatch.setattr(r.rain,'export_image',lambda image:SimpleNamespace(getDownloadURL=lambda params:'https://earthengine.googleapis.com/fixture'))
    def download(http,url,path):
        params=r.parameters(a['geometry']);w,h=params['dimensions']
        with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=2,dtype='float32',crs='EPSG:4326',
                           transform=Affine(*params['crs_transform'])) as stream:
            stream.write(np.full((h,w),2.,dtype='float32'),1);stream.write(np.ones((h,w),dtype='float32'),2)
        return {'retrieved_at':'2026-10-06T00:00:00+00:00',**r.rain.soi.fingerprint(path)}
    monkeypatch.setattr(r.rain,'download',download)


def test_full_extraction_validation_preserves_exact_bytes_hashes_and_mtimes(monkeypatch):
    install_offline_pipeline(monkeypatch)
    with TemporaryDirectory() as directory:
        root=Path(directory);output,raw=root/'completed_v1',root/'raw'
        result=r.extract(output,raw)
        assert result['daily_records']==33 and result['independent_scalar_checks']==33
        assert result['antecedent_features'][0]['rain_30d_mm']==60.
        before={p:(p.read_bytes(),r.rain.soi.fingerprint(p),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        assert r.validate(output)==result
        with pytest.raises(ValueError,match='exists'):r.extract(output,raw,True)
        assert before=={p:(p.read_bytes(),r.rain.soi.fingerprint(p),p.stat().st_mtime_ns) for p in before}
        with (output/'daily_rainfall.csv').open('a') as stream:stream.write('\n')
        with pytest.raises(ValueError,match='checksum'):r.validate(output)


def test_partial_retrieval_retains_validated_rasters_and_resumes_without_rewrite(monkeypatch):
    install_offline_pipeline(monkeypatch,fail_day='2005-08-17')
    with TemporaryDirectory() as directory:
        root=Path(directory);output,raw=root/'completed_v1',root/'raw'
        with pytest.raises(RuntimeError,match='controlled unavailable'):r.extract(output,raw)
        assert not output.exists()
        access=r.read(raw/'access_attempt1.json')
        assert access['validated_coverage'][0]['antecedent_days']==2
        assert '2005-08-17' in access['validated_coverage'][0]['not_retrieved_dates']
        old={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in raw.rglob('*.tif')}
        install_offline_pipeline(monkeypatch)
        result=r.extract(output,raw,True)
        assert result['daily_records']==33
        assert old=={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in old}
