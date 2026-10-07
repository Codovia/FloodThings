"""Controlled offline processing fixtures; every write is temporary and removed."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('glofas_pilot', Path(__file__).resolve().parents[2] / 'scripts/build_glofas_pilot.py')
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


def test_native_grid_nearest_and_exact_alignment():
    axis = [1.975,1.925,1.875]
    assert g.nearest(axis,1.93)==1 and g.aligned(axis,1.925)==1
    with pytest.raises(ValueError): g.aligned(axis,1.93)
    with pytest.raises(ValueError): g.nearest(axis,2.1)
    with pytest.raises(ValueError): g.nearest([float('nan')],1)


def test_haversine_distance_is_metric_and_symmetric():
    assert g.distance([0,0],[0,1]) == pytest.approx(111195.0802,rel=1e-6)
    assert g.distance([1,2],[1,2])==0
    assert g.distance([1,2],[3,4])==g.distance([3,4],[1,2])


def history():
    return {'canonical_coordinate_selected':False,'coordinates_modified':False,'source_history':[
        {'source':'old','publication':'fixture','original':{'latitude':1.1,'longitude':2.1}},
        {'source':'portal','resource_update':'fixture','original_fields':{'Latitude':['1.2'],'Longitude':['2.2']}},
        {'source':'book','coordinates':[1.3,2.3]},
        {'source':'new','original':{'latitude':1.1,'longitude':2.1}}]}


def test_coordinate_history_conflicts_preserved_without_averaging():
    h=history();original=deepcopy(h);r=g.coordinates(h)
    assert h==original and len(r)==4
    assert [x['latitude'] for x in r]==[1.1,1.2,1.3,1.1]
    assert r[0]['source']=='old' and r[-1]['source']=='new'


@pytest.mark.parametrize('field', ['canonical_coordinate_selected','coordinates_modified'])
def test_coordinate_repair_disallowed(field):
    h=history();h[field]=True
    with pytest.raises(ValueError):g.coordinates(h)


@pytest.mark.parametrize('area', [-1,float('nan'),float('inf')])
def test_invalid_upstream_area_rejected(area):
    with pytest.raises(ValueError):g.area_comparison(area,2)


def test_upstream_units_signed_absolute_percent_and_missing():
    r=g.area_comparison(2200000,2)
    assert r['upstream_area_km2']==2.2
    assert r['signed_difference_km2']==pytest.approx(.2)
    assert r['absolute_difference_km2']==pytest.approx(.2)
    assert r['percent_difference']==pytest.approx(10)
    assert all(v is None for v in g.area_comparison(None,2).values())
    assert g.scalar(np.ma.masked) is None and g.scalar(float('nan')) is None
    assert g.scalar(0)==0  # Actual zero differs from missing.
    with pytest.raises(ValueError):g.area_comparison(2,0)


def test_cwc_column_heading_and_units_required():
    s={'station_id':'FIXTURE','source_history':[{'source':'CWC_HO2025','original':
        {'latitude':1.2,'longitude':2.3,'source_cells':['']*9+['123']}}]}
    text='Catchment Area (Sq.km)\n1.2 2.3 123 HO/FF FIXTURE'
    assert g.cwc_area(s,text)==123
    for bad in [text.replace('Sq.km','m'),text.replace('Catchment','Level'),text.replace('123','124')]:
        with pytest.raises(ValueError):g.cwc_area(s,bad)


def test_gokak_style_coordinate_ambiguity_not_discarded():
    direct=[{'cell_id':'east'}]*3+[{'cell_id':'west'}]
    candidates=[{'cell_id':'east','channel_positive':True,'percent_difference':41},
        {'cell_id':'west','channel_positive':True,'percent_difference':1}]
    result=g.mapping(direct,candidates)
    assert result['status']=='glofas_cell_match_ambiguous' and result['selected_cell'] is None
    assert result['coordinate_candidate_cells']==['east','west']


@pytest.mark.parametrize('channel,error,status', [(True,5,'glofas_cell_match_supported'),
    (False,5,'glofas_cell_match_unresolved'),(True,41,'glofas_cell_match_unresolved'),
    (True,None,'glofas_cell_match_unresolved')])
def test_nearest_only_does_not_establish_match(channel,error,status):
    row={'cell_id':'a','channel_positive':channel,'percent_difference':error}
    r=g.mapping([{'cell_id':'a'}]*4,[row])
    assert r['status']==status
    assert (r['selected_cell']=='a')==(status=='glofas_cell_match_supported')


def test_no_discharge_magnitude_selection():
    row={'cell_id':'a','channel_positive':True,'percent_difference':5,'discharge_peak':0}
    original=g.mapping([{'cell_id':'a'}]*4,[row]);row['discharge_peak']=1e12
    assert g.mapping([{'cell_id':'a'}]*4,[row])==original


def clocks():
    start=datetime(2019,7,2,tzinfo=timezone.utc)
    return [start+timedelta(days=i) for i in range(62)]


def test_original_timestamp_and_interpreted_bounds_remain_separate():
    t=clocks();before=deepcopy(t);r=g.intervals(t)
    assert t==before and len(r)==62
    assert r[0]['model_valid_time']=='2019-07-02T00:00:00+00:00'
    assert r[0]['interpreted_interval_start']=='2019-07-01T00:00:00+00:00'
    assert r[-1]['model_valid_time']=='2019-09-01T00:00:00+00:00'
    assert 'file_bounds_absent' in r[0]['interval_status']
    assert not any('flood_label' in x or 'observation_date' in x for x in r)


@pytest.mark.parametrize('change', ['duplicate','gap','wrong_start','hourly'])
def test_invalid_time_grid_rejected(change):
    t=clocks()
    if change=='duplicate':t[1]=t[0]
    if change=='gap':t.pop(1)
    if change=='wrong_start':t=[x+timedelta(days=1) for x in t]
    if change=='hourly':t[1]=t[0]+timedelta(hours=1)
    with pytest.raises(ValueError):g.intervals(t)


def quality():
    return [{'canonical_cwc_station_id':g.STATIONS[0] if i<2 else g.STATIONS[2],
        'variable':'discharge','frequency':'daily','units':'m3/sec','analysis_eligibility':'eligible_with_quality_caveat',
        'observation_time':'fixture','observation_timezone':'not_documented','original_value':'fixture',
        'source_row_number':str(i),'source_resource_id':'fixture','source_quality_status':'unverified'} for i in range(14)]


def test_source_separation_and_no_pointwise_comparisons_without_time_equivalence():
    q=quality();before=deepcopy(q);r=g.comparison_evidence(q)
    assert q==before and len(r)==14
    assert all(x['hydrology_source_type']=='measured_cwc_nwdp' and x['modelled_source_type']=='modelled_glofas' for x in r)
    assert all(x['paired_modelled_discharge'] is None and x['model_minus_measured'] is None for x in r)
    assert {x['comparison_status'] for x in r}=={'temporal_semantics_unresolved'}
    assert not any('flood_label' in x or 'danger_level' in x or 'model_accuracy' in x for x in r)


@pytest.mark.parametrize('field,value', [('variable','water_level'),('frequency','hourly'),
    ('units','meter'),('analysis_eligibility','retain_not_use_for_features'),
    ('canonical_cwc_station_id',g.STATIONS[1])])
def test_no_water_levels_conflicts_or_gokak_quantitative_comparison(field,value):
    q=quality();q[0][field]=value
    assert not g.comparison_eligible(q[0])
    with pytest.raises(ValueError):g.comparison_evidence(q)


def test_immutable_manifest_checksums_and_readonly_validation(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        output=Path(folder)/'version';artifact={'notes.json':g.encode({'source_type':'modelled_glofas','labels':0})}
        monkeypatch.setattr(g,'assemble',lambda:(artifact,{'labels':0,'features':0}))
        monkeypatch.setattr(g,'source_inputs',lambda:[])
        g.build(output);before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in output.iterdir()}
        assert g.validate(output)=={'labels':0,'features':0}
        assert all(v==(p.read_bytes(),p.stat().st_mtime_ns) for p,v in before.items())
        with pytest.raises(ValueError,match='Immutable'):g.build(output)
        manifest=json.loads((output/'manifest.json').read_bytes());manifest['files']['notes.json']['sha256']='wrong'
        (output/'manifest.json').write_bytes(g.encode(manifest))
        with pytest.raises(ValueError,match='reproduction'):g.validate(output)


def test_source_checksum_change_detected(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        source=Path(folder)/'source';source.write_bytes(b'original official fixture bytes')
        output=Path(folder)/'version'
        monkeypatch.setattr(g,'assemble',lambda:({'notes.json':b'{}\n'},{'labels':0}))
        monkeypatch.setattr(g,'source_inputs',lambda:[{'sha256':g.digest(source)}])
        g.build(output);source.write_bytes(b'corrupted')
        with pytest.raises(ValueError,match='Input'):g.validate(output)


def test_fixed_direction_codes():
    assert g.LDD[6]==(0,1) and g.LDD[9]==(-1,1) and g.LDD[5]==(0,0)
    assert set(g.LDD)==set(range(1,10))
