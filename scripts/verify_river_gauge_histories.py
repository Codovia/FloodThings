#!/usr/bin/env python3
"""Phase12G: native-clock diagnostics, never certified targets or model fitting.

Build streams ONLY the two already-retained manual NWDP resources once, selecting
two exact station aliases. All original fields/values and conflicting rows stay
in ignored local JSONL. Validation replays that bounded subset and fingerprints
the original archives; --replay-raw additionally checks extraction completeness.
Public products are aggregate diagnostics, without coordinates or measurements.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
from pathlib import Path
import tempfile

from inventory_riverine_station_series import ALIASES, encoded, sha, value_class

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path('data/working/river_gauge_verification_phase12g_v1')
PUBLIC = Path('docs/phase12g')
REGISTRY = Path('data/working/karnataka_hydrology_2019_pilot_v1/raw_source_registry.json')
STATIONS = {'CW1KRU000083': 'Sadalga', 'CW1KRU000339': 'Huvinhedgi'}
FIELDS = {'rwl_manual_hr_cwc_007_1991_2020.csv':
          ('stage', 'River Water Level Manual Hourly (meter)', 'm'),
          'river_discharge_manual_daily_cwc_ka_2001_2025.csv':
          ('discharge', 'Manual Daily River Water Discharge (m3/sec)', 'm3/s')}
BLOCKERS = ['DATED_STATION_CROSSWALK_UNVERIFIED', 'OBSERVATION_TIMEZONE_AND_ROLE_UNKNOWN',
            'STAGE_DATUM_HISTORY_UNRESOLVED', 'MEASUREMENT_METHOD_AND_STATISTIC_UNVERIFIED',
            'RECORD_QC_AND_CORRECTIONS_ABSENT', 'ISSUE_TIME_INPUT_AVAILABILITY_UNKNOWN',
            'DETAILED_REUSE_RIGHTS_UNRESOLVED', 'INDEPENDENT_TARGET_AND_EVALUATION_APPROVAL_PENDING']
INPUTS = [REGISTRY, Path('docs/phase12f/measured_series_inventory.json'),
          Path('docs/phase12f/measured_station_year_coverage.json'),
          Path('docs/phase12f/target_protocol.json'),
          Path('data/working/karnataka_hydrology_2019_reconciled_v1/station_identity.json'),
          Path('data/working/karnataka_hydrology_2019_reconciled_v1/datum_compatibility.json'),
          Path('data/working/karnataka_hydrology_semantics_v1/measurement_semantics.json'),
          Path('data/working/karnataka_hydrology_semantics_v1/reuse_policy.json'),
          Path('data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf'),
          Path('data/raw/reference/stage4a_v1/cwc_hddp2018.pdf')]
MAX_SELECTED_ROWS = 100000
MAX_SERIES_TIMES = 50000


def native_time(literal):
    """Keep date-only precision; never assign midnight/IST/UTC to unknown clocks."""
    for fmt, precision in (('%d-%m-%Y %H:%M', 'MINUTE'), ('%d-%m-%Y', 'DATE_ONLY')):
        try:
            parsed = dt.datetime.strptime(literal, fmt)
            return (parsed.isoformat() if precision == 'MINUTE' else parsed.date().isoformat(), precision)
        except ValueError:
            pass
    return None, 'INVALID'


def source_files(root):
    sources = [s for s in json.loads((root/REGISTRY).read_text()) if s['original_filename'] in FIELDS]
    if {s['original_filename'] for s in sources} != set(FIELDS):
        raise ValueError('Both reviewed resources required')
    for s in sources:
        p = root/'data/raw/reference/stage4b_v1'/s['original_filename']
        if p.stat().st_size != s['download']['bytes'] or sha(p) != s['download']['sha256']:
            raise ValueError('Original source fingerprint mismatch')
    return sources


def extract(root, destination, sources):
    """Original source-row ordinals and complete string fields; no preferred value."""
    selected = 0
    with destination.open('xb') as out:
        for s in sources:
            name = s['original_filename']; variable, field, _ = FIELDS[name]
            with (root/'data/raw/reference/stage4b_v1'/name).open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != s['schema_and_census']['original_columns']:
                    raise ValueError('Unreviewed source schema')
                for ordinal, row in enumerate(reader, 1):
                    if ordinal > 5000000:
                        raise ValueError('Archive row budget exceeded')
                    station = ALIASES.get(row['Station'].strip().casefold())
                    if station not in STATIONS:
                        continue
                    selected += 1
                    if selected > MAX_SELECTED_ROWS:
                        raise ValueError('Selected row memory/review budget exceeded')
                    record = {'station_id_candidate': station, 'variable': variable,
                              'source_resource_id': s['resource_id'], 'source_row_ordinal': ordinal,
                              'source_sha256': s['download']['sha256'], 'value_field': field, 'original': row}
                    out.write((json.dumps(record, sort_keys=True, ensure_ascii=True)+'\n').encode())
    return selected


def load_subset(path):
    """Bounded candidate-only memory; original fields remain on disk."""
    series = {}; count = 0; seen_refs = set()
    with path.open() as f:
        for line in f:
            count += 1
            if count > MAX_SELECTED_ROWS or len(line) > 32768:
                raise ValueError('Subset budget exceeded')
            r = json.loads(line); station = r['station_id_candidate']; variable = r['variable']
            if station not in STATIONS or variable not in {'stage', 'discharge'}:
                raise ValueError('Unreviewed subset identity')
            ref = (r['source_resource_id'], r['source_row_ordinal'])
            if ref in seen_refs:
                raise ValueError('Source-row reference repeated')
            seen_refs.add(ref)
            literal = r['original']['Data Acquisition Time']; time, precision = native_time(literal)
            classification, value = value_class(r['original'][r['value_field']], variable)
            key = station, variable
            if key not in series:
                series[key] = {'groups': {}, 'formats': Counter(), 'invalid_rows': 0,
                               'rows': 0, 'source_resource_id': r['source_resource_id']}
            s = series[key]; s['rows'] += 1; s['formats'][precision] += 1
            if time is None:
                s['invalid_rows'] += 1
                continue
            group = s['groups'].setdefault(time, {'refs': [], 'values': set(), 'invalid': False, 'precision': precision})
            group['refs'].append(r['source_row_ordinal']); group['values'].add(value)
            group['invalid'] |= classification != 'FINITE_SOURCE_VALUE_NOT_QC_APPROVED'
            if len(s['groups']) > MAX_SERIES_TIMES:
                raise ValueError('Candidate series budget exceeded')
    return series


def group_flags(g):
    return {'rows': len(g['refs']), 'conflict': len(g['values']) > 1, 'invalid': g['invalid']}


def interval_summary(times):
    ordered = sorted(dt.datetime.fromisoformat(t) for t in times)
    gaps = Counter(int((b-a).total_seconds()/60) for a, b in zip(ordered, ordered[1:]))
    return {'intervals': len(ordered)-1 if ordered else 0,
            'interval_minutes_histogram': {str(k): v for k, v in sorted(gaps.items())},
            'intervals_over_24h': sum(v for k,v in gaps.items() if k > 1440),
            'intervals_over_7days': sum(v for k,v in gaps.items() if k > 10080),
            'intervals_outside_general_policy_1h_5h_14h': sum(v for k,v in gaps.items() if k not in {60,300,840}),
            'max_interval_minutes': max(gaps, default=None),
            'expected_missing_readings': 'UNKNOWN_WITHOUT_SITE_YEAR_SCHEDULE'}


def coverage(station, variable, s, year=None):
    groups = {t:g for t,g in s['groups'].items() if year is None or int(t[:4]) == year}
    dates = {t[:10] for t in groups}; times = [t for t,g in groups.items() if g['precision']=='MINUTE']
    bounds = [min(groups), max(groups)] if groups else [None, None]
    if year:
        days = (dt.date(year+1,1,1)-dt.date(year,1,1)).days
    elif dates:
        days = (dt.date.fromisoformat(max(dates))-dt.date.fromisoformat(min(dates))).days+1
    else:
        days = 0
    result = {'station_id_candidate': station, 'station_name': STATIONS[station], 'variable': variable,
              'source_resource_id': s['source_resource_id'], 'year': year,
              'rows': sum(len(g['refs']) for g in groups.values()), 'unique_native_times': len(groups),
              'unique_minute_precision_times': len(times), 'date_only_time_groups': len(groups)-len(times),
              'duplicate_timestamp_extra_rows': sum(len(g['refs'])-1 for g in groups.values()),
              'duplicate_timestamp_groups': sum(len(g['refs'])>1 for g in groups.values()),
              'conflicting_timestamp_groups': sum(len(g['values'])>1 for g in groups.values()),
              'invalid_value_groups': sum(g['invalid'] for g in groups.values()),
              'native_bounds': bounds, 'distinct_observed_dates': len(dates),
              'calendar_dates_without_any_record': days-len(dates),
              'missing_date_denominator': 'FULL_CALENDAR_YEAR' if year else 'BETWEEN_SOURCE_BOUNDS',
              'clock_minute_histogram': dict(sorted(Counter(t[11:16] for t in times).items())),
              'units_in_source_header': 'm' if variable=='stage' else 'm3/s',
              'source_reported_cadence': 'MANUAL_HOURLY' if variable=='stage' else 'MANUAL_DAILY',
              'record_clock': 'NAIVE_UNVERIFIED_NOT_UTC', 'record_QC': 'NOT_SUPPLIED',
              'eligible_forecast_pairs': 0, 'frequency_diagnostics': interval_summary(times)}
    day_clocks=defaultdict(set)
    for t in times:
        day_clocks[t[:10]].add(t[11:16])
    full_hours={f'{h:02}:00' for h in range(24)}
    result['observed_day_patterns']={
        'exact_24_integer_hour_times':sum(clocks==full_hours for clocks in day_clocks.values()),
        'exact_08_13_18_only':sum(clocks=={'08:00','13:00','18:00'} for clocks in day_clocks.values()),
        'other_observed_patterns':sum(clocks!=full_hours and clocks!={'08:00','13:00','18:00'} for clocks in day_clocks.values()),
        'interpretation':'OBSERVED_STRUCTURE_ONLY_NOT_PRODUCER_CONFIRMED_SCHEDULE_OR_QC'}
    if year is None:
        result.update({'native_precision_counts': dict(s['formats']), 'unparseable_rows': s['invalid_rows']})
    # Adjacent intervals by later-reading year; include cross-year gap explicitly.
    all_times = sorted(times if year is None else [t for t,g in s['groups'].items() if g['precision']=='MINUTE'])
    adjacent = Counter()
    for a,b in zip(all_times,all_times[1:]):
        if year is None or int(b[:4])==year:
            adjacent[int((dt.datetime.fromisoformat(b)-dt.datetime.fromisoformat(a)).total_seconds()/60)] += 1
    result['adjacent_interval_minutes_by_later_year'] = {str(k):v for k,v in sorted(adjacent.items())}
    return result


def issue_times(groups, mode):
    times = sorted(dt.datetime.fromisoformat(t) for t,g in groups.items() if g['precision']=='MINUTE')
    if mode == 'READING_TIME':
        return times
    if mode != 'NATIVE_6H_GRID':
        raise ValueError('Unreviewed issue mode')
    if not times:
        return []
    t = times[0].replace(hour=0, minute=0, second=0)
    result = []
    while t <= times[-1]:
        if t >= times[0]:
            result.append(t)
        t += dt.timedelta(hours=6)
    return result


def pair_records(station, s, mode, horizon_hours):
    """Exact future matches, ≤1h current input; no interpolation or conflict choice.

    Diagnostic lags are exact issue-1h/-6h/-24h. These are separate from the
    minimum persistence input; they are not a newly approved baseline feature set.
    Naive arithmetic measures source-clock structure, never an actual UTC issue.
    """
    groups = {t:g for t,g in s['groups'].items() if g['precision']=='MINUTE'}
    times = sorted(dt.datetime.fromisoformat(t) for t in groups)
    for issue in issue_times(groups, mode):
        target = issue+dt.timedelta(hours=horizon_hours)
        idx = bisect_right(times, issue)-1
        latest = times[idx] if idx >= 0 else None
        current = latest if latest is not None and issue-latest <= dt.timedelta(hours=1) else None
        ig = groups.get(current.isoformat()) if current else None
        tg = groups.get(target.isoformat())
        lag_groups = {str(h): groups.get((issue-dt.timedelta(hours=h)).isoformat()) for h in (1,6,24)}
        present = [g for g in [ig,tg] if g is not None]
        structural = ig is not None and tg is not None
        flags = {'with_input_within_one_hour': ig is not None,
                 'matching_future_measurements': tg is not None,
                 'structural_pairs_current_and_exact_target': structural,
                 'missing_future_measurements': tg is None,
                 'pairs_with_duplicate_input_or_target': structural and any(len(g['refs'])>1 for g in present),
                 'pairs_with_conflicting_input_or_target': structural and any(len(g['values'])>1 for g in present),
                 'pairs_with_invalid_input_or_target': structural and any(g['invalid'] for g in present),
                 'pairs_singleton_finite_input_and_target': structural and all(len(g['refs'])==1 and not g['invalid'] for g in present),
                 'pairs_without_numeric_conflict_input_target': structural and all(len(g['values'])==1 and not g['invalid'] for g in present),
                 'pairs_with_exact_antecedents_1_6_24h': structural and all(g is not None for g in lag_groups.values()),
                 'pairs_with_missing_required_antecedents': structural and any(g is None for g in lag_groups.values()),
                 'pairs_with_conflicting_required_antecedents': structural and any(g is not None and len(g['values'])>1 for g in lag_groups.values()),
                 'pairs_with_unique_finite_input_target_and_all_antecedents': structural and
                    all(g is not None and len(g['refs'])==1 and not g['invalid'] for g in [ig,tg,*lag_groups.values()])}
        yield {'station_id_candidate': station, 'source_resource_id': s['source_resource_id'],
               'issue_mode': mode, 'horizon_hours': horizon_hours,
               'issue_native': issue.isoformat(), 'candidate_target_native': target.isoformat(),
               'latest_prior_native': latest.isoformat() if latest else None,
               'input_native': current.isoformat() if current else None,
               'input_source_rows_all_variants': ig['refs'] if ig else [],
               'target_source_rows_all_variants': tg['refs'] if tg else [],
               'lag_source_rows_all_variants': {h:g['refs'] if g else [] for h,g in lag_groups.items()},
               'flags': flags, 'scientific_eligibility': 'UNKNOWN',
               'blocking_evidence': BLOCKERS, 'issue_clock': 'UNVERIFIED_NATIVE_WALL_CLOCK',
               'input_historical_availability': 'UNKNOWN', 'missing_target_outcome': 'UNKNOWN_NOT_NONFLOOD'}


def pair_summary(records, sink=None):
    years = defaultdict(Counter)
    for r in records:
        c = years[int(r['issue_native'][:4])]; c['candidate_issue_times_total'] += 1
        for k,v in r['flags'].items():
            c[k] += int(v)
        if sink:
            sink.write((json.dumps(r, sort_keys=True)+'\n').encode())
    return {str(year): {**dict(sorted(c.items())), 'scientifically_eligible_pairs': 0,
                       'all_issue_times_temporally_unverified': c['candidate_issue_times_total'],
                       'all_issue_times_QC_unverified': c['candidate_issue_times_total'],
                       'all_issue_times_historical_availability_unknown': c['candidate_issue_times_total']}
            for year,c in sorted(years.items())}


def summarize(series, pair_path):
    coverage_records = []; year_records = []; pair_years = []; cadence = []
    with pair_path.open('xb') as sink:
        for (station, variable),s in sorted(series.items()):
            aggregate = coverage(station, variable, s); coverage_records.append(aggregate)
            years = range(int(aggregate['native_bounds'][0][:4]), int(aggregate['native_bounds'][1][:4])+1)
            for year in years:
                year_records.append(coverage(station, variable, s, year))
            if variable != 'stage':
                continue
            for mode in ('NATIVE_6H_GRID', 'READING_TIME'):
                for horizon in (6,24):
                    summary = pair_summary(pair_records(station,s,mode,horizon),sink)
                    for year,counts in summary.items():
                        pair_years.append({'station_id_candidate': station, 'year': int(year),
                                           'issue_mode': mode, 'horizon_hours': horizon, 'counts': counts})
            # Fixed leads suggested by the GENERAL policy, not a station schedule.
            for horizon in (1,5,14):
                result = pair_summary(pair_records(station,s,'READING_TIME',horizon))
                scheduled=pair_summary(r for r in pair_records(station,s,'READING_TIME',horizon)
                    if horizon==1 or r['issue_native'][11:16] in ({'08:00','13:00'} if horizon==5 else {'18:00'}))
                cadence.append({'station_id_candidate': station, 'fixed_lead_hours': horizon,
                                'meaning': {1:'Fixed1h, proposed hourly regime',5:'Fixed5h, e.g.08→13 or13→18',14:'Fixed14h, e.g.18→next08'}[horizon],
                                'schedule_status':'GENERAL_POLICY_ONLY_SITE_YEAR_APPLICATION_UNKNOWN',
                                'all_reading_clock_counts': totals(result.values()),
                                'policy_example_clock_counts':totals(scheduled.values())})
    return coverage_records, year_records, pair_years, cadence


def totals(records):
    c = Counter()
    for r in records:
        c.update(r)
    return dict(sorted(c.items()))


def products(root, subset, pair_path):
    series = load_subset(subset)
    cover, years, pairs, cadence = summarize(series,pair_path)
    prior = json.loads((root/'docs/phase12f/measured_series_inventory.json').read_text())
    for r in cover:
        old = next(x for x in prior['candidate_series'] if x['station_id_candidate']==r['station_id_candidate']
                   and x['source_resource_id']==r['source_resource_id'])
        if (r['rows'], r['duplicate_timestamp_extra_rows'], r['conflicting_timestamp_groups']) != (
            old['counts']['rows'],old['duplicate_timestamp_extra_rows'],old['conflicting_timestamp_groups']):
            raise ValueError('Selected histories disagree with preserved Phase12F inventory')
    datum = json.loads((root/INPUTS[5]).read_text())
    thresholds=[]
    for station in STATIONS:
        d=next(x for x in datum if x['station_id']==station)
        original=d['stage4a_thresholds_original']
        thresholds.append({'station_id_candidate':station, 'official_document_has_warning_and_danger':True,
            'source_url':'https://cwc.gov.in/sites/default/files/sopapril2025.pdf',
            'source_pdf_page':original['source_page'], 'source_ordinal':original['source_ordinal'],
            'source_table_reference':original['source_table_reference'], 'source_station_code_in_threshold_row':False,
            'variable':'stage','units':original['units'], 'gauge_datum_compatibility':d['threshold_compatibility'],
            'historical_effective_dates':'UNKNOWN', 'official_status':original['status'],
            'usable_flood_thresholds':0, 'threshold_values_published_here':False,
            'warning_danger_comparisons_computed':0})
    pair_totals=[]
    for station in STATIONS:
        for mode in ('NATIVE_6H_GRID','READING_TIME'):
            for horizon in (6,24):
                entries=[r['counts'] for r in pairs if r['station_id_candidate']==station and
                         r['issue_mode']==mode and r['horizon_hours']==horizon]
                pair_totals.append({'station_id_candidate':station,'issue_mode':mode,
                                    'horizon_hours':horizon,'counts':totals(entries)})
    sources=source_files(root)
    provenance={str(p):{'sha256':sha(root/p),'bytes':(root/p).stat().st_size} for p in INPUTS}
    source_register=[{'filename':s['original_filename'],'resource_id':s['resource_id'],'dataset_id':s['dataset_id'],
        'source_url':s['download']['source_url'],'sha256':s['download']['sha256'],'bytes':s['download']['bytes'],
        'original_fields':s['schema_and_census']['original_columns'], 'quality_columns':s['schema_and_census']['quality_columns'],
        'access':'RETAINED_ONLY_NO_DOWNLOAD', 'rights':'OTHER_OPEN_NOT_STANDARD_LICENCE_DETAILED_LOCAL_ONLY'} for s in sources]
    report={'phase':'12G','decision':'CONDITIONAL','current_training':'NO-GO',
        'scope':'Sadalga and Huvinhedgi native manual stage/discharge histories only',
        'candidate_rows':sum(r['rows'] for r in cover),'candidate_stage_rows':sum(r['rows'] for r in cover if r['variable']=='stage'),
        'pair_totals':pair_totals,'scientifically_eligible_forecast_pairs':0,
        'officially_compatible_flood_thresholds':0,'flood_positive_labels':0,'flood_negative_labels':0,
        'verified_predictive_geographic_units':0,'fits':0,'messages_sent':0,
        'blockers':BLOCKERS,'source_date_interpretation':'NATIVE_UNKNOWN_TIMEZONE_NO_UTC_CONVERSION',
        'pair_rules':{'target_match':'EXACT_NATIVE_ISSUE_PLUS_FIXED_LEAD_NO_INTERPOLATION',
            'current_input':'LATEST_PRIOR_MINUTE_PRECISION_READING_AGE_AT_MOST_1H_NO_CONFLICT_FALLBACK',
            'additional_diagnostic_lags_hours':[1,6,24], 'grid':'00/06/12/18 NATIVE WALL CLOCK; NOT proposed UTC grid',
            'reading_time':'AT_EACH_UNIQUE_MINUTE_PRECISION_READING; availability not established',
            'year_assignment':'ISSUE_YEAR; targets/antecedents may cross year; no split approval',
            'duplicate_count':'Extra rows within resource/station/native timestamp',
            'conflict_count':'Timestamp groups with >1 distinct Decimal-normalized value; all originals retained'},
        'cadence_warning':'Adjacent next-reading gaps are retrospective, not an as-issued schedule or variable-lead forecasting target',
        'minimum_experiment':'Official dictionary/dated identity/datum + QC correction table + release latency evidence + rights + independent target/evaluation approval; persistence then simple statistical baseline',
        'memory_bound':'CSV streaming once; subset<=100000 rows; each series<=50000 timestamps; pair JSONL streamed; no global CSV in RAM',
        'publication':'Aggregates only; exact native row/pair references and original fields stay ignored locally'}
    return {'report.json':report,'station_readiness.json':cover,'station_year_coverage.json':years,
            'forecast_pair_year_feasibility.json':pairs,'reported_cadence_feasibility.json':cadence,
            'threshold_evidence.json':thresholds,'source_register.json':source_register,'input_provenance.json':provenance}


def build(root=ROOT):
    root=Path(root); output=root/OUTPUT; public=root/PUBLIC
    if output.exists() or public.exists():
        raise ValueError('Version exists; validate instead')
    sources=source_files(root); output.mkdir(parents=True)
    subset=output/'native_observations.jsonl'; extract(root,subset,sources)
    pairs=output/'native_forecast_candidates.jsonl'
    result=products(root,subset,pairs); public.mkdir(parents=True)
    for name,value in result.items():
        (output/name).open('xb').write(encoded(value)); (public/name).open('xb').write(encoded(value))
    manifest={'code_sha256':sha(Path(__file__)), 'helper_sha256':sha(Path(__file__).with_name('inventory_riverine_station_series.py')),
              'private_files':{p.name:sha(p) for p in (subset,pairs)},
              'products':{n:sha(output/n) for n in result}}
    (output/'manifest.json').open('xb').write(encoded(manifest))
    return {'status':'BUILT', 'candidate_rows':result['report.json']['candidate_rows'], 'eligible_pairs':0}


def validate(root=ROOT, replay_raw=False):
    root=Path(root); output=root/OUTPUT; manifest=json.loads((output/'manifest.json').read_text())
    if sha(Path(__file__)) != manifest['code_sha256'] or sha(Path(__file__).with_name('inventory_riverine_station_series.py')) != manifest['helper_sha256']:
        raise ValueError('Pinned audit code changed')
    for name,digest in manifest['private_files'].items():
        if sha(output/name)!=digest:
            raise ValueError('Private original-row/pair receipt mismatch')
    source_files(root)  # Whole-source fingerprints, not repeat full archive inventory.
    with tempfile.TemporaryDirectory(prefix='phase12g_replay_',dir=root/'data/recovery') as temp:
        temp=Path(temp)
        if replay_raw:
            extract(root,temp/'native.jsonl',source_files(root))
            if sha(temp/'native.jsonl')!=sha(output/'native_observations.jsonl'):
                raise ValueError('Native row extraction mismatch')
        result=products(root,output/'native_observations.jsonl',temp/'pairs.jsonl')
        if sha(temp/'pairs.jsonl')!=manifest['private_files']['native_forecast_candidates.jsonl']:
            raise ValueError('Exact native forecast register replay mismatch')
        for name,value in result.items():
            if sha(output/name)!=manifest['products'][name] or (output/name).read_bytes()!=encoded(value) or (root/PUBLIC/name).read_bytes()!=encoded(value):
                raise ValueError('Aggregate replay/source provenance mismatch')
    return {'status':'VALIDATED','products':len(result),'private_registers':2,
            'original_sources_fingerprinted':2,'raw_extraction_replayed':replay_raw,'eligible_pairs':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','validate']);parser.add_argument('--replay-raw',action='store_true')
    args=parser.parse_args()
    if args.command=='build' and args.replay_raw:
        parser.error('--replay-raw applies only to validate')
    print(json.dumps(build() if args.command=='build' else validate(replay_raw=args.replay_raw),indent=2))
