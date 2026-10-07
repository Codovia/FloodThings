#!/usr/bin/env python3
"""Stage 4C: immutable, offline reconciliation; never select or rewrite source values.

build creates a new local version; validate reproduces it read-only. Detailed
Year Book, coordinate and observation products stay outside Git. No features.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('stage4b', Path(__file__).with_name('recover_karnataka_hydrology.py'))
b = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(b)
PILOT = ROOT / 'data/working/karnataka_hydrology_2019_pilot_v1'
FOUNDATION = ROOT / 'data/working/karnataka_hydrology_stations_v1'
RAW = ROOT / 'data/raw/reference/stage4b_v1'
POLICY = ROOT / 'data/raw/reference/stage4c_v1'
OUTPUT = ROOT / 'data/working/karnataka_hydrology_2019_reconciled_v1'
PUBLIC = ROOT / 'data/reference/karnataka_hydrology_2019_reconciled_v1'
DATUM = {'datum_compatible', 'datum_probably_compatible_but_unverified', 'datum_incompatible', 'datum_unresolved'}
IDENTITY = {'identity_verified', 'identity_strongly_supported', 'identity_ambiguous', 'identity_conflict'}
ELIGIBILITY = {'eligible_measured_observation', 'eligible_with_quality_caveat', 'retain_not_use_for_features', 'unresolved'}
RULES = {
    'comparison_difference': 'NWDP minus Year Book; relative difference divides by absolute Year Book value; null for missing or zero denominator',
    'comparison': 'Independently parse original CSV and PDF text-layout; preserve prior classification alongside new evidence categories',
    'markers': '* computed; # discarded/changed by rating curve; unmarked Q is observed/estimated with no explicit cell status, never assumed directly measured',
    'computed_conflict': 'A computed marker describes the book cell; it does not establish why sources differ or resolve the conflict',
    'rounding': 'Book section1.5.1(iv): integer above1000, one decimal100-999, two10-99, three below10. Half-up used for comparison; boundary1000 or tie cases are not certified rounding-equivalent',
    'preference': 'All preferred_for_analysis/preference_basis null; no authoritative source priority rule found',
    'identity': 'No current CWC ID in NWDP. Explicit names, agency, basin/river, state/district and independent official gauge opening support identity, not direct ID equality',
    'coordinates': 'Haversine, sphere radius6371008.8m. Assumed geographic lat/lon for approximate screening only; original coordinate datum/accuracy unknown. No averaging or relocation',
    'river_proximity': 'Unknown: no authoritative georeferenced river geometry was verified for point-to-river distances. Source river association is documentary, not spatial validation',
    'datum': 'Book section1.4.1 identifies MSL elevation and table WL corresponding mean. Portal metre units and auxiliary RL/MeanSeaLevel fields do not document measured-field datum. No magnitude inference or automatic offset',
    'thresholds': 'No exceedances: portal datum unresolved, SOP datum unstated and 2025 threshold applicability to2019 unverified',
    'eligibility': 'Only nonconflicting NWDP daily discharge corroborated by unmarked book cells eligible with caveat. Computed/discarded/conflicting discharge and unresolved-datum hourly levels retained but excluded from features',
    'cadence': 'Nominal hourly resource does not document a strict24-per-day schedule or timezone. Actual counts only; expected counts and fractions null, including missing days',
    'availability': 'availability_semantics_unverified; retrieval separate from acquisition; no historical latency assumption',
    'publication': 'Keep conservative detailed-data handling. Other(Open) not a standard licence; no explicit third-party notice assumed from agency alone. Book official-use marking evaluated separately',
    'features': False, 'labels': False, 'source_value_replacement': False,
}


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def require(ok, message):
    if not ok: raise ValueError(message)


def marker_status(marker, value):
    require(marker in {'', '*', '#'}, 'Unknown Year Book marker')
    if value in {None, '', '-'}: return 'missing'
    return {'*': 'computed', '#': 'discarded_or_rating_curve_changed', '': 'unmarked_observed_or_estimated'}[marker]


def compare(a, c, unit_a='m3/sec', unit_c='cumec'):
    if a in {None, '', '-'} or c in {None, '', '-'}: return 'source_missing'
    if (unit_a, unit_c) != ('m3/sec', 'cumec'): return 'comparison_not_valid'
    x, y = Decimal(a), Decimal(c)
    require(x.is_finite() and y.is_finite() and x >= 0 and y >= 0, 'Invalid comparison value')
    if x == y: return 'exact'
    step = Decimal(1) if y >= 1000 else Decimal('.1') if y >= 100 else Decimal('.01') if y >= 10 else Decimal('.001')
    if x.quantize(step, rounding=ROUND_HALF_UP) == y:
        if y == 1000 or abs(x-y) == step/2: return 'unit_or_precision_issue'
        return 'rounding_equivalent'
    return 'source_value_conflict'


def classify_case(a, c, marker, unit_a='m3/sec', unit_c='cumec'):
    status = marker_status(marker, c); base = compare(a, c, unit_a, unit_c)
    if base != 'source_value_conflict': return base
    if status == 'computed': return 'yearbook_computed_vs_nwdp'
    if status == 'discarded_or_rating_curve_changed': return 'yearbook_discarded_or_rating_curve_changed'
    return base


def differences(a, c):
    if a in {None, '', '-'} or c in {None, '', '-'}: return None, None
    x,y = Decimal(a),Decimal(c); delta=x-y
    return str(delta), str(delta/abs(y)) if y else None


def distance_m(first, second):
    require(len(first)==len(second)==2, 'Coordinate shape')
    for lat,lon in [first,second]:
        require(math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180, 'Invalid coordinate')
    lat1,lat2 = map(math.radians,[first[0],second[0]])
    dl = math.radians(second[1]-first[1]); dp=lat2-lat1
    hav=math.sin(dp/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2
    return 6371008.8*2*math.atan2(math.sqrt(min(1,max(0,hav))), math.sqrt(max(0,1-hav)))


def identity_status(*, source_id=None, expected_id=None, direct_code_link=False, name=False, agency=False, river=False, opening=False, conflict=False):
    if conflict or (source_id and source_id!=expected_id): return 'identity_conflict'
    if source_id==expected_id and source_id and direct_code_link: return 'identity_verified'
    if all([name,agency,river,opening]): return 'identity_strongly_supported'
    return 'identity_ambiguous'


def threshold_allowed(status):
    require(status in DATUM, 'Unknown datum vocabulary')
    return status=='datum_compatible'


def eligibility(variable, identity, datum, cross_status=None, book_status=None):
    require(identity in IDENTITY and datum in DATUM, 'Invalid eligibility vocabulary')
    if identity in {'identity_ambiguous','identity_conflict'}: return 'unresolved'
    if variable=='water_level' and not threshold_allowed(datum): return 'retain_not_use_for_features'
    if variable=='discharge':
        if cross_status in {'exact','rounding_equivalent'} and book_status=='unmarked_observed_or_estimated':
            return 'eligible_with_quality_caveat'
        return 'retain_not_use_for_features'
    return 'eligible_with_quality_caveat'


def hourly_coverage(observations, ids, start=b.START, end=b.END):
    result=[]; counts=Counter((r['canonical_cwc_station_id'],r['observation_time'][:10]) for r in observations if r['variable']=='water_level')
    for key in ids:
        when=date.fromisoformat(start)
        while when<=date.fromisoformat(end):
            result.append({'station_id':key,'date':when.isoformat(),'actual_count':counts[key,when.isoformat()],
                'expected_hourly_count':None,'coverage_fraction':None,'cadence_status':'strict_hourly_schedule_not_documented',
                'missing_day':counts[key,when.isoformat()]==0,'values_interpolated':False})
            when+=timedelta(days=1)
    return result


def publication_class(artifact, *, explicit_resource_rights=False, third_party_notice=False):
    if artifact=='yearbook': return 'internal_research_only'
    if artifact in {'code','aggregate_metadata'}: return 'publishable_with_source_acknowledgement'
    if artifact=='portal_observations' and explicit_resource_rights and not third_party_notice:
        return 'publishable_with_source_acknowledgement'
    return 'publication_terms_unresolved'


def independent_book(pdf, page, legacy):
    """Alternative scalar text-layout parser, independent of Stage4B bbox parser."""
    text=b.pdf_text(pdf,page);require(legacy in text,'Wrong Year Book identity')
    require('*:ComputedDischarge' in text.replace(' ',''), 'Missing computed notation')
    results={}
    for line in text.splitlines():
        tokens=line.split()
        if not tokens or not tokens[0].isdigit() or not 1<=int(tokens[0])<=31: continue
        day=int(tokens.pop(0)); groups=[]
        while tokens:
            require(len(tokens)>=2,'Incomplete scalar WL/Q pair')
            wl,q=tokens.pop(0),tokens.pop(0)
            marker=tokens.pop(0) if tokens and tokens[0] in {'*','#'} else ''
            marker_status(marker,q); groups.append((wl,q,marker))
        require(len(groups)==(3 if day==31 else 6), 'Unexpected month column count')
        for month,index in [(7,0 if day==31 else 1),(8,1 if day==31 else 2)]:
            when=date(2019,month,day).isoformat()
            if not b.START<=when<=b.END: continue
            require(when not in results,'Duplicate scalar book date');results[when]=groups[index]
    require(len(results)==27,'Missing scalar book dates')
    return results,text


def reconstruct(observations, identities):
    # Search original daily CSV by exact reviewed source identity and actual date.
    values={}
    with (RAW/'river_discharge_manual_daily_cwc_ka_2001_2025.csv').open(newline='') as f:
        for line,r in enumerate(csv.DictReader(f),2):
            key=next((k for k,i in identities.items() if r['Station'] in i['csv_names']),None)
            if not key: continue
            require(r['Agency']=='CWC' and r['Local River'] in identities[key]['csv_local_rivers'],'Original station evidence conflict')
            when=datetime.strptime(r['Data Acquisition Time'],'%d-%m-%Y %H:%M').date().isoformat()
            if not b.START<=when<=b.END: continue
            require((key,when) not in values,'Duplicate daily comparison source')
            values[key,when]=(r['Manual Daily River Water Discharge (m3/sec)'],r['Data Acquisition Time'],line)
    result=[]; sources={r['canonical_cwc_station_id']:r for r in observations if r['variable']=='discharge'}
    for key,i in identities.items():
        book,text=independent_book(RAW/'krishna_wyb2019_20.pdf',b.PILOTS[key]['table_page'],i['yearbook_legacy_code'])
        for when,(_,q,marker) in sorted(book.items()):
            raw=values.get((key,when)); value=raw[0] if raw else None; unit='m3/sec' if raw else None
            delta,relative=differences(value,q); status=marker_status(marker,q)
            category=classify_case(value,q,marker,unit,'cumec')
            prior=compare(value,q,unit,'cumec');prior={'exact':'exact_match','source_missing':'unavailable_in_one_source','source_value_conflict':'discrepancy'}.get(prior,prior)
            result.append({'station_id':key,'date':when,'nwdp_original_value':value,'nwdp_unit':unit,
                'yearbook_original_value':q,'yearbook_unit':'cumec','difference_nwdp_minus_yearbook':delta,
                'relative_difference_yearbook_denominator':relative,'yearbook_literal_marker':marker,'yearbook_status':status,
                'nwdp_quality_status':'not_supplied','nwdp_quality_field':None,'prior_classification':prior,'classification':category,
                'conflict_resolved':False if prior=='discrepancy' else None,'preferred_for_analysis':None,'preference_basis':None,
                'nwdp_source_row':raw[2] if raw else None,'nwdp_original_time':raw[1] if raw else None,
                'nwdp_resource_id':b.CONFIG['cwc_discharge']['id'],'yearbook_pdf_page':b.PILOTS[key]['table_page'],
                'yearbook_source_id':i['yearbook_legacy_code'],'source_provenance':{'csv':str((RAW/'river_discharge_manual_daily_cwc_ka_2001_2025.csv').relative_to(ROOT)),
                    'pdf':str((RAW/'krishna_wyb2019_20.pdf').relative_to(ROOT)), 'retrieval_time':sources[key]['retrieval_time']},
                'time_scope':'Date-level comparison; source measurement time/finalisation differences unresolved'})
    old={(r['canonical_cwc_station_id'],r['observation_date']):r for r in rows(PILOT/'cross_source_comparison.csv')}
    require(len(old)==len(result)==81,'Comparison case coverage changed')
    for r in result:
        previous=old[r['station_id'],r['date']]
        require((r['nwdp_original_value'] or '')==previous['nwdp_original_value'] and r['yearbook_original_value']==previous['yearbook_original_value'] and
            r['yearbook_literal_marker']==previous['yearbook_flag'] and r['prior_classification']==previous['classification'], 'Independent comparison did not reproduce Stage4B')
    return result


def station_records(identities, registry, observations):
    result=[]
    for key,i in identities.items():
        current=registry[key]; selected=[r for r in observations if r['canonical_cwc_station_id']==key]
        source_records=[json.loads(r['source_record']) for r in selected]
        text=b.pdf_text(RAW/'krishna_wyb2019_20.pdf',i['history_pdf_page'])
        require(text==i['source_history_text'],'Official history text changed')
        # Preserve originals including spelling variants; no inferred current-LGD names.
        history_fields={}
        for field in ['State','District','Basin','Local River','Discharge','Gauge']:
            pattern=(r'^\s*'+field+r'\s*:\s*([^\n]+?)(?=\s{3,}|$)') if field in {'Gauge','Discharge'} else (r'\b'+field+r'\s*:?\s+(.+?)(?=\s{3,}|$)')
            match=re.search(pattern,text,re.M)
            history_fields[field]=match[1].strip() if match else None
        status=identity_status(expected_id=key,name=all(r['Station'] in i['csv_names'] for r in source_records),
            agency=all(r['Agency']=='CWC' for r in source_records),river=all(r['Local River'] in i['csv_local_rivers'] and r['Basin']=='Krishna' and r['State']=='Karnataka' and r['District']==current['source_district'] for r in source_records),
            opening=i['gauge_opening_corroborated'])
        points={'stage4a':[current['latitude'],current['longitude']], 'nwdp':[i['nwdp_latitude'],i['nwdp_longitude']], 'yearbook':[i['yearbook_latitude'],i['yearbook_longitude']]}
        distances={pair:distance_m(points[a],points[c]) for pair,a,c in [('stage4a_nwdp','stage4a','nwdp'),('stage4a_yearbook','stage4a','yearbook'),('nwdp_yearbook','nwdp','yearbook')]}
        result.append({'station_id':key,'identity_status':status,'direct_current_id_in_csv':False,
            'stage4a_original':deepcopy(current),'nwdp_identity_fields':{f:sorted({r[f] for r in source_records}) for f in ['Station','Agency','Local River','River','Basin','State','District','Latitude','Longitude']},
            'yearbook_legacy_id':i['yearbook_legacy_code'],'yearbook_original_name':i['yearbook_name'],'yearbook_history_fields':history_fields,
            'gauge_opening_date':i['gauge_opening_date'],'gauge_opening_corroborated':True,
            'yearbook_history_page':i['history_pdf_page'],'coordinates_by_source':points,'approximate_distance_m':distances,
            'coordinate_precision':{'stage4a':'three decimal degrees; accuracy/datum unspecified','nwdp':'eight displayed decimals; accuracy/datum unspecified','yearbook':'whole arcseconds; accuracy/datum unspecified'},
            'coordinate_status':i['nwdp_vs_stage4a_coordinate_status'],'river_proximity_status':'unresolved_no_verified_georeferenced_river_layer',
            'evidence_basis':'CWC official name/agency/river/basin/state/district and gauge opening; coordinate differences unresolved, not direct ID equality',
            'discharge_opening_status':'one_day_source_difference' if key=='CW1KRU000212' else 'source_values_preserved',
            'coordinates_modified':False,'nwdp_station_type':'not_supplied',
            'yearbook_zero_gauge_history_literal':text[text.index('Zero of Gauge'):text.index('Opening Date')].strip(),
            'yearbook_hfl_during_2019_20':(re.search(r'HFL During 2019-20\s*:\s*([\d.]+)',text)[1] if re.search(r'HFL During 2019-20\s*:\s*([\d.]+)',text) else None),
            'yearbook_hfl_date':(datetime.strptime(re.search(r'Date & Time of\s*:\s*(\d{2}/\d{2}/\d{4})',text)[1],'%d/%m/%Y').date().isoformat() if re.search(r'Date & Time of\s*:\s*(\d{2}/\d{2}/\d{4})',text) else None)})
    return result


def datum_records(stations, observations):
    inventory=b.read(FOUNDATION/'flood_station_inventory.json');result=[]
    for station in stations:
        key=station['station_id']; accepted={station['stage4a_original']['official_name'],station['yearbook_original_name']}
        thresholds=[r for r in inventory if r['official_name'] in accepted]
        require(len(thresholds)==1,'Ambiguous threshold identity')
        source=[json.loads(r['source_record']) for r in observations if r['canonical_cwc_station_id']==key and r['variable']=='water_level']
        result.append({'station_id':key,'nwdp_unit':'meter','nwdp_water_level_datum':'unresolved',
            'yearbook_water_level_datum':'elevation_above_MSL; table corresponding_mean_water_level',
            'yearbook_datum_evidence':{'section':'1.4.1;1.5.1(iii)','pdf_pages':[21,23],'history_page':station['yearbook_history_page']},
            'nwdp_auxiliary_fields':{f:sorted({r[f] for r in source}) for f in ['RL_of_zeroGauge','MeanSeaLevel']},
            'auxiliary_fields_interpretation':'No published measured-field offset/reference definition found; zero strings not missing-value replacements',
            'stage4a_thresholds_original':deepcopy(thresholds[0]),'threshold_compatibility':'datum_unresolved',
            'thresholds_usable':False,'threshold_temporal_applicability':'2025_SOP_not_verified_for2019','offset_applied':False,
            'threshold_exceedances_computed':False,
            'yearbook_zero_gauge_history_literal':station['yearbook_zero_gauge_history_literal'],
            'yearbook_hfl_during_2019_20':station['yearbook_hfl_during_2019_20'],'yearbook_hfl_date':station['yearbook_hfl_date'],
            'hfl_cross_publication_status':'differences_preserved_not_reconciled' if station['yearbook_hfl_during_2019_20'] else 'not_compared_without_history_hfl',
            'hfl_note':'Book2019-20 and SOP2025 refer to different source vintages; no value/date silently substituted'})
    return result


def policy_records(resources):
    result=[]
    for r in resources:
        path=RAW/(next(name for name,c in b.CONFIG.items() if c['id']==r['resource_id'])+'_resource.html')
        review=POLICY/(r['resource_id']+'.html.json');live=b.read(review)
        if live['status']=='retrieved': path=POLICY/(r['resource_id']+'.html')
        p=b.Page();p.feed(path.read_text()); text=' '.join(p.text)
        require(r['resource_licence'] in text,'Resource licence changed or missing')
        explicit=[phrase for phrase in ['third-party copyright','third party copyright','copyright of a third party'] if phrase in text.lower()]
        result.append({'artifact':r['resource_id'],'artifact_kind':'portal_observations','producer':r['producer'],
            'resource_url':r['resource_page_url'],'resource_update':r['resource_page_update'],'licence_field':r['resource_licence'],
            'other_open_is_standard_licence':False,'explicit_third_party_copyright_notice':explicit or None,
            'notice_review_scope':'official resource page; producer alone not a third-party notice',
            'current_page_check':{k:live.get(k) for k in ['source_url','retrieved_at','http_status','status','sha256']},
            'portal_policy_support':'accurate/nonmisleading attributed reproduction except explicitly third-party material',
            'classification':publication_class('portal_observations'),
            'reason':'Detailed resource rights/source-policy interaction not definitively settled; retain established conservative handling',
            'publish_detailed_data':False})
    for artifact,kind in [('krishna_wyb2019_20.pdf','yearbook'),('observation_quality.csv','derived_detail'),('discharge_reconciliation.csv','derived_detail'),('station_identity.json','derived_detail'),('datum_compatibility.json','derived_detail'),('hourly_coverage.csv','derived_detail'),('source_notes.json','derived_detail'),('rules.json','aggregate_metadata'),('publication_policy.json','aggregate_metadata'),('processing_code','code'),('aggregate_provenance','aggregate_metadata')]:
        result.append({'artifact':artifact,'artifact_kind':kind,'classification':publication_class(kind),
            'source_marking':'FOR OFFICIAL USE ONLY' if kind=='yearbook' else None,
            'reason':'Book retained locally as comparison evidence; this project handling is not a legal grant' if kind=='yearbook' else 'Only own code and non-restricted aggregate metadata published' if kind in {'code','aggregate_metadata'} else 'Contains detailed portal/book/coordinate material; rights unresolved',
            'publish_detailed_data':kind in {'code','aggregate_metadata'}})
    return result


def check_inputs():
    # No network or writes. Pin all original Stage4B source/output/code hashes.
    m=b.read(PILOT/'manifest.json')
    for name,r in m['files'].items():
        p=PILOT/name;require(p.stat().st_size==r['bytes'] and b.digest(p)==r['sha256'],'Stage4B output integrity failure')
    for r in m['source_inputs']+m['protected_foundation_inputs']+[m['processing_code']]:
        p=ROOT/r['path'];require(p.stat().st_size==r['bytes'] and b.digest(p)==r['sha256'],'Original input integrity failure')


def quality_rows(observations, indexed, status):
    quality=[]
    for r in observations:
        key=r['canonical_cwc_station_id']; case=indexed[key,r['observation_time'][:10]] if r['variable']=='discharge' else None
        item=deepcopy(r) # Includes every original value/unit/time/quality/source row unchanged.
        item.update(source_quality_status='original_quality_flags_supplied_uninterpreted' if json.loads(r.get('quality_flags','{}')) else 'original_quality_flag_not_supplied',cross_source_status=case['classification'] if case else 'not_compared_hourly_vs_daily_mean',
            yearbook_status=case['yearbook_status'] if case else None,identity_status=status[key],datum_status='datum_unresolved' if r['variable']=='water_level' else 'not_applicable_to_discharge',
            analysis_eligibility=eligibility(r['variable'],status[key],'datum_unresolved' if r['variable']=='water_level' else 'datum_compatible',case['classification'] if case else None,case['yearbook_status'] if case else None),
            preferred_for_analysis=None,preference_basis=None)
        require(all(item[k]==v for k,v in r.items()),'Source field changed');quality.append(item)
    return quality


def assemble():
    check_inputs(); observations=rows(PILOT/'observations.csv'); require(len(observations)==1697,'Stage4B row count changed')
    identities=b.read(PILOT/'identity_evidence.json'); registry={r['source_station_id']:r for r in b.read(FOUNDATION/'station_registry.json')}
    comparisons=reconstruct(observations,identities); stations=station_records(identities,registry,observations);datums=datum_records(stations,observations)
    indexed={(r['station_id'],r['date']):r for r in comparisons}; status={r['station_id']:r['identity_status'] for r in stations}
    quality=quality_rows(observations,indexed,status)
    policies=policy_records(b.read(PILOT/'raw_source_registry.json'));coverage=hourly_coverage(observations,identities)
    decision=[]
    for key in identities:
        for variable in ['water_level','discharge']:
            selected=[r for r in quality if r['canonical_cwc_station_id']==key and r['variable']==variable]
            eligible=sum(r['analysis_eligibility']=='eligible_with_quality_caveat' for r in selected)
            decision.append({'station_id':key,'variable':variable,'rows':len(selected),'eligible_with_caveat':eligible,
                'usable_for_stage4d':eligible>0,'scope':'Only corroborated nonconflicting daily rows; no continuous trend/window readiness' if variable=='discharge' else 'Blocked pending measured-field datum documentation',
                'threshold_relative_usable':False,'quality_flags_required':True,'historical_availability_verified':False})
    result={'observations':len(quality),'comparisons':len(comparisons),'prior_comparison_counts':dict(Counter(r['prior_classification'] for r in comparisons)),
        'comparison_categories':dict(Counter(r['classification'] for r in comparisons)),
        'unresolved_discharge_discrepancies':sum(r['prior_classification']=='discrepancy' for r in comparisons),
        'eligibility_counts':dict(Counter(r['analysis_eligibility'] for r in quality)),
        'station_identity':{r['station_id']:r['identity_status'] for r in stations},
        'datum_compatibility':{r['station_id']:r['threshold_compatibility'] for r in datums},
        'publication_counts':dict(Counter(r['classification'] for r in policies)),
        'hourly_coverage_metadata_rows':len(coverage),'feature_readiness':'hydrology_features_ready_limited' if any(r['usable_for_stage4d'] for r in decision) else 'hydrology_feature_engineering_blocked',
        'readiness_scope':'Offline exploratory subset only; all threshold-relative/absolute-level and real-time predictor use blocked',
        'station_variable_readiness':decision,'features_created':0,'labels_created':0,'source_values_changed':0}
    notes={'yearbook':[{'pdf_page':n,'printed_page':label,'literal_text':b.pdf_text(RAW/'krishna_wyb2019_20.pdf',n)} for n,label in [(21,'x'),(22,'xi'),(23,'xii')]],
        'policy':[{'source_path':str(path.relative_to(ROOT)), 'literal_page_text':policy_text(path)} for path in [ROOT/'data/raw/reference/stage4a_v1/cwc_copyright.html',RAW/'nwdp_copyright.html',POLICY/'nwdp_policy.html',POLICY/'cwc_policy.html']],
        'marker_scope':'Pilot cells contain blank and *; # occurs elsewhere on Huvinhedgi table. Numeric0.000 retained, not missing; no additional nil/missing marker definition inferred'}
    artifacts={'observation_quality.csv':b.table_bytes(quality),'discharge_reconciliation.csv':b.table_bytes(comparisons),
        'station_identity.json':b.json_bytes(stations),'datum_compatibility.json':b.json_bytes(datums),
        'hourly_coverage.csv':b.table_bytes(coverage),'publication_policy.json':b.json_bytes(policies),'rules.json':b.json_bytes(RULES),'source_notes.json':b.json_bytes(notes)}
    return artifacts,result


def policy_text(path):
    page=b.Page();page.feed(Path(path).read_text());return ' '.join(page.text)


def inputs():
    paths=list(PILOT.iterdir())+list(FOUNDATION.iterdir())+list(RAW.iterdir())+list(POLICY.iterdir())
    paths += [Path(b.__file__),ROOT/'data/raw/reference/stage3e3_v1/cwc_station_metadata.pdf',ROOT/'data/raw/reference/stage4a_v1/cwc_sop_april2025.pdf',ROOT/'data/raw/reference/stage4a_v1/cwc_copyright.html',ROOT/'data/raw/reference/stage4a_v1/cwc_copyright.html.json',ROOT/'data/raw/reference/stage4a_v1/nwdp_copyright.html',ROOT/'data/raw/reference/stage4a_v1/nwdp_copyright.html.json']
    return [b.file_record(p) for p in sorted(paths) if p.is_file()]


def freeze(output=OUTPUT):
    output=Path(output);require(not output.exists(),'Immutable reconciliation already exists')
    artifacts,result=assemble();manifest={'version':'karnataka_hydrology_2019_reconciled_v1','created_at':datetime.now(timezone.utc).isoformat(),
        'input_checksums':inputs(),'processing_code':b.file_record(Path(__file__)),'rules':RULES,'summary':result,
        'files':{n:{'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()} for n,body in artifacts.items()}}
    output.mkdir(parents=True)
    for n,body in artifacts.items():(output/n).write_bytes(body)
    (output/'manifest.json').write_bytes(b.json_bytes(manifest));return result


def validate(output=OUTPUT):
    output=Path(output);m=b.read(output/'manifest.json')
    for r in m['input_checksums']+[m['processing_code']]:
        p=ROOT/r['path'];require(p.stat().st_size==r['bytes'] and b.digest(p)==r['sha256'],'Reconciliation input integrity mismatch')
    artifacts,result=assemble();require(result==m['summary'] and RULES==m['rules'],'Reconciliation rules/summary changed')
    for n,body in artifacts.items():
        require(body==(output/n).read_bytes() and len(body)==m['files'][n]['bytes'] and hashlib.sha256(body).hexdigest()==m['files'][n]['sha256'],'Reconciliation output reproduction failed')
    return result


def public_manifest(output=OUTPUT):
    m=b.read(Path(output)/'manifest.json')
    return {'version':m['version'],'created_at':m['created_at'],'rules':m['rules'],'summary':m['summary'],
        'files':m['files'],'input_checksums':m['input_checksums'],'processing_code':m['processing_code'],
        'local_manifest_sha256':b.digest(Path(output)/'manifest.json'),
        'resource_policy_metadata':[{k:r[k] for k in ['artifact','producer','resource_url','resource_update','licence_field','explicit_third_party_copyright_notice','current_page_check','classification']} for r in b.read(Path(output)/'publication_policy.json') if r['artifact_kind']=='portal_observations'],
        'official_policy_sources':[{'source_url':b.read(POLICY/(name+'.html.json'))['source_url'],'retrieval_time':b.read(POLICY/(name+'.html.json'))['retrieved_at'],'sha256':b.digest(POLICY/(name+'.html'))} for name in ['nwdp_policy','cwc_policy']],
        'publication':'Detailed products local; no original source values or coordinates in this metadata'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['build','validate']);parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args();print(json.dumps(freeze(args.output) if args.command=='build' else validate(args.output),indent=2))
