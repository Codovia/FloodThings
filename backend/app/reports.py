"""Private, consented citizen reports and authenticated moderation. No public feed."""
import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from .shelters import authorized, shelter_engine, mode
from .shelter_security import SecurityConfig, now, digest
from .shelter_schema import limits
from .report_schema import reports, images, audit
from .report_images import extract_image

router = APIRouter()
CONSENT_VERSION = 'private-review-v1-2026-10-13'
MAX_BODY = 7 * 1024 * 1024
RATE_SALT = secrets.token_bytes(32)


class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    request_id: uuid.UUID
    withdrawal_secret: str = Field(pattern=r'^[a-f0-9]{64}$')
    event_type: Literal['flooding','waterlogging','drainage_blockage','other']
    description: str = Field(min_length=10, max_length=2000)
    observed_at: datetime
    gps_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=10000000)
    consent: bool = Field(strict=True)
    image_rights: bool = Field(default=False, strict=True)
    metadata_consent: bool = Field(default=False, strict=True)
    photo_base64: str | None = Field(default=None, max_length=7000000)
    photo_mime: Literal['image/jpeg','image/png'] | None = None

    @field_validator('observed_at', 'gps_at')
    @classmethod
    def utc_clock(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Timezone required')
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def valid(self):
        if not self.consent:
            raise ValueError('Private review consent required')
        if bool(self.photo_base64) != bool(self.photo_mime) or (self.photo_base64 and not self.image_rights):
            raise ValueError('Photo requires MIME and upload rights confirmation')
        return self


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    state: Literal['UNDER_REVIEW','APPROVED','REJECTED']
    revision: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=10, max_length=2000)


class WithdrawalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    withdrawal_secret: str = Field(pattern=r'^[a-f0-9]{64}$')


def event(identity, before, after, reason, actor=None):
    return {'id': str(uuid.uuid4()), 'report_id': identity, 'actor_id': actor,
            'at': now(), 'action': after.lower(), 'before_state': before,
            'after_state': after, 'reason': reason}


def receipt(row):
    return {'id': row['id'], 'state': row['state'], 'source': row['source'],
            'received_at': row['received_at'], 'demonstration': row['demonstration'],
            'message': 'Recorded for private admin review; no emergency dispatch, public warning or training label was created.'}


def serialize(row):
    result = {k: v for k, v in dict(row).items() if k not in ('position','withdrawal_hash','payload_sha256')}
    if row['received_at'] <= now()-timedelta(days=30):
        result.update(description='[private evidence expired]',latitude=None,longitude=None,accuracy_m=None,gps_at=None,image_metadata=None)
    return result


class ReportStore:
    def __init__(self, engine=None):
        self.engine = engine or shelter_engine()

    def reserve(self, peer):
        timestamp = now(); start = timestamp.replace(minute=timestamp.minute//15*15, second=0, microsecond=0)
        keys = [(digest('report-global'),60), (hmac.new(RATE_SALT,peer.encode(),hashlib.sha256).hexdigest(),5)]
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(814210)'))
            for key, maximum in keys:
                row = c.execute(select(limits).where(limits.c.key==key)).mappings().one_or_none()
                count = row['attempts'] if row and row['window_start']==start else 0
                if count >= maximum:
                    raise HTTPException(429,'Report submission limit reached; retry after 15 minutes', headers={'Retry-After':'900'})
                if row:
                    c.execute(update(limits).where(limits.c.key==key).values(window_start=start,attempts=count+1))
                else:
                    c.execute(limits.insert().values(key=key,window_start=start,attempts=1))

    def submit(self, payload):
        timestamp = now()
        fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        # Serialize duplicate UUIDs; the same content returns the original receipt.
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':int(payload.request_id.hex[:15],16)})
            old = c.execute(select(reports).where(reports.c.request_id==str(payload.request_id))).mappings().one_or_none()
            if old:
                if old['payload_sha256'] != fingerprint:
                    raise HTTPException(409,'Submission token reused with changed content')
                return receipt(old)
            if not timestamp-timedelta(days=7) <= payload.observed_at <= timestamp+timedelta(minutes=5):
                raise HTTPException(422,'Observed time must be within the last seven days and not in the future')
            if not timestamp-timedelta(minutes=10) <= payload.gps_at <= timestamp+timedelta(seconds=5):
                raise HTTPException(422,'Acquire a fresh GPS fix before submitting')
            photo = extract_image(payload.photo_base64,payload.photo_mime,payload.metadata_consent,payload.latitude,payload.longitude,payload.accuracy_m,payload.observed_at) if payload.photo_base64 else None
            identity = str(uuid.uuid4())
            values = dict(id=identity, request_id=str(payload.request_id), payload_sha256=fingerprint,
                withdrawal_hash=digest(payload.withdrawal_secret), source='USER_REPORTED',
                event_type=payload.event_type, description=payload.description, observed_at=payload.observed_at,
                received_at=timestamp, gps_at=payload.gps_at, latitude=payload.latitude, longitude=payload.longitude,
                accuracy_m=payload.accuracy_m, position=func.ST_SetSRID(func.ST_MakePoint(payload.longitude,payload.latitude),4326),
                state='SUBMITTED', revision=1, demonstration=mode()=='demonstration', consent_version=CONSENT_VERSION,
                image_sha256=photo['sha256'] if photo else None, image_metadata=photo['metadata'] if photo else None)
            c.execute(reports.insert().values(**values))
            if photo:
                c.execute(images.insert().values(report_id=identity,original=photo['original'],preview=photo['preview'],preview_sha256=photo['preview_sha256'],expires_at=timestamp+timedelta(days=7)))
            c.execute(audit.insert().values(**event(identity,None,'SUBMITTED','Citizen consented to private review')))
            return receipt(values)

    def rows(self, limit=50, offset=0):
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            query = select(reports).where(reports.c.demonstration==(mode()=='demonstration'))
            rows = c.execute(query.order_by(reports.c.received_at.desc(),reports.c.id).limit(limit).offset(offset)).mappings()
            total = c.execute(select(func.count()).select_from(reports).where(reports.c.demonstration==(mode()=='demonstration'))).scalar_one()
            return {'reports':[serialize(r) for r in rows], 'total':total,'limit':limit,'offset':offset,'mode':mode()}

    def review(self, identity, payload, actor):
        with self.engine.begin() as c:
            row = c.execute(select(reports).where(reports.c.id==identity,reports.c.demonstration==(mode()=='demonstration')).with_for_update()).mappings().one_or_none()
            if not row:
                raise HTTPException(404,'Report not found')
            if row['revision'] != payload.revision:
                raise HTTPException(409,'Report changed; reload before review')
            allowed = {'SUBMITTED':{'UNDER_REVIEW'}, 'UNDER_REVIEW':{'APPROVED','REJECTED'}}
            if payload.state not in allowed.get(row['state'],set()):
                raise HTTPException(409,'Start review before approving/rejecting; completed or withdrawn reports cannot transition')
            c.execute(update(reports).where(reports.c.id==identity).values(state=payload.state,revision=row['revision']+1,reviewed_by=actor['id'],reviewed_at=now(),review_reason=payload.reason))
            c.execute(audit.insert().values(**event(identity,row['state'],payload.state,payload.reason,actor['id'])))
            return serialize(c.execute(select(reports).where(reports.c.id==identity)).mappings().one())

    def history(self, identity):
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            row = c.execute(select(reports.c.id).where(reports.c.id==identity,reports.c.demonstration==(mode()=='demonstration'))).scalar_one_or_none()
            if not row:
                raise HTTPException(404,'Report not found')
            return {'events':[dict(r) for r in c.execute(select(audit).where(audit.c.report_id==identity).order_by(audit.c.at,audit.c.id).limit(100)).mappings()]}

    def photo(self, identity, actor):
        with self.engine.begin() as c:
            row = c.execute(select(images.c.preview).join(reports,reports.c.id==images.c.report_id).where(reports.c.id==identity,reports.c.state!='WITHDRAWN',reports.c.demonstration==(mode()=='demonstration'),images.c.expires_at>now())).one_or_none()
            if not row:
                raise HTTPException(404,'Private photo unavailable or expired')
            state = c.execute(select(reports.c.state).where(reports.c.id==identity)).scalar_one()
            c.execute(audit.insert().values(**event(identity,state,state,'Private sanitized photo viewed',actor['id'])))
            return bytes(row.preview)

    def withdraw(self, identity, secret):
        with self.engine.begin() as c:
            row = c.execute(select(reports).where(reports.c.id==identity).with_for_update()).mappings().one_or_none()
            if not row or not hmac.compare_digest(row['withdrawal_hash'],digest(secret)):
                raise HTTPException(404,'Report or withdrawal key unavailable')
            if row['state']!='WITHDRAWN':
                self.erase(c,row,None,'Citizen withdrew private evidence')
            return {'id':identity,'state':'WITHDRAWN'}

    def erase(self,c,row,actor,reason):
        c.execute(delete(images).where(images.c.report_id==row['id']))
        c.execute(update(reports).where(reports.c.id==row['id']).values(state='WITHDRAWN',revision=row['revision']+1,description='[private evidence removed]',latitude=None,longitude=None,accuracy_m=None,position=None,gps_at=None,image_metadata=None))
        c.execute(audit.insert().values(**event(row['id'],row['state'],'WITHDRAWN',reason,actor)))

    def purge(self, actor):
        with self.engine.begin() as c:
            c.execute(delete(images).where(images.c.expires_at<=now()))
            rows = c.execute(select(reports).where(reports.c.received_at<=now()-timedelta(days=30),reports.c.state!='WITHDRAWN').with_for_update()).mappings().all()
            for row in rows:
                self.erase(c,row,actor['id'],'Private evidence retention elapsed')
            return {'state':'purged','reports_removed':len(rows)}

    def evidence(self, limit=50, offset=0):
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            rows = c.execute(select(reports).where(reports.c.state=='APPROVED',reports.c.demonstration==(mode()=='demonstration'),reports.c.received_at>now()-timedelta(days=30)).order_by(reports.c.received_at,reports.c.id).limit(limit).offset(offset)).mappings()
            return {'schema_version':'citizen-evidence-v1','source':'USER_REPORTED','label_eligibility':'NOT_ASSESSED','negative_labels':False,
                    'records':[{**serialize(r),'training_eligible':False,'official_warning':False,'environmental_snapshot_status':'not_captured','image_license':'submitter_authorized_private_review_only' if r['image_sha256'] else None} for r in rows], 'limit':limit,'offset':offset}


def get_report_store():
    return ReportStore()


def execute(fn, *args):
    try:
        return fn(*args)
    except SQLAlchemyError:
        raise HTTPException(503,'Report database unavailable; operation may be incomplete. Retry only with the same submission token.') from None


@router.get('/api/reports/options')
def options():
    return {'consent_version':CONSENT_VERSION,'photo_limit_bytes':5*1024*1024,'image_retention_days':7,'report_retention_days':30,'public_publication':False,'vision_model':'unavailable'}


@router.post('/api/reports', status_code=201)
async def submit(request:Request, store=Depends(get_report_store)):
    SecurityConfig().same_origin(request)
    if request.headers.get('content-type','').split(';')[0]!='application/json' or request.headers.get('x-floodpulse-report')!='1':
        raise HTTPException(403,'Same-origin JSON report header required')
    await run_in_threadpool(execute,store.reserve,request.client.host if request.client else 'unknown')
    raw=bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>MAX_BODY:
                    raise HTTPException(413,'Report exceeds upload limit')
                raw.extend(chunk)
    except TimeoutError:
        raise HTTPException(408,'Report upload timed out') from None
    try:
        payload=ReportInput.model_validate_json(raw)
    except (ValidationError,ValueError):
        raise HTTPException(422,'Invalid report; check consent, timestamps, GPS and photo fields') from None
    return await run_in_threadpool(execute,store.submit,payload)


@router.post('/api/reports/{identity}/withdraw')
def withdraw(identity:uuid.UUID, payload:WithdrawalInput, request:Request,store=Depends(get_report_store)):
    SecurityConfig().same_origin(request)
    return execute(store.withdraw,str(identity),payload.withdrawal_secret)


@router.get('/api/admin/reports')
def rows(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(authorized),store=Depends(get_report_store)):
    return execute(store.rows,limit,offset)


@router.post('/api/admin/reports/retention/purge')
def purge(actor=Depends(authorized),store=Depends(get_report_store)):
    return execute(store.purge,actor)


@router.get('/api/admin/reports/evidence')
def evidence(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(authorized),store=Depends(get_report_store)):
    return execute(store.evidence,limit,offset)


@router.post('/api/admin/reports/{identity}/review')
def review(identity:uuid.UUID,payload:ReviewInput,actor=Depends(authorized),store=Depends(get_report_store)):
    return execute(store.review,str(identity),payload,actor)


@router.get('/api/admin/reports/{identity}/audit')
def history(identity:uuid.UUID,actor=Depends(authorized),store=Depends(get_report_store)):
    return execute(store.history,str(identity))


@router.get('/api/admin/reports/{identity}/photo')
def photo(identity:uuid.UUID,actor=Depends(authorized),store=Depends(get_report_store)):
    return Response(execute(store.photo,str(identity),actor),media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="private-report-preview.jpg"'})
