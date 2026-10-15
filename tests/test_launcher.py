"""Offline Linux process-control tests; no database, provider or model fitting."""
import os
import json
from pathlib import Path
import secrets
import signal
import socket
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
if kind=='python' and any(a.endswith('/scripts/'+name) for a in sys.argv for name in ['launcher_config.py','launcher_processes.py']):
 os.execv(sys.executable,[sys.executable,*sys.argv[2:]])
with (root/'events').open('a') as f:f.write(kind+' '+(' '.join(sys.argv[1:]) if kind=='docker' else '')+'\n')
if kind=='python' and 'preflight' in sys.argv:
 sys.stdin.read();assert os.environ['VIRTUAL_ENV']==str(root/'backend/.venv')
 assert os.environ.get('DATABASE_URL') and os.environ.get('SHELTER_DATABASE_URL')
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
 assert not any(k in os.environ for k in ['DATABASE_URL','SHELTER_DATABASE_URL','LOCATION_DIRECTORY_ADMIN_URL','TELEGRAM_BOT_USERNAME','TELEGRAM_BOT_TOKEN','TELEGRAM_DESTINATIONS','TELEGRAM_WEBHOOK_SECRET'])
 (root/'frontend.isolated').touch()
if label=='backend' and os.environ.get('EXPECT_TELEGRAM_FILE'):
 assert os.environ.get('TELEGRAM_BOT_USERNAME')=='FloodPulsebot'
 assert all(os.environ.get(k) for k in ['TELEGRAM_BOT_TOKEN','TELEGRAM_DESTINATIONS','TELEGRAM_WEBHOOK_SECRET'])
 assert 'LOCATION_DIRECTORY_ADMIN_URL' not in os.environ
if os.environ.get('FAIL_'+label.upper()):
 print('PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',flush=True);sys.exit(17)
worker_code="""
import os,signal,socket,time,sys
from pathlib import Path
root=Path(os.environ['FAKE_ROOT']);label=sys.argv[1]
if os.environ.get('DETACH_WORKER'):os.setsid()
if os.environ.get('IGNORE_TERM_WORKER'):signal.signal(signal.SIGTERM,signal.SIG_IGN)
if os.environ.get('BIND_WORKER'):
 listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
 listener.bind(('127.0.0.1',int(os.environ['FLOODPULSE_BACKEND_PORT' if label=='backend' else 'FLOODPULSE_FRONTEND_PORT'])));listener.listen()
(root/(label+'.worker')).touch()
time.sleep(120)
"""
worker=subprocess.Popen([sys.executable,'-c',worker_code,label])
with (root/'pids').open('a') as f:f.write(str(os.getpid())+'\n'+str(worker.pid)+'\n')
for _ in range(100):
 if (root/(label+'.worker')).exists():break
 time.sleep(.01)
else:sys.exit(18)
(root/(label+'.ready')).write_text('ready')
if label=='frontend' and os.environ.get('EXIT_FRONTEND_PARENT'):sys.exit(19)
time.sleep(120)
'''


@pytest.fixture
def project(tmp_path):
    script = tmp_path / 'start.sh'
    script.write_bytes((ROOT / 'start.sh').read_bytes()); script.chmod(0o700)
    envdir = tmp_path / 'backend/.venv/bin'; envdir.mkdir(parents=True)
    (tmp_path / 'frontend').mkdir()
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    (scripts / 'launcher_config.py').write_bytes((ROOT / 'scripts/launcher_config.py').read_bytes())
    (scripts / 'launcher_processes.py').write_text((ROOT / 'scripts/launcher_processes.py').read_text().replace('STARTUP_TIMEOUT = 30','STARTUP_TIMEOUT = 2'))
    (envdir / 'activate').write_text(f'export VIRTUAL_ENV={tmp_path}/backend/.venv\n')
    tools = tmp_path / 'bin'; tools.mkdir()
    for name in ['python', 'node', 'npm', 'docker', 'curl', 'sleep']:
        file = (envdir if name == 'python' else tools) / name
        file.write_text('#!' + sys.executable + '\n' + FAKE); file.chmod(0o700)
    (tmp_path / 'state').write_text('running')
    env = dict(os.environ, PATH=str(tools) + ':' + os.environ['PATH'], FAKE_ROOT=str(tmp_path),
               DATABASE_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY', SHELTER_DATABASE_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',
               LOCATION_DIRECTORY_ADMIN_URL='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY', TELEGRAM_BOT_TOKEN='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',
               TELEGRAM_DESTINATIONS='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY', TELEGRAM_WEBHOOK_SECRET='PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY')
    # Never depend on the operator's live ports being free, including shutdown
    # checks in tests which use fake preflight executables.
    configure_test_ports((tmp_path, env))
    return tmp_path, env


def run(project, *args, **settings):
    root, env = project
    result = subprocess.run([str(root / 'start.sh'), *args], env={**env, **settings}, cwd='/', capture_output=True, text=True, timeout=20)
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


def test_launcher_bootstraps_private_profile_with_no_exported_urls(project):
    root, env = project
    password = root / 'password'; password.write_text('PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY'); password.chmod(0o600)
    file = root / 'data/tmp/launcher/config.json'; file.parent.mkdir(parents=True)
    file.write_text(json.dumps({'database_connections': {
        name: {'url': 'postgresql+psycopg://service@127.0.0.1:55436/floodpulse_directory', 'password_file': 'password'}
        for name in ['DATABASE_URL', 'SHELTER_DATABASE_URL']}})); file.chmod(0o600)
    result = run(project, '--check', DATABASE_URL='', SHELTER_DATABASE_URL='', FLOODPULSE_CONFIG_LOADED='')
    assert result.returncode == 0 and 'Checks passed' in result.stdout
    assert not (root / 'pids').exists()


def test_root_dotenv_reaches_only_backend_even_with_explicit_database_connections(project):
    root, env = project
    keys = ['TELEGRAM_BOT_USERNAME', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_DESTINATIONS', 'TELEGRAM_WEBHOOK_SECRET']
    for key in keys: env.pop(key, None)
    values = {key: secrets.token_urlsafe(32) for key in keys}
    values['TELEGRAM_BOT_USERNAME'] = 'FloodPulsebot'
    file = root / '.env'
    file.write_text('\n'.join(f'{key}={value}' for key, value in values.items()))
    file.chmod(0o600)
    result = run(project, EXPECT_TELEGRAM_FILE='1', FAIL_FRONTEND='1')
    assert result.returncode != 0
    assert (root / 'backend.ready').exists() and (root / 'frontend.isolated').exists()
    assert all(value not in result.stdout + result.stderr for value in values.values())
    no_orphans(root)


@pytest.mark.parametrize('missing', ['DATABASE_URL', 'SHELTER_DATABASE_URL'])
def test_real_preflight_names_missing_variable_without_printing_other_values(missing):
    code = (ROOT / 'start.sh').read_text().split('"$VENV/bin/python" - preflight <<\'PY\'\n')[1].split('\nPY\n')[0]
    env = {**os.environ, 'DATABASE_URL': 'PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY',
           'SHELTER_DATABASE_URL': 'PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY'}
    del env[missing]
    result = subprocess.run([sys.executable, '-B', '-'], input=code, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0 and f'Missing {missing}.' in result.stderr
    assert 'PRIVATE_SENTINEL_LAUNCHER_TEST_ONLY' not in result.stdout + result.stderr


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
        assert proc.returncode == 130 and 'Application: http://127.0.0.1:' + env['FLOODPULSE_FRONTEND_PORT'] in stdout
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


def configure_test_ports(project):
    root, env = project
    with socket.socket() as backend, socket.socket() as frontend:
        backend.bind(('127.0.0.1', 0)); frontend.bind(('127.0.0.1', 0))
        first, second = backend.getsockname()[1], frontend.getsockname()[1]
    env.update(FLOODPULSE_BACKEND_PORT=str(first), FLOODPULSE_FRONTEND_PORT=str(second),
               SHELTER_PUBLIC_ORIGIN='http://127.0.0.1:'+str(second), BIND_WORKER='1')
    return first, second


def launch_until_ready(project):
    root, env = project
    for name in ('backend.ready','frontend.ready','backend.worker','frontend.worker'):
        (root/name).unlink(missing_ok=True)
    terminal = (root/'terminal.log').open('w')
    proc = subprocess.Popen([str(root/'start.sh')], cwd='/', env=env,
                            stdout=terminal, stderr=subprocess.STDOUT)
    terminal.close()
    try:
        for _ in range(300):
            if 'Press Ctrl+C' in (root/'terminal.log').read_text():return proc
            assert proc.poll() is None, (root/'terminal.log').read_text()
            time.sleep(.02)
        pytest.fail('Mocked launcher did not become ready')
    except BaseException:
        if proc.poll() is None:proc.send_signal(signal.SIGTERM);proc.wait(timeout=15)
        raise


def assert_released(ports):
    for port in ports:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',port));listener.listen()


@pytest.mark.parametrize('signum',[signal.SIGINT,signal.SIGTERM])
def test_repeated_restarts_release_groups_detached_descendants_and_ports(project,signum):
    ports=configure_test_ports(project)
    root, env=project;env['DETACH_WORKER']='1'
    for _ in range(3):
        proc=launch_until_ready(project)
        try:
            proc.send_signal(signum);proc.wait(timeout=15)
            assert proc.returncode==128+signum
            no_orphans(root);assert_released(ports)
            assert not (root/'data/tmp/launcher/processes.json').exists()
            assert run(project,'--check').returncode==0
        finally:
            if proc.poll() is None:proc.send_signal(signal.SIGTERM);proc.wait(timeout=15)


def test_sigterm_resistant_descendant_is_killed_before_shutdown_finishes(project):
    ports=configure_test_ports(project);root,env=project
    env.update(IGNORE_TERM_WORKER='1',DETACH_WORKER='1')
    proc=launch_until_ready(project)
    try:
        proc.send_signal(signal.SIGTERM)
        duplicate=run(project,'--check')
        assert duplicate.returncode!=0 and 'already running' in duplicate.stderr
        proc.wait(timeout=15)
        assert proc.returncode==143
        no_orphans(root);assert_released(ports)
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)


def test_hard_killed_launcher_recovers_only_nonce_proven_children_on_restart(project):
    ports=configure_test_ports(project);root,env=project;env['DETACH_WORKER']='1'
    first=launch_until_ready(project)
    first.kill();first.wait(timeout=5)
    old_pids=[int(p) for p in (root/'pids').read_text().splitlines()]
    assert any(active(pid) for pid in old_pids)
    second=launch_until_ready(project)
    try:
        assert 'Cleaning up verified children' in (root/'terminal.log').read_text()
        assert not any(active(pid) for pid in old_pids)
        second.send_signal(signal.SIGINT);second.wait(timeout=15)
        assert second.returncode==130
        no_orphans(root);assert_released(ports)
    finally:
        if second.poll() is None:second.send_signal(signal.SIGTERM);second.wait(timeout=15)


def test_npm_parent_exit_still_cleans_worker_listener(project):
    ports=configure_test_ports(project);root,env=project
    result=run(project,EXIT_FRONTEND_PARENT='1',DETACH_WORKER='1')
    assert result.returncode!=0
    no_orphans(root);assert_released(ports)
