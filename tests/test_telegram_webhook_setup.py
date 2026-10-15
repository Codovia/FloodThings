"""Offline setup protocol; ephemeral credentials, no real Telegram or database."""
import io
import json
import os
from pathlib import Path
import secrets
import signal
import ssl
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import telegram_webhook_setup as setup
import full_launcher as full


@pytest.fixture
def config():
    # Random inert values exist only in temporary memory/files, never fixtures in Git.
    return setup.Configuration('FloodPulsebot', str(secrets.randbelow(900000) + 100000) + ':' + secrets.token_urlsafe(32),
                               secrets.token_urlsafe(32), {})


class FakeTelegram:
    def __init__(self, config, url=''):
        self.config, self.url, self.calls = config, url, []
        self.answer, self.confirm = True, True

    def call(self, method, payload=None):
        self.calls.append((method, payload))
        if method == 'getMe':
            return {'id': int(self.config.token.split(':')[0]), 'username': self.config.username, 'is_bot': True}
        if method == 'getWebhookInfo':
            return {'url': self.url, 'allowed_updates': ['message'], 'max_connections': 4}
        assert method == 'setWebhook'  # No sender/deleteWebhook exists in this fake.
        if self.confirm:
            self.url = payload['url']
        return self.answer


@pytest.mark.parametrize('current', ['', 'https://new-session.trycloudflare.com/api/telegram/webhook'])
def test_register_exact_configuration_and_private_signed_receipt(tmp_path, config, current):
    api = FakeTelegram(config, current)
    path = tmp_path / 'ownership.json'
    url = setup.register(config, api, 'https://new-session.trycloudflare.com', path, tmp_path)
    assert url == api.url
    assert [m for m, _ in api.calls] == ['getMe', 'getWebhookInfo', 'setWebhook', 'getWebhookInfo']
    assert api.calls[2][1] == {'url': url, 'secret_token': config.secret, 'allowed_updates': ['message'],
                              'max_connections': 4, 'drop_pending_updates': False}
    assert path.stat().st_mode & 0o777 == 0o600
    assert config.token not in path.read_text() and config.secret not in path.read_text()
    assert setup.read_ownership(path, config, tmp_path, int(config.token.split(':')[0]))['confirmed'] is True


def test_signed_previous_session_can_be_replaced(tmp_path, config):
    api = FakeTelegram(config)
    path = tmp_path / 'ownership.json'
    setup.register(config, api, 'https://old-session.trycloudflare.com', path, tmp_path)
    setup.register(config, api, 'https://new-session.trycloudflare.com', path, tmp_path)
    assert api.url.startswith('https://new-session.')


@pytest.mark.parametrize('current', ['https://other.example/webhook', 'https://unowned.trycloudflare.com/api/telegram/webhook'])
def test_never_take_over_unrelated_registration(tmp_path, config, current):
    api = FakeTelegram(config, current)
    with pytest.raises(setup.SetupError, match='unrelated'):
        setup.register(config, api, 'https://new.trycloudflare.com', tmp_path / 'receipt', tmp_path)
    assert [m for m, _ in api.calls] == ['getMe', 'getWebhookInfo']


@pytest.mark.parametrize('damage', ['tampered', 'permissions', 'different-root', 'token-rotation', 'unconfirmed', 'symlink'])
def test_invalid_receipt_cannot_establish_ownership(tmp_path, config, damage):
    path = tmp_path / 'receipt'
    api = FakeTelegram(config)
    setup.register(config, api, 'https://old.trycloudflare.com', path, tmp_path)
    value = json.loads(path.read_text())
    root, selected = tmp_path, config
    if damage == 'tampered':
        value['record']['url'] = 'https://forged.trycloudflare.com/api/telegram/webhook'
        path.write_text(json.dumps(value))
    elif damage == 'permissions':
        path.chmod(0o644)
    elif damage == 'different-root':
        root = tmp_path / 'other'
    elif damage == 'token-rotation':
        selected = setup.Configuration(config.username, config.token + 'x', config.secret, {})
    elif damage == 'unconfirmed':
        value['record']['confirmed'] = False
        value['signature'] = setup.signature(config, value['record'])
        path.write_text(json.dumps(value))
    else:
        path.unlink(); path.symlink_to(tmp_path / 'missing')
    api.calls.clear()
    with pytest.raises(setup.SetupError):
        setup.register(selected, api, 'https://new.trycloudflare.com', path, root)
    assert not any(m == 'setWebhook' for m, _ in api.calls)


@pytest.mark.parametrize('failure', ['false', 'wrong-url', 'timeout', 'wrong-bot'])
def test_no_confirmation_or_receipt_on_failure(tmp_path, config, failure):
    api = FakeTelegram(config)
    original = api.call
    def call(method, payload=None):
        if failure == 'timeout' and method == 'setWebhook':
            raise setup.SetupError('Uncertain transport')
        value = original(method, payload)
        if failure == 'wrong-bot' and method == 'getMe':
            value['username'] = 'AnotherBot'
        return value
    api.call = call
    api.answer = failure != 'false'
    api.confirm = failure != 'wrong-url'
    with pytest.raises(setup.SetupError):
        setup.register(config, api, 'https://new.trycloudflare.com', tmp_path / 'receipt', tmp_path)
    assert not (tmp_path / 'receipt').exists()
    assert sum(m == 'setWebhook' for m, _ in api.calls) <= 1


@pytest.mark.parametrize('value', ['http://abc.trycloudflare.com', 'https://abc.trycloudflare.com:443',
    'https://user@abc.trycloudflare.com', 'https://abc.trycloudflare.com.evil.example', 'https://a.b.trycloudflare.com',
    'https://abc.trycloudflare.com/', 'https://abc.trycloudflare.com?x=y', 'https://abc.trycloudflare.com#x',
    'https://-abc.trycloudflare.com', 'https://ABC.trycloudflare.com', 'https://127.0.0.1', 'https://[broken',
    '\nhttps://abc.trycloudflare.com', 'https://abc.trycloudflare.com/../api/telegram/webhook'])
def test_tunnel_url_rejects_unsafe_or_nonexact_values(value):
    with pytest.raises(setup.SetupError):
        setup.tunnel_url(value)


def test_tunnel_output_only_accepts_one_owned_exact_origin():
    output = full.TunnelOutput(io.BytesIO(b'{"message":"| https://fresh.trycloudflare.com |"}\n'))
    output.thread.join()
    assert output.origin == 'https://fresh.trycloudflare.com' and not output.error
    for text in [b'Tunnel URL: http://bad.trycloudflare.com\n', b'| https://evil.example |\n',
                 b'| https://first.trycloudflare.com |\n| https://second.trycloudflare.com |\n', b'x' * 8193]:
        output = full.TunnelOutput(io.BytesIO(text)); output.thread.join()
        assert output.error


def test_dns_delay_and_ingress_checks_before_registration(monkeypatch):
    attempts, probes = [], []
    def resolver(host, env):
        attempts.append(host)
        return [] if len(attempts) < 3 else ['1.1.1.1']
    def probe(origin, path, method, addresses):
        probes.append((path, method))
        return 404 if path == '/admin' else 403
    monkeypatch.setattr(full.time, 'sleep', lambda _: None)
    full.wait_public('https://fresh.trycloudflare.com', lambda: None, {}, resolver, probe)
    assert len(attempts) == 3
    assert probes == [('/admin', 'GET'), ('/api/telegram/webhook', 'POST')]


@pytest.mark.parametrize('admin,webhook', [(200, 403), (404, 200), (None, None)])
def test_public_failure_never_passes(monkeypatch, admin, webhook):
    monkeypatch.setattr(full, 'PUBLIC_TIMEOUT', .02)
    monkeypatch.setattr(full.time, 'sleep', lambda _: None)
    with pytest.raises(setup.SetupError, match='No new registration attempted'):
        full.wait_public('https://fresh.trycloudflare.com', lambda: None, {},
                         lambda *_: ['1.1.1.1'], lambda origin, path, *_: admin if path == '/admin' else webhook)


@pytest.mark.parametrize('addresses', [['127.0.0.1'], ['10.0.0.1'], ['::1'], ['1.1.1.1', '192.168.1.1'], []])
def test_dns_rejects_private_or_empty_addresses(monkeypatch, addresses):
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(addresses).encode()))
    assert setup.resolve_public('fresh.trycloudflare.com', {}) == []


def test_telegram_transport_redacts_provider_errors_and_does_not_retry(monkeypatch, config):
    calls = []
    class Broken:
        def __init__(self, *a, **kw):
            calls.append((a, kw))
        def set_debuglevel(self, level):
            assert level == 0
        def request(self, *a, **kw):
            raise OSError(config.token + config.secret)
        def close(self):
            pass
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Broken)
    with pytest.raises(setup.SetupError) as failure:
        setup.TelegramAPI(config).call('getMe')
    assert len(calls) == 1 and calls[0][0] == ('api.telegram.org',)
    assert config.token not in str(failure.value) and config.secret not in str(failure.value)
    with pytest.raises(setup.SetupError):
        setup.TelegramAPI(config).call('sendMessage')


def test_absolute_deadline_and_signal_restoration():
    handler = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with setup.deadline(.02):
            time.sleep(1)
    assert signal.getsignal(signal.SIGALRM) == handler and signal.getitimer(signal.ITIMER_REAL)[0] == 0


@pytest.mark.parametrize('status,raw,valid', [(200, b'{"ok":true,"result":true}', True),
    (302, b'{"ok":true,"result":true}', False), (403, b'{"ok":false}', False),
    (200, b'invalid json', False), (200, b'x' * 65537, False), (200, b'{"ok":true}', False)])
def test_bounded_tls_telegram_protocol_never_redirects(monkeypatch, config, status, raw, valid):
    requests = []
    class Connection:
        def __init__(self, host, *, timeout, context):
            assert host == 'api.telegram.org' and timeout == 8
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        def set_debuglevel(self, value):assert value == 0
        def request(self, method, path, *, body, headers):
            assert method == 'POST' and path == '/bot' + config.token + '/getMe'
            assert json.loads(body) == {} and headers == {'Content-Type': 'application/json'}
            requests.append(True)
        def getresponse(self):return SimpleNamespace(status=status, read=lambda limit: raw[:limit])
        def close(self):pass
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    if valid:
        assert setup.TelegramAPI(config).call('getMe') is True
    else:
        with pytest.raises(setup.SetupError):setup.TelegramAPI(config).call('getMe')
    assert len(requests) == 1


def test_public_https_pins_checked_address_and_keeps_certificate_hostname(monkeypatch):
    import socket
    calls = []
    class Connection:
        def __init__(self, host, *, timeout, context):
            assert host == 'fresh.trycloudflare.com' and context.check_hostname
            self._context = context
        def request(self, method, path, **kwargs):
            calls.append((method, path)); assert 'X-Telegram-Bot-Api-Secret-Token' not in kwargs['headers']
        def getresponse(self):return SimpleNamespace(status=404, read=lambda limit: b'')
        def close(self):pass
    def connect(address, timeout):
        assert address == ('1.1.1.1', 443) and timeout == 4
        return SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(socket, 'create_connection', connect)
    monkeypatch.setattr(ssl.SSLContext, 'wrap_socket', lambda self, raw, *, server_hostname: calls.append(server_hostname))
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    assert setup.public_status('https://fresh.trycloudflare.com', '/admin', 'GET', ['1.1.1.1']) == 404
    assert calls == ['fresh.trycloudflare.com', ('GET', '/admin')]


@pytest.mark.parametrize('problem', ['absent', 'missing-secret', 'permissions', 'malformed', 'destinations', 'username'])
def test_private_configuration_fails_closed_without_values(tmp_path, config, problem):
    env = {'TELEGRAM_BOT_USERNAME': config.username, 'TELEGRAM_BOT_TOKEN': config.token,
           'TELEGRAM_WEBHOOK_SECRET': config.secret,
           'TELEGRAM_DESTINATIONS': json.dumps({'test': {'label': 'Ephemeral test', 'chat_id': str(secrets.randbelow(100000) + 1), 'test_only': True}})}
    if problem == 'absent':
        env = {}
    elif problem == 'missing-secret':
        env.pop('TELEGRAM_WEBHOOK_SECRET')
    elif problem == 'destinations':
        env['TELEGRAM_DESTINATIONS'] = '{}'
    elif problem == 'username':
        env['TELEGRAM_BOT_USERNAME'] = 'DifferentBot'
    path = tmp_path / '.env'
    path.write_text('\n'.join(k + '=' + json.dumps(v) for k, v in env.items()) if problem != 'malformed' else 'not an assignment')
    path.chmod(0o644 if problem == 'permissions' else 0o600)
    (tmp_path / 'backend').symlink_to(ROOT / 'backend', target_is_directory=True)
    with pytest.raises(setup.SetupError) as error:
        setup.load_configuration(tmp_path, {})
    assert config.token not in str(error.value) and config.secret not in str(error.value)


def test_existing_parser_precedence_and_backend_validator(tmp_path, config):
    env = {'TELEGRAM_BOT_USERNAME': config.username, 'TELEGRAM_BOT_TOKEN': config.token,
           'TELEGRAM_WEBHOOK_SECRET': config.secret,
           'TELEGRAM_DESTINATIONS': json.dumps({'test': {'label': 'Ephemeral test', 'chat_id': str(secrets.randbelow(100000) + 1), 'test_only': True}})}
    path = tmp_path / '.env'
    path.write_text('\n'.join(k + '=' + json.dumps(v) for k, v in env.items())); path.chmod(0o600)
    (tmp_path / 'backend').symlink_to(ROOT / 'backend', target_is_directory=True)
    before = path.read_bytes()
    loaded = setup.load_configuration(tmp_path, {})
    assert loaded.token == config.token and config.token not in repr(loaded)
    with pytest.raises(setup.SetupError):
        setup.load_configuration(tmp_path, {'TELEGRAM_BOT_TOKEN': ''})
    assert before == path.read_bytes()
    assert setup.public_environment({**env, 'DATABASE_URL': 'private', 'PATH': '/bin', 'HTTPS_PROXY': 'private'}) == {'PATH': '/bin'}
