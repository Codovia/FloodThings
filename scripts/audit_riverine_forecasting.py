#!/usr/bin/env python3
"""Reproducible Phase12F inventory and forecast gate; offline, read-only inputs.

No fits, API credentials, thresholds calculated, station point chosen, predictor
matrix synthesized, production route or alert. Public outputs exclude government
geometry, coordinates, threshold values and individual measurement rows.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from acquire_riverine_source_metadata import JOBS, RAW, validate as validate_sources
from riverine_forecast_contract import observation_blockers

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path('data/working/riverine_forecasting_phase12f_v1')
PUBLIC = Path('docs/phase12f')
HYDRO = 'data/working/karnataka_hydrology_2019_reconciled_v1'
SEMANTICS = 'data/working/karnataka_hydrology_semantics_v1'
GLOFAS = 'data/working/karnataka_glofas_2019_pilot_v1'
EXTERNAL = 'data/working/karnataka_external_hydrology_closure_v1'
INPUTS = (f'{HYDRO}/observation_quality.csv', f'{HYDRO}/discharge_reconciliation.csv',
          f'{HYDRO}/datum_compatibility.json', f'{SEMANTICS}/coordinate_provenance.json',
          f'{SEMANTICS}/stage4d_readiness.json', f'{GLOFAS}/station_mapping.json',
          f'{GLOFAS}/daily_modelled_discharge.csv', f'{GLOFAS}/manifest.json',
          f'{EXTERNAL}/summary.json', 'docs/phase12e/riverine_readiness.json',
          'docs/phase12f/source_access_review.json',
          'docs/phase12f/measured_series_inventory.json',
          'docs/phase12f/measured_station_year_coverage.json',
          'data/raw/reference/stage4a_v1/cwc_hddp2018.pdf')


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return {'sha256': h.hexdigest(), 'bytes': Path(path).stat().st_size}


def read_json(root, path):
    return json.loads((root/path).read_text())


def rows(root, path):
    with (root/path).open(newline='') as f:
        for index, row in enumerate(csv.DictReader(f)):
            if index >= 200000:
                raise ValueError('Bounded pilot row budget exceeded')
            yield row


def target_protocol():
    return {
        'status': 'PROPOSED_NOT_INDEPENDENTLY_APPROVED',
        'first_experiment': 'A_STAGE_PLUS_6H',
        'unit': 'One verified dated gauge cross-section; never whole district or inundation footprint',
        'station_priority': ['CW1KRU000339', 'CW1KRU000083'],
        'issue_times_utc': ['00:00', '06:00', '12:00', '18:00'],
        'lead_hours': 6, 'last_measured_input_maximum_age_hours': 1,
        'A_stage': 'Instantaneous measured water-level at issue+6h, metre, same verified station datum',
        'A_discharge_alternative': 'Measured discharge at a declared session/interval with compatible method and timing; existing daily sessions cannot validate +6h instantaneous discharge',
        'A_is_flood_prediction': False,
        'B': 'Stage strictly greater than effective official CWC danger level at issue+6h; warning-level exceedance is a separately named target',
        'B_interval_claim': 'Point-time only; any exceedance during (issue,issue+6h] requires separately approved sampling/detection and full interval coverage for absence',
        'B_is_inundation_map': False,
        'unknown': 'Missing/conflicted/unapproved/computed/rejected/datum-incompatible/time-ambiguous measurements; never filled by GloFAS',
        'B_negative': 'Accepted measured value <= applicable official level at the exact future instant only; missing times and daily averages cannot establish interval absence',
        'training_period': ['2013-06-01', '2017-06-01'],
        'validation_period': ['2017-06-01', '2018-06-01'],
        'test_period': ['2018-06-01', '2020-06-01'],
        'interval_convention': 'Half-open UTC; provisional water-year blocks, confirm seasonal completeness before approval',
        'split_rule': 'Chronological, no random rows; feature/outcome windows wholly within split; maximum24h antecedents and minimum24h embargo around boundaries; complete flood episodes assigned to one block, enlarging embargo to episode end; longer AI context requires separate larger embargo',
        'sample_adequacy': 'Independent reviewer must approve usable water years, effective event sample count, missingness, non-exceedance coverage and uncertainty; seven nominal common water years is not an automatic pass',
        'models': ['Persistence of last available measured stage',
                   'Training-only regularized linear regression of stage lags/change and reviewed rainfall',
                   'GloFAS only as compatible modelled-discharge reference, not a stage baseline without reviewed conversion',
                   'OpenHydroNet only after forcing/static/observed-discharge/schema/local skill gates'],
        'A_metrics': ['MAE/RMSE/bias in original units', 'skill relative to persistence', 'peak magnitude/timing and rising-limb errors', 'event-block confidence intervals'],
        'B_metrics': ['event detection/misses/false alarms and warning lead time', 'precision/recall and Brier/reliability for probabilities', 'separate point-time vs event-window scoring'],
        'historical_inputs': 'Actual release/availability <= issue; retrospective reforecasts explicitly labelled later-generated, version-pinned, tested separately from as-issued operational claims',
        'scientific_approval': None, 'training_authorized': False}


def predictor_matrix():
    return [
        {'feature': 'Measured stage lags/change', 'retained': '1642 source rows', 'issue_time_status': 'UNKNOWN', 'blocker': 'Gauge/datum stability, exact timezone, QC, record-release evidence'},
        {'feature': 'Measured discharge lags', 'retained': '55 source rows, 14 legacy quality-caveated rows', 'issue_time_status': 'UNKNOWN', 'blocker': 'Observed/computed/session statistic, timestamps, QC and release latency'},
        {'feature': 'Upstream observed rainfall, 1/6/24h antecedents', 'retained': 'No validated gauge-catchment issue-time joins', 'issue_time_status': 'UNKNOWN', 'blocker': 'Verified upstream basin polygons with rights, rain gauge/grid mapping, interval bounds, latency'},
        {'feature': 'Historically issued NWP/QPF', 'retained': 'No validated original issue-time forecast joins', 'issue_time_status': 'UNKNOWN', 'blocker': 'Archived initialization/issue/publication/valid intervals and upstream aggregation; IMD QPF returned401'},
        {'feature': 'GloFAS historical discharge', 'retained': '806 modelled rows', 'issue_time_status': 'NOT_DEMONSTRATED_AS_ISSUED', 'blocker': 'Historical simulation, not original forecast; v5 vs current v4 forecast overview, calibration/mapping/aggregation caveats'},
        {'feature': 'GloFAS reforecast', 'retained': 'No newly acquired native values', 'issue_time_status': 'LATER_GENERATED_REFERENCE_ONLY', 'blocker': 'EWDS authenticated access/terms, exact version/native schema; daily means not +6h stage'},
        {'feature': 'Reservoir operation/releases and upstream stage', 'retained': 'No validated issue-time joins', 'issue_time_status': 'UNKNOWN', 'blocker': 'Original issued operation records, station network travel times, publication latency'},
        {'feature': 'Catchment/static attributes', 'retained': 'CWC2025 catchment context and model static grids retained', 'issue_time_status': 'HISTORICAL_APPLICABILITY_UNRESOLVED', 'blocker': 'Canonical dated gauge and upstream delineation; 2025 publication not proof of2019 geometry'}]


def assemble(root=ROOT):
    root = Path(root)
    raw = root/RAW.relative_to(ROOT)
    source_summary = validate_sources(raw)
    access = read_json(root, 'docs/phase12f/source_access_review.json')
    if access['scientific_approval'] is not None or access['live_forecast_integrations'] != 0:
        raise ValueError('This source-audit version cannot assert independent approval/live forecasts')
    stations = {x['station_id']: x for x in read_json(root, f'{SEMANTICS}/coordinate_provenance.json')}
    datum = {x['station_id']: x for x in read_json(root, f'{HYDRO}/datum_compatibility.json')}
    mapping = {x['station_id']: x for x in read_json(root, f'{GLOFAS}/station_mapping.json')}
    stage = {x['station_id']: x for x in read_json(root, f'{SEMANTICS}/stage4d_readiness.json')}
    counts, days, times, blocked, keys = defaultdict(Counter), defaultdict(set), defaultdict(list), defaultdict(Counter), Counter()
    measured_total = 0
    for row in rows(root, f'{HYDRO}/observation_quality.csv'):
        key = row['canonical_cwc_station_id']
        if key not in stations:
            raise ValueError('Unexpected station; bounded shortlist changed')
        counts[key][row['variable']] += 1
        counts[key][row['analysis_eligibility']] += 1
        days[key].add(row['observation_time'][:10]); times[key].append(row['observation_time'])
        keys[(key, row['variable'], row['observation_time'], row['source_resource_id'])] += 1
        adapted = {'station_id': key, 'source_class': 'measured_cwc_nwdp',
                   'variable': row['variable'], 'value': row['value'],
                   'units': {'meter': 'm', 'm3/sec': 'm3/s'}.get(row['units'], row['units']),
                   'original_units': row['units'],
                   'observation_time': row['observation_time'], 'availability_time': row['availability_time'],
                   'datum': row['datum'], 'quality_status': row['source_quality_status'],
                   'statistic': 'UNRESOLVED_EXACT_EXPORT_SEMANTICS'}
        reasons = observation_blockers(adapted, {'station_id': key, 'datum': None, 'reviews': {}})
        if not reasons:
            raise ValueError('Frozen unresolved station observation unexpectedly passed scientific gate')
        blocked[key].update(reasons); measured_total += 1
    register = []
    for key in sorted(stations):
        legacy = counts[key]['eligible_with_quality_caveat']
        if legacy != stage[key]['currently_eligible_rows']:
            raise ValueError('Legacy source eligibility changed')
        threshold = datum[key]['stage4a_thresholds_original']
        register.append({'station_id': key, 'name': stations[key]['name'],
                         'river_identity_as_retained': stations[key]['river'],
                         'source_district_identity': threshold['source_district'],
                         'district_mapping_status': 'SOURCE_ALIAS_ONLY_CURRENT_PUBLIC_LGD_JOIN_NOT_APPROVED',
                         'priority': 'DEFER_REACH_RESOLUTION' if mapping[key]['selected_cell'] is None else 'REQUEST_STATION_HISTORY',
                         'source_rows': dict(sorted(counts[key].items())),
                         'source_date_count': len(days[key]), 'source_time_min': min(times[key]),
                         'source_time_max': max(times[key]), 'source_timezone': 'UNDOCUMENTED',
                         'verified_canonical_coordinates': False,
                         'coordinate_status': stations[key]['status'], 'model_cell_screen_status': mapping[key]['status'],
                         'official_stage_levels_documented': True, 'official_levels_compatible': datum[key]['thresholds_usable'],
                         'threshold_effectiveness': datum[key]['threshold_temporal_applicability'],
                         'official_station_status_2025_sop': threshold['status'],
                         'training_observations': 0, 'forecast_pairs': 0,
                         'record_blocker_counts': dict(sorted(blocked[key].items())),
                         'geometry_and_threshold_values_withheld': True})
    glofas_count = 0; cells, model_times = set(), set()
    for row in rows(root, f'{GLOFAS}/daily_modelled_discharge.csv'):
        if row['hydrology_source_type'] != 'modelled_glofas':
            raise ValueError('Modelled/measured provenance changed')
        cells.add((row['station_id'], row['cell_id'])); model_times.add(row['model_valid_time']); glofas_count += 1
    external = read_json(root, f'{EXTERNAL}/summary.json')
    if measured_total != external['preserved_measured_rows'] or sum(x['source_rows'].get('eligible_with_quality_caveat', 0) for x in register) != external['preserved_eligible_rows']:
        raise ValueError('Frozen source reconciliation differs')
    receipts = []
    for name, _ in JOBS:
        receipt = read_json(root, str(raw.relative_to(root)/(name+'.receipt.json')))
        receipts.append({'name': name, **receipt})
    for source in access['sources']:
        names = source['receipt_names']
        if any(n not in dict(JOBS) for n in names):
            raise ValueError('Access assessment has an unpinned source receipt')
    inventory = read_json(root, 'docs/phase12f/measured_series_inventory.json')
    report = {'phase': '12F', 'decision': 'CONDITIONAL', 'current_training_decision': 'NO-GO',
              'condition': 'Obtain authoritative historical station/time/datum/method dictionaries, QC/correction and release records for already retained Sadalga/Huvinhedgi series through documented CWC unclassified-data request; independent quality review required, not guaranteed',
              'full_archive_candidate_rows': inventory['candidate_rows'],
              'full_archive_rows_streamed': inventory['global_rows_streamed'],
              'full_archive_duplicate_extra_rows': sum(x['duplicate_timestamp_extra_rows'] for x in inventory['candidate_series']),
              'full_archive_conflicting_timestamp_groups': sum(x['conflicting_timestamp_groups'] for x in inventory['candidate_series']),
              'target_A_current': 'NO-GO', 'target_B_current': 'NO-GO',
              'measured_source_rows': measured_total, 'legacy_quality_caveated_discharge_rows': external['preserved_eligible_rows'],
              'retained_reconciliation_cases': external['preserved_comparison_cases'],
              'retained_disagreements': external['preserved_disagreements'],
              'duplicate_source_keys': sum(n-1 for n in keys.values() if n>1),
              'glofas_modelled_rows': glofas_count, 'glofas_station_cell_series': len(cells), 'glofas_timesteps': len(model_times),
              'scientifically_eligible_measured_targets': 0, 'complete_issue_time_feature_rows': 0,
              'eligible_future_pairs': 0, 'verified_threshold_exceedance_labels': 0, 'verified_threshold_nonexceedance_labels': 0,
              'models_fitted': 0, 'baseline_metrics_computed': 0, 'live_forecast_integrations': 0,
              'messages_sent': 0, 'canonical_points_or_reach_district_joins_created': 0,
              'source_metadata': source_summary, 'scientific_review_status': 'PENDING_INDEPENDENT_APPROVAL',
              'statewide_prediction_implemented': False,
              'geographic_coverage': {'shortlist': 3, 'request_priority': 2,
                 'source_district_aliases': sorted({x['source_district_identity'] for x in register}),
                 'verified_predictive_reaches': 0, 'verified_predictive_districts': 0,
                 'restriction': 'Documentary Belgaum/Raichur identities are not canonical LGD joins or uniform district forecasts'},
              'specific_blockers': ['Longer raw station-alias series exist but no quality-approved historical station export; only27-day pilot reconciled',
                 'Station coordinates/relocation/cross-section history unresolved',
                 'Exact observation timezone, timestamp role and sampling/session semantics unresolved',
                 'Gauge datum stability and official stage-threshold compatibility/effectiveness unverified',
                 'Observed/computed/revised/rejected QC lineage unresolved;33 disagreements retained',
                 'Original measurement/feature release latency and upstream-catchment associations missing',
                 'Independent target, rights, sample-adequacy and chronological test approval missing']}
    return {'report.json': report, 'station_shortlist.json': register,
            'target_protocol.json': target_protocol(), 'predictor_availability_matrix.json': predictor_matrix(),
            'source_receipts.json': receipts,
            'input_provenance.json': {p: fingerprint(root/p) for p in INPUTS}}


def build(root=ROOT, output=OUTPUT, public=PUBLIC):
    root = Path(root); output = root/output; public = root/public
    if output.exists():
        raise ValueError('Output version exists; validate instead')
    products = assemble(root)
    for name in products:
        if (public/name).exists():
            raise ValueError('Public metadata exists; cannot overwrite')
    output.mkdir(parents=True); public.mkdir(parents=True, exist_ok=True)
    for name, value in products.items():
        payload = encoded(value)
        (output/name).open('xb').write(payload); (public/name).open('xb').write(payload)
    manifest = {'input_fingerprints': products['input_provenance.json'],
                'code_fingerprints': {p: fingerprint(root/p) for p in
                    ['scripts/audit_riverine_forecasting.py', 'scripts/riverine_forecast_contract.py', 'scripts/acquire_riverine_source_metadata.py']},
                'products': {name: fingerprint(output/name) for name in products}}
    (output/'manifest.json').open('xb').write(encoded(manifest))
    return products['report.json']


def validate(root=ROOT, output=OUTPUT, public=PUBLIC):
    root = Path(root); output = root/output; public = root/public
    manifest = read_json(root, str(output.relative_to(root)/'manifest.json'))
    for path, expected in {**manifest['input_fingerprints'], **manifest['code_fingerprints']}.items():
        if fingerprint(root/path) != expected:
            raise ValueError('Input/code fingerprint changed: '+path)
    products = assemble(root)
    if set(products) != set(manifest['products']):
        raise ValueError('Product inventory changed')
    for name, value in products.items():
        if fingerprint(output/name) != manifest['products'][name] or (output/name).read_bytes() != encoded(value) or (public/name).read_bytes() != encoded(value):
            raise ValueError('Deterministic public/local reproduction failed: '+name)
    return {'status': 'VALIDATED', 'products': len(products), 'decision': products['report.json']['decision'],
            'current_training_decision': 'NO-GO', 'model_fits': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'])
    args = parser.parse_args()
    print(json.dumps((build if args.command == 'build' else validate)(), indent=2))
