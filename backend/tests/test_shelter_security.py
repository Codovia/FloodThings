"""Offline security/state checks: no database or live provider calls."""
import os,secrets
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.shelter_security import HASHER,SecurityConfig,csrf_token,digest,password_matches
from app.shelters import ShelterInput,Verification,serialize,directions,get_store,VERIFICATION_HOURS,mode
from app.shelter_schema import SHELTER_TABLES,shelters


def pending():
    return {'name':'ISOLATED TEST ONLY','address':'Test fixture, never a real shelter','district_id':'nic:udupi.nic.in','capacity':10,'occupancy':0}


def opening():
    return {**pending(),'latitude':13.5,'longitude':74.7,'status':'open','verification':{'authorization':True,'entrance':True,'usability':True,'capacity':True,'evidence':'Isolated unit-test confirmation only'}}


def test_memory_hard_password_salt_and_verification():
    password=secrets.token_urlsafe(24);a=HASHER.hash(password);b=HASHER.hash(password)
    assert a.startswith('$scrypt$ln=17,r=8,p=1$') and a!=b and password not in a
    assert password_matches(a,password) and not password_matches(a,'wrong password')
    assert not password_matches(a.replace('ln=17','ln=10'),password)
    assert not password_matches('malformed',password)


@pytest.mark.parametrize('field',['authorization','entrance','usability','capacity','evidence'])
def test_open_requires_every_explicit_confirmation(field):
    body=opening();body['verification'][field]='' if field=='evidence' else False
    with pytest.raises(ValidationError):ShelterInput(**body)


@pytest.mark.parametrize('change',[{'latitude':91},{'longitude':181},{'latitude':float('nan')},{'latitude':None},{'capacity':0},{'occupancy':11},{'occupancy':10},{'capacity':True},{'status':'full','occupancy':1}])
def test_invalid_entrance_capacity_or_status(change):
    with pytest.raises(ValidationError):ShelterInput(**{**opening(),**change})


def test_pending_can_have_unknown_entrance_without_becoming_open():
    p=ShelterInput(**pending());assert p.status=='pending' and p.latitude is None
    assert ShelterInput(**{**opening(),'status':'full','occupancy':10}).status=='full'
    with pytest.raises(ValidationError):Verification(authorization='true')


@pytest.mark.parametrize('secure,origin',[('false','https://example.com'),('false','http://example.com'),('true','http://127.0.0.1:5173'),('false','http://127.0.0.1:5173/path'),('nonsense','https://example.com')])
def test_fail_closed_cookie_configuration(monkeypatch,secure,origin):
    monkeypatch.setenv('SHELTER_COOKIE_SECURE',secure);monkeypatch.setenv('SHELTER_PUBLIC_ORIGIN',origin)
    with pytest.raises(HTTPException):SecurityConfig()


def test_origin_and_csrf_are_independent_controls(monkeypatch):
    monkeypatch.setenv('SHELTER_COOKIE_SECURE','true');monkeypatch.setenv('SHELTER_PUBLIC_ORIGIN','https://example.com')
    config=SecurityConfig();token=secrets.token_urlsafe(32)
    assert config.cookie.startswith('__Host-') and csrf_token(token)!=digest(token)
    config.require_csrf(SimpleNamespace(headers={'origin':config.origin,'x-csrf-token':csrf_token(token)}),token)
    for headers in [{'origin':'https://evil.example','x-csrf-token':csrf_token(token)},{'origin':config.origin},{'origin':config.origin,'x-csrf-token':'wrong'},{'origin':config.origin,'x-csrf-token':csrf_token(token),'sec-fetch-site':'cross-site'}]:
        with pytest.raises(HTTPException) as error:config.require_csrf(SimpleNamespace(headers=headers),token)
        assert error.value.status_code==403


def test_directions_encode_exact_entrance_and_optional_origin():
    from urllib.parse import urlsplit,parse_qs
    url=directions(13.5,74.7,12.9,74.8);q=parse_qs(urlsplit(url).query)
    assert q=={'api':['1'],'destination':['13.5,74.7'],'origin':['12.9,74.8']}
    assert '%2C' in url and 'origin=' not in directions(13.5,74.7)


def test_public_serialization_omits_private_contact_notes_and_actor():
    now=datetime.now(timezone.utc)
    row={**pending(),'id':'isolated-test','district_name':'Udupi','latitude':13.5,'longitude':74.7,'status':'open','water':'unknown','toilets':'yes','accessibility':'Unknown','verified_at':now,'updated_at':now,'restrictions':'TEST ONLY','demonstration':True,'contact':'private test contact','publish_contact':False,'notes':'private note','created_by':'private actor','verification_notes':'private evidence','straight_line_km':2.345678}
    result=serialize(row,True)
    assert result['contact'] is None and result['available_capacity']==10 and result['straight_line_km']==2.346
    assert not {'notes','created_by','verification_notes'}&result.keys()
    assert result['verification_expires_at']==now+timedelta(hours=VERIFICATION_HOURS)


def test_no_public_write_route_and_no_public_registration():
    with TestClient(app) as client:
        for path in ['/api/shelters','/api/admin/register']:
            assert client.post(path,json={}).status_code in (404,405)


def test_validation_errors_do_not_echo_credentials(monkeypatch):
    app.dependency_overrides[get_store]=lambda:object()
    secret=secrets.token_urlsafe(30)
    try:
        with TestClient(app) as client:
            r=client.post('/api/admin/login',json={'username':'INVALID','password':secret})
            assert r.status_code==422 and secret not in r.text and r.headers['cache-control']=='no-store'
    finally:app.dependency_overrides.pop(get_store,None)


def test_unconfigured_database_is_explicit_without_weather_dependency(monkeypatch):
    from app.shelters import shelter_engine
    monkeypatch.delenv('SHELTER_DATABASE_URL',raising=False);shelter_engine.cache_clear()
    with TestClient(app) as client:
        assert client.get('/api/shelters').status_code==503
        assert client.get('/api/health').status_code==200


def test_schema_separates_audit_and_directory_tables():
    assert len(SHELTER_TABLES)==5 and 'location_directory_districts' not in [t.name for t in SHELTER_TABLES]
    assert shelters.c.entrance.type.srid==4326 and shelters.c.entrance.type.geometry_type=='POINT'
    assert shelters.c.demonstration.nullable is False
    constraints=' '.join(str(c.sqltext) for c in shelters.constraints if hasattr(c,'sqltext'))
    assert 'occupancy < capacity' in constraints and 'ST_X(entrance)=longitude' in constraints and 'authorization_confirmed' in constraints


def test_invalid_mode_fails_closed(monkeypatch):
    monkeypatch.setenv('SHELTER_DIRECTORY_MODE','unknown')
    with pytest.raises(HTTPException):mode()
