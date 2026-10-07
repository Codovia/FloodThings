#!/usr/bin/env python3
"""Offline, immutable Stage 4D evidence from retained official GloFAS/CWC files.

No credentials, network requests, station-coordinate repairs, labels or features.
All detailed station/series/comparison evidence remains local.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'data/raw/reference/glofas_v5_static'
META = ROOT / 'data/raw/reference/glofas_v5_pilot_metadata_v1'
MODEL = ROOT / 'data/working/glofas_access_smoke_v1/glofas_v5_karnataka_pilot_2019_jul_aug.nc'
SEMANTICS = ROOT / 'data/working/karnataka_hydrology_semantics_v1'
PRIOR = ROOT / 'data/working/karnataka_hydrology_2019_reconciled_v1'
PILOT = ROOT / 'data/working/karnataka_hydrology_2019_pilot_v1'
PDF = ROOT / 'data/raw/reference/stage3e3_v1/cwc_station_metadata.pdf'
OUTPUT = ROOT / 'data/working/karnataka_glofas_2019_pilot_v1'
PUBLIC = ROOT / 'data/reference/karnataka_glofas_2019_pilot_v1/manifest.json'
EXPECTED_MODEL = '563ef9718aaa99b84c4d843d1384970635fb1b83b7a63675980d6b3b1dd3e90d'
EXPECTED_AREA = '798b89dd5881ff17e6fc6ffb1981ab82784a3ae46289cb016bd07d4aed43706f'
STATIONS = ['CW1KRU000083', 'CW1KRU000212', 'CW1KRU000339']
LDD = {1:(1,-1), 2:(1,0), 3:(1,1), 4:(0,-1), 5:(0,0),
       6:(0,1), 7:(-1,-1), 8:(-1,0), 9:(-1,1)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': digest(path)}


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def table(records):
    require(bool(records), 'No fabricated empty evidence table')
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(records[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(records)
    return out.getvalue().encode()


def prior_gate():
    for folder in [PILOT, PRIOR, SEMANTICS]:
        for name, expected in read(folder / 'manifest.json')['files'].items():
            require(Path(name).name == name, 'Unsafe previous manifest path')
            p = folder / name
            require(digest(p) == expected['sha256'] and p.stat().st_size == expected['bytes'], 'Protected version changed')
    quality = rows(PRIOR / 'observation_quality.csv')
    observations = rows(PILOT / 'observations.csv')
    comparisons = rows(PRIOR / 'discharge_reconciliation.csv')
    require(len(quality) == len(observations) == 1697 and len(comparisons) == 81, 'Protected counts changed')
    require(all(all(q[k] == v for k,v in o.items()) for q,o in zip(quality, observations)), 'Protected source values changed')
    eligible = [q for q in quality if q['analysis_eligibility'] == 'eligible_with_quality_caveat']
    require(Counter(q['canonical_cwc_station_id'] for q in eligible) ==
            {STATIONS[0]:2, STATIONS[2]:12}, 'Eligibility expanded')
    require(Counter(c['classification'] for c in comparisons)['source_value_conflict'] == 21 and
            Counter(c['classification'] for c in comparisons)['yearbook_computed_vs_nwdp'] == 12,
            'Disagreements changed')
    return eligible


def coordinates(station):
    require(station['canonical_coordinate_selected'] is False and station['coordinates_modified'] is False,
            'Canonical coordinate must remain unselected')
    result = []
    for source in station['source_history']:
        if 'original' in source:
            pos = [source['original']['latitude'], source['original']['longitude']]
        elif 'coordinates' in source:
            pos = source['coordinates']
        else:
            pos = [float(source['original_fields'][k][0]) for k in ['Latitude','Longitude']]
        require(len(pos) == 2 and -90 <= pos[0] <= 90 and -180 <= pos[1] <= 180, 'Invalid source coordinate')
        result.append({'source':source['source'], 'latitude':pos[0], 'longitude':pos[1],
            'source_publication':source.get('publication', source.get('resource_update')),
            'source_page':source.get('page')})
    require(len(result) == 4, 'All four source histories required')
    return result


def distance(a, b):
    la, lb = math.radians(a[0]), math.radians(b[0])
    h = math.sin((lb-la)/2)**2 + math.cos(la)*math.cos(lb)*math.sin(math.radians(b[1]-a[1])/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def nearest(axis, value):
    axis = np.asarray(axis)
    require(axis.ndim == 1 and len(axis)>0 and np.isfinite(axis).all(), 'Invalid grid axis')
    require(float(axis.min()) <= value <= float(axis.max()), 'Coordinate outside retained grid')
    # Exact ties use the first source index; no axis inversion or resampling.
    return int(np.argmin(np.abs(axis-value)))


def aligned(axis, value):
    index = nearest(axis, value)
    require(abs(float(axis[index])-value) < 1e-8, 'Static/historical grids do not align')
    return index


def area_comparison(area_m2, cwc_km2):
    require(cwc_km2 > 0 and math.isfinite(cwc_km2), 'Unverified/invalid CWC area')
    if area_m2 is None:
        return {'upstream_area_km2':None,'signed_difference_km2':None,'absolute_difference_km2':None,'percent_difference':None}
    require(math.isfinite(area_m2) and area_m2 >= 0, 'Invalid upstream area')
    model = area_m2/1e6
    return {'upstream_area_km2':model,'signed_difference_km2':model-cwc_km2,
        'absolute_difference_km2':abs(model-cwc_km2),'percent_difference':100*abs(model-cwc_km2)/cwc_km2}


def scalar(value):
    if np.ma.is_masked(value): return None
    value = float(value)
    return value if math.isfinite(value) else None


def cwc_area(station, text):
    require('Catchment' in text and re.search(r'\bArea\b', text) and re.search(r'Sq\.km', text), 'CWC area heading/units absent')
    pattern = r'(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+(?:\.\d+)?)\s+HO(?:/FF)?\s+' + station['station_id']
    matches = re.findall(pattern, text)
    require(len(matches) == 1, 'Ambiguous CWC catchment row')
    source = next(s for s in station['source_history'] if s['source']=='CWC_HO2025')['original']
    require([float(x) for x in matches[0][:2]] == [source['latitude'], source['longitude']] and
            float(matches[0][2]) == float(source['source_cells'][9]), 'CWC row/source mismatch')
    return float(matches[0][2])


def mapping(direct, candidates):
    unique = sorted(set(d['cell_id'] for d in direct))
    if len(unique) != 1:
        return {'status':'glofas_cell_match_ambiguous','selected_cell':None,
            'coordinate_candidate_cells':unique,'reason':'Official coordinate variants identify different cells; no canonical station point'}
    row = next(c for c in candidates if c['cell_id']==unique[0])
    good = row['channel_positive'] and row['percent_difference'] is not None and row['percent_difference'] <= 10
    return {'status':'glofas_cell_match_supported' if good else 'glofas_cell_match_unresolved',
        'selected_cell':unique[0] if good else None, 'coordinate_candidate_cells':unique,
        'reason':'All coordinate variants converge; official channel and <=10 percent area screen; coordinate/river identity caveats remain'
        if good else 'Nearest cell not supported by channel/area evidence; alternatives retained without forced selection'}


def intervals(times):
    require(len(times)==62 and times[0]==datetime(2019,7,2,tzinfo=timezone.utc) and
            times[-1]==datetime(2019,9,1,tzinfo=timezone.utc) and
            all(b-a==timedelta(days=1) for a,b in zip(times,times[1:])), 'Unexpected model time grid')
    return [{'model_valid_time':t.isoformat(), 'interpreted_interval_start':(t-timedelta(days=1)).isoformat(),
        'interpreted_interval_end':t.isoformat(), 'interval_status':'documented_last24h_end_timestamp_file_bounds_absent'} for t in times]


def comparison_eligible(row):
    return (row['variable']=='discharge' and row['frequency']=='daily' and row['units']=='m3/sec' and
        row['analysis_eligibility']=='eligible_with_quality_caveat' and row['canonical_cwc_station_id'] in {STATIONS[0],STATIONS[2]})


def comparison_evidence(eligible):
    require(len(eligible)==14 and all(comparison_eligible(q) for q in eligible), 'Only approved discharge subset may enter review')
    return [{'station_id':q['canonical_cwc_station_id'], 'hydrology_source_type':'measured_cwc_nwdp',
        'source_observation_time':q['observation_time'], 'source_timezone':q['observation_timezone'],
        'source_value':q['original_value'], 'source_units':q['units'], 'source_row':q['source_row_number'],
        'source_resource_id':q['source_resource_id'], 'source_quality_status':q['source_quality_status'],
        'analysis_eligibility':q['analysis_eligibility'], 'modelled_source_type':'modelled_glofas',
        'paired_modelled_discharge':None, 'model_minus_measured':None,
        'comparison_status':'temporal_semantics_unresolved',
        'reason':'CWC dated gauge reading/timezone/daily aggregation is not a demonstrated equivalent of model 24h mean'} for q in eligible]


def inspect_nc(path):
    from netCDF4 import Dataset
    with Dataset(path) as d:
        return {'format':d.data_model, 'dimensions':{k:len(v) for k,v in d.dimensions.items()},
            'global_attributes':{k:str(d.getncattr(k)) for k in d.ncattrs()},
            'variables':{k:{'dimensions':list(v.dimensions),'dtype':str(v.dtype),
                'attributes':{a:str(v.getncattr(a)) for a in v.ncattrs()}} for k,v in d.variables.items()}}


def source_inputs():
    paths = [MODEL, STATIC/'upArea_repaired_correctedmetadata_3000.nc',STATIC/'chan_Global_03min.nc',STATIC/'ldd_repaired.nc',
        SEMANTICS/'coordinate_provenance.json', PDF, PRIOR/'observation_quality.csv', PRIOR/'discharge_reconciliation.csv',
        *[p for p in META.iterdir() if p.is_file()], *[p for p in STATIC.iterdir() if p.is_file() and p.suffix != '.nc']]
    return [record(p) for p in sorted(set(paths))]


def assemble():
    from netCDF4 import Dataset, num2date
    require(digest(MODEL)==EXPECTED_MODEL and digest(STATIC/'upArea_repaired_correctedmetadata_3000.nc')==EXPECTED_AREA,
            'Supplied source checksum mismatch')
    eligible = prior_gate(); protocol = read(META/'search_protocol.json')
    require(protocol['neighborhood_half_width_cells']==2 and protocol['maximum_source_distance_m']==12000 and
            protocol['plausible_area_screen_percent']==10, 'Declared search changed')
    readme = (META/'release_readme.txt').read_text(); changelog = (META/'changelog.txt').read_text()
    require('same\n  hydrological model set up as used for GloFAS v5.x' in changelog and 'v2.1.1 (2026-09-03)' in changelog,
            'Version compatibility not documented')
    require('upArea_repaired_correctedmetadata_3000.nc (accumulated area of all upstream hydrologically connected pixels, m2)' in readme,
            'Upstream-area units not documented')
    histories = read(SEMANTICS/'coordinate_provenance.json')
    require([s['station_id'] for s in histories]==STATIONS, 'Station scope changed')
    model_meta = inspect_nc(MODEL); area_meta = inspect_nc(STATIC/'upArea_repaired_correctedmetadata_3000.nc')
    direct_rows=[]; candidates=[]; maps=[]; series=[]; hydrographs=[]; cwc_sources=[]
    with Dataset(MODEL) as model, Dataset(STATIC/'upArea_repaired_correctedmetadata_3000.nc') as area, \
            Dataset(STATIC/'chan_Global_03min.nc') as channel, Dataset(STATIC/'ldd_repaired.nc') as direction:
        q = model['avg_dis']
        require(q.getncattr('GRIB_configuration')=='v5.0' and q.units=='m**3 s**-1' and
                q.getncattr('GRIB_stepType')=='avg' and q.dimensions==('valid_time','latitude','longitude'), 'Model version/variable/units changed')
        lat=np.asarray(model['latitude'][:]);lon=np.asarray(model['longitude'][:])
        require(np.allclose(np.diff(lat),-.05,rtol=0,atol=1e-10) and np.allclose(np.diff(lon),.05,rtol=0,atol=1e-10),'Native grid changed')
        ui=[aligned(area['lat'][:],float(x)) for x in lat];uj=[aligned(area['lon'][:],float(x)) for x in lon]
        for other in [channel,direction]:
            require(np.allclose(other['lat'][:],area['lat'][:],atol=1e-10,rtol=0) and
                    np.allclose(other['lon'][:],area['lon'][:],atol=1e-10,rtol=0),'Static grids changed')
        times=list(num2date(model['valid_time'][:],model['valid_time'].units,calendar=model['valid_time'].calendar,
            only_use_cftime_datetimes=False,only_use_python_datetimes=True))
        time_rows=intervals([t.replace(tzinfo=timezone.utc) for t in times])
        allq=q[:]; valid=np.asarray(np.ma.filled(allq,np.nan));require(np.nanmin(valid)>=0,'Negative discharge')
        model_meta['technical_counts']={'values':int(valid.size),'finite':int(np.isfinite(valid).sum()),
            'missing':int((~np.isfinite(valid)).sum()),'minimum':float(np.nanmin(valid)),'maximum':float(np.nanmax(valid))}
        for station in histories:
            coords=coordinates(station);source=next(s for s in station['source_history'] if s['source']=='CWC_HO2025');page=source['page']
            text=subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(PDF),'-'],check=True,capture_output=True,text=True,timeout=30).stdout
            ca=cwc_area(station,text);cwc_sources.append({'station_id':station['station_id'],'area_km2':ca,
                'source_page':page,'source_heading':'Catchment Area (Sq.km)','source_pdf_sha256':digest(PDF),'source_vintage':'April2025; not proven historical2019 catchment reference'})
            positions=set();direct=[]
            for c in coords:
                i=nearest(lat,c['latitude']);j=nearest(lon,c['longitude']);cell=f'{i}:{j}'
                r={'station_id':station['station_id'],**c,'cell_id':cell,'cell_latitude':float(lat[i]),'cell_longitude':float(lon[j]),
                    'distance_m':distance([c['latitude'],c['longitude']],[float(lat[i]),float(lon[j])]),
                    **area_comparison(scalar(area['Band1'][ui[i],uj[j]]),ca),'cwc_catchment_area_km2':ca,
                    'canonical_coordinate_selected':False}
                direct.append(r);direct_rows.append(r)
                for a in range(max(0,i-2),min(len(lat),i+3)):
                    for b in range(max(0,j-2),min(len(lon),j+3)):positions.add((a,b))
            local=[]
            for i,j in sorted(positions):
                distances=[distance([c['latitude'],c['longitude']],[float(lat[i]),float(lon[j])]) for c in coords]
                if min(distances)>12000:continue
                ar=scalar(area['Band1'][ui[i],uj[j]]);ch=scalar(channel['Band1'][ui[i],uj[j]])
                ld=scalar(direction['Band1'][ui[i],uj[j]]);code=int(ld) if ld is not None else None
                require(code in set(LDD)|{None}, 'Unrecognised direction code')
                downstream=None;down_area=None
                if code and code!=5:
                    dr,dc=LDD[code];a,b=i+dr,j+dc
                    if 0<=a<len(lat) and 0<=b<len(lon):
                        downstream=f'{a}:{b}';down_area=scalar(area['Band1'][ui[a],uj[b]])
                comp=area_comparison(ar,ca);cell=f'{i}:{j}';direct_cell=cell in {r['cell_id'] for r in direct}
                plausible=ch==1 and comp['percent_difference'] is not None and comp['percent_difference']<=10
                r={'station_id':station['station_id'],'cell_id':cell,'row':i,'column':j,'latitude':float(lat[i]),'longitude':float(lon[j]),
                    'minimum_source_distance_m':min(distances),'maximum_source_distance_m':max(distances),
                    'channel_positive':ch==1,'channel_mask_status':'positive' if ch==1 else 'not_marked_or_nodata',
                    'upstream_area_m2':ar,**comp,'cwc_catchment_area_km2':ca,'direct_coordinate_candidate':direct_cell,
                    'area_screen_pass':plausible,'ldd_code':code,'downstream_cell':downstream,
                    'downstream_upstream_area_m2':down_area,'extract_series':ch==1 and (direct_cell or plausible)}
                local.append(r);candidates.append(r)
            result={'station_id':station['station_id'],'station_name':station['name'],**mapping(direct,local),
                'canonical_coordinate_selected':False,'calibration_relation':'glofas_calibration_relation_unresolved',
                'area_screen_alternatives':[r['cell_id'] for r in local if r['area_screen_pass']],
                'local_model_topology_only':True}
            maps.append(result)
            for candidate in local:
                if not candidate['extract_series']:continue
                i,j=candidate['row'],candidate['column'];values=[scalar(v) for v in allq[:,i,j]]
                require(all(v is None or v>=0 for v in values),'Invalid candidate discharge')
                for clock,value in zip(time_rows,values):
                    series.append({'station_id':station['station_id'],'cell_id':candidate['cell_id'],
                        'latitude':candidate['latitude'],'longitude':candidate['longitude'],**clock,
                        'hydrology_source_type':'modelled_glofas','dataset_id':'cems-glofas-historical','model_version':'5.0',
                        'variable':'avg_dis','modelled_discharge':value,'units':'m**3 s**-1',
                        'status':'available' if value is not None else 'unavailable','source_sha256':EXPECTED_MODEL,
                        'role':'supported_primary' if candidate['cell_id']==result['selected_cell'] else 'candidate_only'})
                finite=[(k,v) for k,v in enumerate(values) if v is not None]
                peak=max(finite,key=lambda pair:pair[1]) if finite else None
                hydrographs.append({'station_id':station['station_id'],'cell_id':candidate['cell_id'],
                    'valid_days':len(finite),'min_modelled_discharge':min(v for _,v in finite) if finite else None,
                    'max_modelled_discharge':peak[1] if peak else None,
                    'peak_model_valid_time':time_rows[peak[0]]['model_valid_time'] if peak else None,
                    'peak_interpreted_interval_start':time_rows[peak[0]]['interpreted_interval_start'] if peak else None,
                    'role':'supported_primary' if candidate['cell_id']==result['selected_cell'] else 'candidate_only',
                    'use':'descriptive_context_only_not_model_skill_or_flood_threshold'})
    summary={'access':'glofas_v5_access_verified_from_supplied_official_file_not_new_authentication',
        'readiness':'modelled_hydrology_ready_limited','stations':3,'coordinate_variants':len(direct_rows),
        'reviewed_candidates':len(candidates),'extracted_cell_series':len(hydrographs),'modelled_rows':len(series),
        'valid_modelled_rows':sum(r['modelled_discharge'] is not None for r in series),'model_time_steps':62,
        'mapping_status_counts':dict(Counter(r['status'] for r in maps)),
        'approved_measured_rows_reviewed':14,'time_compatible_quantitative_comparisons':0,
        'comparison_status':'temporal_semantics_unresolved','gokak_comparison':'measured_comparison_unavailable',
        'preserved_measured_observations':1697,'preserved_comparisons':81,'preserved_eligible_rows':14,
        'preserved_unresolved_disagreements':33,'labels':0,'features':0,'coordinate_repairs':0}
    limitations={'source_class':'GloFAS is LISFLOOD modelled discharge; never measured CWC/NWDP',
        'time':'Original valid_time retained; separate interpreted preceding24h interval from official end-timestamp documentation. No CF time bounds in file; CWC timezone/averaging equivalence unverified. No automatic date join, numeric differences or skill metrics.',
        'selection':'Static channel/distance/upstream area only; no discharge magnitude selection. <=10 percent is a declared exploratory screen, not proof of river identity or accuracy. All coordinate histories/nearby alternatives retained.',
        'grid':'Native0.05degrees, no rainfall/GFD resampling. Band1 units missing in upstream NetCDF; m2 defined by official README. Zeros/masks not interchangeable.',
        'coordinates':'All three canonical_coordinate_selected remain false; source datums/precision/conflicts uncorrected',
        'calibration':'Station calibration relationships remain unresolved; no independent validation claim',
        'model':'Discrepancies may reflect forcing, routing, catchment representation, reservoirs, calibration, human water management or grid mismatch; no preferred truth or bias correction',
        'reuse':'All detailed station/model/CWC-derived records remain local; source references/checksums/aggregate provenance only published'}
    artifacts={'coordinate_candidates.csv':table(direct_rows),'cell_candidates.csv':table(candidates),
        'station_mapping.json':encode(maps),'cwc_catchment_provenance.json':encode(cwc_sources),
        'daily_modelled_discharge.csv':table(series),'comparison_evidence.csv':table(comparison_evidence(eligible)),
        'hydrograph_context.json':encode(hydrographs),'technical_metadata.json':encode({'historical':model_meta,'upstream':area_meta}),
        'limitations.json':encode(limitations),'source_provenance.json':encode(read(META/'manual_source_provenance.json'))}
    return artifacts,summary


def build(output=OUTPUT):
    output=Path(output);require(not output.exists(),'Immutable Stage4D version exists')
    artifacts,summary=assemble()
    manifest={'version':'karnataka_glofas_2019_pilot_v1','created_at':datetime.now(timezone.utc).isoformat(),
        'inputs':source_inputs(),'processing_code':record(Path(__file__)),'summary':summary,
        'files':{name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in artifacts.items()}}
    output.mkdir(parents=True)
    for name,content in artifacts.items():(output/name).write_bytes(content)
    (output/'manifest.json').write_bytes(encode(manifest))
    return summary


def validate(output=OUTPUT):
    output=Path(output);m=read(output/'manifest.json')
    require(m['inputs']==source_inputs() and m['processing_code']==record(Path(__file__)),'Input/code checksum changed')
    artifacts,summary=assemble();require(summary==m['summary'] and set(artifacts)==set(m['files']),'Summary/files changed')
    for name,content in artifacts.items():
        require((output/name).read_bytes()==content and m['files'][name]=={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()},'Source-to-output reproduction failed')
    return summary


def public_manifest(output=OUTPUT):
    m=read(Path(output)/'manifest.json')
    return {**m,'local_manifest_sha256':digest(Path(output)/'manifest.json'),
        'source_provenance':read(META/'manual_source_provenance.json'),
        'publication':'Code/tests/methodology and non-spatial aggregate provenance/checksums only; detailed outputs and source binaries local'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['build','validate','publish-metadata'])
    parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    if args.command=='publish-metadata':
        validate(args.output);PUBLIC.parent.mkdir(parents=True,exist_ok=True)
        with PUBLIC.open('xb') as f:f.write(encode(public_manifest(args.output)))
        print(json.dumps({'metadata_file':str(PUBLIC)}))
    else:print(json.dumps((build if args.command=='build' else validate)(args.output),indent=2))
