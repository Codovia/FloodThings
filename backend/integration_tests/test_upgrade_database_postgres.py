"""scripts/upgrade_database.py on a disposable database: 0006 -> head, grants, verification; existing rows kept."""
import importlib.util
import secrets
import sys
import uuid
from pathlib import Path

from alembic import command
from psycopg import sql
import psycopg
from sqlalchemy import select, text

from conftest import migrate
from app.shelter_security import now
from app.subscription_schema import subscriptions

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('upgrade_database', ROOT / 'scripts/upgrade_database.py')
upgrade = importlib.util.module_from_spec(spec); spec.loader.exec_module(upgrade)


def test_upgrade_from_0006_grants_the_application_role_and_keeps_existing_rows(db, monkeypatch, capsys):
    command.downgrade(migrate(), '0006_report_position_provenance')
    with db.begin() as c:
        c.execute(subscriptions.insert().values(subscriber_key='k' * 64, active=True, command_at=now(), received_at=now(), update_id=1, consent_version='TEST'))
    role, password = 'upgrade_test_' + uuid.uuid4().hex[:12], secrets.token_urlsafe(24)
    admin = db.url.set(drivername='postgresql').render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
    url = db.url.render_as_string(hide_password=False)
    app_url = db.url.set(username=role, password=password).render_as_string(hide_password=False)
    monkeypatch.setattr(upgrade, 'maintenance_url', lambda root, environment, prompt: url)
    monkeypatch.setenv('SHELTER_DATABASE_URL', app_url)
    monkeypatch.setattr(sys, 'argv', ['upgrade_database.py', '--check'])
    assert upgrade.main() == 0 and 'An upgrade is needed' in capsys.readouterr().out
    with db.connect() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0006_report_position_provenance'
    monkeypatch.setattr(sys, 'argv', ['upgrade_database.py'])
    assert upgrade.main() == 0
    out = capsys.readouterr().out
    assert 'Upgraded to 0007_telegram_district_alerts' in out and 'cannot alter audit history' in out and password not in out
    with db.connect() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0007_telegram_district_alerts'
        assert c.execute(select(subscriptions.c.consent_version)).scalar_one() == 'TEST'
        assert c.execute(text("SELECT has_table_privilege(:r,'telegram_district_subscribers','DELETE')"), {'r': role}).scalar_one()
        assert not c.execute(text("SELECT has_table_privilege(:r,'telegram_district_audit','UPDATE')"), {'r': role}).scalar_one()
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(sql.SQL('REASSIGN OWNED BY {} TO CURRENT_USER').format(sql.Identifier(role)))
        a.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
