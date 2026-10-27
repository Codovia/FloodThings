"""Explicit maintenance grants and read-only service readiness; no credentials logged."""
import argparse
import os
import re
from sqlalchemy import inspect, text
from .location_database import database_engine

APP_PRIVILEGES = {
    'location_directory_districts': ('SELECT',), 'location_directory_active': ('SELECT',),
    'shelter_admins': ('SELECT',),
    'shelter_sessions': ('SELECT','INSERT','UPDATE','DELETE'),
    'shelter_login_limits': ('SELECT','INSERT','UPDATE','DELETE'),
    'emergency_shelters': ('SELECT','INSERT','UPDATE'), 'shelter_audit': ('SELECT','INSERT'),
    'admin_notifications': ('SELECT','INSERT','UPDATE'),
    'citizen_reports': ('SELECT','INSERT','UPDATE'),
    'citizen_report_images': ('SELECT','INSERT','DELETE'),
    'citizen_report_positions': ('SELECT','INSERT','UPDATE'),
    'citizen_report_audit': ('SELECT','INSERT'),
    'telegram_subscriptions': ('SELECT','INSERT','UPDATE'),
    'telegram_subscription_audit': ('SELECT','INSERT'),
    'telegram_district_subscribers': ('SELECT','INSERT','UPDATE','DELETE'),
    'telegram_district_subscriptions': ('SELECT','INSERT','DELETE'),
    'telegram_district_audit': ('SELECT','INSERT'),
    'district_notifications': ('SELECT','INSERT','UPDATE'),
    'telegram_district_deliveries': ('SELECT','INSERT'),
}


def grant_app_role(engine, role):
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,62}', role):
        raise ValueError('Supply a valid, existing restricted application role')
    with engine.begin() as c:
        target=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolcanlogin FROM pg_roles WHERE rolname=:role'),{'role':role}).one_or_none()
        if not target or any(target[:3]) or not target.rolcanlogin:
            raise ValueError('Application role must exist, allow login and have no administrative capabilities')
        owns=c.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=:role"),{'role':role}).scalar_one()
        memberships=c.execute(text('SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:role'),{'role':role}).scalar_one()
        if owns or memberships:
            raise ValueError('Application role must not own tables or inherit other roles')
        available=set(inspect(c).get_table_names())
        if not set(APP_PRIVILEGES)<=available:
            raise ValueError('Run the verified forward migration before granting privileges')
        quote=c.dialect.identifier_preparer.quote
        database=c.execute(text('SELECT current_database()')).scalar_one()
        c.exec_driver_sql(f'GRANT CONNECT ON DATABASE {quote(database)} TO {quote(role)}')
        c.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO {quote(role)}')
        for table,privileges in APP_PRIVILEGES.items():
            c.exec_driver_sql(f'GRANT {", ".join(privileges)} ON {quote(table)} TO {quote(role)}')


def check_app_connection(connection):
    available=set(inspect(connection).get_table_names())
    missing=sorted(set(APP_PRIVILEGES)-available)
    if missing:raise ValueError('Missing MVP tables: '+', '.join(missing))
    for table,privileges in APP_PRIVILEGES.items():
        for privilege in privileges:
            if not connection.execute(text('SELECT has_table_privilege(current_user,:table,:privilege)'),{'table':table,'privilege':privilege}).scalar_one():
                raise ValueError('Missing '+privilege+' privilege on '+table)
    for table in ('shelter_audit','citizen_report_audit','telegram_subscription_audit','telegram_district_audit','telegram_district_deliveries'):
        for privilege in ('UPDATE','DELETE'):
            if connection.execute(text('SELECT has_table_privilege(current_user,:table,:privilege)'),{'table':table,'privilege':privilege}).scalar_one():
                raise ValueError('Application role must not alter audit history')
    return {'tables_checked':len(APP_PRIVILEGES),'audit_mutation':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grant-to', help='Explicitly grant the finite MVP privileges through the maintenance connection')
    args=parser.parse_args()
    key='LOCATION_DIRECTORY_ADMIN_URL' if args.grant_to else 'SHELTER_DATABASE_URL'
    if not os.environ.get(key):parser.error('Configure '+key+' privately; no default connection is used')
    engine=database_engine(os.environ[key])
    try:
        if args.grant_to:
            grant_app_role(engine,args.grant_to);print('MVP table grants applied to the designated restricted role; no account or password created.')
        else:
            with engine.connect().execution_options(postgresql_readonly=True) as c:check_app_connection(c)
            print('MVP service tables and least-privilege checks passed; no data changed.')
    except Exception:
        parser.exit(1,'MVP database readiness failed; check forward migrations and documented restricted-role grants. No credentials were displayed.\n')
    finally:engine.dispose()


if __name__=='__main__':main()
