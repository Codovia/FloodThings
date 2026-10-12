#!/usr/bin/env python3
"""Offline native-grid quality screening, separate from flood-label certification.

Source classes are preserved. No source pixel is automatically promoted to a
temporary-flood or non-flood label. Frozen earlier contracts are composed here,
not rewritten. Raw raster reads are bounded to the reviewed 100x100 subsets.
"""
import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from acquire_direct_observation_metadata import ROOT, validate_receipts
from acquire_opera_bounded_preview import BANDS, IDS, validate_plan
from audit_satellite_observations import audit as audit_contracts

RAW = 'data/raw/direct_flood_observations_phase12e_v1'
OUTPUT = 'data/working/direct_flood_observations_phase12e_v1'
PUBLIC = 'docs/phase12e'


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return {'bytes': Path(path).stat().st_size, 'sha256': digest.hexdigest()}


def load(root, relative):
    return json.loads((root/relative).read_text())


def classify_source_pixels(bands):
    """Quality categories, not labels. Unknown codes and class contradictions fail closed.

    Both spec DIAG=120 fill and exported EE=255 are insufficient. WTR/CONF masks
    250/251 differ from DIAG 252/253. TIFF export nodata=0 is not source nodata:
    actual raw zeros are valid source classes; source/export fill is explicit.
    """
    if (not isinstance(bands, np.ndarray) or bands.ndim != 3 or bands.shape[0] != 4
            or bands.dtype.kind not in 'ui' or bands.shape[1]*bands.shape[2] > 14400
            or bands.shape[1]*bands.shape[2] == 0):
        raise ValueError('Require four integer class bands within the preview pixel budget')
    wtr, bwtr, conf, diag = bands
    raw_valid = np.isin(wtr, [0, 1, 3]) & np.isin(bwtr, [0, 1]) & (diag >= 0) & (diag <= 100)
    coherent = ((wtr == 0) & (bwtr == 0) & np.isin(conf, [0, 5, 6, 7, 30, 36, 37])
                | (wtr == 1) & (bwtr == 1) & np.isin(conf, [1, 2, 31, 32])
                | (wtr == 3) & (bwtr == 1) & (conf == 35))
    candidate = raw_valid & coherent
    output = np.full(wtr.shape, 'INSUFFICIENT_OBSERVATION', dtype='<U48')
    output[candidate & (wtr == 0) & np.isin(conf, [0, 30])] = 'SOURCE_NOT_WATER_CANDIDATE'
    output[candidate & (wtr == 1) & np.isin(conf, [1, 31])] = 'SOURCE_OPEN_WATER_HIGH_CONFIDENCE'
    output[candidate & (wtr == 3)] = 'SOURCE_INUNDATED_VEGETATION_UNVERIFIED'
    # Potential vegetation, moderate water and ancillary/bimodality exclusions
    # cannot establish adequate absence in this unvalidated local pilot.
    counts = dict(sorted(Counter(output.flat).items()))
    histograms = []
    for layer in bands:
        values, frequencies = np.unique(layer, return_counts=True)
        histograms.append({str(int(v)): int(n) for v, n in zip(values, frequencies)})
    return {'pixels': int(wtr.size), 'raw_class_histograms': dict(zip(BANDS, histograms)),
            'source_quality_counts': counts, 'coherent_nonfill_source_pixels': int(candidate.sum()),
            'contradictory_or_invalid_source_pixels': int((~candidate).sum()),
            'outcome_evidence_partition': {
                'OBSERVED_TEMPORARY_INUNDATION': 0, 'ADEQUATELY_OBSERVED_ABSENCE': 0,
                'PERMANENT_WATER': 0, 'INSUFFICIENT_OBSERVATION': counts.get('INSUFFICIENT_OBSERVATION', 0),
                'UNKNOWN': int(wtr.size)-counts.get('INSUFFICIENT_OBSERVATION', 0)},
            'permanence_status': 'UNKNOWN_NO_CONTEMPORANEOUS_VALIDATED_BASELINE',
            'classification_status': 'SOURCE_CLASS_QC_ONLY_NOT_INDEPENDENT_LABEL_CERTIFICATION'}


def read_preview(path):
    with rasterio.open(path) as ds:
        if (ds.count != 4 or ds.width != 100 or ds.height != 100 or str(ds.crs) != 'EPSG:32643'
                or ds.transform != Affine(30, 0, 471150, 0, -30, 1476450)
                or any(d != 'uint8' for d in ds.dtypes)):
            raise ValueError('Unexpected raster schema/grid; cannot resample or expand acquisition')
        # Explicit documented source codes; the returned TIFF tags nodata=0 even
        # though zero is a valid WTR/BWTR/CONF/DIAG class. Preserve original bytes.
        result = classify_source_pixels(ds.read(masked=False))
        result['export_nodata_tag'] = ds.nodata
        result['export_nodata_handling'] = 'Raw codes; source/export fill=255 and DIAG=120 are insufficient; zero is a valid class'
        return result


def sensing_interval(start, end):
    start, end = (dt.datetime.fromisoformat(v.replace('Z', '+00:00')) for v in (start, end))
    if start.tzinfo is None or end.tzinfo is None or end < start or end-start > dt.timedelta(minutes=5):
        raise ValueError('Missing timezone or non-acquisition interval; daily/composite metadata is not sensing time')
    return start, end


def geographic_metadata_check(umm_extent, platform_properties):
    rectangle = umm_extent['HorizontalSpatialDomain']['Geometry']['BoundingRectangles']
    if len(rectangle) != 1:
        raise ValueError('Unreviewed original footprint schema')
    box = rectangle[0]
    original = [box[k] for k in ('WestBoundingCoordinate','SouthBoundingCoordinate',
                                 'EastBoundingCoordinate','NorthBoundingCoordinate')]
    footprint = platform_properties['system:footprint']
    if footprint['type'] != 'LinearRing':
        raise ValueError('Unreviewed platform footprint schema')
    coordinates = footprint['coordinates']
    platform = [min(x[0] for x in coordinates),min(x[1] for x in coordinates),
                max(x[0] for x in coordinates),max(x[1] for x in coordinates)]
    if not all(np.isfinite(v) for v in original+platform):
        raise ValueError('Nonfinite geographic metadata')
    difference = [abs(a-b) for a,b in zip(original,platform)]
    return {'publisher_bbox_wgs84':original, 'platform_footprint_bbox_wgs84':platform,
            'absolute_bbox_edge_differences_degrees':difference,
            'status':'GEOGRAPHIC_METADATA_DISAGREEMENT_NATIVE_GEOREFERENCING_REQUIRES_VERIFICATION'
                     if max(difference) > 0.00001 else 'BBOX_AGREEMENT_NOT_PIXEL_ACCURACY_CERTIFICATION',
            'spatial_accuracy_verified':False, 'coordinates_shifted_or_repaired':False}


def product_records(root):
    products = []
    for index in range(2):
        entry = load(root, f'{RAW}/opera-dec2024-umm-{index}.json')['items'][0]
        umm = entry['umm']
        attrs = {x['Name']: x['Values'] for x in umm.get('AdditionalAttributes', [])}
        files = umm['DataGranule']['ArchiveAndDistributionInformation']
        products.append({'source': 'NASA_OPERA_DSWX_S1', 'native_product_id': umm['GranuleUR'],
                         'concept_id': entry['meta']['concept-id'], 'version': '1.0',
                         'software_version': attrs.get('SoftwareVersion'),
                         'sensing_interval': umm['TemporalExtent']['RangeDateTime'],
                         'native_footprint': umm['SpatialExtent'],
                         'publisher_package_bytes': sum(x['SizeInBytes'] for x in files),
                         'native_class_files': [x for x in files if '_B0' in x['Name'] and x['Name'].endswith('.tif')],
                         'input_rtc_files': umm.get('InputGranules', []),
                         'cmr_revision': entry['meta'], 'pixel_spacing_m': 30,
                         'preview_source_id': IDS[index], 'rights': 'NASA EOSDIS unrestricted use with attribution',
                         'correction_status': 'Outside known May-November2025 issue; no local accuracy certification',
                         'role': 'SURFACE_WATER_CLASSIFICATION_NOT_TEMPORARY_FLOOD_TRUTH'})
    for x in load(root, f'{RAW}/opera-2025-current.json')['feed']['entry']:
        products.append({'source': 'NASA_OPERA_DSWX_S1', 'native_product_id': x['title'],
                         'concept_id': x['id'], 'sensing_start': x['time_start'], 'sensing_end': x['time_end'],
                         'catalogue_size_mb_binary_convention': x['granule_size'], 'native_bbox': x.get('boxes'),
                         'updated': x['updated'], 'pixel_spacing_m': 30, 'version': '1.0',
                         'correction_status': 'QUARANTINED_AFFECTED_PERIOD_REPLACEMENT_NOT_VERIFIED',
                         'role': 'METADATA_ONLY_NO_NATIVE_ACQUISITION'})
    for x in load(root, f'{RAW}/sentinel1-native-catalogue.json')['value']:
        attrs = {a['Name']: a['Value'] for a in x['Attributes']}
        products.append({'source': 'COPERNICUS_SENTINEL1_GRD', 'native_product_id': x['Name'],
                         'catalogue_id': x['Id'], 'publisher_package_bytes': x['ContentLength'],
                         'publisher_checksums_not_download_verified': x.get('Checksum', []),
                         'catalogue_publication_time': x.get('PublicationDate'),
                         'catalogue_modification_time': x.get('ModificationDate'),
                         'sensing_start': x['ContentDate']['Start'], 'sensing_end': x['ContentDate']['End'],
                         'native_footprint': x['GeoFootprint'], 'pixel_spacing_m': 10,
                         'nominal_resolution_m': [20, 22], 'relative_orbit': attrs['relativeOrbitNumber'],
                         'processing_version': 'UNKNOWN_REQUIRES_NATIVE_SAFE_ANNOTATIONS',
                         'rights': 'Copernicus free full open data; acknowledge source',
                         'role': 'CONTINUOUS_BACKSCATTER_NOT_FLOOD_CLASSIFICATION'})
    for year in (2005, 2009):
        for x in load(root, f'{RAW}/modis-{year}-metadata.json')['feed']['entry']:
            products.append({'source': 'NASA_MODIS_MOD09GQ', 'native_product_id': x['title'],
                             'concept_id': x['id'], 'catalogue_time_start': x['time_start'],
                             'catalogue_time_end': x['time_end'], 'catalogue_size_mb': x['granule_size'],
                             'native_footprint': x.get('polygons'), 'pixel_spacing_m': 250,
                             'version': '061', 'actual_sensing_interval': 'UNKNOWN_DAILY_PRODUCT_METADATA',
                             'rights': 'NASA unrestricted use with attribution',
                             'role': 'DAILY_SURFACE_REFLECTANCE_NOT_GFD_ORIGINAL_V006_OR_FLOOD_MASK'})
    return products


def compute(root=ROOT):
    metadata_audit = validate_receipts(root/RAW)
    source_receipts = [json.loads(p.read_text()) for p in sorted((root/RAW).glob('*.receipt.json'))]
    source_receipts.append({'source':'EARTH_ENGINE_ASSET_METADATA',
                            'dataset_reference':'https://developers.google.com/earth-engine/datasets/catalog/OPERA_DSWX_L3_V1_S1',
                            'status':load(root,f'{RAW}/ee-opera-dec2024-metadata.json')['status'],
                            'started_at':load(root,f'{RAW}/ee-opera-dec2024-metadata.json')['started_at'],
                            **fingerprint(root/f'{RAW}/ee-opera-dec2024-metadata.json')})
    source_receipts += [load(root,f'{RAW}/previews/opera-{i}.receipt.json') for i in range(2)]
    plan = load(root, 'data/recovery/phase12e_v1/bounded_preview_plan.json')
    metadata = load(root, f'{RAW}/ee-opera-dec2024-metadata.json')
    validate_plan(plan, metadata)
    products = product_records(root)
    observations, contracts = [], []
    for index in range(2):
        product = products[index]
        relative = f'{RAW}/previews/opera-{index}.tif'
        receipt = load(root, f'{RAW}/previews/opera-{index}.receipt.json')
        if (receipt['status'] != 'RETRIEVED' or receipt['source_id'] != IDS[index]
                or fingerprint(root/relative) != {'bytes': receipt['bytes'], 'sha256': receipt['sha256']}
                or receipt['bytes'] > plan['byte_ceiling_per_download']):
            raise ValueError('Preview acquisition receipt or checksum mismatch')
        if receipt['plan_sha256'] != fingerprint(root/'data/recovery/phase12e_v1/bounded_preview_plan.json')['sha256']:
            raise ValueError('Preview plan binding differs')
        if receipt['metadata_sha256'] != fingerprint(root/f'{RAW}/ee-opera-dec2024-metadata.json')['sha256']:
            raise ValueError('Preview metadata binding differs')
        interval = product['sensing_interval']
        start, end = sensing_interval(interval['BeginningDateTime'], interval['EndingDateTime'])
        if product['native_product_id'] != 'OPERA_L3_DSWx-S1_'+IDS[index].split('/')[-1]+'_30_v1.0':
            raise ValueError('Platform subset does not match original product identity')
        quality = read_preview(root/relative)
        geography = geographic_metadata_check(product['native_footprint'], metadata['images']['features'][index]['properties'])
        observations.append({'observation_id': f'opera-udupi-preview-{index}',
                             'native_product_id': product['native_product_id'],
                             'source_reference': relative, 'source_sha256': receipt['sha256'],
                             'sensing_start': start.isoformat(), 'sensing_end': end.isoformat(),
                             'platform_nominal_time_ms': metadata['images']['features'][index]['properties']['system:time_start'],
                             'native_interval_source': f'{RAW}/opera-dec2024-umm-{index}.json',
                             'geographic_unit': 'Existing public Udupi 3km window, not a district polygon',
                             'quality': quality, 'geographic_quality':geography,
                             'scientifically_verified_temporary_flood_pixels': 0,
                             'scientifically_verified_nonflood_pixels': 0, 'permanent_water_verified_pixels': 0,
                             'future_predictive_labels': 0})
        # No acquired source class has independently validated permanence and
        # flood quality. The existing scientific evidence contract stays UNKNOWN.
        contracts.append({'observation_id': f'opera-udupi-preview-{index}',
                          'target': 'ACQUISITION_TEMPORARY_INUNDATION',
                          'spatial_unit_id': 'udupi-public-3km-window',
                          'geometry_reference': 'data/processed/udupi_drainage_gis_v1/study_area.geojson',
                          'source_reference': relative, 'source_sha256': receipt['sha256'],
                          'event_group': 'UNKNOWN_NO_VERIFIED_FLOOD_EVENT', 'source_group': product['native_product_id'],
                          'review_group': 'phase12e-source-class-screen', 'unit_pixels': 10000,
                          'valid_pixels': 0, 'temporary_water_pixels': 0, 'permanent_water_pixels': 0,
                          'dry_pixels': 0, 'unknown_pixels': 10000, 'acquisition_time': start.isoformat(),
                          'acquisition_end': end.isoformat(), 'source_type': 'OBSERVED',
                          'product_role': 'ACQUISITION_CLASSIFICATION'})
    contract_audit = audit_contracts(contracts, root)
    if any(r['problems'] for r in contract_audit['results']):
        raise ValueError('Actual observation records violate consistency contract')
    hydro = load(root, 'data/working/karnataka_external_hydrology_closure_v1/summary.json')
    glofas = load(root, 'data/working/karnataka_glofas_2019_pilot_v1/manifest.json')['summary']
    stations = {}
    with (root/'data/working/karnataka_hydrology_2019_reconciled_v1/observation_quality.csv').open() as f:
        for row in csv.DictReader(f):
            key = row['canonical_cwc_station_id']
            station = stations.setdefault(key, {'source_rows': {}, 'caveated_daily_discharge_rows': 0, 'observation_times': []})
            station['source_rows'][row['variable']] = station['source_rows'].get(row['variable'], 0)+1
            station['observation_times'].append(row['observation_time'])
            station['caveated_daily_discharge_rows'] += row['analysis_eligibility'].startswith('eligible')
    for station in stations.values():
        times = station.pop('observation_times')
        station.update(first_source_date=min(times)[:10], last_source_date=max(times)[:10],
                       timezone='UNKNOWN', level_datum='UNKNOWN', compatible_flood_threshold='NONE_VERIFIED',
                       forecast_validation_status='NO_GO')
    hydro_review = {'retained_closure_counts': hydro, 'station_coverage': stations,
                   'retained_glofas_counts': glofas, 'measured_glofas_rows': 0,
                   'independently_validated_discharge_flood_thresholds': 0,
                   'threshold_exceedance_labels': 0, 'complete_forecast_outcome_joins': 0,
                   'current_catalogue': {'historical_overview': 'v5.0 operational released2026-07-15',
                                         'reforecast_overview': 'v4.0;2003-2022 referenceyears;00UTC Mon/Thu;24hmeans',
                                         'version_parity': 'UNRESOLVED_NOT_INTERCHANGEABLE'}}
    partition = Counter()
    for obs in observations:
        partition.update(obs['quality']['outcome_evidence_partition'])
    target = load(root, f'{PUBLIC}/candidate_target_protocol.json')
    if (target['training_authorized'] is not False or target['deployment_authorized'] is not False
            or target['review_status'] != 'PROPOSED_REQUIRES_INDEPENDENT_SCIENTIFIC_REVIEW'):
        raise ValueError('No independent scientific approval was acquired in this phase')
    report = {'phase': '12E', 'training_decision': 'NO_GO', 'models_trained': 0,
              'metadata_acquisition': metadata_audit,
              'proposed_target_id': target['protocol_id'], 'target_review_status': target['review_status'],
              'native_metadata_product_ids': len(products), 'bounded_previews_acquired': len(observations),
              'preview_bytes': sum((root/f'{RAW}/previews/opera-{i}.tif').stat().st_size for i in range(2)),
              'observation_pixel_contexts': 20000, 'source_nonfill_acquisitions': sum(o['quality']['coherent_nonfill_source_pixels'] > 0 for o in observations),
              'native_geographic_accuracy_verified_acquisitions':0,
              'publisher_platform_footprint_disagreements':sum(o['geographic_quality']['status'].startswith('GEOGRAPHIC_METADATA_DISAGREEMENT') for o in observations),
              'source_open_water_high_confidence_pixels': sum(o['quality']['source_quality_counts'].get('SOURCE_OPEN_WATER_HIGH_CONFIDENCE', 0) for o in observations),
              'source_inundated_vegetation_pixels': sum(o['quality']['source_quality_counts'].get('SOURCE_INUNDATED_VEGETATION_UNVERIFIED', 0) for o in observations),
              'outcome_evidence_partition': dict(partition), 'eligible_positive_labels': 0,
              'defensible_negative_labels': 0, 'independent_eligible_flood_events': 0,
              'verified_future_predictive_observations': contract_audit['forecast_eligible'],
              'complete_issue_time_feature_joins': 0, 'negative_24hour_intervals_verified': 0,
              'district_coverage': {'Udupi_public_research_window': {'acquisitions': 2, 'nonfill_acquisitions': 1, 'eligible_labels': 0},
                                    'Belagavi_native_scene_metadata': {'scenes': 3, 'new_native_rasters': 0, 'eligible_labels': 0}},
              'observation_year_coverage': {'2024': {'previews': 2, 'eligible_labels': 0}},
              'blockers': ['No contemporary independently reviewed permanent-water baseline',
                           'Publisher catalogue bounds differ from platform footprints; original GeoTIFF georeferencing not verified',
                           'No local class/detection-limit validation, especially inundated vegetation',
                           'Second acquisition is entirely no-data; source footprint is not valid coverage',
                           '2500m2 threshold is not supported by OPERA documented >3ha/200m open-water domain',
                           'Discrete acquisitions cannot certify complete next24hour absence',
                           'No pre-issued acquisition schedule or historical feature availability receipts',
                           'No independently approved target or independent event/time/geography evaluation set',
                           'CWC time/datum/QC/threshold/coordinate and reuse gaps;14caveated rows are not labels',
                           'GloFAS modelled dailymean/reforecast version parity is unresolved']}
    return {'native_product_register.json': products, 'observation_quality.json': observations,
            'observation_contracts.json': contracts, 'observation_contract_audit.json': contract_audit,
            'riverine_readiness.json': hydro_review, 'source_receipts.json': source_receipts, 'report.json': report}


def input_paths(root):
    paths = [p.relative_to(root).as_posix() for p in (root/RAW).rglob('*') if p.is_file()]
    paths += ['data/recovery/phase12e_v1/bounded_preview_plan.json',
              'data/recovery/phase12e_v1/acquisition_plan_initial.json',
              'data/processed/udupi_drainage_gis_v1/study_area.geojson',
              'data/working/karnataka_external_hydrology_closure_v1/summary.json',
              'data/working/karnataka_glofas_2019_pilot_v1/manifest.json',
              'data/working/karnataka_hydrology_2019_reconciled_v1/observation_quality.csv',
              'data/recovery/phase12b_v1/opera-product-page.html',
              f'{PUBLIC}/candidate_target_protocol.json']
    paths += ['scripts/'+n for n in ('audit_direct_flood_observations.py', 'acquire_direct_observation_metadata.py',
                                     'acquire_opera_bounded_preview.py', 'audit_satellite_observations.py')]
    return sorted(paths)


def build(root=ROOT):
    output = root/OUTPUT
    if output.exists():
        raise ValueError('Version exists; validate or create a separately reviewed new version')
    result = compute(root)
    output.mkdir(parents=True)
    for name, value in result.items():
        (output/name).write_bytes(encoded(value))
    manifest = {'version': 'direct_flood_observations_phase12e_v1',
                'inputs': {p: fingerprint(root/p) for p in input_paths(root)},
                'outputs': {n: fingerprint(output/n) for n in result},
                'publication_policy': 'Only aggregate report and independently open native product metadata; no rasters or restricted geometry'}
    (output/'manifest.json').write_bytes(encoded(manifest))
    return result['report.json']


def validate(root=ROOT, public=None):
    output = root/OUTPUT
    manifest = load(root, f'{OUTPUT}/manifest.json')
    for p, expected in manifest['inputs'].items():
        if fingerprint(root/p) != expected:
            raise ValueError('Input/code checksum changed: '+p)
    for name, expected in manifest['outputs'].items():
        if fingerprint(output/name) != expected:
            raise ValueError('Output checksum changed: '+name)
    replay = compute(root)
    for name, value in replay.items():
        if (output/name).read_bytes() != encoded(value):
            raise ValueError('Deterministic read-only reproduction differs: '+name)
    if public:
        for name in ('report.json', 'native_product_register.json', 'riverine_readiness.json', 'source_receipts.json'):
            if (public/name).read_bytes() != (output/name).read_bytes():
                raise ValueError('Public permitted metadata differs: '+name)
    return replay['report.json']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'validate'))
    parser.add_argument('--public', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build() if args.command == 'build' else validate(public=args.public), indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, 'Direct observation audit failed: '+str(error)+'\n')
