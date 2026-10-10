"""Offline Telegram protocol checks: no sockets, credentials or persistent writes."""
import json
import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.notifications import DraftInput, ApprovalInput, render_message, public_snapshot, canonical_hash
from app.telegram_delivery import TelegramConfig, ConfigurationUnavailable, TelegramSender

TOKEN = '123456:' + 'ISOLATED_TEST_ONLY_' * 2


def configure(monkeypatch, rows=None):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('TELEGRAM_DESTINATIONS', json.dumps(rows or {'private-test': {'label': 'Isolated test', 'chat_id': '123', 'test_only': True}}))
    return TelegramConfig.from_environment()


def draft(**values):
    return DraftInput(request_id=uuid.uuid4(), destination_id='private-test', kind='informational', message=values.pop('message', 'Isolated protocol test only'), **values)


def test_config_absence_redaction_and_fingerprint(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.delenv('TELEGRAM_DESTINATIONS', raising=False)
    with pytest.raises(ConfigurationUnavailable, match='not configured'):
        TelegramConfig.from_environment()
    c = configure(monkeypatch)
    assert TOKEN not in repr(c) and '123' not in repr(c.destinations['private-test'])
    assert len(c.fingerprint(c.destinations['private-test'])) == 64
    assert c.fingerprint(c.destinations['private-test']) == c.fingerprint(c.destinations['private-test'])


@pytest.mark.parametrize('rows', [[], {}, {'BAD ALIAS': {}}, {'x': {'label': 'X', 'chat_id': 123}},
    {'x': {'label': 'X', 'chat_id': '0'}}, {'x': {'label': 'X', 'chat_id': '-123', 'test_only': True}},
    {'x': {'label': 'X', 'chat_id': '123', 'test_only': 'true'}},
    {'x': {'label': 'X', 'chat_id': '123', 'token': 'secret'}},
    {'x': {'label': 'X\nY', 'chat_id': '123'}},
    {'x': {'label': 'X', 'chat_id': '123'}, 'y': {'label': 'x', 'chat_id': '124'}},
    {'x': {'label': 'X', 'chat_id': '123'}, 'y': {'label': 'Y', 'chat_id': '123'}}])
def test_config_rejects_bad_routing_without_echo(monkeypatch, rows):
    configure(monkeypatch)
    monkeypatch.setenv('TELEGRAM_DESTINATIONS', json.dumps(rows))
    with pytest.raises(ConfigurationUnavailable) as e:
        TelegramConfig.from_environment()
    assert TOKEN not in str(e.value) and 'secret' not in str(e.value)


@pytest.mark.parametrize('message', ['', '  ', '\x00bad', TOKEN, '\ud800', 'x'*3501])
def test_message_validation(message):
    with pytest.raises(ValidationError): draft(message=message)


def test_preview_is_plain_text_and_explicit_approval():
    p = draft(message='Test <b>literal</b>\nNo automatic warning')
    out = render_message(p, None)
    assert out.endswith(p.message) and 'prototype' in out
    with pytest.raises(ValidationError): ApprovalInput(approve='true', content_sha256='a'*64)
    with pytest.raises(ValidationError): DraftInput(**p.model_dump(), chat_id='unapproved')
    assert canonical_hash({'x': 1, 'y': 2}) == canonical_hash({'y': 2, 'x': 1})
    with pytest.raises(HTTPException): render_message(draft(message='😀'*3000), None)
    assert public_snapshot({'id':'x','contact':'private','notes':'private','capacity':2})['capacity']==2
    assert 'notes' not in public_snapshot({'notes':'private'})


def transport(monkeypatch, body, status=200, error=None):
    calls = []
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == 'api.telegram.org' and kwargs['timeout'] == 10
            assert kwargs['context'].check_hostname
        def set_debuglevel(self, value): assert value == 0
        def request(self, method, path, **kwargs):
            calls.append((method, path, json.loads(kwargs['body'])))
            if error: raise error
        def getresponse(self): return SimpleNamespace(status=status, read=lambda limit: body)
        def close(self): pass
    monkeypatch.setattr('app.telegram_delivery.http.client.HTTPSConnection', Connection)
    return calls


def test_protocol_acceptance_is_not_recipient_reading(monkeypatch, caplog):
    c = configure(monkeypatch)
    raw = json.dumps({'ok': True, 'result': {'message_id': 99, 'chat': {'id':123,'type':'private'},'text':'TEST ONLY'}}).encode()
    calls = transport(monkeypatch, raw)
    r = TelegramSender().send(c,c.destinations['private-test'],'TEST ONLY')
    assert r.status == 'accepted' and r.telegram_message_id == 99
    assert len(calls)==1 and calls[0][0]=='POST' and calls[0][1].endswith('/sendMessage')
    assert calls[0][2] == {'chat_id':'123','text':'TEST ONLY','link_preview_options':{'is_disabled':True}}
    assert TOKEN not in caplog.text and not hasattr(r, 'read_by_recipient')


@pytest.mark.parametrize('body,status,expected', [
    ({'ok':False,'error_code':403,'description':TOKEN},403,'rejected'),
    ({'ok':True,'result':{}},200,'delivery_unknown'),
    ({'ok':True,'result':{'message_id':1,'chat':{'id':123,'type':'group'},'text':'TEST'}},200,'delivery_unknown'),
    ({'ok':True,'result':{'message_id':1,'chat':{'id':124,'type':'private'},'text':'TEST'}},200,'delivery_unknown'),
    ({'ok':True,'result':{'message_id':1,'chat':{'id':123,'type':'private'},'text':'changed'}},200,'delivery_unknown'),
    ({'ok':True},302,'delivery_unknown'), ([],200,'delivery_unknown')])
def test_api_rejection_uncertainty_and_no_provider_body_leak(monkeypatch, body, status, expected, caplog):
    c=configure(monkeypatch); calls=transport(monkeypatch,json.dumps(body).encode(),status)
    r=TelegramSender().send(c,c.destinations['private-test'],'TEST')
    assert r.status==expected and len(calls)==1 and TOKEN not in repr(r)+caplog.text


@pytest.mark.parametrize('error', [TimeoutError(TOKEN), OSError(TOKEN)])
def test_transport_failure_is_uncertain_and_never_retried(monkeypatch,error,caplog):
    c=configure(monkeypatch);calls=transport(monkeypatch,b'',error=error)
    r=TelegramSender().send(c,c.destinations['private-test'],'TEST')
    assert r.status=='delivery_unknown' and r.code=='transport_uncertain' and len(calls)==1
    assert TOKEN not in repr(r)+caplog.text


@pytest.mark.parametrize('body', [b'not json', b'x'*65537])
def test_malformed_or_oversized_response_is_unknown(monkeypatch,body):
    c=configure(monkeypatch);transport(monkeypatch,body)
    assert TelegramSender().send(c,c.destinations['private-test'],'TEST').status=='delivery_unknown'
