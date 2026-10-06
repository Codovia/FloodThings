#!/usr/bin/env python3
"""JRC-only diagnostics on retained Stage 3E SAR grids. No flood calculation.

The historical pilot evaluator remains available only for archive validation.
This module is the replacement interface for independent SAR/JRC validity.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_sentinel1_pilot as pilot

GLOBAL = 'JRC/GSW1_4/GlobalSurfaceWater'
MONTHLY = 'JRC/GSW1_4/MonthlyHistory'
YEARLY = 'JRC/GSW1_4/YearlyHistory'
RAW = pilot.ROOT/'data/raw/jrc/stage3e2_v1'
OUTPUT = pilot.ROOT/'data/working/karnataka_jrc_auxiliary_v1'
PRIOR = pilot.ROOT/'data/working/karnataka_sentinel1_flood_pilot_v2'
CORROBORATION = frozenset({'exact_date_and_spatial_scope','date_supported_spatially_broad',
                          'year_event_supported_only','unresolved'})
SUITABILITY = frozenset({'calibration_candidate_supported','calibration_candidate_temporally_weak',
                        'calibration_candidate_spatially_weak','calibration_candidate_unresolved'})


def temporal_asset(collection, returned_id):
    """EE may return a basename. Retain it separately; never invent an index."""
    pilot.require(collection in {MONTHLY, YEARLY}, 'Unexpected JRC temporal collection')
    name = returned_id.rsplit('/', 1)[-1]
    import re
    pattern = r'\d{4}_\d{2}' if collection == MONTHLY else r'\d{4}'
    pilot.require(bool(re.fullmatch(pattern, name)), 'Malformed temporal asset identifier')
    if collection == MONTHLY:
        pilot.require(1 <= int(name[-2:]) <= 12, 'Invalid source month')
    pilot.require('/' not in returned_id or returned_id == collection+'/'+name, 'Wrong asset collection')
    return collection+'/'+name


def source_assets(metadata, year, months):
    pilot.require(metadata['year_count'] == 1 and metadata['year']['year'] == year, 'Yearly source date mismatch')
    yearly = temporal_asset(YEARLY, metadata['year_id'])
    pilot.require(yearly == YEARLY+'/'+str(year), 'Yearly source ID mismatch')
    assets = {}
    pilot.require(set(metadata['months']) == {str(m) for m in months}, 'Monthly source coverage mismatch')
    for month in months:
        row = metadata['months'][str(month)]
        pilot.require(row['count'] == 1 and row['properties'] == {'year':year,'month':month}, 'Monthly source date mismatch')
        asset = temporal_asset(MONTHLY,row['id'])
        pilot.require(asset == f'{MONTHLY}/{year}_{month:02}', 'Monthly source ID mismatch')
        assets[str(month)] = asset
    return {'global':GLOBAL,'yearly':yearly,'monthly':assets}


def sar_validity(values, names, scope):
    """Original SAR masks/nodata and local geometry only; no auxiliary gates."""
    pilot.require(values.shape[0] == len(names) and values.shape[1:] == scope.shape, 'SAR layout mismatch')
    selected = [i for i, n in enumerate(names) if n.startswith('s') and n.rsplit('_', 1)[-1] in {'VV','VH','angle'}]
    pilot.require(len(selected) >= 6 and len(selected) % 3 == 0, 'Incomplete SAR pair')
    return scope & np.all(np.isfinite(values[selected]) & (values[selected] != pilot.NODATA), axis=0)


def classification(values, masks, maximum):
    """Preserve masked (-1) versus explicit class-0 no data; no dry imputation."""
    pilot.require(values.shape == masks.shape, 'JRC mask layout mismatch')
    pilot.require(np.isfinite(masks).all() and ((masks >= 0) & (masks <= 1)).all(), 'Invalid JRC mask')
    present = masks > 0
    v = values[present]
    pilot.require(np.isfinite(v).all() and ((v >= 0) & (v <= maximum) & (v == np.floor(v))).all(), 'Invalid JRC class')
    return np.where(present, values, -1).astype('int8')


def auxiliary_flags(month, month_mask, year, year_mask):
    monthly = classification(month, month_mask, 2)
    yearly = classification(year, year_mask, 3)
    pilot.require(monthly.shape == yearly.shape, 'Temporal grid mismatch')
    return {'jrc_monthly_state': monthly, 'jrc_yearly_water_class': yearly,
            'jrc_monthly_data_available': monthly > 0, 'jrc_yearly_data_available': yearly > 0,
            'jrc_permanent_water': yearly == 3,
            'jrc_permanent_water_status_known': yearly > 0,
            'jrc_aux_data_available': (monthly > 0) | (yearly > 0)}


def permanent_water_exclusion(sar_valid, flags):
    # False exclusion for unknown is not an assertion that the pixel is dry.
    return sar_valid & flags['jrc_permanent_water']


def global_band_diagnostic(values, masks, sar_valid):
    pilot.require(values.shape == masks.shape == sar_valid.shape, 'Global grid mismatch')
    pilot.require(np.isfinite(masks).all() and ((masks >= 0) & (masks <= 1)).all(), 'Invalid GlobalSurfaceWater mask')
    present = (masks > 0) & np.isfinite(values) & (values != pilot.NODATA)
    def count(a): return int(np.count_nonzero(a))
    overlap = present & sar_valid
    return {'unmasked_cells': count(present), 'masked_cells': count(~present),
            'sar_valid_intersection_cells': count(overlap),
            'sar_valid_masked_cells': count(sar_valid & ~present),
            'fractional_mask_cells': count((masks > 0) & (masks < 1)),
            'original_mask_range': [float(masks.min()), float(masks.max())],
            'value_range_on_unmasked_sar_cells': [float(values[overlap].min()), float(values[overlap].max())] if overlap.any() else None,
            'use': 'water-history context only; mask is neither SAR validity nor general observation availability'}


def diagnostics(sar_values, sar_names, scope, jrc, event_month):
    valid = sar_validity(sar_values, sar_names, scope)
    def count(a): return int(np.count_nonzero(valid & a))
    global_counts = {b: global_band_diagnostic(jrc[b], jrc[b+'_mask'], valid)
                     for b in ['occurrence','seasonality','max_extent']}
    year = classification(jrc['yearly'], jrc['yearly_mask'], 3)
    months = {}
    for name in sorted(n for n in jrc if n.startswith('month_') and not n.endswith('_mask')):
        c = classification(jrc[name], jrc[name+'_mask'], 2)
        months[name] = {'masked_cells': count(c == -1), 'no_data_class_0_cells': count(c == 0),
                        'not_water_class_1_cells': count(c == 1), 'water_class_2_cells': count(c == 2),
                        'data_available_cells': count(c > 0), 'resolution': 'monthly context, not event-day verification'}
    flags = auxiliary_flags(jrc[event_month], jrc[event_month+'_mask'], jrc['yearly'], jrc['yearly_mask'])
    return {'scope_cells': int(scope.sum()), 'sar_valid_cells': int(valid.sum()),
            'global': global_counts, 'monthly': months,
            'yearly': {'masked_cells': count(year == -1), 'no_data_class_0_cells': count(year == 0),
                       'not_water_class_1_cells': count(year == 1), 'seasonal_water_class_2_cells': count(year == 2),
                       'permanent_water_class_3_cells': count(year == 3), 'data_available_cells': count(year > 0)},
            'legacy_occurrence_seasonality_intersection_cells': count((jrc['occurrence_mask'] > 0) & (jrc['seasonality_mask'] > 0)),
            'cells_without_event_month_or_year_auxiliary_information': count(~flags['jrc_aux_data_available']),
            'permanent_water_excluded_cells': int(permanent_water_exclusion(valid, flags).sum()),
            'permanent_water_status_unknown_cells': count(~flags['jrc_permanent_water_status_known']),
            'interpretation': 'Counts of 10 m SAR-grid cells with nearest 30 m JRC context; not independent 30 m sample counts or flood labels'}


def suitability(corroboration, acquisition_usable):
    pilot.require(corroboration in CORROBORATION, 'Unknown corroboration vocabulary')
    if corroboration == 'year_event_supported_only': return 'calibration_candidate_temporally_weak'
    if corroboration == 'date_supported_spatially_broad': return 'calibration_candidate_spatially_weak'
    if corroboration == 'exact_date_and_spatial_scope' and acquisition_usable:
        return 'calibration_candidate_supported'
    return 'calibration_candidate_unresolved'


def preserve_status(prior, method_status):
    pilot.require(method_status in SUITABILITY, 'Unknown suitability vocabulary')
    pilot.validate_result(prior)
    # A diagnostic or independent report cannot automatically promote evidence.
    return deepcopy(prior)


def bhuvan_inventory(html):
    """Parse retained public catalogue HTML only; do not contact WMS services."""
    import html as markup
    import re
    layers = {}
    for element in re.finditer(r'<input\b[^>]*>[^<]*',html):
        item = element.group()
        call = re.search(r'loadfloodmap\("([^"]+)","(https://[^"]+)","([^"]+)"\)',item)
        if call and call[3].startswith(('ka_2018_','ka_2019_')):
            label = markup.unescape(item.split('>',1)[1]).strip()
            row = {'portal_layer_id':call[1],'wms_url':call[2],'source_layer_id':call[3],
                   'original_date_label':label,'access_status':'public_catalogue_only_layer_data_not_requested',
                   'district_intersection':'not_verified'}
            pilot.require(call[3] not in layers or layers[call[3]] == row, 'Conflicting public inventory entry')
            layers[call[3]] = row
    return {'dated_karnataka_products':list(layers.values()),
            'karnataka_2018_dated_entry_found':any(k.startswith('ka_2018_') for k in layers),
            'aggregated_2003_2020_karnataka_entry_found': 'State Level Aggregated Flood Maps (2003-2020)' in html and 'agg_karnataka' in html,
            'interpretation':'Only the inspected portal inventory; no assertion that absent catalogue items or districts lack inundation'}


def raster_counts(raw=RAW, prior=PRIOR):
    records = pilot.read(prior/'evidence.json'); results = []
    metadata = pilot.read(prior/'scene_inventory.json')
    for record in records:
        if 'sensitivity' not in record['result']: continue
        eid = record['event']['ifi_source_event_id']; folder = raw/eid
        plan = pilot.read(folder/'plan.json'); sar_plan = record['plan']
        year = int(record['event']['start'][:4])
        source_assets(pilot.read(folder/'source_metadata.json'),year,[5,6] if year == 2018 else [1])
        pilot.require(plan['partitions'] == sar_plan['partitions'] and plan['crs'] == pilot.CRS, 'JRC not on retained SAR grid')
        s = np.empty((len(record['bands']),200,200), dtype='float32')
        a = np.empty((len(plan['names']),200,200), dtype='float32')
        for tile, part in zip(record['tiles'], sar_plan['partitions']):
            pilot.require(tile['download'] == pilot.source.fingerprint(pilot.ROOT/tile['file']), 'Protected SAR tile changed')
            x0,x1,y0,y1 = part['window']; s[:,y0:y1,x0:x1] = pilot.read_tile(pilot.ROOT/tile['file'],part,record['bands'])
            p = folder/f"tile{part['index']}.tif"; info = pilot.read(p.with_suffix('.json'))
            pilot.require(info['download']['sha256'] == pilot.source.fingerprint(p)['sha256'] and info['download']['bytes'] == p.stat().st_size, 'JRC raw checksum mismatch')
            a[:,y0:y1,x0:x1] = pilot.read_tile(p,part,plan['names'])
        geometry = next(r['public_geometry'] for r in metadata['events'] if r['event'] == record['event'])
        scope = pilot.scope_mask(geometry,sar_plan); month = 'month_'+str(int(record['event']['start'][5:7]))
        results.append({'event_id':eid,'source_district':record['event']['source_districts'],
                        'event_start':record['event']['start'],'event_end_inclusive':record['event']['end_inclusive'],
                        'retained_evidence_status':record['result']['status'],
                        'counts':diagnostics(s,record['bands'],scope,dict(zip(plan['names'],a)),month)})
    return results


def validate(output=OUTPUT):
    m = pilot.read(output/'manifest.json')
    for rel, expected in m['inputs'].items():
        pilot.require(pilot.source.fingerprint(pilot.ROOT/rel) == expected, 'JRC input checksum mismatch')
    for rel, expected in m['files'].items():
        pilot.require(pilot.source.fingerprint(output/rel) == expected, 'JRC output checksum mismatch')
    pilot.require(pilot.source.fingerprint(Path(__file__)) == m['code'], 'JRC processing code changed')
    pilot.require(raster_counts() == pilot.read(output/'diagnostics.json'), 'JRC counts not reproducible')
    inventory_source = pilot.ROOT/m['bhuvan_inventory_source']
    pilot.require(bhuvan_inventory(inventory_source.read_text()) == pilot.read(output/'bhuvan_inventory.json'), 'Public catalogue not reproducible')
    for c in pilot.read(output/'corroboration.json'):
        pilot.require(suitability(c['corroboration'],c['acquisition_usable']) == c['suitability'], 'Invalid calibration decision')
        pilot.require(c['retained_evidence_status'] == 'sentinel1_ambiguous' and c['flood_calculation_performed'] is False, 'Automatic evidence promotion/rerun forbidden')
    return {'events':2,'raster_diagnostics_reproduced':True,'live_requests':0,'new_flood_calculations':0,'promoted_evidence':0}


def retrieve(raw=RAW, prior=PRIOR):
    """Resume-safe, eight <=1 MiB JRC tiles, 60 s request/900 s total phase."""
    import requests
    raw.mkdir(parents=True,exist_ok=True)
    session = pilot.bounded.TimedEE(raw,60,900); session.initialize(); ee = session.ee
    for r in pilot.read(prior/'evidence.json'):
        if 'sensitivity' not in r['result']: continue
        eid = r['event']['ifi_source_event_id']; year = int(r['event']['start'][:4])
        months = [5,6] if year == 2018 else [1]
        pilot.require((year,months) in [(2018,[5,6]),(2019,[1])], 'Only two retained pilot scopes allowed')
        folder = raw/eid; folder.mkdir(exist_ok=True); cache = folder/'source_metadata.json'
        if cache.exists(): metadata = pilot.read(cache)
        else:
            yc = ee.ImageCollection(YEARLY).filter(ee.Filter.eq('year',year))
            sets = {str(m):ee.ImageCollection(MONTHLY).filter(ee.Filter.eq('year',year)).filter(ee.Filter.eq('month',m)) for m in months}
            metadata = session.request(lambda:ee.Dictionary({'year_count':yc.size(),'year':yc.first().toDictionary(),
                'year_id':yc.first().id(),'year_projection':yc.first().select('waterClass').projection(),
                'months':ee.Dictionary({k:ee.Dictionary({'count':c.size(),'id':c.first().id(),'properties':c.first().toDictionary(),
                    'projection':c.first().select('water').projection()}) for k,c in sets.items()}),
                'global_asset':ee.Image(GLOBAL).toDictionary(),
                'global_projections':ee.Dictionary({b:ee.Image(GLOBAL).select(b).projection() for b in ['occurrence','seasonality','max_extent']})}).getInfo(),f'jrc_source_metadata:{eid}')
            pilot.source.write_new(cache,metadata)
        pilot.require(metadata['year_count']==1 and all(v['count']==1 for v in metadata['months'].values()), 'JRC temporal source unavailable/ambiguous')
        source_assets(metadata,year,months)
        bands=[]; names=[]
        def add(image, band, name):
            value=image.select(band); names.extend([name,name+'_mask'])
            bands.extend([value.unmask(pilot.NODATA,sameFootprint=False).rename(name).toFloat(),
                          value.mask().unmask(0,sameFootprint=False).rename(name+'_mask').toFloat()])
        for b in ['occurrence','seasonality','max_extent']: add(ee.Image(GLOBAL),b,b)
        for m in months: add(ee.Image(temporal_asset(MONTHLY,metadata['months'][str(m)]['id'])),'water',f'month_{m}')
        add(ee.Image(temporal_asset(YEARLY,metadata['year_id'])),'waterClass','yearly')
        image=ee.Image.cat(bands); plan=r['plan']; plan_file=folder/'plan.json'
        if plan_file.exists():
            saved=pilot.read(plan_file); pilot.require(saved['names']==names and saved['partitions']==plan['partitions'], 'Retained JRC plan mismatch')
        else:
            pilot.source.write_new(plan_file,{'names':names,'partitions':plan['partitions'],'crs':pilot.CRS,
                'request_deadline_seconds':60,'phase_total_seconds':900,'original_resolution_m':30,'resampling':'nearest',
                'band_cells_per_partition':10000*len(names),'maxPixels':300000,'bestEffort':False,'reductions':'none; local only'})
        with requests.Session() as http:
            for part in plan['partitions']:
                p=folder/f"tile{part['index']}.tif"; sidecar=p.with_suffix('.json')
                params={'crs':pilot.CRS,'crs_transform':part['crs_transform'],'dimensions':part['dimensions'],'format':'GEO_TIFF','filePerBand':False}
                if sidecar.exists():
                    info=pilot.read(sidecar); fp=pilot.source.fingerprint(p)
                    pilot.require(info['parameters']==params and all(info['download'][k]==fp[k] for k in fp), 'Cached JRC tile changed')
                    pilot.read_tile(p,part,names); continue
                pilot.require(not p.exists(), 'Unjournalled JRC tile: preserve for explicit recovery')
                url=session.request(lambda:pilot.download_url(image,params),f'jrc_download_url:{eid}:{part["index"]}')
                attempt=[0]
                def fetch():
                    attempt[0]+=1
                    return pilot.download.download(http,url,p.with_suffix(f'.attempt{attempt[0]}.partial.tif'))
                info=session.request(fetch,f'jrc_download:{eid}:{part["index"]}')
                p.with_suffix(f'.attempt{attempt[0]}.partial.tif').rename(p); pilot.read_tile(p,part,names)
                pilot.source.write_new(sidecar,{'names':names,'parameters':params,'download':info})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['retrieve','diagnose','validate'])
    args=parser.parse_args()
    if args.operation=='retrieve': retrieve()
    else: print(json.dumps(validate() if args.operation=='validate' else raster_counts(),indent=2))
