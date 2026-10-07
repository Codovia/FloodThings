#!/usr/bin/env python3
"""Stage 4E: bounded offline topology and authoritative time-semantics closure.

Build a separate immutable version; never alter Stage 4A-D or source data.
No credential access, network, model-discharge matching, features or labels.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from html import unescape
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage4e_v1'
STATIC = ROOT / 'data/raw/reference/glofas_v5_static'
PRIOR = ROOT / 'data/working/karnataka_glofas_2019_pilot_v1'
SEMANTICS = ROOT / 'data/working/karnataka_hydrology_semantics_v1'
BOOK = ROOT / 'data/raw/reference/stage4b_v1/krishna_wyb2019_20.pdf'
HANDBOOK = ROOT / 'data/raw/reference/stage4c2_v1/cwc_handbook2020.pdf'
OUTPUT = ROOT / 'data/working/karnataka_hydrology_closure_v1'
PUBLIC = ROOT / 'data/reference/karnataka_hydrology_closure_v1/manifest.json'
STATION = 'CW1KRU000212'
RESOURCE = 'f95150ea-c8fc-4740-8815-d9c34c9d53a3'
LDD = {1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, -1),
       5: (0, 0), 6: (0, 1), 7: (-1, -1), 8: (-1, 0), 9: (-1, 1)}
TEMPORAL = {'temporal_semantics_resolved', 'temporal_semantics_partially_resolved',
            'temporal_semantics_unresolved'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    p = Path(path)
    return {'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': digest(p)}


def plain(body):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', body))).strip()


def pdf_page(path, page):
    text = subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), '-layout',
                           str(path), '-'], capture_output=True, text=True, check=True, timeout=30).stdout
    return re.sub(r'\s+', ' ', text).strip()


def prior_module():
    spec = importlib.util.spec_from_file_location('stage4d_pilot', ROOT / 'scripts/build_glofas_pilot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_prior():
    module = prior_module()
    eligible = module.prior_gate()  # Hashes, source values, 1697/81/14 and 33 conflicts.
    manifest = read(PRIOR / 'manifest.json')
    require(manifest['summary']['modelled_rows'] == 806, 'Stage 4D baseline changed')
    for name, expected in manifest['files'].items():
        require(Path(name).name == name and record(PRIOR / name)['sha256'] == expected['sha256']
                and (PRIOR / name).stat().st_size == expected['bytes'], 'Stage 4D integrity changed')
    require(manifest['processing_code'] == record(ROOT / 'scripts/build_glofas_pilot.py'), 'Stage 4D code changed')
    for source in manifest['inputs']:
        require(record(ROOT / source['path']) == source, 'Stage 4D input changed')
    return module, eligible


def cell_id(row, column):
    return f'{row}:{column}'


def target(row, column, code):
    require(code in set(LDD) | {None}, 'Unrecognised drainage direction')
    if code in {None, 5}:
        return None
    dr, dc = LDD[code]
    return cell_id(row + dr, column + dc)


def trace(start, cells, maximum_steps=8):
    """Finite local model path; no claim of complete catchment tracing."""
    require(1 <= maximum_steps <= 8, 'Unbounded topology request')
    path = []
    current = start
    for _ in range(maximum_steps):
        if current not in cells:
            return {'cells': path, 'stop': 'outside_bounded_window'}
        require(current not in path, 'Cycle in drainage directions')
        row = cells[current]
        path.append(current)
        if not row['channel_positive']:
            return {'cells': path, 'stop': 'channel_not_marked_or_nodata'}
        if row['ldd_code'] is None:
            return {'cells': path, 'stop': 'direction_unavailable'}
        if row['ldd_code'] == 5:
            return {'cells': path, 'stop': 'model_pit'}
        current = target(row['row'], row['column'], row['ldd_code'])
    return {'cells': path, 'stop': 'step_limit'}


def predecessors(key, cells):
    return sorted(k for k, c in cells.items() if c['channel_positive'] and
                  target(c['row'], c['column'], c['ldd_code']) == key)


def reach_decision(candidates, *, independent_anchor=None):
    """Connectivity/area alone cannot determine which side of a junction has the gauge."""
    require(len(candidates) == 2 and len({c['cell_id'] for c in candidates}) == 2,
            'Both original Gokak candidates required')
    selected = None
    if independent_anchor is not None:
        # This task supplies no such anchor. A future explicit official crosswalk is required.
        require(set(independent_anchor) == {'station_id', 'cell_id', 'source_type', 'url', 'sha256', 'version'},
                'Independent static evidence required; no magnitude/timing selection')
        require(independent_anchor['station_id'] == STATION and independent_anchor['version'] == '5.0'
                and independent_anchor['source_type'] == 'official_station_to_model_reach_link'
                and re.fullmatch(r'[0-9a-f]{64}', independent_anchor['sha256'])
                and urlparse(independent_anchor['url']).scheme == 'https'
                and urlparse(independent_anchor['url']).hostname in
                {'cwc.gov.in', 'www.cwc.gov.in', 'jeodpp.jrc.ec.europa.eu', 'data.jrc.ec.europa.eu'},
                'Unverified station/reach anchor')
        selected = independent_anchor['cell_id']
        require(any(c['cell_id'] == selected and c['channel_positive'] for c in candidates), 'Anchor outside candidates')
    return {'station_id': STATION, 'status': 'station_grid_match_supported' if selected else 'station_grid_match_ambiguous',
            'selected_model_cell': selected, 'station_coordinate_status': 'coordinate_conflict_unresolved',
            'canonical_coordinate_selected': False, 'coordinate_conflict_resolved': False,
            'independent_anchor': deepcopy(independent_anchor),
            'reason': 'Explicit official station/reach anchor, independent of discharge' if selected else
            'Both cells lie on a connected model path; area and connectivity do not place the gauge relative to the eastern junction'}


def temporal_decision(measured, modelled, *, contextual_evidence=False):
    """Require independently defined statistic, timezone and exact bounds; never join by date alone."""
    require(measured['hydrology_source_type'] in {'measured_cwc_nwdp', 'published_cwc_yearbook'} and
            modelled['hydrology_source_type'] == 'modelled_glofas', 'Measured/modelled source conflation')
    require(measured['variable'] == modelled['variable'] == 'discharge', 'No water-level comparisons')
    fields = ['statistic', 'timezone', 'interval_start', 'interval_end']
    documented = all(measured.get(k) is not None and modelled.get(k) is not None for k in fields)
    compatible = (documented and measured.get('exact_field_documented') is True and
                  modelled.get('exact_field_documented') is True and measured['statistic'] == 'mean' and
                  all(measured[k] == modelled[k] for k in fields))
    if compatible:
        start = datetime.fromisoformat(modelled['interval_start'])
        end = datetime.fromisoformat(modelled['interval_end'])
        require(modelled['timezone'] == 'UTC' and start.utcoffset() == end.utcoffset() == timedelta(0)
                and end - start == timedelta(days=1), 'Exact documented model24h UTC interval required')
    status = ('temporal_semantics_resolved' if compatible else
              'temporal_semantics_partially_resolved' if contextual_evidence or documented else
              'temporal_semantics_unresolved')
    return {'status': status, 'pointwise_comparison_allowed': compatible,
            'aligned_quantitative_pairs': 0,
            'performance_metrics_allowed': False, 'features_created': 0, 'flood_labels_created': 0}


def readiness(reach_status, temporal_status):
    require(reach_status in {'station_grid_match_supported', 'station_grid_match_ambiguous'} and
            temporal_status in TEMPORAL, 'Unknown semantic status')
    if reach_status == 'station_grid_match_supported' and temporal_status == 'temporal_semantics_resolved':
        return 'hydrology_semantics_ready'
    if reach_status == 'station_grid_match_supported' or temporal_status != 'temporal_semantics_unresolved':
        return 'hydrology_semantics_ready_limited'
    return 'hydrology_semantics_blocked_by_source_metadata'


def network(module):
    from netCDF4 import Dataset
    history = next(s for s in read(SEMANTICS / 'coordinate_provenance.json') if s['station_id'] == STATION)
    require(history['status'] == 'coordinate_conflict_unresolved', 'Station coordinate status changed')
    coords = module.coordinates(history)
    direct = []; cells = {}
    with Dataset(STATIC / 'upArea_repaired_correctedmetadata_3000.nc') as a, \
            Dataset(STATIC / 'chan_Global_03min.nc') as ch, Dataset(STATIC / 'ldd_repaired.nc') as ld:
        lat = np.asarray(a['lat'][:]); lon = np.asarray(a['lon'][:])
        for d in [ch, ld]:
            require(np.array_equal(d['lat'][:], lat) and np.array_equal(d['lon'][:], lon), 'Static alignment changed')
        positions = [(module.nearest(lat, c['latitude']), module.nearest(lon, c['longitude'])) for c in coords]
        unique = sorted(set(positions))
        require(len(unique) == 2, 'Gokak candidate baseline changed')
        selected_area = next(r for r in read(PRIOR / 'cwc_catchment_provenance.json') if r['station_id'] == STATION)
        area_km2 = selected_area['area_km2']
        for c, (row, col) in zip(coords, positions):
            for candidate_row, candidate_col in unique:
                direct.append({**c, 'nearest_static_cell': cell_id(row, col),
                               'candidate_cell': cell_id(candidate_row, candidate_col),
                               'candidate_latitude': float(lat[candidate_row]), 'candidate_longitude': float(lon[candidate_col]),
                               'distance_m': module.distance([c['latitude'], c['longitude']],
                                                            [float(lat[candidate_row]), float(lon[candidate_col])])})
        positions = sorted({(r, c) for i, j in unique for r in range(i-2, i+3) for c in range(j-2, j+3)})
        require(len(positions) <= 30, 'Unbounded local window')
        for i, j in positions:
            area = module.scalar(a['Band1'][i, j]); channel = module.scalar(ch['Band1'][i, j]); code = module.scalar(ld['Band1'][i, j])
            code = int(code) if code is not None else None
            require(code in set(LDD) | {None}, 'Unknown direction')
            cells[cell_id(i, j)] = {'cell_id': cell_id(i, j), 'row': i, 'column': j, 'latitude': float(lat[i]),
                'longitude': float(lon[j]), 'channel_positive': channel == 1,
                'channel_mask_status': 'positive' if channel == 1 else 'not_marked_or_nodata',
                'ldd_code': code, 'downstream_cell': target(i, j, code), 'upstream_area_m2': area,
                **module.area_comparison(area, area_km2)}
    candidates = []
    for key in [cell_id(*p) for p in unique]:
        incoming = predecessors(key, cells)
        row = deepcopy(cells[key])
        row.update(incoming_channel_cells=incoming, path=trace(key, cells),
                   incoming_channel_upstream_area_m2=[cells[k]['upstream_area_m2'] for k in incoming])
        candidates.append(row)
    west, east = candidates
    require(west['longitude'] < east['longitude'], 'Candidate west/east ordering changed')
    topology = {'bounded_cells': len(cells), 'west_to_east_connected': east['cell_id'] in west['path']['cells'],
                'west_incoming_count': len(west['incoming_channel_cells']), 'east_incoming_count': len(east['incoming_channel_cells']),
                'same_connected_model_channel_path': east['cell_id'] in west['path']['cells'],
                'east_is_model_junction': len(east['incoming_channel_cells']) > 1,
                'named_river_mapping_available': False, 'cwc_documentary_river': 'Ghataprabha',
                'named_tributaries_inferred': False,
                'limitation': 'Static Band1 grids contain no river names/station crosswalk. Connected path is not proof of gauge location; upstream/downstream sides of a junction remain distinct.'}
    return {'station_candidates': candidates, 'coordinate_distances': direct, 'local_network_cells': list(cells.values()),
            'topology': topology, 'decision': reach_decision(candidates)}


def document_register():
    docs = []
    for name, title, version in [('nwdp_discharge_resource.html', 'NWDP Karnataka CWC manual daily discharge resource', 'resource metadata'),
        ('nwdp_discharge_catalogue.json', 'NWDP official CWC discharge catalogue', 'dataset v1'),
        ('nwdp_discharge_preview.html', 'NWDP resource Preview and field schema', 'resource metadata'),
        ('cf_time.html', 'CF Metadata Conventions', '1.7, section4.4'),
        ('model_output.html', 'ECMWF CEMS Model Output', 'live documentation')]:
        side = read(RAW / (name + '.json')); require(side['status'] == 'retrieved' and side['http_status'] == '200', 'Source document unavailable')
        require(digest(RAW / name) == side['sha256'], 'Source response checksum changed')
        docs.append({'title': title, 'version': version, **record(RAW / name),
                     'url': side['source_url'], 'retrieved_at': side['retrieved_at']})
    for path, title, version in [(BOOK, 'CWC Krishna Water Year Book VolumeI2019-20', 'March2021; PDF21-23,590'),
                                (HANDBOOK, 'CWC Hand Book of Hydro-Meteorological Observations', 'June2020; PDF23,57,139,188-189')]:
        side = read(Path(str(path) + '.json'))
        docs.append({'title': title, 'version': version, **record(path), 'url': side['source_url'], 'retrieved_at': side['retrieved_at']})
    return docs


def static_register():
    provenance = read(PRIOR / 'source_provenance.json')
    base = ('https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/'
            'LISFLOOD_static_and_parameter_maps_for_GloFAS/v2.1.1_OS-LISFLOOD-v5.x/'
            'Catchments_morphology_and_river_network/')
    names = ['upArea_repaired_correctedmetadata_3000.nc', 'chan_Global_03min.nc', 'ldd_repaired.nc']
    times = [provenance['upstream_area']['retrieved_at'],
             provenance['auxiliary_downloads']['channel']['retrieved_at'],
             provenance['auxiliary_downloads']['direction_resume']['retrieved_at']]
    return {'release': 'v2.1.1_OS-LISFLOOD-v5.x', 'model_compatibility': '5.x',
            'release_evidence': provenance['release_evidence'], 'licence': 'CC BY4.0',
            'grid': 'native0.05degree WGS84; descending latitude; no reprojection/resampling',
            'units': {'upstream_area': 'm2 from official README; no units attribute',
                      'channel': '1 positive; zero/fill not proof of river absence',
                      'direction': 'PCRaster1-9; 5pit; 255masked'},
            'files': [{**record(STATIC / name), 'url': base + name, 'retrieved_at': t,
                       'retrieval_stage': 'manual_before4D' if t is None else '4D',
                       'redownloaded_in_stage4e': False} for name, t in zip(names, times)]}


def time_evidence():
    book = {str(p): pdf_page(BOOK, p) for p in [21, 22, 23, 590]}
    handbook = {str(p): pdf_page(HANDBOOK, p) for p in [23, 57, 139, 188, 189]}
    require('commencing at about 0800 hours' in book['21'] and 'against 0800 hours water level' in book['22']
            and 'measuring time' in book['23'], 'Year Book temporal anchors absent')
    require('daily discharge observations at 8:00 hrs' in handbook['57']
            and 'MEAN GAUGE' in handbook['139'] and '08:30AM' in handbook['188'], 'Handbook temporal anchors absent')
    cf = plain((RAW / 'cf_time.html').read_text()); output = plain((RAW / 'model_output.html').read_text())
    require('if the time zone is omitted the default is UTC' in cf, 'CF timezone evidence absent')
    require('GloFAS variable river discharge' in output and 'end of averaging period' in output, 'Model interval evidence absent')
    preview = (RAW / 'nwdp_discharge_preview.html').read_text()
    fields = json.loads(re.search(r'const gdataDict = (\[.*?\])\s*\n', preview)[1])
    field_names = [f['id'] for f in fields]
    require('Data Acquisition Time' in field_names and 'Manual Daily River Water Discharge (m3/sec)' in field_names, 'Wrong resource schema')
    catalogue = read(RAW / 'nwdp_discharge_catalogue.json')['result']['results'][0]
    require(catalogue['id'] == '08fa3fd0-7861-471d-a295-27c1b239d1fa', 'Wrong source dataset')
    resource = next(r for r in catalogue['resources'] if r['id'] == RESOURCE)
    technical = read(PRIOR / 'technical_metadata.json')['historical']
    time_meta = technical['variables']['valid_time']['attributes']
    require(technical['global_attributes']['Conventions'] == 'CF-1.7' and
            time_meta['units'] == 'seconds since 1970-01-01' and 'bounds' not in time_meta, 'Time metadata changed')
    from netCDF4 import Dataset, num2date
    with Dataset(ROOT / 'data/working/glofas_access_smoke_v1/glofas_v5_karnataka_pilot_2019_jul_aug.nc') as source:
        time = source['valid_time']
        clocks = list(num2date(time[:], time.units, calendar=time.calendar, only_use_cftime_datetimes=False))
    intervals = [{'original_valid_time_utc': t.replace(tzinfo=timezone.utc).isoformat(),
                  'documented_interval_start_utc': (t.replace(tzinfo=timezone.utc)-timedelta(days=1)).isoformat(),
                  'documented_interval_end_utc': t.replace(tzinfo=timezone.utc).isoformat(),
                  'bounds_source': 'ECMWF period-end documentation; CF-default UTC; no file time bounds'} for t in clocks]
    require(len(intervals) == 62 and intervals[0]['original_valid_time_utc'].startswith('2019-07-02')
            and intervals[-1]['original_valid_time_utc'].startswith('2019-09-01'), 'Model timestamps changed')
    measured = {'hydrology_source_type': 'measured_cwc_nwdp', 'variable': 'discharge', 'statistic': None,
                'timezone': None, 'interval_start': None, 'interval_end': None, 'exact_field_documented': False}
    modelled = {'hydrology_source_type': 'modelled_glofas', 'variable': 'discharge', 'statistic': 'mean',
                'timezone': 'UTC', 'interval_start': None, 'interval_end': None, 'exact_field_documented': True}
    findings = {'nwdp': {'dataset_id': catalogue['id'], 'resource_id': RESOURCE, 'resource_title': resource['name'],
        'field_schema': fields, 'dataset_description': catalogue['notes'], 'resource_description': resource['description'],
        'units': 'm3/sec', 'frequency': 'daily', 'source_field_definition': 'unresolved',
        'timezone': 'undocumented', 'aggregation_window': 'undocumented', 'acquisition_timestamp_role': 'label_only_definition_unresolved',
        'metadata_update_timezone_not_observation_timezone': True, 'source_data_update': resource['last_modified'],
        'resource_metadata_update': resource['metadata_modified'], 'licence': catalogue['license_title'],
        'identical_semantics_to_yearbook': 'not_established'},
        'yearbook': {'source_type': 'published_cwc_yearbook', 'period': '2019-20', 'definition': 'daily_observed_or_estimated_measurement_session_flows',
        'measurement_commencement': 'about0800; except Sundays/holidays', 'estimated_discharge_anchor': '0800_gauge_reading',
        'full_day_mean_established': False, 'timezone': 'not_stated_in_reviewed_notes', 'session_end': 'record_specific_not_supplied',
        'instantaneous_at_exact0800': 'not_established; measurements have duration'},
        'handbook': {'rd1': 'daily observation at0800', 'rd2': 'ten-daily summary of observed discharge; Mean Gauge is not a daily discharge mean',
        'adcp': 'commences0830; reported average follows measurement transects, not a documented24hmean',
        'version_caveat': 'June2020 method context; not proof of method used for each2019 NWDP row',
        'publication_latency': 'eSWIS entry immediate if available; otherwise within one month; no record-specific2019 latency inferred'},
        'glofas': {'dataset_id': 'cems-glofas-historical', 'model_version': '5.0', **modelled,
        'original_units': time_meta['units'], 'calendar': time_meta['calendar'], 'timezone_basis': 'CF1.7 section4.4 defaultUTC',
        'timestamp_role': 'end_of_preceding24h_mean', 'explicit_bounds_in_file': False,
        'intervals': intervals, 'time_coordinates_modified': False},
        'decision': temporal_decision(measured, modelled, contextual_evidence=True)}
    return findings, {'yearbook_pages': book, 'handbook_pages': handbook}


def inputs():
    paths = [*RAW.iterdir(), BOOK, Path(str(BOOK)+'.json'), HANDBOOK, Path(str(HANDBOOK)+'.json'),
             SEMANTICS / 'coordinate_provenance.json', PRIOR / 'manifest.json', PRIOR / 'technical_metadata.json',
             PRIOR / 'cwc_catchment_provenance.json', PRIOR / 'source_provenance.json', ROOT / 'scripts/build_glofas_pilot.py',
             ROOT / 'data/working/glofas_access_smoke_v1/glofas_v5_karnataka_pilot_2019_jul_aug.nc',
             *[STATIC / n for n in ['upArea_repaired_correctedmetadata_3000.nc', 'chan_Global_03min.nc', 'ldd_repaired.nc']]]
    return [record(p) for p in sorted(set(paths)) if p.is_file()]


def assemble():
    module, eligible = check_prior()
    sources = document_register(); net = network(module); times, notes = time_evidence()
    summary = {'stage': '4E', 'status': readiness(net['decision']['status'], times['decision']['status']),
               'gokak_status': net['decision']['status'], 'selected_gokak_model_cell': None,
               'coordinate_conflict_resolved': False, 'reviewed_static_cells': net['topology']['bounded_cells'],
               'gokak_coordinate_variants': 4, 'coordinate_to_candidate_distances': 8,
               'temporal_status': times['decision']['status'], 'aligned_quantitative_comparisons': 0,
               'pointwise_comparison_allowed': False, 'preserved_measured_rows': 1697,
               'preserved_comparison_cases': 81, 'preserved_eligible_rows': len(eligible),
               'preserved_disagreements': 33, 'features_created': 0, 'labels_created': 0,
               'new_discharge_observations': 0, 'static_downloads': 0}
    questions = [{'id': 'gokak', 'question': 'Please establish the2019 CWC gauge reach relative to the modelled eastern confluence, using a dated official gauge/cross-section map or station-to-v5-cell crosswalk; resolve model matching separately from coordinate history.', 'station_id': STATION},
                 {'id': 'nwdp_time', 'question': 'For resource '+RESOURCE+', does the exact Manual Daily River Water Discharge field represent a measurement session, instantaneous reading, computed0800 flow or daily mean? Define Data Acquisition Time, timezone and any bounds; distinguish it from portal update UTC and Year Book revision.'},
                 {'id': 'method_history', 'question': 'Which2019 measurement method, session start/end, rating-curve/QC and publication latency apply to the14 reviewed rows? Do not manufacture historical bounds from general schedules.'}]
    limitations = {'scientific': 'Limited semantic closure: connected model path and measurement-session procedure established; station/reach crosswalk and exact NWDP temporal dictionary remain unavailable in bounded official research.',
                   'no_automatic_feature_permission': True, 'no_pointwise_comparison': True,
                   'no_source_preference': True, 'no_water_level_or_threshold_use': True,
                   'calibration_relation': 'unresolved; no independent model validation',
                   'publication': 'Detailed coordinates/topology/source observations and source documents stay local; own code, paraphrased methods and source/checksum/aggregate provenance only public',
                   'next_task': 'Obtain official Gokak reach/cross-section evidence and exact NWDP daily field/timezone/aggregation clarification; do not start ML/features.'}
    artifacts = {'gokak_reach_evidence.json': encode(net), 'temporal_evidence.json': encode(times),
                 'static_sources.json': encode(static_register()),
                 'source_documents.json': encode(sources), 'local_page_notes.json': encode(notes),
                 'unresolved_questions.json': encode(questions), 'limitations.json': encode(limitations),
                 'summary.json': encode(summary)}
    return artifacts, summary


def build(output=OUTPUT):
    output = Path(output); require(not output.exists(), 'Immutable Stage4E version exists')
    artifacts, summary = assemble()
    manifest = {'version': 'karnataka_hydrology_closure_v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                'inputs': inputs(), 'processing_code': record(Path(__file__)), 'summary': summary,
                'files': {name: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for name, b in artifacts.items()}}
    output.mkdir(parents=True)
    for name, content in artifacts.items(): (output / name).write_bytes(content)
    (output / 'manifest.json').write_bytes(encode(manifest))
    return summary


def validate(output=OUTPUT):
    output = Path(output); manifest = read(output / 'manifest.json')
    require(manifest['inputs'] == inputs() and manifest['processing_code'] == record(Path(__file__)), 'Input/code checksum changed')
    artifacts, summary = assemble()
    require(manifest['summary'] == summary and set(manifest['files']) == set(artifacts), 'Summary/files changed')
    for name, content in artifacts.items():
        require((output / name).read_bytes() == content and manifest['files'][name] ==
                {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}, 'Source-to-product reproduction failed')
    return summary


def public_manifest(output=OUTPUT):
    return {**read(Path(output) / 'manifest.json'), 'local_manifest_sha256': digest(Path(output) / 'manifest.json'),
            'sources': document_register(), 'static_sources': static_register(),
            'publication': 'Source references/checksums and aggregate statuses only; detailed evidence local'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'publish-metadata'])
    parser.add_argument('--output', type=Path, default=OUTPUT); args = parser.parse_args()
    if args.command == 'publish-metadata':
        validate(args.output); PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        with PUBLIC.open('xb') as f: f.write(encode(public_manifest(args.output)))
        print(json.dumps({'public_metadata': str(PUBLIC)}))
    else:
        print(json.dumps((build if args.command == 'build' else validate)(args.output), indent=2))
