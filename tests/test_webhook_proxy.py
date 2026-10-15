"""Real loopback HTTP ingress against an isolated fake backend; no live services."""
from contextlib import contextmanager
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import telegram_webhook_proxy as proxy


@contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.fixture
def ingress():
    secret, requests = secrets.token_urlsafe(32), []
    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            requests.append((self.path, dict(self.headers), body))
            accepted = hmac.compare_digest(self.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), secret)
            self.send_response(200 if accepted else 403)
            self.end_headers(); self.wfile.write(b'{"ok":true}' if accepted else b'{}')
    with serving(ThreadingHTTPServer(('127.0.0.1', 0), Backend)) as backend:
        with serving(proxy.Server(0, backend)) as port:
            yield port, secret, requests


def request(port, method='POST', path=proxy.PATH, body=b'{}', headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request(method, path, body=body, headers={'Content-Type': 'application/json', **(headers or {})})
        reply = connection.getresponse()
        return reply.status, reply.read(), dict(reply.headers)
    finally:
        connection.close()


@pytest.mark.parametrize('method,path', [('GET', '/admin'), ('POST', '/admin'), ('GET', '/api/health'),
    ('GET', proxy.PATH), ('HEAD', '/admin'), ('PUT', proxy.PATH), ('OPTIONS', proxy.PATH),
    ('POST', proxy.PATH + '?query=1'), ('POST', '//api/telegram/webhook'), ('POST', '/api/telegram/webhook/')])
def test_every_other_route_is_closed(ingress, method, path):
    port, secret, received = ingress
    assert request(port, method, path, headers={'X-Telegram-Bot-Api-Secret-Token': secret})[0] == 404
    assert received == []


def test_backend_secret_check_and_allowlisted_forwarding(ingress, capsys):
    port, secret, received = ingress
    assert request(port)[0] == 403
    assert received == []
    assert request(port, headers={'X-Telegram-Bot-Api-Secret-Token': secrets.token_urlsafe(32)})[0] == 403
    status, body, headers = request(port, headers={'X-Telegram-Bot-Api-Secret-Token': secret,
        'Cookie': 'private-cookie', 'Authorization': 'private-header', 'X-Forwarded-Host': 'untrusted.example'})
    assert status == 200 and body == b'{"ok":true}' and headers['Cache-Control'] == 'no-store'
    assert received[-1][0] == proxy.PATH and received[-1][2] == b'{}'
    assert 'Cookie' not in received[-1][1] and 'Authorization' not in received[-1][1] and 'X-Forwarded-Host' not in received[-1][1]
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('headers,body,expected', [({'Transfer-Encoding': 'chunked'}, b'{}', 400),
    ({'Expect': '100-continue'}, b'{}', 400), ({'Content-Type': 'text/plain'}, b'{}', 415),
    ({'Content-Length': '0'}, b'', 413), ({'Content-Length': '65537'}, b'{}', 413),
    ({'Content-Length': '-1'}, b'{}', 411), ({'X-Telegram-Bot-Api-Secret-Token': 'bad'}, b'{}', 403)])
def test_input_validation_without_forwarding(ingress, headers, body, expected):
    port, secret, received = ingress
    assert request(port, body=body, headers={'X-Telegram-Bot-Api-Secret-Token': secret, **headers})[0] == expected
    assert not received


def test_duplicate_content_length_is_rejected(ingress):
    port, secret, received = ingress
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        raw = ('POST ' + proxy.PATH + ' HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\nContent-Length: 2\r\n'
               'Content-Type: application/json\r\nX-Telegram-Bot-Api-Secret-Token: ' + secret + '\r\n\r\n{}').encode()
        connection.sendall(raw)
        assert b' 411 ' in connection.recv(4096)
    assert not received


def test_failed_upstream_is_unavailable():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0)); unused = reservation.getsockname()[1]
    with serving(proxy.Server(0, unused)) as port:
        assert request(port, headers={'X-Telegram-Bot-Api-Secret-Token': secrets.token_urlsafe(32)})[0] == 502


def test_absolute_deadline_closes_slow_headers(monkeypatch):
    monkeypatch.setattr(proxy, 'REQUEST_TIMEOUT', .15)
    with serving(proxy.Server(0)) as port:
        with socket.create_connection(('127.0.0.1', port), timeout=1) as connection:
            connection.sendall(b'POST /api/telegram/webhook HTTP/1.1\r\nHost:')
            beginning = time.monotonic()
            answer = connection.recv(4096)
            assert time.monotonic() - beginning < .7
            assert not answer or b' 411 ' in answer


def test_concurrency_is_bounded(monkeypatch):
    monkeypatch.setattr(proxy, 'REQUEST_TIMEOUT', 1)
    with serving(proxy.Server(0)) as port:
        connections = []
        try:
            for _ in range(8):
                connection = socket.create_connection(('127.0.0.1', port), timeout=1)
                connection.sendall(b'GET /admin HTTP/1.1\r\nHost:'); connections.append(connection)
            time.sleep(.05)
            with socket.create_connection(('127.0.0.1', port), timeout=1) as overflow:
                assert overflow.recv(1) == b''
        finally:
            for connection in connections:
                connection.close()


def test_absolute_deadline_stops_slow_http10_upstream_and_releases_slot(monkeypatch):
    monkeypatch.setattr(proxy, 'REQUEST_TIMEOUT', .12)
    finished = threading.Event()
    class Slow(BaseHTTPRequestHandler):
        def log_message(self, *_):pass
        def do_POST(self):
            self.send_response(200); self.end_headers()
            try:
                for _ in range(100):
                    self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.01)
            except OSError:
                pass
            finally:
                finished.set()
    with serving(ThreadingHTTPServer(('127.0.0.1', 0), Slow)) as backend:
        with proxy.Server(0, backend) as server:
            with serving(server) as port:
                beginning = time.monotonic()
                try:
                    request(port, headers={'X-Telegram-Bot-Api-Secret-Token': secrets.token_urlsafe(32)})
                except http.client.RemoteDisconnected:
                    pass
                assert time.monotonic() - beginning < .7
                assert finished.wait(.5)
                assert server.slots.acquire(timeout=.5)
                server.slots.release()


def test_oversized_upstream_reply_is_rejected():
    class Large(BaseHTTPRequestHandler):
        def log_message(self, *_):pass
        def do_POST(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'x' * (proxy.MAX_BODY + 1))
    with serving(ThreadingHTTPServer(('127.0.0.1', 0), Large)) as backend:
        with serving(proxy.Server(0, backend)) as port:
            assert request(port, headers={'X-Telegram-Bot-Api-Secret-Token': secrets.token_urlsafe(32)})[0] == 502
