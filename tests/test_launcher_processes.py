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
    code = (ROOT / 'start.sh').read_text().split('"$VENV/bin/python" - preflight <<\'PY\'\n')[1].split('\nPY\n')[0]
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
