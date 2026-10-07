"""Offline Stage4B source contracts. Controlled observations never enter research data."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().parents[2]/'scripts/recover_karnataka_hydrology.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
KEY='CW1FIX000001'


def identities():
    return {KEY:{'csv_names':['Fixture'],'csv_local_rivers':['Fixture river'],
        'gauge_opening_corroborated':True,'nwdp_vs_stage4a_coordinate_status':'source_coordinate_conflict'}}


def record():
    return {'Station':'Fixture','Agency':'CWC','Local River':'Fixture river','Latitude':'15','Longitude':'75',
        'Data Acquisition Time':'10-08-2019 08:30','q':'2.5','Quality Flag':'provisional'}


def config():return {'frequency':'hourly','value':'q','variable':'discharge','units':'m3/sec'}


def resource():return {'resource_id':'fixture-resource','download':{'retrieved_at':'2026-10-07T00:00:00+00:00'}}


def test_resource_metadata_requires_published_exact_download():
    url='https://nwdp.nwic.gov.in/dataset/fixture/resource/r/download/original.csv'
    d={'success':True,'result':{'results':[{'title':'Fixture dataset','id':'dataset',
        'organization':{'title':'CWC'},'license_title':'Other (Open)','license_id':'other-open',
        'resources':[{'id':'r','url':url,'name':'Original resource 2001-2025','format':'CSV','size':3,'last_modified':'2026-01-01'}]}]}}
    page=f'<a href="{url}">Download</a><p>Other (Open)</p><p>Data last updated</p><p>January 1, 2026</p>'.encode()
    body=json.dumps(d);r=h.resource_metadata(body,'r',page,retrieval_time='fixture-time')
    assert r['resource_title']=='Original resource 2001-2025' and r['resource_licence']=='Other (Open)'
    assert r['publication_handling']=='redistribution_unresolved' and r['producer']=='CWC'
    assert r['original_filename']=='original.csv'
    with pytest.raises(ValueError,match='advertised'):h.resource_metadata(body,'r',b'',retrieval_time='fixture-time')
    with pytest.raises(ValueError,match='identity'):h.resource_metadata(body,'unknown',page,retrieval_time='fixture-time')


@pytest.mark.parametrize('title,kwargs,expected',[(None,{},'redistribution_unresolved'),
    ('Other (Open)',{},'redistribution_unresolved'),('Open',{},'redistribution_unresolved'),
    ('Creative Commons Attribution 4.0',{'explicit_terms_verified':True},'open_with_attribution'),
    ('Creative Commons Attribution 4.0',{},'resource_specific_terms_apply'),
    ('Creative Commons Attribution 4.0',{'explicit_terms_verified':True,'third_party':True},'redistribution_unresolved')])
def test_licence_not_inferred_from_title(title,kwargs,expected):
    assert h.classify_licence(title,**kwargs)==expected


def test_source_id_first_and_conflicts_never_name_overridden():
    r=record();r['Station ID']=KEY
    assert h.match_station(r,identities(),'Station ID')==KEY
    r['Station ID']='other-network';assert h.match_station(r,identities(),'Station ID') is None
    r['Station ID']=KEY;r['Station']='Similar fixture'
    with pytest.raises(ValueError,match='conflict'):h.match_station(r,identities(),'Station ID')


def test_secondary_name_requires_independent_agency_river_and_history():
    i=identities();r=record();original=deepcopy((i,r))
    assert h.match_station(r,i)==KEY and (i,r)==original
    r['Agency']='Karnataka';assert h.match_station(r,i) is None
    r['Agency']='CWC';r['Local River']='Other'
    with pytest.raises(ValueError,match='river'):h.match_station(r,i)
    r=record();i[KEY]['gauge_opening_corroborated']=False
    with pytest.raises(ValueError,match='independent'):h.match_station(r,i)


def test_ambiguous_or_fuzzy_alias_refused():
    i=identities();i['other']=deepcopy(i[KEY])
    with pytest.raises(ValueError,match='Ambiguous'):h.match_station(record(),i)
    r=record();r['Station']='Fixtures';assert h.match_station(r,identities()) is None


@pytest.mark.parametrize('value,frequency,expected',[('10-08-2019 08:30','hourly','2019-08-10T08:30:00'),
    ('10-08-2019','daily','2019-08-10'),('10-08-2019 08:30','daily','2019-08-10T08:30:00')])
def test_actual_hourly_daily_timestamps(value,frequency,expected):
    assert h.parse_timestamp(value,frequency)==expected


@pytest.mark.parametrize('value,frequency',[('10-08-2019','hourly'),('31-02-2019','daily'),('unknown','hourly')])
def test_malformed_or_missing_hour_not_invented(value,frequency):
    with pytest.raises(ValueError):h.parse_timestamp(value,frequency)


def test_original_values_units_quality_and_times_preserved():
    r=record();original=deepcopy(r);normalized=h.normalize(r,config(),identities()[KEY],KEY,2,resource())
    assert normalized['original_value']=='2.5' and normalized['units']=='m3/sec'
    assert normalized['quality_flags']=={'Quality Flag':'provisional'}
    assert normalized['source_record']==original and r==original
    assert normalized['retrieval_time']!=normalized['observation_time']
    assert normalized['availability_time'] is None and normalized['historical_availability_status']=='availability_semantics_unverified'
    assert normalized['source_station_id'] is None


@pytest.mark.parametrize('stamp',['24-07-2019 08:00','21-08-2019 08:00'])
def test_bounded_window_excludes_outside_dates(stamp):
    r=record();r['Data Acquisition Time']=stamp
    with pytest.raises(ValueError,match='Outside'):h.normalize(r,config(),identities()[KEY],KEY,2,resource())


@pytest.mark.parametrize('value',[None,'','-'])
def test_missing_value_not_zero(value):assert h.numeric(value,'discharge') is None


@pytest.mark.parametrize('value',['nan','inf','-1','bad'])
def test_invalid_discharge(value):
    with pytest.raises(ValueError):h.numeric(value,'discharge')


def test_gauge_negative_value_with_unknown_datum_preserved():
    assert h.numeric('-1','water_level')=='-1'


def test_duplicate_census_and_original_schema(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        p=Path(d)/'fixture.csv';rows=[record(),record()]
        p.write_bytes(h.table_bytes(rows))
        records,audit=h.csv_audit(p,config(),identities(),resource())
        assert audit['duplicate_station_timestamp_rows']==1 and audit['conflicting_station_timestamp_rows']==0
        assert audit['original_columns']==list(rows[0]) and len(records)==2
        assert audit['quality_columns']==['Quality Flag']
        rows[1]['q']='9';p.write_bytes(h.table_bytes(rows))
        _,audit=h.csv_audit(p,config(),identities(),resource())
        assert audit['conflicting_station_timestamp_rows']==1


def test_source_bad_pilot_value_not_silently_omitted(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        p=Path(d)/'fixture.csv';r=record();r['q']='nan';p.write_bytes(h.table_bytes([r]))
        with pytest.raises(ValueError,match='Pilot window'):h.csv_audit(p,config(),identities(),resource())


@pytest.mark.parametrize('a,b,expected',[('10','10','exact_match'),('12978.274','12978','rounding_equivalent'),
    ('853.34','853.3','rounding_equivalent'),('1800','1671','discrepancy'),(None,'10','unavailable_in_one_source')])
def test_cross_source_decimal_rounding_and_discrepancies(a,b,expected):
    assert h.compare_values(a,b)==expected


def test_computed_discharge_not_promoted_and_conflicts_not_chosen():
    o={'canonical_cwc_station_id':KEY,'variable':'discharge','observation_time':'2019-08-10T08:00:00',
       'original_value':'2','value':'2','units':'m3/sec','source_row_number':2}
    y={'canonical_cwc_station_id':KEY,'variable':'discharge','observation_date':'2019-08-10',
       'original_value':'2','value':'2','units':'cumec','measurement_status':'computed','source_quality_flag':'*'}
    r=h.cross_compare([o],[y])[0]
    assert r['classification']=='exact_match' and not r['measured_confirmation']
    assert r['yearbook_flag']=='*'
    with pytest.raises(ValueError,match='Conflicting'):h.cross_compare([o,o],[y])
    o['units']='meter'
    with pytest.raises(ValueError,match='units'):h.cross_compare([o],[y])


def test_hourly_levels_are_not_compared_as_daily_means():
    assert h.cross_compare([{'variable':'water_level'}],[{'variable':'water_level'}])==[]


def test_history_identity_uses_independent_opening_date_and_keeps_source_values():
    text='Site : Fixture (Seasonal) Code : OLD123\nLatitude : 16°30\'00" Longitude : 75°00\'00"\nGauge : 01/02/1976\nState : Karnataka Basin : Krishna'
    canonical={'source_station_id':KEY,'official_name':'Fixture','source_start_dates_cell':'01/02/1976\n01/02/1976','latitude':16.49,'longitude':74.99}
    r=h.history_identity(text,canonical,{'history_page':1,'csv_name':'Fixture','local_river':'Krishna'})
    assert r['yearbook_legacy_code']=='OLD123' and r['source_history_text']==text
    assert r['stage4a_latitude']==16.49 and r['yearbook_latitude']==16.5
    canonical['source_start_dates_cell']='01/02/1977'
    with pytest.raises(ValueError,match='opening conflict'):h.history_identity(text,canonical,{'history_page':1})


def test_coordinate_conflicts_not_repaired():
    assert h.coordinate_comparison(16.18138889,74.80111111,16.181,74.801)=='verified_source_coordinate'
    assert h.coordinate_comparison(16.56,74.52,16.556,74.502)=='source_coordinate_conflict'


def bbox_fixture(flag='*'):
    words=[]
    def word(text,x,y):words.append(f'<word xMin="{x}" xMax="{x+2}" yMin="{y}" yMax="{y+2}">{text}</word>')
    word('Day',100,10)
    for label,x in [('Jun',200),('Jul',300),('Aug',400),('Sep',500)]:word(label,x,10)
    word('OLD',0,0)
    for n in range(1,32):
        y=30+n*10;word(str(n),100,y)
        for x in [280,380]:word('100.5',x,y);word('2.5',x+25,y);word(flag,x+40,y)
    return ('<doc><page>'+''.join(words)+'</page></doc>').encode()


@pytest.mark.parametrize('flag,status',[('*','computed'),('#','discarded_replaced_by_rating_curve'),('', 'observed')])
def test_pdf_classes_temporal_window_no_transcription(flag,status):
    xml=bbox_fixture(flag)
    if not flag:xml=xml.replace(b'<word xMin="320" xMax="322" yMin=',b'<word xMin="320" xMax="322" yMin=')
    # Empty word still represents a blank quality token, accepted as observed.
    rows=h.parse_yearbook_xml(xml,{'yearbook_legacy_code':'OLD','canonical_cwc_station_id':KEY,'yearbook_name':'Fixture'},1)
    assert len(rows)==54
    assert all(h.START<=r['observation_date']<=h.END for r in rows)
    assert all(r['measurement_status']==status for r in rows if r['variable']=='discharge')
    assert all(r['temporal_semantics']=='daily_mean' for r in rows if r['variable']=='water_level')


def test_pdf_wrong_identity_and_unknown_quality_rejected():
    i={'yearbook_legacy_code':'OTHER','canonical_cwc_station_id':KEY,'yearbook_name':'Fixture'}
    with pytest.raises(ValueError,match='Wrong station'):h.parse_yearbook_xml(bbox_fixture(),i,1)
    i['yearbook_legacy_code']='OLD'
    with pytest.raises(ValueError,match='Unknown publisher'):h.parse_yearbook_xml(bbox_fixture('!'),i,1)


def test_table_bytes_deterministic_original_rows_unmodified():
    rows=[{'original_value':'001.2300','source_record':{'quality':'provisional'},'value':None}];before=deepcopy(rows)
    assert h.table_bytes(rows)==h.table_bytes(rows) and rows==before
    assert b'001.2300' in h.table_bytes(rows)
    with pytest.raises(ValueError,match='empty'):h.table_bytes([])


def snap(root):return {str(p.relative_to(root)):(p.read_bytes(),h.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def test_immutable_freeze_and_read_only_validation(monkeypatch,tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        root=Path(d);monkeypatch.setattr(h,'ROOT',root)
        raw=root/'data/raw/source';raw.mkdir(parents=True);(raw/'source.csv').write_text('controlled fixture')
        foundation=root/'data/working/karnataka_hydrology_stations_v1';foundation.mkdir(parents=True);(foundation/'registry.json').write_text('{}')
        code=root/'code.py';code.write_text('# fixture')
        actual=h.file_record;monkeypatch.setattr(h,'file_record',lambda p:actual(code if Path(p)==Path(h.__file__) else p))
        monkeypatch.setattr(h,'assemble',lambda raw:({'fixture.csv':b'column\nvalue\n'},{'readiness':'source_identity_unresolved'}))
        output=root/'data/working/output';h.freeze(output,raw);before=snap(root)
        assert h.validate(output)=={'readiness':'source_identity_unresolved'} and snap(root)==before
        with pytest.raises(ValueError,match='Immutable'):h.freeze(output,raw)
        assert snap(root)==before
        (output/'fixture.csv').write_text('corrupt')
        with pytest.raises(ValueError,match='integrity'):h.validate(output)


def test_bounded_fetch_failure_preserves_partial_and_prevents_retries(monkeypatch,tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        p=Path(d)/'source.csv'
        def timeout(*args,**kwargs):
            assert kwargs['timeout']==10
            p.write_bytes(b'original partial')
            raise subprocess.TimeoutExpired('fixture',10)
        monkeypatch.setattr(h.subprocess,'run',timeout)
        r=h.fetch('https://nwdp.nwic.gov.in/dataset/fixture/resource/r/download/source.csv',p,deadline=10)
        assert r['status']=='retrieval_failed' and p.read_bytes()==b'original partial'
        assert r['sha256']==h.digest(p)
        with pytest.raises(ValueError,match='never overwrite'):h.fetch('https://nwdp.nwic.gov.in/dataset/fixture/download/file.csv',p)


@pytest.mark.parametrize('url,deadline,ceiling',[('https://example.test/private',180,100),
    ('https://nwdp.nwic.gov.in/dataset/x/download/x.csv',181,100),
    ('https://nwdp.nwic.gov.in/dataset/x/download/x.csv',10,513*1024*1024)])
def test_live_fetch_contract_rejects_unbounded_or_nonpublished(monkeypatch,tmp_path,url,deadline,ceiling):
    with TemporaryDirectory(dir=tmp_path) as d:
        with pytest.raises(ValueError):h.fetch(url,Path(d)/'x',deadline=deadline,byte_ceiling=ceiling)
