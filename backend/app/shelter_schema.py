"""Shelter-only schema; public directory/research tables are independent."""
from geoalchemy2 import Geometry
from sqlalchemy import (MetaData,Table,Column,String,Integer,Boolean,Float,DateTime,ForeignKey,
                        ForeignKeyConstraint,CheckConstraint,Index,func)
from sqlalchemy.dialects.postgresql import JSONB,UUID

metadata=MetaData()
admins=Table('shelter_admins',metadata,
    Column('id',UUID(as_uuid=False),primary_key=True),Column('username',String(64),nullable=False,unique=True),
    Column('password_hash',String(512),nullable=False),Column('active',Boolean,nullable=False,server_default='true'),
    Column('created_at',DateTime(timezone=True),nullable=False,server_default=func.now()))
sessions=Table('shelter_sessions',metadata,
    Column('token_hash',String(64),primary_key=True),Column('admin_id',UUID(as_uuid=False),ForeignKey(admins.c.id),nullable=False),
    Column('created_at',DateTime(timezone=True),nullable=False),Column('expires_at',DateTime(timezone=True),nullable=False),
    Column('last_seen_at',DateTime(timezone=True),nullable=False))
limits=Table('shelter_login_limits',metadata,
    Column('key',String(64),primary_key=True),Column('window_start',DateTime(timezone=True),nullable=False),
    Column('attempts',Integer,nullable=False),CheckConstraint('attempts >= 0'))
shelters=Table('emergency_shelters',metadata,
    Column('id',UUID(as_uuid=False),primary_key=True),Column('name',String(200),nullable=False),Column('address',String(1000),nullable=False),
    Column('district_version',String(100),nullable=False),Column('district_id',String(100),nullable=False),
    Column('latitude',Float),Column('longitude',Float),Column('entrance',Geometry('POINT',srid=4326,spatial_index=False)),
    Column('capacity',Integer,nullable=False),Column('occupancy',Integer,nullable=False),
    Column('water',String(20),nullable=False),Column('toilets',String(20),nullable=False),Column('accessibility',String(2000),nullable=False),
    Column('contact',String(200)),Column('publish_contact',Boolean,nullable=False),
    Column('status',String(20),nullable=False),Column('authorization_confirmed',Boolean,nullable=False),
    Column('entrance_confirmed',Boolean,nullable=False),Column('usability_confirmed',Boolean,nullable=False),Column('capacity_confirmed',Boolean,nullable=False),
    Column('verification_notes',String(2000),nullable=False),Column('verified_at',DateTime(timezone=True)),
    Column('verified_by',UUID(as_uuid=False),ForeignKey(admins.c.id)),
    Column('created_by',UUID(as_uuid=False),ForeignKey(admins.c.id),nullable=False),Column('updated_by',UUID(as_uuid=False),ForeignKey(admins.c.id),nullable=False),
    Column('created_at',DateTime(timezone=True),nullable=False),Column('updated_at',DateTime(timezone=True),nullable=False),
    Column('demonstration',Boolean,nullable=False),Column('revision',Integer,nullable=False),Column('notes',String(2000),nullable=False),Column('restrictions',String(2000),nullable=False),
    ForeignKeyConstraint(['district_version','district_id'],['location_directory_districts.version','location_directory_districts.id']),
    CheckConstraint("status IN ('pending','open','full','closed')"),
    CheckConstraint('capacity BETWEEN 1 AND 100000 AND occupancy BETWEEN 0 AND capacity AND revision >= 1'),
    CheckConstraint("water IN ('yes','no','unknown') AND toilets IN ('yes','no','unknown')"),
    CheckConstraint("(latitude IS NULL AND longitude IS NULL AND entrance IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND entrance IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AND ST_X(entrance)=longitude AND ST_Y(entrance)=latitude)"),
    CheckConstraint("status NOT IN ('open','full') OR (latitude IS NOT NULL AND longitude IS NOT NULL AND entrance IS NOT NULL AND authorization_confirmed AND entrance_confirmed AND usability_confirmed AND capacity_confirmed AND verified_at IS NOT NULL AND verified_by IS NOT NULL AND length(trim(verification_notes)) > 0)"),
    CheckConstraint("status <> 'open' OR occupancy < capacity"),CheckConstraint("status <> 'full' OR occupancy = capacity"))
audit=Table('shelter_audit',metadata,
    Column('id',UUID(as_uuid=False),primary_key=True),Column('shelter_id',UUID(as_uuid=False),ForeignKey(shelters.c.id),nullable=False),
    Column('admin_id',UUID(as_uuid=False),ForeignKey(admins.c.id),nullable=False),Column('at',DateTime(timezone=True),nullable=False),
    Column('action',String(20),nullable=False),Column('before',JSONB),Column('after',JSONB,nullable=False))
# Reference-only metadata stub for SQLAlchemy FK ordering; no DDL is emitted for it.
Table('location_directory_districts',metadata,Column('version',String(100),primary_key=True),Column('id',String(100),primary_key=True))
Index('ix_shelter_entrance',shelters.c.entrance,postgresql_using='gist')
Index('ix_shelter_available',shelters.c.status,shelters.c.verified_at)
Index('ix_shelter_audit_history',audit.c.shelter_id,audit.c.at)
Index('ix_shelter_session_expiry',sessions.c.expires_at)
SHELTER_TABLES=[admins,sessions,limits,shelters,audit]
