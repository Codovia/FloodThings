"""Offline private-profile checks with synthetic credentials in tmp_path only."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
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
    dotenv = root / '.env'
    dotenv.write_text('TELEGRAM_BOT_USERNAME=FloodPulsebot\n'
                      'TELEGRAM_BOT_TOKEN=' + secrets.token_urlsafe(32) + '\n')
    dotenv.chmod(0o600)
    launcher = root / 'start.sh'
    launcher.write_text('#!' + sys.executable + '\nimport os,sys\n'
                        'assert os.environ["FLOODPULSE_CONFIG_LOADED"]=="1"\n'
                        'assert os.environ["DATABASE_URL"] and os.environ["SHELTER_DATABASE_URL"]\n'
                        'assert os.environ["TELEGRAM_BOT_USERNAME"]=="FloodPulsebot"\n'
                        'assert os.environ["TELEGRAM_BOT_TOKEN"]\n'
                        'assert sys.argv[1:]==["--check"]\nprint("ready")\n')
    launcher.chmod(0o700)
    env = {k: v for k, v in os.environ.items() if k not in config.CONNECTIONS | config.TELEGRAM_KEYS}
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/launcher_config.py'), str(root), '--check'],
                            cwd='/', env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout == 'ready\n'
    assert SYNTHETIC not in result.stdout + result.stderr


@pytest.fixture
def dotenv(tmp_path):
    # Ephemeral inert fixture values, never operator credentials or real chat IDs.
    values = {'TELEGRAM_BOT_USERNAME': 'FloodPulsebot',
              'TELEGRAM_BOT_TOKEN': secrets.token_urlsafe(32),
              'TELEGRAM_DESTINATIONS': json.dumps({'fixture': {'label': 'Offline only'}}),
              'TELEGRAM_WEBHOOK_SECRET': secrets.token_urlsafe(32)}
    file = tmp_path / '.env'
    file.write_text('# Private configuration\n' + '\n'.join(
        f"{key}='{value}'" for key, value in values.items()) + '\n')
    file.chmod(0o600)
    return tmp_path, file, values


def test_telegram_only_loading_preserves_explicit_environment_and_database_boundary(dotenv):
    root, file, values = dotenv
    with file.open('a') as stream:
        stream.write('DATABASE_URL=ignored\nSHELTER_DATABASE_URL=ignored\n'
                     'LOCATION_DIRECTORY_ADMIN_URL=ignored\nVITE_PRIVATE_VALUE=ignored\n')
    original = {'DATABASE_URL': 'existing', 'UNCHANGED': 'yes',
                'TELEGRAM_BOT_USERNAME': 'ExplicitOperatorBot', 'TELEGRAM_BOT_TOKEN': ''}
    result = config.telegram_environment(root, original)
    assert original == {'DATABASE_URL': 'existing', 'UNCHANGED': 'yes',
                        'TELEGRAM_BOT_USERNAME': 'ExplicitOperatorBot', 'TELEGRAM_BOT_TOKEN': ''}
    assert result['TELEGRAM_BOT_USERNAME'] == 'ExplicitOperatorBot'
    assert result['TELEGRAM_BOT_TOKEN'] == ''
    assert result['DATABASE_URL'] == 'existing'
    assert not {'SHELTER_DATABASE_URL', 'LOCATION_DIRECTORY_ADMIN_URL', 'VITE_PRIVATE_VALUE'} & result.keys()
    assert all(result[key] == values[key] for key in ('TELEGRAM_DESTINATIONS', 'TELEGRAM_WEBHOOK_SECRET'))


def test_missing_optional_file_or_keys_never_invents_credentials(tmp_path):
    assert config.telegram_environment(tmp_path, {'UNCHANGED': 'yes'}) == {'UNCHANGED': 'yes'}
    file = tmp_path / '.env'
    file.write_text('TELEGRAM_BOT_USERNAME=FloodPulsebot\n'); file.chmod(0o600)
    result = config.telegram_environment(tmp_path, {})
    assert result == {'TELEGRAM_BOT_USERNAME': 'FloodPulsebot'}


def test_supported_quotes_comments_export_json_and_no_shell_or_variable_expansion(tmp_path):
    marker = tmp_path / 'should-not-exist'
    literal = '$(touch ' + str(marker) + ') `${UNSET}` # literal'
    file = tmp_path / '.env'
    file.write_text('export TELEGRAM_BOT_USERNAME = FloodPulsebot # public name\n'
                    'TELEGRAM_DESTINATIONS={"fixture":{"label":"offline only"}}\n'
                    'TELEGRAM_BOT_TOKEN=' + json.dumps(literal) + ' # comment\n'
                    "TELEGRAM_WEBHOOK_SECRET='literal#hash' # comment\n")
    file.chmod(0o600)
    result = config.telegram_environment(tmp_path, {})
    assert result['TELEGRAM_BOT_USERNAME'] == 'FloodPulsebot'
    assert result['TELEGRAM_BOT_TOKEN'] == literal
    assert result['TELEGRAM_WEBHOOK_SECRET'] == 'literal#hash'
    assert isinstance(json.loads(result['TELEGRAM_DESTINATIONS']), dict)
    assert not marker.exists()


@pytest.mark.parametrize('mode', [0o644, 0o640, 0o400, 0o700, 0o660])
def test_dotenv_requires_exact_owner_only_0600(dotenv, mode):
    root, file, _ = dotenv
    file.chmod(mode)
    with pytest.raises(ValueError): config.telegram_environment(root, {})


def test_dotenv_rejects_wrong_owner(dotenv, monkeypatch):
    monkeypatch.setattr(config.os, 'getuid', lambda: -1)
    with pytest.raises(ValueError): config.telegram_environment(dotenv[0], {})


@pytest.mark.parametrize('kind', ['symlink', 'dangling', 'directory', 'fifo', 'oversized', 'encoding'])
def test_dotenv_rejects_unsafe_files(dotenv, kind):
    root, file, _ = dotenv
    if kind in ('symlink', 'dangling'):
        target = root / 'private-target'
        file.rename(target)
        if kind == 'dangling': target.unlink()
        file.symlink_to(target)
    elif kind == 'directory': file.unlink(); file.mkdir()
    elif kind == 'fifo': file.unlink(); os.mkfifo(file, 0o600)
    elif kind == 'oversized': file.write_text('#' * 65537)
    elif kind == 'encoding': file.write_bytes(b'\xff')
    with pytest.raises((OSError, ValueError)): config.telegram_environment(root, {})


@pytest.mark.parametrize('contents', [
    'MISSING_EQUALS', 'TELEGRAM_BOT_TOKEN="unclosed', "TELEGRAM_BOT_TOKEN='unclosed",
    'TELEGRAM_BOT_TOKEN="value" junk', "TELEGRAM_BOT_TOKEN='value' junk",
    'TELEGRAM_BOT_TOKEN=x\nTELEGRAM_BOT_TOKEN=y',
    'TELEGRAM_BOT_TOKEN="line\\nbreak"', 'TELEGRAM_BOT_TOKEN=bad\x00value',
    'TELEGRAM_BOT_TOKEN="\\ud800"',
    'TELEGRAM_BOT_TOKEN="multiline\nvalue"', 'INVALID-KEY=value',
])
def test_malformed_dotenv_is_rejected_without_partial_environment_update(dotenv, contents):
    root, file, _ = dotenv
    file.write_text(contents)
    original = {'UNCHANGED': 'yes'}
    with pytest.raises(ValueError): config.telegram_environment(root, original)
    assert original == {'UNCHANGED': 'yes'}


def test_dotenv_failure_never_echoes_input_even_with_explicit_database_urls(dotenv):
    root, file, values = dotenv
    file.write_text('TELEGRAM_BOT_TOKEN="' + values['TELEGRAM_BOT_TOKEN'])
    env = {key: value for key, value in os.environ.items() if key not in config.TELEGRAM_KEYS}
    env.update({key: 'explicit-unused' for key in config.CONNECTIONS})
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/launcher_config.py'), str(root)],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0 and 'root .env unavailable/invalid' in result.stderr
    assert 'Traceback' not in result.stderr
    assert all(value not in result.stdout + result.stderr for value in values.values())


def test_helper_loads_dotenv_even_when_database_connections_are_already_exported(dotenv):
    root, _, _ = dotenv
    launcher = root / 'start.sh'
    launcher.write_text('#!' + sys.executable + '\nimport os\n'
                        'assert os.environ["TELEGRAM_BOT_USERNAME"]=="FloodPulsebot"\n'
                        'assert all(os.environ.get(k) for k in '
                        '["TELEGRAM_BOT_TOKEN","TELEGRAM_DESTINATIONS","TELEGRAM_WEBHOOK_SECRET"])\n'
                        'assert os.environ["DATABASE_URL"]=="explicit-existing"\nprint("ready")\n')
    launcher.chmod(0o700)
    env = {key: value for key, value in os.environ.items() if key not in config.TELEGRAM_KEYS}
    env.update({key: 'explicit-existing' for key in config.CONNECTIONS})
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/launcher_config.py'), str(root), '--check'],
                            cwd='/', env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout == 'ready\n'


def test_routing_keys_load_from_private_dotenv_and_are_stripped_from_vite(tmp_path, monkeypatch):
    # TEST FIXTURE ONLY — key-shaped strings, not credentials.
    file = tmp_path / '.env'
    file.write_text("OPENROUTESERVICE_API_KEY='test-ors'\nGOOGLE_MAPS_EMBED_API_KEY='AIza" + 'T' * 35 + "'\n")
    file.chmod(0o600)
    result = config.telegram_environment(tmp_path, {})
    assert result == {'OPENROUTESERVICE_API_KEY': 'test-ors', 'GOOGLE_MAPS_EMBED_API_KEY': 'AIza' + 'T' * 35}
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    processes_spec = importlib.util.spec_from_file_location('launcher_processes_under_test', ROOT / 'scripts/launcher_processes.py')
    launcher_processes = importlib.util.module_from_spec(processes_spec)
    processes_spec.loader.exec_module(launcher_processes)
    assert {'OPENROUTESERVICE_API_KEY', 'GOOGLE_MAPS_EMBED_API_KEY'} <= launcher_processes.SECRET_KEYS
