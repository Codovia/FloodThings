"""Versioned public directory persistence; no weather or research-data writes."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from geoalchemy2 import Geometry
from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, Float,
                        DateTime, ForeignKey, ForeignKeyConstraint, CheckConstraint,
                        UniqueConstraint, Index, create_engine, select, text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from .locations import LocationStore, LocationsUnavailable, validate_directory, require

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


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def database_engine(url=None):
    url = url or os.environ.get('DATABASE_URL')
    if not url:
        raise LocationsUnavailable('Location database is not configured')
    # Require the existing PostgreSQL driver; never silently use another database.
    from sqlalchemy.engine import make_url
    try:
        parsed = make_url(url)
        require(parsed.drivername in ('postgresql', 'postgresql+psycopg'), 'Location database must use PostgreSQL/psycopg')
        return create_engine(parsed.set(drivername='postgresql+psycopg'), hide_parameters=True,
            pool_size=3, max_overflow=2, pool_timeout=5, pool_pre_ping=True,
            connect_args={'connect_timeout': 5, 'options': '-c statement_timeout=5000'})
    except LocationsUnavailable:
        raise
    except (ValueError, SQLAlchemyError) as exc:
        raise LocationsUnavailable('Location database configuration is invalid') from exc


@lru_cache(maxsize=1)
def configured_engine():
    return database_engine()


def dispose_engine():
    if configured_engine.cache_info().currsize:
        configured_engine().dispose()
        configured_engine.cache_clear()


def reconstruct(connection, version):
    source = connection.execute(select(versions).where(versions.c.version == version)).mappings().one()
    district_rows = connection.execute(select(districts.c.record).where(districts.c.version == version).order_by(districts.c.ordinal).limit(51)).scalars().all()
    place_rows = connection.execute(select(localities.c.record).where(localities.c.version == version).order_by(localities.c.ordinal).limit(1001)).scalars().all()
    require(len(district_rows) <= 50 and len(place_rows) <= 1000, 'Location database exceeds reviewed coverage bounds')
    data = {**source['header'], 'districts': district_rows, 'localities': place_rows}
    require(content_hash(data) == source['content_sha256'] and content_hash(source['source_manifest']) == source['manifest_content_sha256'], 'Location database integrity check failed')
    validate_directory(data, version)
    require(source['source_manifest']['files']['directory.json']['sha256'] == source['directory_sha256'], 'Location source checksum mismatch')
    expected_ids = {(r['id'], r['id']) for r in place_rows} | {(a, r['id']) for r in place_rows for a in r.get('identifier_aliases', [])}
    actual_ids = set(connection.execute(select(identifiers.c.identifier, identifiers.c.locality_id).where(identifiers.c.version == version)))
    require(actual_ids == expected_ids, 'Location identifiers are inconsistent')
    return data


class DatabaseLocationStore:
    def __init__(self, engine=None):
        self.engine = engine

    def load(self):
        try:
            engine = self.engine or configured_engine()
            with engine.connect().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True) as connection:
                with connection.begin():
                    version = connection.execute(select(active.c.version).where(active.c.singleton == 1)).scalar_one_or_none()
                    require(version is not None, 'No active location directory is imported')
                    return reconstruct(connection, version)
        except LocationsUnavailable:
            raise
        except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
            raise LocationsUnavailable('Location database is unavailable or invalid; no file fallback was used') from exc


def import_directory(engine, directory, activate=True):
    """Validate first; atomically import/activate. An existing version is immutable."""
    path = Path(directory)
    data = LocationStore(path).load()
    raw = (path / 'directory.json').read_bytes()
    manifest_raw = (path / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    fingerprints = dict(directory_sha256=hashlib.sha256(raw).hexdigest(), manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(), content_sha256=content_hash(data), manifest_content_sha256=content_hash(manifest))
    require(len(raw) < 512000 and len(manifest_raw) < 128000 and json.loads(raw) == data,
            'Source changed during import validation')
    require(manifest['version'] == data['version'] and manifest['files']['directory.json'] == {'sha256': fingerprints['directory_sha256'], 'bytes': len(raw)}
            and manifest['district_count'] == len(data['districts']) and manifest['locality_count'] == len(data['localities']),
            'Source manifest changed during import validation')
    version = data['version']
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(714206)'))
        existing = connection.execute(select(versions).where(versions.c.version == version)).mappings().one_or_none()
        if existing:
            require(all(existing[k] == v for k, v in fingerprints.items()), 'Existing directory version conflicts with source; create a reviewed new version')
            require(reconstruct(connection, version) == data, 'Existing directory content differs')
        else:
            connection.execute(versions.insert().values(version=version, header={k: v for k, v in data.items() if k not in ('districts', 'localities')}, source_manifest=manifest, **fingerprints))
            for ordinal, row in enumerate(data['districts']):
                connection.execute(districts.insert().values(version=version, id=row['id'], name=row['name'], ordinal=ordinal, record=row))
            for ordinal, row in enumerate(data['localities']):
                point = row['coordinates']
                connection.execute(localities.insert().values(version=version, id=row['id'], district_id=row['district_id'], name=row['name'], ordinal=ordinal,
                    record=row, selectable=row['selectable'], coordinate_status=row['coordinate_status'], latitude=point['latitude'] if point else None, longitude=point['longitude'] if point else None,
                    point=func.ST_SetSRID(func.ST_MakePoint(point['longitude'], point['latitude']), 4326) if point else None))
                for identity in [row['id'], *row.get('identifier_aliases', [])]:
                    connection.execute(identifiers.insert().values(version=version, identifier=identity, locality_id=row['id']))
            require(reconstruct(connection, version) == data, 'Imported directory failed reproduction')
        if activate:
            from sqlalchemy.dialects.postgresql import insert
            connection.execute(insert(active).values(singleton=1, version=version).on_conflict_do_update(index_elements=[active.c.singleton], set_={'version': version}))
    return {'version': version, 'status': 'already_imported' if existing else 'imported', 'active': activate,
            'districts': len(data['districts']), 'localities': len(data['localities']), 'selectable': sum(r['selectable'] for r in data['localities'])}
