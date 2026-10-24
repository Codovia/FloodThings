"""Loopback webhook-only ingress. No credentials, request logs or arbitrary proxying."""
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import socket
import threading

PATH = '/api/telegram/webhook'
MAX_BODY = 65536
REQUEST_TIMEOUT = 30


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 closes every connection; no pipelining, upgrades or keep-alive.
    server_version = 'FloodPulseWebhook'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.upstream_socket = None
        self.expired = threading.Event()
        self.timer = threading.Timer(REQUEST_TIMEOUT, self.expire)
        self.timer.daemon = True
        self.timer.start()

    def expire(self):
        # Absolute bound also covers slow headers/body and slow upstream replies.
        self.expired.set()
        sockets = [self.connection, self.upstream_socket]
        for connection in sockets:
            if connection:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def finish(self):
        self.timer.cancel()
        super().finish()

    def log_message(self, *_args):
        pass

    def parse_request(self):
        if not super().parse_request():
            return False
        # BaseHTTPRequestHandler normalizes leading //; this ingress requires
        # the exact request target instead of accepting equivalent-looking paths.
        self.path = self.requestline.split()[1]
        return True

    def respond(self, status, body=b''):
        self.close_connection = True
        try:
            self.send_response(status)
            for key, value in [('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
                               ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                               ('Connection', 'close')]:
                self.send_header(key, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except OSError:
            pass

    def do_POST(self):
        if self.path != PATH:
            return self.respond(404)
        if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Expect'):
            return self.respond(400)
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,8}', lengths[0]):
            return self.respond(411)
        length = int(lengths[0])
        if not 1 <= length <= MAX_BODY:
            return self.respond(413)
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self.respond(415)
        headers = self.headers.get_all('X-Telegram-Bot-Api-Secret-Token', [])
        if len(headers) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', headers[0]):
            return self.respond(403)
        connection = None
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                return self.respond(400)
            connection = HTTPConnection('127.0.0.1', self.server.backend_port, timeout=12)
            connection.request('POST', PATH, body=body,
                               headers={'Content-Type': 'application/json',
                                        'X-Telegram-Bot-Api-Secret-Token': headers[0]})
            # HTTP/1.0 getresponse() can detach connection.sock while its file
            # is still reading. Retain the original socket for deadline shutdown.
            self.upstream_socket = connection.sock
            if self.expired.is_set():
                self.expire()
                return
            response = connection.getresponse()
            answer = response.read(MAX_BODY + 1)
            return self.respond(502) if len(answer) > MAX_BODY else self.respond(response.status, answer)
        except (OSError, HTTPException):
            self.respond(502)
        finally:
            if connection:
                connection.close()

    def denied(self):
        self.respond(404)

    do_GET = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = denied


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8

    def __init__(self, port=18060, backend_port=18050):
        self.backend_port = backend_port
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', port), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass  # Never emit request bodies, headers or exceptions.


if __name__ == '__main__':
    try:
        with Server() as server:
            server.serve_forever(poll_interval=.2)
    except (OSError, KeyboardInterrupt):
        raise SystemExit(1)
