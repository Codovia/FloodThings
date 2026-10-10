from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app import location_database as dbmod
from app.locations import DATASET, LocationStore, LocationsUnavailable, get_store, matching, page
from app.main import app
from alembic.config import Config


def migrate():
    return Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))


def imported(db):
    dbmod.import_directory(db, DATASET)
    return dbmod.DatabaseLocationStore(db)


def test_clean_and_existing_schema_migration_and_safe_rollback(db):
    with db.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0003_admin_notifications'
        assert c.exec_driver_sql('SELECT note FROM unrelated_existing WHERE id=1').scalar() == 'preserve'
        names = set(c.exec_driver_sql("SELECT tablename FROM pg_tables WHERE schemaname='public'").scalars())
        assert set(dbmod.metadata.tables) <= names
    command.downgrade(migrate(), 'base')
    with db.connect() as c:
        assert c.exec_driver_sql('SELECT note FROM unrelated_existing').scalar() == 'preserve'
        assert c.exec_driver_sql("SELECT count(*) FROM pg_extension WHERE extname='postgis'").scalar() == 1
    command.upgrade(migrate(), 'head')


def test_postgis_required_and_transactional_ddl(db):
    # Before any rows are imported, remove the isolated test extension only.
    command.downgrade(migrate(), 'base')
    with db.begin() as c:
        c.exec_driver_sql('DROP EXTENSION postgis')
    try:
        with pytest.raises(RuntimeError, match='PostGIS is required'):
            command.upgrade(migrate(), 'head')
        with db.connect() as c:
            assert c.exec_driver_sql("SELECT to_regclass('location_directory_versions')").scalar() is None
            assert c.exec_driver_sql('SELECT note FROM unrelated_existing').scalar() == 'preserve'
    finally:
        with db.begin() as c:
            c.exec_driver_sql('CREATE EXTENSION postgis')
        command.upgrade(migrate(), 'head')


def test_import_idempotence_provenance_disabled_and_exact_reproduction(db):
    first = dbmod.import_directory(db, DATASET)
    with db.connect() as c:
        timestamp = c.execute(select(dbmod.versions.c.imported_at)).scalar()
    assert first == {'version': 'karnataka_location_directory_v2', 'status': 'imported', 'active': True, 'districts': 31, 'localities': 6, 'selectable': 5}
    assert dbmod.import_directory(db, DATASET)['status'] == 'already_imported'
    assert dbmod.DatabaseLocationStore(db).load() == LocationStore().load()
    with db.connect() as c:
        source = c.execute(select(dbmod.versions)).mappings().one()
        assert source['imported_at'] == timestamp
        assert source['manifest_sha256'] == hashlib.sha256((DATASET/'manifest.json').read_bytes()).hexdigest()
        assert source['source_manifest'] == json.loads((DATASET/'manifest.json').read_bytes())
        points = c.execute(text('SELECT id, latitude, longitude, ST_X(point), ST_Y(point), ST_SRID(point) FROM location_directory_localities WHERE selectable')).all()
        assert len(points) == 5 and all((p[2],p[1],4326) == (p[3],p[4],p[5]) for p in points)
        kaup = c.execute(select(dbmod.localities).where(dbmod.localities.c.id=='udupi-admin:municipality:kaup')).mappings().one()
        assert not kaup['selectable'] and kaup['point'] is None and kaup['record']['unavailable_reason']


def test_version_activation_preserves_v1(db):
    v1 = DATASET.parent/'karnataka_location_directory_v1'
    dbmod.import_directory(db,v1)
    assert dbmod.DatabaseLocationStore(db).load()==LocationStore(v1).load()
    dbmod.import_directory(db, DATASET, activate=False)
    assert dbmod.DatabaseLocationStore(db).load()['version'].endswith('_v1')
    dbmod.import_directory(db, DATASET)
    with db.connect() as c:
        assert dbmod.reconstruct(c,'karnataka_location_directory_v1') == LocationStore(v1).load()
    assert dbmod.DatabaseLocationStore(db).load()['coverage']['selectable_localities']==5


def test_failed_import_rolls_back_activation_and_rows(db,monkeypatch):
    v1 = DATASET.parent/'karnataka_location_directory_v1'
    dbmod.import_directory(db,v1)
    original=dbmod.reconstruct
    def fail(c,v):
        if v.endswith('_v2'):raise LocationsUnavailable('Injected pre-activation validation failure')
        return original(c,v)
    monkeypatch.setattr(dbmod,'reconstruct',fail)
    with pytest.raises(LocationsUnavailable):dbmod.import_directory(db,DATASET)
    with db.connect() as c:
        assert c.execute(select(dbmod.versions.c.version)).scalars().all()==['karnataka_location_directory_v1']
    assert dbmod.DatabaseLocationStore(db).load()==LocationStore(v1).load()


@pytest.mark.parametrize('change', ['duplicate','invalid_coordinate','conflicting_version'])
def test_invalid_sources_rejected_without_partial_import(db,change):
    imported(db)
    with TemporaryDirectory() as folder:
        p=Path(folder);d=deepcopy(LocationStore().load())
        if change=='duplicate':d['localities'].append(deepcopy(d['localities'][0]))
        elif change=='invalid_coordinate':d['localities'][0]['coordinates']['latitude']=95
        else:d['localities'][0]['aliases'].append('additional name not reviewed in this version')
        raw=json.dumps(d).encode();m=json.loads((DATASET/'manifest.json').read_bytes())
        m['files']['directory.json']={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        (p/'directory.json').write_bytes(raw);(p/'manifest.json').write_text(json.dumps(m))
        with pytest.raises(LocationsUnavailable):dbmod.import_directory(db,p)
    assert dbmod.DatabaseLocationStore(db).load()==LocationStore().load()


@pytest.mark.parametrize('statement',[
 "UPDATE location_directory_localities SET longitude=181 WHERE selectable",
 "UPDATE location_directory_localities SET point=ST_SetSRID(ST_MakePoint(13,74),4326) WHERE selectable",
 "UPDATE location_directory_localities SET point=ST_SetSRID(ST_MakePoint(74,13),3857) WHERE selectable",
 "UPDATE location_directory_localities SET district_id='nic:unknown'",
 "UPDATE location_directory_localities SET selectable=true WHERE NOT selectable",
 "INSERT INTO location_directory_active VALUES (2,'karnataka_location_directory_v2')",
 "UPDATE location_directory_identifiers SET identifier='osm:node:245620117'",
])
def test_database_constraints_reject_invalid_state(db,statement):
    imported(db)
    with pytest.raises(DBAPIError):
        with db.begin() as c:c.exec_driver_sql(statement)
    assert dbmod.DatabaseLocationStore(db).load()==LocationStore().load()


def test_missing_active_and_corruption_fail_explicitly(db):
    with pytest.raises(LocationsUnavailable,match='No active'):dbmod.DatabaseLocationStore(db).load()
    store=imported(db)
    with db.begin() as c:c.execute(update(dbmod.versions).values(content_sha256='0'*64))
    with pytest.raises(LocationsUnavailable,match='integrity'):store.load()


def test_read_only_application_role_and_api_contract(db):
    # Unique role lives only for this test; actual public API cannot mutate rows.
    import uuid
    role='fp_reader_'+uuid.uuid4().hex
    with db.begin() as c:
        c.exec_driver_sql(f'CREATE ROLE {role}')
        c.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO {role}')
        c.exec_driver_sql(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}')
    imported(db)
    with db.connect() as c:
        c.exec_driver_sql(f'SET ROLE {role}')
        assert c.execute(select(dbmod.active.c.version)).scalar().endswith('_v2')
        c.rollback()
    try:
        with pytest.raises(DBAPIError):
            with db.begin() as c:
                c.exec_driver_sql(f'SET ROLE {role}')
                c.execute(dbmod.active.delete())
        store=dbmod.DatabaseLocationStore(db)
        app.dependency_overrides[get_store]=lambda:store
        with TestClient(app) as api:
            d=LocationStore().load()
            assert api.get('/api/locations/districts').json()==page(matching(d['districts'],''),0,50,d)
            assert api.get('/api/locations/localities',params={'district_id':'nic:udupi.nic.in'}).json()['total']==5
            assert api.get('/api/locations/search',params={'q':'Mangalore'}).json()['items'][0]['id']=='osm:node:245612641'
            assert api.get('/api/locations/localities/osm:node:245623778').json()['name']=='Kundapur'
            assert api.get('/api/locations/localities/unknown').status_code==404
            assert api.get('/api/locations/localities',params={'district_id':'unknown'}).status_code==404
            assert api.get('/api/locations/search',params={'q':'  '}).status_code==422
    finally:
        app.dependency_overrides.pop(get_store,None)
        with db.begin() as c:
            c.exec_driver_sql(f'DROP OWNED BY {role}')
            c.exec_driver_sql(f'DROP ROLE {role}')


def test_clean_database_migration(db):
    command.downgrade(migrate(), 'base')
    with db.begin() as c:
        c.exec_driver_sql('DROP TABLE unrelated_existing')
    try:
        command.upgrade(migrate(), 'head')
        assert imported(db).load() == LocationStore().load()
    finally:
        with db.begin() as c:
            c.exec_driver_sql('CREATE TABLE unrelated_existing (id integer PRIMARY KEY, note text)')
            c.exec_driver_sql("INSERT INTO unrelated_existing VALUES (1, 'preserve')")


def test_concurrent_import_is_serialized_and_idempotent(db):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: dbmod.import_directory(db, DATASET), range(2)))
    assert sorted(r['status'] for r in results) == ['already_imported', 'imported']
    assert dbmod.DatabaseLocationStore(db).load() == LocationStore().load()
