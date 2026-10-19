"""Unexpected errors: generic reply to visitors, full details only in the server log."""
import logging

from fastapi.testclient import TestClient

from app.main import app


def test_unexpected_error_is_generic_logged_and_hides_internals(caplog):
    @app.get('/api/_test_crash')
    def crash(latitude: float = 0):
        raise RuntimeError('TEST internal detail /secret/path password=hunter2')
    try:
        with caplog.at_level(logging.ERROR, logger='floodpulse'), TestClient(app, raise_server_exceptions=False) as http:
            response = http.get('/api/_test_crash', params={'latitude': 13.34})
        body = response.json()
        assert response.status_code == 500 and body['status'] == 'error' and len(body['error_id']) == 12
        assert 'secret' not in response.text and 'RuntimeError' not in response.text and 'Traceback' not in response.text
        record = next(r for r in caplog.records if body['error_id'] in r.getMessage())
        assert '/api/_test_crash' in record.getMessage() and '13.34' not in record.getMessage()  # no query string
        assert record.exc_info and 'TEST internal detail' in str(record.exc_info[1])  # full detail kept server-side
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', '') != '/api/_test_crash']


def test_imd_parser_errors_are_reported_generically():
    import asyncio
    import httpx
    from app.official import OfficialService
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'not json')))
    raw = asyncio.run(OfficialService(client).imd_features())
    assert raw['features'] is None and raw['error'] == 'invalid response'
    asyncio.run(client.aclose())


def test_readiness_reports_database_state(monkeypatch):
    import app.shelters as shelters

    class Broken:
        def connect(self):
            raise RuntimeError('TEST connection refused to db:5432 password=x')
    fake = lambda: Broken()
    fake.cache_info = lambda: type('Info', (), {'currsize': 0})()  # shutdown cleanup checks the cache
    monkeypatch.setattr(shelters, 'shelter_engine', fake)
    with TestClient(app) as http:
        response = http.get('/api/health/ready')
    assert response.status_code == 503 and response.json() == {'status': 'unavailable', 'database': 'unavailable'}
    assert 'password' not in response.text and '5432' not in response.text
