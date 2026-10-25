"""deploy/auto-update.sh and deploy/backup.sh against throwaway Git repositories.

docker, crontab and setup.sh are stand-ins that record their calls; no real database, crontab or
network is used.
"""
import fcntl
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'
DOCKER = """#!/bin/sh
echo "docker $*" >> "$CALLS"
case "$*" in
  *pg_dump*) echo DUMP ;;
  *api/health/ready*) exit "${READY_EXIT:-0}" ;;
esac
"""
CRONTAB = """#!/bin/sh
if [ "$1" = -l ]; then cat "$CRON" 2>/dev/null || exit 1; else cat > "$CRON"; fi
"""
SETUP = """#!/bin/sh
echo setup >> "$CALLS"
exit "${SETUP_EXIT:-0}"
"""


def sh(*args, cwd, env=None, check=True):
    return subprocess.run(args, cwd=cwd, env=env, check=check, capture_output=True, text=True)


def write(path, text, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


@pytest.fixture
def server(tmp_path_factory):
    """(origin work tree, server clone, environment, calls file)."""
    root = tmp_path_factory.mktemp('auto-update')
    env = {**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'Test',
           'GIT_AUTHOR_EMAIL': 'test@example.invalid', 'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
           'CALLS': str(root / 'calls'), 'CRON': str(root / 'crontab'), 'FLOODPULSE_READY_WAIT': '1'}
    write(root / 'bin/docker', DOCKER)
    write(root / 'bin/crontab', CRONTAB)
    env['PATH'] = f"{root / 'bin'}:{env['PATH']}"
    sh('git', 'init', '-q', '--bare', '-b', 'main', str(root / 'origin.git'), cwd=root, env=env)
    dev = root / 'dev'
    sh('git', 'clone', '-q', str(root / 'origin.git'), str(dev), cwd=root, env=env)
    write(dev / 'deploy/setup.sh', SETUP)
    for name in ('auto-update.sh', 'backup.sh'):
        shutil.copy2(DEPLOY / name, dev / 'deploy' / name)
    (dev / '.gitignore').write_text('deploy/.auto-update.*\n*.log\ndeploy/backups/\n')
    sh('git', 'add', '.', cwd=dev, env=env)
    sh('git', 'commit', '-qm', 'first', cwd=dev, env=env)
    sh('git', 'push', '-q', 'origin', 'main', cwd=dev, env=env)
    srv = root / 'server'
    sh('git', 'clone', '-q', str(root / 'origin.git'), str(srv), cwd=root, env=env)
    return dev, srv, env, root / 'calls'


def push(dev, env, name='feature.txt'):
    (dev / name).write_text(name)
    sh('git', 'add', name, cwd=dev, env=env)
    sh('git', 'commit', '-qm', f'add {name}', cwd=dev, env=env)
    sh('git', 'push', '-q', 'origin', 'main', cwd=dev, env=env)
    return sh('git', 'rev-parse', 'HEAD', cwd=dev, env=env).stdout.strip()


def run(srv, env, *args, **extra):
    return sh(str(srv / 'deploy/auto-update.sh'), *args, cwd=srv, env={**env, **extra}, check=False)


def head(srv, env):
    return sh('git', 'rev-parse', 'HEAD', cwd=srv, env=env).stdout.strip()


def calls(path):
    return path.read_text().splitlines() if path.exists() else []


def log(srv):
    path = srv / 'deploy/auto-update.log'
    return path.read_text() if path.exists() else ''


def test_nothing_new_changes_nothing(server):
    _, srv, env, record = server
    assert run(srv, env).returncode == 0
    assert calls(record) == [] and log(srv) == ''


def test_new_commit_is_backed_up_pulled_set_up_and_checked(server):
    dev, srv, env, record = server
    new = push(dev, env)
    assert run(srv, env).returncode == 0
    assert head(srv, env) == new
    steps = calls(record)
    assert 'pg_dump' in steps[0] and steps[1] == 'setup' and 'api/health/ready' in steps[2]
    assert [p.name.split('-2')[0] for p in (srv / 'deploy/backups').iterdir()] == ['pre-update']
    assert f'OK: now running {new[:7]}' in log(srv)
    assert run(srv, env).returncode == 0 and len(calls(record)) == 3   # up to date: nothing more


def test_updated_files_stay_readable_inside_the_docker_image(server):
    """Regression: a private umask made updated code unreadable to the container's user (PermissionError on main.py)."""
    dev, srv, env, _ = server
    push(dev, env, 'new_module.py')
    (dev / '.gitignore').write_text((dev / '.gitignore').read_text() + 'extra/\n')   # a changed file is rewritten too
    sh('git', 'commit', '-qam', 'change', cwd=dev, env=env)
    sh('git', 'push', '-q', 'origin', 'main', cwd=dev, env=env)
    assert run(srv, env).returncode == 0
    for name in ('new_module.py', '.gitignore'):
        assert (srv / name).stat().st_mode & 0o044 == 0o044, name
    assert (srv / 'deploy/auto-update.log').stat().st_mode & 0o077 == 0   # the script's own log stays private


def test_changes_made_on_the_server_are_never_overwritten(server):
    dev, srv, env, record = server
    old = head(srv, env)
    (srv / 'deploy/setup.sh').write_text('#!/bin/sh\necho edited on server\n')
    new = push(dev, env)
    assert run(srv, env).returncode == 1
    assert head(srv, env) == old and calls(record) == []
    assert 'files tracked by Git were changed on the server' in log(srv)
    assert run(srv, env).returncode == 0 and log(srv).count('FAILED') == 1   # not retried for the same commit
    assert (srv / 'deploy/.auto-update.failed').read_text().strip() == new


def test_failed_setup_is_logged_once_and_a_newer_commit_is_tried(server):
    dev, srv, env, record = server
    first = push(dev, env)
    assert run(srv, env, SETUP_EXIT='1').returncode == 1
    assert f'setup.sh failed at {first[:7]}' in log(srv) and calls(record).count('setup') == 1
    assert run(srv, env).returncode == 0 and calls(record).count('setup') == 1
    second = push(dev, env, 'fix.txt')
    assert run(srv, env).returncode == 0
    assert head(srv, env) == second and f'OK: now running {second[:7]}' in log(srv)
    assert not (srv / 'deploy/.auto-update.failed').exists()


def test_app_not_ready_is_reported(server):
    dev, srv, env, _ = server
    new = push(dev, env)
    assert run(srv, env, READY_EXIT='1').returncode == 1
    assert f'did not report ready within 1s after updating to {new[:7]}' in log(srv)


def test_a_second_copy_waits_for_the_running_one(server):
    dev, srv, env, record = server
    push(dev, env)
    with open(srv / 'deploy/.auto-update.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert run(srv, env).returncode == 0
    assert calls(record) == []


def test_on_off_keeps_other_cron_jobs(server):
    _, srv, env, _ = server
    cron = Path(env['CRON'])
    cron.write_text('0 2 * * * cd ~/floodpulse/deploy && ./backup.sh\n')
    for _ in range(2):
        assert run(srv, env, '--on').returncode == 0
    lines = cron.read_text().splitlines()
    assert lines == ['0 2 * * * cd ~/floodpulse/deploy && ./backup.sh', f"*/5 * * * * {(srv / 'deploy').resolve()}/auto-update.sh"]
    assert 'Automatic updates: on' in run(srv, env, '--status').stdout
    assert run(srv, env, '--off').returncode == 0
    assert cron.read_text().splitlines() == lines[:1]
    assert 'Automatic updates: off' in run(srv, env, '--status').stdout
    bogus = run(srv, env, "--bogus")
    assert bogus.returncode == 2 and "--on" in bogus.stdout


def test_update_backups_rotate_separately_from_daily_backups(tmp_path_factory, server):
    _, _, env, _ = server
    deploy = tmp_path_factory.mktemp('backups')
    shutil.copy2(DEPLOY / 'backup.sh', deploy / 'backup.sh')
    (deploy / 'backups').mkdir()
    for k in range(3):
        (deploy / f'backups/floodpulse-2026010{k}-000000.dump').write_text('daily')
    for k in range(15):
        old = deploy / f'backups/pre-update-202601{k + 10}-000000.dump'
        old.write_text('old')
        os.utime(old, (1_000_000 + k, 1_000_000 + k))
    assert sh('./backup.sh', 'pre-update', cwd=deploy, env=env).returncode == 0
    names = sorted(p.name for p in (deploy / 'backups').iterdir())
    assert sum(n.startswith('floodpulse-') for n in names) == 3
    assert sum(n.startswith('pre-update-') for n in names) == 14 and 'pre-update-20260110-000000.dump' not in names
    assert sh('./backup.sh', 'anything', cwd=deploy, env=env, check=False).returncode == 2
