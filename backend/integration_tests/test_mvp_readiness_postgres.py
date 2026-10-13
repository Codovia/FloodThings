"""Forward-only upgrade and restricted role operations in UUID-isolated PostGIS."""
import secrets
import uuid
import pytest
import psycopg
from psycopg import sql
from sqlalchemy import text,inspect
from alembic import command
from conftest import migrate
from app.location_database import database_engine
from app.mvp_database import grant_app_role,check_app_connection,APP_PRIVILEGES


def test_forward_0003_0004_0005_preserves_sentinel_and_schema(isolated_database,monkeypatch):
    engine,url=isolated_database;monkeypatch.setenv('LOCATION_DIRECTORY_ADMIN_URL',url)
    command.upgrade(migrate(),'0003_admin_notifications')
    with engine.connect() as c:
        original=set(inspect(c).get_table_names())
        assert c.execute(text('SELECT note FROM unrelated_existing')).scalar_one()=='preserve'
    command.upgrade(migrate(),'0004_citizen_reports')
    with engine.connect() as c:
        assert original<=set(inspect(c).get_table_names())
        assert len(inspect(c).get_check_constraints('citizen_reports'))>=6
        assert {i['name'] for i in inspect(c).get_indexes('citizen_reports')}>= {'ix_citizen_report_position','ix_citizen_report_received'}
    command.upgrade(migrate(),'0005_telegram_subscriptions')
    command.upgrade(migrate(),'head')
    command.upgrade(migrate(),'head')
    with engine.connect() as c:
        assert set(APP_PRIVILEGES)<=set(inspect(c).get_table_names())
        assert c.execute(text('SELECT note FROM unrelated_existing')).scalar_one()=='preserve'
    # Only this disposable database is reset for other tests.
    command.downgrade(migrate(),'base')


@pytest.fixture
def restricted(db):
    role='mvp_app_'+uuid.uuid4().hex;password=secrets.token_urlsafe(32)
    admin=psycopg.connect(db.url.set(drivername='postgresql').render_as_string(hide_password=False),autocommit=True)
    admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
    engine=None
    try:
        grant_app_role(db,role)
        engine=database_engine(db.url.set(username=role,password=password).render_as_string(hide_password=False))
        yield engine,role
    finally:
        if engine:engine.dispose()
        admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)));admin.close()


def test_exact_service_grants_and_audit_write_protection(restricted):
    engine,role=restricted
    with engine.connect().execution_options(postgresql_readonly=True) as c:
        assert check_app_connection(c)['audit_mutation'] is False
        for table in APP_PRIVILEGES:
            assert c.execute(text('SELECT has_table_privilege(current_user,:table,\'SELECT\')'),{'table':table}).scalar_one()
        assert not c.execute(text("SELECT has_table_privilege(current_user,'shelter_admins','UPDATE')")).scalar_one()
        assert not c.execute(text("SELECT has_table_privilege(current_user,'emergency_shelters','DELETE')")).scalar_one()


def test_grant_helper_rejects_administrative_and_untrusted_role_names(db):
    for role in ['postgres','bad; DROP TABLE citizen_reports','missing_restricted_role']:
        with pytest.raises(ValueError):grant_app_role(db,role)
