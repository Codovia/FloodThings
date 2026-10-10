"""Offline private-profile checks with synthetic credentials in tmp_path only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher_config', ROOT / 'scripts/launcher_config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
SYNTHETIC = 'TEST_ONLY_secret:@/$()'


@pytest.fixture
def profile(tmp_path):
    file = tmp_path / 'data/tmp/launcher/config.json'
    file.parent.mkdir(parents=True)
    password = tmp_path / 'password'
    password.write_text(SYNTHETIC + '\n'); password.chmod(0o600)
    records = {'database_connections': {
        name: {'url': 'postgresql+psycopg://service@127.0.0.1:55436/floodpulse_directory',
               'password_file': 'password'} for name in config.CONNECTIONS}}
    file.write_text(json.dumps(records)); file.chmod(0o600)
    return tmp_path, file, password, records


def test_profile_resolves_references_without_shell_evaluation_or_secret_copy(profile):
    root, file, password, _ = profile
    env = config.configured_environment(root, {'UNCHANGED': 'yes'})
    assert env['UNCHANGED'] == 'yes' and env['FLOODPULSE_CONFIG_LOADED'] == '1'
    for name in config.CONNECTIONS:
        assert unquote(urlsplit(env[name]).password) == SYNTHETIC
    assert SYNTHETIC not in file.read_text()
    assert password.read_text() == SYNTHETIC + '\n'


def test_explicit_environment_takes_precedence_and_does_not_read_unused_password(profile):
    root, _, password, _ = profile
    password.unlink()
    env = config.configured_environment(root, {name: 'EXPLICIT' for name in config.CONNECTIONS})
    assert all(env[name] == 'EXPLICIT' for name in config.CONNECTIONS)


@pytest.mark.parametrize('target', ['profile', 'password'])
def test_non_private_permissions_are_rejected(profile, target):
    root, file, password, _ = profile
    (file if target == 'profile' else password).chmod(0o644)
    with pytest.raises(ValueError): config.configured_environment(root, {})


def test_symlink_password_rejected(profile):
    root, _, password, _ = profile
    target = root / 'target'; password.rename(target); password.symlink_to(target)
    with pytest.raises(ValueError): config.configured_environment(root, {})


def test_wrong_owner_rejected(profile, monkeypatch):
    monkeypatch.setattr(config.os, 'getuid', lambda: -1)
    with pytest.raises(ValueError): config.configured_environment(profile[0], {})


@pytest.mark.parametrize('change', ['embedded_password', 'unknown_field', 'shell_command', 'missing_connection'])
def test_invalid_profile_rejected(profile, change):
    root, file, _, records = profile
    row = records['database_connections']['DATABASE_URL']
    if change == 'embedded_password': row['url'] = row['url'].replace('service@', 'service:secret@')
    if change == 'unknown_field': records['command'] = 'echo unsafe'
    if change == 'shell_command': row['url'] = '$(touch SHOULD_NOT_EXIST)'
    if change == 'missing_connection': del records['database_connections']['SHELTER_DATABASE_URL']
    file.write_text(json.dumps(records))
    with pytest.raises(ValueError): config.configured_environment(root, {})
    assert not (root / 'SHOULD_NOT_EXIST').exists()


def test_configuration_failure_never_prints_secret(profile):
    root, file, _, _ = profile
    file.write_text(SYNTHETIC)  # Invalid JSON; exception must not echo its input.
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/launcher_config.py'), str(root)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'profile unavailable/invalid' in result.stderr
    assert SYNTHETIC not in result.stdout + result.stderr


def test_helper_executes_launcher_from_another_directory_without_url_exports(profile):
    root, _, _, _ = profile
    launcher = root / 'start.sh'
    launcher.write_text('#!' + sys.executable + '\nimport os,sys\n'
                        'assert os.environ["FLOODPULSE_CONFIG_LOADED"]=="1"\n'
                        'assert os.environ["DATABASE_URL"] and os.environ["SHELTER_DATABASE_URL"]\n'
                        'assert sys.argv[1:]==["--check"]\nprint("ready")\n')
    launcher.chmod(0o700)
    env = {k: v for k, v in os.environ.items() if k not in config.CONNECTIONS}
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/launcher_config.py'), str(root), '--check'],
                            cwd='/', env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout == 'ready\n'
    assert SYNTHETIC not in result.stdout + result.stderr
