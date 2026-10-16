import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import routing
from app.shelters import get_store

SHELTER = {'id': '11111111-1111-1111-1111-111111111111', 'name': 'Test fixture shelter', 'latitude': 13.35,
           'longitude': 74.79, 'available_capacity': 20}
ROUTE = {'type': 'FeatureCollection', 'features': [{'type': 'Feature',
         'geometry': {'type': 'LineString', 'coordinates': [[74.69, 13.62], [74.79, 13.35]]},
         'properties': {'summary': {'distance': 31234.4, 'duration': 2400.2},
                        'segments': [{'steps': [{'instruction': 'Head south', 'distance': 100.0, 'duration': 10.0}]}]}}]}
BODY = {'shelter_id': SHELTER['id'], 'origin': {'latitude': 13.62, 'longitude': 74.69, 'accuracy_m': 25}}


class Store:
    engine = object()


def make_app(monkeypatch, handler, points=(), shelter=SHELTER):
    monkeypatch.setattr(routing, 'report_points', lambda *a: list(points))
    import app.notifications as notifications
    monkeypatch.setattr(notifications, 'available_shelter', lambda store, identity: dict(shelter))
    app = FastAPI()
    app.include_router(routing.router)
    app.dependency_overrides[routing.store_provider] = lambda: (lambda: Store())
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return app


def test_not_configured_keeps_external_link(monkeypatch):
    monkeypatch.delenv('OPENROUTESERVICE_API_KEY', raising=False)
    with TestClient(make_app(monkeypatch, lambda r: httpx.Response(500))) as http:
        assert http.get('/api/route/status').json()['configured'] is False
        response = http.post('/api/route', json=BODY)
        assert response.status_code == 503 and response.json()['status'] == 'not_configured'


def test_not_configured_is_reported_before_the_shelter_database_is_opened(monkeypatch):
    monkeypatch.delenv('OPENROUTESERVICE_API_KEY', raising=False)
    app = make_app(monkeypatch, lambda r: httpx.Response(500))

    def no_database():
        raise AssertionError('shelter database must not be opened without a routing key')
    app.dependency_overrides[routing.store_provider] = lambda: no_database
    with TestClient(app) as http:
        response = http.post('/api/route', json=BODY)
        assert response.status_code == 503 and response.json()['status'] == 'not_configured'


def test_route_avoids_approved_reports_and_never_claims_safety(monkeypatch):
    monkeypatch.setenv('OPENROUTESERVICE_API_KEY', 'test-key-not-real')
    seen = {}

    def handler(request):
        seen['auth'] = request.headers['authorization']
        seen['body'] = json.loads(request.content)
        seen['path'] = request.url.path
        return httpx.Response(200, json=ROUTE)
    with TestClient(make_app(monkeypatch, handler, points=[(13.5, 74.72), (13.4, 74.75)])) as http:
        response = http.post('/api/route', json=BODY)
    body = response.json()
    assert response.status_code == 200 and body['status'] == 'available'
    assert body['flood_safe_certified'] is False and 'NOT certified flood-safe' in body['label']
    assert body['avoided_reports'] == 2 and body['distance_m'] == 31234
    assert seen['path'] == '/v2/directions/foot-walking/geojson' and seen['auth'] == 'test-key-not-real'
    polygons = seen['body']['options']['avoid_polygons']
    assert polygons['type'] == 'MultiPolygon' and len(polygons['coordinates']) == 2
    ring = polygons['coordinates'][0][0]
    assert ring[0] == ring[-1] and len(ring) == 9


def test_no_reports_sends_no_avoid_option(monkeypatch):
    monkeypatch.setenv('OPENROUTESERVICE_API_KEY', 'test-key-not-real')
    seen = {}
    with TestClient(make_app(monkeypatch, lambda r: seen.update(body=json.loads(r.content)) or httpx.Response(200, json=ROUTE))) as http:
        assert http.post('/api/route', json=BODY).json()['avoided_reports'] == 0
    assert 'options' not in seen['body']


@pytest.mark.parametrize('status,expected', [(429, 'rate_limited'), (404, 'no_route'), (500, 'no_route')])
def test_provider_errors_are_honest(monkeypatch, status, expected):
    monkeypatch.setenv('OPENROUTESERVICE_API_KEY', 'test-key-not-real')
    with TestClient(make_app(monkeypatch, lambda r: httpx.Response(status, json={'error': 'x'}))) as http:
        response = http.post('/api/route', json=BODY)
    assert response.json()['status'] == expected and 'geometry' not in response.json()


def test_full_shelter_and_bad_origins_are_refused(monkeypatch):
    monkeypatch.setenv('OPENROUTESERVICE_API_KEY', 'test-key-not-real')
    with TestClient(make_app(monkeypatch, lambda r: httpx.Response(200, json=ROUTE), shelter={**SHELTER, 'available_capacity': 0})) as http:
        assert http.post('/api/route', json=BODY).status_code == 409
        outside = {**BODY, 'origin': {'latitude': 19.5, 'longitude': 73.0, 'accuracy_m': 10}}
        assert http.post('/api/route', json=outside).status_code == 422
        vague = {**BODY, 'origin': {**BODY['origin'], 'accuracy_m': 5000}}
        assert http.post('/api/route', json=vague).status_code == 422
