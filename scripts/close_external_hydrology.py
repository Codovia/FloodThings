"""Stage4F bounded external-evidence closure. Offline builder/validator only.

No credentials, HTTP, source rewrites, features, labels or performance metrics.
Human-reviewed primary-document findings are inputs, not inferred from labels.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html import unescape
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage4f_v1'
PRIOR = ROOT / 'data/working/karnataka_hydrology_closure_v1'
OUTPUT = ROOT / 'data/working/karnataka_external_hydrology_closure_v1'
PUBLIC = ROOT / 'data/reference/karnataka_external_hydrology_closure_v1/manifest.json'
ATTRIBUTES = ('value_semantics', 'timezone', 'timestamp_meaning', 'aggregation_window', 'yearbook_equivalence')
STATION = 'CW1KRU000212'
RESOURCE = 'f95150ea-c8fc-4740-8815-d9c34c9d53a3'
DATASET = '08fa3fd0-7861-471d-a295-27c1b239d1fa'
SOURCE_TYPES = {'measured_cwc_nwdp', 'published_cwc_yearbook', 'modelled_glofas'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    p = Path(path)
    return {'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': sha(p)}


def provenance(row):
    host = urlparse(row['url'])
    require(host.scheme == 'https' and (host.hostname.endswith('.gov.in') or
            host.hostname == 'cwc.gov.in'), 'Primary official HTTPS source required')
    for field in ('title', 'publisher', 'version', 'section', 'retrieved_at', 'classification'):
        require(isinstance(row.get(field), str) and bool(row[field]), 'Incomplete source provenance: '+field)
    require(bool(re.fullmatch(r'[a-f0-9]{64}', row.get('sha256', ''))), 'Invalid source checksum')
    datetime.fromisoformat(row['retrieved_at'])
    return deepcopy(row)


def reach_decision(candidates, anchor=None):
    require(len(candidates) == 2 and {x['side'] for x in candidates} == {'west', 'east'},
            'Both Gokak candidates must remain explicit')
    require(all(x['upstream_area_km2'] > 0 and x['source'] for x in candidates), 'Upstream provenance required')
    selected = None
    if anchor is not None:
        provenance(anchor)
        require(set(anchor) <= {'url','title','publisher','version','section','retrieved_at','classification',
                               'sha256','station_id','side','basis','model_version'}, 'Discharge/nearest scoring forbidden')
        require(anchor.get('station_id') == STATION and anchor.get('model_version') == '5.0'
                and anchor.get('side') in {'west','east'}
                and anchor.get('basis') == 'independent_official_gauge_to_model_junction_link'
                and anchor['classification'] == 'conclusive_reach_anchor', 'Independent gauge/junction evidence required')
        selected = anchor['side']
    return {'status': 'gokak_reach_resolved_'+selected if selected else 'gokak_reach_externally_unresolved',
            'selected_cell': next((deepcopy(x) for x in candidates if x['side'] == selected), None),
            'station_grid_status': 'station_grid_match_supported' if selected else 'station_grid_match_ambiguous',
            'station_coordinate_status': 'coordinate_conflict_unresolved',
            'coordinate_conflict_resolved': False, 'selection_uses_discharge': False}


def temporal_decision(attributes):
    require(set(attributes) == set(ATTRIBUTES), 'Every temporal attribute required')
    resolved = []
    for name, finding in attributes.items():
        allowed = {'resolved','unresolved'} if name == 'timezone' else {'resolved','partially_resolved','unresolved'}
        require(finding['status'] in allowed, 'Invalid temporal status')
        require(bool(finding.get('reason')), 'Temporal reason required')
        if finding['status'] != 'unresolved':
            require(finding.get('resource_id') == RESOURCE and finding.get('exact_field_documented') is True,
                    'General daily/manual/0800/update-clock context cannot define exact NWDP fields')
            provenance(finding['source'])
            require(bool(finding.get('definition')), 'Exact definition required; no defaults')
        resolved.append(finding['status'])
    overall = ('nwdp_temporal_semantics_resolved' if all(s == 'resolved' for s in resolved)
               else 'nwdp_temporal_semantics_partially_resolved' if any(s != 'unresolved' for s in resolved)
               else 'nwdp_temporal_semantics_externally_unresolved')
    # Closure does not create pairs: even a later dictionary needs record-level interval alignment.
    return {'status': overall, 'attributes': deepcopy(attributes), 'aligned_quantitative_pairs': 0,
            'pointwise_comparison_allowed': False,
            'comparison_gate': 'Exact statistic/timezone/bounds and record alignment plus source-quality eligibility required separately'}


def closure_status(gokak, temporal, search_closed):
    require(search_closed, 'Complete declared bounded public research before closure')
    g = gokak.startswith('gokak_reach_resolved_')
    t = temporal == 'nwdp_temporal_semantics_resolved'
    require(g or gokak in {'gokak_reach_externally_unresolved','gokak_reach_resolution_supported_but_not_conclusive'}, 'Invalid reach class')
    require(temporal in {'nwdp_temporal_semantics_resolved','nwdp_temporal_semantics_partially_resolved',
                        'nwdp_temporal_semantics_externally_unresolved'}, 'Invalid temporal class')
    return ('external_hydrology_closure_complete' if g and t else
            'external_hydrology_closure_partial' if g or t else
            'external_hydrology_closure_complete_with_unresolved_items')


def usage_matrix():
    rows = [
        ('sadalga_modelled_discharge','allowed_with_conditions','modelled_glofas',
         'Supported Stage4D cell only; native24hUTC interval; model version/calibration uncertainty; prediction-time availability must be assessed in Stage5'),
        ('huvinhedgi_modelled_discharge','allowed_with_conditions','modelled_glofas',
         'Supported Stage4D cell with coordinate caveat; preserve model identity, grid/time and calibration uncertainty; no claim of measured truth'),
        ('rainfall_antecedent','allowed_with_conditions','CHIRPS',
         'Only dates strictly before anchor; native grid/masks; geography vintage and historical availability explicit'),
        ('validated_spatial_static_context','allowed_with_conditions','independently_verified_static',
         'Source-specific coverage, date, projected metric methods, licence and geometry uncertainty retained'),
        ('gokak_canonical_discharge','not_allowed','modelled_glofas','Ambiguous gauge-to-model-junction identity; preserve both candidates locally'),
        ('time_aligned_measured_modelled_pairs','not_allowed','measured_cwc_nwdp + modelled_glofas','Exact NWDP statistic/timezone/timestamp/bounds unverified'),
        ('model_skill_metrics_or_calibration_claims','not_allowed','measured_cwc_nwdp + modelled_glofas','Unknown alignment, limited quality-caveated sample, calibration relationship unresolved'),
        ('water_level_threshold_features','not_allowed','measured_cwc_nwdp','Absolute datum compatibility unresolved'),
        ('within_station_water_level_change','not_allowed','measured_cwc_nwdp','Requires separate interval/quality/identity/availability method review; not approved automatically'),
        ('missing_observation_as_flood_negative','not_allowed','any','Missing observations are unknown, never verified negatives'),
        ('modelled_replacement_of_measured_values','not_allowed','modelled_glofas','Independent source class; never fill measured gaps'),
        ('instant_historical_prediction_availability','not_allowed','any','Observation time is not publication availability; latency unverified'),
    ]
    return [dict(use=u,permission=p,source_type=s,conditions=c) for u,p,s,c in rows]


def check_source_type(value):
    require(value in SOURCE_TYPES, 'Measured/modelled source identity required')
    return value


def visible(text):
    body = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text, flags=re.I | re.S)
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', body))).strip()


def page(path, number):
    return subprocess.run(['pdftotext','-f',str(number),'-l',str(number),'-layout',str(path),'-'],
                          check=True,capture_output=True,text=True,timeout=30).stdout


def reviewed_sources():
    rows = []
    for finding in read(RAW / 'review_findings.json'):
        p = RAW / finding['path']; receipt = read(Path(str(p)+'.json'))
        require(receipt['status'] == 'retrieved' and receipt['http_status'] == '200' and
                receipt['bytes'] == p.stat().st_size and receipt['sha256'] == sha(p), 'Source retrieval integrity failed')
        rows.append(provenance({**finding, 'path':str(p.relative_to(ROOT)), 'url':receipt['source_url'],
                               'retrieved_at':receipt['retrieved_at'], 'sha256':receipt['sha256'],'bytes':receipt['bytes']}))
    require(len(rows) == 8 and len({x['path'] for x in rows}) == 8, 'Declared eight source documents required')
    # Anchor page notes to actual original documents; human interpretation remains explicit.
    checks = [('cwc_handbook2017.pdf',45,['4.6','8:00','e-SWIS']),
              ('cwc_network_details.pdf',88,['Gokak Falls','2770','AKT00P9']),
              ('cwc_ho2020.pdf',196,['Gokak Falls','CW1KRU000212','2770']),
              ('krishna_basin_complete.pdf',68,['Map 20']),
              ('krishna_basin_complete.pdf',162,['Gokak','2770'])]
    for name,n,tokens in checks:
        body = page(RAW/name,n)
        require(all(t in body for t in tokens), 'Reviewed PDF page changed')
    preview = (RAW/'nwdp_discharge_preview.html').read_text()
    require('Manual Daily River Water Discharge' in preview and 'Data Acquisition Time' in preview,
            'Exact NWDP fields not present')
    return rows


def prior_module():
    spec = importlib.util.spec_from_file_location('prior_stage4e', ROOT/'scripts/close_hydrology_semantics.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def input_records():
    paths = list(RAW.iterdir()) + list(PRIOR.iterdir()) + [ROOT/'scripts/close_hydrology_semantics.py',
        ROOT/'data/working/karnataka_hydrology_semantics_v1/clarification_package.json',
        ROOT/'data/raw/reference/stage4a_v1/cwc_krishna_map.pdf',
        ROOT/'data/raw/reference/stage4a_v1/cwc_krishna_map.pdf.json']
    return [record(p) for p in sorted(set(paths)) if p.is_file()]


def assemble():
    baseline = prior_module().validate(PRIOR)
    require((baseline['preserved_measured_rows'],baseline['preserved_comparison_cases'],
             baseline['preserved_eligible_rows'],baseline['preserved_disagreements']) == (1697,81,14,33), 'Protected hydrology counts changed')
    log = read(RAW/'research_log.json')
    require(log['queries_used'] == 24 and log['retained_public_fetches'] == 8 and
            log['new_observation_downloads'] == log['new_model_downloads'] == log['messages_sent'] == 0,
            'Bounded research/no retrieval or contact rule violated')
    sources = reviewed_sources()
    net = read(PRIOR/'gokak_reach_evidence.json')
    static = read(PRIOR/'static_sources.json')
    candidates = [{**x, 'side':side,'source':'Stage4E original v5 static grid; hashes in static_sources.json'}
                  for x,side in zip(net['station_candidates'],('west','east'))]
    decision = reach_decision(candidates)
    attrs = {key:{'status':'unresolved','reason':reason} for key,reason in zip(ATTRIBUTES,[
        'General RD1 observation sessions at0800 do not define the statistic in this exact NWDP export',
        'No observation timezone defined; portal display/update clock is not a data-field dictionary',
        'Data Acquisition Time label/text schema lacks observation/period/reporting definition',
        'No exact bounds or24h aggregation specified for the field; daily frequency is insufficient',
        'General eSWIS/yearbook processing path does not prove exact field/time or revision equivalence'])}
    temporal = temporal_decision(attrs)
    catalogue = read(RAW/'nwdp_discharge_catalogue.json')['result']['results'][0]
    resource = next(x for x in catalogue['resources'] if x['id'] == RESOURCE)
    require(catalogue['id'] == DATASET, 'Wrong official dataset')
    require(not resource.get('data_dictionary') and not resource.get('schema'), 'New dictionary requires human review')
    metadata = {'dataset_id':DATASET,'resource_id':RESOURCE,'resource_title':resource['name'],
                'data_last_modified':resource['last_modified'],'metadata_modified':resource['metadata_modified'],
                'licence':catalogue['license_title'],'dictionary_supplied':False,
                'original_field_names':['Manual Daily River Water Discharge (m3/sec)','Data Acquisition Time'],
                'hydrology_source_type':'measured_cwc_nwdp','units':'m3/sec',
                'portal_clock_not_observation_timezone':True}
    questions = [
        {'id':'gokak_site','station_id':STATION,'question':'Provide canonical dated Gokak Falls gauge/cross-section coordinates and site/relocation/correction history. Is the2019 gauge upstream or downstream of the local Ghataprabha tributary junction corresponding to the eastern model confluence? A dated site map/schematic and named tributaries would help distinguish the preserved western/eastern v5 candidates. Coordinate conflict and model-grid matching are separate questions.'},
        {'id':'nwdp_value','resource_id':RESOURCE,'question':'For Manual Daily River Water Discharge (m3/sec), specify whether the exported value is a measurement-session/instantaneous observation, computed flow, daily aggregate or another quantity; identify method/status fields and whether semantics match Year Book daily discharge.'},
        {'id':'nwdp_time','resource_id':RESOURCE,'question':'Define Data Acquisition Time: observation, period start/end or reporting/upload time? Specify timezone and, if an aggregate, exact daily interval/boundary convention. Please distinguish this from portal metadata update time.'}]
    summary = {'stage':'4F','status':closure_status(decision['status'],temporal['status'],log['search_closed']),
        'gokak_status':decision['status'],'selected_gokak_cell':None,'station_coordinate_status':'coordinate_conflict_unresolved',
        'nwdp_status':temporal['status'],'nwdp_attributes':{k:v['status'] for k,v in attrs.items()},
        'public_search_closed':True,'search_queries':24,'new_retained_sources':8,'authenticated_requests':0,
        'quantitative_comparisons':0,'performance_metrics':0,'features_created':0,'labels_created':0,'messages_sent':0,
        'preserved_measured_rows':1697,'preserved_comparison_cases':81,'preserved_eligible_rows':14,'preserved_disagreements':33}
    artifacts = {
        'external_source_register.json':sources,
        'gokak_external_evidence.json':{'candidates':candidates,'topology':net['topology'],
             'original_coordinate_variants':net['coordinate_distances'],'new_documentary_findings':[s for s in sources if 'gokak' in s['finding'].lower()],
             'basis':'No independent dated gauge-to-junction link; overview maps not georeferenced; no magnitude matching, coordinate averaging or inferred relocation'},
        'gokak_reach_decision.json':decision,'static_sources.json':static,
        'nwdp_temporal_source_register.json':{'metadata':metadata,'source_ids':[s['path'] for s in sources if 'nwdp' in s['path'] or 'handbook' in s['path']]},
        'nwdp_semantics_decision.json':temporal,'unresolved_external_questions.json':questions,
        'clarification_request_package.json':{'purpose':'FloodPulse bounded academic research, no training/labels','sent':False,
             'prior_package':'data/working/karnataka_hydrology_semantics_v1/clarification_package.json',
             'dataset_id':DATASET,'resource_id':RESOURCE,'station_id':STATION,'questions':questions,
             'source_urls':[s['url'] for s in sources],'attachments':'Source references and local candidate evidence only; no large binaries or source observations'},
        'stage5_hydrology_usage_matrix.json':usage_matrix(),
        'methodology_limitations.json':{'search_log':log,'glofas_semantics':'Stage4E preceding24h mean ending at original00UTC timestamps unchanged; no assumption that NWDP uses the same window',
             'scope':'Public evidence exhausted within24queries/8document fetches; not a claim that unpublished records do not exist',
             'publication':'Official source documents, source coordinates and detailed evidence stay local; code/paraphrase/source refs/checksums/aggregate decisions only public',
             'no_field_rewrites':True,'no_automatic_stage5_execution':True,
             'next_task':'Stage5 bounded research-feature methodology and prediction-time availability design using supported modelled Sadalga/Huvinhedgi and antecedent rainfall/static context; exclude Gokak canonical and unresolved CWC alignment/datum; no training'},
        'summary.json':summary}
    return {name:encode(value) for name,value in artifacts.items()},summary


def build(output=OUTPUT):
    p = Path(output); require(not p.exists(), 'Immutable Stage4F version exists')
    artifacts,summary = assemble()
    manifest = {'version':'karnataka_external_hydrology_closure_v1','created_at':datetime.now(timezone.utc).isoformat(),
        'inputs':input_records(),'processing_code':record(Path(__file__)),'summary':summary,
        'files':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in artifacts.items()}}
    p.mkdir(parents=True)
    for n,b in artifacts.items(): (p/n).write_bytes(b)
    (p/'manifest.json').write_bytes(encode(manifest))
    return summary


def validate(output=OUTPUT):
    p=Path(output); manifest=read(p/'manifest.json')
    require(manifest['inputs']==input_records() and manifest['processing_code']==record(Path(__file__)), 'Input/code checksum changed')
    artifacts,summary=assemble()
    require(manifest['summary']==summary and set(manifest['files'])==set(artifacts), 'Manifest schema changed')
    for n,b in artifacts.items():
        require((p/n).read_bytes()==b and manifest['files'][n]=={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}, 'Offline reproduction failed')
    return summary


def publish_metadata(output=OUTPUT):
    validate(output)
    sources=[{k:v for k,v in row.items() if k in {'url','path','title','publisher','version','section','retrieved_at','sha256','bytes','classification','reuse'}}
             for row in read(Path(output)/'external_source_register.json')]
    return {**read(Path(output)/'manifest.json'),'local_manifest_sha256':sha(Path(output)/'manifest.json'),
            'sources':sources,'stage5_usage':usage_matrix(),
            'publication':'Own code, source references/checksums and aggregate statuses only; detailed evidence and source binaries local'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','validate','publish-metadata'])
    parser.add_argument('--output',type=Path,default=OUTPUT); args=parser.parse_args()
    if args.command=='publish-metadata':
        metadata=publish_metadata(args.output); PUBLIC.parent.mkdir(parents=True,exist_ok=True)
        with PUBLIC.open('xb') as stream: stream.write(encode(metadata))
        print(json.dumps({'public_manifest':str(PUBLIC)}))
    else: print(json.dumps((build if args.command=='build' else validate)(args.output),indent=2))
