"""Preview and explicit administrator approval; no automatic alert callers."""
import hashlib
import json
import time
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, update, func, text as sql_text
from sqlalchemy.exc import SQLAlchemyError

from .notification_schema import notifications
from .shelters import authorized, get_store, shelter_engine, execute, mode, now
from .telegram_subscriptions import require_subscription,is_subscribed
from .shelter_schema import limits
from .shelter_security import digest
from .telegram_delivery import ConfigurationUnavailable, Destination, TelegramConfig, TOKEN_PATTERN, get_sender
from .district_alert_schema import deliveries, district_notices
from .district_alerts import active_districts, forget_blocked, normalize, recipients, subscriber_counts

router = APIRouter(prefix='/api/admin/notifications')
# District alerts: one approved message is sent to each subscriber, paced under Telegram's ~30 messages/second.
MAX_DISTRICT_RECIPIENTS = 1000
SEND_INTERVAL_S = 0.04


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    destination_id: str | None = Field(default=None, min_length=1, max_length=40, pattern=r'^[a-z][a-z0-9_-]*$')
    district_id: str | None = Field(default=None, min_length=5, max_length=100, pattern=r'^nic:[a-z0-9.-]+$')
    kind: Literal['informational', 'emergency']
    message: str = Field(min_length=1, max_length=3500)
    shelter_id: uuid.UUID | None = None

    @field_validator('message')
    @classmethod
    def valid_message(cls, value):
        if not value.strip() or TOKEN_PATTERN.search(value):
            raise ValueError('Empty messages and credential-like text are not allowed')
        if any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('Unsupported control characters')
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValueError('Invalid Unicode') from None
        return value

    @model_validator(mode='after')
    def one_target(self):
        if (self.destination_id is None) == (self.district_id is None):
            raise ValueError('Choose exactly one configured destination or one district')
        return self


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approve: bool = Field(strict=True)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def configured():
    try:
        return TelegramConfig.from_environment()
    except ConfigurationUnavailable as exc:
        raise HTTPException(503, str(exc)) from None


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def public_snapshot(row):
    return {k: row.get(k) for k in ['id', 'name', 'address', 'district_name', 'latitude', 'longitude',
        'capacity', 'occupancy', 'available_capacity', 'water', 'toilets', 'accessibility',
        'restrictions', 'verified_at', 'updated_at', 'verification_expires_at', 'demonstration']}


def available_shelter(store, identity):
    # Exact lookup, not an unbounded list. Public-only serialization excludes private fields.
    from .shelter_schema import shelters
    from .location_database import districts
    from .shelters import serialize, VERIFICATION_HOURS
    query = select(shelters, districts.c.name.label('district_name')).join(districts,
        (districts.c.version == shelters.c.district_version) & (districts.c.id == shelters.c.district_id)).where(
        shelters.c.id == identity, shelters.c.demonstration == (mode() == 'demonstration'),
        shelters.c.status == 'open', shelters.c.verified_at > now() - timedelta(hours=VERIFICATION_HOURS))
    with store.engine.connect().execution_options(postgresql_readonly=True) as connection:
        row = connection.execute(query).mappings().one_or_none()
    if not row:
        raise HTTPException(409, 'Shelter is not currently verified Open; create a new preview after verification')
    # JSON timestamps must remain deterministic for snapshot comparison.
    from fastapi.encoders import jsonable_encoder
    return public_snapshot(jsonable_encoder(serialize(row, public=True)))


def district_destination(district):
    # Routing identity for a district's subscribers; never a real chat (each subscriber's chat is used at send time).
    return Destination('district-' + normalize(district['name']).replace(' ', '-'), (district['name'] + ' district subscribers')[:80], 'district:' + district['id'])


def render_message(payload, snapshot, district=None):
    outgoing = ('FloodPulse prototype — administrator-approved ' + payload.kind.upper() + ' notice\nSource: ADMIN_ALERT\n'
                + ('District: ' + district['name'] + '\n' if district else '') + '\n' + payload.message)
    if snapshot:
        outgoing += ('\n\nAdministrator-verified shelter information:\n' + snapshot['name'] + '\n'
            + snapshot['address'] + ' · ' + snapshot['district_name'] + '\n'
            + f"Reported available capacity: {snapshot['available_capacity']} / {snapshot['capacity']}\n"
            + f"Water: {snapshot['water']}; toilets: {snapshot['toilets']}\n"
            + 'Accessibility: ' + (snapshot['accessibility'] or 'Not reported') + '\n'
            + 'Restrictions: ' + (snapshot['restrictions'] or 'Not reported') + '\n'
            + f"Entrance: {snapshot['latitude']}, {snapshot['longitude']}\n"
            + 'Verified: ' + snapshot['verified_at'] + '\n'
            + 'Availability may change. Confirm access before travel. Routes are not verified flood-safe.')
    if district:
        outgoing += f"\n\nYou receive this because you subscribed to {district['name']} alerts. Stop: /stop {normalize(district['name'])} · Stop all: /stop"
    if TOKEN_PATTERN.search(outgoing):
        raise HTTPException(422, 'Credential-like text is not allowed in a notification')
    if len(outgoing.encode('utf-16-le')) // 2 > 4096:
        raise HTTPException(422, 'Complete notice exceeds Telegram length limit; shorten the message')
    return outgoing


def safe_record(row):
    # Token, chat ID, routing fingerprint and provider response body never leave this service.
    return {'source':'ADMIN_ALERT', **{k: row[k] for k in ['id', 'created_by', 'destination_id', 'destination_label', 'kind',
        'text', 'content_sha256', 'shelter_id', 'demonstration', 'created_at', 'confirmed_at',
        'confirmed_by', 'attempted_at', 'completed_at', 'status', 'result_code', 'http_status',
        'telegram_error_code', 'telegram_message_id']}}


def with_district(record, notice):
    if notice:
        record['district'] = {k: notice[k] for k in ('district_id', 'district_name', 'recipients', 'accepted', 'rejected', 'uncertain')}
    return record


class NotificationStore:
    def __init__(self, engine=None):
        self.engine = engine or shelter_engine()

    def history(self, offset=0, limit=50):
        query = select(notifications).where(notifications.c.demonstration == (mode() == 'demonstration'))
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            rows = c.execute(query.order_by(notifications.c.created_at.desc(), notifications.c.id).offset(offset).limit(limit)).mappings().all()
            total = c.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            summaries = {n['notification_id']: n for n in c.execute(select(district_notices).where(
                district_notices.c.notification_id.in_([r['id'] for r in rows]))).mappings()} if rows else {}
        return {'notifications': [with_district(safe_record(r), summaries.get(r['id'])) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    def create(self, payload, actor, shelter_store):
        config = configured()
        district = None
        if payload.district_id:
            district = next((d for d in active_districts(self.engine) if d['id'] == payload.district_id), None)
            if district is None:
                raise HTTPException(422, 'Select a Karnataka district from the active place directory')
            destination = district_destination(district)
        else:
            destination = config.destinations.get(payload.destination_id)
            if destination is None or (mode() == 'demonstration' and not destination.test_only):
                raise HTTPException(422, 'Select an authorized configured destination')
        if config.token in payload.message:
            raise HTTPException(422, 'Credential-like text is not allowed')
        snapshot = available_shelter(shelter_store, str(payload.shelter_id)) if payload.shelter_id else None
        outgoing = render_message(payload, snapshot, district)
        fingerprint = config.fingerprint(destination)
        content = canonical_hash({'destination': destination.id, 'label': destination.label,
            'fingerprint': fingerprint, 'kind': payload.kind, 'text': outgoing, 'shelter': snapshot})
        with self.engine.begin() as c:
            if district:
                if not recipients(c, district['id'], mode() == 'demonstration'):
                    raise HTTPException(409, f"Nobody has subscribed to {district['name']} alerts yet; nothing to preview or send.")
            else:
                require_subscription(c,config,destination)
            # Serialize same-key preview retries; no duplicate draft on lost responses.
            c.execute(sql_text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                      {'key': actor['id'] + ':' + str(payload.request_id)})
            old = c.execute(select(notifications).where(notifications.c.created_by == actor['id'],
                notifications.c.request_id == str(payload.request_id))).mappings().one_or_none()
            if old:
                if old['content_sha256'] != content or old['demonstration'] != (mode() == 'demonstration'):
                    raise HTTPException(409, 'Preview request already used for different content; create a new preview')
                return with_district(safe_record(old), c.execute(select(district_notices).where(district_notices.c.notification_id == old['id'])).mappings().one_or_none())
            values = dict(id=str(uuid.uuid4()), request_id=str(payload.request_id), created_by=actor['id'],
                destination_id=destination.id, destination_label=destination.label, destination_fingerprint=fingerprint,
                kind=payload.kind, text=outgoing, content_sha256=content, shelter_id=str(payload.shelter_id) if payload.shelter_id else None,
                shelter_snapshot=snapshot, demonstration=mode() == 'demonstration', created_at=now(), status='draft')
            row = c.execute(notifications.insert().values(**values).returning(notifications)).mappings().one()
            notice = c.execute(district_notices.insert().values(notification_id=row['id'], district_id=district['id'], district_name=district['name'])
                               .returning(district_notices)).mappings().one() if district else None
        return with_district(safe_record(row), notice)

    def claim(self, identity, approval, actor, shelter_store):
        if not approval.approve:
            raise HTTPException(422, 'Explicit reviewed-message approval is required')
        with self.engine.begin() as c:
            row = c.execute(select(notifications).where(notifications.c.id == identity,
                notifications.c.demonstration == (mode() == 'demonstration')).with_for_update()).mappings().one_or_none()
            if not row:
                raise HTTPException(404, 'Notification not found')
            if row['created_by'] != actor['id'] or row['content_sha256'] != approval.content_sha256:
                raise HTTPException(409, 'Only the composing administrator may approve this exact preview')
            notice = c.execute(select(district_notices).where(district_notices.c.notification_id == identity)).mappings().one_or_none()
            if row['status'] != 'draft':
                return dict(row), None, None, None  # Already claimed: never call Telegram again.
            if row['created_at'] + timedelta(minutes=30) <= now():
                raise HTTPException(409, 'Preview expired; create and review a new notification')
            config = configured()
            targets = None
            if notice:
                destination = district_destination({'id': notice['district_id'], 'name': notice['district_name']})
                if config.fingerprint(destination) != row['destination_fingerprint'] or destination.label != row['destination_label']:
                    raise HTTPException(409, 'Telegram configuration changed; create a new preview')
                # Recipients are the district's subscribers at approval time (people may join or leave after the preview).
                targets = recipients(c, notice['district_id'], mode() == 'demonstration')
                if not targets:
                    raise HTTPException(409, 'Nobody is subscribed to this district any more; nothing was sent.')
                if len(targets) > MAX_DISTRICT_RECIPIENTS:
                    raise HTTPException(409, f'More than {MAX_DISTRICT_RECIPIENTS} subscribers: this prototype does not send to that many in one approval.')
            else:
                destination = config.destinations.get(row['destination_id'])
                if not destination or (mode() == 'demonstration' and not destination.test_only) or config.fingerprint(destination) != row['destination_fingerprint'] or destination.label != row['destination_label']:
                    raise HTTPException(409, 'Destination configuration changed; create a new preview')
                require_subscription(c,config,destination)
            if row['shelter_id'] and available_shelter(shelter_store, row['shelter_id']) != row['shelter_snapshot']:
                raise HTTPException(409, 'Shelter information changed; create and review a new preview')
            timestamp = now()
            c.execute(sql_text('SELECT pg_advisory_xact_lock(814211)'))
            key=digest('telegram-dispatch-global')
            start=timestamp.replace(minute=timestamp.minute//15*15,second=0,microsecond=0)
            bucket=c.execute(select(limits).where(limits.c.key==key)).mappings().one_or_none()
            count=bucket['attempts'] if bucket and bucket['window_start']==start else 0
            if count>=20:raise HTTPException(429,'Telegram send limit reached; retry after 15 minutes',headers={'Retry-After':'900'})
            if bucket:c.execute(update(limits).where(limits.c.key==key).values(window_start=start,attempts=count+1))
            else:c.execute(limits.insert().values(key=key,window_start=start,attempts=1))
            updated = c.execute(update(notifications).where(notifications.c.id == identity, notifications.c.status == 'draft')
                .values(status='sending', confirmed_at=timestamp, confirmed_by=actor['id'], attempted_at=timestamp)
                .returning(notifications)).mappings().one()
            if notice:
                c.execute(update(district_notices).where(district_notices.c.notification_id == identity).values(recipients=len(targets)))
        # Claim is durable before external I/O. Crash/timeout cannot cause retry sends.
        return dict(updated), config, destination, targets

    def delivery(self, identity, key, result):
        with self.engine.begin() as c:
            c.execute(deliveries.insert().values(notification_id=identity, subscriber_key=key, status=result.status, result_code=result.code,
                http_status=result.http_status, telegram_error_code=result.telegram_error_code,
                telegram_message_id=result.telegram_message_id, completed_at=now()))
            if result.telegram_error_code == 403:
                forget_blocked(c, key, now())

    def finish_district(self, identity, results):
        accepted = [r for r in results if r.status == 'accepted']
        uncertain = sum(r.status == 'delivery_unknown' for r in results)
        status = 'delivery_unknown' if uncertain else 'accepted' if accepted else 'rejected'
        with self.engine.begin() as c:
            # 'accepted' records one accepted message id; per-recipient results are in telegram_district_deliveries.
            row = c.execute(update(notifications).where(notifications.c.id == identity, notifications.c.status == 'sending')
                .values(status=status, result_code='district_broadcast', completed_at=now(),
                        telegram_message_id=accepted[0].telegram_message_id if status == 'accepted' else None)
                .returning(notifications)).mappings().one()
            notice = c.execute(update(district_notices).where(district_notices.c.notification_id == identity)
                .values(accepted=len(accepted), uncertain=uncertain, rejected=len(results) - len(accepted) - uncertain)
                .returning(district_notices)).mappings().one()
        return with_district(safe_record(row), notice)

    def finish(self, identity, result):
        with self.engine.begin() as c:
            row = c.execute(update(notifications).where(notifications.c.id == identity, notifications.c.status == 'sending')
                .values(status=result.status, result_code=result.code, http_status=result.http_status,
                        telegram_error_code=result.telegram_error_code, telegram_message_id=result.telegram_message_id,
                        completed_at=now()).returning(notifications)).mappings().one()
        return safe_record(row)


def get_notifications():
    # get_store normalizes connection/configuration failures using existing conventions.
    return NotificationStore(get_store().engine)


@router.get('/options')
def options(actor=Depends(authorized), store=Depends(get_store)):
    try:
        config = TelegramConfig.from_environment()
    except ConfigurationUnavailable as exc:
        return {'configured': False, 'reason': str(exc), 'destinations': [], 'shelters': []}
    shelters = execute(store.rows, public=True)['shelters']
    try:
        with store.engine.connect().execution_options(postgresql_readonly=True) as c:
            destinations=[{'id':d.id,'label':d.label,'test_only':d.test_only,'opted_in':is_subscribed(c,config,d)}
                for d in sorted(config.destinations.values(),key=lambda d:(d.label.casefold(),d.id)) if mode()!='demonstration' or d.test_only]
            counts=subscriber_counts(c,mode()=='demonstration')
        districts=[{'id':d['id'],'name':d['name'],'subscribers':counts.get(d['id'],0)} for d in active_districts(store.engine)]
    except SQLAlchemyError:
        raise HTTPException(503,'Subscription database unavailable') from None
    return {'configured':True,'destinations':destinations,'districts':districts,'send_limit':'20 attempts per 15 minutes',
        'shelters':[{'id':s['id'],'name':s['name'],'district_name':s['district_name']} for s in shelters]}



@router.get('')
def history(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
            actor=Depends(authorized), store=Depends(get_notifications)):
    return execute(store.history, offset, limit)


@router.post('', status_code=201)
def preview(payload: DraftInput, actor=Depends(authorized), store=Depends(get_notifications), shelters=Depends(get_store)):
    return execute(store.create, payload, actor, shelters)


@router.post('/{identity}/send')
def send(identity: uuid.UUID, approval: ApprovalInput, actor=Depends(authorized), store=Depends(get_notifications),
         shelters=Depends(get_store), sender=Depends(get_sender)):
    row, config, destination, targets = execute(store.claim, str(identity), approval, actor, shelters)
    if config is None:
        return safe_record(row)
    if targets is not None:
        results = []
        for index, (key, chat_id) in enumerate(targets):
            if index:
                time.sleep(SEND_INTERVAL_S)
            result = sender.send(config, Destination(destination.id, destination.label, chat_id), row['text'])
            results.append(result)
            try:
                execute(store.delivery, str(identity), key, result)
            except HTTPException:
                raise HTTPException(503, f'Sent to {len(results)} of {len(targets)} subscribers, then the result could not be recorded. Remaining subscribers were not contacted; do not resend without checking history.') from None
        try:
            return execute(store.finish_district, str(identity), results)
        except HTTPException:
            raise HTTPException(503, 'Attempt finished but the summary could not be recorded. Do not resend; inspect history.') from None
    result = sender.send(config, destination, row['text'])
    try:
        return execute(store.finish, str(identity), result)
    except HTTPException:
        raise HTTPException(503, 'Attempt started but result could not be recorded. Delivery may have occurred; do not resend. Inspect history and Telegram.') from None
