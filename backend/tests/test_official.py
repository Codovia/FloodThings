import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import official
from app.official import (OfficialService, OfficialUnavailable, active, decode_day, imd_district, imd_nowcast, names_district,
                          parse_cap, rss_items)

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)
# TEST FIXTURES ONLY: shapes follow the published IMD and CAP 1.2 formats; the values are invented.
SQUARE = {'type': 'MultiPolygon', 'coordinates': [[[[74.6, 13.5], [74.9, 13.5], [74.9, 13.8], [74.6, 13.8], [74.6, 13.5]]]]}
IMD_FEATURE = {'type': 'Feature', 'geometry': SQUARE, 'properties': {
    'District': 'UDUPI', 'Date': '2026-10-16', 'UTC': 6, 'updated_at': '2026-10-16T03:20:07Z',
    'Day_1': '16,4', 'Day_2': '2,4', 'Day_3': '1', 'Day_4': '99', 'Day_5': '',
    'Day1_Color': 2, 'Day2_Color': 3, 'Day3_Color': 4, 'Day4_Color': 3, 'Day5_Color': 0}}

# TEST FIXTURE ONLY: IMD district nowcast shape; update_time holds Indian time despite its "Z" (as the live layer does).
NOWCAST_FEATURE = {'type': 'Feature', 'geometry': SQUARE, 'properties': {
    'State_District': 'UDUPI', 'Date': '2026-10-16', 'update_time': '2026-10-16T08:45:00Z',
    'cat1': 0, 'cat2': 2, 'cat4': 4, 'cat6': 6, 'cat9': 0, 'cat16': 'TEST ONLY\nstrong winds along the coast', 'message': '  TEST ONLY  '}}


def cap_xml(identifier='IN-1_19', msg_type='Alert', status='Actual', expires='2026-10-16T12:00:00+05:30',
            headline='TEST ONLY: heavy rain likely over Udupi and Dakshina Kannada districts', references=''):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>{identifier}</identifier><sender>TEST-SDMA</sender>
<sent>2026-10-16T08:00:00+05:30</sent><status>{status}</status><msgType>{msg_type}</msgType><scope>Public</scope>
<references>{references}</references><info><language>en-IN</language><category>Met</category><event>Heavy rain</event>
<urgency>Expected</urgency><severity>Severe</severity><certainty>Likely</certainty><effective>2026-10-16T08:00:00+05:30</effective>
<expires>{expires}</expires><headline>{headline}</headline><instruction>Please follow SDMA guidelines.</instruction>
<area><areaDesc>2 districts of Karnataka</areaDesc><geocode><valueName>LGD District Code</valueName><value>550</value></geocode></area>
</info></alert>'''.encode()


def rss_xml(links):
    items = ''.join(f'<item><title>TEST</title><link>{l}</link><author>test@example.invalid</author></item>' for l in links)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>TEST</title>{items}</channel></rss>'.encode()


def test_imd_codes_and_colours_follow_the_published_tables():
    day = datetime(2026, 10, 16).date()
    assert decode_day('16,4', 2, day) == {'date': '2026-10-16', 'status': 'available', 'level': 'orange', 'meaning': 'Alert (be prepared)',
                                         'warnings': ['Very heavy rain', 'Thunderstorm & lightning, squall etc'], 'rain_warning': True}
    assert decode_day('1', 4, day)['warnings'] == [] and decode_day('1', 4, day)['level'] == 'green'
    assert decode_day('', 0, day)['status'] == 'unavailable'  # never "green" by default
    assert decode_day('99', 3, day)['status'] == 'unavailable'


TODAY = datetime(2026, 10, 16).date()


def test_imd_district_by_point_in_polygon_with_directory_name():
    found = imd_district([IMD_FEATURE], 13.62, 74.69, TODAY)
    assert found['district'] == 'Udupi' and found['imd_name'] == 'UDUPI'
    assert [d['date'] for d in found['days']] == ['2026-10-16', '2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20']
    assert [d['level'] for d in found['days']] == ['orange', 'yellow', 'green', None, None]
    assert imd_district([IMD_FEATURE], 12.97, 77.59, TODAY)['status'] == 'no_district'


def test_past_bulletin_days_are_dropped_and_old_bulletins_are_stale():
    later = imd_district([IMD_FEATURE], 13.62, 74.69, datetime(2026, 10, 17).date())
    assert later['status'] == 'available' and later['days'][0]['date'] == '2026-10-17' and len(later['days']) == 4
    old = imd_district([IMD_FEATURE], 13.62, 74.69, datetime(2026, 10, 18).date())
    assert old['status'] == 'stale' and 'not shown as current' in old['message']


def test_nowcast_decodes_published_categories_and_reads_indian_time():
    body = imd_nowcast([NOWCAST_FEATURE], 13.62, 74.69, NOW)
    assert body['status'] == 'available' and body['district'] == 'Udupi'
    assert body['categories'] == ['Light rain (under 5 mm/h)', 'Light thunderstorm (gusts under 40 km/h)', 'Lightning possible (under 30%)']
    assert body['issued_at'] == '2026-10-16T08:45:00+05:30' and body['valid_until'] == '2026-10-16T11:45:00+05:30'
    assert body['other'] == 'TEST ONLY strong winds along the coast' and body['message'] == 'TEST ONLY'
    quiet = {**NOWCAST_FEATURE, 'properties': {**NOWCAST_FEATURE['properties'], 'cat1': 1, 'cat2': 0, 'cat4': '', 'cat6': None, 'cat16': '', 'message': ''}}
    assert imd_nowcast([quiet], 13.62, 74.69, NOW)['categories'] == []
    assert imd_nowcast([NOWCAST_FEATURE], 20.0, 80.0, NOW)['status'] == 'not_issued'


def test_old_or_future_nowcasts_are_never_current():
    def at(stamp):
        return imd_nowcast([{**NOWCAST_FEATURE, 'properties': {**NOWCAST_FEATURE['properties'], 'update_time': stamp}}], 13.62, 74.69, NOW)
    old = at('2026-10-16T06:20:00Z')  # 3 h 10 min before 09:30 IST
    assert old['status'] == 'expired' and 'categories' not in old and 'older than three hours' in old['message']
    assert at('2026-10-16T13:00:00Z')['status'] == 'expired'  # later than now even as IST: unverifiable
    assert at('not a time')['status'] == 'expired'


def test_cap_parsing_and_safety():
    alert = parse_cap(cap_xml())
    assert alert['severity'] == 'Severe' and alert['event'] == 'Heavy rain' and alert['lgd_district_codes'] == ['550']
    with pytest.raises(OfficialUnavailable):
        parse_cap(b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"/>')
    with pytest.raises(OfficialUnavailable):
        parse_cap(b'<rss/>')
    assert rss_items(rss_xml(['https://sachet.ndma.gov.in/x?identifier=1', 'https://elsewhere.example/y'])) == [
        {'link': 'https://sachet.ndma.gov.in/x?identifier=1', 'title': 'TEST', 'author': 'test@example.invalid'}]


def test_only_actual_unexpired_uncancelled_alerts_are_active():
    alerts = [parse_cap(cap_xml('IN-1_19')), parse_cap(cap_xml('IN-2_19', expires='2026-10-16T08:59:00+05:30')),
              parse_cap(cap_xml('IN-3_19', status='Exercise')), parse_cap(cap_xml('IN-4_19')),
              parse_cap(cap_xml('IN-5_19', msg_type='Cancel', references='TEST,IN-4_19,2026-10-16T08:00:00+05:30'))]
    assert [a['identifier'] for a in active(alerts, NOW)] == ['IN-1_19']
    assert active(alerts, NOW)[0]['expires_in_minutes'] == 150


def test_district_naming_uses_known_spellings_with_word_boundaries():
    alert = parse_cap(cap_xml(headline='TEST ONLY: thunderstorm over Chikkamagaluru and Shivamogga'))
    assert names_district(alert, 'CHIKMAGALUR') and names_district(alert, 'SHIMOGA')
    assert not names_district(alert, 'UDUPI') and not names_district(alert, None)


def handler_factory(calls, imd_status=200, rss_status=200):
    def handler(request):
        calls.append(str(request.url))
        if request.url.host == 'reactjs.imd.gov.in':
            feature = NOWCAST_FEATURE if request.url.params.get('typename') == 'imd:NowcastWarningDistrict' else IMD_FEATURE
            return httpx.Response(imd_status, json={'type': 'FeatureCollection', 'features': [feature]})
        if request.url.path.endswith('rss_karnataka.xml'):
            return httpx.Response(rss_status, content=rss_xml(['https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier=1']))
        if 'FetchXMLFile' in request.url.path:
            return httpx.Response(200, content=cap_xml())
        return httpx.Response(404)
    return handler


def service(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client, OfficialService(client, clock=lambda: NOW.timestamp())


def test_service_combines_sources_and_caches():
    calls = []
    client, svc = service(handler_factory(calls))
    body = asyncio.run(svc.warnings(13.62, 74.69))
    assert body['official'] is True and body['imd']['district'] == 'Udupi'
    assert body['sachet']['status'] == 'available' and body['sachet']['alerts'][0]['names_your_district'] is True
    assert body['nowcast']['status'] == 'available' and body['nowcast']['district'] == 'Udupi'
    first = len(calls)
    asyncio.run(svc.warnings(13.62, 74.69))
    assert len(calls) == first
    asyncio.run(client.aclose())


def test_failures_are_unavailable_never_no_warning():
    client, svc = service(handler_factory([], imd_status=503, rss_status=503))
    body = asyncio.run(svc.warnings(13.62, 74.69))
    assert body['imd']['status'] == 'unavailable' and 'does not mean there is no warning' in body['imd']['message']
    assert body['sachet']['status'] == 'unavailable' and body['sachet']['alerts'] == []
    assert body['nowcast']['status'] == 'unavailable' and 'categories' not in body['nowcast']
    asyncio.run(client.aclose())


def test_route_validation():
    app = FastAPI()
    app.include_router(official.router)
    client, svc = service(handler_factory([]))
    app.state.official = svc
    with TestClient(app) as http:
        assert http.get('/api/official/warnings', params={'latitude': 13.62}).status_code == 422
        assert http.get('/api/official/warnings', params={'latitude': 19.5, 'longitude': 73.0}).status_code == 422
        statewide = http.get('/api/official/warnings')
        assert statewide.status_code == 200 and statewide.json()['imd']['status'] == 'not_requested'
        assert statewide.headers['cache-control'] == 'no-store'
    asyncio.run(client.aclose())


def test_statewide_districts_keep_only_karnataka_and_suggest_only_orange_red():
    from app.official import karnataka_districts, official_suggestions
    neighbour = {**IMD_FEATURE, 'properties': {**IMD_FEATURE['properties'], 'District': 'KASARAGOD'}}
    green = {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[76.0, 15.0], [76.3, 15.0], [76.3, 15.3], [76.0, 15.3], [76.0, 15.0]]]},
             'properties': {**IMD_FEATURE['properties'], 'District': 'GADAG', 'Day_1': '1', 'Day1_Color': 4, 'Day_2': '1', 'Day2_Color': 4}}
    districts = karnataka_districts([IMD_FEATURE, neighbour, green], TODAY)
    assert [d['district'] for d in districts] == ['Gadag', 'Udupi']
    assert [day['level'] for day in districts[1]['days']] == ['orange', 'yellow'] and districts[1]['geometry']['type'] == 'MultiPolygon'
    drafts = official_suggestions(districts, NOW.isoformat())
    assert [s['id'] for s in drafts['suggestions']] == ['imd-UDUPI-2026-10-16']
    first = drafts['suggestions'][0]
    assert first['source'] == 'OFFICIAL_WARNING' and first['suggested_kind'] == 'informational'
    assert 'India Meteorological Department' in first['suggested_message'] and 'not a government channel' in first['suggested_message']
    assert 'explicitly approve' in drafts['note']


def test_district_endpoint_and_admin_suggestions_require_login():
    app = FastAPI()
    app.include_router(official.router)
    client, svc = service(handler_factory([]))
    app.state.official = svc
    with TestClient(app) as http:
        body = http.get('/api/official/districts').json()
        assert body['status'] == 'available' and body['districts'][0]['district'] == 'Udupi'
        denied = http.get('/api/admin/official/suggestions')
        assert denied.status_code in (401, 403, 503) and 'suggestions' not in denied.json()
    asyncio.run(client.aclose())


def test_official_tls_context_adds_only_the_pinned_emsign_root(monkeypatch, tmp_path):
    from app.official import official_tls_context, EMSIGN_ROOT
    context = official_tls_context()
    subjects = [dict(x[0] for x in c['subject']).get('commonName') for c in context.get_ca_certs()]
    assert 'emSign Root CA - G1' in subjects
    assert context.verify_mode.name == 'CERT_REQUIRED' and context.check_hostname
    # A swapped certificate file is refused (fingerprint pin).
    import ssl
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        other = Path(folder) / 'other.pem'
        der = ssl.PEM_cert_to_DER_cert(EMSIGN_ROOT.read_text())
        other.write_text(ssl.DER_cert_to_PEM_cert(der[:-1] + bytes([der[-1] ^ 1])))
        monkeypatch.setattr(official, 'EMSIGN_ROOT', other)
        try:
            official_tls_context()
            assert False, 'tampered certificate accepted'
        except RuntimeError as error:
            assert 'fingerprint' in str(error)
