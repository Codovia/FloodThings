#!/usr/bin/env python3
"""Two pinned, native-grid Udupi OPERA subsets; no full scenes or credentials written."""
import argparse
import hashlib
import json
from pathlib import Path

from acquire_direct_observation_metadata import ROOT, utcnow

PLAN = ROOT / 'data/recovery/phase12e_v1/bounded_preview_plan.json'
METADATA = ROOT / 'data/raw/direct_flood_observations_phase12e_v1/ee-opera-dec2024-metadata.json'
RAW = ROOT / 'data/raw/direct_flood_observations_phase12e_v1/previews'
BANDS = ['WTR_Water_classification', 'BWTR_Binary_water', 'CONF_Confidence', 'DIAG_diagnostic']
IDS = ['OPERA/DSWX/L3_V1/S1/T43PDQ_20241204T004900Z_20241204T183634Z_S1A',
       'OPERA/DSWX/L3_V1/S1/T43PDQ_20241209T005659Z_20241212T220859Z_S1A']


def validate_plan(plan, metadata):
    if plan.get('large_download_authorized') is not False or plan.get('source_ids') != IDS:
        raise ValueError('Only the two reviewed acquisitions are permitted')
    expected = {'dimensions': [100, 100], 'bands': BANDS, 'native_crs': 'EPSG:32643',
                'window_transform': [30, 0, 471150, 0, -30, 1476450],
                'byte_ceiling_per_download': 2097152, 'total_download_ceiling': 4194304}
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValueError('Plan changed: '+key)
    if metadata.get('status') != 'RETRIEVED':
        raise ValueError('No successful source metadata')
    images = metadata['images']['features']
    if [im['id'] for im in images] != IDS:
        raise ValueError('Metadata identity mismatch')
    for im in images:
        if im['properties']['DSWX_PRODUCT_VERSION'] != '1.0':
            raise ValueError('Unreviewed product version')
        if [b['id'] for b in im['bands']] != BANDS:
            raise ValueError('Unexpected band schema')
        for band in im['bands']:
            if band['crs'] != 'EPSG:32643' or band['crs_transform'] != [30, 0, 399960, 0, -30, 1500000]:
                raise ValueError('Native grid changed; resampling not permitted')
    return images


def fetch():
    plan_bytes, metadata_bytes = PLAN.read_bytes(), METADATA.read_bytes()
    plan, metadata = json.loads(plan_bytes), json.loads(metadata_bytes)
    images = validate_plan(plan, metadata)
    RAW.mkdir(parents=True, exist_ok=True)
    if any(RAW.iterdir()):
        raise ValueError('Existing preview directory is immutable; validate it offline')
    import ee
    from verify_earth_engine import wall_limit
    receipts, total = [], 0
    with wall_limit(100):
        ee.Initialize(project='floodpulse')  # Retained extraction query.project, existing authentication only.
        ee.data.setDeadline(25000)
        ee.data.setMaxRetries(0)
        for index, im in enumerate(images):
            record = {'source_id': im['id'], 'started_at': utcnow(),
                      'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(),
                      'metadata_sha256': hashlib.sha256(metadata_bytes).hexdigest(),
                      'derivative': 'Earth Engine native-grid subset, not untouched PO.DAAC granule',
                      'grid': {'dimensions': {'width': 100, 'height': 100},
                               'affineTransform': {'scaleX': 30, 'shearX': 0, 'translateX': 471150,
                                                   'shearY': 0, 'scaleY': -30, 'translateY': 1476450},
                               'crsCode': 'EPSG:32643'}, 'bands': BANDS,
                      'nodata_export_code': 255, 'source_product_version': '1.0',
                      'byte_ceiling': plan['byte_ceiling_per_download']}
            try:
                # Explicit 100x100 grid bounds both computation and returned raster memory.
                body = ee.data.computePixels({'expression': ee.Image(im['id']).select(BANDS).unmask(255),
                                              'fileFormat': 'GEO_TIFF', 'grid': record['grid']})
                total += len(body)
                if len(body) > record['byte_ceiling'] or total > plan['total_download_ceiling']:
                    raise ValueError('Preview response budget exceeded')
                path = RAW / f'opera-{index}.tif'
                path.write_bytes(body)
                record.update(status='RETRIEVED', filename=path.name, bytes=len(body),
                              sha256=hashlib.sha256(body).hexdigest())
            except Exception as error:
                record.update(status='UNAVAILABLE', error_type=type(error).__name__, bytes=0)
            record['finished_at'] = utcnow()
            receipts.append(record)
            (RAW/f'opera-{index}.receipt.json').write_text(json.dumps(record, indent=2)+'\n')
            print(json.dumps({k:record[k] for k in ('source_id','status','bytes')}), flush=True)
    return receipts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'fetch'))
    args = parser.parse_args()
    if args.command == 'plan':
        plan = json.loads(PLAN.read_text())
        validate_plan(plan, json.loads(METADATA.read_text()))
        print(json.dumps(plan, indent=2))
    else:
        fetch()
