#!/usr/bin/env python3
"""One July2021 official anchor, progressive S1 metadata gate, optional continuous SAR.

No PDF digitization, flood classes, thresholds, rainfall or restricted SOI upload.
Source products and scene footprints stay local; archive validators stay unchanged.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import date,timedelta
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point,Polygon,box,mapping,shape

sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_sentinel1_pilot as p
import verify_jrc_auxiliary as jrc

ROOT=p.ROOT
RAW=ROOT/'data/raw/sentinel1/stage3e4_v1'
SOURCES=ROOT/'data/raw/reference/stage3e4_v1'
OUTPUT=ROOT/'data/working/belagavi_2021_sentinel1_anchor_v1'
REFERENCE=ROOT/'data/reference/belagavi_2021_sentinel1_anchor_v1'
EVENT='fp-official-belagavi-20210726'
START,END='2021-06-15','2021-08-16'  # Exclusive end includes August15.
PAIR_STATUSES={'sentinel1_pair_available','sentinel1_pair_unavailable','sentinel1_coverage_query_inconclusive'}
REFERENCES={'machine_readable_reference_available','official_map_reference_available','locality_only_reference','reference_unavailable'}
METHOD={'source':p.SOURCE,'metadata_search':[START,END],'aoi_sides_m':[2000,25000,90000,180000],
 'scope':'retrieval_window_not_official_flood_boundary','metadata_cap':192,
 'grouping':'same IW, exact VV+VH combination, orbit pass/relative orbit, H/10m, strict same platform',
 'baseline':'up to two distinct pre-July26 acquisitions, latest first, median dB',
 'event':'July26 exact preferred; otherwise July26-28 contextual bracket, then <=7days after July28; near-event is not verified daily flood',
 'timing':'July26 primary WorldView3 observation, July28 separate Resourcesat2A corroboration, July29 listing/issue',
 'continuous':'VV/VH/angle baseline median, event and event-minus-baseline dB; no flood classes or thresholds',
 'sar_validity':'finite original SAR masks/nodata only; independent of JRC and terrain',
 'auxiliary':'JRC MonthlyHistory2021_07 and YearlyHistory2021; masked/class0 unknown, yearly3 permanent only, yearly2 retained',
 'grid':'2km EPSG:32643 10m nearest analysis window, four half-open100x100 partitions; source resolution retained separately',
 'limits':{'request_seconds':60,'phase_seconds':900,'attempts':3,'backoff_seconds':[2,4],
           'maxPixels':300000,'bestEffort':False,'safety_factor':1.25,'target_band_pixels':250000,
           'raster_bytes':1048576,'raster_seconds':30},
 'reference':'official GeoPDF map coverage only; no pixel-level inundation ground truth',
 'threshold_analysis_performed':False,'flood_label':None}


def geospatial_viewports(path):
    """Read only retained ArcMap uncompressed GEO dictionaries; fail closed otherwise.

    GPTS are source-provided latitude/longitude registration points, never drawn
    flood shapes. This deliberately does not implement a general PDF digitizer.
    """
    b=Path(path).read_bytes();p.require(b.startswith(b'%PDF') and len(b)<=20971520,'Invalid/big source PDF')
    objects={int(i):body for i,body in re.findall(rb'(\d+) 0 obj\s*(.*?)endobj',b,re.S)}
    results=[]
    for body in objects.values():
        if not re.search(rb'/Type\s*/Page\b',body) or b'/VP[' not in body:continue
        pattern=rb'/Type/Viewport/BBox\[([^]]+)\]/Name \(([^)]*)\)/Measure (\d+) 0 R'
        for bbox,name,identifier in re.findall(pattern,body):
            measure=objects[int(identifier)]
            p.require(b'/Subtype/GEO' in measure,'Viewport is not a GEO registration')
            points=[float(v) for v in re.search(rb'/GPTS\[([^]]+)\]',measure)[1].split()]
            p.require(len(points)==8 and all(math.isfinite(v) for v in points),'Unsupported geographic registration')
            coordinates=[[points[i+1],points[i]] for i in range(0,8,2)]
            polygon=Polygon(coordinates);p.require(polygon.is_valid and not polygon.is_empty,'Invalid source viewport')
            gcs=objects[int(re.search(rb'/GCS (\d+) 0 R',measure)[1])]
            wkt=re.search(rb'/WKT\((.*?)\)',gcs,re.S)[1].decode('ascii')
            label=name.decode('utf-16') if name.startswith(b'\xfe\xff') else name.decode('ascii')
            results.append({'name':label,'source_measure_object':int(identifier),'bbox_pdf_points':[float(v) for v in bbox.split()],
              'geographic_registration_lon_lat':coordinates,'geographic_bounds':list(polygon.bounds),
              'source_projected_wkt':wkt,'interpretation':'Source-provided map viewport registration, not inundation geometry'})
    p.require(results and sum(v['name']=='Postflood' for v in results)==1,'No unambiguous official postflood viewport')
    return results


def validate_anchor(claims):
    c=deepcopy(claims)
    p.require(c['event_id']==EVENT,'Wrong event')
    p.require(not {'flood_polygon','digitized_pdf_extent','pixel_ground_truth'}&c.keys(),'PDF digitization/reference labels forbidden')
    primary=c['primary'];other=c['corroborating_map']
    p.require(primary['acquisition_date']=='2021-07-26' and primary['sensor']=='WorldView-3','Wrong acquisition/sensor')
    p.require(other['acquisition_date']=='2021-07-28' and other['sensor']=='Resourcesat-2A LISS-III','Wrong separate observation')
    p.require(primary['listing_date']==primary['issue_date']=='2021-07-29','Listing/issue dates changed')
    p.require(c['reference_status']=='official_map_reference_available','This version has GeoPDFs, not inundation labels')
    p.require(c['contextual_observation_bracket']=={'start':'2021-07-26','end_inclusive':'2021-07-28',
              'status':'derived_bracket_between_two_official_observations_not_daily_flood_labels'},'Contextual interval changed')
    return c


def aoi_plan(location):
    p.require(location['type']=='node' and location['id']==2548417075 and location['tags']['name']=='Hulagabali'
              and location['tags']['place']=='village','Wrong public named locality')
    lon,lat=location['lon'],location['lat'];p.require(74<lon<76 and 16<lat<18,'Unexpected locality coordinates')
    forward=Transformer.from_crs(4326,p.CRS,always_xy=True);back=Transformer.from_crs(p.CRS,4326,always_xy=True)
    x,y=forward.transform(lon,lat);rows=[]
    for level,side in enumerate(METHOD['aoi_sides_m'],1):
        corners=[back.transform(x+dx*side/2,y+dy*side/2) for dx,dy in [(-1,-1),(-1,1),(1,1),(1,-1)]]
        polygon=Polygon(corners);bounds=list(polygon.bounds)
        rows.append({'level':level,'side_m':side,'area_m2_projected':side*side,'crs':p.CRS,
          'projected_bounds':[x-side/2,y-side/2,x+side/2,y+side/2],
          'geographic_bounds':bounds,'public_geometry':mapping(polygon),'scope_type':METHOD['scope']})
    return rows


def filter_attrition(scenes):
    iw=[r for r in scenes if r['properties'].get('instrumentMode')=='IW']
    vv=[r for r in iw if 'VV' in r['properties'].get('transmitterReceiverPolarisation',[])]
    vh=[r for r in iw if 'VH' in r['properties'].get('transmitterReceiverPolarisation',[])]
    both=[r for r in vv if 'VH' in r['properties'].get('transmitterReceiverPolarisation',[])]
    return {'unfiltered':len(scenes),'IW':len(iw),'IW_VV':len(vv),'IW_VH':len(vh),'IW_VV_VH':len(both),
      'ascending':sum(r['properties'].get('orbitProperties_pass')=='ASCENDING' for r in both),
      'descending':sum(r['properties'].get('orbitProperties_pass')=='DESCENDING' for r in both),
      'relative_orbits':dict(sorted(Counter(str(r['properties'].get('relativeOrbitNumber_start')) for r in both).items())),
      'platforms':dict(sorted(Counter(str(r['properties'].get('platform_number')) for r in both).items()))}


def normalize_histogram_keys(counts):
    """EE numeric histogram keys may be '63.0'; retain raw response separately."""
    result=deepcopy(counts);hist={}
    for key,value in counts['relative_orbits'].items():
        number=float(key);p.require(math.isfinite(number) and number.is_integer() and 1<=number<=175,'Malformed relative orbit')
        normalized=str(int(number));p.require(normalized not in hist,'Conflicting orbit histogram keys')
        hist[normalized]=value
    result['relative_orbits']=hist
    return result


def role(scene):
    day=p.utc_day(scene['properties']['system:time_start'])
    if day<'2021-07-26':return 'pre_event_baseline'
    if day=='2021-07-26':return 'same_day_as_official_spatial_observation'
    if day<='2021-07-28':return 'during_documented_observation_bracket'
    if day<='2021-08-04':return 'shortly_after_event'
    return 'temporally_unsuitable'


def group_inventory(scenes):
    grouped={};rejected=[]
    for row in sorted(scenes,key=lambda r:r['id']):
        config=p.config(row);day=p.utc_day(row['properties']['system:time_start'])
        props=row['properties'];key=(*config,props.get('resolution'))
        if not START<=day<END:rejected.append({'id':row['id'],'reason':'outside_search_dates'});continue
        grouped.setdefault(key,[]).append(row)
    summaries=[];candidates=[]
    for key,rows in sorted(grouped.items(),key=lambda item:str(item[0])):
        rows=sorted(rows,key=lambda r:(r['properties']['system:time_start'],r['id']))
        eligible=(key[0]=='IW' and key[1] in {'ASCENDING','DESCENDING'} and key[2] is not None and key[3]==10
                  and key[4]==('VH','VV') and key[5] in {'A','B'} and key[6]=='H')
        before=[r for r in rows if role(r)=='pre_event_baseline'];event=[r for r in rows if role(r) in {'same_day_as_official_spatial_observation','during_documented_observation_bracket'}]
        after=[r for r in rows if role(r)=='shortly_after_event']
        summary={'configuration':[list(v) if isinstance(v,tuple) else v for v in key],
          'scene_ids':[r['id'] for r in rows],'acquisition_dates':[p.utc_day(r['properties']['system:time_start']) for r in rows],
          'scenes':len(rows),'pre_event_scenes':len(before),'event_window_scenes':len(event),'shortly_after_scenes':len(after),
          'post_event_scenes':sum(p.utc_day(r['properties']['system:time_start'])>'2021-07-28' for r in rows),
          'diagnostic_configuration_eligible':eligible}
        summaries.append(summary)
        if not eligible:continue
        usable=[r for r in before if r['analysis_window_coverage_fraction']>=.9999]
        # Adjacent same-pass frames are not independent baseline dates.
        baseline=list({p.utc_day(r['properties']['system:time_start']):r for r in usable}.values())[-2:]
        for r in event+after:
            if baseline and r['analysis_window_coverage_fraction']>=.9999:
                candidates.append({'configuration':summary['configuration'],'baseline':baseline,'event_scene':r,'temporal_role':role(r),
                 'days_from_primary_observation':(date.fromisoformat(p.utc_day(r['properties']['system:time_start']))-date(2021,7,26)).days,
                 'incidence_comparability':'Same orbit/pass/platform configuration; pixel angle agreement requires subsequent continuous diagnostic'})
    candidates.sort(key=lambda r:(r['temporal_role']=='shortly_after_event',abs(r['days_from_primary_observation']),-len(r['baseline']),r['event_scene']['id']))
    return {'groups':summaries,'rejected':rejected,'pairs':candidates,'selected':candidates[0] if candidates else None,
            'status':'sentinel1_pair_available' if candidates else 'sentinel1_pair_unavailable',
            'decision_scope':'full planned2km Hulagabali diagnostic window; wider scene intersections are not local pairs'}


def coverage_decision(grouping=None,error=None):
    if error is not None:return 'sentinel1_coverage_query_inconclusive'
    p.require(grouping is not None,'A completed inventory or explicit error is required')
    return grouping['status']


def footprint_relation(scene,plan):
    """Footprint intersection describes scene coverage, never observed floodwater."""
    footprint=shape(scene['footprint']);region=shape(plan['public_geometry'])
    p.require(footprint.is_valid and not footprint.is_empty,'Invalid scene footprint')
    return {'intersects':footprint.intersects(region),'covers':footprint.covers(region),
            'interpretation':'geometric scene footprint only; original pixel masks determine SAR validity'}


def area_fraction(intersection_area,region_area):
    """Both areas must use the same CRS/area convention; never mix UTM and sphere."""
    p.require(region_area>0 and intersection_area>=0,'Invalid area values')
    fraction=intersection_area/region_area
    p.require(fraction<=1.00001,'Inconsistent intersection/reference areas')
    return fraction


def validate_inventory(scenes):
    p.require(len({r['id'] for r in scenes})==len(scenes),'Duplicate scene identities')
    for r in scenes:
        p.require(r['id']==p.SOURCE+'/'+r['properties']['system:index'],'Wrong scene source identity')
        p.require(START<=p.utc_day(r['properties']['system:time_start'])<END,'Unexpected acquisition date')
        p.require(0<=r['analysis_window_coverage_fraction']<=1.00001,'Invalid scene coverage fraction')
        p.require(set(r['aoi_coverage_fractions'])=={'1','2','3','4'} and
                  all(0<=v<=1.00001 for v in r['aoi_coverage_fractions'].values()),'Invalid AOI coverage fractions')
        for level in ['1','2','3','4']:
            fraction=area_fraction(r['aoi_intersection_areas_m2'][level],r['aoi_areas_m2'][level])
            p.require(abs(fraction-r['aoi_coverage_fractions'][level])<1e-8,'Coverage fraction is not reproducible from like-unit areas')


def associate_ifi(events,claims):
    names={'Belagavi','Belgaum','Chikodi','Gokak'}|set(claims['primary']['localities'])|set(claims['corroborating_map']['localities'])
    results=[]
    for row in events:
        a,b=row['parsed_start_date'],row['parsed_end_date_inclusive'];tokens={v.strip() for v in row['source_districts'].split(',')}
        if not (a and b and a<=b and a<='2021-07-28' and b>='2021-07-26' and tokens&names):continue
        duration=(date.fromisoformat(b)-date.fromisoformat(a)).days+1
        try: stated=float(row['source_duration_days'])
        except (ValueError,TypeError):stated=None
        uncertain=stated is not None and stated!=duration
        results.append({'ifi_event_id':row['ifi_source_event_id'],'source_row_ordinal':row['source_row_ordinal'],
           'source_start':row['source_start_date'],'source_end':row['source_end_date'],
           'retained_parsed_start':a,'retained_parsed_end_inclusive':b,'source_district_token':row['source_districts'],
           'source_lgd_token':row['source_district_lgd_codes'],'source_duration_days':row['source_duration_days'],
           'retained_parser_duration_days':duration,'association_status':'ambiguous' if uncertain else 'possible',
           'basis':'Exact literal named district/locality token and overlap with official observation bracket; no forced spatial identity or date repair'})
    return {'status':'ambiguous' if any(r['association_status']=='ambiguous' for r in results) else ('possible' if results else 'none'),
            'records':sorted(results,key=lambda r:r['ifi_event_id']),'primary_anchor_changed':False}


def diagnostic_plan(location,pair):
    ids,names=band_names(pair);p.require(2<=len(ids)<=3,'Only up to2baselines plus one event permitted')
    grid=p.plan_window(mapping(box(location['lon']-.001,location['lat']-.001,location['lon']+.001,location['lat']+.001)),len(names))
    grid.update(safety_factor=1.25,target_band_pixels=250000,scope_type=METHOD['scope'])
    grid['maximum_safe_partition_workload']=math.ceil(grid['per_partition_band_pixels']*1.25)
    p.require(grid['maximum_safe_partition_workload']<=250000<grid['maxPixels'],'Band-aware preflight exceeded; do not increase limits')
    return grid


def band_names(pair):
    ids=[r['id'] for r in pair['baseline']]+[pair['event_scene']['id']]
    return ids,[f's{i}_{b}' for i in range(len(ids)) for b in ['VV','VH','angle']]+['monthly','monthly_mask','yearly','yearly_mask']


def continuous(values,names):
    p.require(values.shape==(len(names),200,200) and (len(names)-4)%3==0,'Unexpected diagnostic layout')
    n=(len(names)-4)//3;p.require(2<=n<=3,'Only one event plus one/two baselines permitted')
    data=dict(zip(names,values));valid=jrc.sar_validity(values,names,np.ones((200,200),bool))
    flags=jrc.auxiliary_flags(data['monthly'],data['monthly_mask'],data['yearly'],data['yearly_mask'])
    products={}
    for band in ['VV','VH','angle']:
        baseline=np.median(np.stack([data[f's{i}_{band}'] for i in range(n-1)]),axis=0);event=data[f's{n-1}_{band}']
        products.update({f'baseline_{band}':baseline,f'event_{band}':event,f'change_{band}':event-baseline})
    def stats(a):
        return {'cells':int(valid.sum()),'min':float(a[valid].min()),'max':float(a[valid].max()),'mean':float(a[valid].mean(dtype='float64'))} if valid.any() else {'cells':0,'min':None,'max':None,'mean':None}
    def count(a):return int((valid&a).sum())
    angle=(products['baseline_angle']>=30)&(products['baseline_angle']<=45)&(products['event_angle']>=30)&(products['event_angle']<=45)&(np.abs(products['change_angle'])<=1)
    result={'sar_valid_cells':int(valid.sum()),'incidence_comparable_cells':count(angle),
      'continuous_statistics':{name:stats(a) for name,a in products.items()},
      'monthly_counts':{str(c):count(flags['jrc_monthly_state']==c) for c in [-1,0,1,2]},
      'yearly_counts':{str(c):count(flags['jrc_yearly_water_class']==c) for c in [-1,0,1,2,3]},
      'permanent_water_cells':count(flags['jrc_permanent_water']),
      'permanent_water_status_unknown_cells':count(~flags['jrc_permanent_water_status_known']),
      'auxiliary_unknown_cells':count(~flags['jrc_aux_data_available']),
      'threshold_analysis_performed':False,'threshold_sensitivity':[],'flood_label':None,
      'status':'continuous_diagnostics_completed_not_flood_verification',
      'interpretation':'Near-event SAR change only; no pixel-level NRSC inundation truth, classification, threshold or accuracy claim'}
    return result,products,valid,flags


def ensure_no_labels(result):
    p.require(result['flood_label'] is None and result['threshold_analysis_performed'] is False
              and result['threshold_sensitivity']==[],'Flood labels/thresholds forbidden')
    p.require(not {'flood','daily_flood_label','binary_label','risk','probability','candidate_cells'}&result.keys(),'Classification/risk fields forbidden')


def write_continuous(path,values,names,grid):
    import rasterio
    from affine import Affine
    p.require(not path.exists(),'Completed continuous product immutable')
    result,products,valid,flags=continuous(values,names);ensure_no_labels(result)
    data=[];labels=[]
    for name,a in products.items():data.append(np.where(valid,a,p.NODATA));labels.append(name+('_degrees' if 'angle' in name else '_dB'))
    for name in ['jrc_monthly_state','jrc_yearly_water_class']:
        data.append(np.where(flags[name]>=0,flags[name],p.NODATA));labels.append(name)
    for name in ['jrc_permanent_water','jrc_permanent_water_status_known','jrc_aux_data_available']:
        data.append(flags[name].astype('float32'));labels.append(name)
    data.append(valid.astype('float32'));labels.append('sar_valid')
    with rasterio.open(path,'w',driver='GTiff',width=200,height=200,count=len(data),dtype='float32',
          crs=p.CRS,transform=Affine(*grid['transform']),nodata=p.NODATA,compress='deflate') as r:
        r.write(np.asarray(data,dtype='float32'))
        for i,name in enumerate(labels,1):r.set_band_description(i,name)
    return result


def extract(raw=RAW):
    p.require(not (raw/'diagnostics.json').exists(),'Completed diagnostics immutable')
    metadata=p.read(raw/'metadata.json');pair=metadata['grouping']['selected']
    p.require(pair is not None and metadata['grouping']['status']=='sentinel1_pair_available','No defensible homogeneous pair')
    p.require(metadata['claims']['reference_status'] in {'official_map_reference_available','machine_readable_reference_available'},'Spatial reference gate fails')
    p.require(metadata['grouping']==group_inventory(metadata['scene_inventory']),'Frozen grouping changed')
    ids,names=band_names(pair);grid=diagnostic_plan(metadata['location'],pair)
    preflight={'grid':grid,'source_ids':ids,'bands':names,'method':METHOD}
    if (raw/'diagnostic_preflight.json').exists():p.require(p.read(raw/'diagnostic_preflight.json')==preflight,'Resume preflight changed')
    else:p.source.write_new(raw/'diagnostic_preflight.json',preflight)
    import requests
    session=p.bounded.TimedEE(raw,60,900);session.initialize();ee=session.ee
    monthly=jrc.MONTHLY+'/2021_07';yearly=jrc.YEARLY+'/2021'
    def projection(asset,band):
        value=ee.Image(asset).select(band)
        return ee.Dictionary({'projection':value.projection(),'nominal_scale_m':value.projection().nominalScale()})
    native_file=raw/'native_source_metadata.json'
    if native_file.exists():native=p.read(native_file)
    else:
        native=session.request(lambda:ee.Dictionary({'sar':ee.Dictionary({asset:ee.Dictionary({band:projection(asset,band) for band in ['VV','VH','angle']}) for asset in ids}),
      'monthly':ee.Dictionary({'id':ee.Image(monthly).id(),'properties':ee.Image(monthly).toDictionary(['year','month']),'band':projection(monthly,'water')}),
      'yearly':ee.Dictionary({'id':ee.Image(yearly).id(),'properties':ee.Image(yearly).toDictionary(['year']),'band':projection(yearly,'waterClass')})}).getInfo(),'selected_source_projections_and_auxiliary_identity')
        p.source.write_new(native_file,native)
    p.require(set(native['sar'])==set(ids),'Cached source identities changed')
    p.require(native['monthly']['properties']=={'year':2021,'month':7} and native['yearly']['properties']=={'year':2021},'Wrong auxiliary dates')
    p.require(jrc.temporal_asset(jrc.MONTHLY,native['monthly']['id'])==monthly and jrc.temporal_asset(jrc.YEARLY,native['yearly']['id'])==yearly,'Auxiliary identity mismatch')
    images=[]
    for i,asset in enumerate(ids):
        image=ee.Image(asset)
        images.extend(image.select(b).unmask(p.NODATA,sameFootprint=False).rename(f's{i}_{b}').toFloat() for b in ['VV','VH','angle'])
    for asset,band,name in [(monthly,'water','monthly'),(yearly,'waterClass','yearly')]:
        value=ee.Image(asset).select(band)
        images.extend([value.unmask(p.NODATA,sameFootprint=False).rename(name).toFloat(),value.mask().unmask(0,sameFootprint=False).rename(name+'_mask').toFloat()])
    image=ee.Image.cat(images);full=np.empty((len(names),200,200),dtype='float32')
    try:
        with requests.Session() as http:
            for part in grid['partitions']:
                path=raw/f'tile{part["index"]}.tif';sidecar=path.with_suffix('.json')
                parameters={'crs':p.CRS,'crs_transform':part['crs_transform'],'dimensions':part['dimensions'],'format':'GEO_TIFF','filePerBand':False}
                if sidecar.exists():
                    cached=p.read(sidecar);p.require(cached['parameters']==parameters and cached['bands']==names and
                      all(cached['download'][k]==v for k,v in p.source.fingerprint(path).items()),'Cached source tile changed')
                    x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=p.read_tile(path,part,names)
                    continue
                p.require(not path.exists(),'Unjournalled source tile; explicit recovery required')
                url=session.request(lambda:p.download_url(image,parameters),f'continuous_tile_url:{part["index"]}');attempt=[0]
                def fetch():
                    attempt[0]+=1
                    return p.download.download(http,url,path.with_suffix(f'.attempt{attempt[0]}.partial.tif'))
                downloaded=session.request(fetch,f'continuous_tile_download:{part["index"]}')
                path.with_suffix(f'.attempt{attempt[0]}.partial.tif').rename(path)
                x0,x1,y0,y1=part['window'];full[:,y0:y1,x0:x1]=p.read_tile(path,part,names)
                p.source.write_new(sidecar,{'parameters':parameters,'bands':names,'download':downloaded})
        result=write_continuous(raw/'continuous_products.tif',full,names,grid)
        p.source.write_new(raw/'diagnostics.json',result);print(json.dumps(result),flush=True)
    except Exception as error:
        p.source.write_new(raw/f'diagnostic_failure_{len(list(raw.glob("diagnostic_failure_*.json")))}.json',{'status':'continuous_diagnostics_incomplete','error':p.source.provider_error(error),'retrieved_at':p.source.now()})
        raise


def assemble_metadata(raw=RAW):
    claims=validate_anchor(p.read(SOURCES/'official_claims.json'));location=p.read(SOURCES/'hulagabali_osm.json')['elements'][0]
    plans=aoi_plan(location);checkpoints=[p.read(raw/f'aoi{level}.json') for level in range(1,5)]
    for plan,record in zip(plans,checkpoints):p.require(record['plan']==json.loads(json.dumps(plan)),'Cached AOI plan changed')
    inventory=p.read(raw/'scene_inventory_response.json');counts=p.read(raw/'filter_attrition_response.json')
    p.require(len(inventory)==counts['unfiltered']==checkpoints[-1]['response']['count'],'Truncated/inconsistent scene inventory')
    validate_inventory(inventory)
    for row in inventory:
        row['acquisition_utc']=p.datetime.fromtimestamp(row['properties']['system:time_start']/1000,p.timezone.utc).isoformat()
        row['local_aoi_footprint_relation']=footprint_relation(row,plans[0])
    normalized=normalize_histogram_keys(counts)
    p.require(filter_attrition(inventory)==normalized,'Offline filter counts do not match live incremental filters')
    base=p.plan_window(mapping(box(location['lon']-.001,location['lat']-.001,location['lon']+.001,location['lat']+.001)),1)
    return {'event_id':EVENT,'claims':claims,'location':location,'analysis_grid':base,'aois':checkpoints,'scene_inventory':inventory,
            'filter_attrition':counts,'filter_attrition_normalized':normalized,'grouping':group_inventory(inventory),
            'ifi_association':associate_ifi(p.read(p.IFI),claims),'method':METHOD,
            'retrieved_at':p.source.now(),'project':'floodpulse'}


def metadata(raw=RAW):
    p.require(not (raw/'metadata.json').exists(),'Completed metadata immutable')
    raw.mkdir(parents=True,exist_ok=True);claims=validate_anchor(p.read(SOURCES/'official_claims.json'))
    location=p.read(SOURCES/'hulagabali_osm.json')['elements'][0];plans=aoi_plan(location)
    if all((raw/name).exists() for name in [*[f'aoi{i}.json' for i in range(1,5)],'filter_attrition_response.json','scene_inventory_response.json']):
        result=assemble_metadata(raw);p.source.write_new(raw/'metadata.json',result)
        print(json.dumps({'resume':'completed entirely offline','pair_status':result['grouping']['status'],'groups':len(result['grouping']['groups'])}),flush=True)
        return
    # Actual retrieval grid is snapped; count/intersection against this exact grid.
    base=p.plan_window(mapping(box(location['lon']-.001,location['lat']-.001,location['lon']+.001,location['lat']+.001)),1)
    a=base['transform'];session=p.bounded.TimedEE(raw,60,900);session.initialize();ee=session.ee
    analysis=ee.Geometry.Rectangle([a[2],a[5]-2000,a[2]+2000,a[5]],proj=p.CRS,geodesic=False)
    checkpoints=[]
    try:
        for plan in plans:
            cache=raw/f'aoi{plan["level"]}.json'
            if cache.exists():record=p.read(cache);p.require(record['plan']==json.loads(json.dumps(plan)),'Cached AOI plan changed')
            else:
                geometry=ee.Geometry.Rectangle(plan['projected_bounds'],proj=p.CRS,geodesic=False)
                coll=ee.ImageCollection(p.SOURCE).filterBounds(geometry).filterDate(START,END)
                response=session.request(lambda:ee.Dictionary({'count':coll.size(),'earliest_ms':coll.aggregate_min('system:time_start'),
                   'latest_ms':coll.aggregate_max('system:time_start'),'area_m2_ee':geometry.area(1)}).getInfo(),f'availability_aoi{plan["level"]}')
                record={'plan':plan,'response':response,'retrieved_at':p.source.now(),'filters':['filterBounds','filterDate']}
                p.source.write_new(cache,record)
            checkpoints.append(record);print(json.dumps({'aoi':plan['level'],**record['response']}),flush=True)
        outer=ee.Geometry.Rectangle(plans[-1]['projected_bounds'],proj=p.CRS,geodesic=False)
        coll=ee.ImageCollection(p.SOURCE).filterBounds(outer).filterDate(START,END)
        iw=coll.filter(ee.Filter.eq('instrumentMode','IW'));vv=iw.filter(ee.Filter.listContains('transmitterReceiverPolarisation','VV'))
        vh=iw.filter(ee.Filter.listContains('transmitterReceiverPolarisation','VH'));both=vv.filter(ee.Filter.listContains('transmitterReceiverPolarisation','VH'))
        count_file=raw/'filter_attrition_response.json'
        if count_file.exists():counts=p.read(count_file)
        else:
            counts=session.request(lambda:ee.Dictionary({'unfiltered':coll.size(),'IW':iw.size(),'IW_VV':vv.size(),'IW_VH':vh.size(),'IW_VV_VH':both.size(),
          'ascending':both.filter(ee.Filter.eq('orbitProperties_pass','ASCENDING')).size(),
          'descending':both.filter(ee.Filter.eq('orbitProperties_pass','DESCENDING')).size(),
          'relative_orbits':both.aggregate_histogram('relativeOrbitNumber_start'),'platforms':both.aggregate_histogram('platform_number')}).getInfo(),'incremental_filter_attrition')
            p.source.write_new(count_file,counts)
        p.require(checkpoints[-1]['response']['count']<=192,'Inventory exceeds metadata cap; coverage decision inconclusive')
        props=['system:index','system:time_start','system:time_end','instrumentMode','transmitterReceiverPolarisation','orbitProperties_pass',
               'relativeOrbitNumber_start','relativeOrbitNumber_stop','orbitNumber_start','platform_number','resolution','resolution_meters']
        def descriptor(obj):
            image=ee.Image(obj);geometry=image.geometry()
            return ee.Dictionary({'id':ee.String(p.SOURCE+'/').cat(ee.String(image.get('system:index'))),'properties':image.toDictionary(props),
              'footprint':geometry,'analysis_window_coverage_fraction':geometry.intersection(analysis,1).area(1).divide(analysis.area(1)),
              'aoi_intersection_areas_m2':ee.Dictionary({str(plan['level']):geometry.intersection(ee.Geometry.Rectangle(plan['projected_bounds'],proj=p.CRS,geodesic=False),1).area(1) for plan in plans}),
              'aoi_areas_m2':ee.Dictionary({str(plan['level']):ee.Geometry.Rectangle(plan['projected_bounds'],proj=p.CRS,geodesic=False).area(1) for plan in plans}),
              'aoi_coverage_fractions':ee.Dictionary({str(plan['level']):geometry.intersection(ee.Geometry.Rectangle(plan['projected_bounds'],proj=p.CRS,geodesic=False),1).area(1).divide(ee.Geometry.Rectangle(plan['projected_bounds'],proj=p.CRS,geodesic=False).area(1)) for plan in plans})})
        inventory_file=raw/'scene_inventory_response.json'
        if inventory_file.exists():inventory=p.read(inventory_file)
        else:
            inventory=session.request(lambda:coll.sort('system:time_start').limit(192).toList(192).map(descriptor).getInfo(),'full_unfiltered_scene_inventory')
            p.source.write_new(inventory_file,inventory)
        result=assemble_metadata(raw);grouping=result['grouping']
        p.source.write_new(raw/'metadata.json',result)
        print(json.dumps({'filter_attrition':counts,'pair_status':grouping['status'],'groups':len(grouping['groups']),
            'selected':grouping['selected']['event_scene']['id'] if grouping['selected'] else None}),flush=True)
    except Exception as error:
        p.source.write_new(raw/f'coverage_failure_{len(list(raw.glob("coverage_failure_*.json")))}.json',
              {'status':'sentinel1_coverage_query_inconclusive','error':p.source.provider_error(error),'retrieved_at':p.source.now(),'completed_aoi_levels':len(checkpoints)})
        raise


def retained_values(raw=RAW):
    preflight=p.read(raw/'diagnostic_preflight.json');grid=preflight['grid'];names=preflight['bands']
    values=np.empty((len(names),200,200),dtype='float32')
    for part in grid['partitions']:
        path=raw/f'tile{part["index"]}.tif';record=p.read(path.with_suffix('.json'))
        p.require(record['bands']==names and all(record['download'][k]==v for k,v in p.source.fingerprint(path).items()),'Retained source tile checksum mismatch')
        x0,x1,y0,y1=part['window'];values[:,y0:y1,x0:x1]=p.read_tile(path,part,names)
    return values,names,grid


def independent_checks(values,names):
    """Scalar medians/changes/math.fsum on every valid cell; no flood assessment."""
    import statistics
    result,products,valid,flags=continuous(values,names);data=dict(zip(names,values));n=(len(names)-4)//3
    scalar={}
    for band in ['VV','VH','angle']:
        samples=[data[f's{i}_{band}'][valid].tolist() for i in range(n)]
        baseline=[float(np.float32(statistics.median(v))) for v in zip(*samples[:-1])]
        event=samples[-1];change=[float(np.float32(b-a)) for a,b in zip(baseline,event)]
        for name,row in [(f'baseline_{band}',baseline),(f'event_{band}',event),(f'change_{band}',change)]:
            expected=result['continuous_statistics'][name]
            p.require(np.array_equal(np.array(row,dtype='float32'),products[name][valid]),'Independent scalar median/change mismatch')
            mean=math.fsum(row)/len(row) if row else None
            p.require(mean is None or math.isclose(mean,expected['mean'],rel_tol=1e-12,abs_tol=1e-12),'Independent scalar mean mismatch')
            scalar[name]={'cells':len(row),'scalar_mean':mean}
    difference=np.abs(products['change_angle'])<=1
    original_range=(products['baseline_angle']>=30)&(products['baseline_angle']<=45)&(products['event_angle']>=30)&(products['event_angle']<=45)
    return {'all_valid_cells_checked':int(valid.sum()),'scalar_statistics':scalar,
       'angle_difference_within_predeclared_one_degree_cells':int((valid&difference).sum()),
       'within_legacy_30_45_degree_range_cells':int((valid&original_range).sum()),
       'outside_legacy_30_45_degree_range_cells':int((valid&~original_range).sum()),
       'incidence_comparable_cells_definition':'Original diagnostics field intersects both30-45degree range and<=1degree difference; zero is not zero SAR validity or zero angle agreement',
       'thresholds_changed':False}


def validate(output=OUTPUT):
    import rasterio
    from affine import Affine
    manifest=p.read(output/'manifest.json')
    p.require(manifest['method']==METHOD,'Frozen method changed')
    for name,fp in manifest['code'].items():p.require(p.source.fingerprint(ROOT/name)==fp,'Processing dependency changed')
    for name,fp in manifest['inputs'].items():p.require(p.source.fingerprint(ROOT/name)==fp,'Source/input checksum mismatch')
    for name,fp in manifest['files'].items():p.require(p.source.fingerprint(output/name)==fp,'Output checksum mismatch')
    md=p.read(RAW/'metadata.json');reproduced=assemble_metadata(RAW);reproduced['retrieved_at']=md['retrieved_at']
    p.require(md==reproduced,'Metadata grouping/filter/IFI/AOI reconstruction differs')
    for product in [md['claims']['primary'],md['claims']['corroborating_map']]:
        p.require(geospatial_viewports(ROOT/product['source_file'])==product['viewports'],'GeoPDF registration mismatch')
    a=md['analysis_grid']['transform'];transform=Transformer.from_crs(p.CRS,4326,always_xy=True)
    window=Polygon([transform.transform(x,y) for x,y in [(a[2],a[5]),(a[2]+2000,a[5]),(a[2]+2000,a[5]-2000),(a[2],a[5]-2000)]])
    viewport=next(v for v in md['claims']['primary']['viewports'] if v['name']=='Postflood')
    p.require(Polygon(viewport['geographic_registration_lon_lat']).covers(window),'Diagnostic window is outside official map coverage')
    p.require(manifest['pair_status']==coverage_decision(md['grouping']) and
              manifest['reference_status']==md['claims']['reference_status'],'Evidence status changed')
    values,names,grid=retained_values();p.require(grid==diagnostic_plan(md['location'],md['grouping']['selected']),'Workload preflight changed')
    result,products,valid,flags=continuous(values,names);ensure_no_labels(result)
    p.require(result==p.read(RAW/'diagnostics.json')==p.read(output/'continuous_diagnostics.json'),'Continuous diagnostics mismatch')
    checks=independent_checks(values,names);p.require(checks==p.read(output/'independent_checks.json'),'Scalar checks mismatch')
    with rasterio.open(RAW/'continuous_products.tif') as raster:
        p.require(str(raster.crs)==p.CRS and raster.transform.almost_equals(Affine(*grid['transform'])) and
                  raster.count==15 and raster.width==raster.height==200 and raster.nodata==p.NODATA,'Derived raster georeferencing/schema mismatch')
        for name,array in products.items():
            label=name+('_degrees' if 'angle' in name else '_dB')
            p.require(np.array_equal(raster.read(raster.descriptions.index(label)+1),np.where(valid,array,p.NODATA)),'Derived SAR values/masks mismatch')
        for name in ['jrc_monthly_state','jrc_yearly_water_class']:
            p.require(np.array_equal(raster.read(raster.descriptions.index(name)+1),np.where(flags[name]>=0,flags[name],p.NODATA)),'Auxiliary classes/masks mismatch')
        for name in ['jrc_permanent_water','jrc_permanent_water_status_known','jrc_aux_data_available']:
            p.require(np.array_equal(raster.read(raster.descriptions.index(name)+1),flags[name].astype('float32')),'Auxiliary flag mismatch')
        p.require(np.array_equal(raster.read(raster.descriptions.index('sar_valid')+1),valid.astype('float32')),'SAR mask mismatch')
    return {'event_id':EVENT,'aoi_scene_counts':[r['response']['count'] for r in md['aois']],
            'scene_inventory_count':len(md['scene_inventory']),'homogeneous_groups':len(md['grouping']['groups']),
            'pair_status':manifest['pair_status'],'reference_status':manifest['reference_status'],'sar_valid_cells':result['sar_valid_cells'],
            'independent_cells_checked':checks['all_valid_cells_checked'],'thresholds_or_binary_labels':0,'live_requests':0,'source_and_pixel_reproducibility':True}


def freeze(output=OUTPUT,reference=REFERENCE):
    p.require(not output.exists() and not reference.exists(),'Completed output/reference versions are immutable')
    md=p.read(RAW/'metadata.json');p.require(md['grouping']['status']=='sentinel1_pair_available','Pair gate fails')
    values,names,grid=retained_values();result=continuous(values,names)[0];ensure_no_labels(result)
    p.require(result==p.read(RAW/'diagnostics.json'),'Diagnostics not reproducible before freeze')
    output.mkdir(parents=True)
    for name,value in [('anchor.json',md['claims']),('scene_inventory.json',md),('continuous_diagnostics.json',result),
                       ('independent_checks.json',independent_checks(values,names))]:p.source.write_new(output/name,value)
    paths=set(path for base in [RAW,SOURCES] for path in base.rglob('*') if path.is_file())
    paths.update([p.IFI,ROOT/'data/raw/reference/stage3e2_v1/bhuvan.html'])
    code={str(path.relative_to(ROOT)):p.source.fingerprint(path) for path in [Path(__file__),Path(p.__file__),Path(jrc.__file__)]}
    manifest={'version':output.name,'created_at':p.source.now(),'event_id':EVENT,'method':METHOD,'code':code,
      'pair_status':md['grouping']['status'],'reference_status':md['claims']['reference_status'],
      'inputs':{str(path.relative_to(ROOT)):p.source.fingerprint(path) for path in sorted(paths)},
      'files':{path.name:p.source.fingerprint(path) for path in sorted(output.iterdir())},
      'attribution':{'official':'Source: NRSC, ISRO/DOS; https://www.nrsc.gov.in; products retained locally',
         'sar':'Copernicus Sentinel-1/ESA, Earth Engine calibrated/terrain-corrected sigma0 dB',
         'jrc':'EC JRC/Google/Pekel et al.2016; 2021 MonthlyHistory/YearlyHistory auxiliary context sampled to SAR grid',
         'coordinates':'OpenStreetMap contributors, ODbL1.0; named-place node only',
         'ifi':'Saharia/IIT Delhi HydroSense India Flood Inventory, CC BY-NC4.0; no forced match'},
      'publication':'Original maps/imagery/source footprints/raw rasters stay local; source metadata/checksums and aggregate provenance only'}
    p.source.write_new(output/'manifest.json',manifest);verified=validate(output)
    sources={name:{key:product[key] for key in ['title','acquisition_date','sensor','listing_date','issue_date',
             'pdf_creation_timestamp','analysis_date','map_id','disaster_event_id','localities','spatial_resolution','limitations','provenance']}
             for name,product in [('primary',md['claims']['primary']),('corroborating_map',md['claims']['corroborating_map'])]}
    pair=md['grouping']['selected']
    permitted={'version':output.name,'event_id':EVENT,'created_at':manifest['created_at'],'sources':sources,
      'source_listing':md['claims']['listing_source'],'terms':md['claims']['terms_source'],'source_reuse':md['claims']['reuse'],
      'reference_status':manifest['reference_status'],'spatial_evidence_type':'official_georeferenced_map_only',
      'map_coverage':'Source GeoPDF registration retained locally; not a categorical flood layer',
      'documented_period_literal':md['claims']['documented_period_literal'],'contextual_observation_bracket':md['claims']['contextual_observation_bracket'],
      'ifi_association':md['ifi_association'],'aois':[{key:r['plan'][key] for key in ['level','side_m','area_m2_projected','crs','geographic_bounds','scope_type']}|{'response':r['response'],'retrieved_at':r['retrieved_at']} for r in md['aois']],
      'filter_attrition_original':md['filter_attrition'],'filter_attrition_normalized':md['filter_attrition_normalized'],
      'group_summaries':[{key:g[key] for key in ['configuration','scenes','acquisition_dates','pre_event_scenes','event_window_scenes','shortly_after_scenes','post_event_scenes']} for g in md['grouping']['groups']],
      'pair_status':manifest['pair_status'],'selected':{'configuration':pair['configuration'],'baseline_ids':[r['id'] for r in pair['baseline']],
         'event_id':pair['event_scene']['id'],'event_utc':pair['event_scene']['acquisition_utc'],'temporal_role':pair['temporal_role'],
         'days_from_primary_observation':pair['days_from_primary_observation']},
      'continuous_diagnostic_summary':result,'independent_check_summary':p.read(output/'independent_checks.json'),
      'validation':verified,'preflight':{'bands':len(names),'partitions':grid['partition_count'],'maximum_safe_band_workload':grid['maximum_safe_partition_workload'],'maxPixels':grid['maxPixels'],'bestEffort':False},
      'local_manifest':{'path':str((output/'manifest.json').relative_to(ROOT)),**p.source.fingerprint(output/'manifest.json')},
      'local_outputs':manifest['files'],'method':METHOD,'code':code,'attribution':manifest['attribution'],'publication':manifest['publication'],
      'calibration_status':'calibration_inconclusive','scientific_limitations':['Near-event July29 is not July26/28 pixel truth',
        'No machine-readable independent inundation labels','All angles outside old30-45degree range; cutoff not relaxed',
        'Continuous backscatter change is not a verified flood-positive count or classification']}
    reference.mkdir(parents=True);p.source.write_new(reference/'manifest.json',permitted)
    return verified


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['metadata','extract','freeze','validate']);args=parser.parse_args()
    if args.operation=='metadata':metadata()
    elif args.operation=='extract':extract()
    elif args.operation=='freeze':print(json.dumps(freeze(),indent=2))
    else:print(json.dumps(validate(),indent=2))
