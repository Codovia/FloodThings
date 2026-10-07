"""Offline Stage4E decision/topology/immutability fixtures. All writes are temporary."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec = importlib.util.spec_from_file_location('closure', Path(__file__).resolve().parents[2] / 'scripts/close_hydrology_semantics.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def candidates():
    return [{'cell_id': 'west', 'channel_positive': True, 'upstream_area_m2': 2811724288},
            {'cell_id': 'east', 'channel_positive': True, 'upstream_area_m2': 3907502592}]


def graph():
    return {c.cell_id(r, col): {'row': r, 'column': col, 'channel_positive': True, 'ldd_code': direction}
            for r, col, direction in [(0, 0, 6), (0, 1, 6), (-1, 1, 2), (1, 0, 9), (0, 2, 8)]}


@pytest.mark.parametrize('code,expected', [(1,'1:-1'),(2,'1:0'),(3,'1:1'),(4,'0:-1'),(5,None),
                                         (6,'0:1'),(7,'-1:-1'),(8,'-1:0'),(9,'-1:1'),(None,None)])
def test_pcraster_native_descending_latitude_direction(code, expected):
    assert c.target(0, 0, code) == expected


def test_two_candidates_connected_east_junction_preserved():
    original = graph(); before = deepcopy(original)
    assert c.trace('0:0', original) == {'cells': ['0:0','0:1','0:2'], 'stop': 'outside_bounded_window'}
    assert c.predecessors('0:1', original) == ['-1:1','0:0','1:0']
    assert original == before


@pytest.mark.parametrize('change,stop', [('channel','channel_not_marked_or_nodata'),
                                       ('missing','direction_unavailable'),('pit','model_pit')])
def test_missing_channel_and_direction_not_invented(change, stop):
    cells=graph()
    if change=='channel':cells['0:0']['channel_positive']=False
    if change=='missing':cells['0:0']['ldd_code']=None
    if change=='pit':cells['0:0']['ldd_code']=5
    assert c.trace('0:0',cells)['stop']==stop


def test_cycles_unknown_codes_and_unbounded_paths_rejected():
    cells=graph();cells['0:1']['ldd_code']=4
    with pytest.raises(ValueError, match='Cycle'):c.trace('0:0',cells)
    with pytest.raises(ValueError):c.target(0,0,255)
    with pytest.raises(ValueError):c.trace('0:0',cells,9)
    assert c.trace('0:0',cells,1)['stop']=='step_limit'


def test_area_distance_and_discharge_cannot_select_gauge_cell():
    rows=candidates();before=deepcopy(rows);decision=c.reach_decision(rows)
    assert decision['status']=='station_grid_match_ambiguous' and decision['selected_model_cell'] is None
    rows[0].update(discharge_peak=1e12, observed_match=True, distance_m=0, percent_difference=0)
    assert c.reach_decision(rows)==decision
    assert before[0]['upstream_area_m2']==2811724288 and before[1]['upstream_area_m2']==3907502592


@pytest.mark.parametrize('rows', [[], [candidates()[0]], [candidates()[0]]*2])
def test_both_candidates_required(rows):
    with pytest.raises(ValueError):c.reach_decision(rows)


def anchor():
    # Explicit controlled fixture only, never written as a research observation.
    return {'station_id': c.STATION, 'cell_id': 'west', 'source_type':'official_station_to_model_reach_link',
            'url':'https://cwc.gov.in/fixture', 'sha256':'a'*64, 'version':'5.0'}


def test_model_match_does_not_resolve_station_coordinate_conflict():
    a=anchor();before=deepcopy(a);r=c.reach_decision(candidates(),independent_anchor=a)
    assert r['selected_model_cell']=='west' and a==before
    assert r['station_coordinate_status']=='coordinate_conflict_unresolved'
    assert not r['canonical_coordinate_selected'] and not r['coordinate_conflict_resolved']


@pytest.mark.parametrize('change', ['magnitude','timing','nearest','authority','hash','version','station','cell','channel'])
def test_no_unsupported_anchor(change):
    a=anchor();rows=candidates()
    if change in {'magnitude','timing','nearest'}:a[change]=1
    if change=='authority':a['url']='https://example.org/not-official'
    if change=='hash':a['sha256']='bad'
    if change=='version':a['version']='4.0'
    if change=='station':a['station_id']='OTHER'
    if change=='cell':a['cell_id']='elsewhere'
    if change=='channel':rows[0]['channel_positive']=False
    with pytest.raises(ValueError):c.reach_decision(rows,independent_anchor=a)


def times():
    start=datetime(2019,8,1,tzinfo=timezone.utc);end=start+timedelta(days=1)
    m={'hydrology_source_type':'measured_cwc_nwdp','variable':'discharge','statistic':'mean','timezone':'UTC',
       'interval_start':start.isoformat(),'interval_end':end.isoformat(),'exact_field_documented':True}
    g={**m,'hydrology_source_type':'modelled_glofas'}
    return m,g


@pytest.mark.parametrize('field', ['statistic','timezone','interval_start','interval_end','exact_field_documented'])
def test_missing_semantics_prevent_pointwise_comparison(field):
    m,g=times();m[field]=None;r=c.temporal_decision(m,g)
    assert r['status']!='temporal_semantics_resolved' and not r['pointwise_comparison_allowed']
    assert r['aligned_quantitative_pairs']==0


@pytest.mark.parametrize('change', ['instantaneous','session','timezone','day','mean_gauge'])
def test_daily_label_or_measurement_session_is_not_daily_mean(change):
    m,g=times()
    if change in {'instantaneous','session','mean_gauge'}:m['statistic']=change
    if change=='timezone':m['timezone']='undocumented'
    if change=='day':m['interval_start']='2019-07-31T00:00:00+00:00'
    r=c.temporal_decision(m,g,contextual_evidence=True)
    assert r['status']=='temporal_semantics_partially_resolved' and not r['pointwise_comparison_allowed']


def test_exact_bounds_only_allow_comparison_not_metrics_features_labels():
    m,g=times();before=deepcopy((m,g));r=c.temporal_decision(m,g)
    assert r['status']=='temporal_semantics_resolved' and r['pointwise_comparison_allowed']
    assert r['aligned_quantitative_pairs']==r['features_created']==r['flood_labels_created']==0
    assert not r['performance_metrics_allowed'] and (m,g)==before


@pytest.mark.parametrize('change', ['naive','hourly','backwards'])
def test_bounds_must_be_explicit_utc_24_hours(change):
    m,g=times()
    if change=='naive':m['interval_start']=g['interval_start']='2019-08-01T00:00:00'
    if change=='hourly':m['interval_end']=g['interval_end']='2019-08-01T01:00:00+00:00'
    if change=='backwards':m['interval_end']=g['interval_end']='2019-07-31T00:00:00+00:00'
    with pytest.raises(ValueError):c.temporal_decision(m,g)


@pytest.mark.parametrize('change', ['measured_is_modelled','model_is_measured','water_level'])
def test_source_separation_and_no_water_level_feature_use(change):
    m,g=times()
    if change=='measured_is_modelled':m['hydrology_source_type']='modelled_glofas'
    if change=='model_is_measured':g['hydrology_source_type']='measured_cwc_nwdp'
    if change=='water_level':m['variable']=g['variable']='water_level'
    with pytest.raises(ValueError):c.temporal_decision(m,g)


@pytest.mark.parametrize('reach,time,status', [
    ('station_grid_match_ambiguous','temporal_semantics_unresolved','hydrology_semantics_blocked_by_source_metadata'),
    ('station_grid_match_ambiguous','temporal_semantics_partially_resolved','hydrology_semantics_ready_limited'),
    ('station_grid_match_supported','temporal_semantics_unresolved','hydrology_semantics_ready_limited'),
    ('station_grid_match_supported','temporal_semantics_resolved','hydrology_semantics_ready')])
def test_readiness_from_evidence_not_schedule(reach,time,status):
    assert c.readiness(reach,time)==status
    with pytest.raises(ValueError):c.readiness(reach,'invented_complete')


def test_immutable_build_validation_bytes_hash_size_mtime_and_provenance(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root=Path(folder);source=root/'official.html';source.write_bytes(b'controlled source fixture\r\n')
        monkeypatch.setattr(c,'ROOT',root)
        inputs=[{**c.record(source),'url':'https://cwc.gov.in/fixture'}]
        product={'summary.json':c.encode({'status':'hydrology_semantics_ready_limited','pairs':0})}
        monkeypatch.setattr(c,'inputs',lambda:deepcopy(inputs))
        monkeypatch.setattr(c,'assemble',lambda:(deepcopy(product),{'pairs':0}))
        # This module lies outside temporary ROOT; isolate its code record too.
        old_record=c.record
        monkeypatch.setattr(c,'record',lambda p: {'path':'code.py','bytes':1,'sha256':'b'*64} if Path(p)==Path(c.__file__) else old_record(p))
        output=root/'version';c.build(output)
        paths=[source,*output.iterdir()]
        before={p:(p.read_bytes(),c.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths}
        assert c.validate(output)=={'pairs':0}
        assert before=={p:(p.read_bytes(),c.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths}
        manifest=c.read(output/'manifest.json')
        assert manifest['inputs'][0]['url'].startswith('https://cwc.gov.in/')
        assert manifest['inputs'][0]['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
        with pytest.raises(ValueError,match='Immutable'):c.build(output)
        (output/'summary.json').write_bytes(b'corrupted')
        with pytest.raises(ValueError,match='reproduction'):c.validate(output)


def test_input_checksum_change_fails_readonly_validation(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root=Path(folder);output=root/'version';output.mkdir();manifest=output/'manifest.json'
        manifest.write_bytes(c.encode({'inputs':[{'sha256':'a'*64}],'processing_code':{}}))
        before=(manifest.read_bytes(),manifest.stat().st_mtime_ns)
        monkeypatch.setattr(c,'inputs',lambda:[{'sha256':'b'*64}])
        with pytest.raises(ValueError,match='Input/code'):c.validate(output)
        assert (manifest.read_bytes(),manifest.stat().st_mtime_ns)==before


def test_encoding_deterministic_finite_only():
    assert c.encode({'b':2,'a':1})==c.encode({'a':1,'b':2})
    with pytest.raises(ValueError):c.encode({'value':float('nan')})
    r=c.temporal_decision({'hydrology_source_type':'measured_cwc_nwdp','variable':'discharge'},
                          {'hydrology_source_type':'modelled_glofas','variable':'discharge'})
    assert r['status']=='temporal_semantics_unresolved' and r['aligned_quantitative_pairs']==0
    assert r['flood_labels_created']==0 and r['features_created']==0


def test_official_static_urls_hashes_units_and_retrieval_times_preserved(tmp_path,monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root=Path(folder);static=root/'static';prior=root/'prior';static.mkdir();prior.mkdir()
        names=['upArea_repaired_correctedmetadata_3000.nc','chan_Global_03min.nc','ldd_repaired.nc']
        for name in names:(static/name).write_bytes(b'fixture only, not a real NetCDF')
        provenance={'upstream_area':{'retrieved_at':None}, 'auxiliary_downloads':{
            'channel':{'retrieved_at':'2026-01-01T00:00:00+00:00'},
            'direction_resume':{'retrieved_at':'2026-01-02T00:00:00+00:00'}},
            'release_evidence':{'changelog_url':'https://jeodpp.jrc.ec.europa.eu/fixture'}}
        (prior/'source_provenance.json').write_bytes(c.encode(provenance))
        monkeypatch.setattr(c,'ROOT',root);monkeypatch.setattr(c,'STATIC',static);monkeypatch.setattr(c,'PRIOR',prior)
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in [*static.iterdir(),*prior.iterdir()]}
        r=c.static_register()
        assert r==c.static_register() and r['model_compatibility']=='5.x' and r['licence']=='CC BY4.0'
        assert r['files'][0]['retrieved_at'] is None
        assert 'official README' in r['units']['upstream_area']
        for row,name in zip(r['files'],names):
            assert row['url'].endswith('/v2.1.1_OS-LISFLOOD-v5.x/Catchments_morphology_and_river_network/'+name)
            assert row['sha256']==c.digest(static/name) and not row['redownloaded_in_stage4e']
        assert before=={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before}
