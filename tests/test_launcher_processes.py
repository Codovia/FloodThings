"""Real local sockets/processes in tmp_path; no database or provider access."""
import errno
import importlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import launcher_processes as processes


@pytest.mark.parametrize('label', ['backend', 'frontend'])
def test_specific_port_pid_diagnostics_preserve_foreign_listener_and_hide_secrets(label, monkeypatch):
    private = secrets.token_urlsafe(32)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', private)
    monkeypatch.setenv('DATABASE_URL', private)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(processes.LaunchError) as error:
            processes.ensure_ports_available({label: port})
        text = str(error.value)
        assert f'{label} port {port}' in text and f'PID {os.getpid()}' in text
        assert private not in text and 'TELEGRAM_BOT_TOKEN' not in text
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            peer, _ = listener.accept(); peer.close()


def test_time_wait_is_not_reported_as_a_listener_or_an_orphan():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0)); listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(('127.0.0.1', port)) as client:
            peer, _ = listener.accept()
            peer.close(); assert client.recv(1) == b''
    with socket.socket() as old_probe:
        with pytest.raises(OSError) as error:
            old_probe.bind(('127.0.0.1', port))
        assert error.value.errno == errno.EADDRINUSE
    processes.ensure_ports_available({'backend': port})


def test_unavailable_pid_diagnostics_still_identify_the_port(monkeypatch):
    monkeypatch.setattr(processes, 'port_owners', lambda _: 'listener owner unavailable')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        with pytest.raises(processes.LaunchError, match='frontend port .*listener owner unavailable'):
            processes.ensure_ports_available({'frontend': listener.getsockname()[1]})


@pytest.mark.parametrize('failure', ['dependency', 'model', 'configuration'])
def test_preflight_distinguishes_non_port_failures_without_echoing_exception(failure, monkeypatch):
    private = secrets.token_urlsafe(32)
    monkeypatch.setenv('DATABASE_URL', private)
    monkeypatch.setenv('SHELTER_DATABASE_URL', private)
    monkeypatch.setenv('FLOODPULSE_BACKEND_PORT', private)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    def dependency(name):
        if failure == 'dependency': raise ImportError(private)
    def model():
        if failure == 'model': raise OSError(private)
    monkeypatch.setattr(importlib, 'import_module', dependency)
    monkeypatch.setitem(sys.modules, 'app.rainfall_outlook', SimpleNamespace(RainfallModel=model))
    code = (ROOT / 'scripts/app_launcher.sh').read_text().split('"$VENV/bin/python" - preflight <<\'PY\'\n')[1].split('\nPY\n')[0]
    with pytest.raises(SystemExit) as error:
        exec(code, {})
    message = str(error.value)
    expected = {'dependency': 'Python dependency', 'model': 'model artifact', 'configuration': 'Launcher configuration'}
    assert expected[failure] in message and 'occupied' not in message and private not in message


@pytest.fixture
def foreign_process(tmp_path):
    ready = tmp_path / 'foreign-port'
    code = ('import socket,sys,time;from pathlib import Path;'
            's=socket.socket();s.bind(("127.0.0.1",0));s.listen();'
            'Path(sys.argv[1]).write_text(str(s.getsockname()[1]));time.sleep(120)')
    child = subprocess.Popen([sys.executable, '-c', code, str(ready)])
    try:
        import time
        for _ in range(100):
            if ready.exists(): break
            assert child.poll() is None
            time.sleep(.01)
        assert ready.exists()
        yield child, int(ready.read_text())
    finally:
        child.terminate(); child.wait(timeout=5)


def test_stale_or_recycled_pid_without_run_proof_is_never_signalled(tmp_path, foreign_process):
    child, port = foreign_process
    row = processes.identity(child.pid)
    stale = {**row, 'start': row['start'] + 1}
    processes.signal_process(stale, signal.SIGTERM)
    assert child.poll() is None
    with socket.socket() as free:
        free.bind(('127.0.0.1', 0)); second = free.getsockname()[1]
    path = processes.receipt_path(tmp_path); path.parent.mkdir(parents=True)
    state = {'root': str(tmp_path), 'uid': os.getuid(), 'run_id': secrets.token_hex(32),
             'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'launcher': stale, 'ports': {'backend': port, 'frontend': second}}
    processes.save_receipt(tmp_path, state)
    with pytest.raises(processes.LaunchError, match='backend port .*occupied'):
        processes.recover(tmp_path)
    assert child.poll() is None


@pytest.mark.parametrize('kind', ['malformed', 'permissions', 'symlink'])
def test_bad_ownership_receipt_fails_closed(tmp_path, foreign_process, kind):
    child, _ = foreign_process
    path = processes.receipt_path(tmp_path); path.parent.mkdir(parents=True)
    path.write_text('{}'); path.chmod(0o600)
    if kind == 'permissions': path.chmod(0o644)
    if kind == 'symlink':
        target = path.with_suffix('.target'); path.rename(target); path.symlink_to(target)
    with pytest.raises((OSError, ValueError, processes.LaunchError)):
        processes.recover(tmp_path)
    assert child.poll() is None


@pytest.fixture
def stoppable(tmp_path):
    """A throwaway process standing in for a running launcher; it exits on Ctrl+C (SIGINT)."""
    child = subprocess.Popen([sys.executable, '-c', 'import time\ntry:\n time.sleep(120)\nexcept KeyboardInterrupt:\n pass'])
    import time
    for _ in range(100):
        if processes.identity(child.pid): break
        time.sleep(.01)
    try:
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def receipt_for(tmp_path, launcher, boot=None):
    state = {'root': str(tmp_path), 'uid': os.getuid(), 'run_id': secrets.token_hex(32),
             'boot_id': boot or Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'launcher': launcher, 'ports': {'backend': 18050, 'frontend': 14180}}
    processes.receipt_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    processes.save_receipt(tmp_path, state)


def test_stop_signals_only_the_verified_running_launcher(tmp_path, stoppable):
    import time
    time.sleep(.3)  # let the child install its interpreter before it is interrupted
    receipt_for(tmp_path, processes.identity(stoppable.pid))
    assert processes.stop_running(tmp_path, wait=10) is True
    assert stoppable.wait(timeout=5) == 0  # exited through its Ctrl+C handler


def test_stop_never_signals_a_recycled_pid_or_a_previous_boot(tmp_path, stoppable):
    row = processes.identity(stoppable.pid)
    receipt_for(tmp_path, {**row, 'start': row['start'] + 1})
    assert processes.stop_running(tmp_path, wait=1) is False and stoppable.poll() is None
    receipt_for(tmp_path, row, boot='0' * 36)
    assert processes.stop_running(tmp_path, wait=1) is False and stoppable.poll() is None


def test_stop_without_a_receipt_does_nothing(tmp_path):
    assert processes.stop_running(tmp_path) is False


@pytest.mark.parametrize('address, expected', [('10.73.242.93', '10.73.242.93'), ('192.168.1.5', '192.168.1.5'),
                                               ('8.8.8.8', None), ('127.0.0.1', None), ('169.254.3.4', None), (OSError, None)])
def test_lan_address_is_only_a_private_network_address(address, expected, monkeypatch):
    class Probe:
        def __enter__(self):return self
        def __exit__(self, *exc):return False
        def connect(self, target):
            if address is OSError:raise OSError(errno.ENETUNREACH, 'unreachable')
        def getsockname(self):return (address, 40000)
    monkeypatch.setattr(processes.socket, 'socket', lambda *args:Probe())
    assert processes.lan_address() == expected
