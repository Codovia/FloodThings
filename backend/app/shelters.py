"""Manual shelter assignment, never inferred from weather/model predictions."""
import os
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,update,delete,func,text
from sqlalchemy.exc import SQLAlchemyError

from .location_database import database_engine,districts,active
from .locations import LocationsUnavailable
from .shelter_schema import admins,sessions,limits,shelters,audit
from .shelter_security import Login,SecurityConfig,HASHER,password_matches,dummy_hash,digest,csrf_token,now

router=APIRouter()
VERIFICATION_HOURS=24 # Application expiry policy, not an official emergency standard.


class Verification(BaseModel):
    model_config=ConfigDict(extra='forbid')
    authorization: bool=Field(default=False,strict=True)
    entrance: bool=Field(default=False,strict=True)
    usability: bool=Field(default=False,strict=True)
    capacity: bool=Field(default=False,strict=True)
    evidence: str=Field(default='',max_length=2000)


class ShelterInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str=Field(min_length=1,max_length=200)
    address: str=Field(min_length=1,max_length=1000)
    district_id: str=Field(min_length=1,max_length=100)
    latitude: float|None=Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    longitude: float|None=Field(default=None,ge=-180,le=180,allow_inf_nan=False)
    capacity: int=Field(ge=1,le=100000,strict=True)
    occupancy: int=Field(ge=0,strict=True)
    water: Literal['yes','no','unknown']='unknown'
    toilets: Literal['yes','no','unknown']='unknown'
    accessibility: str=Field(default='',max_length=2000)
    contact: str|None=Field(default=None,max_length=200)
    publish_contact: bool=False
    status: Literal['pending','open','full','closed']='pending'
    verification: Verification=Field(default_factory=Verification)
    notes: str=Field(default='',max_length=2000)
    restrictions: str=Field(default='',max_length=2000)
    revision: int|None=Field(default=None,ge=1,strict=True)

    @model_validator(mode='after')
    def valid(self):
        if (self.latitude is None)!=(self.longitude is None):
            raise ValueError('Supply both entrance coordinates or neither')
        if self.occupancy>self.capacity:
            raise ValueError('Occupancy cannot exceed capacity')
        if self.status in ('open','full'):
            v=self.verification
            if self.latitude is None or not all((v.authorization,v.entrance,v.usability,v.capacity)) or not v.evidence.strip():
                raise ValueError('Open/Full requires four explicit confirmations, entrance and verification evidence')
        if self.status=='open' and self.occupancy>=self.capacity:
            raise ValueError('Open requires available capacity; select Full instead')
        if self.status=='full' and self.occupancy!=self.capacity:
            raise ValueError('Full requires occupancy equal to capacity')
        return self


def mode():
    value=os.environ.get('SHELTER_DIRECTORY_MODE','live')
    if value not in ('live','demonstration'):
        raise HTTPException(503,'Shelter directory mode is invalid')
    return value


@lru_cache(maxsize=1)
def shelter_engine():
    url=os.environ.get('SHELTER_DATABASE_URL')
    if not url:raise HTTPException(503,'Shelter database is not configured')
    return database_engine(url)


def dispose_shelter_engine():
    if shelter_engine.cache_info().currsize:
        shelter_engine().dispose();shelter_engine.cache_clear()


class ShelterStore:
    def __init__(self,engine=None):
        self.engine=engine or shelter_engine()

    def login(self,username,password,peer):
        timestamp=now();start=timestamp.replace(minute=timestamp.minute//15*15,second=0,microsecond=0)
        blocked=False
        # Atomic cross-worker rate buckets; ignore untrusted forwarded headers.
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(814208)'))
            c.execute(delete(limits).where(limits.c.window_start<start-timedelta(hours=1)))
            for identity,maximum in [('peer:'+peer,20),('account:'+username,5)]:
                key=digest(identity);row=c.execute(select(limits).where(limits.c.key==key)).mappings().one_or_none()
                count=row['attempts'] if row and row['window_start']==start else 0
                if count>=maximum:blocked=True;break
                if row:c.execute(update(limits).where(limits.c.key==key).values(window_start=start,attempts=count+1))
                else:c.execute(limits.insert().values(key=key,window_start=start,attempts=1))
            user=c.execute(select(admins).where(admins.c.username==username)).mappings().one_or_none() if not blocked else None
        if blocked:raise HTTPException(429,'Login temporarily rate limited; retry after the 15-minute window',headers={'Retry-After':'900'})
        valid=password_matches(user['password_hash'] if user else dummy_hash(),password)
        if not valid or not user or not user['active']:
            raise HTTPException(401,'Invalid administrator credentials')
        token=__import__('secrets').token_urlsafe(32)
        with self.engine.begin() as c:
            c.execute(delete(limits).where(limits.c.key==digest('account:'+username)))
            c.execute(delete(sessions).where(sessions.c.expires_at<=timestamp))
            c.execute(sessions.insert().values(token_hash=digest(token),admin_id=user['id'],created_at=timestamp,last_seen_at=timestamp,expires_at=timestamp+timedelta(hours=8)))
        return token,{'id':user['id'],'username':user['username']}

    def session(self,token):
        timestamp=now()
        with self.engine.begin() as c:
            row=c.execute(select(sessions,admins.c.username,admins.c.active).join(admins).where(sessions.c.token_hash==digest(token)).with_for_update(of=sessions)).mappings().one_or_none()
            if not row:return None
            if not row['active'] or row['expires_at']<=timestamp or row['last_seen_at']+timedelta(minutes=30)<=timestamp:
                c.execute(delete(sessions).where(sessions.c.token_hash==digest(token)));return None
            c.execute(update(sessions).where(sessions.c.token_hash==digest(token)).values(last_seen_at=timestamp))
            return {'id':row['admin_id'],'username':row['username']}

    def logout(self,token):
        with self.engine.begin() as c:c.execute(delete(sessions).where(sessions.c.token_hash==digest(token)))

    def rows(self,public=False,latitude=None,longitude=None,offset=0,limit=100):
        timestamp=now();is_demo=mode()=='demonstration'
        query=select(shelters,districts.c.name.label('district_name')).join(districts,(districts.c.version==shelters.c.district_version)&(districts.c.id==shelters.c.district_id)).where(shelters.c.demonstration==is_demo)
        if public:query=query.where(shelters.c.status=='open',shelters.c.verified_at>timestamp-timedelta(hours=VERIFICATION_HOURS))
        if latitude is not None:
            distance=func.ST_DistanceSphere(shelters.c.entrance,func.ST_SetSRID(func.ST_MakePoint(longitude,latitude),4326))/1000
            query=query.add_columns(distance.label('straight_line_km')).order_by(distance.asc().nulls_last(),shelters.c.name,shelters.c.id)
        else:query=query.order_by(shelters.c.name,shelters.c.id)
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            rows=c.execute(query.limit(limit).offset(offset)).mappings().all()
            total=c.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one()
        return {'status':'available','mode':mode(),'shelters':[serialize(r,public,latitude,longitude) for r in rows],'total':total,'limit':limit,'offset':offset,'retrieved_at':timestamp.isoformat(),'verification_valid_hours':VERIFICATION_HOURS}

    def save(self,payload,actor,shelter_id=None):
        timestamp=now();is_demo=mode()=='demonstration'
        with self.engine.begin() as c:
            old=None
            if shelter_id:
                old=c.execute(select(shelters).where(shelters.c.id==shelter_id,shelters.c.demonstration==is_demo).with_for_update()).mappings().one_or_none()
                if not old:raise HTTPException(404,'Shelter not found')
                if payload.revision!=old['revision']:raise HTTPException(409,'Shelter changed; reload before saving')
            elif payload.status!='pending' or payload.revision is not None:
                raise HTTPException(422,'New shelters must start Pending verification')
            version=c.execute(select(active.c.version).where(active.c.singleton==1)).scalar_one_or_none()
            district=c.execute(select(districts.c.name).where(districts.c.version==version,districts.c.id==payload.district_id)).scalar_one_or_none()
            if not district:raise HTTPException(422,'Unknown district in active location directory')
            v=payload.verification;verified=payload.status in ('open','full')
            values=payload.model_dump(exclude={'verification','revision'})
            values.update(district_version=version,demonstration=is_demo,updated_at=timestamp,updated_by=actor['id'],revision=old['revision']+1 if old else 1,
                          authorization_confirmed=verified and v.authorization,entrance_confirmed=verified and v.entrance,
                          usability_confirmed=verified and v.usability,capacity_confirmed=verified and v.capacity,
                          verification_notes=v.evidence.strip() if verified else old['verification_notes'] if old and payload.status=='closed' else '',verified_at=timestamp if verified else old['verified_at'] if old and payload.status=='closed' else None,verified_by=actor['id'] if verified else old['verified_by'] if old and payload.status=='closed' else None,
                          entrance=func.ST_SetSRID(func.ST_MakePoint(payload.longitude,payload.latitude),4326) if payload.latitude is not None else None)
            identity=shelter_id or str(uuid.uuid4())
            if old:c.execute(update(shelters).where(shelters.c.id==identity).values(**values))
            else:c.execute(shelters.insert().values(id=identity,created_at=timestamp,created_by=actor['id'],**values))
            row=c.execute(select(shelters,districts.c.name.label('district_name')).join(districts,(districts.c.version==shelters.c.district_version)&(districts.c.id==shelters.c.district_id)).where(shelters.c.id==identity)).mappings().one()
            result=serialize(row,False)
            c.execute(audit.insert().values(id=str(uuid.uuid4()),shelter_id=identity,admin_id=actor['id'],at=timestamp,action='update' if old else 'create',before=audit_snapshot(old) if old else None,after=audit_snapshot(row)))
        return result

    def history(self,identity):
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            exists=c.execute(select(shelters.c.id).where(shelters.c.id==identity,shelters.c.demonstration==(mode()=='demonstration'))).scalar_one_or_none()
            if not exists:raise HTTPException(404,'Shelter not found')
            rows=c.execute(select(audit).where(audit.c.shelter_id==identity).order_by(audit.c.at,audit.c.id).limit(100)).mappings().all()
            return {'events':[dict(r) for r in rows],'limit':100}


def audit_snapshot(row):
    return {k:(v.isoformat() if hasattr(v,'isoformat') else v) for k,v in dict(row).items() if k not in ('entrance','district_name','straight_line_km')}


def directions(latitude,longitude,origin_lat=None,origin_lon=None):
    values={'api':1,'destination':f'{latitude},{longitude}'}
    if origin_lat is not None:values['origin']=f'{origin_lat},{origin_lon}'
    return 'https://www.google.com/maps/dir/?'+urlencode(values)


def serialize(row,public=False,latitude=None,longitude=None):
    r=dict(row);result={k:r[k] for k in ['id','name','address','district_id','district_name','latitude','longitude','capacity','occupancy','water','toilets','accessibility','status','verified_at','updated_at','restrictions','demonstration'] if k in r}
    result.update(available_capacity=r['capacity']-r['occupancy'],contact=r['contact'] if r['publish_contact'] or not public else None,
                  verification_expires_at=r['verified_at']+timedelta(hours=VERIFICATION_HOURS) if r['verified_at'] else None)
    if public:
        result.update(straight_line_km=round(r['straight_line_km'],3) if r.get('straight_line_km') is not None else None,
                      directions_url=directions(r['latitude'],r['longitude'],latitude,longitude),source='Manually assigned and verified by a provisioned prototype administrator; not an affiliation claim')
    else:
        for key in ['revision','notes','publish_contact','verification_notes','authorization_confirmed','entrance_confirmed','usability_confirmed','capacity_confirmed','created_by','updated_by','verified_by','created_at']:
            result[key]=r[key]
        result['publicly_available']=r['status']=='open' and r['verified_at'] is not None and r['verified_at']>now()-timedelta(hours=VERIFICATION_HOURS)
    return result


def get_store():
    try:return ShelterStore()
    except (LocationsUnavailable,SQLAlchemyError):raise HTTPException(503,'Shelter database unavailable') from None


def execute(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except (LocationsUnavailable,SQLAlchemyError):raise HTTPException(503,'Shelter database unavailable; operation not completed') from None


def authorized(request:Request,store=Depends(get_store)):
    config=SecurityConfig();token=request.cookies.get(config.cookie,'')
    if len(token)!=43:raise HTTPException(401,'Administrator login required')
    user=execute(store.session,token)
    if not user:raise HTTPException(401,'Administrator session expired or unavailable')
    if request.method not in ('GET','HEAD'):config.require_csrf(request,token)
    return user


@router.post('/api/admin/login')
def login(payload:Login,request:Request,store=Depends(get_store)):
    config=SecurityConfig();config.same_origin(request)
    if request.headers.get('x-floodpulse-login')!='1' or request.headers.get('content-type','').split(';')[0]!='application/json':
        raise HTTPException(403,'JSON same-origin login header required')
    token,user=execute(store.login,payload.username,payload.password,request.client.host if request.client else 'unknown')
    response=JSONResponse({'user':user,'csrf_token':csrf_token(token),'mode':mode(),'idle_timeout_minutes':30,'absolute_timeout_hours':8})
    config.set_cookie(response,token);return response


@router.get('/api/admin/session')
def session(request:Request,user=Depends(authorized)):
    token=request.cookies[SecurityConfig().cookie]
    return {'user':user,'csrf_token':csrf_token(token),'mode':mode(),'idle_timeout_minutes':30,'absolute_timeout_hours':8}


@router.post('/api/admin/logout')
def logout(request:Request,user=Depends(authorized),store=Depends(get_store)):
    execute(store.logout,request.cookies[SecurityConfig().cookie]);response=JSONResponse({'status':'logged_out'});SecurityConfig().clear_cookie(response);return response


@router.get('/api/admin/shelters')
def admin_list(offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),user=Depends(authorized),store=Depends(get_store)):
    return execute(store.rows,offset=offset,limit=limit)


@router.post('/api/admin/shelters',status_code=201)
def create(payload:ShelterInput,user=Depends(authorized),store=Depends(get_store)):
    return execute(store.save,payload,user)


@router.put('/api/admin/shelters/{identity}')
def edit(identity:uuid.UUID,payload:ShelterInput,user=Depends(authorized),store=Depends(get_store)):
    return execute(store.save,payload,user,str(identity))


@router.get('/api/admin/shelters/{identity}/audit')
def history(identity:uuid.UUID,user=Depends(authorized),store=Depends(get_store)):
    return execute(store.history,str(identity))


@router.get('/api/shelters')
def public_shelters(latitude:float|None=Query(None,ge=-90,le=90,allow_inf_nan=False),longitude:float|None=Query(None,ge=-180,le=180,allow_inf_nan=False),offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),store=Depends(get_store)):
    if (latitude is None)!=(longitude is None):raise HTTPException(422,'Supply both origin coordinates or neither')
    return execute(store.rows,public=True,latitude=latitude,longitude=longitude,offset=offset,limit=limit)
