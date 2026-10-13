"""Opt-in/out and one mocked explicit delivery in disposable PostgreSQL only."""
from copy import deepcopy
from datetime import timedelta
import pytest
from sqlalchemy import select,update
from app.main import app
from app.telegram_subscriptions import SubscriptionStore,get_subscriptions
from app.subscription_schema import subscriptions,subscription_audit
from app.shelter_security import now,digest
from app.shelter_schema import limits
from test_notifications_postgres import notice,preview,approve,body
from test_shelter_postgres import api,sign_in

SECRET='ISOLATED_WEBHOOK_SECRET_NO_CREDENTIAL_12345'


@pytest.fixture
def consent(notice,monkeypatch):
    api,*_=notice;monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setenv('TELEGRAM_BOT_USERNAME','TEST_ONLY_FloodPulse_bot')
    app.dependency_overrides[get_subscriptions]=lambda:SubscriptionStore(api[1])
    try:yield notice
    finally:app.dependency_overrides.pop(get_subscriptions,None)


def command(text,update_id=10,seconds=0):
    return {'update_id':update_id,'message':{'date':int((now()+timedelta(seconds=seconds)).timestamp()),'text':text,'chat':{'id':123,'type':'private'},'from':{'id':123,'is_bot':False}}}


def intake(consent,payload):
    return consent[0][0].post('/api/telegram/webhook',headers={'X-Telegram-Bot-Api-Secret-Token':SECRET},json=payload)


def test_authenticated_opt_out_blocks_preview_and_pending_send_until_new_opt_in(consent):
    api,store,sender=consent;headers,row=preview(consent)
    assert intake(consent,command('/stop',10)).json()['processed']
    assert approve(api[0],headers,row).status_code==409 and not sender.calls
    assert api[0].post('/api/admin/notifications',headers=headers,json=body()).status_code==409
    assert intake(consent,command('/start floodpulse',11)).json()['processed']
    response=approve(api[0],headers,row)
    assert response.status_code==200 and response.json()['status']=='accepted' and len(sender.calls)==1
    assert approve(api[0],headers,row).status_code==200 and len(sender.calls)==1
    data=api[0].get('/api/admin/notifications/options').json()
    assert data['destinations'][0]['opted_in'] is True and 'chat_id' not in str(data)
    with api[1].connect() as c:
        row=c.execute(select(subscriptions)).mappings().one()
        assert row['active'] and '123' not in row['subscriber_key']
        assert len(c.execute(select(subscription_audit)).all())==3


def test_spoofed_duplicate_stale_and_unapproved_updates_cannot_reactivate(consent):
    api=consent[0];client=api[0]
    assert client.post('/api/telegram/webhook',json=command('/stop')).status_code==403
    assert intake(consent,command('/stop',20)).json()['processed']
    assert intake(consent,command('/start floodpulse',19)).json()['processed'] is False
    assert intake(consent,command('/stop',20)).json()['processed'] is False
    spoof=command('/start floodpulse',21);spoof['message']['from']['id']=999
    assert intake(consent,spoof).json()['processed'] is False
    unknown=command('/start floodpulse',22);unknown['message']['from']['id']=unknown['message']['chat']['id']=999
    assert intake(consent,unknown).json()['processed'] is False
    assert intake(consent,command('/start floodpulse',23,seconds=-864000)).json()['processed'] is False
    with api[1].connect() as c:assert c.execute(select(subscriptions.c.active)).scalar_one() is False


def test_webhook_readiness_does_not_send_or_expose_secrets(consent,monkeypatch):
    client=consent[0][0];sender=consent[2]
    public=client.get('/api/alerts/subscription')
    assert public.json()['status']=='available' and public.json()['url'].startswith('https://t.me/TEST_ONLY_')
    assert SECRET not in public.text and public.headers['cache-control']=='no-store'
    malformed=command('/stop');malformed['message']['chat']='invalid'
    assert intake(consent,malformed).json()['processed'] is False
    assert not sender.calls
    monkeypatch.delenv('TELEGRAM_WEBHOOK_SECRET')
    assert client.get('/api/alerts/subscription').json()['status']=='unavailable'
    assert client.post('/api/telegram/webhook',json={}).status_code==503


def test_persistent_global_send_budget_blocks_attempt_before_sender(consent):
    api,store,sender=consent;headers,row=preview(consent)
    timestamp=now();start=timestamp.replace(minute=timestamp.minute//15*15,second=0,microsecond=0)
    with api[1].begin() as c:c.execute(limits.insert().values(key=digest('telegram-dispatch-global'),window_start=start,attempts=20))
    response=approve(api[0],headers,row)
    assert response.status_code==429 and response.headers['retry-after']=='900' and not sender.calls
    assert store.history()['notifications'][0]['status']=='draft'
