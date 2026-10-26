"""Full-system supervisor (app + Telegram tunnel); the app launcher keeps its lifecycle/DB guards. Run via ./floodpulse.sh."""
import argparse
import ctypes
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import threading
import time

from launcher_config import APP_LAUNCHER, private_file
from launcher_processes import (identity, same_process, signal_process, ensure_ports_available, LaunchError, reap,
                                lan_address, LAN_CERTIFICATE, LAN_MISSING)
from telegram_webhook_setup import (SetupError, atomic_private_json, load_configuration, register,
                                    tunnel_url, resolve_public, public_status, public_environment, TelegramAPI)
from telegram_webhook_setup import deadline

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'FLOODPULSE_FULL_LAUNCH_ID'
START_TIMEOUT = 120
TUNNEL_TIMEOUT = 45
PUBLIC_TIMEOUT = 60
GRACE = 12
TERM_GRACE = 5
PORTS = {'backend': 18050, 'frontend': 14180}


class Stopping(Exception):
    def __init__(self, signum):
        self.signum = signum


def runtime(root, create=False):
    current = root
    for part in ('data', 'tmp', 'full_launcher'):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                return current
            current.mkdir(mode=0o700)
            info = current.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022
                or part == 'full_launcher' and stat.S_IMODE(info.st_mode) != 0o700):
            raise SetupError('Full-launcher runtime must be user-owned, non-symlink directories; full_launcher requires 0700. No service changed.')
    return current


def owned(state):
    rows, found = {}, {}
    marker = (MARKER + '=' + state['run_id']).encode()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        row = identity(int(proc.name))
        if not row or row['uid'] != os.getuid() or row['start'] < state['launcher']['start']:
            continue
        rows[row['pid']] = row
        try:
            if marker in (proc / 'environ').read_bytes().split(b'\0'):
                found[row['pid']] = row
        except OSError:
            pass
    if state['launcher']['pid'] == os.getpid() and same_process(state['launcher']):
        found.update({pid: row for pid, row in rows.items() if row['ppid'] == os.getpid()})
    while True:
        descendants = {pid: row for pid, row in rows.items() if row['ppid'] in found}
        if descendants.keys() <= found.keys():
            return list(found.values())
        found.update(descendants)


def stop_owned(state, receipt):
    # Give the app launcher its normal shutdown grace before touching any surviving workers.
    rows = {row['pid']: row for row in owned(state)}
    for child in state.get('leaders', []):
        if child['pid'] in rows and rows[child['pid']]['start'] == child['start']:
            signal_process(child, signal.SIGTERM)
    beginning = time.monotonic()
    signalled, empty = set(), 0
    while True:
        reap()
        rows = owned(state)
        if not rows:
            empty += 1
            if empty == 3:
                break
        else:
            empty = 0
        elapsed = time.monotonic() - beginning
        if elapsed >= GRACE:
            for row in rows:
                key = (row['pid'], row['start'])
                if elapsed >= GRACE + TERM_GRACE or key not in signalled:
                    signal_process(row, signal.SIGKILL if elapsed >= GRACE + TERM_GRACE else signal.SIGTERM)
                    signalled.add(key)
        if elapsed > GRACE + TERM_GRACE + 3:
            raise SetupError('Verified full-launcher children did not stop; ownership receipt retained. No unrelated process was signalled.')
        time.sleep(.05)
    deadline = time.monotonic() + 3
    while True:
        try:
            ensure_ports_available(state['ports'])
            break
        except LaunchError:
            if time.monotonic() >= deadline:
                raise SetupError('A configured port is still occupied after owned shutdown; no unrelated listener was stopped.') from None
            time.sleep(.1)
    receipt.unlink(missing_ok=True)


def recover(root, folder):
    path = folder / 'processes.json'
    try:
        state = json.loads(private_file(path, 16384, required_mode=0o600))
    except FileNotFoundError:
        return
    try:
        if (state['root'] != str(root) or state['uid'] != os.getuid()
                or not re.fullmatch(r'[a-f0-9]{64}', state['run_id'])
                or state['ports'] not in (PORTS, {**PORTS, 'webhook proxy': 18060})
                or type(state['launcher']['pid']) is not int or state['launcher']['pid'] <= 1
                or type(state['launcher']['start']) is not int or state['launcher']['start'] <= 0
                or not isinstance(state['leaders'], list)):
            raise ValueError()
        for row in state['leaders']:
            if (type(row['pid']) is not int or row['pid'] <= 1 or type(row['start']) is not int
                    or row['start'] <= 0 or row['uid'] != os.getuid()):
                raise ValueError()
        if state['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
            path.unlink()
            return
        if same_process(state['launcher']):
            raise SetupError('The recorded full launcher is still active; stop its owning terminal before restart.')
    except (KeyError, TypeError, ValueError):
        raise SetupError('Invalid private full-launcher process receipt; no process stopped.') from None
    stop_owned(state, path)


def listener_owned(port, state):
    inodes = set()
    for family in ('tcp', 'tcp6'):
        for line in Path('/proc/net', family).read_text().splitlines()[1:]:
            row = line.split()
            if row[3] == '0A' and int(row[1].split(':')[1], 16) == port:
                inodes.add('socket:[' + row[9] + ']')
    for row in owned(state):
        try:
            if any(os.readlink(fd) in inodes for fd in (Path('/proc') / str(row['pid']) / 'fd').iterdir()):
                return True
        except OSError:
            pass
    return False


def local_status(port, path, method='GET', ca=None):
    connection = None
    try:
        # --lan serves the website over HTTPS with the local certificate (its names include 127.0.0.1).
        connection = (http.client.HTTPSConnection('127.0.0.1', port, timeout=2, context=ssl.create_default_context(cafile=ca))
                      if ca else http.client.HTTPConnection('127.0.0.1', port, timeout=2))
        with deadline(2):
            connection.request(method, path, body=b'{}' if method == 'POST' else None,
                           headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            body = response.read(65537)
            return response.status, body if len(body) <= 65536 else b''
    except (OSError, http.client.HTTPException):
        return None, b''
    finally:
        if connection:
            connection.close()


class TunnelOutput:
    """Consume only the owned process pipe; discard logs instead of persisting them."""
    def __init__(self, stream):
        self.origin = None
        self.error = False
        self.thread = threading.Thread(target=self.consume, args=(stream,), daemon=True)
        self.thread.start()

    def consume(self, stream):
        try:
            while True:
                raw = stream.readline(8193)
                if not raw:
                    return
                if len(raw) > 8192:
                    self.error = True
                    return
                line = raw.decode('utf-8', errors='replace')
                try:
                    value = json.loads(line)
                    line = value.get('message', '') if isinstance(value, dict) else ''
                except ValueError:
                    pass
                if not isinstance(line, str):
                    continue
                urls = re.findall(r'https?://[^\s|<>"\\]+', line)
                for url in urls:
                    if 'trycloudflare.com' in url or line.strip().startswith(('|', 'Tunnel URL:')):
                        candidate = tunnel_url(url)
                        if self.origin and self.origin != candidate:
                            raise SetupError('Tunnel changed unexpectedly.')
                        self.origin = candidate
        except (OSError, SetupError):
            self.error = True


def wait_public(origin, pulse, environment, resolver=resolve_public, probe=public_status):
    deadline = time.monotonic() + PUBLIC_TIMEOUT
    while time.monotonic() < deadline:
        pulse()
        addresses = resolver(origin.split('/')[2], environment)
        if addresses and probe(origin, '/admin', 'GET', addresses) == 404:
            if probe(origin, '/api/telegram/webhook', 'POST', addresses) == 403:
                pulse()
                return
        pulse()
        time.sleep(.5)
    raise SetupError('Public DNS/HTTPS readiness timed out or ingress checks failed. Required: /admin 404 and unauthorized webhook POST 403. No new registration attempted; any existing registration is preserved.')


def application_environment(environment):
    return {key: value for key, value in environment.items() if key != 'LOCATION_DIRECTORY_ADMIN_URL'}


def fixed_environment(environment):
    for key, expected in [('FLOODPULSE_BACKEND_PORT', '18050'), ('FLOODPULSE_FRONTEND_PORT', '14180'),
                          ('SHELTER_PUBLIC_ORIGIN', 'http://127.0.0.1:14180'),
                          ('SHELTER_DIRECTORY_MODE', 'live'), ('LOCATION_DIRECTORY_BACKEND', 'postgres')]:
        if environment.get(key, expected) != expected:
            raise SetupError('Full launcher requires the documented live database environment and fixed loopback ports 18050/14180. Use the separate manual two-server procedure for DEMO ONLY.')


def supervise(root, environment, telegram, cloudflared=None):
    folder = runtime(root, create=True)
    lock_path = folder / 'lock'
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise SetupError('Full-launcher lock must be a user-owned regular 0600 file.')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SetupError('A full-system launcher is already running for this checkout.') from None
        return locked_run(root, folder, environment, telegram, cloudflared)
    finally:
        os.close(fd)


def locked_run(root, folder, environment, telegram, cloudflared):
    recover(root, folder)
    ports = {**PORTS, **({'webhook proxy': 18060} if telegram else {})}
    ensure_ports_available(ports)
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise SetupError('Linux child ownership tracking unavailable; nothing started.')
    state = {'root': str(root), 'uid': os.getuid(), 'run_id': secrets.token_hex(32),
             'launcher': identity(os.getpid()), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'ports': ports, 'leaders': []}
    receipt = folder / 'processes.json'
    children, output = [], None
    result = 1
    lan = lan_address() if environment.get('FLOODPULSE_LAN') == '1' else None
    ca = str(root / 'data/tmp/launcher/tls/ca.crt') if lan else None
    site = f'https://{lan}:14180' if lan else 'http://127.0.0.1:14180'
    def stopping(signum, frame):
        raise Stopping(signum)
    old_handlers = {sig: signal.signal(sig, stopping) for sig in (signal.SIGINT, signal.SIGTERM)}
    def start(command, env, pipe=False):
        child = subprocess.Popen(command, cwd=root, env={**env, MARKER: state['run_id']},
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if pipe else subprocess.DEVNULL,
                                 stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        children.append(child)
        row = identity(child.pid)
        if not row:
            raise SetupError('A required service exited during startup; no readiness claimed.')
        state['leaders'].append(row)
        atomic_private_json(receipt, state)
        return child
    def pulse():
        if any(child.poll() is not None for child in children) or output and output.error:
            raise SetupError('An owned service or Cloudflare tunnel failed. Telegram is not connected; owned services will stop. Inspect prerequisites without publishing credentials.')
    def wait_local():
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            pulse()
            health, _ = local_status(18050, '/api/health')
            front, _ = local_status(14180, '/', ca=ca)
            mode_status, body = local_status(18050, '/api/environment')
            try:
                live = mode_status == 200 and json.loads(body).get('mode') == 'live'
            except (ValueError, AttributeError):
                live = False
            if health == front == 200 and live and all(listener_owned(port, state) for port in PORTS.values()):
                return
            time.sleep(.2)
        raise SetupError('Application readiness timed out. Run ./floodpulse.sh --check separately; no database recreated or migrated.')
    try:
        atomic_private_json(receipt, state)
        print('Starting existing FloodPulse launcher on 18050/14180…', flush=True)
        app_env = application_environment(telegram.environment if telegram else environment)
        start([str(root / APP_LAUNCHER)], app_env)
        wait_local()
        if telegram:
            status, body = local_status(18050, '/api/alerts/subscription')
            try:
                config = json.loads(body)
                if status != 200 or config.get('status') != 'available' or config.get('url') != 'https://t.me/' + telegram.username + '?start=floodpulse':
                    raise ValueError()
            except (ValueError, AttributeError):
                raise SetupError('Running backend Telegram configuration is not ready/matching; nothing registered.') from None
            # Verify backend secret enforcement independently, with no valid secret/update.
            if local_status(18050, '/api/telegram/webhook', 'POST')[0] != 403:
                raise SetupError('Backend did not reject an unauthorized webhook with 403; nothing exposed.')
            start([str(root / 'backend/.venv/bin/python'), '-B', str(root / 'scripts/telegram_webhook_proxy.py')], public_environment(environment))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                pulse()
                if (local_status(18060, '/admin')[0] == 404
                        and local_status(18060, '/api/telegram/webhook', 'POST')[0] == 403
                        and listener_owned(18060, state)):
                    break
                time.sleep(.1)
            else:
                raise SetupError('Restricted webhook proxy readiness failed; nothing registered.')
            home = folder / 'cloudflared-home'
            if not home.exists():
                home.mkdir(mode=0o700)
            info = home.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise SetupError('Cloudflare private empty-home directory is invalid; nothing registered.')
            if any(home.iterdir()):
                raise SetupError('Cloudflare launcher home must remain empty; existing tunnel configuration will not be loaded.')
            clean = {**public_environment(environment), 'HOME': str(home), 'XDG_CONFIG_HOME': str(home)}
            # /dev/null decodes as an empty config and prevents discovery of
            # unrelated system/user ingress rules or named-tunnel credentials.
            tunnel = start([cloudflared, '--no-autoupdate', 'tunnel', '--config', '/dev/null', '--url', 'http://127.0.0.1:18060',
                            '--logformat', 'json', '--loglevel', 'info', '--metrics', '127.0.0.1:0'], clean, pipe=True)
            output = TunnelOutput(tunnel.stdout)
            deadline = time.monotonic() + TUNNEL_TIMEOUT
            while not output.origin and time.monotonic() < deadline:
                pulse()
                time.sleep(.1)
            pulse()
            if not output.origin:
                raise SetupError('Cloudflare did not assign a valid HTTPS Quick Tunnel before timeout; nothing registered.')
            print('Checking public DNS, HTTPS and restricted ingress…', flush=True)
            wait_public(output.origin, pulse, environment)
            pulse()
            register(telegram, TelegramAPI(telegram), output.origin, folder / 'webhook.json', root)
            pulse()
        print(f'\nApplication: {site}' + ('  (this laptop and every device on the same Wi-Fi)' if lan else '')
              + f'\nAdmin:       {site}/admin', flush=True)
        if lan:
            print(LAN_CERTIFICATE.format(origin=site), flush=True)
        print('Backend/frontend: verified; database managed only by the app launcher.', flush=True)
        if telegram:
            print('Public webhook hostname: ' + output.origin.split('/')[2] + '\nBot: @' + telegram.username
                  + '\nProxy/DNS/HTTPS ingress: verified. Telegram webhook registration: verified. No alert sent.', flush=True)
        print('Press Ctrl+C to stop owned services. PostgreSQL and webhook registration remain unchanged on shutdown.', flush=True)
        next_probe = time.monotonic() + 30
        while True:
            pulse()
            if telegram and time.monotonic() >= next_probe:
                wait_public(output.origin, pulse, environment)
                next_probe = time.monotonic() + 30
            time.sleep(.2)
    except Stopping as stopped:
        result = 128 + stopped.signum
        print('Stopping owned services; PostgreSQL preserved. Stopped Quick Tunnel is offline; webhook is not unregistered.', flush=True)
    except (SetupError, LaunchError) as error:
        print('FloodPulse: ' + str(error), file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print('FloodPulse: full-system startup failed; no secret-bearing error details displayed.', file=sys.stderr)
    finally:
        for sig in old_handlers:
            signal.signal(sig, signal.SIG_IGN)
        try:
            stop_owned(state, receipt)
            for child in children:
                child.wait()
            if output:
                output.thread.join(timeout=1)
                tunnel.stdout.close()
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SetupError('Invalid arguments. Use ./floodpulse.sh --help; argument values are not displayed.')


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only readiness; no service start or Telegram API request')
    parser.add_argument('--telegram', action='store_true', help='Authorize owned Quick Tunnel webhook setup, never notifications')
    try:
        args = parser.parse_args()
        fixed_environment(os.environ)
        if os.environ.get('FLOODPULSE_LAN') == '1' and not args.check and not lan_address():
            raise SetupError(LAN_MISSING)
        config = load_configuration(ROOT, os.environ) if args.telegram else None
        binary = shutil.which('cloudflared') if args.telegram else None
        if args.telegram and not binary:
            raise SetupError('cloudflared is missing. Install it separately; this launcher downloads nothing.')
        if args.check:
            # No new runtime files, recovery, public probes or Telegram calls.
            folder = ROOT / 'data/tmp/full_launcher'
            if folder.exists():
                runtime(ROOT)
            lock = folder / 'lock'
            if lock.exists() or lock.is_symlink():
                private_file(lock, 4096, required_mode=0o600)
                fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise SetupError('A full-system launcher is already running.') from None
                finally:
                    os.close(fd)
            ensure_ports_available({**PORTS, **({'webhook proxy': 18060} if args.telegram else {})})
            environment = application_environment(config.environment if config else os.environ)
            check = subprocess.run([str(ROOT / APP_LAUNCHER), '--check'], cwd=ROOT, env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=150)
            if check.returncode:
                raise SetupError('./floodpulse.sh --check did not pass. Run that read-only command for safe dependency/database diagnostics; no service was started.')
            print('Checks passed. No service started, account created, webhook changed or Telegram request made. Bot/network ownership is checked only on an explicit --telegram start.')
            return 0
        return supervise(ROOT, os.environ, config, binary)
    except (SetupError, LaunchError) as error:
        print('FloodPulse: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print('FloodPulse: private configuration/runtime check failed; values are not displayed.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
