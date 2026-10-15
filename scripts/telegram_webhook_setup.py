"""Bounded Telegram setup and signed local ownership; no notification sender."""
from dataclasses import dataclass, field
from contextlib import contextmanager
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit

from launcher_config import private_file, telegram_environment

WEBHOOK_PATH = '/api/telegram/webhook'
HOST = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com')


class SetupError(Exception):
    """Only fixed, credential-free messages may be raised here."""


@contextmanager
def deadline(seconds):
    """Linux main-thread wall-clock bound, including DNS and slow-drip replies."""
    def expired(_signum, _frame):
        raise TimeoutError()
    previous = signal.signal(signal.SIGALRM, expired)
    timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    beginning = time.monotonic()
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.001, timer[0] - (time.monotonic() - beginning)), timer[1])


@dataclass(frozen=True)
class Configuration:
    username: str
    token: str = field(repr=False)
    secret: str = field(repr=False)
    environment: dict = field(repr=False)


def load_configuration(root, environment):
    try:
        env = telegram_environment(root, environment)
        username, token, secret = (env.get(key, '') for key in
                                  ('TELEGRAM_BOT_USERNAME', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET'))
        if (not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', username)
                or username.casefold() != 'floodpulsebot'
                or not re.fullmatch(r'[0-9]{5,}:[A-Za-z0-9_-]{20,120}', token)
                or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret)
                or not env.get('TELEGRAM_DESTINATIONS')):
            raise ValueError()
        # Reuse the backend's authoritative destination/token validator in a
        # credential-private local process, without changing this process env.
        code = "import sys;sys.path.insert(0,'backend');from app.telegram_delivery import TelegramConfig;TelegramConfig.from_environment()"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=root, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if result.returncode:
            raise ValueError()
        return Configuration(username, token, secret, env)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        raise SetupError('Private Telegram configuration missing/invalid. Use the existing root .env parser, a user-owned regular 0600 file and all four documented keys; values are never displayed.') from None


def tunnel_url(value, webhook=False):
    """Exact lowercase HTTPS Quick Tunnel origin, no credentials/port/query/fragment."""
    if not isinstance(value, str) or len(value) > 200:
        raise SetupError('Invalid or unexpected Cloudflare tunnel URL; nothing registered.')
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise SetupError('Invalid or unexpected Cloudflare tunnel URL; nothing registered.') from None
    if (parsed.scheme != 'https' or not HOST.fullmatch(parsed.netloc)
            or parsed.path != (WEBHOOK_PATH if webhook else '') or parsed.query or parsed.fragment
            or value != 'https://' + parsed.netloc + parsed.path):
        raise SetupError('Invalid or unexpected Cloudflare tunnel URL; nothing registered.')
    return value


def public_environment(environment):
    # Do not pass proxy, bot, database, account or tunnel credentials to helpers.
    return {key: value for key, value in environment.items() if key in ('PATH', 'LANG', 'LC_ALL')}


def resolve_public(host, environment):
    code = "import socket,json,sys;print(json.dumps(sorted({r[4][0] for r in socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))"
    try:
        result = subprocess.run([sys.executable, '-B', '-c', code, host],
                                env=public_environment(environment), capture_output=True, timeout=3)
        if result.returncode or len(result.stdout) > 4096:
            return []
        addresses = json.loads(result.stdout)
        if not isinstance(addresses, list) or not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
            return []
        return sorted(addresses, key=lambda a: ':' in a)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return []


def public_status(origin, path, method, addresses):
    """Verified TLS pinned to a checked public DNS address; no redirects/proxies."""
    import socket
    host = urlsplit(tunnel_url(origin)).hostname
    connection = None
    try:
        with deadline(4):
            connection = http.client.HTTPSConnection(host, timeout=4, context=ssl.create_default_context())
            # Pin this connection, preserving the hostname for SNI and cert validation.
            raw = socket.create_connection((addresses[0], 443), timeout=4)
            try:
                connection.sock = connection._context.wrap_socket(raw, server_hostname=host)
            except BaseException:
                raw.close()
                raise
            connection.request(method, path, body=b'{}' if method == 'POST' else None,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            response.read(4097)
            return response.status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        if connection:
            connection.close()


class TelegramAPI:
    def __init__(self, config):
        self.config = config

    def call(self, method, payload=None):
        if method not in ('getMe', 'getWebhookInfo', 'setWebhook'):
            raise SetupError('Unsupported Telegram setup operation.')
        connection = None
        try:
            with deadline(8):
                connection = http.client.HTTPSConnection('api.telegram.org', timeout=8,
                                                       context=ssl.create_default_context())
                connection.set_debuglevel(0)
                connection.request('POST', '/bot' + self.config.token + '/' + method,
                               body=json.dumps(payload or {}).encode(), headers={'Content-Type': 'application/json'})
                response = connection.getresponse()
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError()
                data = json.loads(raw)
                if response.status != 200 or not isinstance(data, dict) or data.get('ok') is not True:
                    raise ValueError()
                return data['result']
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
            raise SetupError('Telegram setup request failed or returned an unverifiable response. No message was sent; registration may be uncertain. Inspect privately before retrying.') from None
        finally:
            if connection:
                connection.close()


def atomic_private_json(path, value):
    import secrets
    temporary = path.parent / ('.receipt-' + secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def signature(config, value):
    return hmac.new(config.token.encode(), json.dumps(value, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()


def read_ownership(path, config, root, bot):
    try:
        envelope = json.loads(private_file(path, 16384, required_mode=0o600))
    except FileNotFoundError:
        if path.is_symlink():
            raise SetupError('Webhook ownership receipt must not be a symlink; nothing replaced.') from None
        return None
    except (OSError, ValueError):
        raise SetupError('Webhook ownership receipt is unreadable or insecure; existing registration was not replaced.') from None
    try:
        value = envelope['record']
        if (not hmac.compare_digest(envelope['signature'], signature(config, value))
                or value['root'] != str(root) or value['uid'] != os.getuid()
                or value['bot_id'] != bot or value['username'].casefold() != config.username.casefold()):
            raise ValueError()
        tunnel_url(value['url'], webhook=True)
        return value
    except (ValueError, KeyError, TypeError, AttributeError):
        raise SetupError('Webhook ownership receipt is invalid or belongs to another bot/checkout. Existing registration was not replaced.') from None


def register(config, api, origin, receipt, root):
    url = tunnel_url(origin) + WEBHOOK_PATH
    bot = api.call('getMe')
    if (not isinstance(bot, dict) or bot.get('is_bot') is not True
            or type(bot.get('id')) is not int or str(bot['id']) != config.token.split(':')[0]
            or not isinstance(bot.get('username'), str)
            or bot['username'].casefold() != config.username.casefold()):
        raise SetupError('Telegram bot identity does not match the configured username/token; nothing registered.')
    previous = read_ownership(receipt, config, root, bot['id'])
    current = api.call('getWebhookInfo')
    if not isinstance(current, dict) or not isinstance(current.get('url'), str):
        raise SetupError('Telegram webhook state could not be verified; nothing registered.')
    owned = previous.get('url') if previous and previous.get('confirmed') is True else None
    if current['url'] not in ('', url, owned):
        raise SetupError('An unrelated Telegram webhook is registered. It was left unchanged. Explicit operator authorization and a separate migration are required; this launcher has no takeover override.')
    # The previous confirmed record is retained until the new URL is verified.
    # A lost setWebhook response must never manufacture ownership of a new URL.
    if api.call('setWebhook', {'url': url, 'secret_token': config.secret, 'allowed_updates': ['message'],
                              'max_connections': 4, 'drop_pending_updates': False}) is not True:
        raise SetupError('Telegram did not confirm webhook registration; no connected status is claimed.')
    verified = api.call('getWebhookInfo')
    if (not isinstance(verified, dict) or verified.get('url') != url
            or verified.get('allowed_updates') != ['message'] or verified.get('max_connections') != 4):
        raise SetupError('Telegram registration could not be confirmed exactly. No connected status is claimed; inspect privately.')
    from datetime import datetime, timezone
    record = {'root': str(root), 'uid': os.getuid(), 'bot_id': bot['id'], 'username': config.username,
              'url': url, 'confirmed': True, 'verified_at': datetime.now(timezone.utc).isoformat()}
    atomic_private_json(receipt, {'record': record, 'signature': signature(config, record)})
    return url
