#!/usr/bin/env python3
"""Four fixed positive scopes, native CHIRPS rainfall, strict pre-GFD anchors.

Retrospective exploratory context only. No flood-day/negative labels, weighting,
model, SOI transmission or public detailed-table delivery. Rainy-day counts omitted.
"""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from affine import Affine
from shapely import contains_xy
from shapely.geometry import Point, shape

sys.path.insert(0,str(Path(__file__).resolve().parent))
import extract_karnataka_rainfall as rain
import expand_karnataka_satellite as satellite
import extract_udupi_history as history

ROOT=rain.ROOT
OUTPUT=ROOT/'data/working/karnataka_positive_event_rainfall_v1'
RAW=ROOT/'data/raw/chirps/positive_events_v1'
COUNTS={2728:33,3551:23,3652:2,2758:329}
LENGTHS=(1,3,7,14,30)
ANTECEDENT='prediction_time_antecedent_rainfall'
DESCRIPTIVE='DESCRIPTIVE_ONLY_NOT_PREDICTION_FEATURE'
METHOD='Unweighted mean/min/max of valid native CHIRPS cell centres strictly inside retained local WGS84 polygons; planar coordinate membership, boundary centres excluded, no area weighting/resampling/centroid substitution.'
DAILY_FIELDS=['gfd_id','scope_id','scope_name','rainfall_date','relationship','days_relative_to_gfd_start','use_class',
 'regional_mean_mm_per_day','regional_min_mm_per_day','regional_max_mm_per_day','valid_cell_count','candidate_cell_count',
 'valid_coverage_percent','status','units','source_image_id','source_raster_sha256','source_raster_file','retrieved_at']
ANTECEDENT_FIELDS=['gfd_id','scope_id','gfd_start','last_allowed_date','use_class','status',
 *[f'rain_{n}d_mm' for n in LENGTHS],'max_daily_previous_7d_mm','max_daily_previous_14d_mm']
DESCRIPTIVE_FIELDS=['gfd_id','scope_id','gfd_start','gfd_end_inclusive','use_class','status','event_window_total_mm',
 'event_window_daily_mean_mm','event_window_max_daily_mm']


def read(path):return json.loads(Path(path).read_text())


def days(start,end):
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    rain.require(a<=b,'Reversed context window')
    return [(a+timedelta(days=i)).isoformat() for i in range((b-a).days+1)]


def dates(anchor):
    return days((date.fromisoformat(anchor['gfd_start'])-timedelta(days=30)).isoformat(),anchor['gfd_end_inclusive'])


def load_anchors():
    """Read-only verified evidence; no source-date substitutions or new links."""
    spatial=ROOT/'data/processed/udupi_flood_spatial_v1'
    historical=ROOT/'data/processed/udupi_historical_v1'
    first=ROOT/'data/working/karnataka_satellite_event_evidence_v2'
    second=ROOT/'data/working/karnataka_satellite_event_evidence_v4'
    satellite.prior_gate(first);satellite.validate(second)
    history.validate_version(historical)
    prior=read(ROOT/'data/working/karnataka_flood_events_v1/manifest.json')['existing_independent_satellite_evidence']
    ifi=read(ROOT/'data/working/karnataka_flood_events_v1/events.json')
    by_source={r['ifi_source_event_id']:r for r in ifi}
    with (historical/'event_evidence.csv').open() as handle:udupi={int(r['event_id']):r for r in csv.DictReader(handle)}
    results=[]
    for event in read(spatial/'manifest.json')['events']:
        eid=event['event_id'];old=udupi[eid]
        rain.require(event['qualified_pixel_count']==COUNTS[eid] and int(old['positive_observed_pixels'])==COUNTS[eid],
                     'Protected Udupi count changed')
        item=next(r for r in prior if int(r['original_satellite_source_values']['event_id'])==eid)
        overlaps=[{'ifi_source_event_id':identity,'ifi_start':by_source[identity]['parsed_start_date'],
                   'ifi_end_inclusive':by_source[identity]['parsed_end_date_inclusive'],
                   'status':'documentary_overlap_for_review_only_not_confirmed'} for identity in item['overlapping_ifi_ids_for_review_only']]
        boundary=read(spatial/'udupi_boundary.geojson')
        results.append({'gfd_id':eid,'image_id':event['image_id'],'gfd_start':event['start_date'],
         'gfd_end_inclusive':event['end_date_inclusive'],'scope_id':old['boundary_id'],'scope_name':'Udupi',
         'geometry':boundary['geometry'],'geometry_origin':str(spatial/'udupi_boundary.geojson'),
         'qualifying_floodwater_cells':COUNTS[eid],'valid_gfd_observation_cells':int(old['valid_observed_pixels']),
         'observation_status':'satellite_positive','original_observation_status':old['finding'],
         'ifi_association_status':item['association_status'],'ifi_associations':overlaps})
    for directory,eid in [(first,3652),(second,2758)]:
        event=next(r for r in read(directory/'event_evidence.json') if r['gfd_id']==eid)
        rain.require(event['evidence_status']=='satellite_positive' and event['statistics']['qualifying_pixels']==COUNTS[eid],
                     'Protected positive satellite count changed')
        results.append({'gfd_id':eid,'image_id':event['image_id'],'gfd_start':event['gfd_start'],
         'gfd_end_inclusive':event['gfd_end_inclusive'],'scope_id':event['review_region']['shapeID'],
         'scope_name':event['review_region']['shapeName'],'geometry':event['preflight']['region']['geometry'],
         'geometry_origin':str(directory/'event_evidence.json')+'#/preflight/region/geometry',
         'qualifying_floodwater_cells':event['statistics']['qualifying_pixels'],
         'valid_gfd_observation_cells':event['statistics']['valid_pixels'],'observation_status':event['evidence_status'],
         'original_observation_status':event['evidence_status'],'ifi_association_status':event['association_status'],
         'ifi_associations':[{'ifi_source_event_id':event['ifi_source_event_id'],'ifi_start':event['ifi_start'],
          'ifi_end_inclusive':event['ifi_end_inclusive'],'status':event['association_status']}]})
    rain.require({r['gfd_id'] for r in results}==set(COUNTS),'Positive scope identity changed')
    for a in results:
        rain.require(a['image_id']==history.event_asset(a['gfd_id'],a['gfd_start'],a['gfd_end_inclusive']),
                     'GFD image dates differ from anchor')
        g=shape(a['geometry'])
        rain.require(g.geom_type in {'Polygon','MultiPolygon'} and g.is_valid and not g.is_empty,'Missing or invalid retained geometry')
        a.update(anchor_rule='GFD_start',geometry_source=satellite.source.BOUNDARY,
                 geometry_crs='EPSG:4326',geometry_vintage='geoBoundaries v6.0.0 (2023 composite), not historical boundaries',
                 geometry_sha256=hashlib.sha256(satellite.source.packed(a['geometry'])).hexdigest())
    return sorted(results,key=lambda a:a['gfd_id'])


def parameters(geometry):
    g=shape(geometry);rain.require(g.is_valid and not g.is_empty,'Invalid local review geometry')
    west,south,east,north=g.bounds
    rain.require(73.5<=west<east<=79 and 11<=south<north<=19,'Scope outside bounded Karnataka window')
    native=Affine(*rain.GRID)
    c0,r0=~native @ (west,north);c1,r1=~native @ (east,south)
    c0,r0,c1,r1=math.floor(c0),math.floor(r0),math.ceil(c1),math.ceil(r1)
    rain.require(0<(c1-c0)*(r1-r0)<=4096,'Envelope exceeds 4096 native cells')
    crop=native @ Affine.translation(c0,r0)
    return {'crs':'EPSG:4326','crs_transform':list(crop)[:6],'dimensions':[c1-c0,r1-r0],
            'format':'GEO_TIFF','bands':['precipitation','valid_mask'],'filePerBand':False}


def membership(geometry,params):
    width,height=params['dimensions'];rows,cols=np.indices((height,width))
    x,y=Affine(*params['crs_transform']) @ (cols+.5,rows+.5)
    mask=contains_xy(shape(geometry),x,y)
    rain.require(mask.any(),'Scope contains no native CHIRPS cell centres')
    return mask,(x,y)


def summarize(anchor,day,values,valid,mask,record):
    relative=(date.fromisoformat(day)-date.fromisoformat(anchor['gfd_start'])).days
    rain.require(day in dates(anchor),'Rainfall date outside exact authorized context window')
    observed=values[mask & valid].astype(np.float64);n,total=int(observed.size),int(mask.sum())
    return {'gfd_id':anchor['gfd_id'],'scope_id':anchor['scope_id'],'scope_name':anchor['scope_name'],
     'rainfall_date':day,'relationship':'antecedent' if relative<0 else 'event_window','days_relative_to_gfd_start':relative,
     'use_class':ANTECEDENT if relative<0 else DESCRIPTIVE,
     'regional_mean_mm_per_day':float(observed.mean()) if n else None,
     'regional_min_mm_per_day':float(observed.min()) if n else None,
     'regional_max_mm_per_day':float(observed.max()) if n else None,'valid_cell_count':n,'candidate_cell_count':total,
     'valid_coverage_percent':100*n/total if total else None,'status':'available' if n==total else 'partial_spatial_coverage' if n else 'no_valid_pixels',
     'units':'mm/day','source_image_id':record['source_image_id'],'source_raster_sha256':record['download']['sha256'],
     'source_raster_file':record['file'],'retrieved_at':record['download']['retrieved_at']}


def validate_daily(rows,anchors,allow_partial=False):
    by_id={a['gfd_id']:a for a in anchors};seen=set()
    for r in rows:
        rain.require(set(r)==set(DAILY_FIELDS),'Unexpected daily fields: flood labels are forbidden')
        key=(r['gfd_id'],r['rainfall_date']);rain.require(key not in seen,'Duplicate event/date');seen.add(key)
        rain.require(r['gfd_id'] in by_id,'Non-positive/control event forbidden')
        a=by_id[r['gfd_id']];delta=(date.fromisoformat(r['rainfall_date'])-date.fromisoformat(a['gfd_start'])).days
        rain.require(r['rainfall_date'] in dates(a),'Future/out-of-window rainfall date')
        rain.require(r['scope_id']==a['scope_id'] and r['scope_name']==a['scope_name'],'Rainfall geography changed')
        rain.require(r['relationship']==('antecedent' if delta<0 else 'event_window') and
                     r['use_class']==(ANTECEDENT if delta<0 else DESCRIPTIVE) and r['days_relative_to_gfd_start']==delta,
                     'Temporal leakage: rainfall role/date mismatch')
        rain.require(r['units']=='mm/day' and r['source_image_id']==f"{rain.SOURCE}/{r['rainfall_date'].replace('-','')}",
                     'Rainfall source/units changed')
        n,total=r['valid_cell_count'],r['candidate_cell_count']
        rain.require(type(n) is int and type(total) is int and 0<=n<=total and total>0,'Invalid rainfall mask counts')
        vals=[r[k] for k in ['regional_min_mm_per_day','regional_mean_mm_per_day','regional_max_mm_per_day']]
        rain.require(all(v is not None and math.isfinite(v) and v>=0 for v in vals) if n else all(v is None for v in vals),
                     'Invalid or invented unavailable rainfall')
        if n:rain.require(vals[0]<=vals[1]<=vals[2],'Rainfall summary order invalid')
        rain.require(r['status']==('available' if n==total else 'partial_spatial_coverage' if n else 'no_valid_pixels') and
                     r['valid_coverage_percent']==100*n/total,'Mask/coverage status mismatch')
    expected={(a['gfd_id'],day) for a in anchors for day in dates(a)}
    rain.require(seen.issubset(expected) and (allow_partial or seen==expected),'Requested daily coverage incomplete')
    return [{'gfd_id':a['gfd_id'],'requested_days':len(dates(a)),
      'antecedent_days':sum(r['gfd_id']==a['gfd_id'] and r['relationship']=='antecedent' for r in rows),
      'available_antecedent_days':sum(r['gfd_id']==a['gfd_id'] and r['relationship']=='antecedent' and r['status']=='available' for r in rows),
      'event_window_days':sum(r['gfd_id']==a['gfd_id'] and r['relationship']=='event_window' for r in rows),
      'unavailable_or_partial_dates':[r['rainfall_date'] for r in rows if r['gfd_id']==a['gfd_id'] and r['status']!='available'],
      'not_retrieved_dates':[day for day in dates(a) if (a['gfd_id'],day) not in seen]} for a in anchors]


def derived(rows,anchors):
    validate_daily(rows,anchors,allow_partial=True)
    lookup={(r['gfd_id'],r['rainfall_date']):r for r in rows};features=[];description=[]
    for a in anchors:
        start=date.fromisoformat(a['gfd_start'])
        def select_days(requested,role):
            result=[lookup.get((a['gfd_id'],d)) for d in requested]
            rain.require(all(r is None or r['relationship']==role for r in result),'Temporal leakage in derived window')
            return result if all(r and r['status']=='available' for r in result) else None
        f={'gfd_id':a['gfd_id'],'scope_id':a['scope_id'],'gfd_start':a['gfd_start'],
           'last_allowed_date':(start-timedelta(days=1)).isoformat(),'use_class':ANTECEDENT}
        for n in LENGTHS:
            window=[(start-timedelta(days=i)).isoformat() for i in range(n,0,-1)]
            values=select_days(window,'antecedent')
            f[f'rain_{n}d_mm']=math.fsum(r['regional_mean_mm_per_day'] for r in values) if values else None
            if n in {7,14}:f[f'max_daily_previous_{n}d_mm']=max(r['regional_mean_mm_per_day'] for r in values) if values else None
        f['status']='complete' if all(f[f'rain_{n}d_mm'] is not None for n in LENGTHS) else 'incomplete_antecedent_data'
        features.append(f)
        event=select_days(days(a['gfd_start'],a['gfd_end_inclusive']),'event_window')
        total=math.fsum(r['regional_mean_mm_per_day'] for r in event) if event else None
        description.append({'gfd_id':a['gfd_id'],'scope_id':a['scope_id'],'gfd_start':a['gfd_start'],
            'gfd_end_inclusive':a['gfd_end_inclusive'],'use_class':DESCRIPTIVE,
            'status':'complete' if event else 'incomplete_descriptive_data','event_window_total_mm':total,
            'event_window_daily_mean_mm':total/len(event) if event else None,
            'event_window_max_daily_mm':max(r['regional_mean_mm_per_day'] for r in event) if event else None})
    validate_feature_sets(features,description)
    return features,description


def validate_feature_sets(features,description):
    for r in features:
        rain.require(set(r)==set(ANTECEDENT_FIELDS) and r['use_class']==ANTECEDENT and
                     r['last_allowed_date']==(date.fromisoformat(r['gfd_start'])-timedelta(days=1)).isoformat(),
                     'Descriptive/future fields in antecedent feature set')
    for r in description:
        rain.require(set(r)==set(DESCRIPTIVE_FIELDS) and r['use_class']==DESCRIPTIVE,
                     'Antecedent/descriptive schemas mixed')


def scalar_check(anchor,row,values,valid,centres):
    x,y=centres;g=shape(anchor['geometry'])
    members=[(i,j) for i,j in np.ndindex(values.shape) if Point(float(x[i,j]),float(y[i,j])).within(g)]
    observed=[float(values[i,j]) for i,j in members if valid[i,j]]
    expected={'regional_mean_mm_per_day':math.fsum(observed)/len(observed) if observed else None,
              'regional_min_mm_per_day':min(observed) if observed else None,'regional_max_mm_per_day':max(observed) if observed else None}
    rain.require(len(members)==row['candidate_cell_count'] and len(observed)==row['valid_cell_count'],'Scalar membership/count mismatch')
    for k,v in expected.items():rain.require(v is None and row[k] is None or v is not None and math.isclose(v,row[k],rel_tol=1e-12,abs_tol=1e-10),'Independent scalar rainfall mismatch')
    return {'gfd_id':anchor['gfd_id'],'date':row['rainfall_date'],'candidate_cells':len(members),
            'valid_cells':len(observed),'scalar_mean_mm_per_day':expected['regional_mean_mm_per_day'],'matches':True}


def validate_image(record,day,params,raw):
    rain.require(record['date']==day and record['source_image_id']==f"{rain.SOURCE}/{day.replace('-','')}",
                 'Wrong original daily image')
    parsed=rain.image_record(record['original_metadata'],day)
    for key,value in parsed.items():rain.require(record[key]==value,'Original image metadata mismatch')
    rain.require(record['native_dimensions']==[7200,2000],'Original CHIRPS dimensions changed')
    path=raw/record['file'];rain.require(satellite.source.fingerprint(path)=={k:record['download'][k] for k in ['sha256','bytes']},'Raw raster checksum mismatch')
    values,valid,metadata=rain.read_raster(path,params)
    rain.require(metadata==record['raster_metadata'],'Raster grid/mask changed')
    return values,valid


def write_csv(path,rows,fields):
    with path.open('x',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def csv_rows(path,fields):
    with path.open(newline='') as handle:
        reader=csv.DictReader(handle);rain.require(reader.fieldnames==fields,'Dataset schema changed')
        rows=list(reader)
    ints={'gfd_id','days_relative_to_gfd_start','valid_cell_count','candidate_cell_count'}
    numeric={k for k in fields if k.endswith('_mm') or k.endswith('_mm_per_day') or k=='valid_coverage_percent'}
    for row in rows:
        for k in ints & set(fields):row[k]=int(row[k])
        for k in numeric:row[k]=float(row[k]) if row[k] else None
    return rows


def input_files():
    folders=[ROOT/'data/working/karnataka_satellite_event_evidence_v2',ROOT/'data/working/karnataka_satellite_event_evidence_v4',
             ROOT/'data/processed/udupi_historical_v1',ROOT/'data/processed/udupi_flood_spatial_v1',ROOT/'data/working/karnataka_flood_events_v1']
    return {str(p):satellite.source.fingerprint(p) for folder in folders for p in folder.iterdir() if p.is_file()}


def extract(output,raw,resume=False):
    rain.require_new_output(output);anchors=load_anchors()
    plan={'anchors':anchors,'parameters':{str(a['gfd_id']):parameters(a['geometry']) for a in anchors},
          'method':METHOD,'inputs':input_files(),'project':'floodpulse','max_dates':sum(len(dates(a)) for a in anchors)}
    if raw.exists():
        rain.require(resume and not (raw/'manifest.json').exists(),'Raw version exists; explicit resume required')
        rain.require(read(raw/'plan.json')==plan,'Resume geometry/anchor/source plan changed')
    else:
        rain.require_new_output(raw);raw.mkdir(parents=True)
        satellite.source.write_new(raw/'plan.json',plan)
    cache={}
    log=raw/'retrieval.jsonl'
    if log.exists():
        for line in log.read_text().splitlines():
            record=json.loads(line);key=(record['gfd_id'],record['date'])
            rain.require(key not in cache,'Duplicate validated cache record');cache[key]=record
    rows=[];checks=[];records=[];infos={}
    session=satellite.TimedEE(raw,60,900)
    attempt=1+len(list(raw.glob('access_attempt*.json')))
    access={'started_at':rain.now(),'resume':resume}
    try:
        session.initialize();access['initialization_succeeded']=True
        import requests
        with requests.Session() as http:
            for anchor in anchors:
                eid=anchor['gfd_id'];params=plan['parameters'][str(eid)]
                mask,centres=membership(anchor['geometry'],params)
                folder=raw/str(eid);folder.mkdir(exist_ok=True)
                for day in dates(anchor):
                    key=(eid,day)
                    if key in cache:record=cache[key]
                    else:
                        image=session.ee.Image(f"{rain.SOURCE}/{day.replace('-','')}")
                        if day not in infos:infos[day]=session.request(image.getInfo,f'metadata:{day}')
                        record=rain.image_record(infos[day],day)
                        record.update(gfd_id=eid,original_metadata=infos[day])
                        url=session.request(lambda:rain.export_image(image).getDownloadURL(dict(params)),f'download_url:{eid}:{day}')
                        path=folder/(day.replace('-','')+'.tif');rain.require(not path.exists(),'Unjournaled raster exists; preserve for explicit recovery')
                        number=0
                        def retrieve():
                            nonlocal number
                            number+=1;temporary=path.with_name(path.stem+f'.attempt{attempt}.{number}.partial.tif')
                            return rain.download(http,url,temporary)
                        record['download']=session.request(retrieve,f'raster_download:{eid}:{day}')
                        temporary=path.with_name(path.stem+f'.attempt{attempt}.{number}.partial.tif');temporary.rename(path)
                        record['file']=str(path.relative_to(raw))
                        values,valid,record['raster_metadata']=rain.read_raster(path,params)
                        with log.open('a') as stream:stream.write(json.dumps(record,allow_nan=False)+'\n')
                    values,valid=validate_image(record,day,params,raw)
                    row=summarize(anchor,day,values,valid,mask,record)
                    rows.append(row);records.append(record)
                    # Scalar checks every date, not only selected samples.
                    checks.append(scalar_check(anchor,row,values,valid,centres))
                print(json.dumps({'completed_event':eid,'days':len(dates(anchor)),
                    'available':sum(r['gfd_id']==eid and r['status']=='available' for r in rows)}),flush=True)
        access['regression_counts_after']={a['gfd_id']:a['qualifying_floodwater_cells'] for a in load_anchors()}
    except Exception as exc:
        access.update(stopped_error=satellite.source.provider_error(exc),validated_coverage=validate_daily(rows,anchors,allow_partial=True))
        access['finished_at']=rain.now();satellite.source.write_new(raw/f'access_attempt{attempt}.json',access)
        print(json.dumps(access,indent=2),flush=True)
        raise
    access['finished_at']=rain.now();satellite.source.write_new(raw/f'access_attempt{attempt}.json',access)
    coverage=validate_daily(rows,anchors);features,description=derived(rows,anchors)
    output.mkdir(parents=True,exist_ok=False)
    write_csv(output/'daily_rainfall.csv',rows,DAILY_FIELDS)
    write_csv(output/'antecedent_features.csv',features,ANTECEDENT_FIELDS)
    write_csv(output/'descriptive_event_rainfall.csv',description,DESCRIPTIVE_FIELDS)
    metadata={'version':output.name,'created_at':rain.now(),'project':'floodpulse','source':{
        'collection':rain.SOURCE,'version':'CHIRPS v2.0 Final','units':'mm/day','native_resolution_degrees':.05,
        'url':rain.SOURCE_URL,'license':'Public domain','citation':'Funk et al. (2015), doi:10.1038/sdata.2015.66'},
        'anchors':anchors,'raw_directory':str(raw.resolve()),'download_parameters':plan['parameters'],
        'method':METHOD,'inputs':plan['inputs'],'coverage':coverage,'images':records,'scalar_checks':checks,
        'access':access,'schemas':{'daily_rainfall.csv':DAILY_FIELDS,'antecedent_features.csv':ANTECEDENT_FIELDS,
                                 'descriptive_event_rainfall.csv':DESCRIPTIVE_FIELDS},
        'files':{p.name:satellite.source.fingerprint(p) for p in output.iterdir() if p.is_file()},
        'raw_files':{str(p.resolve()):satellite.source.fingerprint(p) for p in raw.rglob('*') if p.is_file()},
        'scope':'Exploratory retrospective context, not an ML training dataset; no negatives/daily flood labels.',
        'processing_code':{str(p.relative_to(ROOT)):satellite.source.fingerprint(p) for p in
            [Path(__file__),ROOT/'scripts/extract_karnataka_rainfall.py',ROOT/'scripts/expand_karnataka_satellite.py']},
        'antecedent_rule':'T-30 through T-1 only, primary anchor GFD_start; totals require full spatial and temporal coverage.',
        'descriptive_rule':DESCRIPTIVE,'rainy_day_counts':'omitted; no silently chosen threshold',
        'limitations':['District means, not station/locality measurements; sums of daily regional means.',
          'Final CHIRPS is retrospective; contemporaneous release/availability at historical prediction times not verified.',
          'Modern review polygons are not historical district boundaries or independently current-LGD reconciled.',
          'IFI dates remain separate/provisional; GFD-start antecedents need not precede an earlier reported IFI onset.',
          'No causal threshold, statewide model readiness or equal evidential weight for 2 versus 329 flood cells.'],
        'publication':'Detailed rainfall tables and raw rasters remain local conservatively; no SOI geometry used or transmitted.',
        'gfd_license':'CC BY-NC 4.0; Tellman et al., Cloud to Street / DFO','boundary_license':'CC BY 4.0; geoBoundaries v6 / William & Mary geoLab'}
    satellite.source.write_new(output/'manifest.json',metadata)
    return validate(output)


def validate(output):
    m=read(output/'manifest.json');anchors=load_anchors()
    rain.require(m['anchors']==anchors and m['source']['collection']==rain.SOURCE and m['source']['version']=='CHIRPS v2.0 Final',
                 'Verified anchors/source changed')
    rain.require(m['source']['units']=='mm/day' and m['method']==METHOD,'Rainfall method/units changed')
    for name,expected in {**m['inputs'],**m['raw_files']}.items():rain.require(satellite.source.fingerprint(name)==expected,'Input/raw checksum changed')
    for name,expected in m['files'].items():rain.require(Path(name).name==name and satellite.source.fingerprint(output/name)==expected,'Output checksum changed')
    rows=csv_rows(output/'daily_rainfall.csv',DAILY_FIELDS)
    coverage=validate_daily(rows,anchors);features,description=derived(rows,anchors)
    rain.require(features==csv_rows(output/'antecedent_features.csv',ANTECEDENT_FIELDS) and
                 description==csv_rows(output/'descriptive_event_rainfall.csv',DESCRIPTIVE_FIELDS),'Derived rainfall/temporal leakage mismatch')
    raw=Path(m['raw_directory']);rebuilt=[];checks=[]
    lookup={a['gfd_id']:a for a in anchors}
    for image in m['images']:
        a=lookup[image['gfd_id']];params=parameters(a['geometry']);rain.require(params==m['download_parameters'][str(a['gfd_id'])],'Native envelope changed')
        mask,centres=membership(a['geometry'],params)
        values,valid=validate_image(image,image['date'],params,raw)
        row=summarize(a,image['date'],values,valid,mask,image);rebuilt.append(row)
        checks.append(scalar_check(a,row,values,valid,centres))
    rain.require(rebuilt==rows and checks==m['scalar_checks'] and coverage==m['coverage'],'Full raw-to-daily rainfall reproduction failed')
    return {'daily_records':len(rows),'events':coverage,'antecedent_features':features,'descriptive_event_rainfall':description,
            'satellite_regressions':{a['gfd_id']:a['qualifying_floodwater_cells'] for a in anchors},'independent_scalar_checks':len(checks)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT);parser.add_argument('--raw',type=Path,default=RAW)
    parser.add_argument('--resume',action='store_true');parser.add_argument('--validate-only',type=Path)
    args=parser.parse_args()
    result=validate(args.validate_only) if args.validate_only else extract(args.output,args.raw,args.resume)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
