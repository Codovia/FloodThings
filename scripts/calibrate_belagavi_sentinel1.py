#!/usr/bin/env python3
"""One official Belagavi 2019 anchor: metadata and continuous SAR only.

No PDF digitization, pixel truth, thresholds, binary labels or rainfall extraction.
All imagery/local geometry stay outside Git. Archived pilots are read-only.
"""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from affine import Affine
from shapely.geometry import box, mapping

sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_sentinel1_pilot as p
import verify_jrc_auxiliary as jrc

RAW=p.ROOT/'data/raw/sentinel1/stage3e3_v1'
OUTPUT=p.ROOT/'data/working/belagavi_2019_sentinel1_calibration_v1'
REFERENCE=p.ROOT/'data/reference/belagavi_2019_sentinel1_calibration_v1'
EVENT='fp-official-belagavi-chikodi-20190809'
STATUSES=frozenset({'calibration_reference_established','sentinel1_pair_available','sentinel1_pair_unavailable',
 'calibration_spatial_reference_insufficient','calibration_analysis_completed','calibration_inconclusive'})
METHOD={'baseline':'median of up to four distinct UTC pre-August6 acquisitions in dB; July1-August5 only',
 'event':'closest to August9 within the Sadalga station August7-14 window; same platform/orbit/pass/IW/VV+VH/10m',
 'grid':'2km square at official approximate CWC Sadalga station coordinate; EPSG:32643,10m,nearest',
 'scope_type':'retrieval_window_not_official_flood_boundary',
 'sar_validity':'finite unmasked SAR VV/VH/angle at every selected scene; independent of JRC/DEM',
 'change':'event minus median baseline dB; continuous VV/VH, never dB ratios',
 'auxiliary':'JRC MonthlyHistory2019_08 and YearlyHistory2019; classes/masks separate; no-data not dry or invalid SAR',
 'permanent_water':'observed yearly class3 only; unknown preserved; seasonal2 retained',
 'terrain':'SRTM~30m/circa2000 surface elevation and degrees slope; percent=100*tan(degrees); context only, no rejection',
 'incidence':'preserve baseline/event/difference,30-45degree and<=1degree count diagnostics only, no threshold classification',
 'radiometric_terrain_flattening':False,'speckle_filter':False,'threshold_analysis':False,
 'spatial_reference':'published unreferenced NRSC map corroborates event/locality only; no pixel-level ground truth'}


def anchor(claims):
    c=deepcopy(claims)
    p.require(not {'manual_flood_polygon','flood_polygon','digitized_pdf_extent','pixel_ground_truth'} & c.keys(),'Manual PDF flood geometry forbidden')
    p.require(c['event_id']==EVENT and c['primary_spatial_calibration_observation_date']=='2019-08-09','Wrong calibration anchor')
    p.require(c['spatial_source']['reviewed_evidence']['observation_date']=='2019-08-09','NRSC observation mismatch')
    p.require(c['spatial_source']['reviewed_evidence']['machine_readable_flood_extent_available'] is False,'This version retains a published map only; new spatial data need separate review')
    windows=c['official_hydrological_event_window']
    p.require(len(windows)==2 and len({r['station'] for r in windows})==2,'Original station windows required')
    expected={'Sadalga':('2019-08-07','2019-08-14'),'Gokak Falls':('2019-08-06','2019-08-12')}
    p.require({r['station']:(r['start'],r['end_inclusive']) for r in windows}==expected,'Original station intervals changed')
    c['derived_contextual_union']={'start':min(r['start'] for r in windows),'end_inclusive':max(r['end_inclusive'] for r in windows),
                                 'type':'project_derived_union_not_original_station_value'}
    p.require(c['official_district_flood_corroboration']['source']['reviewed_evidence']['survey_date']=='2019-08-11','MHA date changed')
    c['machine_readable_reference_status']='calibration_spatial_reference_insufficient'
    return c


def associate_ifi(events):
    """Literal tokens and retained dates only; ambiguous duration never repaired."""
    results=[]
    tokens={'Belagavi','Belgaum','Chikodi','Sadalgi','Sadalga','Gokak'}
    for r in events:
        lo,hi=r.get('parsed_start_date'),r.get('parsed_end_date_inclusive')
        scope=set(t.strip() for t in r['source_districts'].split(','))
        if not (lo and hi and lo<=hi and lo<='2019-08-14' and hi>='2019-08-06' and scope & tokens):continue
        days=(date.fromisoformat(hi)-date.fromisoformat(lo)).days+1
        try: reported=float(r['source_duration_days'])
        except (ValueError,TypeError):reported=None
        status='ambiguous' if reported is not None and reported!=days else 'possible'
        results.append({'ifi_event_id':r['ifi_source_event_id'],'source_row_ordinal':r['source_row_ordinal'],
            'source_start':r['source_start_date'],'source_end':r['source_end_date'],
            'retained_parsed_start':lo,'retained_parsed_end_inclusive':hi,
            'source_district_token':r['source_districts'],'source_lgd_token':r['source_district_lgd_codes'],
            'source_duration_days':r['source_duration_days'],'derived_duration_from_retained_parser':days,
            'association_status':status,'association_basis':'Exact literal district token and interval overlap; multi-district/no-locality association, not spatial identity',
            'date_uncertainty':'Source duration conflicts with parsed dates; no month/day reinterpretation' if status=='ambiguous' else 'Dates retained without anchor substitution'})
    return {'status':'ambiguous' if any(r['association_status']=='ambiguous' for r in results) else ('possible' if results else 'none'),
            'records':sorted(results,key=lambda r:r['ifi_event_id']),'primary_anchor_changed':False}


def plan(claims):
    origin=claims['scope_origin']['reviewed_evidence']
    p.require(origin['site_code']=='CW1KRU000083' and origin['source_name']=='Sadalga','Wrong official location')
    lon,lat=origin['longitude_degrees_east'],origin['latitude_degrees_north']
    # Use existing bounded grid/half-open partition implementation, not a flood polygon.
    result=p.plan_window(mapping(box(lon-.001,lat-.001,lon+.001,lat+.001)),1)
    result.update(scope_type=METHOD['scope_type'],origin_provenance=deepcopy(claims['scope_origin']),
                  administrative_clip=False,interpretation='Approximate named-location retrieval window; may include adjacent Maharashtra; not a district/municipal or inundation boundary')
    return result


def temporal_role(scene,claims):
    day=p.utc_day(scene['properties']['system:time_start'])
    if day=='2019-08-09':return 'exact_nrsc_calibration_date'
    if any(r['start']<=day<=r['end_inclusive'] for r in claims['official_hydrological_event_window']):return 'within_cwc_extreme_flood_window'
    if '2019-08-15'<=day<='2019-08-18':return 'immediately_after_verified_interval'
    return 'unsuitable_temporal_distance'


def groups(scenes,claims):
    pool={};rejected=[]
    for scene in scenes:
        config=p.config(scene);day=p.utc_day(scene['properties']['system:time_start'])
        if not scene['id'].startswith(p.SOURCE+'/') or config[0]!='IW' or config[3]!=10 or not {'VV','VH'}<=set(config[4]) or config[1] not in {'ASCENDING','DESCENDING'} or config[2] is None or config[5] is None:
            rejected.append({'id':scene['id'],'reason':'unsupported_or_missing_configuration'});continue
        if scene['scope_coverage_fraction']<.9999:
            rejected.append({'id':scene['id'],'reason':'incomplete_window_footprint'});continue
        if not '2019-07-01'<=day<='2019-08-18':
            rejected.append({'id':scene['id'],'reason':'outside_bounded_search'});continue
        pool.setdefault(config,[]).append(scene)
    candidates=[]
    for config,rows in pool.items():
        baseline=sorted([r for r in rows if '2019-07-01'<=p.utc_day(r['properties']['system:time_start'])<='2019-08-05'],key=lambda r:(r['properties']['system:time_start'],r['id']))
        unique={r['properties']['system:time_start']:r for r in baseline};baseline=list(unique.values())[-4:]
        for event in rows:
            day=p.utc_day(event['properties']['system:time_start'])
            if day<'2019-08-06':continue
            candidates.append({'configuration':list(config[:-2])+[list(config[-2]),config[-1]],'baseline':baseline,
             'event_scene':event,'temporal_role':temporal_role(event,claims),
             'local_sadalga_station_window': '2019-08-07'<=day<='2019-08-14',
             'days_from_primary_observation':(date.fromisoformat(day)-date(2019,8,9)).days,
             'source_station_intervals_containing_acquisition':[r['station'] for r in claims['official_hydrological_event_window'] if r['start']<=day<=r['end_inclusive']],
             'homogeneous_pair_available':bool(baseline),'platform_compatibility':'Strict same platform; no A/B cross-platform pairing'})
    candidates.sort(key=lambda r:(not r['homogeneous_pair_available'],not r['local_sadalga_station_window'],
        r['temporal_role']!='exact_nrsc_calibration_date',abs(r['days_from_primary_observation']),-len(r['baseline']),r['event_scene']['id']))
    # A later scene remains metadata context, not an authorized event-raster substitute.
    selected=next((r for r in candidates if r['homogeneous_pair_available'] and r['local_sadalga_station_window']),None)
    return {'candidate_acquisitions':candidates,'selected':selected,'rejected':rejected,
            'configuration_groups':len(pool),'pair_status':'sentinel1_pair_available' if selected else 'sentinel1_pair_unavailable'}


def metadata(raw=RAW):
    p.require(not (raw/'metadata.json').exists(),'Completed metadata is immutable')
    claims=anchor(p.read(raw/'official_claims.json'));grid=plan(claims)
    session=p.bounded.TimedEE(raw,60,900);session.initialize();ee=session.ee
    a=grid['transform'];window=ee.Geometry.Rectangle([a[2],a[5]-2000,a[2]+2000,a[5]],proj=p.CRS,geodesic=False)
    coll=ee.ImageCollection(p.SOURCE).filterBounds(window).filterDate('2019-07-01','2019-08-19')
    props=['system:time_start','system:time_end','system:index','instrumentMode','transmitterReceiverPolarisation',
           'orbitProperties_pass','relativeOrbitNumber_start','relativeOrbitNumber_stop','resolution_meters','platform_number','platformHeading','GRD_Post_Processing_software_version']
    def descriptor(obj):
        image=ee.Image(obj)
        return ee.Dictionary({'id':ee.String(p.SOURCE+'/').cat(ee.String(image.get('system:index'))),'returned_id':image.id(),
          'properties':image.toDictionary(props),'footprint':image.geometry(),
          'scope_coverage_fraction':image.geometry().intersection(window,1).area(1).divide(window.area(1)),
          'native_projections':ee.Dictionary({b:ee.Dictionary({'projection':image.select(b).projection(),'nominal_scale_m':image.select(b).projection().nominalScale()}) for b in ['VV','VH','angle']})})
    response=session.request(lambda:ee.Dictionary({'count':coll.size(),'scenes':coll.sort('system:time_start').limit(40).toList(40).map(descriptor)}).getInfo(),'belagavi_scene_metadata')
    p.require(response['count']==len(response['scenes'])<=40,'Scene inventory cap exceeded; no silent truncation')
    grouped=groups(response['scenes'],claims)
    p.source.write_new(raw/'metadata.json',{'retrieved_at':p.source.now(),'search_dates_exclusive_end':['2019-07-01','2019-08-19'],
      'claims':claims,'grid':grid,'response':response,'groups':grouped,'method':METHOD,'ifi_association':associate_ifi(p.read(p.IFI))})
    print(json.dumps({'scenes':response['count'],'groups':grouped['configuration_groups'],'pair_status':grouped['pair_status'],
       'selected_event':grouped['selected']['event_scene']['id'] if grouped['selected'] else None}),flush=True)


def band_names(pair):
    ids=[s['id'] for s in pair['baseline']]+[pair['event_scene']['id']]
    return ids,[f's{i}_{b}' for i in range(len(ids)) for b in ['VV','VH','angle']]+[
       'monthly','monthly_mask','yearly','yearly_mask','elevation','elevation_mask','slope_degrees','slope_mask']


def continuous(values,names):
    p.require(values.shape==(len(names),200,200),'Unexpected continuous grid')
    data=dict(zip(names,values));n=(len(names)-8)//3
    p.require(n>=2 and len(names)==3*n+8,'Missing homogeneous pair')
    valid=jrc.sar_validity(values,names,np.ones((200,200),bool))
    flags=jrc.auxiliary_flags(data['monthly'],data['monthly_mask'],data['yearly'],data['yearly_mask'])
    arrays={}
    for b in ['VV','VH','angle']:
        baseline=np.median(np.stack([data[f's{i}_{b}'] for i in range(n-1)]),axis=0)
        event=data[f's{n-1}_{b}'];change=event-baseline
        arrays.update({f'baseline_{b}':baseline,f'event_{b}':event,f'change_{b}':change})
    arrays['slope_percent']=100*np.tan(np.deg2rad(data['slope_degrees']))
    def count(a):return int((valid & a).sum())
    def stats(a,mask=valid):
        return {'cells':int(mask.sum()),'min':float(a[mask].min()),'max':float(a[mask].max()),'mean':float(a[mask].mean(dtype='float64'))} if mask.any() else {'cells':0,'min':None,'max':None,'mean':None}
    angle=(arrays['baseline_angle']>=30)&(arrays['baseline_angle']<=45)&(arrays['event_angle']>=30)&(arrays['event_angle']<=45)&(np.abs(arrays['change_angle'])<=1)
    yearly=flags['jrc_yearly_water_class'];monthly=flags['jrc_monthly_state']
    terrain=(data['elevation_mask']>0)&(data['slope_mask']>0)&(data['elevation']!=p.NODATA)&(data['slope_degrees']!=p.NODATA)
    result={'sar_valid_cells':int(valid.sum()),'incidence_geometry_comparable_cells':count(angle),
      'monthly_counts':{str(c):count(monthly==c) for c in [-1,0,1,2]},'yearly_counts':{str(c):count(yearly==c) for c in [-1,0,1,2,3]},
      'monthly_data_available_cells':count(flags['jrc_monthly_data_available']),
      'yearly_data_available_cells':count(flags['jrc_yearly_data_available']),
      'auxiliary_unknown_cells':count(~flags['jrc_aux_data_available']),
      'permanent_water_cells_eligible_for_future_exclusion':int(jrc.permanent_water_exclusion(valid,flags).sum()),
      'permanent_water_status_unknown_cells':count(~flags['jrc_permanent_water_status_known']),
      'terrain_available_cells':count(terrain),'continuous_statistics':{k:stats(v) for k,v in arrays.items() if k!='slope_percent'},
      'terrain_statistics':{'elevation_m':stats(data['elevation'],valid&terrain),'slope_percent':stats(arrays['slope_percent'],valid&terrain)},
      'threshold_sensitivity':[],'threshold_analysis_performed':False,'flood_label':None,
      'calibration_status':'calibration_inconclusive','continuous_analysis_status':'calibration_analysis_completed',
      'reason':'No usable independent machine-readable spatial reference; continuous diagnostics only, no thresholds or pixel-level calibration/assessment'}
    return result,arrays,valid,flags


def ensure_no_binary_labels(result):
    p.require(result['calibration_status'] in STATUSES and result['flood_label'] is None,'Binary/final flood label forbidden')
    p.require(not {'flood','label','daily_flood_label','risk','probability'}&set(result),'Binary/risk fields forbidden')
    p.require(result['threshold_analysis_performed'] is False and result['threshold_sensitivity']==[],'No spatial reference: threshold analysis forbidden')


def unavailable_result():
    return {'calibration_status':'calibration_inconclusive','pair_status':'sentinel1_pair_unavailable',
            'spatial_reference_status':'calibration_spatial_reference_insufficient',
            'continuous_analysis_status':'not_performed_pair_unavailable',
            'threshold_analysis_performed':False,'threshold_sensitivity':[],'flood_label':None,
            'reason':'Zero scenes in both UTM and geographic-window metadata queries; no homogeneous pair or raster processing. Official NRSC map supports event/locality but supplies no usable machine-readable inundation reference.'}


def write_products(path,values,names,grid):
    p.require(not path.exists(),'Continuous product immutable')
    result,arrays,valid,flags=continuous(values,names);data=dict(zip(names,values))
    products=[];labels=[]
    for key,a in arrays.items():
        if key=='slope_percent':continue
        products.append(np.where(valid,a,p.NODATA));labels.append(key+'_degrees' if 'angle' in key else key+'_dB')
    for key,mask in [('elevation','elevation_mask'),('slope_degrees','slope_mask')]:
        products.append(np.where(data[mask]>0,data[key],p.NODATA));labels.append(key)
    products.append(np.where(data['slope_mask']>0,arrays['slope_percent'],p.NODATA));labels.append('slope_percent')
    for key in ['jrc_monthly_state','jrc_yearly_water_class']:
        products.append(np.where(flags[key]>=0,flags[key],p.NODATA));labels.append(key)
    for key in ['jrc_permanent_water','jrc_permanent_water_status_known','jrc_monthly_data_available','jrc_yearly_data_available','jrc_aux_data_available']:
        products.append(flags[key].astype('float32'));labels.append(key)
    products.append(valid.astype('float32'));labels.append('sar_valid')
    p.require(len(labels)==20,'Continuous product schema changed')
    with rasterio.open(path,'w',driver='GTiff',width=200,height=200,count=len(labels),dtype='float32',crs=p.CRS,
                       transform=Affine(*grid['transform']),nodata=p.NODATA,compress='deflate') as r:
        r.write(np.array(products,dtype='float32'))
        for i,label in enumerate(labels,1):r.set_band_description(i,label)
    return result


def extract(raw=RAW):
    p.require(not (raw/'diagnostics.json').exists(),'Completed diagnostics immutable')
    metadata=p.read(raw/'metadata.json');pair=metadata['groups']['selected']
    p.require(pair is not None,'No defensible event pair; retain metadata, no raster requests')
    import requests
    p.require(groups(metadata['response']['scenes'],metadata['claims'])==metadata['groups'],'Metadata grouping changed')
    session=p.bounded.TimedEE(raw,60,900);session.initialize();ee=session.ee
    ids,names=band_names(pair);p.require(len(names)<=23,'Raster band cap exceeded')
    images=[]
    for i,asset in enumerate(ids):
        image=ee.Image(asset)
        images.extend(image.select(b).unmask(p.NODATA,sameFootprint=False).rename(f's{i}_{b}').toFloat() for b in ['VV','VH','angle'])
    for asset,band,name in [(jrc.MONTHLY+'/2019_08','water','monthly'),(jrc.YEARLY+'/2019','waterClass','yearly')]:
        value=ee.Image(asset).select(band)
        images.extend([value.unmask(p.NODATA,sameFootprint=False).rename(name).toFloat(),value.mask().unmask(0,sameFootprint=False).rename(name+'_mask').toFloat()])
    dem=ee.Image(p.DEM).select('elevation')
    for value,name in [(dem,'elevation'),(ee.Terrain.slope(dem),'slope_degrees')]:
        mask_name='elevation_mask' if name=='elevation' else 'slope_mask'
        images.extend([value.unmask(p.NODATA,sameFootprint=False).rename(name).toFloat(),value.mask().unmask(0,sameFootprint=False).rename(mask_name).toFloat()])
    image=ee.Image.cat(images);grid=metadata['grid'];full=np.empty((len(names),200,200),dtype='float32')
    with requests.Session() as http:
        for part in grid['partitions']:
            path=raw/f'tile{part["index"]}.tif';sidecar=path.with_suffix('.json')
            params={'crs':p.CRS,'crs_transform':part['crs_transform'],'dimensions':part['dimensions'],'format':'GEO_TIFF','filePerBand':False}
            if sidecar.exists():
                info=p.read(sidecar);fp=p.source.fingerprint(path)
                p.require(info['parameters']==params and info['bands']==names and all(info['download'][k]==fp[k] for k in fp),'Cached source tile changed')
            else:
                p.require(not path.exists(),'Unjournalled raster; explicit recovery required')
                url=session.request(lambda:p.download_url(image,params),f'belagavi_tile_url:{part["index"]}');attempt=[0]
                def fetch():
                    attempt[0]+=1
                    return p.download.download(http,url,path.with_suffix(f'.attempt{attempt[0]}.partial.tif'))
                downloaded=session.request(fetch,f'belagavi_tile_download:{part["index"]}')
                path.with_suffix(f'.attempt{attempt[0]}.partial.tif').rename(path)
                p.read_tile(path,part,names);info={'parameters':params,'bands':names,'download':downloaded}
                p.source.write_new(sidecar,info)
            x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=p.read_tile(path,part,names)
    result=write_products(raw/'continuous_products.tif',full,names,grid);ensure_no_binary_labels(result)
    p.source.write_new(raw/'diagnostics.json',result)
    print(json.dumps(result),flush=True)


def validate(output=OUTPUT):
    manifest=p.read(output/'manifest.json')
    p.require(manifest['method']==METHOD and manifest['code']==p.source.fingerprint(Path(__file__)),'Calibration method/code changed')
    for rel,fp in manifest['inputs'].items():p.require(p.source.fingerprint(p.ROOT/rel)==fp,'Calibration source/input checksum mismatch')
    for rel,fp in manifest['files'].items():p.require(p.source.fingerprint(output/rel)==fp,'Calibration output checksum mismatch')
    metadata=p.read(RAW/'metadata.json');claims=anchor(p.read(RAW/'official_claims.json'))
    p.require(claims==metadata['claims'] and plan(claims)==metadata['grid'],'Anchor/retrieval geometry not reproducible')
    p.require(associate_ifi(p.read(p.IFI))==metadata['ifi_association'],'IFI association changed')
    p.require(groups(metadata['response']['scenes'],claims)==metadata['groups'],'Homogeneous grouping not reproducible')
    pair=metadata['groups']['selected']
    if pair is None:
        result=p.read(output/'event_evidence.json');ensure_no_binary_labels(result)
        p.require(result==unavailable_result(),'Unavailable result was promoted or reinterpreted')
        p.require(metadata['response']=={'count':0,'scenes':[]},'Unreviewed nonempty inventory')
        check=p.read(RAW/'geographic_query_check.json')
        p.require(check['response']['count']==0 and check['comparison']=='matches_empty_utm_query','Projection check discrepancy')
        p.require(not list(RAW.glob('*.tif')),'Imagery generated without a pair')
        return {'event_id':EVENT,'scenes':0,'homogeneous_groups':0,'pair_status':'sentinel1_pair_unavailable',
                'spatial_reference_status':'calibration_spatial_reference_insufficient','calibration_status':'calibration_inconclusive',
                'threshold_analysis_performed':False,'binary_labels':0,'live_requests':0,'source_and_metadata_reproducibility':True}
    ids,names=band_names(pair)
    full=np.empty((len(names),200,200),dtype='float32')
    for part in metadata['grid']['partitions']:
        x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=p.read_tile(RAW/f'tile{part["index"]}.tif',part,names)
    result,arrays,valid,flags=continuous(full,names);ensure_no_binary_labels(result)
    p.require(result==p.read(output/'diagnostics.json')==p.read(RAW/'diagnostics.json'),'Continuous statistics not reproducible')
    with rasterio.open(RAW/'continuous_products.tif') as products:
        p.require(products.crs==rasterio.crs.CRS.from_string(p.CRS) and products.transform.almost_equals(Affine(*metadata['grid']['transform'])),'Continuous product CRS mismatch')
        for name,a in arrays.items():
            if name=='slope_percent':continue
            label=name+'_degrees' if 'angle' in name else name+'_dB'
            p.require(np.array_equal(products.read(products.descriptions.index(label)+1),np.where(valid,a,p.NODATA)),'Continuous product mismatch')
    return {'event_id':EVENT,'scenes':len(metadata['response']['scenes']),'pair_status':metadata['groups']['pair_status'],
      'calibration_status':result['calibration_status'],'sar_valid_cells':result['sar_valid_cells'],
      'threshold_analysis_performed':False,'binary_labels':0,'live_requests':0,'source_and_continuous_reproducibility':True}


def freeze(output=OUTPUT,reference=REFERENCE):
    """Freeze this unavailable-pair checkpoint; publish provenance only, no geometry."""
    p.require(not output.exists() and not reference.exists(),'Completed versions are immutable')
    metadata=p.read(RAW/'metadata.json');claims=anchor(p.read(RAW/'official_claims.json'))
    p.require(metadata['response']=={'count':0,'scenes':[]} and metadata['groups']==groups([],claims),
              'This checkpoint requires the reviewed empty inventory')
    p.require(metadata['claims']==claims and metadata['grid']==plan(claims),'Source geometry/anchor changed')
    p.require(associate_ifi(p.read(p.IFI))==metadata['ifi_association'],'IFI association changed')
    check=p.read(RAW/'geographic_query_check.json')
    p.require(check['response']['count']==0 and check['comparison']=='matches_empty_utm_query','Projection check mismatch')
    p.require(not list(RAW.glob('*.tif')),'Unexpected raster without pair')
    inputs=set(path for base in [RAW,p.ROOT/'data/raw/reference/stage3e3_v1'] for path in base.rglob('*') if path.is_file())
    inputs.update([p.IFI,p.ROOT/claims['public_spatial_layer_access']['source_file'],Path(p.__file__),Path(jrc.__file__)])
    output.mkdir(parents=True)
    for name,value in [('anchor.json',claims),('scene_inventory.json',metadata),('event_evidence.json',unavailable_result())]:
        p.source.write_new(output/name,value)
    manifest={'version':output.name,'event_id':EVENT,'created_at':p.source.now(),'project':'floodpulse',
      'source_collection':p.SOURCE,'method':METHOD,'code':p.source.fingerprint(Path(__file__)),
      'inputs':{str(path.relative_to(p.ROOT)):p.source.fingerprint(path) for path in sorted(inputs)},
      'files':{path.name:p.source.fingerprint(path) for path in sorted(output.iterdir())},
      'publication':'Local source documents/geometry/scene metadata; Git contains only references, checksums and aggregate provenance',
      'attribution':{'sar':'Copernicus Sentinel-1/ESA, Earth Engine catalogue',
                     'official':'NRSC/ISRO; Government of India DoWR/CWC and MHA',
                     'ifi':'Saharia/IIT Delhi HydroSense India Flood Inventory; CC BY-NC 4.0; association derived without source correction'},
      'source_terms':'Original government products redistribution unresolved; retained locally. No imagery or source geometry published.'}
    p.source.write_new(output/'manifest.json',manifest)
    verified=validate(output)
    sources={name:{'url':source['source']['source_url'],'retrieved_at':source['source']['retrieved_at'],
                        'sha256':source['source']['sha256'],'bytes':source['source']['bytes'],'pdf_page':source['pdf_page']}
             for name,source in [('nrsc',claims['spatial_source']),('cwc_windows',claims['hydrological_source']),
                                 ('mha',claims['official_district_flood_corroboration']['source']),('cwc_location',claims['scope_origin'])]}
    permitted={'version':output.name,'event_id':EVENT,'created_at':manifest['created_at'],
       'primary_spatial_calibration_observation_date':'2019-08-09',
       'official_hydrological_event_window':claims['official_hydrological_event_window'],
       'derived_contextual_union':claims['derived_contextual_union'],
       'mha_district_survey_date':'2019-08-11','sources':sources,
       'scope_type':METHOD['scope_type'],'scope_description':'2km square around approximate CWC Sadalga station CW1KRU000083; 2025 station metadata; no administrative or inundation boundary',
       'local_geometry_metadata':{'path':str((output/'scene_inventory.json').relative_to(p.ROOT)),**p.source.fingerprint(output/'scene_inventory.json')},
       'query':{'project':'floodpulse','collection':p.SOURCE,'start':'2019-07-01','end_exclusive':'2019-08-19',
                'deadline_seconds':60,'total_phase_seconds':900,'attempt_limit':3,'backoff_seconds':[2,4],
                'crs_checks':['EPSG:32643','EPSG:4326'],'scene_count':0,'homogeneous_groups':0},
       'public_bhuvan_layer':{'id':claims['public_spatial_layer_access']['source_layer_id'],
          'original_date_label':claims['public_spatial_layer_access']['original_date_label'],
          'capabilities_url':claims['public_spatial_layer_access']['capabilities_attempt']['source_url'],
          'access_result':'HTTP 400; no usable machine-readable inundation reference'},
       'ifi_association':metadata['ifi_association'],'result':unavailable_result(),'validation':verified,
       'local_manifest':{'path':str((output/'manifest.json').relative_to(p.ROOT)),**p.source.fingerprint(output/'manifest.json')},
       'local_outputs':manifest['files'],'method':METHOD,'attribution':manifest['attribution'],
       'publication':manifest['publication'],'source_terms':manifest['source_terms'],
       'evidence_limitations':'Official event/locality supported; no SAR pair or pixel-level spatial calibration reference, no calibration_reference_established status, no daily/binary labels or threshold analysis'}
    reference.mkdir(parents=True)
    p.source.write_new(reference/'manifest.json',permitted)
    return verified


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['metadata','extract','freeze','validate'])
    args=parser.parse_args()
    if args.operation=='metadata':metadata()
    elif args.operation=='extract':extract()
    elif args.operation=='freeze':print(json.dumps(freeze(),indent=2))
    else:print(json.dumps(validate(),indent=2))
