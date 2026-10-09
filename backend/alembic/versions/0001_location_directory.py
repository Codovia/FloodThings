"""Initial public directory tables. Existing schema and extensions are preserved."""
from alembic import op
from sqlalchemy import text
from sqlalchemy.schema import CreateTable, CreateIndex

from geoalchemy2 import Geometry
from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, Float,
                        DateTime, ForeignKey, ForeignKeyConstraint, CheckConstraint,
                        UniqueConstraint, Index, func)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
versions = Table('location_directory_versions', metadata,
    Column('version', String(100), primary_key=True), Column('header', JSONB, nullable=False),
    Column('source_manifest', JSONB, nullable=False), Column('directory_sha256', String(64), nullable=False),
    Column('manifest_sha256', String(64), nullable=False), Column('content_sha256', String(64), nullable=False),
    Column('manifest_content_sha256', String(64), nullable=False),
    Column('imported_at', DateTime(timezone=True), nullable=False, server_default=func.now()))
districts = Table('location_directory_districts', metadata,
    Column('version', String(100), ForeignKey(versions.c.version), primary_key=True),
    Column('id', String(100), primary_key=True), Column('name', String(200), nullable=False),
    Column('ordinal', Integer, nullable=False), Column('record', JSONB, nullable=False),
    UniqueConstraint('version', 'ordinal'), CheckConstraint("id LIKE 'nic:%'"),
    CheckConstraint("record->>'id' = id AND record->>'name' = name"))
localities = Table('location_directory_localities', metadata,
    Column('version', String(100), primary_key=True), Column('id', String(100), primary_key=True),
    Column('district_id', String(100), nullable=False), Column('name', String(200), nullable=False),
    Column('ordinal', Integer, nullable=False), Column('selectable', Boolean, nullable=False),
    Column('coordinate_status', String(100), nullable=False), Column('latitude', Float), Column('longitude', Float),
    Column('point', Geometry('POINT', srid=4326, spatial_index=False)), Column('record', JSONB, nullable=False),
    ForeignKeyConstraint(['version', 'district_id'], [districts.c.version, districts.c.id]),
    UniqueConstraint('version', 'ordinal'),
    CheckConstraint("record->>'id' = id AND record->>'district_id' = district_id AND record->>'name' = name AND (record->>'selectable')::boolean = selectable AND record->>'coordinate_status' = coordinate_status"),
    CheckConstraint("(selectable AND coordinate_status = 'verified_osm_place_point' AND latitude IS NOT NULL AND longitude IS NOT NULL AND point IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AND ST_X(point) = longitude AND ST_Y(point) = latitude AND record->'coordinates' <> 'null'::jsonb AND (record->'coordinates'->>'latitude')::double precision = latitude AND (record->'coordinates'->>'longitude')::double precision = longitude AND record->'coordinate_source'->>'license' = 'ODbL 1.0') OR (NOT selectable AND coordinate_status = 'unavailable' AND latitude IS NULL AND longitude IS NULL AND point IS NULL AND record->'coordinates' = 'null'::jsonb)"))
identifiers = Table('location_directory_identifiers', metadata,
    Column('version', String(100), primary_key=True), Column('identifier', String(100), primary_key=True),
    Column('locality_id', String(100), nullable=False),
    ForeignKeyConstraint(['version', 'locality_id'], [localities.c.version, localities.c.id]),
    CheckConstraint("identifier NOT LIKE 'nic:%'"))
active = Table('location_directory_active', metadata,
    Column('singleton', Integer, primary_key=True), CheckConstraint('singleton = 1'),
    Column('version', String(100), ForeignKey(versions.c.version), nullable=False))
Index('ix_location_district_name', districts.c.version, districts.c.name)
Index('ix_location_locality_district', localities.c.version, localities.c.district_id)
Index('ix_location_locality_name', localities.c.version, localities.c.name)
Index('ix_location_point', localities.c.point, postgresql_using='gist')

revision = '0001_location_directory'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if not op.get_bind().execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='postgis')")).scalar():
        raise RuntimeError('PostGIS is required. An authorized database administrator must enable it before migration.')
    # Explicit Alembic operations; not unmanaged create_all().
    for table in metadata.sorted_tables:
        op.execute(CreateTable(table))
        for index in sorted(table.indexes, key=lambda i: i.name):
            op.execute(CreateIndex(index))


def downgrade():
    for table in reversed(metadata.sorted_tables):
        op.drop_table(table.name)
    # Shared PostGIS extension and unrelated tables are deliberately retained.
