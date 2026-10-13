"""Run real application/browser checks in a disposable, labelled PostGIS database.

Requires an explicit LOCATION_DIRECTORY_ADMIN_URL maintenance connection. Creates
and drops only its own UUID database and roles; never seeds the configured DB.
The application receives restricted service connections, never maintenance access.
"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.location_database import database_engine, import_directory
from app.locations import DATASET
from app.mvp_database import grant_app_role, check_app_connection
from app.provision_shelter_admin import provision


def main():
    os.umask(0o077)  # Browser screenshots/exports and temporary output stay owner-only.
    if not os.environ.get('LOCATION_DIRECTORY_ADMIN_URL'):
        sys.exit('Explicit private LOCATION_DIRECTORY_ADMIN_URL required; no default database is used.')
    parsed = make_url(os.environ['LOCATION_DIRECTORY_ADMIN_URL'])
    maintenance = parsed.set(drivername='postgresql').render_as_string(hide_password=False)
    suffix = uuid.uuid4().hex
    name = 'floodpulse_mvp_demo_' + suffix
    app_role, reader_role = 'mvp_app_' + suffix, 'mvp_reader_' + suffix
    passwords = {role: secrets.token_urlsafe(32) for role in (app_role, reader_role)}
    admin_password = secrets.token_urlsafe(32)
    engine = None
    created_roles = []
    with psycopg.connect(maintenance, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        try:
            demo_url = parsed.set(database=name).render_as_string(hide_password=False)
            engine = database_engine(demo_url)
            with engine.begin() as c:
                c.exec_driver_sql('CREATE EXTENSION postgis')
            os.environ['LOCATION_DIRECTORY_ADMIN_URL'] = demo_url
            command.upgrade(Config(str(ROOT / 'backend/alembic.ini')), 'head')
            import_directory(engine, DATASET)
            provision(engine, 'test-report-admin', admin_password)
            for role, password in passwords.items():
                admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
                created_roles.append(role)
            grant_app_role(engine, app_role)
            with engine.begin() as c:
                c.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{name}" TO "{reader_role}"')
                c.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{reader_role}"')
                for table in ('versions', 'districts', 'localities', 'identifiers', 'active'):
                    c.exec_driver_sql(f'GRANT SELECT ON location_directory_{table} TO "{reader_role}"')
            app_url = parsed.set(database=name, username=app_role, password=passwords[app_role]).render_as_string(hide_password=False)
            reader_url = parsed.set(database=name, username=reader_role, password=passwords[reader_role]).render_as_string(hide_password=False)
            service = database_engine(app_url)
            with service.connect().execution_options(postgresql_readonly=True) as c:
                check_app_connection(c)
            service.dispose()
            env = {key: value for key, value in os.environ.items()
                   if key not in ('LOCATION_DIRECTORY_ADMIN_URL', 'DATABASE_URL', 'SHELTER_DATABASE_URL')
                   and not key.startswith('TELEGRAM_')}
            env.update(DATABASE_URL=reader_url, SHELTER_DATABASE_URL=app_url,
                       SHELTER_DIRECTORY_MODE='demonstration', FLOODPULSE_REPORT_TEST_PASSWORD=admin_password)
            tests = sys.argv[1:] or ['tests/mvp-e2e.spec.js', 'tests/reports.spec.js']
            return subprocess.call(['npx', 'playwright', 'test', *tests], cwd=ROOT / 'frontend', env=env)
        finally:
            if engine:
                engine.dispose()
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            for role in created_roles:
                admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


if __name__ == '__main__':
    raise SystemExit(main())
