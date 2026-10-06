#!/usr/bin/env python3
"""Bounded Sentinel-1 feasibility pilot. No labels, SOI uploads or GFD edits.

Metadata selection is frozen before pixel retrieval. Experimental change evidence
is always ambiguous without independent spatial validation; it is never absence.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import expand_karnataka_satellite as bounded
import extract_karnataka_rainfall as download

source = bounded.source
ROOT = source.ROOT
SOURCE = 'COPERNICUS/S1_GRD'
WATER = 'JRC/GSW1_4/GlobalSurfaceWater'
DEM = 'USGS/SRTMGL1_003'
RAW = ROOT/'data/raw/sentinel1/stage3e_v1'
OUTPUT = ROOT/'data/working/karnataka_sentinel1_flood_pilot_v1'
IFI = ROOT/'data/working/karnataka_flood_events_v1/events.json'
CRS = 'EPSG:32643'
SCALE = 10
NODATA = -9999.
STATUSES = frozenset({'sentinel1_supported_flood_candidate','sentinel1_no_clear_flood_signal',
    'sentinel1_pair_unavailable','sentinel1_ambiguous','sentinel1_computation_incomplete'})
METHOD = {'baseline':'per-pixel median of up to four distinct pre-start UTC acquisitions in dB',
 'event':'first compatible scene during event; otherwise first within 7 days after inclusive end',
 'change':'event minus baseline dB, independently for VV and VH; no dB division',
 'resampling':'nearest to aligned 10 m EPSG:32643 research grid; no assertion of 10 m physical resolution',
 'change_thresholds_db':[-2.,-3.,-4.], 'event_vv_thresholds_db':[-14.,-16.,-18.],
 'event_vh_threshold_db':-22., 'slope_percent_limits':[3.,5.,7.],
 'incidence_angle_degrees':[30.,45.], 'max_angle_difference_degrees':1.,
 'permanent_water':'GSW v1.4 seasonality >= 10 months; valid occurrence and seasonality masks required',
 'terrain':'SRTM slope in degrees converted locally to percent=100*tan(degrees); not shadow/layover model',
 'threshold_status':'EXPERIMENTAL_PREDECLARED_NOT_VALIDATED',
 'scope_rule':'2 km square around deterministic public district representative point, grid-snapped; local district cell-centre clip',
 'interpretation':'Raw unsmoothed sigma0 change candidates; no connected-pixel filter or speckle correction. Unknown confounders preclude promotion.',
 'future_auxiliary_data':'GSW 1984-2021 summary is retrospective; not prediction-time feature',
 'radiometric_terrain_flattening':False}
SELECT_RULE = ('Unique exact single IFI district token in retained public inventory, Karnataka-only, usable window <=31 days, '
 'baseline search fully inside live coverage; greedily new year, new region, earlier date, stable original ID. '
 'Three scopes; no raster outcomes, no guessed aliases. Availability tested after shortlist; pair unavailable retained.')


def read(path):
    return json.loads(Path(path).read_text())


def require(value, message):
    source.require(value, message)


def utc_day(ms):
    return datetime.fromtimestamp(ms/1000, timezone.utc).date().isoformat()


def coverage():
    require(not (RAW/'coverage.json').exists(),'Coverage checkpoint immutable')
    RAW.mkdir(parents=True,exist_ok=True)
    s=bounded.TimedEE(RAW,60,900);s.initialize();ee=s.ee
    state=ee.FeatureCollection(bounded.STATE_SOURCE).filter(ee.Filter.eq('shapeID',bounded.STATE_ID)).geometry()
    c=ee.ImageCollection(SOURCE).filterBounds(state)
    r=s.request(lambda:ee.Dictionary({'count':c.size(),'earliest_ms':c.aggregate_min('system:time_start'),
      'latest_ms':c.aggregate_max('system:time_start'),'modes':c.aggregate_histogram('instrumentMode'),
      'resolutions_m':c.aggregate_histogram('resolution_meters'),'passes':c.aggregate_histogram('orbitProperties_pass'),
      'polarizations':c.aggregate_array('transmitterReceiverPolarisation').flatten().distinct(),
      'first_scene':c.sort('system:time_start').first().toDictionary()}).getInfo(),'state_collection_metadata')
    a=s.request(lambda:ee.data.getAsset(SOURCE),'collection_asset_metadata')
    source.write_new(RAW/'coverage.json',{'source':SOURCE,'retrieved_at':source.now(),'project':'floodpulse',
       'state_source':bounded.STATE_SOURCE,'state_id':bounded.STATE_ID,'response':r,'asset':a})


def inventory(events, coverage, boundaries):
    lo,hi = [date.fromisoformat(utc_day(coverage['response'][key])) for key in ['earliest_ms','latest_ms']]
    counts = Counter(f['shapeName'] for f in boundaries['response']['features'])
    exact = {f['shapeName']:f for f in boundaries['response']['features'] if counts[f['shapeName']]==1 and f['shapeGroup']=='IND'}
    rows=[]
    for e in events:
        start,end=e['parsed_start_date'],e['parsed_end_date_inclusive']
        valid=bool(start and end and start<=end and e['date_status']['window']=='usable')
        inside=valid and lo<=date.fromisoformat(start)<=date.fromisoformat(end)<=hi
        tokens=[v.strip() for v in e['source_districts'].split(',') if v.strip()]
        matches=sorted(set(tokens)&exact.keys())
        reason=None
        if not inside:reason='invalid_window_or_outside_live_coverage'
        elif e['source_state']!='Karnataka':reason='multi_state_scope_not_narrowed'
        elif len(tokens)!=1 or len(matches)!=1:reason='not_unique_exact_single_district'
        elif (date.fromisoformat(end)-date.fromisoformat(start)).days>30:reason='window_over_31_days'
        elif date.fromisoformat(start)-timedelta(days=45)<lo:reason='baseline_search_before_live_coverage'
        rows.append({'ifi_source_event_id':e['ifi_source_event_id'],'source_row_ordinal':e['source_row_ordinal'],
         'start':start,'end_inclusive':end,'original_start':e['source_start_date'],'original_end':e['source_end_date'],
         'source_state':e['source_state'],'source_districts':e['source_districts'],
         'source_state_codes':e['source_state_codes'],'source_district_lgd_codes':e['source_district_lgd_codes'],
         'identifier_status':e['identifier_status'],'valid_window':valid,'within_live_coverage':inside,
         'exact_public_tokens':matches,'unresolved_tokens':sorted(set(tokens)-exact.keys()),
         'eligible':reason is None,'rejection_reason':reason,
         'public_region':exact[matches[0]] if reason is None else None})
    within=[r for r in rows if r['within_live_coverage']]
    return {'selection_rule':SELECT_RULE,'live_coverage_days':[lo.isoformat(),hi.isoformat()],
     'counts':{'all_ifi_karnataka_records':len(rows),'post_2014_start_records':sum(bool(r['start'] and r['start']>='2014-01-01') for r in rows),
      'within_live_coverage_valid':len(within),'unresolved_location_no_exact_token':sum(not r['exact_public_tokens'] for r in within),
      'partially_unresolved_location':sum(bool(r['unresolved_tokens']) for r in within),
      'narrow_pilot_eligible':sum(r['eligible'] for r in rows)},
     'years':sorted({r['start'][:4] for r in within}), 'rows':rows}


def shortlist(inv, limit=3):
    require(type(limit) is int and 3<=limit<=5,'Pilot must have 3-5 events')
    pool=[r for r in inv['rows'] if r['eligible']];chosen=[];years=set();regions=set()
    while pool and len(chosen)<limit:
        r=min(pool,key=lambda r:(r['start'][:4] in years,r['public_region']['shapeID'] in regions,r['start'],r['ifi_source_event_id']))
        chosen.append(r);years.add(r['start'][:4]);regions.add(r['public_region']['shapeID']);pool.remove(r)
    return chosen


def config(scene):
    p=scene['properties']
    return (p.get('instrumentMode'),p.get('orbitProperties_pass'),p.get('relativeOrbitNumber_start'),
            p.get('resolution_meters'),tuple(sorted(p.get('transmitterReceiverPolarisation',[]))),p.get('platform_number'))


def scene_role(scene,event):
    day=utc_day(scene['properties']['system:time_start'])
    T=date.fromisoformat(event['start']); end=date.fromisoformat(event['end_inclusive']);d=date.fromisoformat(day)
    if T-timedelta(days=45)<=d<T:return 'baseline'
    if T<=d<=end:return 'during_documented_event'
    if end<d<=end+timedelta(days=7):return 'immediately_after_event'
    return 'outside_event'


def group_scenes(scenes,event):
    groups={};rejected=[]
    for s in scenes:
        require(s['id'].startswith(SOURCE+'/'),'Wrong SAR scene source')
        k=config(s);role=scene_role(s,event)
        if k[0]!='IW' or k[3]!=10 or not {'VV','VH'}<=set(k[4]) or k[1] not in {'ASCENDING','DESCENDING'} or type(k[2]) not in {int,float} or k[5] is None:
            rejected.append({'id':s['id'],'reason':'unsupported_or_missing_configuration'});continue
        if s['scope_coverage_fraction']<.9999 or role=='outside_event':
            rejected.append({'id':s['id'],'reason':'incomplete_footprint_or_outside_window'});continue
        groups.setdefault(k,[]).append(s)
    pairs=[]
    for k,rows in groups.items():
        pre=sorted([s for s in rows if scene_role(s,event)=='baseline'],key=lambda s:(s['properties']['system:time_start'],s['id']))
        # Separate sliced products at the same UTC acquisition cannot inflate baseline count.
        seen=set();unique=[]
        for s in reversed(pre):
            t=s['properties']['system:time_start']
            if t not in seen:unique.append(s);seen.add(t)
        pre=list(reversed(unique[:4]))
        post=sorted([s for s in rows if scene_role(s,event)!='baseline'],key=lambda s:(scene_role(s,event)!='during_documented_event',s['properties']['system:time_start'],s['id']))
        if pre and post:pairs.append({'configuration':list(k[:-2])+[list(k[-2]),k[-1]],'baseline':pre,'event_scene':post[0]})
    pairs.sort(key=lambda g:(scene_role(g['event_scene'],event)!='during_documented_event',-len(g['baseline']),g['event_scene']['properties']['system:time_start'],g['event_scene']['id']))
    selected=pairs[0] if pairs else None
    used=set([s['id'] for s in selected['baseline']]+[selected['event_scene']['id']]) if selected else set()
    rejected.extend({'id':s['id'],'reason':'not_in_deterministic_selected_group'} for s in scenes if s['id'] not in used and s['id'] not in {r['id'] for r in rejected})
    return {'selected':selected,'groups_available':len(pairs),'rejected':rejected}


def plan_window(geometry, bands):
    g=shape(geometry);require(g.is_valid and not g.is_empty,'Invalid public district geometry')
    p=g.representative_point();x,y=Transformer.from_crs(4326,32643,always_xy=True).transform(p.x,p.y)
    x0=math.floor((x-1000)/10)*10;y1=math.ceil((y+1000)/10)*10
    require(1<=bands<=20,'Unsafe band count')
    partitions=[]
    for row in range(2):
        for col in range(2):
            partitions.append({'index':row*2+col,'window':[col*100,(col+1)*100,row*100,(row+1)*100],
             'crs_transform':[10,0,x0+col*1000,0,-10,y1-row*1000],'dimensions':[100,100]})
    return {'crs':CRS,'scale_m':10,'transform':[10,0,x0,0,-10,y1],'dimensions':[200,200],
     'area_m2':4000000,'spatial_pixels':40000,'bands':bands,'band_pixels':40000*bands,
     'partition_count':4,'partitions':partitions,'per_partition_spatial_pixels':10000,
     'per_partition_band_pixels':10000*bands,'maxPixels':300000,'bestEffort':False,
     'reductions':'local only, no remote reduceRegion','request_deadline_seconds':60,'phase_total_deadline_seconds':900,
     'download_byte_ceiling':1048576,'download_elapsed_ceiling_seconds':30,
     'scope_label':'deterministic bounded research window, not official flood footprint or municipal boundary'}


def scope_mask(geometry,plan):
    import shapely
    a=Affine(*plan['transform']);rows,cols=np.indices((200,200));x=a.c+(cols+.5)*a.a;y=a.f+(rows+.5)*a.e
    lon,lat=Transformer.from_crs(32643,4326,always_xy=True).transform(x,y)
    return shapely.contains_xy(shape(geometry),lon,lat)


def band_names(pair):
    ids=[s['id'] for s in pair['baseline']]+[pair['event_scene']['id']]
    names=[f's{i}_{b}' for i in range(len(ids)) for b in ['VV','VH','angle']]+['water_seasonality','water_valid','slope_degrees','dem_valid']
    return ids,names


def analyze(values,names,mask):
    require(values.shape==(len(names),200,200),'Unexpected raster dimensions')
    arrays=dict(zip(names,values));n=(len(names)-4)//3;require(n>=2,'Baseline unavailable')
    sar=[arrays[f's{i}_{b}'] for i in range(n) for b in ['VV','VH','angle']]
    observed=mask.copy()
    for a in sar:observed &= np.isfinite(a)&(a!=NODATA)
    auxiliary=(arrays['water_valid']==1)&(arrays['dem_valid']==1)&np.isfinite(arrays['slope_degrees'])&(arrays['slope_degrees']!=NODATA)
    vv=np.median(np.stack([arrays[f's{i}_VV'] for i in range(n-1)]),axis=0)
    vh=np.median(np.stack([arrays[f's{i}_VH'] for i in range(n-1)]),axis=0)
    angle=np.median(np.stack([arrays[f's{i}_angle'] for i in range(n-1)]),axis=0)
    evv,evh,eangle=[arrays[f's{n-1}_{b}'] for b in ['VV','VH','angle']]
    dvv,dvh=evv-vv,evh-vh
    slope=100*np.tan(np.deg2rad(arrays['slope_degrees']))
    permanent=arrays['water_seasonality']>=10
    angular=(angle>=30)&(angle<=45)&(eangle>=30)&(eangle<=45)&(np.abs(eangle-angle)<=1)
    base=observed&auxiliary&angular&~permanent
    sensitivity=[]
    for sl in METHOD['slope_percent_limits']:
        valid=base&(slope<=sl)&(slope>=0)
        for absolute in METHOD['event_vv_thresholds_db']:
            for change in METHOD['change_thresholds_db']:
                candidate=valid&(dvv<=change)&(dvh<=change)&(evv<=absolute)&(evh<=-22)
                count=int(candidate.sum());sensitivity.append({'change_threshold_db':change,'event_vv_threshold_db':absolute,
                    'slope_percent_limit':sl,'valid_analysis_cells':int(valid.sum()),'candidate_cells':count,'candidate_area_m2':count*100})
    nominal=next(r for r in sensitivity if r['change_threshold_db']==-3 and r['event_vv_threshold_db']==-16 and r['slope_percent_limit']==5)
    usable=nominal['valid_analysis_cells'];q=nominal['candidate_cells']
    status='sentinel1_ambiguous' if q or not usable else 'sentinel1_no_clear_flood_signal'
    def limits(a,v):return [float(a[v].min()),float(a[v].max())] if v.any() else None
    return {'status':status,'ml_binary_label':None,'independent_spatial_corroboration':'not_available',
      'promoted_beyond_candidate':False,'scope_cells':int(mask.sum()),'sar_valid_cells':int(observed.sum()),
      'auxiliary_missing_cells':int((observed&~auxiliary).sum()),'permanent_water_cells':int((observed&auxiliary&permanent).sum()),
      'incidence_rejected_cells':int((observed&auxiliary&~angular).sum()),
      'steep_cells_at_5_percent':int((base&(slope>5)).sum()),'nominal':nominal,'sensitivity':sensitivity,
      'event_incidence_degrees_range':limits(eangle,observed),'baseline_incidence_degrees_range':limits(angle,observed),
      'vv_change_db_range':limits(dvv,observed),'vh_change_db_range':limits(dvh,observed),
      'candidate_range_cells':[min(r['candidate_cells'] for r in sensitivity),max(r['candidate_cells'] for r in sensitivity)],
      'candidate_count_interpretation':'not_assessable_no_valid_cells' if not usable else 'experimental_darkening_count_not_verified_floodwater',
      'interpretation':'Small-window experimental dual-pol darkening; no validated flood extent or true negative. Speckle, vegetation, dry surfaces and unmodelled shadow/layover remain.'}


def validate_result(r):
    require(r['status'] in STATUSES,'Invalid Sentinel-1 status')
    require(r['ml_binary_label'] is None and r.get('promoted_beyond_candidate') is False,'Binary/final flood labels forbidden')
    require(not {'flood','label','daily_flood_label','risk','probability'}&set(r),'Binary/risk fields forbidden')
    if 'sensitivity' in r:
        require(len(r['sensitivity'])==27,'Incomplete sensitivity grid')
        require(r['nominal'] in r['sensitivity'],'Nominal sensitivity not retained')
        for s in r['sensitivity']:
            require(type(s['candidate_cells']) is int and 0<=s['candidate_cells']<=s['valid_analysis_cells']<=r['scope_cells'],'Invalid cell counts')
            require(s['candidate_area_m2']==s['candidate_cells']*100,'Invalid metric area')
        require(r['status']!='sentinel1_supported_flood_candidate','Unvalidated pilot must remain ambiguous/no-clear-signal')


def metadata():
    require(not (RAW/'metadata.json').exists(),'Completed metadata is immutable')
    coverage=read(RAW/'coverage.json');boundaries=read(bounded.BOUNDARIES)
    inv=inventory(read(IFI),coverage,boundaries);selected=shortlist(inv)
    # Retain interrupted metadata checks without issuing duplicate successful queries.
    for path,value in [(RAW/'candidate_inventory.json',inv),(RAW/'shortlist.json',selected)]:
        if path.exists():require(read(path)==value,'Retained offline selection changed')
        else:source.write_new(path,value)
    selected=shortlist(inv,5)
    path=RAW/'expanded_shortlist.json'
    if path.exists():require(read(path)==selected,'Expanded metadata shortlist changed')
    else:source.write_new(path,selected)
    session=bounded.TimedEE(RAW,60,900);session.initialize();ee=session.ee;results=[]
    props=['system:time_start','system:time_end','system:index','instrumentMode','transmitterReceiverPolarisation',
      'orbitProperties_pass','relativeOrbitNumber_start','relativeOrbitNumber_stop','resolution_meters','platform_number',
      'platformHeading','productType','GRD_Post_Processing_software_version']
    for e in selected:
        feature=ee.FeatureCollection(source.BOUNDARY).filter(ee.Filter.eq('shapeID',e['public_region']['shapeID']))
        geo=session.request(lambda:ee.Dictionary({'count':feature.size(),'geometry':feature.geometry()}).getInfo(),f"public_region:{e['ifi_source_event_id']}")
        require(geo['count']==1,'Public geometry not unique');plan=plan_window(geo['geometry'],7)
        a=plan['transform'];window=ee.Geometry.Rectangle([a[2],a[5]-2000,a[2]+2000,a[5]],proj=CRS,geodesic=False)
        lo=(date.fromisoformat(e['start'])-timedelta(days=45)).isoformat();hi=(date.fromisoformat(e['end_inclusive'])+timedelta(days=8)).isoformat()
        coll=ee.ImageCollection(SOURCE).filterBounds(window).filterDate(lo,hi)
        def descriptor(obj):
            im=ee.Image(obj);p=im.select('angle').projection()
            return ee.Dictionary({'id':ee.String(SOURCE+'/').cat(ee.String(im.get('system:index'))),'returned_id':im.id(),'properties':im.toDictionary(props),'footprint':im.geometry(),
              'scope_coverage_fraction':im.geometry().intersection(window,1).area(1).divide(window.area(1)),
              'angle_projection':p,'angle_nominal_scale_m':p.nominalScale()})
        cache=RAW/f"{e['ifi_source_event_id']}.scene_metadata.json"
        if cache.exists():info=read(cache)
        else:
            info=session.request(lambda:ee.Dictionary({'count':coll.size(),'scenes':coll.sort('system:time_start').limit(40).toList(40).map(descriptor)}).getInfo(),f"scene_metadata:{e['ifi_source_event_id']}")
            source.write_new(cache,info)
        require(info['count']==len(info['scenes'])<=40,'Scene metadata cap exceeded; no silent truncation')
        groups=group_scenes(info['scenes'],e)
        results.append({'event':e,'public_geometry':geo['geometry'],'public_geometry_sha256':hashlib.sha256(source.packed(geo['geometry'])).hexdigest(),
          'search_dates_exclusive_end':[lo,hi],'retrieved_at':source.now(),'scenes':info['scenes'],'pair':groups})
        print(json.dumps({'metadata_event':e['ifi_source_event_id'],'scene_count':info['count'],'groups':groups['groups_available'],
                         'baseline_count':len(groups['selected']['baseline']) if groups['selected'] else 0}),flush=True)
    source.write_new(RAW/'metadata.json',{'retrieved_at':source.now(),'method':METHOD,'events':results})
    print(json.dumps({'inventory_counts':inv['counts'],'years':inv['years'],'selected_ids':[r['ifi_source_event_id'] for r in selected]}),flush=True)


def read_tile(path,part,names):
    with rasterio.open(path) as r:
        require(r.crs==rasterio.crs.CRS.from_string(CRS) and r.transform.almost_equals(Affine(*part['crs_transform'])),'SAR raster CRS/grid mismatch')
        require((r.width,r.height,r.count)==(100,100,len(names)) and set(r.dtypes)=={'float32'},'SAR raster layout mismatch')
        values=r.read();require(np.isfinite(values).all(),'Unencoded nonfinite values')
        return values


def download_url(image,parameters):
    # The Earth Engine SDK adds an unserialisable image object to its argument.
    # Keep immutable, journalable parameters separate from the SDK working copy.
    return image.getDownloadURL(json.loads(json.dumps(parameters)))


def raw_image(ee,pair):
    ids,names=band_names(pair);bands=[]
    for i,asset in enumerate(ids):
        im=ee.Image(asset)
        for b in ['VV','VH','angle']:bands.append(im.select(b).unmask(NODATA,sameFootprint=False).rename(f's{i}_{b}').toFloat())
    water=ee.Image(WATER);dem=ee.Image(DEM).select('elevation')
    valid=water.select('seasonality').mask().And(water.select('occurrence').mask())
    bands.extend([water.select('seasonality').unmask(NODATA,sameFootprint=False).rename('water_seasonality').toFloat(),
      valid.unmask(0,sameFootprint=False).rename('water_valid').toFloat(),
      ee.Terrain.slope(dem).unmask(NODATA,sameFootprint=False).rename('slope_degrees').toFloat(),
      ee.Terrain.slope(dem).mask().unmask(0,sameFootprint=False).rename('dem_valid').toFloat()])
    return ee.Image.cat(bands),names


def extract():
    import requests
    require(not OUTPUT.exists(),'Completed version or partial output exists; never overwrite')
    m=read(RAW/'metadata.json');require(m['method']==METHOD,'Predeclared method changed')
    session=bounded.TimedEE(RAW,60,900);session.initialize();ee=session.ee;records=[]
    with requests.Session() as http:
        for item in m['events']:
            e=item['event'];pair=item['pair']['selected']
            result={'status':'sentinel1_pair_unavailable','ml_binary_label':None,'promoted_beyond_candidate':False}
            record={'evidence_source':'Sentinel-1','event':e,'gfd_associations':existing_gfd(e),'method':METHOD,
              'scene_selection':item['pair'],'geometry_sha256':item['public_geometry_sha256'],'tiles':[],'result':result}
            if pair:
                im,names=raw_image(ee,pair);plan=plan_window(item['public_geometry'],len(names));record.update(plan=plan,bands=names)
                full=np.full((len(names),200,200),NODATA,dtype='float32')
                folder=RAW/e['ifi_source_event_id'];folder.mkdir(exist_ok=True)
                try:
                    plan_file=folder/'workload_plan.json'
                    if plan_file.exists():require(read(plan_file)==plan,'Retained workload plan changed')
                    else:source.write_new(plan_file,plan)
                    ids,_=band_names(pair)
                    projections=folder/'source_projections.json'
                    if projections.exists():record['source_projections']=read(projections)
                    else:
                        def projection_metadata(asset):
                            image=ee.Image(asset)
                            return ee.Dictionary({b:ee.Dictionary({'projection':image.select(b).projection(),
                               'nominal_scale_m':image.select(b).projection().nominalScale()}) for b in ['VV','VH','angle']})
                        record['source_projections']=session.request(lambda:ee.Dictionary({asset:projection_metadata(asset) for asset in ids}).getInfo(),f"source_projections:{e['ifi_source_event_id']}")
                        source.write_new(projections,record['source_projections'])
                    for part in plan['partitions']:
                        path=folder/f"tile{part['index']}.tif";meta=path.with_suffix('.json')
                        params={'crs':CRS,'crs_transform':part['crs_transform'],'dimensions':part['dimensions'],'format':'GEO_TIFF','filePerBand':False}
                        if meta.exists():
                            info=read(meta);require(info['parameters']==params and info['bands']==names and info['download']==source.fingerprint(path),'Cached SAR tile changed')
                        else:
                            require(not path.exists(),'Unjournaled raster; preserve for explicit recovery')
                            url=session.request(lambda:download_url(im,params),f"download_url:{e['ifi_source_event_id']}:{part['index']}")
                            attempt=0
                            def retrieve():
                                nonlocal attempt
                                attempt+=1;return download.download(http,url,path.with_suffix(f'.attempt{attempt}.partial.tif'))
                            downloaded=session.request(retrieve,f"raster_download:{e['ifi_source_event_id']}:{part['index']}")
                            path.with_suffix(f'.attempt{attempt}.partial.tif').rename(path)
                            read_tile(path,part,names)
                            info={'parameters':params,'bands':names,'download':source.fingerprint(path),'retrieved_at':downloaded['retrieved_at'],'request':downloaded['request']}
                            source.write_new(meta,info)
                        values=read_tile(path,part,names);x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=values
                        record['tiles'].append({'file':str(path.relative_to(ROOT)),**info})
                    record['result']=analyze(full,names,scope_mask(item['public_geometry'],plan));validate_result(record['result'])
                    # Retain exact baseline/event/change products with masks and metadata.
                    product=folder/'change_products.tif';write_products(product,full,names,plan)
                    record['derived_raster']={'file':str(product.relative_to(ROOT)),**source.fingerprint(product)}
                except Exception as exc:
                    record['result']={'status':'sentinel1_computation_incomplete','ml_binary_label':None,'promoted_beyond_candidate':False,'error':source.provider_error(exc)}
                    source.write_new(folder/'incomplete.json',record);records.append(record)
                    finish(records,m,complete=False)
                    raise
            records.append(record)
            source.write_new(RAW/f"{e['ifi_source_event_id']}.completed.json",record)
            print(json.dumps({'event':e['ifi_source_event_id'],'result':record['result']}),flush=True)
    finish(records,m,complete=True)


def write_products(path,values,names,plan):
    require(not path.exists(),'Derived raster immutable')
    n=(len(names)-4)//3;a=dict(zip(names,values));mask=np.ones((200,200),bool)
    for i in range(n):
        for b in ['VV','VH','angle']:mask &= a[f's{i}_{b}']!=NODATA
    products=[];labels=[]
    for b in ['VV','VH']:
        pre=np.median(np.stack([a[f's{i}_{b}'] for i in range(n-1)]),axis=0);event=a[f's{n-1}_{b}']
        for label,v in [('baseline',pre),('event',event),('change',event-pre)]:products.append(np.where(mask,v,NODATA));labels.append(f'{label}_{b}_dB')
    with rasterio.open(path,'w',driver='GTiff',width=200,height=200,count=6,dtype='float32',crs=CRS,
                       transform=Affine(*plan['transform']),nodata=NODATA,compress='deflate') as r:
        r.write(np.array(products,dtype='float32'))
        for i,label in enumerate(labels,1):r.set_band_description(i,label)


def existing_gfd(event):
    # Original documentary relationships only. No new GFD scan or fusion.
    rows=read(ROOT/'data/working/karnataka_satellite_event_evidence_v4/candidates.json')
    return [{'gfd_id':r['gfd_id'],'association_status':r['candidate_status'],
       'satellite_confirmation':r['satellite_confirmation'],
       'interpretation':'Retained provisional documentary relationship, not spatial validation; no new GFD review'}
      for r in rows if r['ifi_source_event_id']==event['ifi_source_event_id'] and r['gfd_id'] is not None]


def finish(records,metadata,complete):
    OUTPUT.mkdir(exist_ok=False)
    source.write_new(OUTPUT/'evidence.json',records)
    source.write_new(OUTPUT/'candidate_inventory.json',read(RAW/'candidate_inventory.json'))
    source.write_new(OUTPUT/'scene_inventory.json',metadata)
    sources={'sar':SOURCE,'water':WATER,'terrain':DEM,'public_geometry':source.BOUNDARY,'ifi_doi':'10.5281/zenodo.16994648'}
    inputs={str(p.relative_to(ROOT)):source.fingerprint(p) for p in [IFI,bounded.BOUNDARIES,
       ROOT/'data/working/karnataka_event_comparison_v1/evidence.json',ROOT/'data/working/karnataka_positive_event_rainfall_v1/manifest.json',
       ROOT/'data/working/karnataka_chirps_soi2025_2025_v1/daily_rainfall.csv']}
    manifest={'version':OUTPUT.name,'created_at':source.now(),'project':'floodpulse','sources':sources,'method':METHOD,
      'computation_complete':complete,'records':len(records),'unreviewed_event_ids':[r['event']['ifi_source_event_id'] for r in metadata['events'] if r['event']['ifi_source_event_id'] not in {v['event']['ifi_source_event_id'] for v in records}],
      'coverage':read(RAW/'coverage.json'),'selection_rule':SELECT_RULE,'candidate_counts':read(RAW/'candidate_inventory.json')['counts'],
      'metadata_selection_extension':'Initial three extended to five after first metadata checks found unavailable pairs; same ranking, no pixel outcomes. Actual dual VV/VH required by this implemented method; missing bands never forced.',
      'licences':{'Sentinel-1':'Copernicus Sentinel Data Terms; Contains modified Copernicus Sentinel data [actual acquisition years retained per scene]',
       'JRC':'European Commission JRC/Copernicus free access; Pekel et al.2016,1984-2021 retrospective GSW v1.4',
       'SRTM':'NASA/USGS public domain; February 2000 DSM, approx30m, not current bare-earth verification',
       'geoBoundaries':'CC BY 4.0 William and Mary geoLab v6.0 2023 composite, not historical boundary',
       'IFI':'Saharia et al./IIT Delhi/HydroSense CC BY-NC 4.0'},
      'inputs':inputs,'files':{p.name:source.fingerprint(p) for p in OUTPUT.iterdir() if p.is_file()},
      'raw_files':{str(p.relative_to(ROOT)):source.fingerprint(p) for p in RAW.rglob('*') if p.is_file()},
      'code':source.fingerprint(Path(__file__)),'publication':'Detailed geometry, SAR rasters and evidence local. Metadata/code/checksums only.'}
    source.write_new(OUTPUT/'manifest.json',manifest)


def validate(output=OUTPUT):
    m=read(output/'manifest.json');require(m['method']==METHOD and m['sources']['sar']==SOURCE,'Source/method changed')
    for k,v in m['files'].items():require(source.fingerprint(output/k)==v,'Output checksum mismatch')
    for k,v in {**m['inputs'],**m['raw_files']}.items():require(source.fingerprint(ROOT/k)==v,'Source/raw checksum mismatch')
    execution=Path(__file__)
    if m['code']!=source.fingerprint(execution):
        execution=ROOT/'data/recovery/stage3e_v1/execution_sources'/f"{m['code']['sha256']}.py"
    require(execution.exists() and m['code']==source.fingerprint(execution),'Recorded processing code unavailable')
    metadata=read(output/'scene_inventory.json');inv=inventory(read(IFI),m['coverage'],read(bounded.BOUNDARIES))
    require(inv==read(output/'candidate_inventory.json'),'Offline inventory changed')
    require(shortlist(inv,5)==[r['event'] for r in metadata['events']],'Non-deterministic selection')
    records=read(output/'evidence.json');require(len(records)==m['records'],'Record count changed')
    require(len({r['event']['ifi_source_event_id'] for r in records})==len(records),'Duplicate events')
    for r in records:
        require(r['evidence_source']=='Sentinel-1' and r['method']==METHOD,'Evidence source/method changed')
        validate_result(r['result']);item=next(i for i in metadata['events'] if i['event']==r['event'])
        require(group_scenes(item['scenes'],r['event'])==r['scene_selection'],'Scene selection changed')
        pair=r['scene_selection']['selected']
        if pair and r['result']['status']!='sentinel1_computation_incomplete':
            ids,names=band_names(pair);plan=plan_window(item['public_geometry'],len(names))
            require(plan==r['plan'] and names==r['bands'],'Grid/workload mismatch')
            full=np.full((len(names),200,200),NODATA,dtype='float32')
            for tile,part in zip(r['tiles'],plan['partitions']):
                require(tile['download']==source.fingerprint(ROOT/tile['file']),'Tile checksum mismatch')
                v=read_tile(ROOT/tile['file'],part,names);x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=v
            require(len(r['tiles'])==4,'Incomplete non-overlapping partition coverage')
            require(analyze(full,names,scope_mask(item['public_geometry'],plan))==r['result'],'Raster evidence not reproducible')
            require(source.fingerprint(ROOT/r['derived_raster']['file'])=={k:r['derived_raster'][k] for k in ['sha256','bytes']},'Derived raster checksum mismatch')
    return {'records':len(records),'statuses':dict(Counter(r['result']['status'] for r in records)),
       'completed_raster_analyses_reproduced':sum('sensitivity' in r['result'] for r in records),
       'raw_checksum_validation':True,'live_requests':0,'binary_labels':0,'computation_complete':m['computation_complete']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['coverage','metadata','extract','validate'])
    p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    RAW=args.raw.resolve();OUTPUT=args.output.resolve()
    if args.operation=='coverage':coverage()
    elif args.operation=='metadata':metadata()
    elif args.operation=='extract':extract()
    else:print(json.dumps(validate(OUTPUT),indent=2))
