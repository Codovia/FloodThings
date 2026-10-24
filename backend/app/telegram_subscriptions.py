"""Signed Telegram command intake; no automatic outbound messages."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select,update,text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from .shelters import shelter_engine,mode
from .shelter_security import now,digest
from .telegram_delivery import TelegramConfig,ConfigurationUnavailable
from .subscription_schema import subscriptions,subscription_audit

router=APIRouter()
CONSENT_VERSION='telegram-private-alerts-v1-2026-10-13'


def subscriber_key(config,chat_id):
    return hmac.new(hashlib.sha256(config.token.encode()).digest(),chat_id.encode(),hashlib.sha256).hexdigest()


def is_subscribed(connection,config,destination):
    # Groups/channels use explicit configured operator authorization and Telegram membership.
    if int(destination.chat_id)<0:
        return True
    return connection.execute(select(subscriptions.c.active).where(subscriptions.c.subscriber_key==subscriber_key(config,destination.chat_id))).scalar_one_or_none() is True


def require_subscription(connection,config,destination):
    if not is_subscribed(connection,config,destination):
        raise HTTPException(409,'Private recipient has not opted in or has opted out. Ask them to send /start floodpulse to the configured bot; no message was sent.')


def webhook_secret():
    value=os.environ.get('TELEGRAM_WEBHOOK_SECRET','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',value):
        raise HTTPException(503,'Telegram webhook secret is not configured')
    return value


class SubscriptionStore:
    def __init__(self,engine=None):
        self.engine=engine or shelter_engine()

    def intake(self,body,config):
        if not isinstance(body,dict):
            raise HTTPException(422,'Invalid Telegram update')
        message=body.get('message',{})
        if not isinstance(message,dict):return {'ok':True,'processed':False}
        chat=message.get('chat',{});sender=message.get('from',{})
        if not isinstance(chat,dict) or not isinstance(sender,dict):return {'ok':True,'processed':False}
        command=message.get('text');identity=chat.get('id')
        if not isinstance(sender,dict) or chat.get('type')!='private' or type(identity) is not int or not 0<identity<2**53 or type(sender.get('id')) is not int or sender.get('id')!=identity or sender.get('is_bot') is not False or 'forward_origin' in message or 'via_bot' in message or command not in ('/start floodpulse','/stop'):
            return {'ok':True,'processed':False}
        destination=next((d for d in config.destinations.values() if d.chat_id==str(identity)),None)
        if not destination or (mode()=='demonstration' and not destination.test_only):
            return {'ok':True,'processed':False}
        update_id=body.get('update_id');sent=message.get('date')
        if type(update_id) is not int or not 0<=update_id<2**63 or type(sent) is not int or not 0<=sent<2**40:
            raise HTTPException(422,'Invalid Telegram command timestamp/update')
        try:command_at=datetime.fromtimestamp(sent,timezone.utc)
        except (OverflowError,OSError,ValueError):raise HTTPException(422,'Invalid Telegram command timestamp') from None
        timestamp=now()
        if not timestamp-timedelta(days=7)<=command_at<=timestamp+timedelta(minutes=1):
            return {'ok':True,'processed':False}
        key=subscriber_key(config,str(identity));active=command=='/start floodpulse'
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'subscription:'+key})
            old=c.execute(select(subscriptions).where(subscriptions.c.subscriber_key==key)).mappings().one_or_none()
            # Message time handles Telegram update-id reseeding after inactivity.
            if old and (command_at,update_id)<=(old['command_at'],old['update_id']):
                return {'ok':True,'processed':False}
            values=dict(active=active,command_at=command_at,received_at=timestamp,update_id=update_id,consent_version=CONSENT_VERSION)
            if old:c.execute(update(subscriptions).where(subscriptions.c.subscriber_key==key).values(**values))
            else:c.execute(subscriptions.insert().values(subscriber_key=key,**values))
            c.execute(subscription_audit.insert().values(id=str(uuid.uuid4()),subscriber_key=key,active=active,command_at=command_at,received_at=timestamp,update_id=update_id))
        return {'ok':True,'processed':True}


def get_subscriptions():return SubscriptionStore()


@router.get('/api/alerts/subscription')
def options():
    username=os.environ.get('TELEGRAM_BOT_USERNAME','')
    try:
        TelegramConfig.from_environment();webhook_secret()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',username) or not username.lower().endswith('bot'):
            raise ValueError()
    except (ValueError,ConfigurationUnavailable,HTTPException):
        return JSONResponse({'status':'unavailable','message':'Telegram subscriptions are not configured. Check official local warning channels.'},headers={'Cache-Control':'no-store'})
    return JSONResponse({'status':'available','url':'https://t.me/'+username+'?start=floodpulse','consent_version':CONSENT_VERSION,
        'message':'Send /start floodpulse to request private project alerts; /stop opts out. Delivery is not guaranteed. Administrator must authorize your destination before alerts are eligible.'},headers={'Cache-Control':'no-store'})


@router.post('/api/telegram/webhook')
async def webhook(request:Request,store=Depends(get_subscriptions)):
    expected=webhook_secret();supplied=request.headers.get('x-telegram-bot-api-secret-token','')
    if not hmac.compare_digest(expected.encode(),supplied.encode()):
        raise HTTPException(403,'Telegram webhook authentication required')
    try:config=TelegramConfig.from_environment()
    except ConfigurationUnavailable:raise HTTPException(503,'Telegram is not configured') from None
    raw=bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>65536:raise HTTPException(413,'Telegram update exceeds limit')
                raw.extend(chunk)
        body=json.loads(raw)
    except (ValueError,TimeoutError):raise HTTPException(422,'Invalid Telegram update') from None
    try:return await run_in_threadpool(store.intake,body,config)
    except SQLAlchemyError:raise HTTPException(503,'Subscription receipt was not recorded; Telegram may retry') from None
