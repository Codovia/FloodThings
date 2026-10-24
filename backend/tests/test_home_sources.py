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

POINT=HomePoint(latitude=16.575,longitude=74.525,accuracy_m=40)
POLYGON={'type':'Polygon','coordinates':[[[74.5,16.55],[74.55,16.55],[74.55,16.60],[74.5,16.60],[74.5,16.55]]]}
# All geographic values are TEST fixtures.

def geocode():
 return {'id':'municipality.test-only','type':'Feature','text':'TEST ONLY town','place_type':['municipality'],
         'geometry':{'type':'Point','coordinates':[74.54,16.59]},
         'context':[{'id':'country.test','country_code':'in'},{'id':'region.test','text':'Karnataka'},{'id':'subregion.test','text':'TEST ONLY context'}]}


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
  a=c.post('/api/location/reverse',json=point)
  assert a.status_code==200 and a.json()['status']=='disabled'
  assert a.headers['Cache-Control']=='no-store'
  assert c.get('/api/location/reverse').status_code==405


def test_weather_access_logs_do_not_persist_precise_query_coordinates():
 from app.home_sources import CoordinateAccessLog
 r=logging.LogRecord('uvicorn.access',20,'test',1,'%s - "%s %s HTTP/%s" %d',('127.0.0.1','GET','/api/weather?latitude=16.575&longitude=74.525','1.1',200),None)
 assert CoordinateAccessLog().filter(r)
 assert '16.575' not in r.getMessage() and '74.525' not in r.getMessage() and '/api/weather' in r.getMessage()


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


def test_location_provider_discovery_has_no_coordinates_or_secrets():
 with TestClient(app) as c:
  response=c.get('/api/location/provider')
  assert response.json()=={'provider':'BigDataCloud'}
  assert response.headers['cache-control']=='no-store'


def test_locality_accuracy_policy_allows_kilometre_uncertainty_only_with_covering_polygon():
 from app.home_geocoding import validate_name
 point=HomePoint(latitude=16.575,longitude=74.525,accuracy_m=1200)
 feature=geocode()
 polygon={'type':'Polygon','coordinates':[[[74.4,16.45],[74.65,16.45],[74.65,16.7],[74.4,16.7],[74.4,16.45]]]}
 assert validate_name(feature,{'type':'Feature','id':feature['id'],'geometry':polygon},point)['accuracy_supported']
 with pytest.raises(ValueError):validate_name(feature,{'type':'Feature','id':feature['id'],'geometry':{'type':'Polygon','coordinates':[[[74.52,16.57],[74.53,16.57],[74.53,16.58],[74.52,16.58],[74.52,16.57]]]}},point)
