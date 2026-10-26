"""Linux launcher ownership, safe port diagnostics and bounded child shutdown.

No argv/environment dumps. A private per-run receipt plus an inherited nonce proves
ownership; pidfds prevent signalling a recycled PID. Unknown listeners are untouched.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time

from launcher_config import private_file

STARTUP_TIMEOUT = 30
TERM_TIMEOUT = 5
KILL_TIMEOUT = 3
MARKER = 'FLOODPULSE_LAUNCH_ID'
SECRET_KEYS = {'DATABASE_URL', 'SHELTER_DATABASE_URL', 'LOCATION_DIRECTORY_ADMIN_URL', 'OPENROUTESERVICE_API_KEY', 'GOOGLE_MAPS_EMBED_API_KEY', 'MAPTILER_PUBLIC_KEY'}


class LaunchError(Exception):
    pass


class StopRequested(Exception):
    def __init__(self, signum):
        self.signum = signum


def identity(pid):
    """Read only kernel identity fields; process names may contain arbitrary text."""
    try:
        path = Path('/proc') / str(pid)
        row = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        if row[0] == 'Z':
            return None
        return {'pid': int(pid), 'start': int(row[19]), 'ppid': int(row[1]),
                'uid': path.stat().st_uid}
    except (OSError, ValueError, IndexError):
        return None


def same_process(expected):
    current = identity(expected['pid'])
    return current is not None and current['start'] == expected['start'] and current['uid'] == os.getuid()


def port_owners(port):
    """Best-effort LISTEN inode lookup; never print arbitrary names or command lines."""
    inodes = set()
    for name in ('tcp', 'tcp6'):
        try:
            for line in Path('/proc/net', name).read_text().splitlines()[1:]:
                row = line.split()
                if row[3] == '0A' and int(row[1].split(':')[1], 16) == port:
                    inodes.add('socket:[' + row[9] + ']')
        except (OSError, ValueError, IndexError):
            continue
    owners = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if not any(os.readlink(fd) in inodes for fd in (proc / 'fd').iterdir()):
                continue
            executable = Path(os.readlink(proc / 'exe')).name
            if not re.fullmatch(r'python(?:3(?:\.\d+)?)?|node|npm|bash|sh', executable):
                executable = 'other executable'
            owners.append(f'PID {int(proc.name)} ({executable}, UID {proc.stat().st_uid})')
        except OSError:
            continue
    return ', '.join(owners) or 'listener owner unavailable'


def ensure_ports_available(ports):
    conflicts = []
    for label, port in ports.items():
        with socket.socket() as probe:
            # Match the servers: TIME_WAIT is not a live listener or an orphan.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as error:
                if error.errno == errno.EADDRINUSE:
                    conflicts.append(f'{label} port {port} (127.0.0.1) is occupied: {port_owners(port)}.')
                else:
                    raise LaunchError(f'Cannot bind {label} port {port}; check local socket permissions.') from None
    if conflicts:
        raise LaunchError(' '.join(conflicts) + ' No unrelated process was stopped; ports were not changed.')


def receipt_path(root):
    return root / 'data/tmp/launcher/processes.json'


def save_receipt(root, state):
    path = receipt_path(root)
    temporary = path.with_suffix('.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(state, stream)
    temporary.replace(path)


def owned_processes(state):
    rows, owned = {}, {}
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
                owned[row['pid']] = row
        except OSError:
            pass
    # Current-run ancestry also covers children which remove their environment or
    # start a new session. The subreaper adopts them if npm/their parent exits.
    if state['launcher']['pid'] == os.getpid() and same_process(state['launcher']):
        owned.update({pid: row for pid, row in rows.items() if row['ppid'] == os.getpid()})
    while True:
        descendants = {pid: row for pid, row in rows.items() if row['ppid'] in owned}
        if descendants.keys() <= owned.keys():
            return list(owned.values())
        owned.update(descendants)


def signal_process(row, signum):
    try:
        fd = os.pidfd_open(row['pid'])
        try:
            if same_process(row):
                signal.pidfd_send_signal(fd, signum)
        finally:
            os.close(fd)
    except ProcessLookupError:
        pass


def reap():
    while True:
        try:
            if os.waitpid(-1, os.WNOHANG)[0] == 0:
                return
        except ChildProcessError:
            return


def stop_owned(root, state):
    deadline = time.monotonic() + TERM_TIMEOUT + KILL_TIMEOUT
    escalate = time.monotonic() + TERM_TIMEOUT
    terminated = set()
    empty_scans = 0
    while True:
        reap()
        rows = owned_processes(state)
        if not rows:
            empty_scans += 1
            if empty_scans >= 3:
                break
            time.sleep(0.05)
            continue
        empty_scans = 0
        hard = time.monotonic() >= escalate
        for row in rows:
            key = (row['pid'], row['start'])
            if hard or key not in terminated:
                signal_process(row, signal.SIGKILL if hard else signal.SIGTERM)
                terminated.add(key)
        if time.monotonic() >= deadline:
            raise LaunchError('Owned launcher processes did not terminate; private ownership receipt retained.')
        time.sleep(0.05)
    # Hold the launcher lock until shutdown is complete, including socket release.
    deadline = time.monotonic() + 2
    while True:
        try:
            ensure_ports_available(state['ports'])
            break
        except LaunchError:
            if time.monotonic() >= deadline:
                receipt_path(root).unlink(missing_ok=True)
                raise
            time.sleep(0.05)
    receipt_path(root).unlink(missing_ok=True)


def load_receipt(root):
    """The private ownership receipt of this checkout's launcher, validated; None if absent."""
    try:
        state = json.loads(private_file(receipt_path(root), 16384, required_mode=0o600))
    except FileNotFoundError:
        return None
    try:
        valid = (state['root'] == str(root) and state['uid'] == os.getuid()
                 and isinstance(state['run_id'], str) and re.fullmatch(r'[a-f0-9]{64}', state['run_id'])
                 and set(state['ports']) == {'backend', 'frontend'}
                 and all(type(port) is int and 1024 <= port <= 65535 for port in state['ports'].values())
                 and type(state['launcher']['pid']) is int and state['launcher']['pid'] > 1
                 and type(state['launcher']['start']) is int and state['launcher']['start'] > 0)
        if not valid:
            raise LaunchError('Invalid private launcher ownership receipt; no process was stopped.')
        state['current_boot'] = state['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return state
    except (KeyError, TypeError):
        raise LaunchError('Invalid private launcher ownership receipt; no process was stopped.') from None


def stop_running(root, wait=45):
    """Stop this checkout's running launcher the way Ctrl+C in its terminal would.

    Only the launcher recorded in the private receipt is signalled, and only if its process id, start time
    and user still match; the launcher then shuts down its own backend and frontend. Returns True if one was stopped.
    """
    state = load_receipt(root)
    if not state or not state['current_boot'] or not same_process(state['launcher']):
        return False
    os.kill(state['launcher']['pid'], signal.SIGINT)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if not same_process(state['launcher']):
            return True
        time.sleep(0.5)
    raise LaunchError('The running FloodPulse did not stop within 45 seconds; stop it with Ctrl+C in its own terminal.')


def recover(root):
    state = load_receipt(root)
    if state is None:
        return
    try:
        if not state['current_boot']:
            receipt_path(root).unlink()
            return  # A previous boot cannot establish current process ownership.
        if same_process(state['launcher']):
            raise LaunchError('Recorded launcher is still active; stop it normally before restarting.')
    except (KeyError, TypeError):
        raise LaunchError('Invalid private launcher ownership receipt; no process was stopped.') from None
    if owned_processes(state):
        print('Cleaning up verified children of a previous launcher; unrelated processes untouched.', flush=True)
    stop_owned(root, state)


def service_environment(frontend=False):
    return {key: value for key, value in os.environ.items()
            if key != 'LOCATION_DIRECTORY_ADMIN_URL'
            and (not frontend or key not in SECRET_KEYS and not key.startswith('TELEGRAM_'))}


def run(root):
    # Reap orphaned grandchildren, including workers which create another session.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise LaunchError('Linux child ownership tracking unavailable; no services started.')
    state = {'root': str(root), 'uid': os.getuid(), 'run_id': secrets.token_hex(32),
             'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'launcher': identity(os.getpid()),
             'ports': {'backend': int(os.environ['FLOODPULSE_BACKEND_PORT']),
                       'frontend': int(os.environ['FLOODPULSE_FRONTEND_PORT'])}}
    children = []
    result = 1
    def stopping(signum, frame):
        raise StopRequested(signum)
    signal.signal(signal.SIGINT, stopping)
    signal.signal(signal.SIGTERM, stopping)
    def start(label, command, cwd, frontend=False):
        log = root / 'data/tmp/launcher' / (label + '.log')
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            environment = service_environment(frontend)
            environment[MARKER] = state['run_id']
            child = subprocess.Popen(command, cwd=cwd, env=environment,
                                     stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        return child
    def ready(child, url, label):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise LaunchError(f'{label} exited; inspect its private launcher log.')
            probe = subprocess.run(['curl', '--silent', '--fail', '--max-time', '2', url],
                                   env=service_environment(True), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=3)
            if probe.returncode == 0:
                return
            time.sleep(0.1)
        raise LaunchError(f'{label} readiness timed out; inspect its private launcher log.')
    try:
        save_receipt(root, state)
        print('[4/5] Starting FastAPI on loopback...', flush=True)
        backend = start('backend', [str(root / 'backend/.venv/bin/python'), '-B', '-m', 'uvicorn',
                        'app.main:app', '--app-dir', str(root / 'backend'), '--host', '127.0.0.1',
                        '--port', str(state['ports']['backend'])], root)
        base = 'http://127.0.0.1:' + str(state['ports']['backend'])
        for path in ('health', 'locations/districts', 'shelters'):
            ready(backend, base + '/api/' + path, 'FastAPI')
        print('[5/5] Starting React/Vite on loopback...', flush=True)
        frontend = start('frontend', ['npm', 'run', 'dev', '--', '--host', '127.0.0.1',
                         '--port', str(state['ports']['frontend']), '--strictPort'], root / 'frontend', True)
        origin = os.environ['SHELTER_PUBLIC_ORIGIN']
        ready(frontend, origin, 'React/Vite')
        print(f'\nApplication: {origin}\nAdmin:       {origin}/admin\nBackend:     {base}\n'
              '\nPress Ctrl+C to stop FloodPulse. No refresh while the browser is closed.', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.1)
        raise LaunchError('A web service exited unexpectedly; both owned services will stop.')
    except StopRequested as stopped:
        print('\nStopping FloodPulse web services; database left running.', flush=True)
        result = 128 + stopped.signum
    except LaunchError as error:
        print('FloodPulse: ' + str(error), file=sys.stderr)
    except (OSError, subprocess.SubprocessError):
        # Never stringify OS/subprocess exceptions: their arguments may be private.
        print('FloodPulse: web startup/service failed; inspect private launcher logs.', file=sys.stderr)
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        stop_owned(root, state)
        for child in children:
            child.wait()
    return result


def main():
    try:
        root = Path(sys.argv[2]).resolve()
        if sys.argv[1] == 'recover':
            recover(root)
            return 0
        if sys.argv[1] == 'stop':
            print('FloodPulse: stopped the running app.' if stop_running(root) else 'FloodPulse: no running app found for this folder.', flush=True)
            return 0
        return run(root)
    except LaunchError as error:
        print('FloodPulse: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError):
        print('FloodPulse: launcher ownership/shutdown failed; no unverified process was stopped. '
              'Check private runtime permissions and port diagnostics.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
