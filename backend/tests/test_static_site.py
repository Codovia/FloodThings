"""Production static serving — TEST FIXTURES ONLY (a tiny fake build directory, removed after each test)."""
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_site import mount_frontend


@pytest.fixture
def build():
    # A private directory outside the guarded tmp_path; deleted automatically.
    with tempfile.TemporaryDirectory() as parent:
        root = Path(parent) / 'dist'
        root.mkdir()
        yield root


def make(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>TEST index</title>')
    (tmp_path / 'assets' / 'app-123.js').write_text('console.log(1)')
    (tmp_path / 'manifest.webmanifest').write_text('{}')
    (tmp_path.parent / 'secret.txt').write_text('outside the build')
    app = FastAPI()

    @app.get('/api/ping')
    def ping():
        return {'ok': True}
    mount_frontend(app, tmp_path)
    return TestClient(app)


def test_serves_files_routes_and_headers(build):
    http = make(build)
    assert http.get('/api/ping').json() == {'ok': True}
    page = http.get('/shelters')
    assert page.status_code == 200 and 'TEST index' in page.text and page.headers['cache-control'] == 'no-cache'
    assert page.headers['x-frame-options'] == 'DENY' and page.headers['x-content-type-options'] == 'nosniff'
    asset = http.get('/assets/app-123.js')
    assert asset.status_code == 200 and 'immutable' in asset.headers['cache-control']
    assert http.get('/manifest.webmanifest').headers['content-type'].startswith('application/manifest+json')


def test_api_paths_and_traversal_never_fall_back(build):
    http = make(build)
    assert http.get('/api/missing').status_code == 404
    leaked = http.get('/..%2Fsecret.txt')
    assert 'outside the build' not in leaked.text
