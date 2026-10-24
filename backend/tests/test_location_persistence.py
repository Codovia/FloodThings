"""Offline access/configuration guards. Live tests are explicitly separate."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app
from app.locations import LocationStore, LocationsUnavailable, get_store, matching
from app.location_database import DatabaseLocationStore, database_engine, content_hash


def test_default_file_backend(monkeypatch):
    monkeypatch.delenv('LOCATION_DIRECTORY_BACKEND',raising=False)
    assert isinstance(get_store(),LocationStore)


def test_explicit_database_backend(monkeypatch):
    monkeypatch.setenv('LOCATION_DIRECTORY_BACKEND','postgres')
    assert isinstance(get_store(),DatabaseLocationStore)


@pytest.mark.parametrize('mode',['postgres','unsupported'])
def test_unconfigured_directory_returns_503_weather_health_independent(monkeypatch,mode):
    monkeypatch.setenv('LOCATION_DIRECTORY_BACKEND',mode)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(app) as client:
        assert client.get('/api/locations/districts').status_code==503
        assert client.get('/api/health').status_code==200
        assert client.get('/api/weather?latitude=95&longitude=74').status_code==422


def test_database_error_does_not_fallback_or_expose_details():
    class FailedEngine:
        def connect(self):raise OperationalError('private_connection_detail',{},Exception('private_secret'))
    app.dependency_overrides[get_store]=lambda:DatabaseLocationStore(FailedEngine())
    try:
        with TestClient(app) as client:
            response=client.get('/api/locations/search?q=Udupi')
            assert response.status_code==503
            assert 'private' not in response.text and 'fallback' in response.text
    finally:app.dependency_overrides.pop(get_store,None)


@pytest.mark.parametrize('url',[None,'sqlite:///:memory:','not-a-url'])
def test_postgres_configuration_required(monkeypatch,url):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with pytest.raises(LocationsUnavailable):database_engine(url)


def test_canonical_hash_stable_for_jsonb_key_reordering():
    assert content_hash({'a':1,'b':[2,3]})==content_hash({'b':[2,3],'a':1})
    assert content_hash({'b':[3,2],'a':1})!=content_hash({'a':1,'b':[2,3]})


def test_duplicate_names_keep_stable_identity_in_search():
    rows=[{'id':'b','name':'Shared','aliases':[],'district_id':'other'}, {'id':'a','name':'Shared','aliases':[],'district_id':'district'}]
    assert [r['id'] for r in matching(rows,'shared')]==['a','b']
