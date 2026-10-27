"""District Telegram alerts end to end in disposable PostgreSQL only, with a mocked sender (no real messages)."""
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.main import app
from app.district_alert_schema import deliveries, district_audit, district_notices, district_subscriptions, subscribers
from app.notification_schema import notifications
from app.notifications import NotificationStore, get_notifications
from app.shelter_security import now
from app.subscription_schema import subscriptions
from app.telegram_delivery import DeliveryResult, get_sender
from app.telegram_subscriptions import SubscriptionStore, get_subscriptions
from test_shelter_postgres import api, sign_in

TOKEN = '123456:' + 'ISOLATED_ONLY_TOKEN_' * 2
SECRET = 'ISOLATED_WEBHOOK_SECRET_NO_CREDENTIAL_12345'
UDUPI, KODAGU, HASSAN = 'nic:udupi.nic.in', 'nic:kodagu.nic.in', 'nic:hassan.nic.in'


class Sender:
    """Records each attempt; a per-chat result can be set. Never opens a socket."""
    def __init__(self): self.calls = []; self.results = {}
    def send(self, config, destination, message):
        self.calls.append((destination.chat_id, message))
        return self.results.get(destination.chat_id, DeliveryResult('accepted', 'telegram_accepted', 200, telegram_message_id=40 + len(self.calls)))


@pytest.fixture
def alerts(api, monkeypatch):
    # Demonstration mode (as in the shelter fixture): only configured private test chats may subscribe.
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', TOKEN); monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('TELEGRAM_BOT_USERNAME', 'TEST_ONLY_FloodPulse_bot')
    monkeypatch.setenv('TELEGRAM_DESTINATIONS', json.dumps({'test': {'label': 'ISOLATED PRIVATE TEST', 'chat_id': '123', 'test_only': True},
                                                            'second': {'label': 'ISOLATED SECOND TEST', 'chat_id': '124', 'test_only': True}}))
    store, sender = NotificationStore(api[1]), Sender()
    app.dependency_overrides[get_subscriptions] = lambda: SubscriptionStore(api[1])
    app.dependency_overrides[get_notifications] = lambda: store
    app.dependency_overrides[get_sender] = lambda: sender
    try: yield api, store, sender
    finally:
        for dependency in (get_subscriptions, get_notifications, get_sender): app.dependency_overrides.pop(dependency, None)


def command(text, update_id, chat=123, seconds=0):
    return {'update_id': update_id, 'message': {'date': int((now() + timedelta(seconds=seconds)).timestamp()), 'text': text,
            'chat': {'id': chat, 'type': 'private'}, 'from': {'id': chat, 'is_bot': False}}}


def say(alerts, text, update_id, chat=123, seconds=0):
    response = alerts[0][0].post('/api/telegram/webhook', headers={'X-Telegram-Bot-Api-Secret-Token': SECRET}, json=command(text, update_id, chat, seconds))
    assert response.status_code == 200, response.text
    return response.json()


def draft(alerts, district_id, headers):
    return alerts[0][0].post('/api/admin/notifications', headers=headers, json={'request_id': str(uuid.uuid4()), 'district_id': district_id,
                             'kind': 'informational', 'message': 'ISOLATED DEMONSTRATION ONLY — no operational notice'})


def approve(alerts, headers, row):
    return alerts[0][0].post(f"/api/admin/notifications/{row['id']}/send", headers=headers, json={'approve': True, 'content_sha256': row['content_sha256']})


def test_subscribe_confirm_list_unsubscribe_and_stop_deletes_the_chat_id(alerts):
    db = alerts[0][1]
    reply = say(alerts, '/start floodpulse udupi', 10)
    assert reply['method'] == 'sendMessage' and reply['chat_id'] == 123 and 'flood alerts for Udupi district' in reply['text']
    assert say(alerts, '/start floodpulse udupi', 10) == {'ok': True, 'processed': False}  # Telegram retry: nothing changes
    assert 'Dakshina Kannada, Udupi' in say(alerts, '/start floodpulse_mangalore', 11)['text']
    assert say(alerts, '/mydistricts', 12)['text'] == 'FloodPulse: your districts: Dakshina Kannada, Udupi.'
    assert 'is not a Karnataka district' in say(alerts, '/start floodpulse goa', 13)['text']
    assert 'You still receive: Dakshina Kannada.' in say(alerts, '/stop udupi', 14)['text']
    with db.connect() as c:
        assert c.execute(select(subscribers.c.chat_id)).scalar_one() == '123'
        assert c.execute(select(district_subscriptions.c.district_id)).scalars().all() == ['nic:dk.nic.in']
    assert 'chat ID was deleted' in say(alerts, '/stop', 15)['text']
    with db.connect() as c:
        assert c.execute(select(func.count()).select_from(subscribers)).scalar_one() == 0
        assert c.execute(select(func.count()).select_from(district_subscriptions)).scalar_one() == 0
        assert [r.action for r in c.execute(select(district_audit).order_by(district_audit.c.update_id))] == ['subscribe', 'subscribe', 'unsubscribe', 'stop']
        assert c.execute(select(subscriptions.c.active)).scalar_one() is False  # /stop also ends the operator opt-in
        assert '123' not in json.dumps([dict(r._mapping) for r in c.execute(select(district_audit))], default=str)
    assert say(alerts, '/start floodpulse udupi', 14, seconds=-60) == {'ok': True, 'processed': False}  # older than the /stop: ignored


def test_public_subscriptions_in_live_mode_and_none_from_unknown_chats_in_a_demonstration(alerts, monkeypatch):
    assert say(alerts, '/start floodpulse kodagu', 20, chat=777) == {'ok': True, 'processed': False}
    assert 'FloodPulse district flood alerts' not in json.dumps(say(alerts, '/start', 21, chat=777))
    monkeypatch.setenv('SHELTER_DIRECTORY_MODE', 'live')
    assert 'Kodagu' in say(alerts, '/start floodpulse kodagu', 22, chat=777)['text']
    assert 'Subscribe: /start floodpulse <district>' in say(alerts, '/start floodpulse', 23, chat=778)['text']
    with alerts[0][1].connect() as c:
        row = c.execute(select(subscribers)).mappings().one()
        assert row['chat_id'] == '777' and row['demonstration'] is False


def test_an_approved_district_alert_reaches_that_districts_subscribers_only(alerts):
    api, store, sender = alerts; headers = sign_in(api)
    say(alerts, '/start floodpulse udupi', 30); say(alerts, '/start floodpulse kodagu', 31, chat=124)
    options = api[0].get('/api/admin/notifications/options').json()
    counts = {d['id']: d['subscribers'] for d in options['districts']}
    assert len(options['districts']) == 31 and counts[UDUPI] == 1 and counts[KODAGU] == 1 and counts[HASSAN] == 0
    assert 'chat_id' not in json.dumps(options) and '124' not in json.dumps(options)
    assert draft(alerts, HASSAN, headers).status_code == 409
    response = draft(alerts, UDUPI, headers); assert response.status_code == 201, response.text
    row = response.json()
    assert row['destination_label'] == 'Udupi district subscribers' and 'District: Udupi\n' in row['text'] and row['district']['recipients'] is None
    assert not sender.calls
    sent = approve(alerts, headers, row).json()
    assert sent['status'] == 'accepted' and sent['district'] == {'district_id': UDUPI, 'district_name': 'Udupi', 'recipients': 1, 'accepted': 1, 'rejected': 0, 'uncertain': 0}
    assert sender.calls == [('123', row['text'])]
    assert approve(alerts, headers, row).json()['status'] == 'accepted' and len(sender.calls) == 1  # never twice
    with api[1].connect() as c:
        assert c.execute(select(deliveries.c.status)).scalars().all() == ['accepted']
        assert c.execute(select(notifications.c.result_code)).scalar_one() == 'district_broadcast'
    history = api[0].get('/api/admin/notifications').json()['notifications'][0]
    assert history['district']['accepted'] == 1 and 'chat_id' not in json.dumps(history)


def test_blocked_and_uncertain_deliveries_and_leaving_before_approval(alerts):
    api, store, sender = alerts; headers = sign_in(api)
    say(alerts, '/start floodpulse udupi', 40); say(alerts, '/start floodpulse udupi', 41, chat=124)
    sender.results = {'123': DeliveryResult('rejected', 'telegram_rejected', 403, 403), '124': DeliveryResult('delivery_unknown', 'transport_uncertain')}
    row = draft(alerts, UDUPI, headers).json()
    sent = approve(alerts, headers, row).json()
    assert sent['status'] == 'delivery_unknown'
    assert {k: sent['district'][k] for k in ('recipients', 'accepted', 'rejected', 'uncertain')} == {'recipients': 2, 'accepted': 0, 'rejected': 1, 'uncertain': 1}
    with api[1].connect() as c:
        assert c.execute(select(subscribers.c.chat_id)).scalars().all() == ['124']  # blocked the bot: chat ID deleted
        assert 'blocked' in c.execute(select(district_audit.c.action)).scalars().all()
    row = draft(alerts, UDUPI, headers).json()
    say(alerts, '/stop udupi', 42, chat=124)
    assert approve(alerts, headers, row).status_code == 409 and len(sender.calls) == 2
    with api[1].connect() as c:
        assert c.execute(select(notifications.c.status).where(notifications.c.id == row['id'])).scalar_one() == 'draft'
        assert c.execute(select(district_notices.c.recipients).where(district_notices.c.notification_id == row['id'])).scalar_one() is None
