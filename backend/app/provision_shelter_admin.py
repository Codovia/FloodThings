"""Explicit local maintenance command; no public registration or default password."""
import argparse
import getpass
import os
import re
import uuid
from sqlalchemy import select,update,delete
from .location_database import database_engine
from .shelter_schema import admins,sessions
from .shelter_security import HASHER


def provision(engine,username,password,reset=False):
    if not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}',username) or not 16<=len(password)<=128:
        raise ValueError('Use a valid username and a password of 16–128 characters')
    encoded=HASHER.hash(password)
    with engine.begin() as c:
        user=c.execute(select(admins).where(admins.c.username==username).with_for_update()).mappings().one_or_none()
        if user:
            if not reset:raise ValueError('Administrator already exists; use explicit --reset-password to rotate')
            c.execute(update(admins).where(admins.c.id==user['id']).values(password_hash=encoded,active=True))
            c.execute(delete(sessions).where(sessions.c.admin_id==user['id']))
            return user['id']
        identity=str(uuid.uuid4());c.execute(admins.insert().values(id=identity,username=username,password_hash=encoded,active=True));return identity


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--username',required=True);parser.add_argument('--reset-password',action='store_true');args=parser.parse_args()
    password=getpass.getpass('New administrator password: ')
    if password!=getpass.getpass('Confirm password: '):parser.error('Passwords differ')
    url=os.environ.get('LOCATION_DIRECTORY_ADMIN_URL')
    if not url:parser.error('Maintenance LOCATION_DIRECTORY_ADMIN_URL is required')
    engine=database_engine(url)
    try:
        provision(engine,args.username,password,args.reset_password)
        print('Administrator securely provisioned; password and hashes are not displayed.')
    except Exception:
        parser.exit(1,'Provisioning failed; check configuration and password policy. No credentials were displayed.\n')
    finally:engine.dispose()


if __name__=='__main__':main()
