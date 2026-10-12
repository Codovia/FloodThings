"""Synthetic fixtures, temporary SQLite/Parquet only; no external/data writes."""
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import socket
import sys

import pytest
import shapely
from shapely.geometry import Polygon, box, Point

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import acquire_groundsource as acquire
import audit_groundsource_karnataka as audit


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args,**kwargs):raise AssertionError("No network in audit fixtures")
    monkeypatch.setattr(socket,"create_connection",blocked)
    monkeypatch.setattr(socket.socket,"connect",blocked)


@pytest.fixture
def boundaries():
    districts=[{"id":"fixture:left","name":"Fixture left","nic_exact_name":None,"supplied_lgd_code_unverified":"not-an-lgd-id","geometry":box(0,0,5,10)},
               {"id":"fixture:right","name":"Fixture right","nic_exact_name":None,"supplied_lgd_code_unverified":"also-not-lgd","geometry":box(5,0,10,10)}]
    return {"state":box(0,0,10,10),"wgs84_bounds":(0,0,10,10),"to_native":lambda x,y:(x,y),
            "districts":districts,"tree":shapely.STRtree([d['geometry'] for d in districts]),
            "manifest":{"current_lgd_verified_identities":0,"nic_exact_name_candidates":0}}


def row(geom,uuid="fixture-uuid",start="2025-08-01",end="2025-08-02",area=1.0):
    return {"uuid":uuid,"geometry":geom.wkb if geom is not None else None,"start_date":start,"end_date":end,
            "area_km2":area,"__index_level_0__":0}


@pytest.mark.parametrize("geom,state,district",[
    (box(1,1,2,2),"DEFINITE_WITHIN_SOURCE_STATE","fixture:left"),
    (box(-1,1,2,2),"CROSS_STATE_INTERSECTION",None),
    (box(-1,1,0,2),"STATE_BOUNDARY_TOUCH_ONLY",None),
    (box(4,1,6,2),"DEFINITE_WITHIN_SOURCE_STATE",None),
    (box(0,0,5,10),"DEFINITE_WITHIN_SOURCE_STATE","fixture:left"),
])
def test_containment_intersection_and_touch_are_distinct(boundaries,geom,state,district):
    status,result=audit.geometry_screen(geom.wkb,boundaries)
    assert status=="VALID_AREAL_GEOMETRY" and result['state_status']==state
    assert result['definite_district_id']==district


def test_bbox_hit_outside_exact_state_is_excluded(boundaries):
    boundaries['state']=Polygon([(0,0),(10,0),(0,10)])
    status,result=audit.geometry_screen(box(8,8,9,9).wkb,boundaries)
    assert status=="VALID_AREAL_GEOMETRY" and result is None


@pytest.mark.parametrize("body,status",[(None,"MISSING_WKB"),(b"not-wkb","INVALID_WKB"),(Polygon().wkb,"EMPTY_GEOMETRY")])
def test_missing_empty_bad_wkb_do_not_create_candidates(boundaries,body,status):
    assert audit.geometry_screen(body,boundaries)==(status,None)


def test_invalid_and_nonareal_candidates_remain_separate_without_repair(boundaries):
    bow=Polygon([(1,1),(3,3),(1,3),(3,1),(1,1)])
    before=bow.wkb
    status,result=audit.geometry_screen(before,boundaries)
    assert status=="INVALID_GEOMETRY" and result['state_status']=="INVALID_OR_AMBIGUOUS_BBOX_SCREEN"
    assert result['native_geometry'] is None and bow.wkb==before
    status,result=audit.geometry_screen(Point(2,2).wkb,boundaries)
    assert status=="NON_AREAL_GEOMETRY" and result['state_status']=="INVALID_OR_AMBIGUOUS_BBOX_SCREEN"


def test_invalid_coordinates_and_antimeridian_are_not_definite(boundaries):
    for geom,status in [(box(-181,1,2,2),"INVALID_COORDINATES"),(box(-179,1,179,2),"AMBIGUOUS_ANTIMERIDIAN")]:
        actual,result=audit.geometry_screen(geom.wkb,boundaries)
        assert actual==status and result['state_status']=="INVALID_OR_AMBIGUOUS_BBOX_SCREEN"


@pytest.mark.parametrize("start,end,status",[
    ("2025-08-01","2025-08-01","USABLE_REPORTED_DATE_RANGE"),
    ("2025-08-02","2025-08-01","REVERSED_INTERVAL"),
    (None,"2025-08-01","MISSING_OR_INVALID_DATE"),
    ("2025-02-30","2025-03-01","MISSING_OR_INVALID_DATE"),
    ("2025-8-1","2025-08-02","MISSING_OR_INVALID_DATE"),
    ("2026-10-13","2026-10-13","FUTURE_DATE_REQUIRES_REVIEW"),
])
def test_date_ranges_are_not_daily_observations(start,end,status):
    actual,duration=audit.date_status(start,end);assert actual==status
    if status!="USABLE_REPORTED_DATE_RANGE":assert duration is None


def test_screening_usable_does_not_certify_label(boundaries):
    r=row(box(1,1,2,2),area=float('nan'))
    _,screen=audit.geometry_screen(r['geometry'],boundaries)
    result=audit.record_candidate(r,7,screen)
    assert result['geographic_temporal_screening_usable'] and result['single_district_screening_usable']
    assert result['supplied_polygon_area_km2'] is None
    assert result['manual_verification_required'] and not result['flood_label_eligible'] and not result['negative_label']


def test_global_and_candidate_duplicates_preserve_every_original(tmp_path,boundaries):
    db=audit.database(tmp_path/'fixture.sqlite')
    rows=[row(box(1,1,2,2)),row(box(1,1,2,2)),row(box(20,20,21,21)),
          row(box(1,1,2,2),uuid='different-uuid'),row(box(4,1,6,2),uuid='multi-district',start='2025-09-01',end='2025-09-01')]
    counts=audit.scan(iter(rows),db,boundaries)
    assert counts['rows_scanned']==5 and db.execute('SELECT count(*) FROM candidates').fetchone()[0]==4
    assert db.execute('SELECT rows,conflicting FROM global_ids WHERE uuid=?',('fixture-uuid',)).fetchone()==(3,1)
    report=audit.summarize(db,counts,boundaries,audit.overlap_screen(db),{}, {'fixture':True})
    assert report['duplicates']['global_repeated_uuid_groups']==1
    assert report['duplicates']['candidate_excess_uuid_rows']==1
    assert report['duplicates']['candidate_excess_geometry_date_rows']==2
    assert report['manual_verification_required']==4 and report['training_readiness']['decision']=='NO-GO'
    matrix,districts,years=audit.coverage(db,boundaries)
    august=[r for r in matrix if r['year']==2025 and r['source_district_id']=='fixture:left'][0]
    assert august['intersecting_report_records']==4 and august['fully_contained_report_records']==3
    year=[r for r in years if r['start_year']==2025][0]
    assert year['reported_candidates']==4  # multi-district record counts only once here
    assert all(r['verified_negative_labels']==0 and r['unreported_unit_days']=='UNKNOWN_NOT_NEGATIVE' for r in matrix)
    assert all(not r['current_lgd_verified'] for r in districts)
    db.close()


def test_geometry_normalization_detects_ring_order_aliases(tmp_path,boundaries):
    geom=box(1,1,2,2);rotated=Polygon(list(geom.exterior.coords)[2:-1]+list(geom.exterior.coords)[:3])
    _,a=audit.geometry_screen(geom.wkb,boundaries);_,b=audit.geometry_screen(rotated.wkb,boundaries)
    assert a['normalized_geometry_sha256']==b['normalized_geometry_sha256']


def test_overlap_cap_is_reported_as_lower_bound_and_no_merge(tmp_path,boundaries):
    db=audit.database(tmp_path/'fixture.sqlite')
    audit.scan(iter([row(box(1,1,2,2),uuid=f'fixture-{n}') for n in range(4)]),db,boundaries)
    report=audit.overlap_screen(db,limit=2)
    assert not report['exhaustive'] and report['comparisons']==2 and report['positive_area_date_overlap_pairs']==2
    assert report['count_status'].startswith('LOWER_BOUND')
    assert db.execute('SELECT count(*) FROM candidates').fetchone()[0]==4
    db.close()


def test_exact_overlap_excludes_touch_only_and_disjoint_dates(tmp_path,boundaries):
    db=audit.database(tmp_path/'fixture.sqlite')
    audit.scan(iter([row(box(1,1,2,2),'a'),row(box(2,1,3,2),'b'),row(box(1,1,2,2),'c','2025-09-01','2025-09-01')]),db,boundaries)
    report=audit.overlap_screen(db)
    assert report['exhaustive'] and report['positive_area_date_overlap_pairs']==0
    db.close()


def test_database_validation_cannot_write(tmp_path):
    path=tmp_path/'fixture.sqlite';db=audit.database(path);db.close()
    before=path.read_bytes();db=audit.database(path,readonly=True)
    with pytest.raises(Exception,match='readonly'):db.execute('DELETE FROM candidates')
    db.close();assert path.read_bytes()==before


def test_inventory_links_are_only_exact_name_date_candidates(tmp_path,boundaries,monkeypatch):
    directory=tmp_path/'data/working/karnataka_flood_events_v1';directory.mkdir(parents=True)
    events=[{'ifi_source_event_id':'fixture-ifi','date_status':{'window':'usable'},'parsed_start_date':'2025-08-01',
             'parsed_end_date_inclusive':'2025-08-02','source_districts':'Fixture left'}]
    (directory/'events.json').write_text(json.dumps(events))
    udupi=tmp_path/'data/processed/udupi_flood_spatial_v1';udupi.mkdir(parents=True)
    (udupi/'manifest.json').write_text('{"events":[]}')
    monkeypatch.setattr(audit,'foundation_validate',lambda root:{'scopes':[
        {'gfd_id':1,'district':'Fixture left','start':'2025-08-01','end':'2025-08-02'},
        {'gfd_id':2,'district':'FixtureLeft','start':'2025-08-01','end':'2025-08-02'}]})
    monkeypatch.setattr(audit,'checked_file',lambda root,name:root/name)
    db=audit.database(tmp_path/'fixture.sqlite');audit.scan(iter([row(box(1,1,2,2))]),db,boundaries)
    report=audit.compare_inventories(db,boundaries,root=tmp_path)
    assert report['IFI']['possible_pairs']==1 and report['GFD']['possible_pairs']==1
    assert report['IFI']['confirmed_same_physical_events'] is None
    assert report['gfd_scopes_with_unresolved_exact_source_name_links']==[2]
    assert db.execute('SELECT count(*) FROM candidates').fetchone()[0]==1
    db.close()


def test_immutable_build_replay_and_source_output_tamper_checks(tmp_path,boundaries,monkeypatch):
    pytest.importorskip('pyarrow')
    archive=tmp_path/'data/raw/groundsource/zenodo_18647054_v1/groundsource_2026.parquet'
    archive.parent.mkdir(parents=True);archive.write_bytes(b'isolated fixture archive')
    boundary_dir=tmp_path/'boundaries';boundary_dir.mkdir();(boundary_dir/'fixture.txt').write_text('fixture boundary source')
    required=['data/working/karnataka_flood_events_v1/events.json','data/working/karnataka_flood_outcome_foundation_v1/report.json',
              'data/processed/udupi_flood_spatial_v1/manifest.json','data/processed/udupi_flood_spatial_v1/event_2728.geojson',
              'data/processed/udupi_flood_spatial_v1/event_3551.geojson']
    for name in required:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('isolated fixture reference')
    monkeypatch.setattr(audit,'ROOT',tmp_path);monkeypatch.setattr(audit,'BOUNDARIES',boundary_dir)
    monkeypatch.setattr(acquire,'RAW',archive.parent);monkeypatch.setattr(acquire,'verify',lambda p:acquire.file_hashes(p))
    monkeypatch.setattr(audit,'load_boundaries',lambda:boundaries)
    monkeypatch.setattr(audit,'compare_inventories',lambda *args,**kwargs:{})
    data=[row(box(1,1,2,2),'a'),row(box(-1,1,1,2),'b'),row(box(20,20,21,21),'c')]
    class Batch:
        num_rows=3;nbytes=1024
        def to_pylist(self):return copy.deepcopy(data)
    monkeypatch.setattr(audit,'parquet_batches',lambda *args,**kwargs:iter([Batch()]))
    monkeypatch.setattr(audit,'EXPECTED_ROWS',3)
    output=tmp_path/'output';report=audit.build(output,archive)
    assert report['candidate_records']==2 and report['training_readiness']['decision']=='NO-GO'
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in output.iterdir()}
    audit.validate(output,replay=True)
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in output.iterdir()}
    with pytest.raises(ValueError,match='overwrite'):audit.build(output,archive)
    (boundary_dir/'fixture.txt').write_text('changed fixture')
    with pytest.raises(ValueError,match='Original source'):audit.validate(output)
    (boundary_dir/'fixture.txt').write_text('fixture boundary source')
    (output/'candidate_events.csv').write_text('tampered fixture output')
    with pytest.raises(ValueError,match='Derived checksum'):audit.validate(output)


class Response(io.BytesIO):
    def __init__(self,body,start,end,total,status=206,declared=None):
        super().__init__(body);self.status=status
        self.headers={'Content-Range':declared or f'bytes {start}-{end}/{total}','Content-Length':str(end-start+1)}


def test_range_download_resumes_exact_existing_offset(tmp_path):
    body=b'0123456789';part=tmp_path/'fixture.part';part.write_bytes(body[:3]);requests=[]
    def opener(req,timeout):
        assert req.full_url==acquire.URL
        start,end=map(int,req.headers['Range'][6:].split('-'));requests.append((start,end))
        return Response(body[start:end+1],start,end,len(body))
    acquire.transfer(part,opener,size=len(body),chunk=4)
    assert part.read_bytes()==body and requests==[(3,6),(7,9)]


@pytest.mark.parametrize('status,declared',[(200,None),(206,'bytes 0-3/999')])
def test_range_not_honored_never_changes_partial_file(tmp_path,status,declared):
    part=tmp_path/'fixture.part';part.write_bytes(b'abc')
    def opener(req,timeout):return Response(b'defg',3,6,7,status,declared)
    with pytest.raises(ValueError,match='ignored or changed'):acquire.transfer(part,opener,size=7,chunk=4)
    assert part.read_bytes()==b'abc'


def test_interrupted_range_preserves_only_written_bytes(tmp_path):
    part=tmp_path/'fixture.part';part.write_bytes(b'abc')
    def opener(req,timeout):return Response(b'de',3,6,7)
    with pytest.raises(ValueError,match='Interrupted'):acquire.transfer(part,opener,size=7,chunk=4)
    assert part.read_bytes()==b'abcde'


def test_parallel_ranges_assemble_in_order_and_guard_concurrent_writes(tmp_path):
    body=b'0123456789';part=tmp_path/'fixture.part';part.write_bytes(body[:3])
    def opener(req,timeout):
        start,end=map(int,req.headers['Range'][6:].split('-'))
        return Response(body[start:end+1],start,end,len(body))
    acquire.parallel_transfer(part,opener,size=len(body),chunk=4,workers=2)
    assert part.read_bytes()==body
    assert not list((tmp_path/'range_chunks').glob('*.part'))
    part.write_bytes(body[:3])
    changed=False
    def competing(req,timeout):
        nonlocal changed
        start,end=map(int,req.headers['Range'][6:].split('-'))
        if not changed:
            with part.open('ab') as stream:stream.write(b'x')
            changed=True
        return Response(body[start:end+1],start,end,len(body))
    with pytest.raises(ValueError,match='concurrently'):
        acquire.parallel_transfer(part,competing,size=len(body),chunk=4,workers=1)
    assert part.read_bytes()==b'012x'


def test_second_download_cannot_obtain_single_writer_lock(tmp_path):
    with (tmp_path/'download.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='exclusive lock'):
            acquire.acquire(tmp_path,{},'')


def test_checksum_failure_does_not_finalize_partial_archive(tmp_path,monkeypatch):
    monkeypatch.setattr(acquire,'SIZE',3);monkeypatch.setattr(acquire,'MD5',hashlib.md5(b'abc').hexdigest())
    p=tmp_path/'fixture.part';p.write_bytes(b'abd')
    with pytest.raises(ValueError,match='MD5'):acquire.verify(p)
    assert p.read_bytes()==b'abd'
    p.write_bytes(b'abc');assert acquire.verify(p)['md5']==acquire.MD5


@pytest.mark.parametrize('change',[{'size':1},{'checksum':'md5:wrong'}])
def test_publisher_changes_block_download(tmp_path,change):
    record={'id':18647054,'doi':'10.5281/zenodo.18647054','metadata':{'license':{'id':'cc-by-4.0'}},
            'files':[{'key':'groundsource_2026.parquet','size':acquire.SIZE,'checksum':'md5:'+acquire.MD5,**change}]}
    with pytest.raises(ValueError,match='size/checksum'):acquire.preflight(record,'Version v1',tmp_path)


def test_optional_parquet_reader_is_batch_bounded_and_checks_crs(tmp_path):
    pytest.importorskip('pyarrow')
    import pyarrow as pa
    import pyarrow.parquet as pq
    rows=[row(box(1,1,2,2),uuid=str(i)) for i in range(7)]
    geo={'primary_column':'geometry','columns':{'geometry':{'encoding':'WKB','crs':{'id':{'authority':'EPSG','code':4326}}}}}
    table=pa.Table.from_pylist(rows).select(audit.SCHEMA).replace_schema_metadata({b'geo':json.dumps(geo).encode()})
    path=tmp_path/'fixture.parquet';pq.write_table(table,path,row_group_size=4)
    batches=list(audit.parquet_batches(path,batch_size=2))
    assert sum(b.num_rows for b in batches)==7 and all(b.num_rows<=2 for b in batches)
    with pytest.raises(ValueError,match='Batch'):list(audit.parquet_batches(path,batch_size=4097))
    geo['columns']['geometry']['crs']['id']['code']=3857
    table=table.replace_schema_metadata({b'geo':json.dumps(geo).encode()});pq.write_table(table,path)
    with pytest.raises(ValueError,match='CRS'):list(audit.parquet_batches(path,batch_size=2))
