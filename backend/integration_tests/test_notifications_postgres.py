"""Authenticated notification transactions in UUID-isolated PostgreSQL only."""
import json
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi import HTTPException
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError, OperationalError
from app.main import app
from app.notifications import NotificationStore, get_notifications, DraftInput, ApprovalInput
from app.notification_schema import notifications
from app.telegram_delivery import get_sender, DeliveryResult
from test_shelter_postgres import api, sign_in, fixture_record, verified

TOKEN = '123456:' + 'ISOLATED_ONLY_TOKEN_' * 2


class FakeSender:
    def __init__(self): self.calls=[]; self.result=DeliveryResult('accepted','telegram_accepted',200,telegram_message_id=19)
    def send(self, config, destination, message):
        self.calls.append((destination.id, message)); return self.result


@pytest.fixture
def notice(api,monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('TELEGRAM_DESTINATIONS', json.dumps({'test':{'label':'ISOLATED PRIVATE TEST','chat_id':'123','test_only':True}}))
    store=NotificationStore(api[1]);sender=FakeSender()
    app.dependency_overrides[get_notifications]=lambda:store
    app.dependency_overrides[get_sender]=lambda:sender
    try: yield api,store,sender
    finally:
        app.dependency_overrides.pop(get_notifications,None);app.dependency_overrides.pop(get_sender,None)


def body(**extra):
    return {'request_id':str(uuid.uuid4()),'destination_id':'test','kind':'informational','message':'ISOLATED DEMONSTRATION ONLY — no operational notice',**extra}


def preview(notice, **extra):
    api,store,sender=notice;headers=sign_in(api)
    response=api[0].post('/api/admin/notifications',headers=headers,json=body(**extra))
    assert response.status_code==201,response.text
    return headers,response.json()


def approve(client,headers,row,**extra):
    return client.post('/api/admin/notifications/'+row['id']+'/send',headers=headers,json={'approve':True,'content_sha256':row['content_sha256'],**extra})


def test_authentication_csrf_and_private_configuration(notice):
    api,store,sender=notice;client=api[0]
    for path in ['/api/admin/notifications','/api/admin/notifications/options']:
        assert client.get(path).status_code==401
    assert client.post('/api/admin/notifications',json=body()).status_code==401
    headers=sign_in(api)
    for bad in [{},{'Origin':'https://other.test','X-CSRF-Token':headers['X-CSRF-Token']},{'Origin':headers['Origin']}]:
        assert client.post('/api/admin/notifications',headers=bad,json=body()).status_code==403
    data=client.get('/api/admin/notifications/options').json()
    assert data['destinations']==[{'id':'test','label':'ISOLATED PRIVATE TEST','test_only':True}]
    assert TOKEN not in json.dumps(data) and 'chat_id' not in json.dumps(data)
    draft=client.post('/api/admin/notifications',headers=headers,json=body()).json()
    assert approve(client,{},draft).status_code==403
    assert approve(client,{**headers,'X-CSRF-Token':'wrong'},draft).status_code==403
    assert store.history()['notifications'][0]['status']=='draft'
    assert not sender.calls


def test_exact_preview_idempotency_approval_audit_and_no_duplicate_delivery(notice):
    api,store,sender=notice;client=api[0];headers=sign_in(api);payload=body()
    draft=client.post('/api/admin/notifications',headers=headers,json=payload).json()
    assert draft['status']=='draft' and not sender.calls
    assert client.post('/api/admin/notifications',headers=headers,json=payload).json()['id']==draft['id']
    assert client.post('/api/admin/notifications',headers=headers,json={**payload,'message':'changed'}).status_code==409
    assert approve(client,headers,draft,approve=False).status_code==422
    assert approve(client,headers,draft,content_sha256='a'*64).status_code==409
    accepted=approve(client,headers,draft).json()
    assert accepted['status']=='accepted' and accepted['confirmed_by']==api[4]
    assert accepted['confirmed_at'] and accepted['attempted_at'] and accepted['completed_at']
    assert sender.calls==[('test',draft['text'])]
    assert approve(client,headers,draft).json()==accepted and len(sender.calls)==1
    history=client.get('/api/admin/notifications?limit=1').json()
    assert history['total']==1 and history['notifications']==[accepted]
    assert TOKEN not in json.dumps(history) and 'chat_id' not in json.dumps(history)
    assert client.get('/api/admin/notifications?limit=101').status_code==422
    with api[1].connect() as c:
        row=c.execute(select(notifications)).mappings().one()
        assert row['status']=='accepted' and row['telegram_message_id']==19 and row['text']==draft['text']
        assert row['destination_fingerprint'] and TOKEN not in str(dict(row))


@pytest.mark.parametrize('result', [DeliveryResult('rejected','telegram_rejected',403,telegram_error_code=403), DeliveryResult('delivery_unknown','transport_uncertain')])
def test_failure_is_audited_not_retried(notice,result):
    api,store,sender=notice;sender.result=result;headers,row=preview(notice)
    response=approve(api[0],headers,row)
    assert response.status_code==200 and response.json()['status']==result.status
    assert approve(api[0],headers,row).json()['status']==result.status and len(sender.calls)==1


def test_missing_configuration_is_explicit_and_does_not_send(notice,monkeypatch):
    api,store,sender=notice;headers,row=preview(notice)
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')
    assert api[0].get('/api/admin/notifications/options').json()['configured'] is False
    assert approve(api[0],headers,row).status_code==503 and not sender.calls
    assert api[0].post('/api/admin/notifications',headers=headers,json=body()).status_code==503
    assert store.history()['notifications'][0]['status']=='draft'


def test_invalid_destination_and_private_test_only_mode(notice,monkeypatch):
    api,store,sender=notice;headers=sign_in(api)
    for payload in [body(destination_id='unknown'),body(chat_id='unauthorized'),body(message=TOKEN)]:
        response=api[0].post('/api/admin/notifications',headers=headers,json=payload)
        assert response.status_code==422 and TOKEN not in response.text
    monkeypatch.setenv('TELEGRAM_DESTINATIONS',json.dumps({'test':{'label':'Broadcast','chat_id':'-123','test_only':False}}))
    assert api[0].get('/api/admin/notifications/options').json()['destinations']==[]
    assert api[0].post('/api/admin/notifications',headers=headers,json=body()).status_code==422
    assert not sender.calls and store.history()['total']==0


def test_configuration_change_expiry_and_other_actor_block_delivery(notice,monkeypatch):
    api,store,sender=notice;headers,row=preview(notice)
    payload=ApprovalInput(approve=True,content_sha256=row['content_sha256'])
    with pytest.raises(HTTPException) as e:store.claim(row['id'],payload,{'id':str(uuid.uuid4())},api[2])
    assert e.value.status_code==409
    monkeypatch.setenv('TELEGRAM_DESTINATIONS',json.dumps({'test':{'label':'ISOLATED PRIVATE TEST','chat_id':'124','test_only':True}}))
    assert approve(api[0],headers,row).status_code==409
    with api[1].begin() as c:c.execute(update(notifications).values(created_at=__import__('app.notifications',fromlist=['now']).now()-timedelta(minutes=31)))
    assert approve(api[0],headers,row).status_code==409 and not sender.calls
    assert api[0].post('/api/admin/notifications/'+str(uuid.uuid4())+'/send',headers=headers,json=payload.model_dump()).status_code==404


def test_shelter_snapshot_excludes_private_data_and_rechecks_changes(notice):
    api,store,sender=notice;client=api[0];headers=sign_in(api);p=fixture_record()
    shelter=client.post('/api/admin/shelters',headers=headers,json=p).json()
    assert client.post('/api/admin/notifications',headers=headers,json=body(shelter_id=shelter['id'])).status_code==409
    shelter=client.put('/api/admin/shelters/'+shelter['id'],headers=headers,json=verified(p,shelter['revision'])).json()
    headers,row=preview(notice,shelter_id=shelter['id'])
    assert 'Reported available capacity: 8 / 10' in row['text']
    assert 'PRIVATE TEST' not in row['text']
    change=verified({**p,'occupancy':3},shelter['revision'])
    assert client.put('/api/admin/shelters/'+shelter['id'],headers=headers,json=change).status_code==200
    assert approve(client,headers,row).status_code==409 and not sender.calls


def test_finalization_failure_preserves_claim_and_prohibits_resend(notice,monkeypatch):
    api,store,sender=notice;headers,row=preview(notice);original=store.finish
    def fail(*args):raise OperationalError('safe statement',{},Exception('controlled failure'))
    monkeypatch.setattr(store,'finish',fail)
    assert approve(api[0],headers,row).status_code==503
    assert store.history()['notifications'][0]['status']=='sending'
    monkeypatch.setattr(store,'finish',original)
    assert approve(api[0],headers,row).json()['status']=='sending' and len(sender.calls)==1


def test_concurrent_claim_is_durable_before_network(notice):
    api,store,sender=notice;headers,row=preview(notice);approval=ApprovalInput(approve=True,content_sha256=row['content_sha256']);actor={'id':api[4]}
    def claim():return store.claim(row['id'],approval,actor,api[2])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
    assert sum(config is not None for _,config,_ in results)==1
    assert store.history()['notifications'][0]['status']=='sending'
    assert all(r[0]['status']=='sending' for r in results)


def test_database_constraints_and_transaction_rollback(notice):
    api,store,sender=notice;headers,row=preview(notice)
    for values in [{'status':'accepted'},{'created_by':str(uuid.uuid4())},{'kind':'automatic_ml_alert'},{'text':''}]:
        with pytest.raises(IntegrityError):
            with api[1].begin() as c:c.execute(update(notifications).values(**values))
    assert store.history()['notifications'][0]['status']=='draft'
    assert not sender.calls


def test_least_privilege_notification_role_can_audit_but_not_delete(notice):
    import psycopg
    import secrets
    from psycopg import sql
    from app.location_database import database_engine
    from sqlalchemy.exc import DBAPIError
    api,store,sender=notice;headers,row=preview(notice);db=api[1]
    role='notice_test_'+uuid.uuid4().hex;password=secrets.token_urlsafe(24)
    admin=psycopg.connect(db.url.set(drivername='postgresql').render_as_string(hide_password=False),autocommit=True)
    limited=None
    try:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        admin.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(db.url.database),sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON admin_notifications TO {}').format(sql.Identifier(role)))
        limited=database_engine(db.url.set(username=role,password=password).render_as_string(hide_password=False))
        n=NotificationStore(limited)
        assert n.history()['total']==1
        claimed,config,destination=n.claim(row['id'],ApprovalInput(approve=True,content_sha256=row['content_sha256']),{'id':api[4]},api[2])
        assert config is not None and claimed['status']=='sending'
        assert n.finish(row['id'],DeliveryResult('rejected','telegram_rejected',403,telegram_error_code=403))['status']=='rejected'
        # A dedicated notification grant cannot mutate the directory, credentials or audit history.
        for statement in ['DELETE FROM admin_notifications','UPDATE shelter_admins SET active=false','UPDATE location_directory_districts SET name=name','DELETE FROM shelter_audit']:
            with pytest.raises(DBAPIError):
                with limited.begin() as c:c.exec_driver_sql(statement)
    finally:
        if limited:limited.dispose()
        admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)));admin.close()
