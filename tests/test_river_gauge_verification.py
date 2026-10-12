"""Isolated native-clock diagnostics; fixtures never become production labels."""
import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_river_gauge_histories as gauge


def series(*rows):
    groups={}
    for ordinal,(time,value) in enumerate(rows,1):
        literal,precision=gauge.native_time(time)
        quality,numeric=gauge.value_class(value,'stage')
        g=groups.setdefault(literal,{'refs':[],'values':set(),'invalid':False,'precision':precision})
        g['refs'].append(ordinal);g['values'].add(numeric)
        g['invalid'] |= quality!='FINITE_SOURCE_VALUE_NOT_QC_APPROVED'
    return {'groups':groups,'source_resource_id':'isolated-fixture','formats':{},'invalid_rows':0,'rows':len(rows)}


@pytest.mark.parametrize('literal,expected,precision',[
    ('31-12-2019 18:00','2019-12-31T18:00:00','MINUTE'),
    ('01-01-2020','2020-01-01','DATE_ONLY'),
    ('31-02-2020 06:00',None,'INVALID'),
    ('2020-01-01T06:00:00Z',None,'INVALID'),
    ('01-01-2020 06:00+05:30',None,'INVALID')])
def test_native_precision_never_fabricates_timezone(literal,expected,precision):
    assert gauge.native_time(literal)==(expected,precision)


@pytest.mark.parametrize('future,match',[
    ('01-01-2020 12:00',True),('01-01-2020 11:59',False),('01-01-2020 12:01',False),
    ('02-01-2020 12:00',False)])
def test_exact_six_hour_target_no_nearest_interpolation(future,match):
    s=series(('01-01-2020 06:00','10'),(future,'11'))
    r=next(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6))
    assert r['flags']['structural_pairs_current_and_exact_target']==match
    assert r['scientific_eligibility']=='UNKNOWN'
    assert r['input_historical_availability']=='UNKNOWN'


def test_date_only_not_midnight_target():
    s=series(('01-01-2020 18:00','10'),('02-01-2020','11'))
    r=next(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6))
    assert not r['flags']['matching_future_measurements']
    assert len(gauge.issue_times(s['groups'],'READING_TIME'))==1


@pytest.mark.parametrize('future_values,duplicate,conflict,singleton',[
    (['11'],False,False,True),(['11','11.0'],True,False,False),(['11','12'],True,True,False)])
def test_all_duplicate_variants_retained_without_preference(future_values,duplicate,conflict,singleton):
    s=series(('01-01-2020 06:00','10'),*[('01-01-2020 12:00',v) for v in future_values])
    r=next(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6));f=r['flags']
    assert f['pairs_with_duplicate_input_or_target']==duplicate
    assert f['pairs_with_conflicting_input_or_target']==conflict
    assert f['pairs_singleton_finite_input_and_target']==singleton
    assert len(r['target_source_rows_all_variants'])==len(future_values)


def test_latest_conflict_does_not_fallback_to_earlier_clean_input():
    s=series(('01-01-2020 05:00','10'),('01-01-2020 06:00','11'),
             ('01-01-2020 06:00','12'),('01-01-2020 12:00','13'))
    r=next(gauge.pair_records('CW1KRU000083',s,'NATIVE_6H_GRID',6))
    assert r['input_source_rows_all_variants']==[2,3]
    assert r['flags']['pairs_with_conflicting_input_or_target']


@pytest.mark.parametrize('age,available',[(60,True),(61,False),(0,True)])
def test_prior_input_age_bound(age,available):
    issue=dt.datetime(2020,1,1,6)
    s=series(((issue-dt.timedelta(minutes=age)).strftime('%d-%m-%Y %H:%M'),'10'),
             ('01-01-2020 12:00','11'))
    r=next(x for x in gauge.pair_records('CW1KRU000083',s,'NATIVE_6H_GRID',6) if x['issue_native']==issue.isoformat())
    assert r['flags']['with_input_within_one_hour']==available


def test_year_boundary_preserves_future_match_assigns_issue_year():
    s=series(('31-12-2019 18:00','10'),('01-01-2020 00:00','11'))
    summary=gauge.pair_summary(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6))
    assert summary['2019']['structural_pairs_current_and_exact_target']==1
    assert summary['2020']['structural_pairs_current_and_exact_target']==0


def test_missing_history_is_separate_from_persistence_structure():
    s=series(('01-01-2020 06:00','10'),('01-01-2020 12:00','11'))
    r=next(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6))
    assert r['flags']['structural_pairs_current_and_exact_target']
    assert r['flags']['pairs_with_missing_required_antecedents']
    assert not r['flags']['pairs_with_unique_finite_input_target_and_all_antecedents']


def test_conflict_in_past_lag_blocks_rich_features_but_not_current_structure():
    s=series(('31-12-2019 06:00','8'),('01-01-2020 00:00','9'),
             ('01-01-2020 05:00','9'),('01-01-2020 05:00','10'),
             ('01-01-2020 06:00','10'),('01-01-2020 12:00','11'))
    r=next(x for x in gauge.pair_records('CW1KRU000083',s,'READING_TIME',6) if x['issue_native']=='2020-01-01T06:00:00')
    assert r['flags']['pairs_with_exact_antecedents_1_6_24h']
    assert r['flags']['pairs_with_conflicting_required_antecedents']
    assert not r['flags']['pairs_with_unique_finite_input_target_and_all_antecedents']


def test_future_input_never_used():
    s=series(('01-01-2020 00:00','9'),('01-01-2020 06:01','10'),('01-01-2020 12:00','11'))
    r=next(x for x in gauge.pair_records('CW1KRU000083',s,'NATIVE_6H_GRID',6)
           if x['issue_native']=='2020-01-01T06:00:00')
    assert r['input_source_rows_all_variants']==[]
    assert r['latest_prior_native']=='2020-01-01T00:00:00'
    assert r['flags']['matching_future_measurements']
    assert not r['flags']['structural_pairs_current_and_exact_target']


def test_interval_histogram_deduplicates_time_not_values():
    s=series(('01-01-2020 08:00','10'),('01-01-2020 08:00','11'),
             ('01-01-2020 13:00','12'),('01-01-2020 18:00','13'),('02-01-2020 08:00','14'))
    c=gauge.coverage('CW1KRU000083','stage',s,2020)
    assert c['frequency_diagnostics']['interval_minutes_histogram']=={'300':2,'840':1}
    assert c['conflicting_timestamp_groups']==1
    assert c['duplicate_timestamp_extra_rows']==1
    assert c['calendar_dates_without_any_record']==364
    assert c['frequency_diagnostics']['expected_missing_readings'].startswith('UNKNOWN')


def test_empty_year_diagnostic_has_no_synthetic_readings():
    s=series(('01-01-2019 08:00','10'),('01-01-2021 08:00','11'))
    c=gauge.coverage('CW1KRU000083','stage',s,2020)
    assert c['rows']==0 and c['unique_native_times']==0
    assert c['calendar_dates_without_any_record']==366


@pytest.mark.parametrize('value',['NaN','Infinity','NA',''])
def test_numeric_missing_invalid_not_validated(value):
    s=series(('01-01-2020 06:00','10'),('01-01-2020 12:00',value))
    r=next(gauge.pair_records('CW1KRU000083',s,'READING_TIME',6))
    assert r['flags']['pairs_with_invalid_input_or_target']
    assert not r['flags']['pairs_singleton_finite_input_and_target']


def test_subset_rejects_repeated_source_reference(tmp_path):
    p=tmp_path/'subset.jsonl'
    r={'station_id_candidate':'CW1KRU000083','variable':'stage','source_resource_id':'fixture',
       'source_row_ordinal':1,'value_field':'stage',
       'original':{'Data Acquisition Time':'01-01-2020 06:00','stage':'10'}}
    p.write_text((json.dumps(r)+'\n')*2)
    with pytest.raises(ValueError,match='reference repeated'):gauge.load_subset(p)


def test_series_budget_enforced(tmp_path,monkeypatch):
    monkeypatch.setattr(gauge,'MAX_SERIES_TIMES',1)
    p=tmp_path/'subset.jsonl';rows=[]
    for ordinal,hour in enumerate((6,12),1):
        rows.append({'station_id_candidate':'CW1KRU000083','variable':'stage','source_resource_id':'fixture',
                     'source_row_ordinal':ordinal,'value_field':'stage',
                     'original':{'Data Acquisition Time':f'01-01-2020 {hour:02}:00','stage':'10'}})
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(ValueError,match='series budget'):gauge.load_subset(p)


def test_stage_discharge_separation_and_no_negative_discharge():
    assert gauge.value_class('-1','stage')[0]=='FINITE_SOURCE_VALUE_NOT_QC_APPROVED'
    assert gauge.value_class('-1','discharge')[0]=='INVALID'


def test_existing_output_refused(tmp_path):
    (tmp_path/gauge.OUTPUT).mkdir(parents=True)
    with pytest.raises(ValueError,match='Version exists'):gauge.build(tmp_path)
