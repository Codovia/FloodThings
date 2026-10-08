"""Offline Stage 5A target and issuance archive review; never builds labels or features.

Original public responses stay local. Build is create-only; validation is read-only
and reproduces every output from hashed source evidence and reviewed decisions.
"""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage5a_v1'
OUTPUT = ROOT / 'data/working/karnataka_target_archive_review_v1'
PUBLIC = ROOT / 'data/reference/karnataka_target_archive_review_v1/manifest.json'
ARCHIVE_STATUSES = {'ISSUANCE_ARCHIVE_VALID', 'ISSUANCE_ARCHIVE_WITH_CAVEATS',
                    'NOT_ISSUANCE_PRESERVING', 'UNRESOLVED'}
TARGET_STATUSES = {'SUPPORTED', 'PARTIALLY_SUPPORTED', 'NOT_SUPPORTED'}
FORBIDDEN_INPUTS = {'event_window_rainfall', 'post_event_flood_extent', 'ifi_event_report',
                    'gokak_canonical_discharge', 'future_observation', 'future_peak',
                    'water_level_threshold', 'missing_as_negative'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def source_register():
    rows = []
    for finding in read(RAW / 'review_findings.json'):
        path = RAW / (finding['id'] + '.html')
        receipt = read(Path(str(path) + '.json'))
        require(all(finding.get(k) for k in ('title', 'publisher', 'version', 'section', 'finding', 'confidence')),
                'Incomplete reviewed source')
        require(urlparse(receipt['url']).scheme == 'https', 'Official source URL required')
        if receipt['status'] == 'retrieved':
            require(receipt['http_status'] == '200' and receipt['sha256'] == sha(path)
                    and receipt['bytes'] == path.stat().st_size, 'Source bytes changed')
        else:
            require(receipt['bytes'] == 0 and receipt['sha256'] in {None, hashlib.sha256(b'').hexdigest()}, 'Failed source is not verified content')
        rows.append({**finding, **receipt, 'original_file': str(path.relative_to(ROOT)) if path.exists() else None})
    require(len(rows) == 22 and len({r['id'] for r in rows}) == 22, 'Reviewed source scope changed')
    for name, title, publisher, version, section, url, retrieved, finding in [
        ('data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf', 'SOP for Flood Forecasting', 'CWC',
         'April 2025', 'Annex 3.2; PDF page 82', 'https://cwc.gov.in/sites/default/files/sopapril2025.pdf',
         '2026-10-06T18:26:19+00:00', 'Station warning/danger/HFL classes are not generic district probability cutoffs.'),
        ('data/raw/reference/stage3e2_v1/action2021.pdf', 'Action Plan for Flood Risk Management 2021', 'KSDMA',
         '2021', 'Tables 5/6; PDF pages 75/78; printed pages 45/48',
         'https://ksdma.karnataka.gov.in/storage/pdf-files/ActionplanforFloodriskmanagement2021.pdf',
         '2026-10-06T13:25:46+00:00', 'Village hazard categories are not issued seven-day Low/Medium/High forecasts.')]:
        rows.append({'id': name, **record(ROOT / name), 'title': title, 'publisher': publisher,
                     'version': version, 'section': section, 'url': url, 'retrieved_at': retrieved,
                     'finding': finding, 'confidence': 'high for inspected table; no generic risk mapping',
                     'status': 'retained_pdf_rendered_and_inspected'})
    return rows


def requirements_from_text(text, source, role):
    """Retain exact matching paragraphs/tables/code blocks with source line numbers.

    This is an inventory, not acceptance of claims in obsolete implementation notes.
    No exact clock, geographic unit or class threshold is inferred by this parser.
    """
    rows, section, block, first = [], 'Preamble', [], 1
    keywords = re.compile(r'flood|risk|low|medium|high|district|localit|forecast|seven|7.day|6.hour|six.hour|alert|warn|sever|impact|probabil|hotspot', re.I)
    lines = text.splitlines(keepends=True)
    def finish(last):
        if block and keywords.search(''.join(block)):
            original = ''.join(block)
            rows.append({'source_document': source, 'source_role': role, 'section': section,
                         'line_start': first, 'line_end': last, 'original_requirement': original,
                         'geographic_unit': 'district/locality mentioned; aggregation unspecified' if re.search(r'district|localit', original, re.I) else None,
                         'temporal_unit': 'six-hour refresh mentioned; interval not defined' if re.search(r'6.hour|six.hour', original, re.I) else None,
                         'prediction_horizon': 'seven forecast days mentioned; boundaries unspecified' if re.search(r'7.day|seven.day', original, re.I) else None,
                         'output_type': 'source statement; interpretation in separate target review',
                         'risk_class_definition': None, 'ambiguity': 'Not automatically a measurable target',
                         'notes': 'Historical implementation claims and proxy thresholds are not accepted scientific evidence.'})
    for index, line in enumerate(lines, 1):
        if line.lstrip().startswith('#'):
            finish(index - 1)
            block = []; section = line.strip().lstrip('#').strip(); first = index
        if not line.strip():
            finish(index - 1); block = []; first = index + 1
        else:
            if not block: first = index
            block.append(line)
    finish(len(lines))
    return rows


def requirements():
    rows = []
    for name, role in [('QandA.md', 'original product intent plus obsolete implementation claims'),
                       ('README.md', 'current verified implementation scope'),
                       ('docs/PREDICTION_FEATURE_METHOD.md', 'current scientific guardrails')]:
        rows.extend(requirements_from_text((ROOT / name).read_text(), name, role))
    return rows


def issuance_definition():
    return {'schedule_status': 'exact_issuance_schedule_unspecified', 'refresh_requirement': 'every six hours',
            'clock_times': None, 'forecast_days': 7, 'forecast_day_boundaries': None,
            'day_boundary_candidates_not_adopted': ['T to T+24h rolling windows', 'next IST calendar day', 'provider forecast day'],
            'required_record_fields': ['prediction_issue_time', 'model_initialization_time', 'documented_available_at',
                                       'retrieved_at', 'valid_interval_start', 'valid_interval_end', 'model_version',
                                       'member_id', 'source_product', 'spatial_unit_version', 'units'],
            'time_basis': 'timezone-aware instants stored as UTC; local display and calendar intervals separate',
            'rule': 'Initialization, publication/availability, retrieval and valid time are distinct.',
            'production_schedule_adopted': False, 'provider_cycles_are_not_application_schedule': True}


def risk_mapping():
    return {'status': 'user_facing_risk_class_mapping_not_defined', 'probability_cutoffs': None,
            'severity_cutoffs': None, 'alert_mapping': None,
            'source_definitions': ['CWC station water level between warning/danger/HFL: above normal, severe, extreme',
                                   'KSDMA 2021 village hazard listings: moderate risk area / very high risk area'],
            'non_equivalence': 'Neither defines district/locality issued Low/Medium/High flood probability, impact or severity.',
            'obsolete_project_thresholds': 'Unvalidated proxy scores in QandA are inventoried, not adopted.'}


def targets():
    rows = []
    for tid, name, geo, temporal, status, reason in [
        ('qualified_cell_window', 'Observation-qualified mapped non-permanent water', 'original GFD raster cell within reviewed scope',
         'at least once in original event window', 'SUPPORTED', 'Measurement target only; four scopes, event maximum, no daily onset or verified absence.'),
        ('scope_event_occurrence', 'Flood occurrence in reviewed geographic event scope', 'reviewed scope, not whole district state',
         'recorded event window', 'PARTIALLY_SUPPORTED', 'Four mapped-positive scopes; documentary windows do not time water onset.'),
        ('spatial_noninundation', 'Observed non-inundation', 'specified cell/area', 'explicit acquisition interval',
         'PARTIALLY_SUPPORTED', 'Observed-zero map evidence exists, but sensitivity and temporal absence are not validated.'),
        ('district_day', 'District-day flood occurrence', 'district with explicit aggregation rule', 'one defined day',
         'NOT_SUPPORTED', 'No complete district-day observations or negatives; event maximum is not daily occurrence.'),
        ('locality_day', 'Locality-day flood occurrence', 'verified locality polygon', 'one defined day',
         'NOT_SUPPORTED', 'Locality footprint and timed inundation labels not established.'),
        ('six_hour', 'Six-hour flood occurrence', 'explicit area not yet selected', 'six-hour observation interval',
         'NOT_SUPPORTED', 'No six-hour outcome observations; six-hour refresh is a product requirement.'),
        ('forecast_window_binary', 'Occurrence within forecast window', 'district/locality unresolved', 'issued interval boundaries unresolved',
         'NOT_SUPPORTED', 'No prediction horizon adopted, temporally precise positives or monitored negatives.'),
        ('severity', 'Multi-class flood severity or impact', 'exposure/hazard spatial unit unresolved', 'event or forecast period unresolved',
         'NOT_SUPPORTED', 'Mapped cell count is not flood depth, damage or severity.'),
        ('risk_classes', 'Low/Medium/High user-facing risk', 'district/locality unresolved', 'seven days, boundaries unresolved',
         'NOT_SUPPORTED', 'No independent class definitions, probability mapping or measurable target.')]:
        rows.append({'target_id': tid, 'target_name': name, 'target_type': 'observation' if tid == 'qualified_cell_window' else 'candidate',
                     'geographic_unit': geo, 'temporal_unit': temporal, 'forecast_horizon': None,
                     'observation_source': 'GFD / IFI / reviewed official products, with separate evidence roles',
                     'positive_definition': 'Mapped non-permanent floodwater with all source masks valid and clear_views > 0; only event/spatial evidence',
                     'negative_definition': None, 'unknown_definition': 'Unavailable, insufficient, unreviewed or not temporally observed',
                     'severity_definition': None, 'prediction_time': None,
                     'label_availability': 'Retrospective; water timing and source detection limitations preserved',
                     'sample_support': {'positive_scopes': 4, 'verified_negative_examples': 0},
                     'leakage_status': 'label_or_evidence_only; never a predictor', 'training_feasibility': 'not approved',
                     'deployment_interpretation': 'No deployable flood prediction target adopted', 'status': status, 'reason': reason,
                     'primary_adopted': False})
    return rows


def validate_target(row):
    require(row['status'] in TARGET_STATUSES and row['geographic_unit'] and row['temporal_unit'], 'Target geography/time required')
    if row['primary_adopted']:
        require(row['status'] == 'SUPPORTED' and row['prediction_time'] and row['forecast_horizon']
                and row['negative_definition'] and row.get('adoption_evidence_url', '').startswith('https://'),
                'Primary target needs independent operational definitions and label support')
    return deepcopy(row)


def negative_review(evidence):
    """Evaluate proposed protocol prerequisites only; this stage never issues negatives."""
    invalid = {'no_ifi_record', 'no_gfd_record', 'random_day', 'unmentioned_district', 'missing_scene', 'observed_zero_event'}
    require(evidence.get('type') not in invalid, 'Absence, missing or event-maximum zero cannot establish a negative')
    required = ['precise_spatial_unit', 'explicit_observation_interval', 'valid_sensor_masks', 'detection_sensitivity_audited',
                'adequate_temporal_coverage', 'independent_reference', 'selection_protocol', 'prediction_time_parity']
    return {'protocol_prerequisites_met': all(evidence.get(k) is True for k in required),
            'binary_label': None, 'negative_created': False, 'requires_separate_authorized_validation': True}


def asof_forecast(product_kind, value, issuance, feature='forecast_precipitation'):
    require(feature not in FORBIDDEN_INPUTS, 'Leakage or unsupported input')
    require(product_kind == 'archived_operational_forecast', 'Hindcast/reanalysis/consolidated is not as-issued')
    def instant(key):
        date = datetime.fromisoformat(value[key]); require(date.tzinfo is not None, 'Explicit timezone required'); return date
    require(issuance.tzinfo is not None, 'Issuance timezone required')
    require(value.get('availability_documented') is True
            and value.get('availability_source_url', '').startswith('https://')
            and re.fullmatch('[a-f0-9]{64}', value.get('availability_source_sha256', '')), 'Documented delivery evidence required')
    require(instant('initialized_at') <= instant('available_at') <= issuance, 'Forecast not available at issuance')
    require(instant('valid_start') < instant('valid_end'), 'Valid interval required')
    return True


def forecast_sources():
    # Values are reviewed catalogue semantics, not retrieved historical run availability.
    rows = []
    def add(sid, product, kind, start, end, freq, lead, grid, temporal, licence, status, caveat, operational, parity='PROXY_REQUIRES_VALIDATION', units='product-specific; retain response/GRIB units'):
        rows.append({'source': sid, 'product': product, 'historical_product': kind, 'operational_product': operational,
                     'issuance_preserved': kind == 'OPERATIONAL_FORECAST_ARCHIVE', 'issue_frequency': freq, 'lead_time': lead,
                     'variable': 'precipitation / temperature' if not sid.startswith('glofas') else 'average daily river discharge',
                     'units': units, 'spatial_resolution': grid, 'temporal_resolution': temporal, 'archive_start': start,
                     'archive_end': end, 'version_alignment': 'run/version-specific; not independently established',
                     'training_serving_parity': parity, 'licence': licence, 'access_method': 'Official documented public API or authenticated official download; terms gate',
                     'status': status, 'caveat': caveat, 'geographic_coverage': 'Global including Karnataka for global models',
                     'actual_selected_event_runs_retrieved': False, 'approved_training_source': False})
    add('om_single_early', 'Open-Meteo ECMWF IFS Single Runs before 2026-05-12T06Z', 'REFORECAST_HINDCAST', '2024-03-14', '2026-05-12T06Z boundary',
        '00/06/12/18 UTC requested cycles', '10 days', '9 km documented IFS grid; response point can differ', 'hourly API', 'CC BY 4.0 data; free hosted API noncommercial',
        'NOT_ISSUANCE_PRESERVING', 'Earlier IFS series explicitly Cycle 49R1 hindcasts; pinned initialization is not proof of as-issued forecast.', 'Current Open-Meteo IFS forecast', units='precipitation mm preceding hour; temperature degC')
    add('om_single_recent', 'Open-Meteo ECMWF IFS Single Runs from 2026-05-12T06Z', 'OPERATIONAL_FORECAST_ARCHIVE', '2026-05-12T06:00Z', 'ongoing; checked 2026-10-08',
        '00/06/12/18 UTC', '10 days', '9 km documented IFS', 'hourly API', 'CC BY 4.0 data; hosted service terms apply',
        'ISSUANCE_ARCHIVE_WITH_CAVEATS', 'Cycle 50R1 transition; model initialization != delivery. Raw response does not echo run/version/publication clock. One technical sample, not original delivery verification.', 'Pinned IFS forecast', units='mm preceding hour; degC')
    add('om_previous', 'Open-Meteo Previous Runs', 'FIXED_LEAD_ARCHIVE', 'mostly January 2024; variable/model-specific', 'ongoing', 'model-specific', 'fixed leads 1–7 days',
        'model-specific', 'hourly', 'CC BY 4.0 data; hosted service terms', 'ISSUANCE_ARCHIVE_WITH_CAVEATS',
        'Fixed lead series is not a complete issued run; GFS temperature from March 2021 does not establish precipitation archive availability.', 'Open-Meteo model-pinned forecast')
    add('om_seamless', 'Open-Meteo Historical Forecast API', 'STITCHED_RETROSPECTIVE', 'model-specific', 'ongoing', 'stitched', 'not one pinned issuance', 'model-specific', 'hourly',
        'CC BY 4.0 data; hosted service terms', 'NOT_ISSUANCE_PRESERVING', 'Seamless historical time series does not reconstruct a full forecast as delivered at T.', 'Open-Meteo forecast')
    add('om_reanalysis', 'Open-Meteo Historical Weather API', 'REANALYSIS_RETROSPECTIVE', '1940 for ERA5; model-specific', 'delayed recent data', 'not forecast issuance', 'none',
        'ERA5 0.25 degree / ERA5-Land 0.1 degree; endpoint dependent', 'hourly', 'CC BY 4.0 data; hosted service terms', 'NOT_ISSUANCE_PRESERVING',
        'Later analysis may include information unavailable at T; not issued forecast.', 'No exact forecast equivalent', 'NO_OPERATIONAL_EQUIVALENT')
    add('ecmwf_tigge', 'ECMWF ECDS tigge-forecasts', 'OPERATIONAL_FORECAST_ARCHIVE', '2006-10 (month precision)', 'ongoing; centre-specific gaps',
        'ECMWF 00/12 UTC; centre-specific', 'typically 10–15 days', 'native/interpolated 0.12–0.9375 degrees; centre/version dependent', '6-hour steps',
        'TIGGE licence; full terms retrieval unavailable, redistribution unresolved', 'ISSUANCE_ARCHIVE_WITH_CAVEATS',
        'Operational ensemble archive, not reforecasts. Public 48-hour delay; initialization cannot serve as public availability. Specific 2009/2010 runs not retrieved. Accumulated precipitation must be differenced within identical run/member.',
        'Current ECMWF open forecasts differ in resolution/member/version; archived TIGGE public delivery route', units='tp kg/m2 accumulated from step 0, parameter 228228; temperature K')
    add('ecmwf_open', 'ECMWF Open Data', 'ROLLING_OPERATIONAL_FORECAST', 'latest 12 runs only', 'rolling 2–3 days', '00/06/12/18 UTC',
        '00/12 up to 360h; 06/18 up to 144h', '0.25 degree public subset', 'forecast steps', 'CC BY 4.0 plus ECMWF terms',
        'ISSUANCE_ARCHIVE_WITH_CAVEATS', 'Public rolling route cannot reconstruct old events. Prospective capture must preserve availability, model/run/member/steps.', 'ECMWF Open Data')
    add('glofas_forecast', 'cems-glofas-forecast', 'OPERATIONAL_FORECAST_ARCHIVE', '2019-11-05', 'ongoing catalogue', 'daily 00 UTC; 51 members',
        'EWDS archive 30 days; other current medium 15 / subseasonal 46-day products distinct', 'v4 catalogue 0.05 degree', 'daily means',
        'CEMS-FLOODS terms; authenticated EWDS', 'ISSUANCE_ARCHIVE_WITH_CAVEATS',
        'Historical operational versions vary; current v4 is not every archived year. v5 historical cell mapping not automatic v4 mapping; Gokak excluded.', 'GloFAS operational forecast', units='m3/s last-24h average; exact forecast-step intervals need validation')
    add('glofas_reforecast', 'cems-glofas-reforecast', 'REFORECAST_HINDCAST', '2003 nominal hindcast years', '2022 nominal hindcast years', '00 UTC, twice weekly; 11 members',
        '46 days', 'v4 0.05 degree', '24-hour steps', 'CEMS-FLOODS terms; EWDS', 'NOT_ISSUANCE_PRESERVING',
        'Later fixed-system simulations are not forecasts historically available at T. Specific hindcast dates/version and retrospective initialization must be reviewed.', 'Operational GloFAS forecast requires independent parity validation', 'PROXY_REQUIRES_VALIDATION', units='m3/s daily modelled discharge')
    add('glofas_history', 'cems-glofas-historical consolidated v5', 'HISTORICAL_CONSOLIDATED', '1980-01-01', '2025-12-31 inspected coverage',
        'retrospective consolidation, not issuance', 'none', '0.05 degree', 'daily', 'CEMS-FLOODS terms; EWDS', 'NOT_ISSUANCE_PRESERVING',
        'Stage 4D end-of-preceding-24h timestamps preserved; no measured substitution, skill comparison or forecast reinterpretation.', 'No exact operational equivalent established', 'NO_OPERATIONAL_EQUIVALENT', units='m3/s average in last 24h')
    for row in rows:
        require(row['status'] in ARCHIVE_STATUSES, 'Archive status vocabulary')
    return rows


def inspect_smoke(body, receipt):
    require(receipt['status'] == 'retrieved' and receipt['http_status'] == '200', 'Smoke retrieval failed')
    require(receipt['parameters']['models'] == 'ecmwf_ifs' and receipt['parameters']['forecast_days'] == '1'
            and receipt['parameters']['timezone'] == 'UTC', 'Bounded pinned request required')
    require(body['utc_offset_seconds'] == 0, 'UTC response required')
    times = body['hourly']['time']; run = receipt['parameters']['run']
    expected = [run[:10] + 'T' + f'{hour:02d}:00' for hour in range(24)]
    require(times == expected and len(set(times)) == 24, 'Exact one-day response alignment')
    require(body['hourly_units']['precipitation'] == 'mm' and body['hourly_units']['temperature_2m'] == '°C', 'Source units changed')
    counts = {}
    for variable in ('precipitation', 'temperature_2m'):
        values = body['hourly'][variable]; require(len(values) == 24, 'Response variable length')
        require(all(x is None or isinstance(x, (float, int)) and math.isfinite(x) for x in values), 'Nonfinite weather response')
        if variable == 'precipitation': require(all(x is None or x >= 0 for x in values), 'Negative precipitation')
        counts[variable] = {'finite': sum(x is not None for x in values), 'missing': sum(x is None for x in values)}
    return {'request': receipt['parameters'], 'url': receipt['url'], 'retrieved_at': receipt['retrieved_at'],
            'sha256': receipt['sha256'], 'bytes': receipt['bytes'], 'http_status': receipt['http_status'],
            'time_steps': 24, 'counts': counts, 'source_units': body['hourly_units'],
            'requested_location_distinct_from_returned_grid': True, 'server_run_version_echo': False,
            'original_delivery_clock_verified': False, 'historical_event_training_runs_retrieved': 0,
            'missing_values_preserved': True, 'purpose': 'technical contract only; no rainfall features or scientific inference'}


def positive_overlap():
    districts = {'2728': ('Udupi', 33), '2758': ('Kolar', 329), '3551': ('Udupi', 23), '3652': ('Chitradurga', 2)}
    with (ROOT / 'data/working/karnataka_positive_event_rainfall_v1/descriptive_event_rainfall.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require({r['gfd_id'] for r in rows} == set(districts), 'Positive identities changed')
    return [{'event_id': r['gfd_id'], 'district': districts[r['gfd_id']][0], 'event_start': r['gfd_start'],
             'event_end': r['gfd_end_inclusive'], 'qualifying_cells': districts[r['gfd_id']][1], 'label_quality': 'observation-qualified event-window positive only',
             'open_meteo_precipitation_archive_overlap': False, 'tigge_catalogue_period_overlap': r['gfd_start'] >= '2006-11-01',
             'tigge_specific_run_available': None, 'glofas_operational_archive_overlap': False,
             'glofas_reforecast_nominal_year_overlap': True, 'glofas_reforecast_was_available_at_event': False,
             'static_features_available': 'Existing scope geometry is retrospective; terrain/landcover vintage and reuse need checks',
             'issuance_reconstruction_possible': 'TIGGE conditional public availability validation' if r['gfd_start'] >= '2006-11-01' else 'not established',
             'candidate_for_future_training': False, 'missing_requirements': ['timed outcome', 'verified comparison evidence', 'run availability', 'source terms/parity']} for r in rows]


def readiness():
    return {'TARGET_DEFINITION': 'UNRESOLVED', 'POSITIVE_LABEL_READINESS': 'LIMITED', 'NEGATIVE_LABEL_READINESS': 'NOT_READY',
            'FORECAST_ARCHIVE_READINESS': 'LIMITED', 'WEATHER_PARITY': 'UNRESOLVED', 'HYDROLOGY_PARITY': 'UNRESOLVED',
            'TEMPORAL_ALIGNMENT': 'NOT_READY', 'SAMPLE_SIZE': 'NOT_READY', 'RISK_CLASS_MAPPING': 'UNRESOLVED',
            'status': 'target_and_archive_validation_ready_limited', 'model_training_allowed': False,
            'primary_target_status': 'primary_target_not_yet_adopted', 'primary_horizon': None,
            'methodology_review_complete': True, 'ml_readiness_status': 'ml_training_still_not_ready'}


def next_plan():
    return {'stage': 'Stage 5B — Time-Resolved Label Development & Issuance Dataset Pilot (gated)',
            'event': 'fp-official-belagavi-20210726', 'period': ['2021-07-24', '2021-07-30'],
            'scope': 'Existing Belagavi 2021 review tile and official Hulagabali/Halyal/Sankaratti context; no expansion',
            'reference': 'Retained NRSC 26 July 2021 WorldView-3 map and corroborating 28 July map; request legitimate categorical reference and acquisition times',
            'label_gate': 'Verify georeferencing, exact observation clock/interval, detection limitations and reuse before defining labels. PDF viewport is not flood geometry.',
            'weather_product': 'ECMWF ECDS tigge-forecasts; ECMWF origin ecmf; preserve initialization, member, version, 6h steps and availability evidence',
            'candidate_initializations_not_retrieved': ['2021-07-23T00:00:00+00:00', '2021-07-23T12:00:00+00:00'],
            'candidate_steps_hours': '48–168; request only required variables/scope after validating official schema and terms',
            'issuance_rule': 'Public availability has 48h delay. Reconstruct T from evidence of delivery, not initialization; valid interval must fit timed target.',
            'positive_proposal': 'Independently mapped non-permanent water in a precise cell/area and source observation interval; no event-window daily expansion',
            'comparison_proposal': 'Monitored non-inundation only after protocol sensitivity/time-coverage/reference checks; no negatives assumed',
            'hydrology': 'Omit from initial pilot until archived operational system network/time/version parity established; exclude Gokak',
            'static': 'Existing SRTM February 2000 terrain may be reviewed for vintage/release/scale; existing 2021 WorldCover cannot be assumed available in July 2021',
            'access_gates': ['TIGGE licence text and acceptance', 'legitimate ECDS account if required', 'official selected-run availability'],
            'stop_if_gate_fails': 'Retain source findings; no training records. Consider prospective pinned-run capture in existing Udupi window with explicit delivery timestamps and monitored outcomes.',
            'training_authorized': False, 'production_target_or_clock_adopted': False}


def input_records():
    paths = list(RAW.iterdir())
    for name in ['QandA.md', 'README.md', 'docs/PREDICTION_FEATURE_METHOD.md', 'docs/COMPARISON_EVIDENCE_METHOD.md',
                 'docs/GLOFAS_PILOT_METHOD.md', 'docs/EXTERNAL_HYDROLOGY_CLOSURE_METHOD.md', 'backend/app/weather.py',
                 'data/working/karnataka_positive_event_rainfall_v1/descriptive_event_rainfall.csv',
                 'data/working/karnataka_event_comparison_v1/evidence.json',
                 'data/working/belagavi_2021_sentinel1_anchor_v1/anchor.json',
                 'data/working/belagavi_2021_incidence_audit_v1/audit.json',
                 'data/working/karnataka_prediction_methodology_v1/manifest.json',
                 'data/working/karnataka_external_hydrology_closure_v1/manifest.json',
                 'data/working/karnataka_chirps_soi2025_2025_v1/manifest.json',
                 'data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf', 'data/raw/reference/stage3e2_v1/action2021.pdf']:
        paths.append(ROOT / name)
    return [record(p) for p in sorted(set(paths)) if p.is_file()]


def prior_gate():
    spec = importlib.util.spec_from_file_location('stage5_prior', ROOT / 'scripts/review_prediction_availability.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    summary = module.validate()
    require(summary['status'] == 'ml_training_not_ready', 'Prior readiness changed')
    return summary


def assemble():
    baseline = prior_gate(); docs = source_register(); req = requirements(); candidates = targets()
    for candidate in candidates: validate_target(candidate)
    smoke_path = RAW / 'om_pinned_smoke.json'; receipt = read(Path(str(smoke_path) + '.receipt.json'))
    require(receipt['sha256'] == sha(smoke_path) and receipt['bytes'] == smoke_path.stat().st_size, 'Original smoke bytes changed')
    smoke = inspect_smoke(read(smoke_path), receipt); sources = forecast_sources(); overlap = positive_overlap()
    matrix = []
    capabilities = ['event_occurred', 'event_did_not_occur', 'inundated_location', 'non_inundated_location', 'recorded_start_end',
                    'actual_onset_cessation', 'daily_occurrence', 'six_hour_occurrence', 'severity', 'impact', 'district_wide_state', 'locality_wide_state', 'risk_classes']
    for kind, supported, caveat in [
        ('gfd_positive', {'event_occurred', 'inundated_location', 'recorded_start_end'}, 'Only qualified event maximum; observation masks and permanent water exclusions required.'),
        ('gfd_observed_zero', {'recorded_start_end'}, 'No positive pixels in usable reviewed map, not proof of entire interval absence.'),
        ('insufficient_observation', {'recorded_start_end'}, 'No target label.'),
        ('ifi_reported', {'event_occurred', 'recorded_start_end'}, 'Documentary reported occurrence/dates only; spatial uncertainty retained.'),
        ('sentinel1_diagnostics', set(), 'Uncalibrated ambiguous SAR changes are not flood-positive labels.'),
        ('nrsc_context', {'event_occurred', 'inundated_location'}, 'Dated official contextual map, not yet machine-readable timed labels.')]:
        matrix.append({'evidence_type': kind, 'capabilities': {k: ('limited_documentary_or_spatial_support' if k in supported else 'not_supported') for k in capabilities}, 'caveat': caveat})
    concepts = {'requirement_classification': 'combination / ambiguous', 'observation_target': candidates[0],
                'model_target': None, 'user_facing_risk_output': risk_mapping(), 'alert_decision': None,
                'product_intent': {'geography': 'Karnataka district/locality; exact aggregation/footprints unspecified',
                                   'horizon': 'seven forecast days', 'refresh': 'every six hours', 'output': 'Low / Medium / High plus hotspots and warnings'},
                'missing_specifications': 'QandA refers to other master/change documents not present; README is verified rebuild scope.',
                'historical_claims_rejected': 'Synthetic/proxy labels, assumed scores and old Done claims are not evidence.',
                'primary_target_status': 'primary_target_not_yet_adopted', 'deployable_target_supported': False}
    negative = {'status': 'protocol_proposal_only; zero negatives created',
                'required': ['Precise spatial unit and time interval', 'Adequate valid observations throughout the interval',
                             'Sensor detection sensitivity / false-negative audit', 'Independent reference or monitored outcome',
                             'Permanent water, clouds, urban/vegetation limitations explicit', 'Predeclared selection and as-of parity'],
                'not_sufficient': ['No IFI/GFD record', 'Missing observation', 'Event maximum zero', 'Random normal day', 'Unmentioned district', '95% spatial availability alone'],
                'positive_unknown_negative_separate': True, 'existing_zero_scopes': ['2698 Bijapur', '3107 Raichur'],
                'no_numeric_quality_threshold_adopted': True}
    periods = [{'source': r['source'], 'start_date': r['archive_start'], 'end_date': r['archive_end'],
                'forecast_issue_preserved': r['issuance_preserved'], 'label_overlap': 'See per-event matrix; catalogue-only except technical smoke',
                'geographic_overlap': r['geographic_coverage'], 'usable_for_training': False, 'reason': r['caveat']} for r in sources]
    periods.append({'source': 'existing static products', 'start_date': 'SRTM acquisition February 2000; WorldCover2021; SOI2025; v5 statics2026',
                    'end_date': None, 'forecast_issue_preserved': False, 'label_overlap': 'Vintage, spatial scope and reuse not automatically compatible',
                    'geographic_overlap': 'Udupi and Belagavi bounded tiles; SOI state polygons local', 'usable_for_training': False,
                    'reason': 'Acquisition != release; current geometry does not establish old boundaries; restricted SOI remains local.'})
    summary = {'status': readiness()['status'], 'model_training_allowed': False, 'primary_target_adopted': False,
               'horizon_adopted': False, 'risk_mapping_defined': False, 'requirements_blocks': len(req), 'reviewed_sources': len(docs),
               'new_document_retrieval_successes': 21, 'new_document_retrieval_failures': 1, 'positive_scopes': 4, 'verified_negatives': 0,
               'tigge_catalogue_overlap_positive_scopes': sum(x['tigge_catalogue_period_overlap'] for x in overlap),
               'actual_historical_event_forecast_runs_retrieved': 0, 'training_records_created': 0,
               'quantitative_hydrology_comparisons': 0, 'stage5_preserved': baseline['status']}
    artifacts = {'product_target_requirements.json': req, 'target_candidate_register.json': candidates,
                 'target_evidence_matrix.json': matrix, 'label_semantics_review.json': concepts,
                 'forecast_issuance_definition.json': issuance_definition(),
                 'weather_forecast_archive_review.json': {'sources': [r for r in sources if not r['source'].startswith('glofas')], 'technical_check': smoke},
                 'glofas_forecast_archive_review.json': {'sources': [r for r in sources if r['source'].startswith('glofas')],
                     'gokak_excluded': True, 'cwc_model_skill_prohibited': True, 'measured_modelled_distinct': True,
                     'supported_history_cells_not_automatically_forecast_cells': True},
                 'forecast_source_parity_register.json': sources, 'archive_label_overlap.json': {'periods': periods, 'positive_events': overlap},
                 'negative_label_methodology.json': negative, 'risk_class_mapping_review.json': risk_mapping(),
                 'readiness_decision.json': readiness(), 'next_data_collection_plan.json': next_plan(),
                 'unresolved_questions.json': ['Occurrence vs impact/risk', 'Spatial aggregation and day boundaries', 'Issue clock and delivery history',
                      'Independent negatives and daily outcomes', 'TIGGE exact terms/run availability', 'Forecast system/network parity', 'SOI publication/current identity'],
                 'feature_source_register.json': docs, 'stage5a_summary.json': summary}
    return {n: encode(v) for n, v in artifacts.items()}, summary


def build(output=OUTPUT):
    output = Path(output); require(not output.exists(), 'Immutable version exists')
    artifacts, summary = assemble()
    manifest = {'version': 'karnataka_target_archive_review_v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                'inputs': input_records(), 'processing_code': record(Path(__file__)), 'summary': summary,
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in artifacts.items()}}
    output.mkdir(parents=True)
    for name, data in artifacts.items(): (output / name).write_bytes(data)
    (output / 'manifest.json').write_bytes(encode(manifest))
    return summary


def validate(output=OUTPUT):
    output = Path(output); manifest = read(output / 'manifest.json')
    require(manifest['inputs'] == input_records() and manifest['processing_code'] == record(Path(__file__)), 'Input/code checksum changed')
    artifacts, summary = assemble()
    require(manifest['summary'] == summary and set(manifest['files']) == set(artifacts), 'Manifest contents changed')
    for name, data in artifacts.items():
        require((output / name).read_bytes() == data and manifest['files'][name] ==
                {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}, 'Review reproduction failed')
    return summary


def public_metadata(output=OUTPUT):
    validate(output); output = Path(output)
    manifest = read(output / 'manifest.json')
    # Publish own decisions and technical counts, not QandA quotes, source imagery,
    # original documents, numeric weather observations, CWC values or SOI geometry.
    decisions = {name: read(output / name) for name in manifest['files'] if name != 'product_target_requirements.json'}
    return {**manifest, 'local_manifest_sha256': sha(output / 'manifest.json'), 'decisions': decisions,
            'publication': 'Own methodology, identifiers, technical counts, provenance and checksums only; original source files and requirements quotes local.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'publish-metadata'])
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.command == 'publish-metadata':
        metadata = public_metadata(args.output); PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        with PUBLIC.open('xb') as stream: stream.write(encode(metadata))
        print(json.dumps({'public_manifest': str(PUBLIC)}))
    else:
        print(json.dumps((build if args.command == 'build' else validate)(args.output), indent=2))
