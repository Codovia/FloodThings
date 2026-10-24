"""Real PostgreSQL/PostGIS checks with labelled fixtures in a disposable database."""
import secrets
from copy import deepcopy
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text,update
from sqlalchemy.exc import DBAPIError
from app.main import app
from app.location_database import import_directory,districts,versions
from app.locations import DATASET
from app.shelters import ShelterStore,get_store
from app.shelter_schema import admins,sessions,shelters,audit
from app.shelter_security import digest
from app.provision_shelter_admin import provision

ORIGIN='https://floodpulse.test'


def fixture_record():
    return {'name':'DEMONSTRATION ONLY — test facility','address':'Isolated fixture, not an operational shelter','district_id':'nic:udupi.nic.in','capacity':10,'occupancy':2,'water':'yes','toilets':'unknown','latitude':13.5,'longitude':74.7,'contact':'PRIVATE TEST CONTACT','publish_contact':False,'notes':'PRIVATE TEST NOTES'}


def verified(body,revision):
    return {**body,'revision':revision,'status':'open','verification':{'authorization':True,'entrance':True,'usability':True,'capacity':True,'evidence':'Isolated fixture confirmation; not real verification'}}


@pytest.fixture
def api(db,monkeypatch):
    import_directory(db,DATASET);password=secrets.token_urlsafe(24);identity=provision(db,'test-admin',password)
    monkeypatch.setenv('SHELTER_PUBLIC_ORIGIN',ORIGIN);monkeypatch.setenv('SHELTER_COOKIE_SECURE','true');monkeypatch.setenv('SHELTER_DIRECTORY_MODE','demonstration')
    store=ShelterStore(db);app.dependency_overrides[get_store]=lambda:store
    try:
        with TestClient(app,base_url=ORIGIN) as client:yield client,db,store,password,identity
    finally:app.dependency_overrides.pop(get_store,None)


def sign_in(api):
    client,db,store,password,identity=api
    response=client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':password})
    assert response.status_code==200
    return {'Origin':ORIGIN,'X-CSRF-Token':response.json()['csrf_token']}


def make_pending(api,body=None):
    client=api[0];headers=sign_in(api);body=body or fixture_record()
    response=client.post('/api/admin/shelters',headers=headers,json=body);assert response.status_code==201
    return headers,body,response.json()


def test_login_cookie_server_side_hash_logout_and_revocation(api):
    client,db,store,password,identity=api;headers=sign_in(api)
    cookie=client.cookies.get('__Host-floodpulse_session')
    with db.connect() as c:
        user=c.execute(select(admins)).mappings().one();session=c.execute(select(sessions)).mappings().one()
        assert user['password_hash'].startswith('$scrypt$') and password not in user['password_hash']
        assert session['token_hash']==digest(cookie) and cookie not in str(dict(session))
    response=client.get('/api/admin/session');assert response.json()['csrf_token']==headers['X-CSRF-Token'] and response.headers['cache-control']=='no-store'
    assert client.post('/api/admin/logout',headers=headers).status_code==200
    client.cookies.set('__Host-floodpulse_session',cookie,domain='floodpulse.test',path='/')
    assert client.get('/api/admin/shelters').status_code==401
    response=client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':password})
    assert all(v.lower() in response.headers['set-cookie'].lower() for v in ['Secure','HttpOnly','SameSite=strict','Path=/'])
    assert client.get('/api/admin/session').status_code==200


def test_wrong_credentials_bounded_persistent_rate_limit_and_recovery(api,monkeypatch):
    client=api[0]
    for _ in range(5):
        assert client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':'incorrect'}).status_code==401
    assert client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':api[3]}).status_code==429
    from app.shelter_security import now
    later=now()+timedelta(minutes=16);monkeypatch.setattr('app.shelters.now',lambda:later)
    sign_in(api)


def test_login_requires_same_origin_and_custom_json_header(api):
    client=api[0];body={'username':'test-admin','password':api[3]}
    for headers in [{'Origin':ORIGIN},{'Origin':'https://evil.test','X-FloodPulse-Login':'1'},{'X-FloodPulse-Login':'1'}]:
        assert client.post('/api/admin/login',headers=headers,json=body).status_code==403
    assert client.post('/api/admin/register',json=body).status_code==404


def test_unauthorized_writes_and_csrf_rejection(api):
    client=api[0]
    assert client.get('/api/admin/shelters').status_code==401
    assert client.post('/api/admin/shelters',json=fixture_record()).status_code==401
    headers=sign_in(api)
    for h in [{'Origin':ORIGIN},{**headers,'Origin':'https://evil.test'},{**headers,'X-CSRF-Token':'wrong'}]:
        assert client.post('/api/admin/shelters',headers=h,json=fixture_record()).status_code==403
    assert client.post('/api/admin/logout').status_code==403


def test_pending_postgis_exact_coordinates_and_private_fields(api):
    client,db,*_=api;headers,body,row=make_pending(api)
    assert row['status']=='pending' and row['verified_at'] is None and not row['publicly_available']
    assert client.get('/api/shelters').json()['shelters']==[]
    with db.connect() as c:
        point=c.execute(text('SELECT ST_X(entrance),ST_Y(entrance),ST_SRID(entrance) FROM emergency_shelters')).one()
        assert tuple(point)==(74.7,13.5,4326)
        assert c.execute(select(audit.c.after)).scalar_one()['status']=='pending'
    assert row['demonstration'] is True


def test_creation_cannot_publish_even_with_confirmations(api):
    headers=sign_in(api);body=verified(fixture_record(),1);body.pop('revision')
    assert api[0].post('/api/admin/shelters',headers=headers,json=body).status_code==422
    assert api[0].get('/api/admin/shelters').json()['total']==0


@pytest.mark.parametrize('field',['authorization','entrance','usability','capacity'])
def test_missing_verification_cannot_open(api,field):
    headers,body,row=make_pending(api);payload=verified(body,row['revision']);payload['verification'][field]=False
    assert api[0].put('/api/admin/shelters/'+row['id'],headers=headers,json=payload).status_code==422
    assert api[0].get('/api/shelters').json()['shelters']==[]


def test_open_full_closed_reopen_audit_and_revision_conflict(api):
    client=api[0];headers,body,row=make_pending(api);url='/api/admin/shelters/'+row['id']
    payload=verified(body,row['revision']);opened=client.put(url,headers=headers,json=payload);assert opened.status_code==200
    assert client.put(url,headers=headers,json=payload).status_code==409
    destinations=client.get('/api/shelters?latitude=13.6&longitude=74.8').json();dest=destinations['shelters'][0]
    assert dest['available_capacity']==8 and dest['straight_line_km']>0 and dest['contact'] is None and 'notes' not in dest
    from urllib.parse import urlsplit,parse_qs
    assert parse_qs(urlsplit(dest['directions_url']).query)['destination']==['13.5,74.7']
    current=opened.json()
    for status,occupancy in [('full',10),('closed',2),('open',2)]:
        payload={**verified(body,current['revision']),'status':status,'occupancy':occupancy};response=client.put(url,headers=headers,json=payload);assert response.status_code==200;current=response.json()
        assert len(client.get('/api/shelters').json()['shelters'])==(1 if status=='open' else 0)
    events=client.get(url+'/audit').json()['events'];assert len(events)==5
    assert [e['after']['status'] for e in events]==['pending','open','full','closed','open']
    assert all(e['admin_id']==api[4] for e in events) and events[2]['before']['occupancy']==2 and events[2]['after']['occupancy']==10


def test_entrance_unknown_district_capacity_validation(api):
    client=api[0];headers=sign_in(api)
    for changes in [{'latitude':91},{'longitude':181},{'latitude':None},{'district_id':'not-verified'},{'occupancy':11},{'capacity':0},{'name':' '}]:
        assert client.post('/api/admin/shelters',headers=headers,json={**fixture_record(),**changes}).status_code==422
    assert client.get('/api/admin/shelters').json()['total']==0
    assert client.get('/api/shelters?latitude=90.1&longitude=74').status_code==422
    assert client.get('/api/shelters?latitude=13').status_code==422
    assert client.get('/api/shelters?limit=101').status_code==422
    assert client.get('/api/admin/shelters/00000000-0000-0000-0000-000000000000/audit').status_code==404


def test_transaction_rolls_back_shelter_when_audit_fails(api):
    client,db,*_=api;headers=sign_in(api)
    with db.begin() as c:c.exec_driver_sql("ALTER TABLE shelter_audit ADD CONSTRAINT injected_failure CHECK (action <> 'create')")
    assert client.post('/api/admin/shelters',headers=headers,json=fixture_record()).status_code==503
    with db.connect() as c:
        assert c.exec_driver_sql('SELECT count(*) FROM emergency_shelters').scalar()==0
        assert c.exec_driver_sql('SELECT count(*) FROM shelter_audit').scalar()==0
        assert c.execute(select(func_count:=__import__('sqlalchemy').func.count()).select_from(districts)).scalar()==31


def test_database_constraints_reject_bypasses_and_preserve_record(api):
    headers,body,row=make_pending(api);db=api[1]
    for statement in ["UPDATE emergency_shelters SET occupancy=capacity+1","UPDATE emergency_shelters SET status='open'","UPDATE emergency_shelters SET entrance=ST_SetSRID(ST_MakePoint(13.5,74.7),4326)","UPDATE emergency_shelters SET entrance=ST_SetSRID(ST_MakePoint(74.7,13.5),3857)"]:
        with pytest.raises(DBAPIError):
            with db.begin() as c:c.exec_driver_sql(statement)
    assert api[0].get('/api/admin/shelters').json()['shelters'][0]['status']=='pending'


def test_expired_verification_and_demo_records_never_become_live_destinations(api,monkeypatch):
    headers,body,row=make_pending(api);payload=verified(body,row['revision']);api[0].put('/api/admin/shelters/'+row['id'],headers=headers,json=payload)
    assert len(api[0].get('/api/shelters').json()['shelters'])==1
    monkeypatch.setenv('SHELTER_DIRECTORY_MODE','live');assert api[0].get('/api/shelters').json()['shelters']==[]
    monkeypatch.setenv('SHELTER_DIRECTORY_MODE','demonstration')
    from app.shelter_security import now
    monkeypatch.setattr('app.shelters.now',lambda:now()+timedelta(hours=25))
    assert api[0].get('/api/shelters').json()['shelters']==[]


def test_expired_disabled_sessions_password_reset_and_no_default_password(api,monkeypatch):
    client,db,store,password,identity=api;sign_in(api)
    new_password=secrets.token_urlsafe(24);provision(db,'test-admin',new_password,reset=True)
    assert client.get('/api/admin/session').status_code==401
    with pytest.raises(ValueError):provision(db,'test-admin',new_password)
    with pytest.raises(ValueError):provision(db,'other-admin','short')
    with db.begin() as c:c.execute(update(admins).where(admins.c.id==identity).values(active=False))
    assert client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':new_password}).status_code==401
    with db.begin() as c:c.execute(update(admins).where(admins.c.id==identity).values(active=True))
    response=client.post('/api/admin/login',headers={'Origin':ORIGIN,'X-FloodPulse-Login':'1'},json={'username':'test-admin','password':new_password});assert response.status_code==200
    from app.shelter_security import now
    monkeypatch.setattr('app.shelters.now',lambda:now()+timedelta(minutes=31))
    assert client.get('/api/admin/session').status_code==401


def test_contact_publication_and_public_reads_do_not_write(api):
    headers,body,row=make_pending(api);payload=verified(body,row['revision']);payload['publish_contact']=True
    api[0].put('/api/admin/shelters/'+row['id'],headers=headers,json=payload)
    with api[1].connect() as c:before=c.exec_driver_sql('SELECT count(*) FROM shelter_audit').scalar()
    r=api[0].get('/api/shelters').json()['shelters'][0];assert r['contact']=='PRIVATE TEST CONTACT' and r['straight_line_km'] is None
    with api[1].connect() as c:assert c.exec_driver_sql('SELECT count(*) FROM shelter_audit').scalar()==before
    assert api[0].post('/api/shelters',json=payload).status_code==405


def test_actual_least_privilege_role_supports_sessions_and_blocks_extra_writes(api):
    import uuid
    import psycopg
    from psycopg import sql
    from app.location_database import database_engine
    db=api[1];name='shelter_test_'+uuid.uuid4().hex;password=secrets.token_urlsafe(24)
    admin_url=db.url.set(drivername='postgresql').render_as_string(hide_password=False)
    connection=psycopg.connect(admin_url,autocommit=True);limited=None
    try:
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
        for query in [sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(db.url.database),sql.Identifier(name)),sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(name)),sql.SQL('GRANT SELECT ON location_directory_districts,location_directory_active,shelter_admins TO {}').format(sql.Identifier(name)),sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON shelter_sessions,shelter_login_limits TO {}').format(sql.Identifier(name)),sql.SQL('GRANT SELECT,INSERT,UPDATE ON emergency_shelters TO {}').format(sql.Identifier(name)),sql.SQL('GRANT SELECT,INSERT ON shelter_audit TO {}').format(sql.Identifier(name))]:connection.execute(query)
        limited=database_engine(db.url.set(username=name,password=password).render_as_string(hide_password=False))
        store=ShelterStore(limited);token,actor=store.login('test-admin',api[3],'isolated-test-peer')
        assert store.session(token)==actor
        row=store.save(__import__('app.shelters',fromlist=['ShelterInput']).ShelterInput(**fixture_record()),actor)
        store.save(__import__('app.shelters',fromlist=['ShelterInput']).ShelterInput(**verified(fixture_record(),row['revision'])),actor,row['id'])
        assert len(store.rows(public=True)['shelters'])==1 and len(store.history(row['id'])['events'])==2
        for statement in ['UPDATE shelter_admins SET active=false','DELETE FROM shelter_audit','UPDATE location_directory_districts SET name=name','DELETE FROM emergency_shelters']:
            with pytest.raises(DBAPIError):
                with limited.begin() as c:c.exec_driver_sql(statement)
        store.logout(token);assert store.session(token) is None
    finally:
        if limited:limited.dispose()
        connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(name)))
        connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)));connection.close()
