#!/usr/bin/env python3
"""Stage 4C2: offline source semantics, immutable build and read-only validation.

Requires retained official documents; no network, source repairs or features.
Detailed coordinates, disagreements and clarification examples stay local.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/reference/stage4c2_v1'
PRIOR = ROOT / 'data/working/karnataka_hydrology_2019_reconciled_v1'
PILOT = ROOT / 'data/working/karnataka_hydrology_2019_pilot_v1'
OUTPUT = ROOT / 'data/working/karnataka_hydrology_semantics_v1'
PUBLIC = ROOT / 'data/reference/karnataka_hydrology_semantics_v1'
RESOURCE = '7778f459-0e82-4681-9638-5e494c36fd42'
DATASET = 'd951a09c-6cf8-470e-be77-e80116f13d34'
DATUM = {'nwdp_datum_verified_msl', 'nwdp_datum_verified_gauge',
         'nwdp_datum_station_specific', 'nwdp_datum_unresolved'}
LINEAGE = {'same_revision_confirmed', 'different_revision_confirmed',
           'revision_possible_record_lineage_unverified', 'independent_publication_paths', 'lineage_unresolved'}
COORDINATES = {'coordinate_variation_explained', 'coordinate_precision_difference_likely',
               'possible_station_relocation_unverified', 'coordinate_conflict_unresolved'}
REUSE = {'reuse_clearly_permitted_with_attribution', 'reuse_permitted_for_internal_research_only',
         'producer_permission_required', 'policy_conflict_unresolved'}
QUESTIONS = {
    'datum': 'Does the exact historical Krishna manual-hourly Water Level field report stage above local gauge zero, R.L. above MSL, or a station-specific reference? Please supply its dictionary and applicable zero/reference history.',
    'lineage': 'Are CWC manual-daily NWDP values field, validated archival, revised, or direct Water Year Book records? Can later revisions differ from the book? Please identify versions for the enclosed disagreements; neither value has been preferred.',
    'quality': 'Which original fields identify observed, computed, revised and rejected/discarded discharge? What do absent flags mean? Please explain the book * and # relationship to NWDP records.',
    'coordinates': 'Which official coordinate version is canonical for these stations? Were sites/gauges relocated or coordinates corrected? Please provide dated station-specific history, including Sadalga and Gokak differences.',
    'reuse': 'May downloaded NWDP CWC observations and derived detailed comparisons be redistributed in an academic open-source project with attribution? How do Other (Open), the NWDP portal policy, National Water Data Policy 2026 and CWC copyright permission requirements apply? Is written permission required?',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def body(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


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


def check_version(path):
    manifest = read(path / 'manifest.json')
    for name, expected in manifest['files'].items():
        require(Path(name).name == name, 'Unsafe manifest path')
        require(record(path / name)['sha256'] == expected['sha256'] and
                (path / name).stat().st_size == expected['bytes'], 'Prior version integrity')


def preserve_prior(observations, quality, cases):
    require(len(observations) == len(quality) == 1697 and len(cases) == 81, 'Frozen row counts changed')
    require(sum(r['analysis_eligibility'] == 'eligible_with_quality_caveat' for r in quality) == 14, 'Eligibility changed')
    require(all(all(r[k] == v for k, v in o.items()) for r, o in zip(quality, observations)), 'Source values changed')


def datum_status(definition=None, *, exact_resource=False, citation=None):
    """Magnitude/unit/auxiliary zeros and general handbook never establish this field."""
    if not exact_resource or not citation or definition is None:
        return 'nwdp_datum_unresolved'
    mapping = {'msl': 'nwdp_datum_verified_msl', 'gauge': 'nwdp_datum_verified_gauge',
               'station_specific': 'nwdp_datum_station_specific'}
    require(definition in mapping, 'Unknown datum definition')
    return mapping[definition]


def threshold_status(observation_reference=None, threshold_reference=None, *, citations=False):
    if not citations or not observation_reference or not threshold_reference:
        return 'datum_unresolved'
    return 'datum_compatible' if observation_reference == threshold_reference else 'datum_incompatible'


def lineage_status(*, record_evidence=None, citation=None, revision_procedure=False):
    if record_evidence is not None:
        require(record_evidence in LINEAGE and citation, 'Record lineage requires authoritative citation')
        return record_evidence
    return 'revision_possible_record_lineage_unverified' if revision_procedure else 'lineage_unresolved'


def lineage_rows(cases, status):
    require(status in LINEAGE, 'Unknown lineage status')
    result = []
    for case in cases:
        if case['classification'] in {'yearbook_computed_vs_nwdp', 'source_value_conflict'}:
            result.append({**deepcopy(case), 'source_lineage_status': status,
                           'record_revision_evidence': None, 'preferred_for_analysis': None,
                           'preference_basis': None})
    return result


def coordinate_status(*, explicit_explanation=None, citation=None, precision_only=False,
                      relocation_claim=False):
    require(not relocation_claim or (explicit_explanation and citation), 'Relocation requires explicit evidence')
    if explicit_explanation and citation:
        return 'coordinate_variation_explained'
    return 'coordinate_precision_difference_likely' if precision_only else 'coordinate_conflict_unresolved'


def parse_coordinate_row(text, station_id):
    """Parse the actual code-anchored HO table, never geocode or average coordinates."""
    matches = list(re.finditer(r'(\d{1,2}\.\d+)\s+(\d{1,3}\.\d+)\s+\d+\s+HO(?:/FF)?\s+' + re.escape(station_id) + r'\b', text))
    require(len(matches) == 1, 'Missing/ambiguous station coordinate row')
    match = matches[0]
    lat, lon = match.group(1, 2)
    require(-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180, 'Invalid coordinates')
    return {'latitude_original': lat, 'longitude_original': lon, 'latitude': float(lat),
            'longitude': float(lon), 'precision_decimal_places': [len(lat.split('.')[1]), len(lon.split('.')[1])],
            'literal_context': text[max(0, text.rfind('\n\n', 0, match.start())):match.end()]}


def reuse_status(*, attributed_permission=False, producer_permission=False, applicability_ambiguous=False,
                 internal_permission=False):
    if applicability_ambiguous:
        return 'policy_conflict_unresolved'
    if producer_permission:
        return 'producer_permission_required'
    if attributed_permission:
        return 'reuse_clearly_permitted_with_attribution'
    if internal_permission:
        return 'reuse_permitted_for_internal_research_only'
    return 'policy_conflict_unresolved'


def change_readiness(*, identity_strong, consistent_units, unique_times, reference_stability_verified,
                     time_semantics_verified):
    if not (identity_strong and consistent_units and unique_times):
        return 'blocked'
    if reference_stability_verified and time_semantics_verified:
        return 'usable_only_for_within_station_change_rate'
    return 'conditional_future_within_station_change_reference_and_time_checks_required'


def discharge_readiness(eligible_count):
    require(isinstance(eligible_count, int) and eligible_count >= 0, 'Invalid eligibility')
    return 'restricted_to_currently_eligible_14_rows' if eligible_count else 'blocked'


def pdf_text(path, page=None):
    command = ['pdftotext', '-layout']
    if page is not None:
        command += ['-f', str(page), '-l', str(page)]
    return subprocess.run(command + [str(path), '-'], check=True, capture_output=True,
                          text=True, timeout=60).stdout


def resource_metadata(catalogue, original):
    datasets = catalogue['result']['results']
    require(len(datasets) == 1 and datasets[0]['id'] == DATASET, 'Wrong NWDP dataset')
    dataset = datasets[0]
    resource = [r for r in dataset['resources'] if r['id'] == RESOURCE]
    require(len(resource) == 1, 'Wrong NWDP resource')
    resource = resource[0]
    return {'dataset_id': DATASET, 'resource_id': RESOURCE, 'producer': dataset['author'],
            'title': resource['name'], 'description': resource['description'], 'format': resource['format'],
            'resource_created': resource['created'], 'resource_updated': resource['last_modified'],
            'resource_metadata_updated': resource['metadata_modified'], 'dataset_metadata_updated': dataset['metadata_modified'],
            'resource_md5': resource['hash'], 'resource_bytes': resource['size'], 'download_url': resource['url'],
            'licence': dataset['license_title'], 'licence_url': dataset.get('license_url'),
            'extras': dataset['extras'], 'original_columns': original['schema_and_census']['original_columns'],
            'original_quality_columns': original['schema_and_census']['quality_columns'],
            'data_dictionary_status': 'exact_field_datum_definition_not_found_in_bounded_official_review',
            'preview': 'Public resource iframe confirms column labels and file/metadata times, not datum',
            'api': 'Advertised catalogue API retrieved; public API page inspected. No hidden observation API used',
            'record_revision_fields': [], 'timestamps_are_record_revision_dates': False,
            'other_open_definition': 'No attached licence text/URL or standard-licence definition found on inspected pages/catalogue'}


def clarification(metadata, identities, conflicts, source_urls=None):
    return {'status': 'prepared_not_sent', 'purpose': 'FloodPulse academic exploratory historical flood research; no model/feature creation or detailed publication',
            'dataset_id': metadata['dataset_id'], 'resource_id': metadata['resource_id'],
            'resource_title': metadata['title'], 'source_url': metadata['download_url'],
            'discharge_resource_id': 'f95150ea-c8fc-4740-8815-d9c34c9d53a3',
            'station_ids': sorted(r['station_id'] for r in identities), 'questions': QUESTIONS,
            'source_urls': deepcopy(source_urls or []),
            'examples': [deepcopy(next(c for c in conflicts if c['station_id'] == r['station_id'])) for r in identities],
            'coordinate_history_attached': 'coordinate_provenance.json (local, small)',
            'no_large_attachments': True, 'no_message_sent': True}


def inputs():
    paths = list(RAW.iterdir()) + list(PRIOR.iterdir()) + list(PILOT.iterdir())
    paths += [ROOT / 'data/raw/reference/stage4a_v1/cwc_hddp2018.pdf',
              ROOT / 'data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf',
              ROOT / 'data/raw/reference/stage3e3_v1/cwc_station_metadata.pdf',
              ROOT / 'data/raw/reference/stage4b_v1/krishna_wyb2019_20.pdf']
    paths += [ROOT / 'data/raw/reference/stage4b_v1' / name for name in
              ['river_discharge_manual_daily_cwc_ka_2001_2025.csv', 'rwl_manual_hr_cwc_007_1991_2020.csv',
               'karnataka_discharge_gauge_daily_1972_to_2020.csv', 'river_discharge_tele_hr_karnataka_ka_1970_2025.csv']]
    return [record(p) for p in sorted(paths) if p.is_file()]


def assemble():
    check_version(PRIOR); check_version(PILOT)
    observations = rows(PILOT / 'observations.csv'); cases = rows(PRIOR / 'discharge_reconciliation.csv')
    quality = rows(PRIOR / 'observation_quality.csv'); identities = read(PRIOR / 'station_identity.json')
    preserve_prior(observations, quality, cases)
    resource = next(r for r in read(PILOT / 'raw_source_registry.json') if r['resource_id'] == RESOURCE)
    metadata = resource_metadata(read(RAW / 'krishna_catalogue.json'), resource)
    documents = []
    for sidecar in sorted(RAW.glob('*.*.json')):
        item = read(sidecar)
        if 'source_url' not in item:
            continue
        original = Path(str(sidecar)[:-5])
        require(item['status'] == 'retrieved' and item['sha256'] == digest(original), 'Document retrieval integrity')
        documents.append({**item, 'local_path': str(original.relative_to(ROOT))})
    retained_policy = ROOT / 'data/raw/reference/stage4a_v1/cwc_hddp2018.pdf'
    documents.append({**read(Path(str(retained_policy) + '.json')), 'local_path': str(retained_policy.relative_to(ROOT)),
                      'reused_original': True, 'edition': 'November2018', 'inspected_pdf_pages': [2,5]})
    handbook = pdf_text(RAW / 'cwc_handbook2020.pdf', 186)
    require('7.560' in handbook and '70.560' in handbook and 'reduced level' in handbook, 'Authoritative formula absent')
    notes = {'handbook': {'edition': 'June2020', 'pdf_pages': [18, 19, 21, 50, 139, 141, 142, 186],
        'gauge_zero': 'Sec2.1.3: gauge zero tied to nearest GTS benchmark; R.L. relative to MSL recorded; normally retained when replacing gauge, special changes possible; moved temporary gauges correlated',
        'formula': 'reported_water_level = gauge_reading + gauge_zero_RL',
        'formula_evidence': 'PDF186 step4 numerical reporting example; PDF18 sec2.1.3 connects zero to MSL',
        'forms': {'CWC/RD-2': 'PDF139 separate mean gauge, MSL water level, Q m3/s and observed/computed; R.L. zero GTS and last check',
                  'CWC/RD-3': 'PDF141 separate gauge reading and water level with zero GTS',
                  'CWC/RD-4': 'PDF142 hourly flood levels with zero GTS'},
        'rating_curve': 'PDF50 sec4.4: discharge computed where daily measurement infeasible; curve based on observed stage/discharge range, extrapolation for extraordinary floods',
        'nwdp_field_definition_established': False},
        'yearbook': {'edition': 'Krishna2019-20 VolumeI March2021', 'pdf_pages': [21,22,23],
            'processing': 'SWDES field forms, division primary validation, regional HYMOS processing/finalisation; sinceJune2016 observed data entered into e-SWIS',
            'rating_revision': 'Sec1.4.3 seasonal rating curve validation/discarding points and checking previous-year shifts; non-observed/discarded Q computed using0800 water level',
            'markers': '* computed; # discarded/changed using rating curve; unmarked observed/estimated not certified directly measured',
            'nwdp_same_snapshot_established': False},
        'policy2026': {'title': 'National Water Data Policy2026', 'pdf_pages': [6,15,17],
            'pdf_metadata_title': 'Final Draft NWDP 2026  -20-03-2026 (5).pdf',
            'adoption_status': 'Official portal-linked document; final adoption/commencement not independently verified. PDF creation/modification dates are not policy commencement dates',
            'supersession': 'Sec1.2 text states supersession of2018 policy; draft metadata means enacted supersession not independently established',
            'quality': 'Sec3.7 assigns producer responsibility for validation/essential metadata, not actual record certification',
            'reuse': 'Sec4.4 unclassified data download free; use in publication acknowledges producer; no express resolution of CWC website copyright/NWDP Other(Open) detailed redistribution interaction'},
        'research_scope': 'Bounded official handbook, exact resource/Preview/catalogue, CWC/WRIS/NWIC official searches and linked2026 metadata. No exact-field dictionary or record lineage found; not proof none exists.'}
    conflicts = lineage_rows(cases, lineage_status(revision_procedure=True))
    require(Counter(c['classification'] for c in conflicts) == {'yearbook_computed_vs_nwdp': 12, 'source_value_conflict': 21}, 'Disagreement regression')
    datums = []; histories = []; readiness = []
    closed_book = pdf_text(RAW / 'cwc_closed2026.pdf')
    previous_datums = {d['station_id']: d for d in read(PRIOR / 'datum_compatibility.json')}
    for identity in identities:
        key = identity['station_id']; old = previous_datums[key]
        datums.append({'station_id': key, 'nwdp_datum_status': datum_status(), 'threshold_compatibility': threshold_status(),
                      'threshold_source_original': deepcopy(old['stage4a_thresholds_original']),
                      'yearbook_datum_evidence': deepcopy(old['yearbook_datum_evidence']),
                      'auxiliary_original': deepcopy(old['nwdp_auxiliary_fields']), 'conversion_applied': False,
                      'threshold_temporal_applicability': old['threshold_temporal_applicability'],
                      'hfl_disagreement': old['hfl_note'], 'threshold_exceedances_computed': False})
        page = identity['stage4a_original']['source_page']
        newer = parse_coordinate_row(pdf_text(RAW / 'cwc_ho2026.pdf', page), key)
        yearbook_text = pdf_text(ROOT / 'data/raw/reference/stage4b_v1/krishna_wyb2019_20.pdf', identity['yearbook_history_page'])
        coordinate_literal = [line.strip() for line in yearbook_text.splitlines() if 'Latitude' in line and 'Longitude' in line]
        require(len(coordinate_literal) == 1, 'Year Book coordinate history absent')
        require(key not in closed_book and identity['stage4a_original']['official_name'].lower() not in closed_book.lower(), 'New closure evidence requires explicit review')
        histories.append({'station_id': key, 'name': identity['stage4a_original']['official_name'],
            'river': identity['stage4a_original']['source_river'], 'gauge_opening': identity['gauge_opening_date'],
            'source_history': [
                {'source': 'CWC_HO2025', 'reference_date': '2025-01-01', 'publication': 'April2025', 'page': page, 'original': identity['stage4a_original']},
                {'source': 'NWDP', 'resource_update': metadata['resource_updated'], 'original_fields': identity['nwdp_identity_fields'],
                 'current_cwc_code_supplied': False},
                {'source': 'YearBook2019-20', 'publication': 'March2021', 'page': identity['yearbook_history_page'],
                 'legacy_code': identity['yearbook_legacy_id'], 'name': identity['yearbook_original_name'],
                 'coordinates': identity['coordinates_by_source']['yearbook'], 'precision': 'whole arcseconds',
                 'coordinate_literal': coordinate_literal[0],
                 'history_fields': identity['yearbook_history_fields'], 'zero_history': identity['yearbook_zero_gauge_history_literal']},
                {'source': 'CWC_HO2026', 'reference_date': '2026-01-01', 'publication': 'March2026', 'page': page,
                 'original': newer}],
            'prior_distances_m': identity['approximate_distance_m'], 'status': coordinate_status(),
            'relocation_evidence': None, 'canonical_coordinate_selected': False, 'coordinates_modified': False,
            'closure_review': 'No target code/name found in bounded full-text review of official closed-HO2026 book; no station-specific relocation/correction explanation found',
            'newer_source_change': [newer['latitude'], newer['longitude']] != identity['coordinates_by_source']['stage4a']})
        selected = [r for r in observations if r['canonical_cwc_station_id'] == key and r['variable'] == 'water_level']
        unique = len({r['observation_time'] for r in selected}) == len(selected)
        units = {r['units'] for r in selected} == {'meter'}
        eligible = sum(r['canonical_cwc_station_id'] == key and r['analysis_eligibility'] == 'eligible_with_quality_caveat' for r in quality)
        readiness.append({'station_id': key, 'hourly_water_level': 'blocked',
            'within_station_future_feasibility': change_readiness(identity_strong=identity['identity_status']=='identity_strongly_supported',
                consistent_units=units, unique_times=unique, reference_stability_verified=False, time_semantics_verified=False),
            'source_identity': identity['identity_status'], 'consistent_unit_and_unique_timestamps': units and unique,
            'constant_reference_verified': False, 'time_zone_latency_verified': False,
            'future_change_rationale': 'Differences remove a constant additive datum mathematically, but gauge/reference stability, QC, irregular time intervals and source revision must be checked; no across-station absolute comparison',
            'daily_discharge': discharge_readiness(eligible), 'currently_eligible_rows': eligible,
            'threshold_relative_level': 'blocked_by_datum', 'coordinate_based_association': 'usable_with_caveat',
            'coordinate_caveat': 'Documentary station identity only; no precise spatial join/canonical point until source conflict resolved',
            'features_created': 0})
    policies = []
    for resource in read(PILOT / 'raw_source_registry.json'):
        policies.append({'resource_id': resource['resource_id'], 'producer': resource['producer'],
            'licence': resource['resource_licence'], 'licence_text_or_url': None,
            'standard_licence_inferred': False, 'reuse_status': reuse_status(applicability_ambiguous=True),
            'portal_policy': 'Attributed accurate/nonmisleading reproduction; explicitly third-party material excepted',
            'producer_policy': 'CWC website reproduction requires permission; state resource-specific definition absent',
            'policy2026': 'Portal-linked document supports unclassified NWIC downloads/use with producer acknowledgement; PDF title Final Draft, adoption not verified; does not settle detailed redistribution applicability',
            'publish_raw_or_detailed': False})
    policies.append({'artifact': 'CWC website documents', 'reuse_status': reuse_status(producer_permission=True),
                     'book_marking': 'FOR OFFICIAL USE ONLY', 'publish_raw_or_detailed': False,
                     'internal_retention': 'Local evidence retention is project handling, not an inferred legal licence grant'})
    summary = {'preserved_observations': len(observations), 'preserved_comparisons': len(cases),
        'preserved_eligible_rows': 14, 'unresolved_disagreements': len(conflicts),
        'disagreement_categories': dict(Counter(c['classification'] for c in conflicts)),
        'datum_status': {d['station_id']: d['nwdp_datum_status'] for d in datums},
        'threshold_compatibility': {d['station_id']: d['threshold_compatibility'] for d in datums},
        'source_lineage_status': lineage_status(revision_procedure=True),
        'coordinate_status': {h['station_id']: h['status'] for h in histories},
        'newer_metadata_coordinate_change': {h['station_id']: h['newer_source_change'] for h in histories},
        'reuse_status': 'policy_conflict_unresolved', 'clarification': 'prepared_not_sent',
        'features_created': 0, 'labels_created': 0, 'source_values_changed': 0,
        'readiness': 'Limited14-row discharge subset retained; absolute/threshold levels blocked; within-station change scientifically conditional, not yet approved for feature construction'}
    artifacts = {'source_documents.json': documents, 'measurement_semantics.json': notes, 'nwdp_resource_metadata.json': metadata,
        'datum_findings.json': datums, 'source_lineage.json': conflicts, 'coordinate_provenance.json': histories,
        'reuse_policy.json': policies, 'stage4d_readiness.json': readiness, 'unresolved_questions.json': QUESTIONS,
        'clarification_package.json': clarification(metadata, identities, conflicts,
            [d['source_url'] for d in documents] +
            ['https://cwc.gov.in/sites/default/files/stage-dischargecompressed.pdf',
             'https://cwc.gov.in/sites/default/files/ho-metadata-book-2025final-publishedsigned.pdf',
             read(ROOT / 'data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf.json')['source_url']] +
            [r['resource_page_url'] for r in read(PILOT / 'raw_source_registry.json')])}
    return {name: body(value) for name, value in artifacts.items()}, summary


def freeze(output=OUTPUT):
    output = Path(output)
    require(not output.exists(), 'Immutable semantics version exists')
    artifacts, summary = assemble()
    manifest = {'version': 'karnataka_hydrology_semantics_v1', 'created_at': datetime.now(timezone.utc).isoformat(),
        'inputs': inputs(), 'processing_code': record(Path(__file__)), 'summary': summary,
        'files': {name: {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()} for name, value in artifacts.items()}}
    output.mkdir(parents=True)
    for name, value in artifacts.items():
        (output / name).write_bytes(value)
    (output / 'manifest.json').write_bytes(body(manifest))
    return summary


def validate(output=OUTPUT):
    output = Path(output); manifest = read(output / 'manifest.json')
    require(inputs() == manifest['inputs'] and record(Path(__file__)) == manifest['processing_code'], 'Semantics input/code changed')
    artifacts, summary = assemble()
    require(summary == manifest['summary'], 'Semantics summary changed')
    require(set(manifest['files']) == set(artifacts), 'Unexpected/missing artifacts')
    for name, value in artifacts.items():
        require((output / name).read_bytes() == value and manifest['files'][name] ==
                {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}, 'Semantics reproduction mismatch')
    return summary


def public_manifest(output=OUTPUT):
    manifest = read(Path(output) / 'manifest.json')
    return {**manifest, 'local_manifest_sha256': digest(Path(output) / 'manifest.json'),
        'source_documents': read(Path(output) / 'source_documents.json'),
        'publication': 'Code, questions template, source references and aggregate provenance only; detailed source values/coordinates and documents remain local'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'])
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output) if args.command == 'build' else validate(args.output), indent=2))
