"""Isolated observation safety tests: no network, models, original sources or database."""
import copy
import io
import json
from pathlib import Path
import sys
import urllib.error

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import acquire_direct_observation_metadata as metadata
import acquire_opera_bounded_preview as preview
import audit_direct_flood_observations as audit


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}
        self.status = 200


@pytest.mark.parametrize('url', [
    'http://cmr.earthdata.nasa.gov/search/granules.json',
    'https://unapproved.example/test', 'https://user:password@cmr.earthdata.nasa.gov/test',
    'https://cmr.earthdata.nasa.gov:444/test', 'https://cmr.earthdata.nasa.gov/test#secret',
    'https://cmr.earthdata.nasa.gov/test?token=secret',
    'https://cmr.earthdata.nasa.gov/data.TIFF', 'https://cmr.earthdata.nasa.gov/native.SAFE/file',
    'https://cmr.earthdata.nasa.gov/archive.zip', 'https://cmr.earthdata.nasa.gov/native%2Etif'])
def test_metadata_rejects_credentials_unapproved_hosts_and_native_downloads(url):
    with pytest.raises(ValueError):
        metadata.validate_url(url)


def test_catalogue_safe_name_query_is_metadata_not_download():
    url = 'https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=Name%20eq%20%27native.SAFE%27'
    assert metadata.validate_url(url) == url


@pytest.mark.parametrize('body,headers,ceiling', [
    (b'ab', {'Content-Length': '3'}, 3), (b'abcdef', {}, 5),
    (b'a', {'Content-Length': '1000'}, 5), (b'a', {}, 0), (b'a', {}, True)])
def test_metadata_rejects_truncation_and_budget_violations(body, headers, ceiling):
    with pytest.raises(ValueError):
        metadata.read_bounded(Response(body, headers), ceiling)


def test_exact_bounded_response_and_no_redirects():
    assert metadata.read_bounded(Response(b'abc', {'Content-Length':'3'}), 3) == b'abc'
    assert metadata.NoRedirect().redirect_request(None, None, 303, None, None, None) is None


def install_response(monkeypatch, body, headers=None):
    class Opener:
        def open(self, request, timeout):
            assert 'Authorization' not in request.headers
            assert timeout == 25
            return Response(body, headers)
    monkeypatch.setattr(metadata.urllib.request, 'build_opener', lambda *_: Opener())


def test_metadata_receipt_immutable_and_no_cookie_retention(tmp_path, monkeypatch):
    install_response(monkeypatch, b'{}', {'Set-Cookie':'DO_NOT_RETAIN', 'Content-Type':'application/json'})
    r = metadata.fetch('record.json','https://cmr.earthdata.nasa.gov/search/granules.json',tmp_path)
    assert r['status'] == 'RETRIEVED'
    receipt = (tmp_path/'record.json.receipt.json').read_text()
    assert 'DO_NOT_RETAIN' not in receipt
    assert json.loads(receipt)['sha256'] == audit.fingerprint(tmp_path/'record.json')['sha256']
    with pytest.raises(ValueError, match='already exists'):
        metadata.fetch('record.json','https://cmr.earthdata.nasa.gov/test',tmp_path)
    assert metadata.validate_receipts(tmp_path)['requests'] == 1
    (tmp_path/'record.json').write_bytes(b'altered')
    with pytest.raises(ValueError, match='checksum'):
        metadata.validate_receipts(tmp_path)


@pytest.mark.parametrize('magic', [b'II*\x00',b'MM\x00*',b'II+\x00',b'PK\x03\x04',b'\x89HDF',b'CDF',b'\x0e\x03\x13\x01'])
def test_native_binary_response_cannot_be_smuggled_through_metadata_url(tmp_path, monkeypatch, magic):
    install_response(monkeypatch, magic)
    r = metadata.fetch('metadata.json','https://cmr.earthdata.nasa.gov/test',tmp_path)
    assert r['status'] == 'UNAVAILABLE_OR_BUDGET_REJECTED'
    assert not (tmp_path/'metadata.json').exists()


def bands(values):
    return np.array(values, dtype='uint8').T.reshape(4, 1, len(values))


def test_raw_zero_nonwater_and_source_water_never_become_flood_labels():
    r = audit.classify_source_pixels(bands([[0,0,0,0], [1,1,1,90], [3,1,35,50]]))
    assert r['coherent_nonfill_source_pixels'] == 3
    assert r['source_quality_counts']['SOURCE_NOT_WATER_CANDIDATE'] == 1
    assert r['source_quality_counts']['SOURCE_OPEN_WATER_HIGH_CONFIDENCE'] == 1
    assert r['source_quality_counts']['SOURCE_INUNDATED_VEGETATION_UNVERIFIED'] == 1
    assert r['outcome_evidence_partition'] == {
        'OBSERVED_TEMPORARY_INUNDATION':0, 'ADEQUATELY_OBSERVED_ABSENCE':0,
        'PERMANENT_WATER':0, 'INSUFFICIENT_OBSERVATION':0, 'UNKNOWN':3}


def test_negative_diagnostic_code_is_invalid_not_confident_nonwater():
    r = audit.classify_source_pixels(np.array([0,0,0,-1],dtype='int16').reshape(4,1,1))
    assert r['source_quality_counts'] == {'INSUFFICIENT_OBSERVATION':1}


@pytest.mark.parametrize('pixel', [[0,0,5,30], [0,0,6,30], [0,0,7,30],
    [0,0,36,30], [0,0,37,30], [1,1,2,90], [1,1,32,90]])
def test_potential_vegetation_ancillary_masks_and_moderate_water_are_insufficient(pixel):
    r = audit.classify_source_pixels(bands([pixel]))
    assert r['source_quality_counts'] == {'INSUFFICIENT_OBSERVATION':1}
    assert r['outcome_evidence_partition']['ADEQUATELY_OBSERVED_ABSENCE'] == 0


@pytest.mark.parametrize('pixel', [[255,255,255,255], [250,250,250,252], [251,251,251,253],
    [0,0,0,120], [0,0,0,255], [0,0,0,101], [0,0,99,0], [1,0,1,90], [0,1,0,0], [3,1,1,90]])
def test_mask_codes_unknown_codes_and_cross_band_contradictions_fail_closed(pixel):
    r = audit.classify_source_pixels(bands([pixel]))
    assert r['source_quality_counts'] == {'INSUFFICIENT_OBSERVATION':1}
    assert r['contradictory_or_invalid_source_pixels'] == 1


@pytest.mark.parametrize('value', [np.zeros((4,121,120),dtype='uint8'),
                                  np.zeros((3,100,100),dtype='uint8'),
                                  np.zeros((4,1,1),dtype='float32'), np.zeros((4,0,0),dtype='uint8')])
def test_qc_rejects_unbounded_or_unreviewed_input(value):
    with pytest.raises(ValueError):
        audit.classify_source_pixels(value)


def test_export_nodata_zero_does_not_destroy_valid_nonwater_codes(tmp_path):
    p = tmp_path/'preview.tif'
    with rasterio.open(p,'w',driver='GTiff',width=100,height=100,count=4,dtype='uint8',
                       crs='EPSG:32643',transform=Affine(30,0,471150,0,-30,1476450),nodata=0) as ds:
        ds.write(np.zeros((4,100,100),dtype='uint8'))
    r = audit.read_preview(p)
    assert r['export_nodata_tag'] == 0
    assert r['source_quality_counts'] == {'SOURCE_NOT_WATER_CANDIDATE':10000}
    assert r['outcome_evidence_partition']['UNKNOWN'] == 10000
    assert r['outcome_evidence_partition']['ADEQUATELY_OBSERVED_ABSENCE'] == 0


@pytest.mark.parametrize('start,end', [
    ('2024-12-04T00:48:40','2024-12-04T00:49:03'),
    ('2024-12-04T00:49:03Z','2024-12-04T00:48:40Z'),
    ('2005-09-14T00:00:00Z','2005-09-14T23:59:59Z')])
def test_daily_nominal_or_invalid_catalogue_intervals_are_not_actual_sensing_intervals(start,end):
    with pytest.raises(ValueError):
        audit.sensing_interval(start,end)


def test_true_acquisition_interval_retains_start_and_end():
    start,end = audit.sensing_interval('2024-12-04T00:48:40Z','2024-12-04T00:49:03Z')
    assert (end-start).total_seconds() == 23


def test_geographic_metadata_disagreement_cannot_be_silently_repaired_or_certified():
    extent={'HorizontalSpatialDomain':{'Geometry':{'BoundingRectangles':[
        {'WestBoundingCoordinate':74,'SouthBoundingCoordinate':12,
         'EastBoundingCoordinate':75,'NorthBoundingCoordinate':13}]}}}
    props={'system:footprint':{'type':'LinearRing','coordinates':[
        [74.05,12.05],[75.05,12.05],[75.05,13.05],[74.05,13.05],[74.05,12.05]]}}
    result=audit.geographic_metadata_check(extent,props)
    assert result['status'].startswith('GEOGRAPHIC_METADATA_DISAGREEMENT')
    assert result['spatial_accuracy_verified'] is result['coordinates_shifted_or_repaired'] is False
    assert extent['HorizontalSpatialDomain']['Geometry']['BoundingRectangles'][0]['WestBoundingCoordinate'] == 74


def reviewed_plan():
    plan = {'large_download_authorized':False, 'source_ids':preview.IDS,
            'dimensions':[100,100], 'bands':preview.BANDS, 'native_crs':'EPSG:32643',
            'window_transform':[30,0,471150,0,-30,1476450], 'byte_ceiling_per_download':2097152,
            'total_download_ceiling':4194304}
    im = [{'id':i, 'properties':{'DSWX_PRODUCT_VERSION':'1.0'},
           'bands':[{'id':b,'crs':'EPSG:32643','crs_transform':[30,0,399960,0,-30,1500000]}
                    for b in preview.BANDS]} for i in preview.IDS]
    return plan, {'status':'RETRIEVED','images':{'features':im}}


@pytest.mark.parametrize('key,value', [('dimensions',[3660,3660]), ('large_download_authorized',True),
    ('source_ids',['unreviewed-id']), ('window_transform',[10,0,0,0,-10,0]),
    ('total_download_ceiling',4194305), ('bands',['WTR_Water_classification'])])
def test_preview_plan_rejects_expanded_region_volume_new_ids_and_missing_quality(key,value):
    plan, source = reviewed_plan()
    plan = copy.deepcopy(plan);plan[key] = value
    with pytest.raises(ValueError):
        preview.validate_plan(plan,source)


def test_preview_plan_and_source_version_are_bound_before_network():
    plan, source = reviewed_plan()
    assert len(preview.validate_plan(plan,source)) == 2
    source['images']['features'][0]['properties']['DSWX_PRODUCT_VERSION'] = 'unreviewed'
    with pytest.raises(ValueError, match='version'):
        preview.validate_plan(plan,source)


def test_existing_label_contract_requires_independent_evidence_not_source_classes(tmp_path):
    p = tmp_path/'source.json';p.write_bytes(b'actual isolated source fixture')
    row = {'observation_id':'fixture', 'target':'ACQUISITION_TEMPORARY_INUNDATION',
           'spatial_unit_id':'unit','geometry_reference':'unit.geojson','source_reference':p.name,
           'source_sha256':audit.fingerprint(p)['sha256'], 'event_group':'event',
           'source_group':'source','review_group':'review','unit_pixels':1,'valid_pixels':0,
           'temporary_water_pixels':0,'permanent_water_pixels':0,'dry_pixels':0,'unknown_pixels':1,
           'acquisition_time':'2024-12-04T00:48:40Z','source_type':'OBSERVED',
           'product_role':'ACQUISITION_CLASSIFICATION'}
    r = audit.audit_contracts([row],tmp_path)
    assert r['observation_eligible'] == r['forecast_eligible'] == 0
    assert r['label_counts'] == {'UNKNOWN':1}
    assert not r['results'][0]['problems']


def test_build_never_overwrites_retained_version(tmp_path):
    (tmp_path/audit.OUTPUT).mkdir(parents=True)
    with pytest.raises(ValueError, match='Version exists'):
        audit.build(tmp_path)
