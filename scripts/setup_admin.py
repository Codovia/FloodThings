"""Private interactive provisioning for the existing local FloodPulse database."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from sqlalchemy import select, text
from sqlalchemy.engine import make_url, URL
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.location_database import database_engine
from app.provision_shelter_admin import provision
from app.shelter_schema import admins
from launcher_config import configured_environment, private_file

DATABASE = 'floodpulse_directory'
TARGET = ('127.0.0.1', 55436, DATABASE)
ADMIN_SECRET = Path('data/tmp/sprint6-db/admin-password')
ORIGIN = 'http://127.0.0.1:14180'


class SetupError(ValueError):
    pass


def local_url(value):
    try:
        parsed = make_url(value)
        if (parsed.drivername not in ('postgresql', 'postgresql+psycopg')
                or (parsed.host, parsed.port, parsed.database) != TARGET
                or not parsed.username or not parsed.password or parsed.query):
            raise ValueError()
        return parsed.set(drivername='postgresql+psycopg')
    except Exception:
        raise SetupError('Expected the existing authenticated local database on 127.0.0.1:55436/floodpulse_directory. Connection values were not displayed.') from None


def maintenance_url(root, environment, prompt=False, ask=getpass.getpass):
    # Service configuration establishes the same target; never reuse its credentials.
    try:
        service = dict(environment)
        if not all(service.get(key) for key in ('DATABASE_URL', 'SHELTER_DATABASE_URL')):
            service = configured_environment(root, environment)
        for key in ('DATABASE_URL', 'SHELTER_DATABASE_URL'):
            local_url(service[key])
    except Exception:
        raise SetupError('Private application connections unavailable. Configure the existing data/tmp/launcher/config.json profile; no database was created or changed.') from None
    supplied = environment.get('LOCATION_DIRECTORY_ADMIN_URL')
    if prompt:
        supplied = ask('Maintenance connection URL (hidden, used only here): ')
    if supplied:
        return local_url(supplied).render_as_string(hide_password=False)
    try:
        password = private_file(root / ADMIN_SECRET, 4096).strip()
        if not password or any(c in password for c in '\n\r\x00'):
            raise ValueError()
    except Exception:
        raise SetupError('Maintenance connection missing: the existing owner-only data/tmp/sprint6-db/admin-password file is unavailable/invalid. Run ./scripts/setup-admin.sh --maintenance-prompt and privately enter an authorized postgresql+psycopg connection URL for this SAME database. Do not paste it into source, chat, shell history or the web API environment.') from None
    return URL.create('postgresql+psycopg', username='postgres', password=password,
                      host=TARGET[0], port=TARGET[1], database=TARGET[2]).render_as_string(hide_password=False)


def check_database(engine, expected_database=DATABASE):
    with engine.connect().execution_options(postgresql_readonly=True) as c:
        if c.execute(text('SELECT current_database()')).scalar_one() != expected_database:
            raise SetupError('Wrong database; no account was created.')
        for privilege in ('SELECT', 'INSERT'):
            if not c.execute(text("SELECT has_table_privilege(current_user,'shelter_admins',:privilege)"), {'privilege': privilege}).scalar_one():
                raise SetupError('Maintenance SELECT/INSERT privileges on shelter_admins are required. Reader/application credentials cannot provision staff. Use --maintenance-prompt with an authorized maintenance connection.')
        head = ScriptDirectory.from_config(Config(str(ROOT / 'backend/alembic.ini'))).get_current_head()
        if c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() != head:
            raise SetupError('Database is not at the current verified migration head. Use the separate backed-up migration procedure; setup does not migrate.')
        return {'database': expected_database, 'revision': head,
                'active_administrators': c.execute(select(text('count(*)')).select_from(admins).where(admins.c.active)).scalar_one()}


def private_inputs(engine, verify_only, ask=getpass.getpass):
    username = ask('Administrator username (hidden, 3–64 lowercase characters): ').strip()
    if not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}', username):
        raise SetupError('Username must start with a lowercase letter; use 3–64 lowercase letters, digits, dots, underscores or hyphens.')
    with engine.connect().execution_options(postgresql_readonly=True) as c:
        existing = c.execute(select(admins.c.id).where(admins.c.username == username)).scalar_one_or_none()
    if verify_only and not existing:
        raise SetupError('This username does not exist. Run setup without --verify-only to create your chosen account.')
    if not verify_only and existing:
        raise SetupError('This account already exists and was left unchanged. Use ./scripts/setup-admin.sh --verify-only to test login; this command never resets accounts.')
    password = ask('Administrator password (hidden, 16–128 characters): ')
    if not 16 <= len(password) <= 128:
        raise SetupError('Password must contain 16–128 characters; nothing was saved.')
    if not verify_only and password != ask('Confirm administrator password (hidden): '):
        raise SetupError('Passwords differ; no account was created.')
    return username, password, existing


def verify_browser(username, password, identity):
    # No maintenance/service/bot credentials reach the browser child, let alone API.
    environment = {key: value for key, value in os.environ.items()
                   if 'DATABASE' not in key and not key.startswith(('TELEGRAM_', 'PG'))
                   and key not in ('LOCATION_DIRECTORY_ADMIN_URL', 'FLOODPULSE_REPORT_TEST_PASSWORD')}
    result = subprocess.run(['node', str(ROOT / 'scripts/verify_admin_login.cjs')],
                            input=json.dumps({'username': username, 'password': password,
                                              'identity': identity, 'origin': ORIGIN}),
                            text=True, capture_output=True, env=environment, timeout=60)
    if result.returncode:
        raise SetupError('Browser verification did not pass. Account credentials were not changed. Check your chosen credentials and start current code with ./start.sh, then run ./scripts/setup-admin.sh --verify-only. No browser logs or credentials were displayed.')
    checks = json.loads(result.stdout)
    if not all(checks.get(key) is True for key in ('login','shelter_management','citizen_moderation','alert_administration','logout','session_revoked')):
        raise SetupError('Browser login/logout checks did not pass; no success is claimed.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only connection, schema and maintenance privilege check')
    parser.add_argument('--verify-only', action='store_true', help='Privately test an existing account through /admin without changing its password')
    parser.add_argument('--maintenance-prompt', action='store_true', help='Privately prompt for an authorized connection when the existing local secret is unavailable')
    args = parser.parse_args()
    if (not args.check or args.maintenance_prompt) and not sys.stdin.isatty():
        parser.exit(1, 'Use your local terminal for hidden credential prompts; redirected input is refused. No credentials were read.\n')
    engine = None
    created = False
    try:
        url = maintenance_url(ROOT, os.environ, args.maintenance_prompt)
        engine = database_engine(url)
        info = check_database(engine)
        print(f"Verified existing {info['database']} at {info['revision']}; maintenance SELECT/INSERT available. Active administrators: {info['active_administrators']}.")
        if args.check:
            print('Read-only check complete. No administrator, grant, migration or database was changed.')
            return 0
        username, password, identity = private_inputs(engine, args.verify_only)
        if not args.verify_only:
            identity = provision(engine, username, password)  # Existing hashing/transaction; reset=False.
            created = True
            print('Administrator created securely in the existing database. Existing accounts and permissions are unchanged.')
        engine.dispose(); engine = None; url = None
        checks = verify_browser(username, password, identity)
        password = None
        folder = ROOT / 'data/tmp/admin_setup'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        receipt = folder / 'verification.json'
        record = {'at': datetime.now(timezone.utc).isoformat(), 'account_created': created,
                  'database': DATABASE, 'revision': info['revision'], 'origin': ORIGIN, **checks}
        # No username, password, URL credentials, cookie or CSRF token in the receipt.
        with os.fdopen(os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), 'w') as f:
            json.dump(record, f, indent=2)
        print('Real /admin browser checks passed: login, shelter management, citizen moderation, alert administration, logout and session revocation.')
        print('Open http://127.0.0.1:14180/admin and sign in with your chosen credentials. No plaintext credentials were written to files or logs.')
        return 0
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print('Setup cancelled; no password was displayed or saved.', file=sys.stderr)
    except Exception:
        print('Setup failed. Check the local database/maintenance connection and current web application. No credentials or exception details were displayed.', file=sys.stderr)
    finally:
        if engine:
            engine.dispose()
    if created:
        print('Account creation DID succeed; browser verification did not. Do not repeat account creation or reset it. Use --verify-only after starting current application code.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
