"""Offline Linux process-control tests; no database, provider or model fitting."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]

# These executables simulate only launcher dependencies inside a temporary tree.
# Application/provider behavior is checked separately by a genuine smoke run.
FAKE = r'''
import os,sys,time,subprocess
from pathlib import Path
root=Path(os.environ['FAKE_ROOT']);kind=Path(sys.argv[0]).name
with (root/'events').open('a') as f:f.write(kind+' '+(' '.join(sys.argv[1:]) if kind=='docker' else '')+'\n')
if kind=='python' and 'preflight' in sys.argv:
 sys.stdin.read();assert os.environ['VIRTUAL_ENV']==str(root/'backend/.venv')
 sys.exit(int(os.environ.get('FAIL_PREFLIGHT','0')))
if kind=='python' and 'database' in sys.argv:
 sys.stdin.read();sys.exit(int(os.environ.get('FAIL_DATABASE','0')))
if kind=='node':
 sys.stdin.read();sys.exit(int(os.environ.get('FAIL_NODE','0')))
if kind=='docker':
 command=sys.argv[1]
 if command=='info':sys.exit(int(os.environ.get('FAIL_DOCKER','0')))
 if command=='inspect':
  if os.environ.get('MISSING_CONTAINER'):sys.exit(1)
  print((root/'state').read_text());sys.exit(0)
 if command=='start':(root/'state').write_text('running');sys.exit(0)
 if command=='exec':
  file=root/'probes';count=int(file.read_text())+1 if file.exists() else 1;file.write_text(str(count))
  sys.exit(1 if count<=int(os.environ.get('NOT_READY_PROBES','0')) else 0)
if kind=='curl':
 if os.environ.get('FAIL_HEALTH'):sys.exit(1)
 # Never report readiness before the mocked process actually starts.
 marker=root/('backend.ready' if '/api/' in sys.argv[-1] else 'frontend.ready')
 sys.exit(0 if marker.exists() else 1)
if kind=='sleep':time.sleep(.03);sys.exit(0)
label='frontend' if kind=='npm' else 'backend'
if label=='frontend':
 assert not any(k in os.environ for k in ['DATABASE_URL','SHELTER_DATABASE_URL','LOCATION_DIRECTORY_ADMIN_URL','TELEGRAM_BOT_TOKEN','TELEGRAM_DESTINATIONS'])
if os.environ.get('FAIL_'+label.upper()):
 print('PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',flush=True);sys.exit(17)
worker=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
with (root/'pids').open('a') as f:f.write(str(os.getpid())+'\n'+str(worker.pid)+'\n')
(root/(label+'.ready')).write_text('ready')
time.sleep(120)
'''


@pytest.fixture
def project(tmp_path):
    script = tmp_path / 'start.sh'
    script.write_bytes((ROOT / 'start.sh').read_bytes()); script.chmod(0o700)
    envdir = tmp_path / 'backend/.venv/bin'; envdir.mkdir(parents=True)
    (tmp_path / 'frontend').mkdir()
    (envdir / 'activate').write_text(f'export VIRTUAL_ENV={tmp_path}/backend/.venv\n')
    tools = tmp_path / 'bin'; tools.mkdir()
    for name in ['python', 'node', 'npm', 'docker', 'curl', 'sleep']:
        file = (envdir if name == 'python' else tools) / name
        file.write_text('#!' + sys.executable + '\n' + FAKE); file.chmod(0o700)
    (tmp_path / 'state').write_text('running')
    env = dict(os.environ, PATH=str(tools) + ':' + os.environ['PATH'], FAKE_ROOT=str(tmp_path),
               DATABASE_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY', SHELTER_DATABASE_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',
               LOCATION_DIRECTORY_ADMIN_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY', TELEGRAM_BOT_TOKEN='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY')
    return tmp_path, env


def run(project, *args, **settings):
    root, env = project
    result = subprocess.run([str(root / 'start.sh'), *args], env={**env, **settings}, cwd='/', capture_output=True, text=True, timeout=10)
    assert 'PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY' not in result.stdout + result.stderr
    return result


def active(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except FileNotFoundError:
        return False


def no_orphans(root):
    if (root / 'pids').exists():
        for _ in range(50):
            if not any(active(int(p)) for p in (root / 'pids').read_text().splitlines()):return
            time.sleep(.02)
        pytest.fail('Owned backend/frontend worker still running')


def test_help_needs_no_configuration(project):
    assert run(project, '--help').returncode == 0
    assert not (project[0] / 'events').exists()


def test_check_from_other_directory_activates_venv_without_starting_services(project):
    result = run(project, '--check')
    assert result.returncode == 0 and 'Checks passed' in result.stdout
    events = (project[0] / 'events').read_text()
    assert 'npm' not in events and 'docker start' not in events
    assert not (project[0] / 'pids').exists()


@pytest.mark.parametrize('setting', ['FAIL_PREFLIGHT', 'FAIL_NODE', 'FAIL_DOCKER', 'FAIL_DATABASE', 'MISSING_CONTAINER'])
def test_prerequisite_errors_do_not_launch_or_expose_secrets(project, setting):
    assert run(project, '--check', **{setting: '1'}).returncode != 0
    assert not (project[0] / 'pids').exists()


def test_check_does_not_start_stopped_database(project):
    (project[0] / 'state').write_text('exited')
    assert run(project, '--check').returncode != 0
    assert 'docker start' not in (project[0] / 'events').read_text()


@pytest.mark.parametrize('setting', ['FAIL_BACKEND', 'FAIL_FRONTEND', 'FAIL_HEALTH'])
def test_startup_failures_clean_up_owned_children_and_keep_logs_private(project, setting):
    result = run(project, **{setting: '1'})
    assert result.returncode != 0 and 'Application:' not in result.stdout
    no_orphans(project[0])


def test_start_wait_duplicate_lock_sigint_shutdown_and_existing_database_preservation(project):
    root, env = project
    (root / 'state').write_text('exited')
    terminal = (root / 'terminal.log').open('w')
    proc = subprocess.Popen([str(root / 'start.sh')], cwd='/', env={**env, 'NOT_READY_PROBES': '2'}, stdout=terminal, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(200):
            if 'Press Ctrl+C' in (root / 'terminal.log').read_text():break
            assert proc.poll() is None
            time.sleep(.03)
        else:pytest.fail('Mocked launcher never reached frontend')
        duplicate = run(project)
        assert duplicate.returncode != 0 and 'already running' in duplicate.stderr
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=10)
        stdout = (root / 'terminal.log').read_text()
        assert proc.returncode == 130 and 'Application: http://127.0.0.1:14180' in stdout
        assert 'PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY' not in stdout
        assert int((root / 'probes').read_text()) >= 3
        assert (root / 'state').read_text() == 'running'
        assert (root / 'events').read_text().count('docker start') == 1
        no_orphans(root)
        assert run(project, '--check').returncode == 0  # Lock released.
    finally:
        if proc.poll() is None:proc.send_signal(signal.SIGTERM);proc.communicate(timeout=10)
        terminal.close()
        no_orphans(root)
