"""GPS camera capture metadata — TEST FIXTURES ONLY (invented coordinates, times and polygon)."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.reports import ReportInput, capture_record, report_district

NOW = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)


def payload(**over):
    base = dict(request_id=str(uuid.uuid4()), withdrawal_secret='a' * 64, event_type='flooding', description='TEST FIXTURE water on road',
                observed_at=NOW.isoformat(), gps_at=(NOW - timedelta(seconds=4)).isoformat(), position_source='BROWSER_GPS',
                latitude=13.34, longitude=74.74, accuracy_m=12.0, consent=True, image_rights=True,
                photo_base64='AAAA', photo_mime='image/jpeg', capture={'source': 'IN_APP_GPS_CAMERA', 'captured_at': NOW.isoformat()})
    base.update(over)
    return ReportInput.model_validate(base)


def test_capture_requires_photo_and_live_gps():
    assert payload().capture.source == 'IN_APP_GPS_CAMERA'
    for over in ({'photo_base64': None, 'photo_mime': None}, {'position_source': 'USER_SELECTED_MAP', 'location_selected_at': NOW.isoformat()}, {'gps_at': None}):
        with pytest.raises(ValidationError):
            payload(**over)
    with pytest.raises(ValidationError):
        payload(capture={'source': 'GALLERY', 'captured_at': NOW.isoformat()})
    with pytest.raises(ValidationError):
        payload(capture={'source': 'IN_APP_GPS_CAMERA', 'captured_at': NOW.isoformat(), 'address': 'not accepted'})
    assert payload(capture=None).capture is None  # reports without the camera keep working


def test_capture_record_is_labelled_client_reported_and_flags_gaps():
    record = capture_record(payload(), NOW + timedelta(seconds=30))
    assert record == {'source': 'IN_APP_GPS_CAMERA', 'client_reported': True, 'captured_at': NOW.isoformat(),
                      'gps_fix_at': (NOW - timedelta(seconds=4)).isoformat(), 'gps_fix_gap_s': 4, 'gps_accuracy_m': 12.0, 'flags': []}
    late = capture_record(payload(gps_at=(NOW - timedelta(minutes=3)).isoformat()), NOW + timedelta(seconds=30))
    assert 'CAPTURE_GPS_GAP_OVER_60S' in late['flags']
    old = capture_record(payload(), NOW + timedelta(minutes=30))
    assert 'CAPTURE_TIME_OUT_OF_RANGE' in old['flags']


def test_district_comes_from_imd_boundaries_without_external_lookup(monkeypatch):
    square = {'type': 'Polygon', 'coordinates': [[[74.5, 13.2], [75.0, 13.2], [75.0, 13.8], [74.5, 13.8], [74.5, 13.2]]]}
    async def fake_statewide(service):
        return [{'district': 'Udupi', 'geometry': square}], {'error': None}
    import app.official as official
    monkeypatch.setattr(official, 'statewide', fake_statewide)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(official=object())))
    assert asyncio.run(report_district(request, 13.34, 74.74)) == {'name': 'Udupi', 'source': 'IMD district boundary (map service)'}
    assert asyncio.run(report_district(request, 15.0, 76.0)) is None
    assert asyncio.run(report_district(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())), 13.34, 74.74)) is None
