"""Home source adapters: isolated HTTP fixtures, no research/DB/network writes."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.home_geography import HomePoint, covers_accuracy
from app.home_geocoding import ReverseGeocoder, validate_name
from app.home_sources import PrivateMapTilerLog
from app.river_outlook import RiverOutlook, parse_discharge, reviewed_reach, validate_grid

RECORD=json.loads((Path(__file__).parent/'fixtures/glofas_forecast_v4.json').read_text())
NOW=datetime.fromisoformat(RECORD['reference_time'])
POINT=HomePoint(latitude=16.575,longitude=74.525,accuracy_m=40)
POLYGON={'type':'Polygon','coordinates':[[[74.5,16.55],[74.55,16.55],[74.55,16.60],[74.5,16.60],[74.5,16.55]]]}
# Declarative review and all geographic values are TEST fixtures, not real approvals.
def reach():
 return {'id':'test-only','name':'TEST ONLY river','model':'forecast_v4','review_status':'independently_verified','public_display_rights':True,
         'query_point':{'latitude':16.575,'longitude':74.525},'expected_grid':{'latitude':16.575005,'longitude':74.52501},
         'grid_source':{'model':'forecast_v4','review_status':'verified_channel_and_topology','url':'https://example.org/test-only','sha256':'f'*64},
         'geographic_source':{'url':'https://example.org/test-only','license':'test-only'},'reviewed_at':NOW.isoformat(),
         'reach_geometry':{'type':'LineString','coordinates':[[74.51,16.575],[74.54,16.575]]},'viewing_geometry':deepcopy(POLYGON),'coverage_description':'TEST ONLY viewing area; no exposure inference'}

def geocode():
 return {'id':'municipality.test-only','type':'Feature','text':'TEST ONLY town','place_type':['municipality'],
         'geometry':{'type':'Point','coordinates':[74.54,16.59]},
         'context':[{'id':'country.test','country_code':'in'},{'id':'region.test','text':'Karnataka'},{'id':'subregion.test','text':'TEST ONLY context'}]}

@pytest.fixture
def payload(): return deepcopy(RECORD['payload'])


def test_live_format_discharge_is_model_output_not_measured_flood(payload):
 body=parse_discharge(payload,NOW)
 assert body['forecast'][0]['river_discharge']==4.22 and body['forecast'][0]['river_discharge_p25']==4.21
 assert body['units']=='m³/s' and body['timezone']=='GMT'
 assert body['source']['data_kind']=='external_modelled_river_forecast'
 assert body['forecast_issued_at'] is None and body['observation_time'] is None
 assert body['model_metadata_status']=='request_pinned_native_version_and_issue_not_echoed'
 assert not any(k in body for k in ['flood_probability','danger_level','water_level','inundation'])
 assert validate_grid(body,reach())['verified_grid'] is True

@pytest.mark.parametrize('field', ['river_discharge_mean','river_discharge_p25','river_discharge_p75'])
def test_omitted_ensemble_statistics_are_unavailable_not_invented(payload,field):
 del payload['daily'][field]
 body=parse_discharge(payload,NOW)
 assert body['status']=='partial' and body['field_quality'][field]=='unsupported_or_omitted'
 assert all(r[field] is None for r in body['forecast'])

@pytest.mark.parametrize('bad', [None, -1, float('nan'), float('inf'), 'bad', True])
def test_discharge_missing_and_invalid_values(payload,bad):
 payload['daily']['river_discharge'][2]=bad
 if bad is None:
  body=parse_discharge(payload,NOW);assert body['status']=='partial' and body['forecast'][2]['river_discharge'] is None
 else:
  with pytest.raises(ValueError):parse_discharge(payload,NOW)

@pytest.mark.parametrize('bad', ['timezone','units','reverse','duplicate','missing_day','future','all_null','bad_model','inverted_range'])
def test_invalid_forecast_semantics_rejected(payload,bad):
 if bad=='timezone':payload['utc_offset_seconds']=19800
 elif bad=='units':payload['daily_units']['river_discharge']='mm'
 elif bad=='reverse':payload['daily']['time'].reverse()
 elif bad=='duplicate':payload['daily']['time'][1]=payload['daily']['time'][0]
 elif bad=='missing_day':payload['daily']['time'].pop()
 elif bad=='future':payload['daily']['time'][0]='2026-10-14'
 elif bad=='all_null':payload['daily']['river_discharge']=[None]*7
 elif bad=='bad_model':payload['model']='consolidated_v4'
 else:payload['daily']['river_discharge_p25'][0]=100
 with pytest.raises(ValueError):parse_discharge(payload,NOW)


def test_ensemble_mean_may_be_outside_interquartile_range(payload):
 payload['daily']['river_discharge_mean'][0]=100
 assert parse_discharge(payload,NOW)['forecast'][0]['river_discharge_mean']==100

@pytest.mark.parametrize('bad',['ambiguous_review','v5','incorrect_grid','rights','unknown_source','no_reach_geometry'])
def test_no_grid_or_nearest_river_promotion(payload,bad):
 r=reach();body=parse_discharge(payload,NOW)
 if bad=='ambiguous_review':r['review_status']='ambiguous'
 elif bad=='v5':r['grid_source']['model']='historical_v5'
 elif bad=='incorrect_grid':body['grid_location']['longitude']+=.05
 elif bad=='rights':r['public_display_rights']=False
 elif bad=='unknown_source':r['grid_source']['sha256']='unverified'
 else:r['reach_geometry']['type']='Point'
 with pytest.raises(ValueError):validate_grid(body,r)


def test_unapproved_or_ambiguous_viewing_area_never_calls_provider():
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('Unapproved network request')))) as c:
   assert (await RiverOutlook(c).outlook(POINT))['status']=='unsupported'
   assert (await RiverOutlook(c,[reach(),{**reach(),'id':'second-test'}]).outlook(POINT))['status']=='unsupported'
   assert (await RiverOutlook(c,[reach()]).outlook(HomePoint(latitude=13.4,longitude=74.7)))['status']=='unsupported'
   assert (await RiverOutlook(c,[reach()]).outlook(HomePoint(latitude=16.575,longitude=74.525,accuracy_m=279949)))['status']=='unsupported'
 asyncio.run(run())


def test_verified_test_reach_caches_and_coalesces_concurrent_reads(payload,monkeypatch):
 monkeypatch.setattr('app.river_outlook.datetime',type('Clock',(datetime,),{'now':staticmethod(lambda tz:NOW)}))
 calls=[]
 def handler(request):
  calls.append(request);assert request.url.params['models']=='forecast_v4' and request.url.params['timezone']=='GMT'
  assert request.url.params['forecast_days']=='7'
  return httpx.Response(200,json=payload)
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
   service=RiverOutlook(c,[reach()]);a,b=await asyncio.gather(service.outlook(POINT),service.outlook(POINT))
   assert a['status']=='available' and b['cache_status']=='fresh_cache'
   assert a['official_warning_status']=='not_connected' and 'cannot currently be assessed reliably' in a['nearby_flood_possibility']
   assert len(calls)==1
 asyncio.run(run())

@pytest.mark.parametrize('status',[429,503,400])
def test_provider_failure_respects_retry_after_and_never_substitutes_observations(status):
 calls=[]
 def handler(request):calls.append(request);return httpx.Response(status,headers={'Retry-After':'3600'})
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
   service=RiverOutlook(c,[reach()]);a=await service.outlook(POINT);b=await service.outlook(POINT)
   assert a['status']=='unavailable' and a['upstream_status']==status and not a['forecast'] and a['retrieved_at'] is None
   assert a['retry_after_seconds']==3600 and len(calls)==1
 asyncio.run(run())


def test_precise_reverse_name_uses_polygon_and_source_context_not_centroid():
 f=geocode();full={'id':f['id'],'type':'Feature','geometry':POLYGON}
 result=validate_name(f,full,POINT)
 assert result['name']=='TEST ONLY town, TEST ONLY context'
 assert result['administrative_identity_status']=='provider_context_not_canonical_directory_join'
 assert 'latitude' not in result and 'longitude' not in result

@pytest.mark.parametrize('bad',['point_only','outside_polygon','border_uncertain','outside_state','wrong_country','wrong_id'])
def test_unverified_locality_name_rejected(bad):
 f=geocode();full={'id':f['id'],'type':'Feature','geometry':deepcopy(POLYGON)};p=POINT
 if bad=='point_only':full['geometry']=f['geometry']
 elif bad=='outside_polygon':p=HomePoint(latitude=13.4,longitude=74.7)
 elif bad=='border_uncertain':p=HomePoint(latitude=16.5501,longitude=74.525,accuracy_m=40)
 elif bad=='outside_state':f['context'][1]['text']='Goa'
 elif bad=='wrong_country':f['context'][0]['country_code']='us'
 else:full['id']='municipality.another'
 with pytest.raises(ValueError):validate_name(f,full,p)


def test_geometry_holes_and_malformed_polygons_fail_closed():
 polygon=deepcopy(POLYGON);polygon['coordinates'].append([[74.52,16.57],[74.53,16.57],[74.53,16.58],[74.52,16.58],[74.52,16.57]])
 assert not covers_accuracy(polygon,POINT.latitude,POINT.longitude,40)
 assert not covers_accuracy(None,POINT.latitude,POINT.longitude)
 assert not covers_accuracy({'type':'Polygon','coordinates':[[[float('nan'),1]]]},POINT.latitude,POINT.longitude)


def test_disabled_and_coarse_geocoding_make_no_network_requests():
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('No unauthorized geocoding')))) as c:
   service=ReverseGeocoder(c,environment={})
   assert (await service.resolve(POINT))['status']=='disabled'
   assert (await service.resolve(HomePoint(latitude=16.575,longitude=74.525,accuracy_m=279949)))['status']=='unsupported'
 asyncio.run(run())


def test_authorized_fixture_reverse_is_rate_limited_cached_and_keeps_secrets_out_of_result():
 calls=[];feature=geocode()
 def handler(request):
  calls.append(request)
  if 'municipality.test-only.json' in request.url.path:return httpx.Response(200,json={'type':'FeatureCollection','features':[{'id':feature['id'],'type':'Feature','geometry':POLYGON}]})
  return httpx.Response(200,json={'type':'FeatureCollection','features':[feature]})
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
   service=ReverseGeocoder(c,environment={'MAPTILER_REVERSE_ENABLED':'true','MAPTILER_GEOCODING_RIGHTS_REVIEWED':'true','MAPTILER_GEOCODING_KEY':'TEST_ONLY_NO_CREDENTIAL','MAPTILER_GEOCODING_HOURLY_BUDGET':'2'})
   a=await service.resolve(POINT);b=await service.resolve(POINT)
   assert a['status']=='available' and a==b and len(calls)==2 and 'TEST_ONLY_NO_CREDENTIAL' not in json.dumps(a)
   assert all(isinstance(k,bytes) and len(k)==32 for k in service.cache)
   assert 'latitude' not in json.dumps(a) and 'longitude' not in json.dumps(a)
   assert (await service.resolve(HomePoint(latitude=16.576,longitude=74.525,accuracy_m=40)))['status']=='unavailable'
 asyncio.run(run())


def test_maptiler_http_logging_redacts_location_and_key():
 r=logging.LogRecord('httpx',20,'test',1,'HTTP request https://api.maptiler.com/geocoding/74.525,16.575.json?key=TEST_ONLY',(),None)
 assert PrivateMapTilerLog().filter(r)
 assert '74.525' not in r.getMessage() and 'TEST_ONLY' not in r.getMessage()


def test_default_home_source_routes_are_disabled_unsupported_and_private():
 with TestClient(app) as c:
  point=POINT.model_dump()
  a=c.post('/api/location/reverse',json=point);b=c.post('/api/river-outlook',json=point)
  assert a.status_code==b.status_code==200
  assert a.json()['status']=='disabled' and b.json()['status']=='unsupported'
  assert a.headers['Cache-Control']==b.headers['Cache-Control']=='no-store'
  assert c.get('/api/location/reverse').status_code==405
  assert c.post('/api/river-outlook',json={**point,'latitude':100}).status_code==422


def test_weather_access_logs_do_not_persist_precise_query_coordinates():
 from app.home_sources import CoordinateAccessLog
 r=logging.LogRecord('uvicorn.access',20,'test',1,'%s - "%s %s HTTP/%s" %d',('127.0.0.1','GET','/api/weather?latitude=16.575&longitude=74.525','1.1',200),None)
 assert CoordinateAccessLog().filter(r)
 assert '16.575' not in r.getMessage() and '74.525' not in r.getMessage() and '/api/weather' in r.getMessage()


def test_forecast_native_version_disagreement_rejected(payload):
 payload['model_version']='5.0'
 with pytest.raises(ValueError,match='native model'):parse_discharge(payload,NOW)


def test_reverse_geocoding_honors_provider_retry_after_across_different_points():
 calls=[];clock=[0]
 def handler(request):calls.append(request);return httpx.Response(429,headers={'Retry-After':'3600'})
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
   service=ReverseGeocoder(c,environment={'MAPTILER_REVERSE_ENABLED':'true','MAPTILER_GEOCODING_RIGHTS_REVIEWED':'true','MAPTILER_GEOCODING_KEY':'TEST_ONLY_NO_CREDENTIAL','MAPTILER_GEOCODING_HOURLY_BUDGET':'10'},clock=lambda:clock[0])
   assert (await service.resolve(POINT))['status']=='unavailable'
   clock[0]=60
   assert (await service.resolve(HomePoint(latitude=16.576,longitude=74.525,accuracy_m=40)))['status']=='unavailable'
   assert len(calls)==1
 asyncio.run(run())


def test_reverse_geocoding_requires_an_explicit_reported_accuracy():
 with TestClient(app) as c:
  assert c.post('/api/location/reverse',json={'latitude':16.575,'longitude':74.525}).status_code==422
