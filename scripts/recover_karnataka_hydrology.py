#!/usr/bin/env python3
"""Stage4B offline recovery from original published downloads; no hidden endpoints.

Use fetch for one advertised Download URL at a time. Freeze only after local
metadata/identity review; validate reproduces the bounded pilot without writes.
Detailed records stay local while Other(Open)/CWC rights remain unresolved.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage4b_v1'
OUTPUT = ROOT / 'data/working/karnataka_hydrology_2019_pilot_v1'
REFERENCE = ROOT / 'data/reference/karnataka_hydrology_2019_pilot_v1'
START, END = '2019-07-25', '2019-08-20'
KINDS = {'daily', 'hourly'}
READY = {'measured_event_hydrology_recovered', 'official_dataset_available_target_stations_absent',
         'official_resource_access_blocked', 'source_identity_unresolved'}
CONFIG = {
    'cwc_discharge': {'id':'f95150ea-c8fc-4740-8815-d9c34c9d53a3', 'frequency':'daily',
        'value':'Manual Daily River Water Discharge (m3/sec)', 'units':'m3/sec', 'variable':'discharge'},
    'cwc_gauge': {'id':'7778f459-0e82-4681-9638-5e494c36fd42', 'frequency':'hourly',
        'value':'River Water Level Manual Hourly (meter)', 'units':'meter', 'variable':'water_level'},
    'state_manual': {'id':'a21e8e48-d5e3-4a35-8274-007e52f92daf', 'frequency':'daily',
        'value':'Water Discharge', 'units':None, 'variable':'discharge'},
    'state_telemetry': {'id':'68440116-aef8-49b6-83b4-f2a61d1ddf2b', 'frequency':'hourly',
        'value':'Telemetry Hourly River Water Discharge (m3/sec)', 'units':'m3/sec', 'variable':'discharge'},
}
# Explicit source-page anchors, not approximate geocoding or guessed legacy IDs.
PILOTS = {
    'CW1KRU000083': {'csv_name':'Sadalga (Seasonal)', 'history_page':603, 'table_page':607,
        'event_start':'2019-08-07', 'event_end':'2019-08-14', 'local_river':'Dudhganga'},
    'CW1KRU000212': {'csv_name':'Gokak falls', 'history_page':590, 'table_page':593,
        'event_start':'2019-08-06', 'event_end':'2019-08-12', 'local_river':'Ghatprabha'},
    'CW1KRU000339': {'csv_name':'Huvinhedigi', 'history_page':539, 'table_page':542,
        'event_start':'2019-08-11', 'event_end':'2019-08-11', 'local_river':'Krishna'},
}
METHOD = {
    'window': [START,END], 'time_zone':'not_documented',
    'availability':'availability_semantics_unverified; acquisition and retrieval times distinct',
    'identity':'ID first. CSVs without station IDs use explicitly reviewed CWC name/agency/river and independent Year Book gauge-opening dates; coordinates/legacy IDs retained separately',
    'coordinate_precision':'0.0005 degree is half a three-decimal metadata rounding step, used only to flag conflicts, never repair coordinates',
    'daily':'Original manual daily discharge records retain actual acquisition timestamps and rates, not accumulated water volume',
    'hourly':'Original manual-hourly rows retained at their actual timestamps, with no assumed complete 24-hour grid or resampling',
    'yearbook':'VolumeI2019-20; daily WL is corresponding mean m.s.l.; Q is observed/computed; * computed and # discarded/rating-curve changed retained',
    'comparison':'Discharge by station/date; exact Decimal comparison, then published rounding; hourly WL versus Year Book daily mean not equivalent',
    'thresholds':'No warning/danger comparisons: Stage4A threshold datum compatibility unverified',
    'state_network':'Distinct source station codes, agency and original non-LGD State Code retained; no CWC identity inferred from nearby names',
    'reuse':'Other(Open) lacks detailed resource terms; CWC permission and NWDP third-party exception unresolved. All raw/detailed products local',
    'features':False, 'labels':False, 'models':False,
}


def require(condition,message):
    if not condition:raise ValueError(message)


def json_bytes(v):
    return (json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()


def read(p):return json.loads(Path(p).read_bytes())


def digest(p,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with Path(p).open('rb') as stream:
        for b in iter(lambda:stream.read(1048576),b''):h.update(b)
    return h.hexdigest()


def file_record(p):
    p=Path(p)
    return {'path':str(p.relative_to(ROOT)),'sha256':digest(p),'bytes':p.stat().st_size}


class Page(HTMLParser):
    """Only public text/links; script/session bodies never exposed as metadata."""
    def __init__(self):
        super().__init__();self.text=[];self.links=[];self.anchor=None;self.a_text=[];self.skip=0
    def handle_starttag(self,t,a):
        if t in {'script','style'}:self.skip+=1
        if t=='a':self.anchor=dict(a).get('href');self.a_text=[]
    def handle_endtag(self,t):
        if t in {'script','style'}:self.skip-=1
        if t=='a' and self.anchor:
            self.links.append((' '.join(' '.join(self.a_text).split()),self.anchor));self.anchor=None
    def handle_data(self,v):
        if not self.skip and v.strip():self.text.append(v.strip())
        if self.anchor and not self.skip:self.a_text.append(v)


def classify_licence(title,*,explicit_terms_verified=False,third_party=False):
    if third_party or title in {None,'','Other (Open)','Other','Open'}:
        return 'redistribution_unresolved'
    if title=='Creative Commons Attribution 4.0' and explicit_terms_verified:
        return 'open_with_attribution'
    return 'resource_specific_terms_apply'


def resource_metadata(body,resource_id,page_body,*,retrieval_time):
    d=json.loads(body)
    require(d.get('success') is True and len(d.get('result',{}).get('results',[]))==1,'Ambiguous official catalogue response')
    package=d['result']['results'][0]
    matches=[r for r in package['resources'] if r['id']==resource_id]
    require(len(matches)==1,'Missing/duplicate resource identity')
    r=matches[0];page=Page();page.feed(page_body.decode('utf-8'))
    require(any(url==r['url'] and 'download' in text.lower() for text,url in page.links),'Download not advertised on official resource page')
    require(r['format']=='CSV' and r['url'].startswith('https://nwdp.nwic.gov.in/dataset/'),'Unexpected official download/format')
    require(r.get('size',0)>0,'Missing resource size')
    licence=package.get('license_title'); require(licence in page.text,'Licence not corroborated by resource page')
    ix=page.text.index('Data last updated')
    return {'dataset_title':package['title'],'dataset_id':package['id'],'resource_title':r['name'],
        'resource_id':r['id'],'producer':package['organization']['title'],
        'download_url':r['url'],'original_filename':r['url'].rsplit('/',1)[1],
        'portal_date_range_label':r['name'],'format':r['format'],'portal_size':r['size'],
        'portal_hash':r.get('hash'),'portal_hash_algorithm':'not labelled; MD5 candidate compared independently',
        'portal_update':r.get('last_modified'),'resource_page_update':page.text[ix+1],
        'resource_licence':licence,'licence_id':package.get('license_id'),
        'publication_handling':classify_licence(licence,third_party=package['organization']['title']=='CWC'),
        'retrieval_time':retrieval_time}


def parse_timestamp(value,frequency):
    require(frequency in KINDS,'Unknown source frequency')
    for fmt in (['%d-%m-%Y %H:%M'] if frequency=='hourly' else ['%d-%m-%Y %H:%M','%d-%m-%Y']):
        try:
            parsed=datetime.strptime(value,fmt)
            return parsed.isoformat() if '%H' in fmt else parsed.date().isoformat()
        except ValueError:pass
    raise ValueError('Malformed source observation timestamp')


def numeric(value,variable):
    if value in {None,'','-'}:return None
    try:v=Decimal(value)
    except InvalidOperation as e:raise ValueError('Malformed observed value') from e
    require(v.is_finite(),'Nonfinite source observation')
    require(variable!='discharge' or v>=0,'Negative discharge')
    return str(v)


def match_station(row,identities,id_field=None):
    """Never silently replace a conflicting supplied ID with a name match."""
    if id_field and row.get(id_field):
        key=row[id_field]
        if key not in identities:return None
        identity=identities[key]
        require(row.get('Agency')=='CWC','Station ID agency conflict')
        require(row.get('Station') in identity['csv_names'],'Station ID/name conflict')
        return key
    if row.get('Agency')!='CWC':return None
    matches=[(key,i) for key,i in identities.items() if row.get('Station') in i['csv_names']]
    require(len(matches)<=1,'Ambiguous official source alias')
    if matches:
        key,identity=matches[0]
        require(identity['gauge_opening_corroborated'] is True,'Name fallback lacks independent official evidence')
        require(row.get('Local River') in identity['csv_local_rivers'],'Station name/river conflict')
        return key
    return None


def normalize(row,config,identity,station_id,line,resource):
    observed=parse_timestamp(row['Data Acquisition Time'],config['frequency'])
    require(START<=observed[:10]<=END,'Outside pilot window')
    value=numeric(row[config['value']],config['variable'])
    # Original masks/status fields remain present even if their meaning is undocumented.
    quality={k:v for k,v in row.items() if any(t in k.lower() for t in ['quality','status','flag'])}
    return {'canonical_cwc_station_id':station_id,'source_station_id':None,
        'source_station_name':row['Station'],'source_resource_id':resource['resource_id'],
        'source_row_number':line,'variable':config['variable'],'original_value':row[config['value']],
        'value':value,'units':config['units'],'frequency':config['frequency'],
        'observation_time':observed,'original_observation_time':row['Data Acquisition Time'],
        'observation_timezone':'not_documented','retrieval_time':resource['download']['retrieved_at'],
        'availability_time':None,'historical_availability_status':'availability_semantics_unverified',
        'quality_flags':quality,'measurement_status':'source_reported_quality_unverified',
        'coordinate_status':identity['nwdp_vs_stage4a_coordinate_status'],
        'datum':'source datum compatibility unverified; original RL/MeanSeaLevel fields retained',
        'source_record':deepcopy(row)}


def csv_audit(path,config,identities,resource):
    """Full source census; only selected/window records normalized. No interpolation."""
    count=0;names=Counter();years=Counter();agencies=Counter();codes=set();duplicates=conflicts=0
    missing=malformed_dates=invalid_values=0;selected=[];seen={};invalid_examples=[]
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames
        require(columns and len(columns)==len(set(columns)),'Missing/duplicate original CSV columns')
        require(config['value'] in columns,'Missing original measurement field')
        namefield='Station' if 'Station' in columns else 'Location Name'
        timefield='Data Acquisition Time' if 'Data Acquisition Time' in columns else 'Monitoring Date'
        idfield=next((c for c in ['Station ID','Station Code','Site Code'] if c in columns),None)
        for line,row in enumerate(reader,2):
            require(None not in row and all(v is not None for v in row.values()),'Malformed CSV row shape')
            count+=1;name=row[namefield];names[name]+=1;agencies[row.get('Agency','Karnataka SW SF')]+=1
            if idfield:codes.add(row[idfield])
            try:when=parse_timestamp(row[timefield],config['frequency']);years[when[:4]]+=1
            except ValueError:
                malformed_dates+=1
                if len(invalid_examples)<5:invalid_examples.append({'line':line,'field':timefield})
                require(match_station(row,identities,idfield) is None,'Pilot station has malformed source timestamp')
                continue
            try:value=numeric(row[config['value']],config['variable'])
            except ValueError:
                invalid_values+=1
                if len(invalid_examples)<5:invalid_examples.append({'line':line,'field':config['value']})
                require(not (match_station(row,identities,idfield) and START<=when[:10]<=END),
                        'Pilot window contains invalid source value')
                continue
            if value is None:missing+=1
            key=(row.get(idfield) if idfield else (name,row.get('Agency'),row.get('Latitude'),
                                                 row.get('Longitude'),row.get('Local River')),when)
            fingerprint=hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='SlNo'},
                                                 separators=(',',':')).encode()).digest()
            if key in seen:
                if seen[key]==fingerprint:duplicates+=1
                else:conflicts+=1
            else:seen[key]=fingerprint
            station_id=match_station(row,identities,idfield)
            if station_id and START<=when[:10]<=END:
                selected.append(normalize(row,config,identities[station_id],station_id,line,resource))
    return selected,{'original_columns':columns,'total_source_rows':count,'distinct_station_names':len(names),
        'original_station_id_fields':[idfield] if idfield else [],'source_names':dict(sorted(names.items())),
        'source_station_codes':sorted(codes),'agencies':dict(agencies),'years':dict(sorted(years.items())),
        'missing_values':missing,'malformed_dates':malformed_dates,'invalid_values':invalid_values,
        'duplicate_station_timestamp_rows':duplicates,'conflicting_station_timestamp_rows':conflicts,
        'invalid_examples':invalid_examples,'units':config['units'],'units_status':'source_field_verified' if config['units'] else 'not_documented',
        'quality_columns':[c for c in columns if any(t in c.lower() for t in ['quality','status','flag'])],
        'selected_rows':len(selected),'current_lgd_mapping':'not_inferred_from_source_geographic_codes'}


def pdf_text(pdf,page):
    return subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(pdf),'-'],
                          capture_output=True,check=True,timeout=30).stdout.decode('utf-8')


def dms(value):
    m=re.fullmatch(r'(\d+)°(\d+)\'(\d+)"',value)
    require(m is not None,'Unrecognized published DMS coordinate')
    a,b,c=map(int,m.groups()); require(b<60 and c<60,'Invalid DMS')
    return a+b/60+c/3600


def history_identity(text,canonical,config):
    name=re.search(r'Site\s*:\s*(.*?)\s+Code\s*:\s*(\S+)',text)
    coords=re.search(r'Latitude\s*:\s*(\S+)\s+Longitude\s*:\s*(\S+)',text)
    gauge=re.search(r'^\s*Gauge\s*:\s*([\d/]+)',text,re.M)
    require(name and coords and gauge,'Missing official Year Book history identity')
    opening=datetime.strptime(gauge[1],'%d/%m/%Y').date().isoformat()
    metadata_open=datetime.strptime(canonical['source_start_dates_cell'].splitlines()[0],'%d/%m/%Y').date().isoformat()
    require(opening==metadata_open,'Historical/current gauge opening conflict; identity unresolved')
    require('Krishna' in text and 'Karnataka' in text,'History geography mismatch')
    return {'canonical_cwc_station_id':canonical['source_station_id'],'stage4a_source_name':canonical['official_name'],
        'yearbook_name':name[1],'yearbook_legacy_code':name[2],'history_pdf_page':config['history_page'],
        'gauge_opening_date':opening,'gauge_opening_corroborated':True,
        'yearbook_latitude':dms(coords[1]),'yearbook_longitude':dms(coords[2]),
        'stage4a_latitude':canonical['latitude'],'stage4a_longitude':canonical['longitude'],
        'csv_names':[config['csv_name']],'csv_local_rivers':[config['local_river']],
        'identity_basis':'Independent official CWC history/current metadata gauge opening date, name/river/agency; no fuzzy/geocoded identity',
        'source_history_text':text,'nwdp_vs_stage4a_coordinate_status':None}


def coordinate_comparison(latitude,longitude,other_latitude,other_longitude):
    require(all(math.isfinite(v) for v in [latitude,longitude,other_latitude,other_longitude]),'Invalid coordinate')
    return 'source_coordinate_conflict' if (abs(latitude-other_latitude)>.0005 or abs(longitude-other_longitude)>.0005) else 'verified_source_coordinate'


def parse_yearbook_xml(xml,identity,page):
    require(b'<!ENTITY' not in xml.upper(),'Unsafe PDF XML')
    p=ET.fromstring(xml).find('.//{*}page');require(p is not None,'Missing PDF page')
    words=[{'text':w.text or '', 'x':(float(w.attrib['xMin'])+float(w.attrib['xMax']))/2,
            'y':(float(w.attrib['yMin'])+float(w.attrib['yMax']))/2} for w in p.findall('.//{*}word')]
    headers={m:[w for w in words if w['text']==m] for m in ['Jun','Jul','Aug','Sep']}
    require(all(len(v)==1 for v in headers.values()),'Ambiguous month header')
    require(' '.join(w['text'] for w in words).find(identity['yearbook_legacy_code'])>=0,'Wrong station table')
    bounds={m:((headers[prev][0]['x']+headers[m][0]['x'])/2,(headers[m][0]['x']+headers[nxt][0]['x'])/2)
            for m,prev,nxt in [('Jul','Jun','Aug'),('Aug','Jul','Sep')]}
    day_headers=[w for w in words if w['text']=='Day']
    require(len(day_headers)==1,'Ambiguous day column')
    row_anchors=sorted([w for w in words if abs(w['x']-day_headers[0]['x'])<5 and re.fullmatch(r'\d+',w['text'])
                       and 1<=int(w['text'])<=31 and w['y']>headers['Jul'][0]['y']],key=lambda w:w['y'])
    require(len(row_anchors)==31 and [int(w['text']) for w in row_anchors]==list(range(1,32)),'Missing/ambiguous table day rows')
    result=[]
    for anchor in row_anchors:
        day=int(anchor['text'])
        for month,number in [('Jul',7),('Aug',8)]:
            when=date(2019,number,day).isoformat()
            if not START<=when<=END:continue
            lo,hi=bounds[month]
            cell=sorted([w for w in words if lo<=w['x']<hi and abs(w['y']-anchor['y'])<3],key=lambda w:w['x'])
            tokens=[w['text'] for w in cell]
            require(len(tokens) in {2,3},'Missing/malformed daily WL/Q cells')
            flag=tokens[2] if len(tokens)==3 else ''
            require(flag in {'','*','#'},'Unknown publisher quality flag')
            for variable,index,unit in [('water_level',0,'m (m.s.l)'),('discharge',1,'cumec')]:
                value=numeric(tokens[index],variable)
                result.append({'canonical_cwc_station_id':identity['canonical_cwc_station_id'],
                    'source_station_id':identity['yearbook_legacy_code'],'source_station_name':identity['yearbook_name'],
                    'observation_date':when,'variable':variable,'original_value':tokens[index],'value':value,'units':unit,
                    'source_quality_flag':flag if variable=='discharge' else '',
                    'measurement_status':('computed' if flag=='*' else 'discarded_replaced_by_rating_curve' if flag=='#' else 'observed') if variable=='discharge' else 'published_corresponding_mean_water_level',
                    'temporal_semantics':'daily_mean' if variable=='water_level' else 'daily_observed_or_computed; measurement_time_unspecified',
                    'source_pdf_page':page,'original_cell_tokens':tokens,
                    'historical_availability_status':'availability_semantics_unverified'})
    require(len(result)==54,'Unexpected bounded Year Book rows')
    return result


def yearbook_rows(pdf,identity,page):
    xml=subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-bbox-layout',str(pdf),'-'],
                       capture_output=True,check=True,timeout=30).stdout
    return parse_yearbook_xml(xml,identity,page)


def compare_values(a,b):
    if a is None or b is None:return 'unavailable_in_one_source'
    first,second=Decimal(a),Decimal(b)
    if first==second:return 'exact_match'
    step=Decimal('1') if second>=1000 else Decimal('.1') if second>=100 else Decimal('.01') if second>=10 else Decimal('.001')
    return 'rounding_equivalent' if first.quantize(step,rounding=ROUND_HALF_UP)==second else 'discrepancy'


def cross_compare(observations,yearbook):
    indexed=defaultdict(list)
    for r in observations:
        if r['variable']=='discharge':indexed[(r['canonical_cwc_station_id'],r['observation_time'][:10])].append(r)
    result=[]
    for reference in yearbook:
        if reference['variable']!='discharge':continue
        candidates=indexed[(reference['canonical_cwc_station_id'],reference['observation_date'])]
        require(len(candidates)<=1,'Conflicting pilot station-date discharge rows; never choose silently')
        row=candidates[0] if candidates else None
        require(row is None or (row['units']=='m3/sec' and reference['units']=='cumec'),
                'Incompatible discharge units; no implicit conversion')
        result.append({'canonical_cwc_station_id':reference['canonical_cwc_station_id'],
            'observation_date':reference['observation_date'],'variable':'discharge',
            'nwdp_original_value':row['original_value'] if row else None,'nwdp_units':row['units'] if row else None,
            'nwdp_observation_time':row['observation_time'] if row else None,
            'nwdp_source_row_number':row['source_row_number'] if row else None,
            'yearbook_original_value':reference['original_value'],'yearbook_units':reference['units'],
            'yearbook_measurement_status':reference['measurement_status'], 'yearbook_flag':reference['source_quality_flag'],
            'classification':compare_values(row['value'] if row else None,reference['value']),
            'time_semantics':'Date-level source comparison only; original measuring time and finalisation may differ',
            'measured_confirmation':bool(row and reference['measurement_status']=='observed' and compare_values(row['value'],reference['value']) in {'exact_match','rounding_equivalent'})})
    return result


def table_bytes(rows):
    require(rows,'Never fabricate an empty observation table')
    fields=list(rows[0]);require(all(list(r)==fields for r in rows),'Inconsistent table schema')
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
    for row in rows:
        writer.writerow({k:json.dumps(v,sort_keys=True,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    return stream.getvalue().encode()


def build_inputs(raw=RAW):
    raw=Path(raw);canonical={r['source_station_id']:r for r in read(ROOT/'data/working/karnataka_hydrology_stations_v1/station_registry.json')}
    identities={key:history_identity(pdf_text(raw/'krishna_wyb2019_20.pdf',c['history_page']),canonical[key],c) for key,c in PILOTS.items()}
    # Source CSV first rows provide coordinates; all selected rows subsequently require
    # those same coordinates via the independent source census identity audit.
    coords={}
    with (raw/'river_discharge_manual_daily_cwc_ka_2001_2025.csv').open(newline='') as f:
        for r in csv.DictReader(f):
            for key,c in PILOTS.items():
                if r['Station']==c['csv_name']:
                    point=(float(r['Latitude']),float(r['Longitude']))
                    require(key not in coords or coords[key]==point,'Changing source station coordinates')
                    coords[key]=point
    require(set(coords)==set(PILOTS),'Missing CWC station-name identity evidence')
    for key,i in identities.items():
        lat,lon=coords[key];i.update(nwdp_latitude=lat,nwdp_longitude=lon)
        i['nwdp_vs_stage4a_coordinate_status']=coordinate_comparison(lat,lon,i['stage4a_latitude'],i['stage4a_longitude'])
        i['yearbook_vs_nwdp_coordinate_status']=coordinate_comparison(lat,lon,i['yearbook_latitude'],i['yearbook_longitude'])
        i['metadata_coordinates_changed']=False
    resources=[];observations=[]
    for name,c in CONFIG.items():
        side=read(raw/(name+'_metadata.json.json'))
        r=resource_metadata((raw/(name+'_metadata.json')).read_bytes(),c['id'],(raw/(name+'_resource.html')).read_bytes(),retrieval_time=side['retrieved_at'])
        r.update(frequency=c['frequency'],variable=c['variable'],units=c['units'],
            resource_page_url=read(raw/(name+'_resource.html.json'))['source_url'])
        p=raw/r['original_filename'];download=read(raw/(p.name+'.json'))
        require(download['status']=='retrieved' and download['bytes']==p.stat().st_size==r['portal_size'],'Incomplete official CSV')
        require(digest(p)==download['sha256'] and digest(p,'md5')==r['portal_hash']==download['md5'],'Official CSV hash mismatch')
        r['download']=download
        selected,audit=csv_audit(p,c,identities,r)
        r['schema_and_census']=audit;resources.append(r);observations+=selected
    # Original bounds, IDs, values, units, hourly rows preserved without aggregation.
    keys=[(r['source_resource_id'],r['canonical_cwc_station_id'],r['variable'],r['observation_time']) for r in observations]
    require(len(keys)==len(set(keys)),'Duplicate/conflicting pilot observation keys')
    for r in observations:
        i=identities[r['canonical_cwc_station_id']]
        require((float(r['source_record']['Latitude']),float(r['source_record']['Longitude']))==(i['nwdp_latitude'],i['nwdp_longitude']),'Gauge/discharge source coordinate conflict')
    observations.sort(key=lambda r:(r['canonical_cwc_station_id'],r['variable'],r['observation_time']))
    yearbook=[]
    for key,i in identities.items():yearbook+=yearbook_rows(raw/'krishna_wyb2019_20.pdf',i,PILOTS[key]['table_page'])
    comparison=cross_compare(observations,yearbook)
    return identities,resources,observations,yearbook,comparison


def summary(identities,resources,observations,comparison):
    pilots=[]
    for key,c in PILOTS.items():
        rows=[r for r in observations if r['canonical_cwc_station_id']==key]
        vars={}
        for v in ['water_level','discharge']:
            selected=[r for r in rows if r['variable']==v];dates={r['observation_time'][:10] for r in selected};valid=[r for r in selected if r['value'] is not None]
            vars[v]={'rows':len(selected),'valid_rows':len(valid),'dates':len(dates),'date_list':sorted(dates),
                'event_rows':sum(c['event_start']<=r['observation_time'][:10]<=c['event_end'] and r['value'] is not None for r in selected),
                'missing_dates':[date.fromisoformat(START).fromordinal(date.fromisoformat(START).toordinal()+n).isoformat() for n in range(27) if date.fromisoformat(START).fromordinal(date.fromisoformat(START).toordinal()+n).isoformat() not in dates]}
        pilots.append({'canonical_cwc_station_id':key,'variables':vars,
            'comparison_classes':dict(Counter(r['classification'] for r in comparison if r['canonical_cwc_station_id']==key)),
            'coordinate_status':identities[key]['nwdp_vs_stage4a_coordinate_status']})
    recovered=any(p['variables']['water_level']['event_rows'] or p['variables']['discharge']['event_rows'] for p in pilots)
    return {'readiness':'measured_event_hydrology_recovered' if recovered else 'source_identity_unresolved',
        'pilot':pilots,'observation_rows':len(observations), 'measured_discharge_corroborated_rows':sum(r['measured_confirmation'] for r in comparison),
        'comparison_counts':dict(Counter(r['classification'] for r in comparison)),
        'all_resources_verified':len(resources),'publication_counts':dict(Counter(r['publication_handling'] for r in resources)),
        'state_agency_cwc_matched_rows':sum(r['schema_and_census']['selected_rows'] for r in resources if r['producer']!='CWC'),
        'water_level_comparison':'hourly observations versus corresponding daily mean: not equivalent; no numeric comparison',
        'availability_status':'availability_semantics_unverified','threshold_comparisons':0,'features':0,'labels':0}


def assemble(raw=RAW):
    identities,resources,observations,yearbook,comparison=build_inputs(raw)
    return {'raw_source_registry.json':json_bytes(resources),'identity_evidence.json':json_bytes(identities),
        'observations.csv':table_bytes(observations),'yearbook_context.csv':table_bytes(yearbook),
        'cross_source_comparison.csv':table_bytes(comparison)},summary(identities,resources,observations,comparison)


def freeze(output=OUTPUT,raw=RAW):
    output=Path(output);require(not output.exists(),'Immutable completed output exists')
    artifacts,result=assemble(raw)
    manifest={'version':'karnataka_hydrology_2019_pilot_v1','created_at':datetime.now(timezone.utc).isoformat(),
        'method':METHOD,'summary':result,'files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for k,v in artifacts.items()},
        'source_inputs':[file_record(p) for p in sorted(Path(raw).iterdir()) if p.is_file()],
        'protected_foundation_inputs':[file_record(p) for p in sorted((ROOT/'data/working/karnataka_hydrology_stations_v1').iterdir()) if p.is_file()],
        'processing_code':file_record(Path(__file__))}
    output.mkdir(parents=True)
    for name,body in artifacts.items():(output/name).write_bytes(body)
    (output/'manifest.json').write_bytes(json_bytes(manifest))
    return result


def validate(output=OUTPUT):
    output=Path(output);m=read(output/'manifest.json')
    for name,r in m['files'].items():
        require(Path(name).name==name,'Unsafe output path')
        p=output/name;require(p.stat().st_size==r['bytes'] and digest(p)==r['sha256'],'Output integrity mismatch')
    for r in m['source_inputs']+m['protected_foundation_inputs']+[m['processing_code']]:
        p=ROOT/r['path'];require(p.stat().st_size==r['bytes'] and digest(p)==r['sha256'],'Input integrity mismatch')
    raw=(ROOT/m['source_inputs'][0]['path']).parent
    artifacts,result=assemble(raw)
    require(result==m['summary'],'Summary reproduction failed')
    for name,body in artifacts.items():require(body==(output/name).read_bytes(),'Source-to-table reproduction failed')
    return result


def public_manifest(output=OUTPUT):
    m=read(Path(output)/'manifest.json');resources=read(Path(output)/'raw_source_registry.json')
    sources=[]
    for r in resources:
        sources.append({k:r[k] for k in ['dataset_title','resource_title','producer','resource_id','download_url',
            'resource_page_url','portal_date_range_label','frequency','variable','units','format','portal_update',
            'resource_page_update','resource_licence','licence_id','publication_handling','retrieval_time','portal_size','portal_hash']})
        sources[-1]['download']={k:r['download'][k] for k in ['original_filename','bytes','sha256','md5','retrieved_at','http_status','status']}
        sources[-1]['source_census']={k:r['schema_and_census'][k] for k in ['original_columns','total_source_rows','distinct_station_names',
            'missing_values','malformed_dates','invalid_values','duplicate_station_timestamp_rows','conflicting_station_timestamp_rows','selected_rows','units_status','quality_columns']}
    return {'version':m['version'],'created_at':m['created_at'],'method':m['method'],'summary':m['summary'],
        'files':m['files'],'local_manifest_sha256':digest(Path(output)/'manifest.json'),'processing_code':m['processing_code'],
        'sources':sources,'source_response_checksums':m['source_inputs'],
        'schema':{'observations':'canonical/source identities, original timestamp/value/units/quality fields, actual frequency, separate retrieval/availability times, original row',
                  'comparison':'date-level discharge source values, original computed/discarded flags, exact/rounding/discrepancy/unavailable classes',
                  'yearbook':'original daily Q and corresponding mean WL; computed records never promoted to direct measurements'}}


def fetch_worker(url,path,byte_ceiling):
    """Child deadline enforced by caller; requests optional in research env only."""
    import requests
    count=0;http={}
    try:
        with requests.get(url,stream=True,timeout=(10,20)) as response,Path(path).open('xb') as stream:
            http={'http_status':response.status_code,'headers':{k:v for k,v in response.headers.items() if k.lower() in {'content-type','content-length','content-disposition','etag','last-modified','content-md5'}}}
            for part in response.iter_content(65536):
                require(count+len(part)<=byte_ceiling,'Download byte ceiling')
                stream.write(part);count+=len(part)
            http['status']='retrieved' if response.ok else 'http_failure'
    except Exception as exc:
        http.update(status='retrieval_failed',error=type(exc).__name__+': '+str(exc))
    return http


def fetch(url,path,*,deadline=180,byte_ceiling=128*1024*1024):
    """One published URL, one attempt. Original or partial bytes never overwritten."""
    path=Path(path);require(not path.exists() and not Path(str(path)+'.json').exists(),'Source already exists; never overwrite')
    require(0<deadline<=180 and 0<byte_ceiling<=512*1024*1024,'Unsafe download bounds')
    require(url.startswith('https://nwdp.nwic.gov.in/dataset/') and '/download/' in url,'Use the published official Download URL')
    path.parent.mkdir(parents=True,exist_ok=True)
    record={'source_url':url,'started_at':datetime.now(timezone.utc).isoformat(),'deadline_seconds':deadline,'byte_ceiling':byte_ceiling}
    try:
        result=subprocess.run([sys.executable,str(Path(__file__)),'_fetch_worker',url,str(path),str(byte_ceiling)],
                              capture_output=True,check=True,timeout=deadline)
        record.update(json.loads(result.stdout))
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as exc:
        record.update(status='retrieval_failed',error=type(exc).__name__)
    record.update(retrieved_at=datetime.now(timezone.utc).isoformat(),bytes=path.stat().st_size if path.exists() else 0,
                  sha256=digest(path) if path.exists() else None,md5=digest(path,'md5') if path.exists() else None)
    Path(str(path)+'.json').write_bytes(json_bytes(record))
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','validate','fetch','_fetch_worker']);p.add_argument('args',nargs='*');p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--raw',type=Path,default=RAW)
    p.add_argument('--deadline',type=int,default=180);p.add_argument('--byte-ceiling',type=int,default=128*1024*1024)
    a=p.parse_args()
    if a.command=='build':result=freeze(a.output,a.raw)
    elif a.command=='validate':result=validate(a.output)
    elif a.command=='fetch':result=fetch(*a.args,deadline=a.deadline,byte_ceiling=a.byte_ceiling)
    else:result=fetch_worker(a.args[0],a.args[1],int(a.args[2]))
    print(json.dumps(result,indent=2))
