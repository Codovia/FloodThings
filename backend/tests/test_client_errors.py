"""Browser crash reports are same-origin, minimal and safe to log."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.client_errors import router

ORIGIN = 'http://127.0.0.1:14180'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SHELTER_PUBLIC_ORIGIN', ORIGIN); monkeypatch.setenv('SHELTER_COOKIE_SECURE', 'false')
    app = FastAPI(); app.include_router(router)
    return TestClient(app)


def report(client, origin=ORIGIN, **body):
    return client.post('/api/client-errors', headers={'Origin': origin}, json={'error_id': 'a1b2c3d4e5f6', 'page': '/shelters', 'message': 'x is undefined', **body})


def test_a_report_is_logged_with_its_id_page_and_message_only(client, caplog):
    with caplog.at_level(logging.WARNING, logger='floodpulse'):
        assert report(client, message='Cannot read 13.3409123 at line\nFAKE LOG LINE').status_code == 204
    line = caplog.records[-1].getMessage()
    assert line == 'browser error a1b2c3d4e5f6 on /shelters: Cannot read 13.# at line FAKE LOG LINE'


@pytest.mark.parametrize('body', [{'page': '/shelters?lat=13.34'}, {'page': 'https://x.test/'}, {'error_id': 'nothex'}, {'message': ''},
                                  {'message': 'x' * 301}, {'stack': 'at App'}])
def test_anything_beyond_the_minimum_is_refused(client, body):
    assert report(client, **body).status_code == 422


def test_other_sites_cannot_write_to_the_log(client):
    assert report(client, origin='https://other.test').status_code == 403


def test_the_access_log_never_records_query_strings_such_as_coordinates():
    import app.main  # noqa: F401 - installs the filter
    record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ('127.0.0.1:5000', 'GET', '/api/weather?latitude=13.3409&longitude=74.7421', '1.1', 200), None)
    assert all(f.filter(record) for f in logging.getLogger('uvicorn.access').filters)
    assert record.getMessage() == '127.0.0.1:5000 - "GET /api/weather HTTP/1.1" 200'
