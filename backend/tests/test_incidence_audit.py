"""Offline incidence/reference contracts; fixture outputs are temporary only."""
import importlib.util
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
import math
import numpy as np
import pytest
from shapely.geometry import box, mapping

spec=importlib.util.spec_from_file_location('incidence_audit',Path(__file__).resolve().parents[2]/'scripts/audit_belagavi_incidence.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def fixture():
    names=[f's{i}_{b}' for i in range(3) for b in ['VV','VH','angle']]
    values=np.ones((9,200,200),dtype='float32')
    for i in range(3):values[names.index(f's{i}_angle')]=45.6+i*.005
    rows=[{'id':'source-'+str(i),'acquisition_utc':'fixture','footprint':mapping(box(74,16,76,18)),
           'properties':{'platform_number':'A','orbitProperties_pass':'DESCENDING','relativeOrbitNumber_start':63}} for i in range(3)]
    grid={'transform':[10,0,499000,0,-10,1843000]}
    return values,names,rows,grid


def test_quantiles_independent_scalar_linear_and_missing():
    r=a.stats([1,2,4,8]);assert r['median']==3 and r['mean']==3.75
    assert r['percentiles']['25']==1.75 and r['percentiles']['99']==pytest.approx(7.88)
    assert a.stats([])['median'] is None
    with pytest.raises(ValueError):a.stats([1,float('nan')])


def test_absolute_range_does_not_determine_sar_validity_or_agreement():
    values,names,rows,grid=fixture();before=values.copy();r=a.incidence(values,names,rows,grid)
    assert r['comparison_cells']==r['agreement_le_1_degree_cells']==40000
    assert r['legacy_30_45_range_cells']==0 and r['legacy_filter_status']=='legacy_angle_filter_unsubstantiated'
    assert r['local_incidence_computed'] is False and np.array_equal(values,before)


def test_separate_angle_vv_vh_masks_and_nodata():
    values,names,rows,grid=fixture();values[2,0,0]=a.p.NODATA;values[0,1,1]=a.p.NODATA
    r=a.incidence(values,names,rows,grid);s=r['scenes'][0]
    assert s['unmasked_angle_cells']==s['valid_vv_vh_cells']==39999 and s['intersection_cells']==39998
    assert r['comparison_cells']==39998


def test_geometry_difference_reported_no_automatic_absolute_rejection():
    values,names,rows,grid=fixture();values[8]+=2
    r=a.incidence(values,names,rows,grid)
    assert r['agreement_le_1_degree_cells']==0 and r['comparison_cells']==40000


def test_tile_must_be_in_retained_scene():
    values,names,rows,grid=fixture();rows[0]['footprint']=mapping(box(1,2,3,4))
    with pytest.raises(ValueError):a.incidence(values,names,rows,grid)


def test_legacy_provenance_is_heuristic_not_documented_validity():
    assert a.METHOD['rule_origin']=='project_heuristic'
    assert a.METHOD['rule_status']=='legacy_angle_filter_unsubstantiated'
    assert a.METHOD['legacy_range']==[30,45] and a.METHOD['threshold_generation'] is False


def test_only_public_advertised_links_no_namespace_guessing():
    html='<a href="../wfs?service=WFS&amp;request=GetCapabilities&amp;version=2.0.0">WFS</a><a href="../wfs?service=WFS&amp;request=GetCapabilities&amp;version=1.0.0">other</a>'
    links=a.advertised_capabilities(html)
    assert len(links)==1 and 'version=2.0.0' in links['WFS']
    with pytest.raises(ValueError):a.advertised_capabilities('<a href="https://mirror.example/wfs?service=WFS&amp;request=GetCapabilities">bad</a>')


@pytest.mark.parametrize('service,body,name',[
 ('WMS',b'<WMS_Capabilities version="1.3.0"><Capability><Request><GetMap><Format>image/png</Format></GetMap></Request><Layer><Layer><Name>flood:ka_2021_28_07</Name><Title>Karnataka July 2021</Title><CRS>EPSG:4326</CRS><EX_GeographicBoundingBox><westBoundLongitude>74</westBoundLongitude><eastBoundLongitude>75</eastBoundLongitude></EX_GeographicBoundingBox></Layer></Layer></Capability></WMS_Capabilities>','flood:ka_2021_28_07'),
 ('WFS',b'<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" version="2.0.0"><wfs:FeatureTypeList><wfs:FeatureType><wfs:Name>flood:ka_2021_25_07</wfs:Name><wfs:Title>Karnataka</wfs:Title><wfs:DefaultCRS>EPSG:4326</wfs:DefaultCRS></wfs:FeatureType></wfs:FeatureTypeList></wfs:WFS_Capabilities>','flood:ka_2021_25_07'),
 ('WCS',b'<Capabilities version="2.0.1"><Contents><CoverageSummary><CoverageId>ka_2021_29_07</CoverageId><Title>Karnataka</Title><WGS84BoundingBox crs="EPSG:4326"><LowerCorner>74 16</LowerCorner><UpperCorner>75 17</UpperCorner></WGS84BoundingBox></CoverageSummary></Contents></Capabilities>','ka_2021_29_07'),
 ('WMTS',b'<Capabilities version="1.0.0"><Contents><Layer><Identifier>ka_2021_28_07</Identifier><Title>map</Title><Format>image/png</Format></Layer></Contents></Capabilities>','ka_2021_28_07'),
])
def test_service_capabilities_parser_and_target_filter(service,body,name):
    r=a.parse_capabilities(body,service);assert r['layers'][0]['name']==name and a.target_layer(r['layers'][0])
    assert not a.target_layer({'name':'other:forest_2020','title':'Karnataka'})


@pytest.mark.parametrize('body',[b'<html>Login</html>',b'<!DOCTYPE test><Capabilities/>',b'<ServiceExceptionReport/>'])
def test_invalid_or_unsafe_capabilities_not_data(body):
    with pytest.raises(ValueError):a.parse_capabilities(body,'WCS')


def candidate(service='WFS'):
    return {'source_url':'https://bhuvan-gp1.nrsc.gov.in/bhuvan/wfs','service':service,'july_2021_verified':True,
            'overlap_verified':True,'geographic_metadata_sufficient':True,'legitimate_access':True,
            'internal_use_permitted':True,'original_subset_retrieved':True,'class_semantics_documented':True}


@pytest.mark.parametrize('service',['WMS','WMTS'])
def test_rendered_maps_never_machine_readable_truth(service):
    assert a.reference_acceptance(candidate(service))=='official_rendered_map_reference'


@pytest.mark.parametrize('field',['july_2021_verified','overlap_verified','geographic_metadata_sufficient','legitimate_access','internal_use_permitted','original_subset_retrieved','class_semantics_documented'])
def test_all_machine_readable_acceptance_evidence_required(field):
    c=candidate();c[field]=False
    assert a.reference_acceptance(c)=='machine_readable_reference_unavailable'


def test_official_source_and_no_guessed_geometry():
    c=candidate();assert a.reference_acceptance(c)=='machine_readable_reference_available'
    c['source_url']='https://mirror.example/official';assert a.reference_acceptance(c)=='machine_readable_reference_unavailable'
    assert not a.official('https://nrsc.gov.in.attacker.example/wfs')
    assert not a.official('https://user:pass@bhuvan.nrsc.gov.in/wfs')


@pytest.mark.parametrize('ref,blocked,expected',[
 ('machine_readable_reference_available',False,'ready_for_bounded_calibration'),
 ('machine_readable_reference_unavailable',False,'ready_for_unlabelled_sar_method_research'),
 ('machine_readable_reference_unavailable',True,'reference_access_blocked'),
])
def test_readiness_vocabulary_no_forced_calibration(ref,blocked,expected):
    assert a.readiness('sentinel1_pair_available','acceptable_for_continuous_comparison',ref,blocked)==expected
    assert a.readiness('sentinel1_pair_available','unsuitable',ref,blocked)=='sar_geometry_unsuitable'
    with pytest.raises(ValueError):a.readiness('wrong','acceptable_for_continuous_comparison',ref)


@pytest.mark.parametrize('key',['flood_threshold','best_threshold','candidate_cells','flood_polygon','digitized_pdf_extent','daily_flood_label'])
def test_no_threshold_generation_or_pdf_digitization(key):
    with pytest.raises(ValueError):a.no_classification({'nested':{key:0}})


class Response:
    headers={'Content-Type':'application/xml'}
    def __init__(self,status):self.status_code=status
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,*args):yield b'<ServiceExceptionReport/>'


class Session:
    def __init__(self,statuses):self.statuses=list(statuses);self.calls=0
    def get(self,*args,**kw):self.calls+=1;return Response(self.statuses.pop(0))


@pytest.mark.parametrize('statuses,expected', [([401,200],1),([403,200],1),([400,200],1),([503,200],2),([503,503,200],2)])
def test_bounded_retries_and_auth_failures_stop(statuses,expected):
    with TemporaryDirectory() as tmp:
        session=Session(statuses);path=Path(tmp)/'response.xml'
        r=a.fetch(session,'https://bhuvan-gp1.nrsc.gov.in/bhuvan/wfs',path,attempts=2,sleep=lambda _:None)
        assert session.calls==expected and len(r['attempts'])==expected
        with pytest.raises(ValueError):a.fetch(session,'https://bhuvan-gp1.nrsc.gov.in/bhuvan/wfs',path)
        with pytest.raises(ValueError):a.fetch(session,'https://bhuvan-gp1.nrsc.gov.in/bhuvan/wfs',Path(tmp)/'other',attempts=3)


def test_freeze_refuses_completed_versions_before_input_read():
    with TemporaryDirectory() as tmp:
        folder=Path(tmp)/'done';folder.mkdir();f=folder/'immutable';f.write_bytes(b'original\r\n')
        fp=a.p.source.fingerprint(f);mtime=f.stat().st_mtime_ns
        with pytest.raises(ValueError):a.freeze(folder,Path(tmp)/'ref')
        assert a.p.source.fingerprint(f)==fp and f.stat().st_mtime_ns==mtime


def test_wmts_link_without_service_parameter_is_advertised():
    r=a.advertised_capabilities('<a href="../gwc/service/wmts?REQUEST=GetCapabilities">WMTS</a>')
    assert set(r)=={'WMTS'}


def test_portal_exact_july_ids_not_other_events_or_flood_shapes():
    body='<input onclick=\'loadfloodmap("layer1","https://bhuvan-gp1.nrsc.gov.in/bhuvan/gwc/service/wms","ka_2021_28_07")\'>28/07/2021<img><input onclick=\'loadfloodmap("other","https://bhuvan-gp1.nrsc.gov.in/bhuvan/gwc/service/wms","ka_2021_14_11_06")\'>November'
    r=a.portal_products(body);assert len(r)==1 and r[0]['title']=='28/07/2021'
    assert r[0]['spatial_coverage'].startswith('not_verified') and 'geometry' not in r[0]


def test_angle_error_status_not_promoted():
    values,names,rows,grid=fixture();values[8]+=2
    assert a.incidence(values,names,rows,grid)['angle_geometry_status']=='angle_geometry_problem_detected'


def test_late_response_preserved_as_unavailable(monkeypatch):
    ticks=iter([0,0,0,61,61,61])
    monkeypatch.setattr(a.p.bounded.grid,'elapsed_clock',lambda:next(ticks))
    with TemporaryDirectory() as tmp:
        r=a.fetch(Session([200]),'https://bhuvan-gp1.nrsc.gov.in/bhuvan/wfs',Path(tmp)/'late.xml')
        assert r['access_status']=='unavailable' and r['error_type']=='ValueError'


def test_terrain_masks_nodata_grid_and_readonly_bytes():
    import rasterio
    from affine import Affine
    with TemporaryDirectory() as tmp:
        raw=Path(tmp);path=raw/'terrain.tif';grid=[10,0,499000,0,-10,1843000]
        data=np.ones((4,200,200),dtype='float32');data[0]=530;data[2]=2;data[0,0,0]=a.p.NODATA;data[1,0,0]=0
        with rasterio.open(path,'w',driver='GTiff',width=200,height=200,count=4,dtype='float32',crs=a.p.CRS,transform=Affine(*grid),nodata=a.p.NODATA) as r:r.write(data)
        a.p.source.write_new(raw/'terrain.json',{'asset':a.p.DEM,'download':a.p.source.fingerprint(path),'parameters':{'crs_transform':grid},'native_metadata':{'nominal_scale_m':30}})
        snapshot={str(p):{**a.p.source.fingerprint(p),'mtime_ns':p.stat().st_mtime_ns} for p in raw.iterdir()}
        result=a.terrain_summary(raw)
        assert result['valid_elevation_cells']==39999 and result['valid_slope_cells']==40000
        assert result['elevation_m']['mean']==530 and result['steep_fraction'] is None and result['local_incidence_computed'] is False
        assert snapshot=={str(p):{**a.p.source.fingerprint(p),'mtime_ns':p.stat().st_mtime_ns} for p in raw.iterdir()}
