"""Private citizen evidence, deliberately separate from flood training labels."""
from sqlalchemy import (MetaData, Table, Column, String, Float, DateTime, Integer,
                        Boolean, LargeBinary, ForeignKey, CheckConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry

metadata = MetaData()
Table('shelter_admins', metadata, Column('id', UUID(as_uuid=False), primary_key=True))
reports = Table('citizen_reports', metadata,
    Column('id', UUID(as_uuid=False), primary_key=True),
    Column('request_id', UUID(as_uuid=False), nullable=False, unique=True),
    Column('payload_sha256', String(64), nullable=False),
    Column('withdrawal_hash', String(64), nullable=False),
    Column('source', String(30), nullable=False),
    Column('event_type', String(30), nullable=False),
    Column('description', String(2000), nullable=False),
    Column('observed_at', DateTime(timezone=True), nullable=False),
    Column('received_at', DateTime(timezone=True), nullable=False),
    Column('gps_at', DateTime(timezone=True)),
    Column('latitude', Float), Column('longitude', Float), Column('accuracy_m', Float),
    Column('position', Geometry('POINT', srid=4326, spatial_index=False)),
    Column('state', String(30), nullable=False),
    Column('revision', Integer, nullable=False),
    Column('demonstration', Boolean, nullable=False),
    Column('consent_version', String(40), nullable=False),
    Column('image_sha256', String(64)), Column('image_metadata', JSONB(none_as_null=True)),
    Column('reviewed_by', UUID(as_uuid=False), ForeignKey('shelter_admins.id')),
    Column('reviewed_at', DateTime(timezone=True)), Column('review_reason', String(2000)),
    CheckConstraint("source='USER_REPORTED'"),
    CheckConstraint("event_type IN ('flooding','waterlogging','drainage_blockage','other')"),
    CheckConstraint("state IN ('SUBMITTED','UNDER_REVIEW','APPROVED','REJECTED','WITHDRAWN')"),
    CheckConstraint('revision >= 1'),
    CheckConstraint("(state='WITHDRAWN' AND latitude IS NULL AND longitude IS NULL AND position IS NULL AND accuracy_m IS NULL) OR (state<>'WITHDRAWN' AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AND accuracy_m BETWEEN 0 AND 10000000 AND latitude IS NOT NULL AND longitude IS NOT NULL AND accuracy_m IS NOT NULL AND position IS NOT NULL AND ST_X(position)=longitude AND ST_Y(position)=latitude)"),
    CheckConstraint("state NOT IN ('APPROVED','REJECTED') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND length(trim(review_reason))>0)"))
images = Table('citizen_report_images', metadata,
    Column('report_id', UUID(as_uuid=False), ForeignKey(reports.c.id), primary_key=True),
    Column('original', LargeBinary), Column('preview', LargeBinary, nullable=False),
    Column('preview_sha256', String(64), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False))
audit = Table('citizen_report_audit', metadata,
    Column('id', UUID(as_uuid=False), primary_key=True),
    Column('report_id', UUID(as_uuid=False), ForeignKey(reports.c.id), nullable=False),
    Column('actor_id', UUID(as_uuid=False), ForeignKey('shelter_admins.id')),
    Column('at', DateTime(timezone=True), nullable=False),
    Column('action', String(30), nullable=False),
    Column('before_state', String(30)), Column('after_state', String(30), nullable=False),
    Column('reason', String(2000), nullable=False))
Index('ix_citizen_report_position', reports.c.position, postgresql_using='gist')
Index('ix_citizen_report_received', reports.c.demonstration, reports.c.received_at)
Index('ix_citizen_report_image_expiry', images.c.expires_at)
REPORT_TABLES = [reports, images, audit]
