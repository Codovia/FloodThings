"""Isolated scientific safety tests. Example values are fixtures, never field data."""
import copy
import csv
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import acquire_direct_observation_metadata as transport
import acquire_riverine_source_metadata as sources
import inventory_riverine_station_series as inventory
import riverine_forecast_contract as contract
import audit_riverine_forecasting as audit


def proof():
    return {'status': 'VERIFIED', 'reviewer': 'Isolated test reviewer',
            'source_url': 'https://example.test/document', 'sha256': 'a'*64}


@pytest.fixture
def pair():
    meta = {'station_id': 'TEST_ONLY', 'datum': 'TEST_DATUM',
            'valid_from': '2010-01-01T00:00Z', 'valid_to': '2030-01-01T00:00Z',
            'reviews': {k: proof() for k in contract.REQUIRED_REVIEWS}}
    row = {'source_class': contract.MEASURED, 'station_id': 'TEST_ONLY',
           'variable': 'water_level', 'units': 'm', 'value': '10', 'datum': 'TEST_DATUM',
           'quality_status': 'ACCEPTED_MEASURED', 'duplicate_status': 'UNIQUE_OR_OFFICIALLY_RECONCILED',
           'statistic': 'instantaneous', 'observation_time': '2020-01-01T00:00Z',
           'availability_time': '2020-01-01T00:00Z'}
    outcome = {**row, 'observation_time': '2020-01-01T06:00Z', 'availability_time': '2020-01-02T06:00Z'}
    return row, outcome, meta


def test_future_truth_may_arrive_later_but_predictor_must_be_available(pair):
    p, o, m = pair
    assert contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['status'] == 'ELIGIBLE_FOR_REVIEW'
    assert contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['training_authorized'] is False
    p['availability_time'] = '2020-01-01T00:01Z'
    assert 'PREDICTOR_NOT_AVAILABLE_AT_ISSUE' in contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['blockers']


@pytest.mark.parametrize('key,value,blocker', [
    ('source_class','modelled_glofas','NOT_MEASURED_STATION_DATA'),
    ('station_id','OTHER','STATION_ID_MISMATCH'),
    ('variable','rainfall','UNSUPPORTED_VARIABLE'),
    ('units','feet','UNITS_NOT_NORMALIZED_WITH_EVIDENCE'),
    ('value','NaN','INVALID_VALUE'), ('value','Inf','INVALID_VALUE'), ('value',True,'INVALID_VALUE'),
    ('quality_status','COMPUTED','QC_NOT_CONFIRMED_MEASURED'),
    ('duplicate_status','CONFLICT','DUPLICATE_CONFLICT_REVIEW_MISSING'),
    ('statistic','daily_mean','INSTANTANEOUS_TARGET_SEMANTICS_UNVERIFIED'),
    ('datum','OTHER','DATUM_MISMATCH_OR_UNKNOWN'),
    ('observation_time','2020-01-01T00:00','UNVERIFIED_OBSERVATION_TIME_OR_METADATA_VALIDITY'),
    ('observation_time','2040-01-01T00:00Z','OUTSIDE_STATION_METADATA_VALIDITY'),
    ('availability_time',None,'PREDICTOR_AVAILABILITY_UNKNOWN'),
    ('availability_time','2019-12-31T23:59Z','PREDICTOR_NOT_AVAILABLE_AT_ISSUE')])
def test_caveats_and_leakage_never_pass_as_measured_training_evidence(pair,key,value,blocker):
    p,o,m=pair; p[key]=value
    assert blocker in contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['blockers']


@pytest.mark.parametrize('review', contract.REQUIRED_REVIEWS)
def test_each_independent_evidence_requirement_is_mandatory(pair,review):
    p,o,m=pair; m['reviews'][review]['status']='UNKNOWN'
    assert 'UNVERIFIED_'+review.upper() in contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['blockers']


@pytest.mark.parametrize('time,blocker', [('2020-01-01T05:59Z','TARGET_NOT_EXACT_LEAD_TIME'),
                                       ('2020-01-01T00:00','PAIR_TIME_INVALID')])
def test_target_cannot_be_interpolated_or_guessed(pair,time,blocker):
    p,o,m=pair;o['observation_time']=time
    assert blocker in contract.assess_pair(p,o,m,'2020-01-01T00:00Z')['blockers']


def threshold(pair):
    p,_,_=pair
    return {**{k:p[k] for k in ['station_id','variable','units','datum']},
            'authority':'CWC','kind':'danger_level','value':10,'review':proof(),
            'valid_from':'2010-01-01T00:00Z','valid_to':'2030-01-01T00:00Z'}


def test_threshold_equality_is_point_nonexceedance_not_interval_absence(pair):
    p,_,m=pair; t=threshold(pair)
    r=contract.threshold_outcome(p,m,t)
    assert r['outcome']=='DOES_NOT_EXCEED_AT_INSTANT'
    assert r['interval_absence_established'] is r['inundation_established'] is False
    p['value']='11'
    assert contract.threshold_outcome(p,m,t)['outcome']=='EXCEEDS'


@pytest.mark.parametrize('key,value', [('authority','PERCENTILE_RULE'),('kind','p95'),('datum','OTHER'),
    ('units','ft'),('station_id','OTHER'),('valid_from','2021-01-01T00:00Z'),('value','NaN')])
def test_arbitrary_incompatible_or_future_threshold_stays_unknown(pair,key,value):
    p,_,m=pair;t=threshold(pair);t[key]=value
    assert contract.threshold_outcome(p,m,t)['outcome']=='UNKNOWN'


@pytest.fixture
def forecast():
    return {'source':'GLOFAS','forecast_class':'external_modelled_river_forecast',
        'access_review':proof(),'display_rights_review':proof(),'geographic_review':proof(),
        'original_sha256':'b'*64,'source_product_id':'TEST_ONLY','product_version':'TEST',
        'geographic_semantics':'verified_model_reach','geographic_id':'TEST_REACH',
        'issue_time':'2020-01-01T00:00Z','availability_time':'2020-01-01T02:00Z',
        'retrieved_at':'2020-01-01T03:00Z','valid_start':'2020-01-01T00:00Z',
        'valid_end':'2020-01-03T00:00Z','expires_at':'2020-01-02T00:00Z','maximum_age_hours':24}


def test_forecast_contract_is_disabled_by_default_and_never_ai_or_alert(forecast):
    with pytest.raises(ValueError,match='disabled'):
        contract.validate_forecast_receipt(forecast,now='2020-01-01T04:00Z')
    r=contract.validate_forecast_receipt(forecast,enabled=True,now='2020-01-01T04:00Z')
    assert r['floodpulse_ai'] is r['automatic_alerts'] is r['training_label'] is False


@pytest.mark.parametrize('key,value', [('source','FLOODPULSE'),('forecast_class','official_river_forecast'),
    ('geographic_semantics','district'),('geographic_semantics','verified_station'),
    ('geographic_review',None),('product_version',None),('original_sha256','bad'),
    ('issue_time','2020-01-01T05:00Z'),('availability_time','2020-01-01T04:00Z'),
    ('valid_end','2020-01-01T00:00Z'),('expires_at','2020-01-01T03:00Z'),
    ('maximum_age_hours',True),('maximum_age_hours',1),('display_rights_review',None)])
def test_stale_missing_rights_or_misattributed_forecasts_rejected(forecast,key,value):
    forecast[key]=value
    with pytest.raises(ValueError):
        contract.validate_forecast_receipt(forecast,enabled=True,now='2020-01-01T04:00Z')


def test_new_metadata_hosts_never_mutate_frozen_phase12e_state():
    original=transport.HOSTS
    with sources.metadata_hosts():
        assert transport.validate_url('https://api.imd.gov.in/public/contact.php')
        with pytest.raises(ValueError):transport.validate_url('https://api.imd.gov.in/native.tif')
    assert transport.HOSTS is original


def test_exact_source_receipts_and_urls_required(tmp_path):
    with pytest.raises(ValueError,match='Exact pinned'):sources.validate(tmp_path)


def test_stream_inventory_counts_conflicts_without_preferring_or_exporting_values(tmp_path):
    source=tmp_path/'source.csv'
    with source.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['Station','Data Acquisition Time','Manual Daily River Water Discharge (m3/sec)'])
        w.writerows([['Sadalga (Seasonal)','01-01-2019 08:00','10'],
                     ['Sadalga (Seasonal)','01-01-2019 08:00','10.0'],
                     ['Sadalga (Seasonal)','01-01-2019 08:00','11'],
                     ['Sadalga (Seasonal)','02-01-2019 08:00','-'],
                     ['Other','01-01-2019 08:00','999']])
    with sqlite3.connect(tmp_path/'isolated.sqlite') as db:
        db.execute('CREATE TABLE observations(source TEXT,station TEXT,time TEXT,value TEXT,quality TEXT)')
        r=inventory.scan(source,'discharge',db,'TEST_ONLY')
    s=r['station_records'][0]
    assert r['total_archive_rows_scanned']==5 and s['counts']['rows']==4
    assert s['duplicate_timestamp_extra_rows']==2 and s['conflicting_timestamp_groups']==1
    assert s['counts']['MISSING']==1 and s['eligible_training_rows']==0
    assert r['year_records'][0]['source_date_count']==2
    assert 'value' not in s and 'latitude' not in json.dumps(s).lower()


def test_aliases_do_not_fuzzily_merge_station_identities():
    assert inventory.candidate_alias(' Sadalga (Seasonal) ')=='CW1KRU000083'
    assert inventory.candidate_alias('Sadalga downstream') is None
    assert inventory.candidate_alias('Huvin') is None


def test_stage_can_be_below_gauge_zero_but_negative_discharge_invalid():
    assert inventory.value_class('-1','water_level')[0]=='FINITE_SOURCE_VALUE_NOT_QC_APPROVED'
    assert inventory.value_class('-1','discharge')[0]=='INVALID'
    assert inventory.value_class('NaN','discharge')[0]=='INVALID'


def test_proposal_never_authorizes_training_or_confuses_stage_and_flood():
    p=audit.target_protocol()
    assert p['training_authorized'] is p['A_is_flood_prediction'] is p['B_is_inundation_map'] is False
    assert p['scientific_approval'] is None and p['lead_hours']==6
    assert p['training_period'][1]==p['validation_period'][0]
    assert p['validation_period'][1]==p['test_period'][0]
