"""Explicit opt-in real PostgreSQL tests in a newly created database only."""
import os
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from app.location_database import database_engine

BACKEND = Path(__file__).resolve().parents[1]


def migrate():
    return Config(str(BACKEND / 'alembic.ini'))


@pytest.fixture(scope='session')
def isolated_database():
    url = os.environ.get('LOCATION_DIRECTORY_ADMIN_URL')
    if not url:
        pytest.skip('Explicit administrator URL required for isolated PostgreSQL integration tests')
    parsed = make_url(url)
    # This suite creates/drops ONLY its UUID-named database, never the configured one.
    name = 'floodpulse_sprint6_test_' + uuid.uuid4().hex
    admin_url = parsed.set(drivername='postgresql').render_as_string(hide_password=False)
    test_url = parsed.set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
    engine = database_engine(test_url)
    try:
        with engine.begin() as c:
            c.exec_driver_sql('CREATE EXTENSION postgis')
            c.exec_driver_sql('CREATE TABLE unrelated_existing (id integer PRIMARY KEY, note text)')
            c.exec_driver_sql("INSERT INTO unrelated_existing VALUES (1, 'preserve')")
        yield engine, test_url
    finally:
        engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def db(isolated_database, monkeypatch):
    engine, url = isolated_database
    monkeypatch.setenv('LOCATION_DIRECTORY_ADMIN_URL', url)
    command.upgrade(migrate(), 'head')
    try:
        yield engine
    finally:
        command.downgrade(migrate(), 'base')
