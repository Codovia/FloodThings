"""Bring this laptop's FloodPulse database to the current migration and refresh the application role's grants.

Local maintenance only, run by the person in their own terminal. The current migrations only add tables; existing
rows are not changed. The connection is the same private maintenance connection ./scripts/setup-admin.sh uses (the
owner-only data/tmp/sprint6-db/admin-password file, or a hidden prompt); it is never printed or passed to the app.

  ./scripts/upgrade-database.sh --check   read-only: show the database version and whether an upgrade is needed
  ./scripts/upgrade-database.sh           upgrade, grant the application role, then verify as that role
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.location_database import database_engine
from app.mvp_database import check_app_connection, grant_app_role
from launcher_config import configured_environment
from setup_admin import SetupError, maintenance_url


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='Read-only: report the database version; change nothing')
    parser.add_argument('--maintenance-prompt', action='store_true', help='Ask privately for the maintenance connection instead of using the local file')
    args = parser.parse_args()
    if args.maintenance_prompt and not sys.stdin.isatty():
        sys.exit('FloodPulse: --maintenance-prompt needs an interactive terminal.')
    engines, previous = [], os.environ.get('LOCATION_DIRECTORY_ADMIN_URL')
    try:
        url = maintenance_url(ROOT, os.environ, args.maintenance_prompt)
        service = configured_environment(ROOT, os.environ) if not os.environ.get('SHELTER_DATABASE_URL') else dict(os.environ)
        role = make_url(service['SHELTER_DATABASE_URL']).username
        os.chdir(ROOT / 'backend')  # alembic.ini paths are relative to backend/
        config = Config('alembic.ini')
        head = ScriptDirectory.from_config(config).get_current_head()
        engine = database_engine(url); engines.append(engine)
        with engine.connect() as c:
            current = c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        print(f'Database version: {current}. Current version: {head}.')
        if args.check:
            print('Up to date.' if current == head else 'An upgrade is needed: run ./scripts/upgrade-database.sh (nothing was changed).')
            return 0
        if current != head:
            os.environ['LOCATION_DIRECTORY_ADMIN_URL'] = url  # read by alembic/env.py in this process only
            command.upgrade(config, 'head')
            print(f'Upgraded to {head}.')
        grant_app_role(engine, role)
        app = database_engine(service['SHELTER_DATABASE_URL']); engines.append(app)
        with app.connect() as c:
            result = check_app_connection(c)
        print(f"Application role can use all {result['tables_checked']} tables and cannot alter audit history. ./floodpulse.sh will start.")
        return 0
    except SetupError as error:
        sys.exit('FloodPulse: ' + str(error))
    except (SQLAlchemyError, ValueError, KeyError, OSError):
        # Never stringify database errors here: they can include connection details.
        sys.exit('FloodPulse: database upgrade or check failed; no connection details are shown. Is the database running (./floodpulse.sh --check)?')
    finally:
        for engine in engines:
            engine.dispose()
        if previous is None:
            os.environ.pop('LOCATION_DIRECTORY_ADMIN_URL', None)
        else:
            os.environ['LOCATION_DIRECTORY_ADMIN_URL'] = previous


if __name__ == '__main__':
    sys.exit(main())
