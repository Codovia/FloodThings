"""Local setup security: no network, no persistence, no echoed credentials."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import URL

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('admin_setup', SCRIPTS / 'setup_admin.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
SECRET = 'ISOLATED TEST ONLY password, never a credential'
def connection(role='postgres'):
    return URL.create('postgresql+psycopg', username=role, password=SECRET,
                      host='127.0.0.1', port=55436, database='floodpulse_directory').render_as_string(hide_password=False)


@pytest.mark.parametrize('change', [{'host':'example.com'}, {'host':'localhost'}, {'port':5432}, {'database':'other'}, {'password':''}, {'query':{'options':'-c role=postgres'}}])
def test_rejects_wrong_target_or_connection_overrides_without_secret_disclosure(change):
    value=setup.make_url(connection()).set(**change).render_as_string(hide_password=False)
    with pytest.raises(setup.SetupError) as e:setup.local_url(value)
    assert SECRET not in str(e.value) and value not in str(e.value)


def test_existing_local_secret_is_separate_from_service_connections(monkeypatch):
    monkeypatch.setattr(setup,'private_file',lambda *args:SECRET)
    result=setup.maintenance_url(Path('/unused'),{'DATABASE_URL':connection('reader'),'SHELTER_DATABASE_URL':connection('app')})
    assert setup.make_url(result).username=='postgres'
    assert setup.make_url(result).password==SECRET


def test_missing_secret_explains_private_prompt_without_falling_back_to_app_role(monkeypatch):
    def missing(*args):raise FileNotFoundError()
    monkeypatch.setattr(setup,'private_file',missing)
    with pytest.raises(setup.SetupError,match='--maintenance-prompt'):
        setup.maintenance_url(Path('/unused'),{'DATABASE_URL':connection('reader'),'SHELTER_DATABASE_URL':connection('app')})


def test_duplicate_username_aborts_before_reading_or_changing_password():
    engine=MagicMock();engine.connect.return_value.execution_options.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value='existing-id'
    calls=[]
    def ask(prompt):calls.append(prompt);return 'existing-admin'
    with pytest.raises(setup.SetupError,match='left unchanged'):setup.private_inputs(engine,False,ask)
    assert len(calls)==1 and not engine.begin.called


def test_password_mismatch_never_reaches_provisioning():
    engine=MagicMock();engine.connect.return_value.execution_options.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value=None
    values=iter(['chosen-admin',SECRET,'different test-only password'])
    with pytest.raises(setup.SetupError,match='Passwords differ'):setup.private_inputs(engine,False,lambda _:next(values))
    assert not engine.begin.called


def test_browser_receives_credentials_only_on_stdin_and_no_maintenance_environment(monkeypatch):
    monkeypatch.setenv('LOCATION_DIRECTORY_ADMIN_URL',connection())
    monkeypatch.setenv('DATABASE_URL',connection('reader'))
    monkeypatch.setenv('SHELTER_DATABASE_URL',connection('app'))
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','TEST ONLY NOT A TOKEN')
    def run(args,**kwargs):
        assert SECRET not in str(args)
        assert not any('DATABASE' in k or k.startswith('TELEGRAM_') or k=='LOCATION_DIRECTORY_ADMIN_URL' for k in kwargs['env'])
        assert SECRET in kwargs['input']
        return MagicMock(returncode=0,stdout='{"login":true,"shelter_management":true,"citizen_moderation":true,"alert_administration":true,"logout":true,"session_revoked":true}')
    monkeypatch.setattr(setup.subprocess,'run',run)
    assert all(setup.verify_browser('chosen-admin',SECRET,'test-id').values())


def test_partial_browser_result_cannot_claim_all_workspaces_passed(monkeypatch):
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**k:MagicMock(returncode=0,stdout='{"login":true,"logout":true}'))
    with pytest.raises(setup.SetupError,match='checks did not pass'):
        setup.verify_browser('chosen-admin',SECRET,'test-id')
