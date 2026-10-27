"""Actual maintenance/provision checks confined to the UUID test database."""
import importlib.util
from pathlib import Path
import sys
import secrets
from sqlalchemy import select,text
import pytest
from app.provision_shelter_admin import provision
from app.shelter_schema import admins
from test_mvp_readiness_postgres import restricted

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('admin_setup_integration',SCRIPTS/'setup_admin.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


def test_setup_checks_existing_head_and_preserves_existing_admin_and_sentinel(db):
    result=setup.check_database(db,db.url.database)
    assert result['revision']=='0007_telegram_district_alerts'
    password=secrets.token_urlsafe(32);identity=provision(db,'chosen-fixture-admin',password)
    with db.connect() as c:before=dict(c.execute(select(admins).where(admins.c.id==identity)).mappings().one())
    with pytest.raises(setup.SetupError,match='left unchanged'):
        setup.private_inputs(db,False,lambda _: 'chosen-fixture-admin')
    with db.connect() as c:
        assert dict(c.execute(select(admins).where(admins.c.id==identity)).mappings().one())==before
        assert c.execute(text('SELECT note FROM unrelated_existing')).scalar_one()=='preserve'
    with pytest.raises(setup.SetupError,match='Wrong database'):setup.check_database(db)


def test_setup_refuses_application_role_insert_privilege(restricted):
    engine,role=restricted
    with pytest.raises(setup.SetupError,match='Maintenance SELECT/INSERT privileges'):
        setup.check_database(engine,engine.url.database)
