"""Preview and explicit administrator approval; no automatic alert callers."""
import hashlib
import json
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update, func, text as sql_text

from .notification_schema import notifications
from .shelters import authorized, get_store, shelter_engine, execute, mode, now
from .telegram_delivery import ConfigurationUnavailable, TelegramConfig, TOKEN_PATTERN, get_sender

router = APIRouter(prefix='/api/admin/notifications')


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    destination_id: str = Field(min_length=1, max_length=40, pattern=r'^[a-z][a-z0-9_-]*$')
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


def render_message(payload, snapshot):
    outgoing = 'FloodPulse prototype — administrator-approved ' + payload.kind.upper() + ' notice\n\n' + payload.message
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
    if TOKEN_PATTERN.search(outgoing):
        raise HTTPException(422, 'Credential-like text is not allowed in a notification')
    if len(outgoing.encode('utf-16-le')) // 2 > 4096:
        raise HTTPException(422, 'Complete notice exceeds Telegram length limit; shorten the message')
    return outgoing


def safe_record(row):
    # Token, chat ID, routing fingerprint and provider response body never leave this service.
    return {k: row[k] for k in ['id', 'created_by', 'destination_id', 'destination_label', 'kind',
        'text', 'content_sha256', 'shelter_id', 'demonstration', 'created_at', 'confirmed_at',
        'confirmed_by', 'attempted_at', 'completed_at', 'status', 'result_code', 'http_status',
        'telegram_error_code', 'telegram_message_id']}


class NotificationStore:
    def __init__(self, engine=None):
        self.engine = engine or shelter_engine()

    def history(self, offset=0, limit=50):
        query = select(notifications).where(notifications.c.demonstration == (mode() == 'demonstration'))
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            rows = c.execute(query.order_by(notifications.c.created_at.desc(), notifications.c.id).offset(offset).limit(limit)).mappings().all()
            total = c.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        return {'notifications': [safe_record(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    def create(self, payload, actor, shelter_store):
        config = configured()
        destination = config.destinations.get(payload.destination_id)
        if destination is None or (mode() == 'demonstration' and not destination.test_only):
            raise HTTPException(422, 'Select an authorized configured destination')
        if config.token in payload.message:
            raise HTTPException(422, 'Credential-like text is not allowed')
        snapshot = available_shelter(shelter_store, str(payload.shelter_id)) if payload.shelter_id else None
        outgoing = render_message(payload, snapshot)
        fingerprint = config.fingerprint(destination)
        content = canonical_hash({'destination': destination.id, 'label': destination.label,
            'fingerprint': fingerprint, 'kind': payload.kind, 'text': outgoing, 'shelter': snapshot})
        with self.engine.begin() as c:
            # Serialize same-key preview retries; no duplicate draft on lost responses.
            c.execute(sql_text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                      {'key': actor['id'] + ':' + str(payload.request_id)})
            old = c.execute(select(notifications).where(notifications.c.created_by == actor['id'],
                notifications.c.request_id == str(payload.request_id))).mappings().one_or_none()
            if old:
                if old['content_sha256'] != content or old['demonstration'] != (mode() == 'demonstration'):
                    raise HTTPException(409, 'Preview request already used for different content; create a new preview')
                return safe_record(old)
            values = dict(id=str(uuid.uuid4()), request_id=str(payload.request_id), created_by=actor['id'],
                destination_id=destination.id, destination_label=destination.label, destination_fingerprint=fingerprint,
                kind=payload.kind, text=outgoing, content_sha256=content, shelter_id=str(payload.shelter_id) if payload.shelter_id else None,
                shelter_snapshot=snapshot, demonstration=mode() == 'demonstration', created_at=now(), status='draft')
            row = c.execute(notifications.insert().values(**values).returning(notifications)).mappings().one()
        return safe_record(row)

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
            if row['status'] != 'draft':
                return dict(row), None, None  # Already claimed: never call Telegram again.
            if row['created_at'] + timedelta(minutes=30) <= now():
                raise HTTPException(409, 'Preview expired; create and review a new notification')
            config = configured()
            destination = config.destinations.get(row['destination_id'])
            if not destination or (mode() == 'demonstration' and not destination.test_only) or config.fingerprint(destination) != row['destination_fingerprint'] or destination.label != row['destination_label']:
                raise HTTPException(409, 'Destination configuration changed; create a new preview')
            if row['shelter_id'] and available_shelter(shelter_store, row['shelter_id']) != row['shelter_snapshot']:
                raise HTTPException(409, 'Shelter information changed; create and review a new preview')
            timestamp = now()
            updated = c.execute(update(notifications).where(notifications.c.id == identity, notifications.c.status == 'draft')
                .values(status='sending', confirmed_at=timestamp, confirmed_by=actor['id'], attempted_at=timestamp)
                .returning(notifications)).mappings().one()
        # Claim is durable before external I/O. Crash/timeout cannot cause retry sends.
        return dict(updated), config, destination

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
    return {'configured': True, 'destinations': [{'id': d.id, 'label': d.label, 'test_only': d.test_only}
        for d in sorted(config.destinations.values(), key=lambda d: (d.label.casefold(), d.id)) if mode() != 'demonstration' or d.test_only], 'shelters': [{'id': s['id'], 'name': s['name'], 'district_name': s['district_name']} for s in shelters]}


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
    row, config, destination = execute(store.claim, str(identity), approval, actor, shelters)
    if config is None:
        return safe_record(row)
    result = sender.send(config, destination, row['text'])
    try:
        return execute(store.finish, str(identity), result)
    except HTTPException:
        raise HTTPException(503, 'Attempt started but result could not be recorded. Delivery may have occurred; do not resend. Inspect history and Telegram.') from None
