"""Offline scientific gates for proposed station forecasts. Never fits a model.

These checks validate supplied evidence, not its scientific authenticity. A named
independent reviewer must verify the source receipts before approving an experiment.
Fixtures used in tests are isolated examples, never production observations.
"""
import datetime as dt
import math
import re
from urllib.parse import urlsplit

MEASURED = 'measured_cwc_nwdp'
REQUIRED_REVIEWS = ('station_history', 'time_dictionary', 'measurement_method',
                    'datum_history', 'quality_control', 'reuse_rights')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp missing')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Documented timezone required; do not assume IST/UTC')
    return result.astimezone(dt.timezone.utc)


def reviewed(receipt):
    if not isinstance(receipt, dict):
        return False
    url = urlsplit(str(receipt.get('source_url', '')))
    return (receipt.get('status') == 'VERIFIED' and
            isinstance(receipt.get('reviewer'), str) and bool(receipt['reviewer'].strip()) and
            url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password and
            not url.query and not url.fragment and
            isinstance(receipt.get('sha256'), str) and
            re.fullmatch('[a-f0-9]{64}', receipt['sha256']) is not None)


def finite(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a measurement')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Nonfinite measurement')
    return number


def observation_blockers(row, metadata, *, issue_time=None):
    """Predictor check when issue supplied; future targets may arrive after issue.

    Dates/values stay original. No interpolation, offset, gap filling or source
    preference is inferred. Timestamp syntax alone does not establish semantics.
    """
    blockers = []
    if row.get('source_class') != MEASURED:
        blockers.append('NOT_MEASURED_STATION_DATA')
    if row.get('station_id') != metadata.get('station_id') or not row.get('station_id'):
        blockers.append('STATION_ID_MISMATCH')
    variable = row.get('variable')
    if variable not in {'water_level', 'discharge'}:
        blockers.append('UNSUPPORTED_VARIABLE')
    expected = 'm' if variable == 'water_level' else 'm3/s'
    if row.get('units') != expected:
        blockers.append('UNITS_NOT_NORMALIZED_WITH_EVIDENCE')
    try:
        value = finite(row.get('value'))
        if variable == 'discharge' and value < 0:
            blockers.append('NEGATIVE_DISCHARGE')
    except (TypeError, ValueError, OverflowError):
        blockers.append('INVALID_VALUE')
    if row.get('quality_status') != 'ACCEPTED_MEASURED':
        blockers.append('QC_NOT_CONFIRMED_MEASURED')
    if row.get('duplicate_status') != 'UNIQUE_OR_OFFICIALLY_RECONCILED':
        blockers.append('DUPLICATE_CONFLICT_REVIEW_MISSING')
    if row.get('statistic') != 'instantaneous':
        blockers.append('INSTANTANEOUS_TARGET_SEMANTICS_UNVERIFIED')
    reviews = metadata.get('reviews', {})
    for key in REQUIRED_REVIEWS:
        if not reviewed(reviews.get(key)):
            blockers.append('UNVERIFIED_'+key.upper())
    if not metadata.get('datum') or row.get('datum') != metadata['datum']:
        blockers.append('DATUM_MISMATCH_OR_UNKNOWN')
    try:
        observed = timestamp(row.get('observation_time'))
        effective_from = timestamp(metadata.get('valid_from'))
        effective_to = timestamp(metadata.get('valid_to'))
        if not effective_from <= observed < effective_to:
            blockers.append('OUTSIDE_STATION_METADATA_VALIDITY')
    except (TypeError, ValueError):
        observed = None
        blockers.append('UNVERIFIED_OBSERVATION_TIME_OR_METADATA_VALIDITY')
    if issue_time is not None:
        try:
            issued = timestamp(issue_time)
            available = timestamp(row.get('availability_time'))
            if observed is None or observed > issued or available > issued or available < observed:
                blockers.append('PREDICTOR_NOT_AVAILABLE_AT_ISSUE')
        except (TypeError, ValueError):
            blockers.append('PREDICTOR_AVAILABILITY_UNKNOWN')
    return sorted(set(blockers))


def assess_pair(predictor, outcome, metadata, issue_time, *, lead_hours=6):
    if type(lead_hours) is not int or lead_hours != 6:
        raise ValueError('This proposed contract is for +6h, not a silently changed target')
    issued = timestamp(issue_time)
    blockers = observation_blockers(predictor, metadata, issue_time=issue_time)
    blockers += observation_blockers(outcome, metadata)
    if predictor.get('variable') != outcome.get('variable'):
        blockers.append('TARGET_VARIABLE_MISMATCH')
    try:
        ptime = timestamp(predictor.get('observation_time'))
        target = timestamp(outcome.get('observation_time'))
        if not dt.timedelta(0) <= issued-ptime <= dt.timedelta(hours=1):
            blockers.append('PREDICTOR_TOO_OLD_OR_FUTURE')
        if target != issued+dt.timedelta(hours=6):
            blockers.append('TARGET_NOT_EXACT_LEAD_TIME')
    except (TypeError, ValueError):
        blockers.append('PAIR_TIME_INVALID')
    return {'status': 'ELIGIBLE_FOR_REVIEW' if not blockers else 'UNKNOWN',
            'blockers': sorted(set(blockers)), 'lead_hours': lead_hours,
            'training_authorized': False}


def threshold_outcome(row, metadata, threshold):
    """Point-time exceedance only; never absence across the next six-hour interval."""
    blockers = observation_blockers(row, metadata)
    if not isinstance(threshold, dict):
        return {'outcome': 'UNKNOWN', 'blockers': ['OFFICIAL_THRESHOLD_MISSING']}
    if not reviewed(threshold.get('review')) or threshold.get('authority') != 'CWC':
        blockers.append('OFFICIAL_THRESHOLD_NOT_VERIFIED')
    if threshold.get('kind') not in {'warning_level', 'danger_level'}:
        blockers.append('NOT_OFFICIAL_WARNING_OR_DANGER_LEVEL')
    for key in ('station_id', 'variable', 'units', 'datum'):
        if not row.get(key) or threshold.get(key) != row[key]:
            blockers.append('THRESHOLD_'+key.upper()+'_MISMATCH')
    try:
        if not timestamp(threshold.get('valid_from')) <= timestamp(row.get('observation_time')) < timestamp(threshold.get('valid_to')):
            blockers.append('THRESHOLD_NOT_EFFECTIVE_AT_OBSERVATION')
        limit = finite(threshold.get('value'))
        value = finite(row.get('value'))
    except (TypeError, ValueError, OverflowError):
        blockers.append('THRESHOLD_VALUE_OR_TIME_INVALID')
    return {'outcome': 'UNKNOWN' if blockers else 'EXCEEDS' if value > limit else 'DOES_NOT_EXCEED_AT_INSTANT',
            'blockers': sorted(set(blockers)), 'interval_absence_established': False,
            'inundation_established': False}


def validate_forecast_receipt(row, *, enabled=False, now):
    """Future read-only integration contract; no network endpoint or alert side effect.

    This is not an operational integration. Only genuinely obtained original
    issued values with proven rights, timing and source geography may be reviewed.
    """
    if enabled is not True:
        raise ValueError('Experimental source integration disabled')
    sources = {'CWC': 'official_river_forecast', 'GLOFAS': 'external_modelled_river_forecast',
               'IMD_FFG': 'official_flash_flood_guidance', 'KSNDMC': 'official_alert'}
    if sources.get(row.get('source')) != row.get('forecast_class'):
        raise ValueError('Incorrect attribution or source class')
    if not reviewed(row.get('access_review')) or not reviewed(row.get('display_rights_review')):
        raise ValueError('Authorized access and display rights not verified')
    if not re.fullmatch('[a-f0-9]{64}', str(row.get('original_sha256', ''))) or not row.get('source_product_id'):
        raise ValueError('Original product provenance missing')
    semantics = {'CWC': 'verified_station', 'GLOFAS': 'verified_model_reach',
                 'IMD_FFG': 'source_watershed', 'KSNDMC': 'source_alert_area'}
    if row.get('geographic_semantics') != semantics[row['source']]:
        raise ValueError('Unverified geographic meaning; district blanket forecasts prohibited')
    if not reviewed(row.get('geographic_review')):
        raise ValueError('Geographic association not verified')
    if not row.get('geographic_id') or not row.get('product_version'):
        raise ValueError('Pinned geographic unit/version required')
    issued, available, retrieved, start, end, current, expires = map(timestamp, (
        row.get('issue_time'), row.get('availability_time'), row.get('retrieved_at'),
        row.get('valid_start'), row.get('valid_end'), now, row.get('expires_at')))
    if not issued <= available <= retrieved <= current or not issued <= start < end or not current < expires <= end:
        raise ValueError('Invalid, stale or inconsistent forecast times')
    if type(row.get('maximum_age_hours')) is not int or not 0 < row['maximum_age_hours'] <= 48:
        raise ValueError('Reviewed source age limit required')
    if current-issued > dt.timedelta(hours=row['maximum_age_hours']):
        raise ValueError('Forecast exceeds reviewed age limit')
    return {'status': 'ELIGIBLE_FOR_SOURCE_REVIEW', 'forecast_class': row['forecast_class'],
            'floodpulse_ai': False, 'automatic_alerts': False, 'training_label': False}
