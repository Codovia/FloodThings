#!/usr/bin/env python3
"""Second bounded batch from retained candidates; never changes prior evidence.

No flood pixels enter selection. Only exact source names, temporal metadata and
public boundary/footprint geometry are used. Detailed products remain local.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_karnataka_satellite as grid
import verify_karnataka_satellite as source
import extract_karnataka_rainfall as retry
import verify_earth_engine as verification

ROOT = source.ROOT
PREVIOUS = ROOT / 'data/working/karnataka_satellite_event_evidence_v2'
BOUNDARIES = ROOT / 'data/raw/flood_satellite/stage3b_access_v1/public_boundary_inventory.json'
OUTPUT = ROOT / 'data/working/karnataka_satellite_event_evidence_v3'
RAW = ROOT / 'data/raw/flood_satellite/stage3b2_v1'
STATE_SOURCE = 'WM/geoLab/geoBoundaries/600/ADM1'
# Verified by the retained bounded 36-feature India ADM1 response. The source
# literally stores 'Karn?taka', not 'Karnataka'; preserve it and query its ID.
STATE_ID = '1811400B56841107211215'
STATE_NAME = 'Karn?taka'
STATE_INVENTORY = ROOT / 'data/raw/flood_satellite/stage3b2_state_diagnostic_v1/state_names.json'
EXCLUDED_IDS = set(grid.IDS) | {2728, 3551}
FINAL_STATUSES = grid.STATUSES - {'not_reviewed'}
RULE = ('Exclude prior IDs, ambiguous IFI links, weak/invalid/out-of-period windows, non-Karnataka-only IFI, '
        'and non-India-primary DFO metadata. Require a unique exact original district token, public Karnataka '
        'state containment >=99%, positive event-footprint intersection and safe existing planner. '
        'All remaining candidates are strong temporal and non-ambiguous; greedily prefer new years, new '
        'regions, higher IFI overlap fraction/Jaccard, smaller region, fewer source tokens, then stable IDs. '
        'Seed diversity from prior seven reviews; one region per GFD ID, up to ten. No raster outcomes used. '
        'Footprint intersections permit research review only, not verified IFI event identity or floodwater.')


def read(path):
    return json.loads(Path(path).read_text())


def verify_execution_code(recorded):
    for name,value in recorded.items():
        path=Path(name)
        if not path.exists() or source.fingerprint(path)!=value:
            path=ROOT/'data/recovery/stage3b2_execution_sources'/f"{value['sha256']}.py"
        source.require(path.exists() and source.fingerprint(path)==value,'Recorded extraction code unavailable or changed')


def verify_state_inventory(path):
    inventory=read(path);response=inventory['response']
    source.require(inventory['source']==STATE_SOURCE and response['count']==len(response['features'])<=50,
                   'State source inventory incomplete')
    matched=[f for f in response['features'] if f['shapeID']==STATE_ID]
    source.require(matched==[{'shapeID':STATE_ID,'shapeName':STATE_NAME,'shapeGroup':'IND','shapeType':'ADM1'}],
                   'Actual source state identity unavailable')


def eligible(table, boundaries):
    source.require(boundaries['source'] == source.BOUNDARY and boundaries['window'] == source.WINDOW,
                   'Wrong retained public boundary inventory')
    features = boundaries['response']['features']
    source.require(boundaries['response']['count'] == len(features) <= 80, 'Incomplete boundary inventory')
    counts = Counter(f['shapeName'] for f in features)
    exact = {f['shapeName']: f for f in features if counts[f['shapeName']] == 1 and f['shapeGroup'] == 'IND'}
    relationships = Counter(c['ifi_project_event_id'] for c in table if c['gfd_id'] is not None)
    pool, exclusions = [], []
    for ordinal, c in enumerate(table):
        reason = None
        if c['gfd_id'] in EXCLUDED_IDS: reason = 'previously_reviewed_gfd'
        elif c['gfd_id'] is None: reason = c['candidate_status']
        elif c['candidate_status'] == 'ambiguous' or relationships[c['ifi_project_event_id']] != 1: reason = 'ambiguous'
        elif c['candidate_status'] != 'strong_temporal_candidate': reason = 'not_strong_temporal'
        elif c['ifi_state_original'] != 'Karnataka': reason = 'not_karnataka_only'
        elif not c['ifi_start'] or not c['ifi_end_inclusive'] or c['ifi_start'] > c['ifi_end_inclusive']: reason = 'invalid_ifi_window'
        elif c['ifi_start'] > source.COVERAGE[1] or c['ifi_end_inclusive'] < source.COVERAGE[0]: reason = 'outside_gfd_coverage'
        elif c['original_properties'].get('dfo_country') != 'India' or 'IND' not in {
                v.strip() for v in c['original_properties'].get('cc', '').split(',')}: reason = 'primary_dfo_india_not_verified'
        tokens = [] if reason else [v.strip() for v in c['ifi_district_tokens_original'].split(',')]
        matches = sorted(set(tokens) & set(exact))
        if not reason and not matches: reason = 'no_unique_exact_public_district_token'
        if reason:
            exclusions.append({'candidate_ordinal': ordinal, 'ifi_project_event_id': c['ifi_project_event_id'],
                               'gfd_id': c['gfd_id'], 'reason': reason})
        else:
            timing = source.overlap(c['ifi_start'], c['ifi_end_inclusive'], c['gfd_start'], c['gfd_end_inclusive'])
            source.require(timing == c['temporal_overlap'] and timing['ifi_fraction'] >= .8, 'Temporal metadata conflict')
            for name in matches:
                pool.append({**c, 'candidate_ordinal': ordinal, 'review_region': exact[name], 'source_token_count': len(tokens)})
    pool.sort(key=lambda c: (c['gfd_id'], c['ifi_project_event_id'], c['review_region']['shapeID']))
    return pool, exclusions


def validate_geography(row, candidate):
    source.require(row['gfd_id'] == candidate['gfd_id'] and row['shapeID'] == candidate['review_region']['shapeID'],
                   'Geographic association identity changed')
    source.require(row['feature_count'] == 1 and row['shapeName'] == candidate['review_region']['shapeName'],
                   'Public feature identity is ambiguous')
    source.require(row['properties']['id'] == candidate['gfd_id'] and row['properties']['dfo_country'] == 'India' and
                   row['properties']['system:index'] == candidate['original_properties']['system:index'], 'Live source metadata conflict')
    source.require(math.isfinite(row['region_area_km2']) and 0 < row['region_area_km2'] <= 20000, 'Unmanageable review region')
    source.require(row['state_fraction'] >= .99 and row['footprint_intersection_km2'] > 0,
                   'Public Karnataka containment or event footprint unavailable')
    plan = grid.planner(row['bounds'][0], {'crs': source.CRS, 'transform': source.TRANSFORM})
    return plan


def selection(table, boundaries, geography, previous, limit=10):
    source.require(type(limit) is int and 1 <= limit <= 10, 'Second batch must contain at most ten events')
    pool, exclusions = eligible(table, boundaries)
    source.require(geography['state_source'] == STATE_SOURCE and geography['state_feature_count'] == 1 and
                   geography.get('state_identity') == {'shapeID': STATE_ID, 'shapeName': STATE_NAME, 'shapeGroup': 'IND'},
                   'Public Karnataka state identity unavailable')
    rows = {(r['gfd_id'], r['shapeID']): r for r in geography['rows']}
    source.require(len(rows) == len(geography['rows']), 'Duplicate geographic metadata')
    accepted = []
    for c in pool:
        key = (c['gfd_id'], c['review_region']['shapeID'])
        source.require(key in rows, 'Missing retained geographic metadata')
        try:
            plan = validate_geography(rows[key], c)
        except ValueError as exc:
            exclusions.append({'candidate_ordinal': c['candidate_ordinal'], 'gfd_id': c['gfd_id'],
                'shapeID': key[1], 'reason': str(exc)})
            continue
        accepted.append({**c, 'association_evidence': rows[key], 'planned_partition_count': plan['partition_count']})
    years = {r['gfd_start'][:4] for r in previous} | {'2005', '2009'}
    regions = {r['review_region']['shapeName'] for r in previous} | {'Udupi'}
    selected, rounds = [], []
    original_pool = accepted.copy()
    while accepted and len(selected) < limit:
        def rank(c):
            return (c['gfd_start'][:4] in years, c['review_region']['shapeName'] in regions,
                    -c['temporal_overlap']['ifi_fraction'], -c['temporal_overlap']['jaccard'],
                    c['association_evidence']['region_area_km2'], c['source_token_count'],
                    c['gfd_id'], c['ifi_project_event_id'], c['review_region']['shapeID'])
        ordered = sorted(accepted, key=rank)
        rounds.append([{'gfd_id': c['gfd_id'], 'ifi_project_event_id': c['ifi_project_event_id'],
                        'shapeID': c['review_region']['shapeID'], 'rank': list(rank(c))} for c in ordered])
        chosen = ordered[0]; selected.append(chosen)
        years.add(chosen['gfd_start'][:4]); regions.add(chosen['review_region']['shapeName'])
        accepted = [c for c in accepted if c['gfd_id'] != chosen['gfd_id']]
    return {'rule': RULE, 'limit': limit, 'excluded_gfd_ids': sorted(EXCLUDED_IDS), 'selected': selected,
            'eligible_ranking_pool': original_pool, 'ranking_rounds': rounds, 'exclusions': exclusions,
            'exclusion_counts': dict(sorted(Counter(r['reason'] for r in exclusions).items())),
            'association_status': 'defensible_research_candidate_only_not_ifi_confirmation'}


class TimedEE(grid.BoundedEE):
    """Same bounded retry policy, plus acceptance and suspension telemetry."""
    def request(self, fn, name):
        def sleep(seconds):
            source.require(grid.elapsed_clock() - self.start + seconds < self.total, 'Total recovery deadline reached')
            time.sleep(seconds)
        def call():
            started, mono_start = grid.elapsed_clock(), time.monotonic()
            remaining = self.total - (started - self.start)
            source.require(remaining > 0, 'Total recovery deadline reached')
            row = {'operation': name, 'started_at': source.now(), 'start_monotonic_seconds': mono_start,
                   'start_suspend_aware_seconds': started, 'deadline_seconds': self.deadline,
                   'total_remaining_seconds': remaining, 'accepted': False}
            try:
                with verification.wall_limit(min(self.deadline, remaining)):
                    result = fn()
                finished = grid.elapsed_clock()
                source.require(finished - self.start < self.total, 'Total recovery deadline reached; late result rejected')
                if finished - started > self.deadline:
                    raise TimeoutError('Request exceeded pause-inclusive deadline; late result rejected')
                row.update(accepted=True, accepted_at=source.now(), deadline_status='within_budget')
                return result
            except verification.VerificationDeadlineExceeded:
                row.update(deadline_status='active_request_deadline_exceeded')
                raise TimeoutError('Recovery request exceeded deadline') from None
            except Exception as exc:
                row.update(error=source.provider_error(exc), deadline_status='rejected_or_failed')
                raise
            finally:
                mono_end, finish = time.monotonic(), grid.elapsed_clock()
                pause = (finish - started) - (mono_end - mono_start)
                row.update(finished_at=source.now(), end_monotonic_seconds=mono_end,
                           end_suspend_aware_seconds=finish, elapsed_seconds=finish-started,
                           suspension_clock_available=hasattr(time, 'CLOCK_BOOTTIME'),
                           suspension_detected=hasattr(time, 'CLOCK_BOOTTIME') and pause > 1,
                           suspension_estimate_seconds=max(0, pause))
                with (self.raw/'timing.jsonl').open('a') as stream:
                    stream.write(json.dumps(row, allow_nan=False)+'\n')
        return retry.bounded_request(call, name, self.raw/'requests.jsonl', sleep=sleep)


def geographical_metadata(session, pool):
    ee = session.ee
    state = ee.FeatureCollection(STATE_SOURCE).filter(ee.Filter.eq('shapeGroup', 'IND')).filter(ee.Filter.eq('shapeID', STATE_ID))
    seen, pairs = set(), []
    props = ['id', 'system:index', 'cc', 'countries', 'dfo_country', 'dfo_other_country',
             'dfo_centroid_x', 'dfo_centroid_y', 'dfo_main_cause', 'dfo_validation_type', 'glide_index']
    for c in pool:
        key = (c['gfd_id'], c['review_region']['shapeID'])
        if key in seen: continue
        seen.add(key)
        feature = ee.FeatureCollection(source.BOUNDARY).filter(ee.Filter.eq('shapeID', key[1]))
        geom = feature.geometry(); area = geom.area(1)
        image = ee.Image(c['image_id'])
        pairs.append(ee.Dictionary({'gfd_id': key[0], 'shapeID': key[1], 'feature_count': feature.size(),
            'shapeName': feature.first().get('shapeName'), 'region_area_km2': area.divide(1e6),
            'state_fraction': geom.intersection(state.geometry(),1).area(1).divide(area),
            'footprint_intersection_km2': geom.intersection(image.geometry(),1).area(1).divide(1e6),
            'bounds': geom.bounds(1,ee.Projection(source.CRS)).coordinates(),
            'properties': image.toDictionary(props)}))
    source.require(len(pairs) <= 32, 'Geographic metadata query exceeds bounded 32-pair scope')
    response = session.request(lambda: ee.Dictionary({'state_source': STATE_SOURCE,
        'state_feature_count': state.size(),
        'state_identity': state.first().toDictionary(['shapeID', 'shapeName', 'shapeGroup']),
        'rows': pairs}).getInfo(), 'candidate_geographic_metadata')
    response.update(retrieved_at=source.now(), source_boundary=source.BOUNDARY,
                    semantics='footprint and public state containment only; no flood-pixel inspection')
    source.write_new(session.raw/'geography.json',response)
    return response


def prior_gate(previous):
    grid.validate(previous)
    records=read(previous/'event_evidence.json')
    source.require([r['gfd_id'] for r in records] == grid.IDS, 'Protected first-batch selection changed')
    positive=next(r for r in records if r['gfd_id']==3652)
    source.require(positive['computation_complete'] and positive['evidence_status']=='satellite_positive' and
                   positive['statistics']['qualifying_pixels']==2, 'Protected 3652 regression failed')
    udupi=grid.udupi_gate(ROOT/'data/processed/udupi_flood_spatial_v1',{'crs':source.CRS,'transform':source.TRANSFORM})
    return {'udupi':udupi,'event_3652_qualifying_pixels':2,'files_modified':0}


def review(session,candidate):
    eid=candidate['gfd_id']
    record={k:candidate[k] for k in ['gfd_id','image_id','ifi_project_event_id','ifi_source_event_id',
        'ifi_start','ifi_end_inclusive','gfd_start','gfd_end_inclusive','review_region','association_status','association_evidence']}
    record.update(ifi_confirmation=False,semantics='event_window_maximum_not_daily_occurrence',partitions=[],
                  evidence_status='incomplete_computation',computation_complete=False,statistics=None)
    try:
        validate_geography(candidate['association_evidence'],candidate)
        image=session.ee.Image(candidate['image_id'])
        projection,metadata,actual_grid=grid.projection_metadata(session,image,eid)
        record.update(source_projection_metadata=metadata,analysis_grid=actual_grid)
        plan,regions,owners=grid.preflight(session,candidate,projection,actual_grid)
        plan.update(ifi_project_event_id=candidate['ifi_project_event_id'],ifi_source_event_id=candidate['ifi_source_event_id'])
        record['preflight']=plan
        source.write_new(session.raw/f'event_{eid}_preflight.json',plan)
        image=grid.evidence_image(session.ee,image,projection)
        for i,p in enumerate(plan['partitions']):
            part={'index':i,'window':p['window']};record['partitions'].append(part)
            if plan['geometry_check']['partitions'][i]['area_m2']==0:
                part.update(statistics=dict.fromkeys(grid.METRICS,0),empty_geometry_skipped=True)
            else:
                expression=image.updateMask(owners[i]).reduceRegion(reducer=session.ee.Reducer.sum().unweighted(),
                    geometry=regions[i],**grid.reducer_parameters(actual_grid))
                part['reduction_expression_sha256']=hashlib.sha256(expression.serialize().encode()).hexdigest()
                result=session.request(lambda:expression.getInfo(),f'reduce:{eid}:{i}')
                source.require(isinstance(result,dict),'Invalid reduction response')
                # Null sums represent zero counted cells, not environmental measurements.
                part['statistics']={name:0 if result.get(name) is None else result[name] for name in grid.METRICS}
            try:grid.validate_part(part,p)
            except Exception:
                part['rejected_statistics']=part.pop('statistics');raise
            record.update(grid.outcome(record['partitions'],plan['partition_count']),retrieved_at=source.now())
            with (session.raw/'progress.jsonl').open('a') as handle:
                handle.write(json.dumps({'gfd_id':eid,'partition':part,'retrieved_at':record['retrieved_at']},allow_nan=False)+'\n')
        counts=record['statistics']
        record['unusable_region_cells']=counts['region_pixels']-counts['valid_pixels']
    except Exception as exc:
        if record['partitions']:record['partitions'][-1]['error']=source.provider_error(exc)
        record.update(grid.outcome(record['partitions'],record.get('preflight',{}).get('partition_count',0)),
                      error=source.provider_error(exc),retrieved_at=source.now())
    source.write_new(session.raw/f'event_{eid}_checkpoint.json',record)
    return record


def cumulative(previous,records):
    combined=[{'gfd_id':2728,'gfd_start':'2005-09-14','review_region':{'shapeName':'Udupi'},
               'evidence_status':'satellite_positive','statistics':{'qualifying_pixels':33}},
              {'gfd_id':3551,'gfd_start':'2009-09-25','review_region':{'shapeName':'Udupi'},
               'evidence_status':'satellite_positive','statistics':{'qualifying_pixels':23}}]+previous+records
    source.require(len({r['gfd_id'] for r in combined})==len(combined),'Duplicate cumulative event')
    statuses={s:sum(r['evidence_status']==s for r in combined) for s in sorted(FINAL_STATUSES)}
    positives=[r for r in combined if r['evidence_status']=='satellite_positive']
    return {'reviewed_events':len(combined),'status_counts':statuses,
        'qualifying_pixels':sum((r.get('statistics') or {}).get('qualifying_pixels',0) for r in combined),
        'qualifying_counts_are_lower_bounds':any(r.get('counts_are_lower_bounds',False) for r in combined),
        'reviewed_years':sorted({r['gfd_start'][:4] for r in combined}),
        'reviewed_regions':sorted({r['review_region']['shapeName'] for r in combined}),
        'positive_years':sorted({r['gfd_start'][:4] for r in positives}),
        'positive_regions':sorted({r['review_region']['shapeName'] for r in positives}),
        'ifi_confirmations':0,'daily_labels_created':0}


def run(previous,output,raw,limit=10,deadline=60,total=900):
    source.require(not output.exists() and not raw.exists(),'Version exists; never overwrite completed or interrupted work')
    source.require(not any((p/'manifest.json').exists() for folder in [output,raw] for p in folder.resolve().parents),
                   'Cannot write inside a completed version')
    verify_state_inventory(STATE_INVENTORY)
    gates=prior_gate(previous);table=read(previous/'candidates.json');boundaries=read(BOUNDARIES)
    original=read(previous/'event_evidence.json');pool,exclusions=eligible(table,boundaries)
    raw.mkdir(parents=True,exist_ok=False)
    records=[];selection_result=None;access={}
    try:
        session=TimedEE(raw,deadline,total);session.initialize();access['initialization_succeeded']=True
        geography=geographical_metadata(session,pool)
        selection_result=selection(table,boundaries,geography,original,limit)
        source.write_new(raw/'selection.json',selection_result)
        for c in selection_result['selected']:
            record=review(session,c);records.append(record)
            print(json.dumps({'gfd_id':record['gfd_id'],'status':record['evidence_status'],
                              'statistics':record['statistics']}),flush=True)
            source.require(record['computation_complete'],'Event failed; remaining batch not started')
        access['regression_gates_after']=prior_gate(previous)
    except Exception as exc:access['stopped_error']=source.provider_error(exc)
    finally:
        access['finished_at']=source.now();source.write_new(raw/'access.json',access)
    output.mkdir(parents=True,exist_ok=False)
    with (output/'candidates.json').open('xb') as handle:handle.write((previous/'candidates.json').read_bytes())
    source.write_new(output/'selection.json',selection_result)
    source.write_new(output/'event_evidence.json',records)
    selected=[] if selection_result is None else [c['gfd_id'] for c in selection_result['selected']]
    manifest={'version':output.name,'schema_version':3,'created_at':source.now(),'source':source.SOURCE,
        'license':'CC BY-NC 4.0','license_url':'https://creativecommons.org/licenses/by-nc/4.0/',
        'attribution':'Cloud to Street / Dartmouth Flood Observatory; Tellman et al. doi:10.1038/s41586-021-03695-w; IFI Saharia et al. doi:10.5281/zenodo.16994648',
        'boundary_source':source.BOUNDARY,'state_source':STATE_SOURCE,'boundary_license':'CC BY 4.0; geoBoundaries v6, William & Mary geoLab',
        'catalogue_discrepancy':'Description 250 m classification; band table 30 m; actual live projections retained, analysis fixed to verified 250 m grid.',
        'previous':str(previous.resolve()),'previous_files':{p.name:source.fingerprint(p) for p in previous.iterdir() if p.is_file()},
        'boundary_inventory':{'path':str(BOUNDARIES),'fingerprint':source.fingerprint(BOUNDARIES)},
        'state_identity_inventory':{'path':str(STATE_INVENTORY),'fingerprint':source.fingerprint(STATE_INVENTORY)},
        'access':access,'regression_gates_before':gates,'selected_ids':selected,
        'unreviewed_ids':[i for i in selected if i not in {r['gfd_id'] for r in records}],
        'summary':cumulative(original,records),'parameters':{'deadline_seconds':deadline,'total_seconds':total,
          'max_attempts':3,'backoff_seconds':[2,4],'crs':source.CRS,'transform':source.TRANSFORM,'scale_m':250,
          'maxPixels':300000,'bestEffort':False,'tileScale':2,'metric_bands':grid.METRICS,'safety_factor':1.25,
          'target_band_pixels':90000,'valid_fraction_zero_gate':source.MIN_VALID_FRACTION,'alignment':grid.ALIGNMENT},
        'files':{n:source.fingerprint(output/n) for n in ['candidates.json','selection.json','event_evidence.json']},
        'raw_files':{str(p.resolve()):source.fingerprint(p) for p in raw.iterdir() if p.is_file()},
        'execution_code':{str(Path(p).resolve()):source.fingerprint(p) for p in [__file__,grid.__file__,source.__file__]},
        'quality_semantics':'Raw source clear_views/clear_perc/duration sums and means; no guessed days/percentage normalization; event-window extent not daily occurrence.',
        'publication':'Detailed events and raw journals remain local; only code/tests and aggregate provenance reviewed for publication.'}
    source.write_new(output/'manifest.json',manifest)
    return validate(output)


def validate(output):
    manifest=read(output/'manifest.json');previous=Path(manifest['previous'])
    source.require(manifest['schema_version']==3 and manifest['source']==source.SOURCE and manifest['license']=='CC BY-NC 4.0','Invalid new dataset identity')
    prior_gate(previous)
    source.require(manifest['regression_gates_before']==prior_gate(previous),'Protected regression gate changed')
    for name,value in manifest['raw_files'].items():
        source.require(source.fingerprint(name)==value,'Retained extraction input changed')
    # Extraction code is versioned provenance, not a demand that future code
    # remain identical. Verify an exact retained snapshot when it has changed;
    # never rewrite the dataset's recorded expected code checksum.
    verify_execution_code(manifest['execution_code'])
    for key,folder in [('files',output),('previous_files',previous)]:
        for name,value in manifest[key].items():
            source.require(Path(name).name==name and source.fingerprint(folder/name)==value,'Dataset checksum changed')
    boundary=manifest['boundary_inventory'];source.require(source.fingerprint(boundary['path'])==boundary['fingerprint'],'Boundary metadata changed')
    if 'state_identity_inventory' in manifest:
        state=manifest['state_identity_inventory']
        source.require(source.fingerprint(state['path'])==state['fingerprint'],'State identity source changed')
        verify_state_inventory(state['path'])
    source.require((output/'candidates.json').read_bytes()==(previous/'candidates.json').read_bytes(),'Candidate bytes changed')
    selected=read(output/'selection.json');original=read(previous/'event_evidence.json')
    records=read(output/'event_evidence.json')
    if selected is not None:
        geo=read(Path(next(n for n in manifest['raw_files'] if Path(n).name=='geography.json')))
        reconstructed=selection(read(output/'candidates.json'),read(boundary['path']),geo,original,selected['limit'])
        source.require(selected==reconstructed,'Selection/ranking reconstruction changed')
        source.require(manifest['selected_ids']==[c['gfd_id'] for c in selected['selected']],'Selected IDs changed')
    else:source.require(not records and not manifest['selected_ids'],'Records without a validated selection')
    source.require([r['gfd_id'] for r in records]==manifest['selected_ids'][:len(records)],'Sequential order changed')
    source.require(manifest['unreviewed_ids']==manifest['selected_ids'][len(records):],'Unreviewed IDs changed')
    for r,c in zip(records,selected['selected'] if selected else []):
        source.require(r['evidence_status'] in FINAL_STATUSES and r['ifi_confirmation'] is False,'Invalid evidence status/promotion')
        for key in ['gfd_id','image_id','ifi_project_event_id','ifi_source_event_id','ifi_start','ifi_end_inclusive',
                    'gfd_start','gfd_end_inclusive','review_region','association_evidence']:
            source.require(r[key]==c[key],'Evidence source identity changed')
        if 'preflight' in r:
            actual_grid=grid.analysis_grid(r['source_projection_metadata']);source.require(actual_grid==r['analysis_grid'],'Analysis grid changed')
            plan=grid.planner(r['preflight']['region']['bounds'][0],actual_grid)
            for key,value in plan.items():source.require(r['preflight'][key]==value,'Preflight reconstruction changed')
            source.require(r['preflight']['ifi_project_event_id']==c['ifi_project_event_id'] and
                           r['preflight']['ifi_source_event_id']==c['ifi_source_event_id'],'Preflight IFI identity changed')
            grid.check_geometry(r['preflight'])
            for i,p in enumerate(r['partitions']):
                source.require(p['index']==i and p['window']==plan['partitions'][i]['window'],'Duplicate/changed partition ownership')
                if 'statistics' in p:grid.validate_part(p,plan['partitions'][i])
            for key,value in grid.outcome(r['partitions'],plan['partition_count']).items():
                source.require(r[key]==value,'Statistics/evidence reconstruction changed')
            if r['computation_complete']:
                source.require(r['unusable_region_cells']==r['statistics']['region_pixels']-r['statistics']['valid_pixels'],'Unusable coverage changed')
        source.require(r==read(Path(next(n for n in manifest['raw_files'] if Path(n).name==f"event_{r['gfd_id']}_checkpoint.json"))),
                       'Per-event checkpoint differs')
    summary=cumulative(original,records);source.require(summary==manifest['summary'],'Cumulative summary changed')
    timings=[]
    for path in manifest['raw_files']:
        if Path(path).name=='timing.jsonl':timings=[json.loads(line) for line in Path(path).read_text().splitlines()]
    for t in timings:
        if t['accepted']:
            source.require(t['deadline_status']=='within_budget' and t['elapsed_seconds']<=t['deadline_seconds'] and
                           t['elapsed_seconds']<t['total_remaining_seconds'] and t.get('accepted_at'),'Late result accepted')
    if not manifest['access'].get('stopped_error'):
        source.require(not manifest['unreviewed_ids'] and manifest['access']['regression_gates_after']==prior_gate(previous),
                       'Completed batch lacks regression gates')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous',type=Path,default=PREVIOUS)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--raw',type=Path,default=RAW)
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--deadline',type=int,default=60)
    parser.add_argument('--total-seconds',type=int,default=900)
    parser.add_argument('--validate-only',type=Path)
    args=parser.parse_args()
    result=validate(args.validate_only) if args.validate_only else run(args.previous,args.output,args.raw,args.limit,args.deadline,args.total_seconds)
    print(json.dumps(result,indent=2),flush=True)
    if not args.validate_only and read(args.output/'manifest.json')['access'].get('stopped_error'):raise SystemExit(2)


if __name__=='__main__':main()
