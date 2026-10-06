"""Controlled offline fixtures; no source observations enter research directories."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

import pytest

SPEC = importlib.util.spec_from_file_location(
    "hydrology_foundation", Path(__file__).resolve().parents[2] / "scripts/verify_karnataka_hydrology.py")
h = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h)


def station():
    return {"source_station_id": "CW1ABC000001", "official_name": "Fixture source name",
            "project_alias": None, "source_state": "Karnataka", "source_type": "GD",
            "source_purpose": "HO", "source_basin": "Fixture basin",
            "variables": ["gauge_level", "discharge"], "latitude": 15., "longitude": 75.,
            "coordinate_status": "verified_source_coordinate",
            "temporal_coverage": {"earliest_verified_observation": None,
                                  "latest_verified_observation": None, "continuity": "unverified"}}


def snapshot(directory):
    return {str(p.relative_to(directory)): (p.read_bytes(), h.digest(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in directory.rglob('*') if p.is_file()}


def test_unique_and_conflicting_ids():
    row = station()
    assert h.validate_registry([row])
    with pytest.raises(ValueError, match="Duplicate station ID"):
        h.validate_registry([row, deepcopy(row)])
    other = deepcopy(row)
    other['longitude'] = 74
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        h.validate_registry([row, other])


@pytest.mark.parametrize('lat,lon', [(91,75),(15,181),(float('nan'),75),(15,float('inf')),(True,75)])
def test_invalid_coordinates(lat,lon):
    with pytest.raises(ValueError):
        h.coordinate_status(lat,lon)


@pytest.mark.parametrize('kwargs,expected', [({},'verified_source_coordinate'),
    ({'conflict':True},'source_coordinate_conflict'),
    ({'state_consistent':False},'geographic_assignment_unresolved')])
def test_coordinate_flags(kwargs,expected):
    assert h.coordinate_status(15,75,**kwargs) == expected


def test_missing_coordinate_is_unknown():
    assert h.coordinate_status(None,75) == 'coordinate_missing'


@pytest.mark.parametrize('change', [{'source_station_id':None},{'official_name':''},
    {'variables':['invented_flow']},{'variables':['discharge','discharge']},
    {'coordinate_status':'repaired'}])
def test_registry_invalid_fields(change):
    row = station(); row.update(change)
    with pytest.raises(ValueError): h.validate_registry([row])


def test_temporal_coverage_never_inferred_from_start():
    row = station(); row['source_start_dates_cell'] = '01.01.1900'
    original = deepcopy(row)
    h.validate_registry([row])
    assert row == original and row['temporal_coverage']['earliest_verified_observation'] is None
    row['temporal_coverage'].update(earliest_verified_observation='2025-02-01',latest_verified_observation='2025-01-01')
    with pytest.raises(ValueError, match='Reversed'): h.validate_registry([row])


def metadata_fixture():
    cells = ['1','Fixture name','Karnataka','Fixture district','Fixture river','GD',
             '01.01.2000\n01.02.2000','15.000','75.000','10','HO','CW1ABC000001']
    tables = [{'page':1,'rows':[cells]}]
    reviewed = {'CW1ABC000001':{'page':1,'source_id_cell':cells[11],
        'source_name_cell':cells[1],'visible_name':cells[1],'basin':'Fixture basin'}}
    return tables,reviewed


def test_source_values_and_alias_preserved():
    tables,reviewed = metadata_fixture(); original = deepcopy((tables,reviewed))
    rows = h.parse_metadata(tables,reviewed)
    assert (tables,reviewed) == original
    assert rows[0]['source_cells'] == tables[0]['rows'][0]
    assert rows[0]['project_alias'] is None
    assert rows[0]['variable_units'] == {'gauge_level':None,'discharge':None}
    assert rows[0]['temporal_coverage']['continuity'] == 'unverified'


def test_review_cannot_guess_source_id():
    tables,reviewed = metadata_fixture()
    reviewed['CW1ABC000001']['source_id_cell']='CW1ABC000002'
    with pytest.raises(ValueError,match='Review'): h.parse_metadata(tables,reviewed)


def test_unreviewed_metadata_rejected():
    tables,_ = metadata_fixture()
    with pytest.raises(ValueError,match='Unreviewed'): h.parse_metadata(tables,{})


def observation(value='2.5', variable='discharge', **kwargs):
    return h.normalize_observation({'Station':'Fixture','Data Acquisition Time':'10-08-2019 10:00','measurement':value},
        variable,'measurement','m3/sec' if variable=='discharge' else 'meter',
        station_id='CW1ABC000001',source={'kind':'measured','url':'https://example.test/fixture'},
        start='2019-08-01',end='2019-08-20',**kwargs)


@pytest.mark.parametrize('value',[None,'','-'])
def test_missing_measurements_are_not_zero(value):
    assert observation(value)['value'] is None


@pytest.mark.parametrize('value',['nan','inf','-1',True])
def test_invalid_discharge(value):
    with pytest.raises(ValueError): observation(value)


@pytest.mark.parametrize('variable',['gauge_level','discharge','reservoir_inflow','reservoir_outflow','reservoir_storage'])
def test_variable_and_units_not_conflated(variable):
    row = observation(variable=variable)
    assert row['variable'] == variable
    assert row['units'] == ('m3/sec' if variable=='discharge' else 'meter')
    assert row['datum']=='not_documented' and row['source_record']['measurement']=='2.5'


def test_negative_gauge_with_unknown_datum_retained():
    assert observation('-0.5',variable='gauge_level')['value'] == -0.5


def test_modelled_source_is_not_measured():
    with pytest.raises(ValueError,match='measured'):
        h.normalize_observation({'measurement':'1'},'discharge','measurement','m3/sec',station_id='fixture',
            source={'kind':'modelled'},start='2019-08-01',end='2019-08-20')


def test_prediction_time_unknown_and_evidence_required():
    row = observation()
    assert row['availability_time'] is None and row['availability_status']=='availability_semantics_unverified'
    assert row['observation_time']=='2019-08-10T10:00:00'
    assert row['observation_timezone']=='not_documented'
    with pytest.raises(ValueError,match='evidence'):
        observation(availability_time='2019-08-10T11:00:00')
    row = observation(availability_time='2019-08-11T10:00:00',availability_evidence='fixture bulletin')
    assert row['availability_time'] != row['observation_time']


def test_outside_event_context_refused():
    with pytest.raises(ValueError,match='outside'):
        h.normalize_observation({'Station':'Fixture','Data Acquisition Time':'10-08-2020 10:00','m':'1'},
            'gauge_level','m','meter',station_id='fixture',source={'kind':'measured'},start='2019-08-01',end='2019-08-20')


def test_missing_units_refused():
    with pytest.raises(ValueError,match='units'):
        h.normalize_observation({},'gauge_level','m',None,station_id='fixture',source={'kind':'measured'},
            start='2019-08-01',end='2019-08-20')


def test_threshold_semantics_and_anomalies_preserved():
    r={'warning_level':2.,'danger_level':3.,'highest_flood_level':1.}
    original=deepcopy(r)
    assert 'recorded_hfl_below_danger; source_value_retained' in h.threshold_flags(r)
    assert 'vertical_datum_unverified' in h.threshold_flags(r) and r==original
    with pytest.raises(ValueError): h.threshold_flags({'warning_level':float('nan')})


def test_inflow_is_not_warning_level_and_keeps_2024_table_vintage():
    cells=['1','Fixture river','Fixture reservoir','Karnataka','Fixture district','100','101','500','x','y']
    r=h.parse_sop([{'page':1,'kind':'inflow_forecast','cells':cells}])[0]
    assert r['source_station_id'] is None
    assert r['warning_level'] is None and r['danger_level'] is None
    assert r['full_reservoir_level_cell']=='100' and r['inflow_threshold_cell']=='500'
    assert r['inflow_threshold_units']=='cumec' and r['source_table_reference']=='flood season2024'
    assert not r['actual_reservoir_observations_retrieved']


def test_missing_sop_threshold_not_zero():
    cells=['1','Fixture river','Fixture site','Karnataka','Fixture district','','','5','01.01.2000','x']
    r=h.parse_sop([{'page':1,'kind':'monitoring_only','cells':cells}])[0]
    assert r['warning_level'] is None and r['danger_level'] is None
    assert r['highest_flood_level']==5 and r['source_table_reference']=='flood season2025'


@pytest.mark.parametrize('relationship',sorted(h.RELATIONSHIPS))
def test_relationship_vocabulary(relationship):
    assert h.validate_relationship({'relationship':relationship,'event_start':'2019-08-01','event_end':'2019-08-02',
        'event_source':'fixture report','station_source':'fixture metadata'})


@pytest.mark.parametrize('changes',[{'relationship':'caused_flood'}, {'event_end':'2019-07-01'},
    {'event_source':None},{'observation_time':'2019-08-01'}, {'daily_flood_label':True}])
def test_documentary_interval_cannot_be_observation_or_label(changes):
    r={'relationship':'same_river_or_basin_supported','event_start':'2019-08-01','event_end':'2019-08-02',
       'event_source':'fixture report','station_source':'fixture metadata'}
    r.update(changes)
    with pytest.raises(ValueError): h.validate_relationship(r)


def test_http_success_is_not_application_success_or_unbounded_rows():
    for response in [{'success':False},{'success':True,'result':{}},
                     {'success':True,'result':{'records':[{},{}]}}]:
        with pytest.raises(ValueError): h.parse_response(json.dumps(response),1)
    assert h.parse_response('{"success":true,"result":{"records":[]}}',1)['records']==[]


@pytest.mark.parametrize('stations,counts,probe,expected',[(0,[0],0,'hydrology_foundation_incomplete'),
    (1,[0,0],0,'station_registry_ready_data_access_blocked'),
    (1,[0,0],1,'station_registry_ready_data_access_partial'),
    (1,[1,0],0,'station_registry_ready_data_access_partial'),(2,[1,1],0,'measured_hydrology_ready')])
def test_readiness_from_actual_access(stations,counts,probe,expected):
    assert h.readiness(stations,counts,probe)==expected


def test_bounded_bbox_reproduction_preserves_empty_cells():
    xml=b'<doc><page><word xMin="1" yMin="10" yMax="12">1</word><word xMin="21" yMin="10" yMax="12">name</word></page></doc>'
    layout=[{'page':1,'kind':'fixture','first':1,'last':1,'columns':[0,10,20,30]}]
    rows=h.parse_bbox_rows(xml,layout)
    assert rows[0]['cells']==['1','','name'] and rows==h.parse_bbox_rows(xml,layout)
    layout[0]['last']=2
    with pytest.raises(ValueError,match='Missing'): h.parse_bbox_rows(xml,layout)


def test_bbox_entities_rejected():
    with pytest.raises(ValueError,match='Unsafe'): h.parse_bbox_rows(b'<!ENTITY a "x"><doc/>',[])


def test_optional_pdf_reader_is_bounded_and_read_only(monkeypatch):
    tables, _=metadata_fixture()
    rows=[['SITE CODE']]+tables[0]['rows']
    page=SimpleNamespace(extract_tables=lambda:[rows])
    class Document:
        pages=[page]
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setitem(sys.modules,'pdfplumber',SimpleNamespace(__version__='0.11.9',open=lambda path:Document()))
    assert h.metadata_pdf_tables('fixture.pdf',[1])==[{'page':1,'bbox':None,'rows':rows}]
    with pytest.raises(ValueError,match='Bound'): h.metadata_pdf_tables('fixture.pdf',[1]*21)


def setup_freeze(monkeypatch,root):
    monkeypatch.setattr(h,'ROOT',root)
    raw=root/'data/raw/fixture'; raw.mkdir(parents=True)
    (raw/'source.json').write_bytes(b'{"fixture":true}\n')
    geometry=root/'data/working/karnataka_soi_abdb2025_v1'; geometry.mkdir(parents=True)
    (geometry/'fixture.txt').write_text('Controlled input; no real geometry')
    code=root/'processing_fixture.py'; code.write_text('# controlled processing fixture\n')
    actual_file_record=h.file_record
    monkeypatch.setattr(h,'file_record',lambda p:actual_file_record(code if Path(p)==Path(h.__file__) else p))
    artifacts={'station_registry.json':[station()], 'flood_station_inventory.json':[],
               'source_availability.json':{'pilot':[{'observations_retrieved':0}], 'sources':[],
                                          'public_access_probe_observations_outside_pilot':0}}
    monkeypatch.setattr(h,'assemble',lambda raw:deepcopy(artifacts))
    return raw,root/'data/working/output'


def test_freeze_validate_publication_and_byte_mtime_preservation(monkeypatch,tmp_path):
    with TemporaryDirectory(dir=tmp_path) as d:
        root=Path(d); raw,output=setup_freeze(monkeypatch,root)
        h.freeze(output,raw,created_at='2026-10-07T00:00:00+00:00')
        before=snapshot(root)
        assert h.validate(output)['pilot_observations']==0
        public=h.public_manifest(output)
        assert snapshot(root)==before
        assert h.json_bytes(public)==h.json_bytes(h.public_manifest(output))
        assert 'latitude' not in h.json_bytes(public).decode()
        assert 'Fixture source name' not in h.json_bytes(public).decode()
        with pytest.raises(ValueError,match='Immutable'): h.freeze(output,raw)
        assert snapshot(root)==before


@pytest.mark.parametrize('alter_input',[False,True])
def test_corrupt_source_or_output_refused(monkeypatch,tmp_path,alter_input):
    with TemporaryDirectory(dir=tmp_path) as d:
        root=Path(d); raw,output=setup_freeze(monkeypatch,root)
        h.freeze(output,raw,created_at='2026-10-07T00:00:00+00:00')
        p=raw/'source.json' if alter_input else output/'station_registry.json'
        p.write_bytes(p.read_bytes()+b' ')
        with pytest.raises(ValueError,match='integrity|checksum'): h.validate(output)
