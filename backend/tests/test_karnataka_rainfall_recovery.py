"""Recovery fixtures use disposable paths; no network or research dataset writes."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BASE = Path(__file__).resolve().parents[2] / 'backend/tests/test_karnataka_rainfall.py'
spec = importlib.util.spec_from_file_location('rainfall_fixture_helpers', BASE)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
rain = helpers.rain


class ReadTimeout(TimeoutError):
    """Controlled transport timeout; EE exposes requests timeouts as TimeoutError."""


def test_timeout_recovers_with_three_attempts_and_bounded_exponential_backoff():
    with TemporaryDirectory() as directory:
        log = Path(directory)/'requests.jsonl'
        call = MagicMock(side_effect=[TimeoutError('private provider text'), ReadTimeout('private provider text'), {'id': 'fixture'}])
        sleep = MagicMock()
        assert rain.bounded_request(call, 'image_metadata', log, '2025-03-05', sleep=sleep) == {'id': 'fixture'}
        assert call.call_count == 3
        assert [c.args[0] for c in sleep.call_args_list] == [2, 4]
        entries = [json.loads(line) for line in log.read_text().splitlines()]
        assert [e['status'] for e in entries] == ['failed', 'failed', 'succeeded']
        assert entries[0]['category'] == entries[1]['category'] == 'network_timeout'
        assert 'private provider text' not in log.read_text()


def test_exhausted_timeout_stops_at_three_and_preserves_accurate_failure():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        log = root/'request_attempts.jsonl'
        call, sleep = MagicMock(side_effect=TimeoutError('secret signed URL')), MagicMock()
        with pytest.raises(rain.BoundedRequestFailure) as caught:
            rain.bounded_request(call, 'image_metadata', log, '2025-03-05', sleep=sleep)
        assert call.call_count == 3 and sleep.call_count == 2
        args = SimpleNamespace(mode='month', month=3, raw_directory=root)
        (root/'retrieval.jsonl').write_text(''.join(json.dumps({'stage': 'validated', 'date': f'2025-03-{i:02d}'})+'\n' for i in range(1, 5)))
        rain.record_failure(args, caught.value)
        failure = json.loads((root/'failure.json').read_text())
        assert failure['attempts'] == 3 and failure['category'] == 'network_timeout'
        assert failure['operation'] == 'image_metadata' and failure['failed_date'] == '2025-03-05'
        assert len(failure['unreviewed_dates']) == 26
        assert 'secret signed URL' not in (root/'failure.json').read_text()


@pytest.mark.parametrize('error,category', [
    (RuntimeError('Image.load: Image asset fixture not found (does not exist or caller does not have access).'), 'source_unavailable_or_access_denied'),
    (ValueError('Invalid grid'), 'non_retryable_error'),
])
def test_source_unavailability_and_validation_errors_are_not_retried(error, category):
    with TemporaryDirectory() as directory:
        call, sleep = MagicMock(side_effect=error), MagicMock()
        with pytest.raises(rain.BoundedRequestFailure) as caught:
            rain.bounded_request(call, 'image_metadata', Path(directory)/'requests.jsonl', sleep=sleep)
        assert caught.value.category == category and call.call_count == 1
        sleep.assert_not_called()


@pytest.mark.parametrize('status,retried', [(503, True), (429, True), (403, False), (404, False)])
def test_http_status_controls_bounded_retries(status, retried):
    with TemporaryDirectory() as directory:
        error = RuntimeError('provider error')
        error.resp = SimpleNamespace(status=status)
        call, sleep = MagicMock(side_effect=error), MagicMock()
        with pytest.raises(rain.BoundedRequestFailure):
            rain.bounded_request(call, 'download_url', Path(directory)/'requests.jsonl', sleep=sleep)
        assert call.call_count == (3 if retried else 1)


def test_nested_ee_timeout_is_classified_from_original_cause():
    timeout = TimeoutError('private URL')
    wrapper = RuntimeError('opaque SDK message')
    wrapper.__cause__ = timeout
    assert rain.failure_category(wrapper) == ('network_timeout', None)


def test_client_retries_disabled_before_init_and_sixty_second_deadline(monkeypatch):
    with TemporaryDirectory() as directory:
        ee = MagicMock()
        ee.Number.return_value.getInfo.return_value = 1
        access = rain.initialize_access(ee, 60, Path(directory)/'requests.jsonl')
        assert access['initialization'] == 'succeeded'
        calls = [str(c) for c in ee.mock_calls]
        assert calls.index('call.data.setMaxRetries(0)') < calls.index("call.Initialize(project='floodpulse')")
        ee.data.setDeadline.assert_called_once_with(60000)
        ee.Number.return_value.getInfo.assert_called_once()
        for deadline in [0, 61, True]:
            with pytest.raises(ValueError, match='1–60'):
                rain.initialize_access(ee, deadline, Path(directory)/'requests.jsonl')


def test_invalid_attempt_counts_cannot_expand_the_retry_budget():
    with TemporaryDirectory() as directory:
        call = MagicMock()
        for count in [0, 4, True]:
            with pytest.raises(ValueError, match='1–3'):
                rain.bounded_request(call, 'image_metadata', Path(directory)/'requests.jsonl', attempts=count)
        call.assert_not_called()


def test_total_runtime_exception_is_never_retried_and_is_recorded():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        call = MagicMock(side_effect=rain.verification.VerificationDeadlineExceeded('Verification exceeded 900 seconds'))
        sleep = MagicMock()
        with pytest.raises(rain.verification.VerificationDeadlineExceeded) as caught:
            rain.bounded_request(call, 'image_metadata', root/'requests.jsonl', sleep=sleep)
        assert call.call_count == 1
        sleep.assert_not_called()
        rain.record_failure(SimpleNamespace(mode='month', month=3, raw_directory=root), caught.value)
        assert json.loads((root/'failure.json').read_text())['category'] == 'total_runtime_limit'


def test_failed_download_keeps_partial_bytes_and_retries_exclusively(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        count = 0
        def controlled_download(session, url, path):
            nonlocal count
            count += 1
            path.write_bytes(b'partial fixture' if count == 1 else b'complete fixture')
            if count == 1:
                raise rain.BoundedRequestFailure('raster_download', None, 1, 'network_timeout', 'ReadTimeout')
            return {'sha256': rain.soi.digest(path), 'bytes': path.stat().st_size}
        monkeypatch.setattr(rain, 'download', controlled_download)
        monkeypatch.setattr(rain.time, 'sleep', MagicMock())
        path = root/'20250305.tif'
        result = rain.download_with_retries(None, 'fixture-only', path, root/'requests.jsonl', '2025-03-05')
        assert count == 2 and path.read_bytes() == b'complete fixture'
        assert (root/'20250305.attempt1.partial.tif').read_bytes() == b'partial fixture'
        assert result['sha256'] == rain.soi.digest(path)


def info_for(day):
    info = deepcopy(helpers.image_info())
    info['id'] = rain.SOURCE+'/'+day.replace('-', '')
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000)
    info['properties'] = {'system:time_start': start, 'system:time_end': start+86400000}
    return info


def test_resume_uses_cached_first_four_days_without_queries_or_mutation(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        boundary_dir, partial = root/'boundary', root/'partial'
        boundary_dir.mkdir(); partial.mkdir()
        (boundary_dir/'manifest.json').write_text('controlled fixture only')
        districts = helpers.fixture_districts()
        boundary = {'version': rain.soi.VERSION, 'district_records': [d['identity'] for d in districts],
                    'sources': {'archive': {'sha256': '0'*64}, 'district_components': [{'sha256': '1'*64}]},
                    'files': {'districts.shp': {'sha256': '2'*64}}}
        monkeypatch.setattr(rain, 'load_boundaries', lambda _: (districts, 'EPSG:4326', boundary))
        monkeypatch.setattr(rain, 'initialize_access', lambda *_: {'initialization': 'fixture only'})
        for day in rain.requested_dates('month', 3)[:4]:
            path = partial/(day.replace('-', '')+'.tif')
            helpers.fixture_raster(path)
            record = rain.image_record(info_for(day), day)
            record.update(file=path.name, download={'retrieved_at': '2026-10-04T00:00:00+00:00',
                                                   'sha256': rain.soi.digest(path), 'bytes': path.stat().st_size})
            record['raster_metadata'] = rain.read_raster(path, helpers.PARAMETERS)[2]
            with (partial/'retrieval.jsonl').open('a') as stream:
                stream.write(json.dumps({'stage': 'validated', **record})+'\n')
        before = helpers.snapshot(partial)
        requested = []
        def get_image(asset):
            day = datetime.strptime(asset.rsplit('/', 1)[1], '%Y%m%d').date().isoformat()
            requested.append(day)
            image = MagicMock(); image.getInfo.return_value = info_for(day)
            return image
        ee = MagicMock(); ee.Image.side_effect = get_image
        def controlled_download(session, url, path):
            helpers.fixture_raster(path)
            return {'retrieved_at': '2026-10-04T00:00:00+00:00', 'sha256': rain.soi.digest(path), 'bytes': path.stat().st_size}
        monkeypatch.setattr(rain, 'download', controlled_download)
        args = SimpleNamespace(mode='month', month=3, boundaries=boundary_dir, output=root/'complete',
                               raw_directory=root/'raw', metadata_output=root/'metadata.json',
                               reuse_smoke=None, reuse_raw=None, reuse_partial_raw=partial, ee_deadline_seconds=60)
        rain.extract(args, ee, MagicMock())
        assert requested == rain.requested_dates('month', 3)[4:]
        assert helpers.snapshot(partial) == before
        assert rain.validate_dataset(args.output, args.raw_directory, boundary_dir)['valid_records'] == 62
        for day in rain.requested_dates('month', 3)[:4]:
            name = day.replace('-', '')+'.tif'
            assert (partial/name).read_bytes() == (args.raw_directory/name).read_bytes()
        complete = helpers.snapshot(root)
        assert rain.validate_dataset(args.output, args.raw_directory, boundary_dir)['valid_records'] == 62
        assert helpers.snapshot(root) == complete
        with (args.raw_directory/'request_attempts.jsonl').open('a') as stream:
            stream.write('{}\n')
        with pytest.raises(ValueError, match='Request-attempt provenance checksum mismatch'):
            rain.validate_dataset(args.output, args.raw_directory, boundary_dir)
