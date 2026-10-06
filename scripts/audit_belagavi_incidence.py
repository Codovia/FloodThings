#!/usr/bin/env python3
"""Read-only July 2021 incidence audit and bounded public reference discovery.

Stage 3E4 rasters/products are inputs only. No SAR classification or PDF tracing.
"""
import argparse
from copy import deepcopy
from html.parser import HTMLParser
import html
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from urllib.parse import urljoin, urlparse, parse_qs
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_belagavi_2021 as prior
p = prior.p
ROOT = p.ROOT
RAW = ROOT / 'data/raw/reference/stage3e5_v1'
TERRAIN = ROOT / 'data/raw/terrain/stage3e5_v1'
OUTPUT = ROOT / 'data/working/belagavi_2021_incidence_audit_v1'
REFERENCE = ROOT / 'data/reference/belagavi_2021_incidence_audit_v1'
LANDING = 'https://bhuvan-gp1.nrsc.gov.in/bhuvan/web/'
PORTAL = 'https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/flood/flood.php?uname=empty'
SOURCES = {
    's1_catalogue': 'https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD',
    's1_mission': 'https://sentiwiki.copernicus.eu/web/s1-mission',
    'sar_tutorial': 'https://developers.google.com/earth-engine/tutorials/community/sar-basics',
    'srtm_catalogue': 'https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003',
    'slope_method': 'https://developers.google.com/earth-engine/apidocs/ee-terrain-slope',
    'nrsc_terms': 'https://www.nrsc.gov.in/nrscnew/termsConditions.php',
    'geoserver': LANDING,
    'flood_portal': PORTAL,
}
QUANTILES = [1, 5, 25, 50, 75, 95, 99]
METHOD = {
    'angle': 'Approximate incidence from ellipsoid, not local terrain incidence',
    'statistics': 'Finite original angle masks/nodata; no absolute-angle filtering; NumPy linear quantiles independently checked by sorted scalar interpolation',
    'comparison': 'Per-pixel float32 median of July5/17 angles vs July29; absolute difference, <=1degree diagnostic reproduced unchanged',
    'legacy_range': [30, 45], 'agreement_degrees': 1,
    'rule_status': 'legacy_angle_filter_unsubstantiated',
    'rule_origin': 'project_heuristic',
    'terrain': 'Existing Stage3E SRTM asset, February2000 DSM; native ee.Terrain.slope four-connected gradient, nearest sampled to exact retained SAR tile; no local incidence/layover/shadow model',
    'steep_fraction': 'omitted: no independently justified steepness threshold for radar artefacts',
    'requests': {'seconds': 60, 'phase_seconds': 900, 'capability_attempts': 2, 'capability_total_seconds': 180, 'max_source_bytes': 8388608, 'max_raster_bytes': 1048576},
    'publication': 'Source documents/capabilities/footprints/rasters local; code/tests/aggregate metadata/checksums only',
    'threshold_generation': False, 'flood_labels': None,
}
READINESS = {'ready_for_bounded_calibration', 'ready_for_unlabelled_sar_method_research', 'sar_geometry_unsuitable', 'reference_access_blocked'}
TARGET_IDS = {'ka_2021_25_07', 'ka_2021_25-27_07', 'ka_2021_28_07', 'ka_2021_29_07', 'ka_2021_29_07_18'}


def stats(values):
    a = np.asarray(values, dtype='float64').ravel()
    p.require(np.isfinite(a).all(), 'Nonfinite unmasked values')
    if not len(a): return {'count': 0, 'min': None, 'max': None, 'mean': None, 'median': None, 'percentiles': {str(q): None for q in QUANTILES}}
    ordered = sorted(a.tolist())
    def scalar(q):
        index = (len(ordered)-1)*q/100; lo = math.floor(index); hi = math.ceil(index)
        return ordered[lo] + (ordered[hi]-ordered[lo])*(index-lo)
    quantiles = np.percentile(a, QUANTILES, method='linear')
    p.require(all(math.isclose(float(v), scalar(q), abs_tol=1e-10, rel_tol=1e-12) for q,v in zip(QUANTILES,quantiles)), 'Independent quantile mismatch')
    mean = math.fsum(ordered)/len(ordered)
    p.require(math.isclose(mean, float(a.mean()), abs_tol=1e-10, rel_tol=1e-12), 'Independent mean mismatch')
    return {'count': len(a), 'min': ordered[0], 'max': ordered[-1], 'mean': mean, 'median': statistics.median(ordered),
            'percentiles': {str(q): float(v) for q,v in zip(QUANTILES,quantiles)}}


def valid(a): return np.isfinite(a) & (a != p.NODATA)


def incidence(values, names, scenes, grid):
    p.require(values.shape == (len(names),200,200) and len(scenes)==3, 'Wrong retained diagnostic layout')
    arrays = dict(zip(names,values)); results=[]; angles=[]; usable=[]
    a=Affine(*grid['transform']); window=box(a.c,a.f-2000,a.c+2000,a.f)
    project=Transformer.from_crs(4326,p.CRS,always_xy=True).transform
    for i,scene in enumerate(scenes):
        angle=arrays[f's{i}_angle']; mask=valid(angle)
        vv_vh=valid(arrays[f's{i}_VV']) & valid(arrays[f's{i}_VH'])
        intersect=mask&vv_vh; angles.append(angle); usable.append(intersect)
        footprint=transform(project,shape(scene['footprint']))
        p.require(footprint.is_valid and footprint.covers(window), 'Retained tile not covered by source scene')
        distribution=stats(angle[mask]); props=scene['properties']
        results.append({'id':scene['id'],'acquisition_utc':scene['acquisition_utc'], 'platform':props['platform_number'],
            'pass':props['orbitProperties_pass'],'relative_orbit':props['relativeOrbitNumber_start'],
            'angle_degrees':distribution,'unmasked_angle_cells':int(mask.sum()),'valid_vv_vh_cells':int(vv_vh.sum()),
            'intersection_cells':int(intersect.sum()),'footprint':scene['footprint'],
            'minimum_tile_distance_to_footprint_edge_m':window.distance(footprint.boundary),
            'range_interpretation':('far_range_inferred_from_45plus_ellipsoid_angles_near_documented_IW_upper_range; precise_subswath_unverified' if distribution['min'] is not None and distribution['min']>45 else 'not_classified_by_an_arbitrary_absolute_angle_threshold'),
            'scene_edge_interpretation':'boundary_distance_only; no invented edge-rejection threshold'})
    mask=np.logical_and.reduce(usable); baseline=np.median(np.stack(angles[:2]),axis=0).astype('float32')
    difference=np.abs(angles[2]-baseline)
    scalar=np.asarray([abs(float(np.float32(c-np.float32(statistics.median([a,b]))))) for a,b,c in zip(*(v[mask].tolist() for v in angles))])
    p.require(np.array_equal(scalar,difference[mask]), 'Independent per-pixel agreement mismatch')
    agreement=int((mask&(difference<=1)).sum())
    legacy=mask&(baseline>=30)&(baseline<=45)&(angles[2]>=30)&(angles[2]<=45)
    return {'scenes':results,'baseline_angle_degrees':stats(baseline[mask]), 'event_angle_degrees':stats(angles[2][mask]),
            'absolute_difference_degrees':stats(difference[mask]),'comparison_cells':int(mask.sum()),
            'agreement_le_1_degree_cells':agreement,'legacy_30_45_range_cells':int(legacy.sum()),
            'independent_scalar_cells_checked':len(scalar),'angle_semantics':METHOD['angle'],
            'angle_geometry_status':('matching_acquisition_geometry_no_detected_inconsistency' if mask.any() and agreement==int(mask.sum()) else 'angle_geometry_problem_detected'),
            'legacy_filter_status':METHOD['rule_status'],'legacy_filter_origin':METHOD['rule_origin'],
            'processing_thresholds_changed':False,'local_incidence_computed':False}


def official(url):
    parsed=urlparse(url)
    return parsed.scheme=='https' and not parsed.username and not parsed.password and bool(parsed.hostname) and (parsed.hostname=='nrsc.gov.in' or parsed.hostname.endswith('.nrsc.gov.in'))


class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            if href:self.links.append(href)


def advertised_capabilities(body, base=LANDING):
    parser=Links();parser.feed(body);found={}
    for href in parser.links:
        url=urljoin(base,html.unescape(href));query={k.lower():v[0] for k,v in parse_qs(urlparse(url).query).items()}
        service=query.get('service','').upper()
        if not service and urlparse(url).path.endswith('/service/wmts'):service='WMTS'
        if query.get('request','').lower()=='getcapabilities' and service in {'WMS','WFS','WCS','WMTS'}:
            p.require(official(url), 'Capabilities link is not official HTTPS')
            # One declared version per service, not namespace/endpoint enumeration.
            found.setdefault(service,url)
    return found


def local(tag): return tag.rsplit('}',1)[-1]


def parse_capabilities(body, service):
    p.require(len(body)<=METHOD['requests']['max_source_bytes'], 'Capabilities exceeds byte ceiling')
    p.require(b'<!DOCTYPE' not in body.upper() and b'<!ENTITY' not in body.upper(), 'Unsafe XML declarations')
    root=ET.fromstring(body);rootname=local(root.tag)
    expected={'WMS':{'WMS_Capabilities','WMT_MS_Capabilities'},'WFS':{'WFS_Capabilities'},'WCS':{'Capabilities','WCS_Capabilities'},'WMTS':{'Capabilities'}}
    p.require(service in expected and rootname in expected[service], 'Not requested service capabilities')
    def text(node,tag):return next((v.text.strip() for v in node if local(v.tag)==tag and v.text),None)
    formats=sorted({v.text.strip() for v in root.iter() if local(v.tag) in {'Format','OutputFormat','formatSupported'} and v.text})
    records=[]
    tags={'WMS':{'Layer'},'WFS':{'FeatureType'},'WCS':{'CoverageSummary','CoverageOfferingBrief'},'WMTS':{'Layer'}}
    for node in root.iter():
        if local(node.tag) not in tags[service]:continue
        identifier=text(node,'Name') or text(node,'Identifier') or text(node,'CoverageId') or text(node,'name')
        if not identifier:continue
        bounds=[]
        for b in node:
            name=local(b.tag)
            if name in {'BoundingBox','LatLonBoundingBox','WGS84BoundingBox','EX_GeographicBoundingBox','lonLatEnvelope'}:
                bounds.append({'type':name,'attributes':dict(b.attrib),'coordinates':{local(v.tag):v.text for v in b}})
        crs=sorted({v.text.strip() for v in node if local(v.tag) in {'CRS','SRS','DefaultCRS','OtherCRS','DefaultSRS','OtherSRS','SupportedCRS'} and v.text})
        records.append({'name':identifier,'title':text(node,'Title') or text(node,'label'),'abstract':text(node,'Abstract') or text(node,'description'),
                        'crs':crs,'bounds':bounds,'formats':formats,'service':service})
    return {'service':service,'version':root.attrib.get('version'),'layers':records,'formats':formats}


def target_layer(layer):
    combined=' '.join(str(layer.get(k) or '') for k in ['name','title','abstract']).lower()
    name=layer['name'].split(':')[-1]
    return name in TARGET_IDS or ('2021' in combined and ('07' in combined or 'july' in combined) and any(v in combined for v in ['karnataka','belagavi','belgaum','09-fl-2021-ka']))


def reference_acceptance(record):
    if not official(record.get('source_url','')):return 'machine_readable_reference_unavailable'
    if record.get('service') in {'WMS','WMTS'}:return 'official_rendered_map_reference'
    required=['july_2021_verified','overlap_verified','geographic_metadata_sufficient','legitimate_access','internal_use_permitted','original_subset_retrieved','class_semantics_documented']
    return 'machine_readable_reference_available' if record.get('service') in {'WFS','WCS'} and all(record.get(k) is True for k in required) else 'machine_readable_reference_unavailable'


def readiness(pair,geometry,reference,access_blocked=False):
    p.require(pair in prior.PAIR_STATUSES, 'Unknown pair status')
    p.require(geometry in {'acceptable_for_continuous_comparison','unsuitable'}, 'Unknown geometry status')
    p.require(reference in {'machine_readable_reference_available','machine_readable_reference_unavailable'}, 'Unknown reference status')
    if pair!='sentinel1_pair_available' or geometry=='unsuitable':return 'sar_geometry_unsuitable'
    if reference=='machine_readable_reference_available':return 'ready_for_bounded_calibration'
    return 'reference_access_blocked' if access_blocked else 'ready_for_unlabelled_sar_method_research'


def no_classification(record):
    for key,value in record.items():
        p.require(key not in {'flood_threshold','best_threshold','candidate_cells','flood_polygon','digitized_pdf_extent','daily_flood_label'}, 'Classification/digitization forbidden')
        if key=='flood_labels':p.require(value is None, 'Labels forbidden')
        if key=='threshold_generation':p.require(value is False, 'Threshold generation forbidden')
        if isinstance(value,dict):no_classification(value)
        elif isinstance(value,list):
            for item in value:
                if isinstance(item,dict):no_classification(item)


def fetch(session,url,path,attempts=1,total_seconds=180,sleep=time.sleep):
    """At most two attempts for transient failures only; HTTP auth/4xx stop immediately."""
    p.require(1<=attempts<=2 and not path.exists() and not path.with_suffix(path.suffix+'.json').exists(), 'Unsafe output/retry count')
    parsed=urlparse(url)
    p.require(parsed.scheme=='https' and not parsed.username and not parsed.password, 'Only legitimate HTTPS public requests')
    started=p.bounded.grid.elapsed_clock();rows=[]
    for attempt in range(1,attempts+1):
        row={'attempt':attempt,'started_at':p.source.now()};payload=bytearray();status=None;error=None
        remaining=total_seconds-(p.bounded.grid.elapsed_clock()-started)
        p.require(remaining>0, 'Discovery deadline reached')
        request_start=p.bounded.grid.elapsed_clock()
        try:
            with p.bounded.verification.wall_limit(min(60,remaining)):
                with session.get(url,stream=True,timeout=(5,20),allow_redirects=False) as response:
                    status=response.status_code
                    for chunk in response.iter_content(65536):
                        payload.extend(chunk);p.require(len(payload)<=8388608,'Source exceeds 8MiB limit')
                    headers={k:response.headers.get(k) for k in ['Content-Type','Last-Modified','Location']}
            elapsed=p.bounded.grid.elapsed_clock()-started
            p.require(elapsed<total_seconds and p.bounded.grid.elapsed_clock()-request_start<min(60,remaining), 'Late/suspended response rejected')
        except p.bounded.verification.VerificationDeadlineExceeded:
            error='request_deadline_exceeded';headers={}
        except Exception as exc:error=type(exc).__name__;headers={}
        row.update(http_status=status,error_type=error,finished_at=p.source.now(),elapsed_seconds=p.bounded.grid.elapsed_clock()-request_start);rows.append(row)
        retry=(error in {'Timeout','ReadTimeout','ConnectTimeout','ConnectionError','request_deadline_exceeded'} or status in {429,500,502,503,504}) and attempt<attempts
        if retry and p.bounded.grid.elapsed_clock()-started+2<total_seconds:sleep(2);continue
        with path.open('xb') as f:f.write(payload)
        record={'url':url,'retrieved_at':p.source.now(),'http_status':status,'error_type':error,'headers':headers,'attempts':rows,
                'access_status':'retrieved' if status==200 and error is None else 'unavailable','original':p.source.fingerprint(path)}
        p.source.write_new(path.with_suffix(path.suffix+'.json'),record)
        return record


def portal_products(body):
    """Exact public catalogue entries; zoom bounds are never flood footprints."""
    rows={}
    for item in re.finditer(r'<input\b[^>]*>[^<]*',body):
        call=re.search(r'loadfloodmap\("([^"\n]+)","(https://[^"\n]+)","([^"\n]+)"\)',item.group())
        if not call or call[3] not in TARGET_IDS:continue
        p.require(official(call[2]), 'Nonofficial portal layer')
        label=html.unescape(item.group().split('>',1)[1]).strip()
        rows[call[3]]={'id':call[3],'title':label,'service_url':call[2],'portal_control_id':call[1],
            'date_semantics':'Literal public product label; sensor/acquisition hour not independently verified',
            'spatial_coverage':'not_verified; portal zoom extent is not flood footprint', 'source':PORTAL}
    return [rows[k] for k in sorted(rows)]


def discover(raw=RAW):
    import requests
    raw.mkdir(parents=True,exist_ok=True)
    p.require(not (raw/'service_discovery.json').exists(),'Completed discovery immutable')
    with requests.Session() as session:
        for name,url in SOURCES.items():
            path=raw/(name+'.html')
            if not path.exists():fetch(session,url,path)
            p.require(path.with_suffix('.html.json').exists(),'Unjournalled source requires explicit recovery')
        landing=p.read(raw/'geoserver.html.json');links=advertised_capabilities((raw/'geoserver.html').read_text()) if landing['access_status']=='retrieved' else {}
        results=[];start=p.bounded.grid.elapsed_clock()
        for service,url in sorted(links.items()):
            remaining=180-(p.bounded.grid.elapsed_clock()-start)
            if remaining<=0:results.append({'service':service,'url':url,'access_status':'not_attempted_total_deadline'});continue
            path=raw/(service.lower()+'_capabilities.xml');fp=path.with_suffix('.xml.json')
            record=p.read(fp) if fp.exists() else fetch(session,url,path,attempts=2,total_seconds=remaining)
            result={'service':service,'url':url,'retrieval':record,'access_status':record['access_status'],'matching_layers':[]}
            if record['access_status']=='retrieved':
                try:
                    parsed=parse_capabilities(path.read_bytes(),service);result.update(layer_count=len(parsed['layers']),version=parsed['version'],formats=parsed['formats'],matching_layers=[v for v in parsed['layers'] if target_layer(v)])
                except (ValueError,ET.ParseError) as error:
                    result.update(access_status='capabilities_invalid',parser_error=str(error))
                    try:
                        exception=ET.fromstring(path.read_bytes())
                        result['service_exceptions']=[v.text.strip() for v in exception.iter() if local(v.tag) in {'ExceptionText','ServiceException'} and v.text]
                    except ET.ParseError:pass
            if record['access_status']!='retrieved' and record['http_status']==400:
                reason=' '.join(re.sub('<[^>]+>',' ',path.read_text(errors='replace')).split())
                result['provider_error_summary']=reason[:1000]
            results.append(result)
    portal=p.read(raw/'flood_portal.html.json')
    layers=portal_products((raw/'flood_portal.html').read_text()) if portal['access_status']=='retrieved' else []
    result={'landing_url':LANDING,'advertised_services':links,'services':results,'portal_url':PORTAL,'july_karnataka_products':layers,
            'reference_status':'machine_readable_reference_unavailable','known_pdf_reference':'official_map_reference_available',
            'spatial_overlap':'Portal zoom bounds only; product coverage and original flood data not verified',
            'no_private_namespace_enumeration':True,'no_rendered_color_digitization':True}
    p.source.write_new(raw/'service_discovery.json',result)
    print(json.dumps({'services':[{k:r.get(k) for k in ['service','access_status','layer_count','matching_layers']} for r in results],'products':len(layers)}))


def terrain_extract(raw=TERRAIN):
    import requests
    p.require(not (raw/'terrain.json').exists(),'Completed terrain checkpoint immutable')
    raw.mkdir(parents=True,exist_ok=True)
    grid=p.read(prior.RAW/'diagnostic_preflight.json')['grid'];a=grid['transform']
    workload=40000*4*1.25;p.require(workload<=250000<300000,'Terrain band preflight exceeds unchanged limits')
    session=p.bounded.TimedEE(raw,60,900);session.initialize();ee=session.ee
    dem=ee.Image(p.DEM).select('elevation');slope=ee.Terrain.slope(dem)
    metadata=session.request(lambda:ee.Dictionary({'id':ee.Image(p.DEM).id(),'projection':dem.projection(), 'nominal_scale_m':dem.projection().nominalScale()}).getInfo(),'existing_SRTM_asset_metadata')
    bands=[dem.unmask(p.NODATA,sameFootprint=False).rename('elevation'),dem.mask().unmask(0,sameFootprint=False).rename('dem_mask'),slope.unmask(p.NODATA,sameFootprint=False).rename('slope_degrees'),slope.mask().unmask(0,sameFootprint=False).rename('slope_mask')]
    parameters={'crs':p.CRS,'crs_transform':a,'dimensions':[200,200],'format':'GEO_TIFF','filePerBand':False}
    url=session.request(lambda:p.download_url(ee.Image.cat(bands).toFloat(),parameters),'terrain_2km_url')
    path=raw/'terrain.tif'
    with requests.Session() as http:download=session.request(lambda:p.download.download(http,url,path),'terrain_2km_download')
    record={'asset':p.DEM,'native_metadata':metadata,'parameters':parameters,'bands':['elevation','dem_mask','slope_degrees','slope_mask'],
            'download':download,'band_workload':160000,'safety_workload':200000,'maxPixels':300000,'bestEffort':False,
            'method':METHOD['terrain'],'attribution':'NASA/USGS SRTM public domain, February2000 surface elevations; not contemporaneous 2021 bare earth'}
    p.source.write_new(raw/'terrain.json',record);print(json.dumps(terrain_summary(raw)))


def terrain_summary(raw=TERRAIN):
    record=p.read(raw/'terrain.json');p.require(record['asset']==p.DEM,'Wrong terrain asset')
    p.require(all(record['download'][k]==v for k,v in p.source.fingerprint(raw/'terrain.tif').items()),'Terrain checksum mismatch')
    with rasterio.open(raw/'terrain.tif') as r:
        p.require(str(r.crs)==p.CRS and r.transform.almost_equals(Affine(*record['parameters']['crs_transform'])) and r.shape==(200,200) and r.count==4,'Terrain grid differs from retained tile')
        z,zm,s,sm=r.read()
    p.require(np.isin(zm,[0,1]).all() and np.isin(sm,[0,1]).all(),'Terrain masks changed')
    zv=(zm==1)&valid(z);sv=(sm==1)&valid(s)
    p.require((z[~zv]==p.NODATA).all() and (s[~sv]==p.NODATA).all(),'Terrain nodata not preserved')
    p.require((s[sv]>=0).all() and (s[sv]<=90).all(),'Invalid slope units')
    return {'elevation_m':stats(z[zv]),'slope_degrees':stats(s[sv]),'valid_elevation_cells':int(zv.sum()),'valid_slope_cells':int(sv.sum()),
            'native_resolution_m':record['native_metadata']['nominal_scale_m'],'source':p.DEM,'method':METHOD['terrain'],
            'steep_fraction':None,'local_incidence_computed':False,'layover_shadow_verified':False,
            'limitations':'Coarse historical DSM slope is context only; vegetation/buildings/local steep banks and radar look orientation are not resolved; no terrain masking or guarantee of absent artefacts'}


def validate_discovery(raw=RAW):
    result=p.read(raw/'service_discovery.json')
    p.require(result['advertised_services']==advertised_capabilities((raw/'geoserver.html').read_text()),'Advertised public endpoints changed')
    p.require(result['july_karnataka_products']==portal_products((raw/'flood_portal.html').read_text()),'Public catalogue changed')
    p.require({v['service'] for v in result['services']}==set(result['advertised_services']),'Missing service result')
    for service in result['services']:
        name=service['service'];path=raw/(name.lower()+'_capabilities.xml');record=p.read(path.with_suffix('.xml.json'))
        p.require(record==service['retrieval'] and record['original']==p.source.fingerprint(path),'Service original bytes/provenance changed')
        p.require(service['url']==result['advertised_services'][name] and len(record['attempts'])<=2,'Unadvertised endpoint or excessive retries')
        if service['access_status']=='retrieved':
            parsed=parse_capabilities(path.read_bytes(),name)
            p.require(service['matching_layers']==[v for v in parsed['layers'] if target_layer(v)],'Layer search not reproducible')
        if record['access_status']!='retrieved' and record['http_status']==400:
            service['provider_error_summary']=' '.join(re.sub('<[^>]+>',' ',path.read_text(errors='replace')).split())[:1000]
        p.require(not service['matching_layers'],'A possible official reference requires explicit bounded metadata/subset review before freezing')
    p.require(result['reference_status']=='machine_readable_reference_unavailable','Reference acceptance changed')
    return result


def source_semantics(raw=RAW):
    """Check retained authoritative statements and original project history offline."""
    for name in SOURCES:
        record=p.read(raw/(name+'.html.json'));path=raw/(name+'.html')
        p.require(record['access_status']=='retrieved' and record['original']==p.source.fingerprint(path),'Official source not retained: '+name)
    def plain(name):
        return ' '.join(html.unescape(re.sub('<[^>]+>',' ',(raw/(name+'.html')).read_text())).split())
    catalogue=plain('s1_catalogue');mission=plain('s1_mission');tutorial=plain('sar_tutorial')
    p.require('Approximate incidence angle from ellipsoid' in catalogue,'Angle semantics not verified')
    p.require(re.search(r'29\.1.{0,20}46\.0',mission) is not None,'Official IW range not verified')
    p.require('30-39 degrees' in tutorial,'AOI-specific tutorial not verified')
    historical=p.read(raw/'legacy_provenance.json')
    for name,fp in historical['source_files'].items():p.require(p.source.fingerprint(raw/name)==fp,'Original rule evidence changed')
    doc=(raw/'legacy_method.md.txt').read_text();code=(raw/'legacy_source.py.txt').read_text()
    p.require('incidence_angle_degrees' in code and '[30.,45.]' in code and 'All numerical gates above are **experimental**' in doc
              and 'does not validate these thresholds' in doc,'Rule origin not independently reproducible')
    return {'angle_definition':METHOD['angle'],'catalogue_nominal_angle_pixel_size_m':20000,
      'retained_selected_source_projection_metadata':p.read(prior.RAW/'native_source_metadata.json')['sar'],
      'official_IW_incidence_range_degrees':[29.1,46.0],
      'tutorial_range':'30-39degrees explicitly for its AOI, not a universal validity criterion',
      'local_incidence':'Relative to terrain normal, not ellipsoid normal; not computed',
      'rule_provenance':historical,'legacy_filter_status':METHOD['rule_status'],
      'official_urls':SOURCES,'scene_range_inference':'Far range inferred, not independently identified subswath; retained footprints quantify boundary proximity'}


def assemble():
    prior.validate();values,names,grid=prior.retained_values();md=p.read(prior.RAW/'metadata.json');pair=md['grouping']['selected']
    audit=incidence(values,names,pair['baseline']+[pair['event_scene']],grid)
    prior_count=p.read(prior.OUTPUT/'independent_checks.json')['angle_difference_within_predeclared_one_degree_cells']
    p.require(audit['agreement_le_1_degree_cells']==prior_count==40000,'Stage3E4 agreement changed')
    discovery=validate_discovery();terrain=terrain_summary();sources=source_semantics()
    geometry='acceptable_for_continuous_comparison' if audit['angle_geometry_status']=='matching_acquisition_geometry_no_detected_inconsistency' else 'unsuitable'
    status=readiness(md['grouping']['status'],geometry,discovery['reference_status'],False)
    result={'event_id':prior.EVENT,'incidence':audit,'terrain':terrain,'service_discovery':discovery,'source_semantics':sources,'method':METHOD,
            'readiness':status,'reference_access_status':'public_service_access_failed_or_no_accepted_reference',
            'calibration':'not_ready_without_independent_machine_readable_inundation; no absolute range assumption or threshold change'}
    no_classification(result);return result


def freeze(output=OUTPUT,reference=REFERENCE):
    p.require(not output.exists() and not reference.exists(),'Completed versions immutable')
    result=assemble();inputs=[path for folder in [RAW,TERRAIN] for path in folder.rglob('*') if path.is_file()]
    inputs += [prior.OUTPUT/'manifest.json',prior.RAW/'metadata.json',prior.RAW/'diagnostic_preflight.json',prior.RAW/'native_source_metadata.json']
    inputs += [prior.RAW/f'tile{i}.{ext}' for i in range(4) for ext in ['tif','json']]
    code=[Path(__file__),Path(prior.__file__),Path(p.__file__),Path(prior.jrc.__file__)]
    manifest={'version':output.name,'created_at':p.source.now(),'method':METHOD,'inputs':{str(v.relative_to(ROOT)):p.source.fingerprint(v) for v in sorted(inputs)},
              'code':{str(v.relative_to(ROOT)):p.source.fingerprint(v) for v in code}}
    output.mkdir(parents=True);p.source.write_new(output/'audit.json',result)
    manifest['files']={'audit.json':p.source.fingerprint(output/'audit.json')};p.source.write_new(output/'manifest.json',manifest)
    public=deepcopy(result)
    for scene in public['incidence']['scenes']:scene.pop('footprint')
    public.update(version=output.name,created_at=manifest['created_at'],source_checksums=manifest['inputs'],code_checksums=manifest['code'],
                  local_outputs={**manifest['files'],'manifest.json':p.source.fingerprint(output/'manifest.json')},publication=METHOD['publication'])
    reference.mkdir(parents=True);p.source.write_new(reference/'manifest.json',public)
    return validate(output)


def validate(output=OUTPUT):
    m=p.read(output/'manifest.json');p.require(m['method']==METHOD,'Audit method changed')
    for key in ['inputs','code']:
        for name,fp in m[key].items():p.require(p.source.fingerprint(ROOT/name)==fp,'Input/code changed: '+name)
    for name,fp in m['files'].items():p.require(p.source.fingerprint(output/name)==fp,'Audit output changed')
    r=p.read(output/'audit.json');p.require(r==assemble(),'Offline angle/terrain/service results not reproducible')
    no_classification(r)
    return {'version':output.name,'scene_count':3,'angle_cells':40000,'agreement_cells':r['incidence']['agreement_le_1_degree_cells'],
            'readiness':r['readiness'],'reference':r['service_discovery']['reference_status'],'live_requests':0,'independent_statistics':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['discover','terrain','freeze','validate']);args=parser.parse_args()
    if args.operation=='discover':discover()
    elif args.operation=='terrain':terrain_extract()
    else:print(json.dumps(freeze() if args.operation=='freeze' else validate(),indent=2))
