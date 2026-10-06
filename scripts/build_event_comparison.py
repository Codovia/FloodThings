#!/usr/bin/env python3
"""Six non-binary evidence contexts; new rainfall only for two fixed observed-zero scopes.

No GFD reanalysis, random/background sampling, labels, thresholds or model fitting.
Completed versions and Stage3C helpers remain read-only. Detailed data stay local.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

from shapely.geometry import shape

sys.path.insert(0,str(Path(__file__).resolve().parent))
import extract_positive_event_rainfall as context

source=context.satellite.source
rain=context.rain
ROOT=context.ROOT
SATELLITE=ROOT/'data/working/karnataka_satellite_event_evidence_v4'
FIRST=ROOT/'data/working/karnataka_satellite_event_evidence_v2'
POSITIVE=context.OUTPUT
OUTPUT=ROOT/'data/working/karnataka_event_comparison_v1'
RAW=ROOT/'data/raw/chirps/comparison_events_v1'
VOCABULARY=frozenset({'satellite_positive','observed_zero_event','unlabeled_background',
                      'insufficient_observation','candidate_mismatch'})
COMPARISON={2698:('Bijapur',166123),3107:('Raichur',132615)}
EXPECTED_COUNTS={**context.COUNTS,2698:0,3107:0}
FEATURES=tuple([f'rain_{n}d_mm' for n in context.LENGTHS]+['max_daily_previous_7d_mm','max_daily_previous_14d_mm'])
CRITERIA='Valid flooded, jrc_perm_water and clear_views masks; clear_views>0; flooded=1 and jrc_perm_water=0. Event-window maximum, never daily occurrence.'
EVIDENCE_FIELDS={'gfd_id','scope_id','scope_name','evidence_class','gfd_start','gfd_end_inclusive',
 'qualifying_floodwater_cells','valid_gfd_observation_cells','original_observation_status','observation_quality',
 'gfd_processing_scale_m','gfd_processing_crs','gfd_observation_criteria','ifi_association_status','ifi_associations',
 'antecedent_features','descriptive_event_window_rainfall','evidence_provenance','rainfall_provenance','ml_binary_label'}


def evidence_class(record,zero_gate):
    """Map original statuses without promoting absence/unusable observations."""
    status=record['evidence_status'];stats=record['statistics']
    rain.require(status in {'satellite_positive','observed_no_qualifying_floodwater',
                            'insufficient_observation','candidate_mismatch'},'Unknown original satellite status')
    if status in {'insufficient_observation','candidate_mismatch'}:return status
    rain.require(record['computation_complete'] is True and record['counts_are_lower_bounds'] is False,
                 'Incomplete evidence cannot enter comparison')
    q,n,total=stats['qualifying_pixels'],stats['valid_pixels'],stats['region_pixels']
    rain.require(all(type(v) is int for v in [q,n,total]) and 0<=q<=n<=total and total>0,'Invalid observation counts')
    rain.require(record['valid_fraction']==n/total,'Observation coverage mismatch')
    if status=='satellite_positive':
        rain.require(q>0,'Positive evidence must contain qualifying cells');return status
    rain.require(q==0 and n>0 and n/total>=zero_gate,'Observed-zero quality gate not met')
    return 'observed_zero_event'


def binary_targets(records):
    raise ValueError('No reviewed binary target methodology: observed-zero/background evidence is not verified non-flood.')


def validate_evidence(records,expected=None):
    expected=EXPECTED_COUNTS if expected is None else expected
    seen=set()
    for r in records:
        rain.require(set(r)==EVIDENCE_FIELDS,'Unexpected evidence fields or binary/risk labels')
        eid=r['gfd_id'];rain.require(type(eid) is int and eid not in seen and eid in expected,'Duplicate/unapproved pilot event');seen.add(eid)
        rain.require(r['evidence_class'] in VOCABULARY and r['evidence_class'] in {'satellite_positive','observed_zero_event'},
                     'Background/insufficient/mismatched observations excluded from pilot')
        rain.require(r['ml_binary_label'] is None,'Binary targets forbidden without separate review')
        rain.require(type(r['qualifying_floodwater_cells']) is int and type(r['valid_gfd_observation_cells']) is int and
                     r['qualifying_floodwater_cells']==expected[eid] and r['valid_gfd_observation_cells']>0,
                     'Protected satellite regression changed')
        rain.require(r['evidence_class']==('satellite_positive' if expected[eid]>0 else 'observed_zero_event'),
                     'Evidence class contradicts observation count')
        rain.require(r['gfd_processing_scale_m']==250 and r['gfd_processing_crs']=='EPSG:32643' and
                     r['gfd_observation_criteria']==CRITERIA,'Satellite criteria/grid changed')
        f,d=r['antecedent_features'],r['descriptive_event_window_rainfall']
        context.validate_feature_sets([f],[d])
        rain.require(all(v is None or math.isfinite(v) and v>=0 for v in [f[k] for k in FEATURES]),'Invalid rainfall predictors')
        rain.require(f['status']!='complete' or all(f[k] is not None for k in FEATURES),'Missing predictor presented as complete')
        rain.require(f['gfd_id']==d['gfd_id']==eid and f['scope_id']==d['scope_id']==r['scope_id'] and
                     f['gfd_start']==d['gfd_start']==r['gfd_start'] and d['gfd_end_inclusive']==r['gfd_end_inclusive'],
                     'Context/event anchor identity mismatch')
        if eid in COMPARISON:
            rain.require(r['scope_name']==COMPARISON[eid][0] and r['valid_gfd_observation_cells']==COMPARISON[eid][1] and
                         r['original_observation_status']=='observed_no_qualifying_floodwater',
                         'Observed-zero source identity/count changed')
    rain.require(seen==set(expected),'Pilot must preserve all six event identities')


def antecedent_predictors(record):
    """Only approved rain fields; never descriptive values or an encoded target."""
    validate_evidence([record],{record['gfd_id']:EXPECTED_COUNTS[record['gfd_id']]})
    f=record['antecedent_features'];rain.require(f['status']=='complete','Unavailable antecedents cannot be predictors')
    return {k:f[k] for k in FEATURES}


def retained_inputs():
    """Validate all source evidence locally; zero Earth Engine calls."""
    positive_result=context.validate(POSITIVE)
    manifest=context.read(SATELLITE/'manifest.json')
    context.satellite.validate(SATELLITE)
    rain.require(manifest['parameters']['valid_fraction_zero_gate']==.95,'Existing quality gate changed')
    anchors=[];evidence=context.read(SATELLITE/'event_evidence.json')
    for eid,(name,valid) in COMPARISON.items():
        r=next(row for row in evidence if row['gfd_id']==eid)
        rain.require(evidence_class(r,.95)=='observed_zero_event' and r['review_region']['shapeName']==name and
                     r['statistics']['valid_pixels']==valid and r['statistics']['qualifying_pixels']==0,
                     'Comparison regression/source mismatch')
        grid=r['analysis_grid'];rain.require(grid['crs']==source.CRS and grid['nominal_scale_m']==250 and
              grid['transform']==source.TRANSFORM and r['preflight']['analysis_scale_m']==250,
              'Original GFD projection/scale changed')
        rain.require(r['image_id']==context.history.event_asset(eid,r['gfd_start'],r['gfd_end_inclusive']),
                     'Original image dates changed')
        geometry=r['preflight']['region']['geometry'];g=shape(geometry)
        rain.require(g.is_valid and not g.is_empty and g.geom_type in {'Polygon','MultiPolygon'},'No reproducible local scope')
        anchors.append({'gfd_id':eid,'image_id':r['image_id'],'gfd_start':r['gfd_start'],
            'gfd_end_inclusive':r['gfd_end_inclusive'],'scope_id':r['review_region']['shapeID'],'scope_name':name,
            'geometry':geometry,'geometry_source':source.BOUNDARY,'geometry_crs':'EPSG:4326',
            'geometry_vintage':'geoBoundaries v6.0.0 (2023 composite), not historical boundaries',
            'geometry_sha256':hashlib.sha256(source.packed(geometry)).hexdigest(),
            'evidence_class':'observed_zero_event','qualifying_floodwater_cells':0,'valid_gfd_observation_cells':valid,
            'original_observation_status':r['evidence_status'],'observation_quality':{
                'valid_fraction':r['valid_fraction'],'region_cells':r['statistics']['region_pixels'],
                'minimum_valid_fraction_gate':.95,'permanent_water_cells':r['statistics']['permanent_water_pixels'],
                'clear_views_mean_valid_raw':r['clear_views_mean_valid'],'clear_perc_mean_valid_raw':r['clear_perc_mean_valid'],
                'quality_gate_is_not_statistical_absence_confidence':True},
            'ifi_association_status':r['association_status'],'ifi_associations':[{'ifi_source_event_id':r['ifi_source_event_id'],
                'ifi_start':r['ifi_start'],'ifi_end_inclusive':r['ifi_end_inclusive'],'status':r['association_status']}],
            'evidence_provenance':{'source_image_id':r['image_id'],'source_retrieved_at':r['retrieved_at'],
                'original_evidence_file':str(SATELLITE/'event_evidence.json'),
                'original_evidence_file_checksum':source.fingerprint(SATELLITE/'event_evidence.json'),
                'original_record_sha256':hashlib.sha256(source.packed(r)).hexdigest(),
                'original_manifest_checksum':source.fingerprint(SATELLITE/'manifest.json')}})
    excluded=[]
    for folder in [FIRST,SATELLITE]:
        m=context.read(folder/'manifest.json')
        for r in context.read(folder/'event_evidence.json'):
            cls=evidence_class(r,source.MIN_VALID_FRACTION)
            if cls in {'insufficient_observation','candidate_mismatch'}:
                excluded.append({'gfd_id':r['gfd_id'],'scope_name':r['review_region']['shapeName'],
                    'evidence_class':cls,'original_status':r['evidence_status'],'rainfall_extracted':False,
                    'original_file_checksum':source.fingerprint(folder/'event_evidence.json')})
    inputs=context.input_files()
    for p in POSITIVE.iterdir():
        if p.is_file():inputs[str(p)]=source.fingerprint(p)
    return {'anchors':anchors,'positive_anchors':context.read(POSITIVE/'manifest.json')['anchors'],
            'positive_result':positive_result,'inputs':inputs,'excluded_evidence':excluded}


def evidence_table(inputs,features,descriptive,output):
    combined_f={f['gfd_id']:f for f in inputs['positive_result']['antecedent_features']+features}
    combined_d={d['gfd_id']:d for d in inputs['positive_result']['descriptive_event_rainfall']+descriptive}
    records=[]
    for a in sorted(inputs['positive_anchors']+inputs['anchors'],key=lambda a:a['gfd_id']):
        eid=a['gfd_id'];cls='satellite_positive' if eid in context.COUNTS else 'observed_zero_event'
        files=POSITIVE if cls=='satellite_positive' else output
        record={k:a[k] for k in ['gfd_id','scope_id','scope_name','gfd_start','gfd_end_inclusive',
             'qualifying_floodwater_cells','valid_gfd_observation_cells','original_observation_status',
             'ifi_association_status','ifi_associations']}
        record.update(evidence_class=cls,ml_binary_label=None,gfd_processing_scale_m=250,
            gfd_processing_crs=source.CRS,gfd_observation_criteria=CRITERIA,
            observation_quality=a.get('observation_quality',{'status':a['original_observation_status'],
                'original_quality_evidence_retained':True}),antecedent_features=combined_f[eid],
            descriptive_event_window_rainfall=combined_d[eid],
            evidence_provenance=a.get('evidence_provenance',{'retained_anchor_file':str(POSITIVE/'manifest.json'),
                'retained_anchor_file_checksum':source.fingerprint(POSITIVE/'manifest.json'),'source_image_id':a['image_id']}),
            rainfall_provenance={'daily_file':str(files/('daily_rainfall.csv' if cls=='satellite_positive' else 'daily_comparison_rainfall.csv')),
                'daily_file_checksum':source.fingerprint(files/('daily_rainfall.csv' if cls=='satellite_positive' else 'daily_comparison_rainfall.csv')),
                'source':rain.SOURCE,'units':'mm/day','method':context.METHOD,'geometry_source':a['geometry_source'],
                'geometry_sha256':a['geometry_sha256'],'geometry_vintage':a['geometry_vintage']})
        records.append(record)
    validate_evidence(records)
    return records


def retrieve(anchors,raw,inputs,resume):
    """Same bounded native-grid retrieval, mask and aggregation as Stage3C."""
    plan={'anchors':anchors,'inputs':inputs,'method':context.METHOD,'project':'floodpulse',
          'parameters':{str(a['gfd_id']):context.parameters(a['geometry']) for a in anchors}}
    if raw.exists():
        rain.require(resume and context.read(raw/'plan.json')==plan,'Explicit resume with identical plan required')
    else:
        rain.require_new_output(raw);raw.mkdir(parents=True);source.write_new(raw/'plan.json',plan)
    log=raw/'retrieval.jsonl';cache={}
    if log.exists():
        for line in log.read_text().splitlines():
            rec=json.loads(line);key=(rec['gfd_id'],rec['date']);rain.require(key not in cache,'Duplicate raw cache');cache[key]=rec
    session=context.satellite.TimedEE(raw,60,900)
    attempt=1+len(list(raw.glob('access_attempt*.json')));access={'started_at':rain.now(),'resume':resume}
    rows=[];checks=[];images=[];infos={}
    try:
        session.initialize();access['initialization_succeeded']=True
        import requests
        with requests.Session() as http:
            for a in anchors:
                eid=a['gfd_id'];params=plan['parameters'][str(eid)];mask,centres=context.membership(a['geometry'],params)
                folder=raw/str(eid);folder.mkdir(exist_ok=True)
                for day in context.dates(a):
                    key=(eid,day)
                    if key in cache:record=cache[key]
                    else:
                        image=session.ee.Image(f"{rain.SOURCE}/{day.replace('-','')}")
                        if day not in infos:infos[day]=session.request(image.getInfo,f'metadata:{day}')
                        record=rain.image_record(infos[day],day);record.update(gfd_id=eid,original_metadata=infos[day])
                        url=session.request(lambda:rain.export_image(image).getDownloadURL(dict(params)),f'download_url:{eid}:{day}')
                        path=folder/(day.replace('-','')+'.tif');rain.require(not path.exists(),'Unjournaled raster exists; explicit recovery required')
                        number=0
                        def download():
                            nonlocal number
                            number+=1
                            return rain.download(http,url,path.with_name(path.stem+f'.attempt{attempt}.{number}.partial.tif'))
                        record['download']=session.request(download,f'raster_download:{eid}:{day}')
                        path.with_name(path.stem+f'.attempt{attempt}.{number}.partial.tif').rename(path)
                        record['file']=str(path.relative_to(raw))
                        _,_,record['raster_metadata']=rain.read_raster(path,params)
                        with log.open('a') as stream:stream.write(json.dumps(record,allow_nan=False)+'\n')
                    values,valid=context.validate_image(record,day,params,raw)
                    row=context.summarize(a,day,values,valid,mask,record);rows.append(row);images.append(record)
                    checks.append(context.scalar_check(a,row,values,valid,centres))
                print(json.dumps({'completed_comparison':eid,'days':len(context.dates(a)),
                                 'complete_days':sum(r['gfd_id']==eid and r['status']=='available' for r in rows)}),flush=True)
    except Exception as exc:
        access.update(stopped_error=source.provider_error(exc),coverage=context.validate_daily(rows,anchors,allow_partial=True),finished_at=rain.now())
        source.write_new(raw/f'access_attempt{attempt}.json',access);print(json.dumps(access,indent=2),flush=True);raise
    access['finished_at']=rain.now();source.write_new(raw/f'access_attempt{attempt}.json',access)
    return rows,images,checks,access,plan


def extract(output,raw,resume=False):
    rain.require_new_output(output);inputs=retained_inputs();anchors=inputs['anchors']
    rows,images,checks,access,plan=retrieve(anchors,raw,inputs['inputs'],resume)
    coverage=context.validate_daily(rows,anchors);features,descriptive=context.derived(rows,anchors)
    # Re-read all immutable source evidence before creating a completed version.
    rain.require(retained_inputs()==inputs,'Protected evidence changed during retrieval')
    output.mkdir(parents=True,exist_ok=False)
    for name,values,fields in [('daily_comparison_rainfall.csv',rows,context.DAILY_FIELDS),
                            ('comparison_antecedent_features.csv',features,context.ANTECEDENT_FIELDS),
                            ('comparison_descriptive_event_rainfall.csv',descriptive,context.DESCRIPTIVE_FIELDS)]:
        context.write_csv(output/name,values,fields)
    records=evidence_table(inputs,features,descriptive,output);source.write_new(output/'evidence.json',records)
    m={'version':output.name,'created_at':rain.now(),'project':'floodpulse','source':context.read(POSITIVE/'manifest.json')['source'],
       'anchors':anchors,'positive_context':str(POSITIVE),'method':context.METHOD,'inputs':inputs['inputs'],
       'raw_directory':str(raw.resolve()),'images':images,'scalar_checks':checks,'access':access,
       'download_parameters':plan['parameters'],'coverage':coverage,'excluded_evidence':inputs['excluded_evidence'],
       'vocabulary':sorted(VOCABULARY),'pilot_classes':['satellite_positive','observed_zero_event'],
       'binary_policy':'All ml_binary_label values null; binary_targets() refuses all targets. Separate review required.',
       'antecedent_schema':context.ANTECEDENT_FIELDS,'descriptive_schema':context.DESCRIPTIVE_FIELDS,
       'evidence_schema':sorted(EVIDENCE_FIELDS),'approved_predictor_fields':list(FEATURES),
       'rainy_day_counts':'omitted identically to Stage3C','descriptive_rule':context.DESCRIPTIVE,
       'files':{p.name:source.fingerprint(p) for p in output.iterdir() if p.is_file()},
       'raw_files':{str(p.resolve()):source.fingerprint(p) for p in raw.rglob('*') if p.is_file()},
       'execution_code':{str(p.relative_to(ROOT)):source.fingerprint(p) for p in [Path(__file__),Path(context.__file__)]},
       'gfd_license':'CC BY-NC 4.0; Tellman et al. (2021), Cloud to Street / DFO',
       'ifi_license':'CC BY-NC 4.0; Saharia / IIT Delhi / HydroSense Lab',
       'boundary_license':'CC BY 4.0; geoBoundaries v6 / William & Mary geoLab',
       'publication':'Detailed rainfall/evidence/raster products stay local; permitted metadata/code/methodology only.',
       'limitations':context.read(POSITIVE/'manifest.json')['limitations']+[
           'Observed-zero is scope/window/resolution-specific non-detection, not verified flood absence.',
           '95% spatial valid-observation gate is an existing research rule, not a calibrated absence confidence.',
           'No background windows collected; selection of future comparable windows requires separate review.']}
    source.write_new(output/'manifest.json',m)
    return validate(output)


def validate(output):
    m=context.read(output/'manifest.json');inputs=retained_inputs();anchors=inputs['anchors']
    rain.require(m['anchors']==anchors and m['inputs']==inputs['inputs'] and m['method']==context.METHOD,'Protected input/method changed')
    rain.require(m['source']==context.read(POSITIVE/'manifest.json')['source'] and m['vocabulary']==sorted(VOCABULARY) and
                 m['approved_predictor_fields']==list(FEATURES),'Rainfall source/evidence schema changed')
    rain.require(m['excluded_evidence']==inputs['excluded_evidence'],'Excluded evidence status changed')
    for p,value in {**m['inputs'],**m['raw_files']}.items():rain.require(source.fingerprint(p)==value,'Input/raw checksum changed')
    for name,value in m['files'].items():rain.require(Path(name).name==name and source.fingerprint(output/name)==value,'Output checksum changed')
    rows=context.csv_rows(output/'daily_comparison_rainfall.csv',context.DAILY_FIELDS)
    coverage=context.validate_daily(rows,anchors);features,description=context.derived(rows,anchors)
    rain.require(features==context.csv_rows(output/'comparison_antecedent_features.csv',context.ANTECEDENT_FIELDS) and
                 description==context.csv_rows(output/'comparison_descriptive_event_rainfall.csv',context.DESCRIPTIVE_FIELDS),
                 'Shared feature reproduction/temporal leakage mismatch')
    rebuilt=[];checks=[];lookup={a['gfd_id']:a for a in anchors}
    for image in m['images']:
        a=lookup[image['gfd_id']];params=context.parameters(a['geometry'])
        rain.require(params==m['download_parameters'][str(a['gfd_id'])],'Native grid window changed')
        mask,centres=context.membership(a['geometry'],params)
        values,valid=context.validate_image(image,image['date'],params,Path(m['raw_directory']))
        row=context.summarize(a,image['date'],values,valid,mask,image);rebuilt.append(row)
        checks.append(context.scalar_check(a,row,values,valid,centres))
    rain.require(rebuilt==rows and checks==m['scalar_checks'] and coverage==m['coverage'],'Full raster reproduction failed')
    evidence=context.read(output/'evidence.json');validate_evidence(evidence)
    rain.require(evidence==evidence_table(inputs,features,description,output),'Six-event source/feature provenance mismatch')
    return {'new_daily_records':len(rows),'coverage':coverage,'evidence_class_counts':dict(Counter(r['evidence_class'] for r in evidence)),
            'antecedent_features':features,'descriptive_event_rainfall':description,
            'satellite_regressions':{r['gfd_id']:{'qualifying_cells':r['qualifying_floodwater_cells'],
                                     'valid_cells':r['valid_gfd_observation_cells']} for r in evidence},
            'binary_targets_created':0,'background_windows_created':0,'independent_scalar_checks':len(checks),
            'excluded_evidence_count':len(inputs['excluded_evidence'])}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--raw',type=Path,default=RAW)
    p.add_argument('--resume',action='store_true');p.add_argument('--validate-only',type=Path)
    args=p.parse_args();result=validate(args.validate_only) if args.validate_only else extract(args.output,args.raw,args.resume)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
