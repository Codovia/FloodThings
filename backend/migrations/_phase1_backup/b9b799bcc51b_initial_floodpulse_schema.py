"""initial floodpulse schema

Creates 34 application tables for the FloodPulse system:
    - Administrative geography: states, districts, taluks, localities
    - Hydrology: river_basins, sub_basins, rivers, river_stations,
                 river_observations, river_forecasts, reservoirs,
                 reservoir_observations
    - Weather: weather_observations, rainfall_observations,
              weather_forecasts
    - Flood: flood_observations, flood_events, flood_hazard_zones
    - Terrain: land_covers, water_bodies, terrain_datasets
    - Prediction: prediction_grid_cells, feature_snapshots,
                  ml_dataset_versions, ml_models, flood_predictions
    - Emergency: emergency_facilities, community_reports
    - Alerts: alerts, telegram_subscriptions
    - System: data_sources, data_ingestion_runs, users, audit_logs

All spatial columns use PostGIS geometry with SRID 4326 (EPSG:4326).
No PostGIS system tables are modified.

Revision ID: b9b799bcc51b
Revises:
Create Date: 2026-09-17 09:38:22.595143
"""

from typing import Sequence, Union

import geoalchemy2  # noqa: F401 — registers PostGIS types
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b9b799bcc51b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---- All FloodPulse application tables (in dependency order) ----
_APPLICATION_TABLES = [
    'river_observations', 'river_forecasts', 'reservoir_observations',
    'flood_predictions', 'feature_snapshots', 'telegram_subscriptions',
    'river_stations', 'reservoirs', 'prediction_grid_cells', 'localities',
    'emergency_facilities', 'weather_observations', 'weather_forecasts',
    'water_bodies', 'rivers', 'taluks', 'rainfall_observations',
    'land_covers', 'alerts', 'sub_basins', 'ml_models', 'districts',
    'data_ingestion_runs', 'community_reports', 'audit_logs',
    'users', 'terrain_datasets', 'states', 'river_basins',
    'ml_dataset_versions', 'flood_observations', 'flood_hazard_zones',
    'flood_events', 'data_sources',
]


def upgrade() -> None:
    # --- Root tables (no FK dependencies) ---

    op.create_table('data_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('expected_update_interval', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table('flood_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('severity', sa.String(50), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('provenance', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_flood_events_start_date', 'flood_events', ['start_date'])

    op.create_table('flood_hazard_zones',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('hazard_level', sa.String(50), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('methodology', sa.Text(), nullable=True),
        sa.Column('reference_period', sa.String(50), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('flood_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('source_record_id', sa.String(100), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('duration_days', sa.Integer(), nullable=True),
        sa.Column('cause', sa.String(200), nullable=True),
        sa.Column('severity', sa.String(50), nullable=True),
        sa.Column('area_affected_km2', sa.Float(), nullable=True),
        sa.Column('casualties', sa.Integer(), nullable=True),
        sa.Column('damage_description', sa.Text(), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_flood_obs_start_date', 'flood_observations', ['start_date'])
    op.create_index('ix_flood_obs_source', 'flood_observations', ['source'])

    op.create_table('ml_dataset_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('feature_schema', postgresql.JSON(), nullable=True),
        sa.Column('label_definition', sa.Text(), nullable=True),
        sa.Column('temporal_range_start', sa.Date(), nullable=True),
        sa.Column('temporal_range_end', sa.Date(), nullable=True),
        sa.Column('spatial_coverage', sa.Text(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('class_balance', postgresql.JSON(), nullable=True),
        sa.Column('provenance', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version'),
    )

    op.create_table('river_basins',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('basin_code', sa.String(20), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('basin_code'),
    )

    op.create_table('states',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('state_code', sa.String(10), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('state_code'),
    )

    op.create_table('terrain_datasets',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('resolution', sa.String(50), nullable=True),
        sa.Column('crs', sa.String(20), nullable=True),
        sa.Column('acquisition_date', sa.Date(), nullable=True),
        sa.Column('processing_method', sa.Text(), nullable=True),
        sa.Column('spatial_extent', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('role', sa.String(30), server_default=sa.text("'citizen'"), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )

    # --- Second tier (FK to root tables) ---

    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target', sa.String(200), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('details', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
    )
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])

    op.create_table('community_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reporter_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('report_type', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('photos', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(20), server_default=sa.text("'UNVERIFIED'"), nullable=False),
        sa.Column('moderator_notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reporter_id'], ['users.id']),
    )
    op.create_index('ix_community_reports_reported_at', 'community_reports', ['reported_at'])

    op.create_table('data_ingestion_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('data_source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('records_fetched', sa.Integer(), nullable=True),
        sa.Column('records_inserted', sa.Integer(), nullable=True),
        sa.Column('records_rejected', sa.Integer(), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('processing_version', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id']),
    )
    op.create_index('ix_ingestion_runs_source_id', 'data_ingestion_runs', ['data_source_id'])
    op.create_index('ix_ingestion_runs_started_at', 'data_ingestion_runs', ['started_at'])

    op.create_table('districts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('district_code_lgd', sa.String(20), nullable=True),
        sa.Column('state_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('centroid', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('district_code_lgd'),
        sa.ForeignKeyConstraint(['state_id'], ['states.id']),
    )
    op.create_index('ix_districts_state_id', 'districts', ['state_id'])

    op.create_table('ml_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('algorithm', sa.String(100), nullable=True),
        sa.Column('dataset_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('hyperparameters', postgresql.JSON(), nullable=True),
        sa.Column('training_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evaluation_metrics', postgresql.JSON(), nullable=True),
        sa.Column('artifact_path', sa.String(500), nullable=True),
        sa.Column('feature_schema', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version'),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['ml_dataset_versions.id']),
    )

    op.create_table('sub_basins',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sub_basin_code', sa.String(20), nullable=True),
        sa.Column('basin_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sub_basin_code'),
        sa.ForeignKeyConstraint(['basin_id'], ['river_basins.id']),
    )
    op.create_index('ix_sub_basins_basin_id', 'sub_basins', ['basin_id'])

    # --- Third tier (FK to second-tier tables) ---

    op.create_table('alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('alert_type', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('issued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('deduplication_key', sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deduplication_key'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_alerts_issued_at', 'alerts', ['issued_at'])
    op.create_index('ix_alerts_district_id', 'alerts', ['district_id'])
    op.create_index('ix_alerts_type', 'alerts', ['alert_type'])

    op.create_table('land_covers',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('classification', sa.String(100), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('reference_date', sa.Date(), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )

    op.create_table('rainfall_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('observation_date', sa.Date(), nullable=False),
        sa.Column('rainfall_mm', sa.Float(), nullable=True),
        sa.Column('measurement_period', sa.String(20), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_record_id', sa.String(100), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('quality', sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_rainfall_obs_district_date', 'rainfall_observations', ['district_id', 'observation_date'])

    op.create_table('rivers',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sub_basin_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTILINESTRING', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['sub_basin_id'], ['sub_basins.id']),
    )
    op.create_index('ix_rivers_sub_basin_id', 'rivers', ['sub_basin_id'])

    op.create_table('taluks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('taluk_code', sa.String(20), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('taluk_code'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_taluks_district_id', 'taluks', ['district_id'])

    op.create_table('water_bodies',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(150), nullable=True),
        sa.Column('water_body_type', sa.String(50), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_water_bodies_district_id', 'water_bodies', ['district_id'])

    op.create_table('weather_forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('forecast_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('wind_speed_mps', sa.Float(), nullable=True),
        sa.Column('rainfall_mm', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('model_method', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_weather_fcst_district_for', 'weather_forecasts', ['district_id', 'forecast_for'])

    op.create_table('weather_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('wind_speed_mps', sa.Float(), nullable=True),
        sa.Column('wind_direction_deg', sa.Float(), nullable=True),
        sa.Column('pressure_hpa', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_record_id', sa.String(100), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('quality', sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    )
    op.create_index('ix_weather_obs_district_observed', 'weather_observations', ['district_id', 'observed_at'])

    # --- Fourth tier ---

    op.create_table('emergency_facilities',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('facility_type', sa.String(50), nullable=False),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('taluk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('contact_info', sa.Text(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('verification_status', sa.String(20), nullable=True),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
        sa.ForeignKeyConstraint(['taluk_id'], ['taluks.id']),
    )
    op.create_index('ix_emergency_fac_district_id', 'emergency_facilities', ['district_id'])
    op.create_index('ix_emergency_fac_type', 'emergency_facilities', ['facility_type'])

    op.create_table('localities',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('locality_code', sa.String(20), nullable=True),
        sa.Column('taluk_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('centroid', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('locality_code'),
        sa.ForeignKeyConstraint(['taluk_id'], ['taluks.id']),
    )
    op.create_index('ix_localities_taluk_id', 'localities', ['taluk_id'])

    op.create_table('prediction_grid_cells',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('taluk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
        sa.ForeignKeyConstraint(['taluk_id'], ['taluks.id']),
    )
    op.create_index('ix_pred_grid_district_id', 'prediction_grid_cells', ['district_id'])

    op.create_table('reservoirs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('reservoir_code', sa.String(50), nullable=True),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('full_reservoir_level_m', sa.Float(), nullable=True),
        sa.Column('capacity_mcm', sa.Float(), nullable=True),
        sa.Column('river_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('operating_agency', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reservoir_code'),
        sa.ForeignKeyConstraint(['river_id'], ['rivers.id']),
    )
    op.create_index('ix_reservoirs_river_id', 'reservoirs', ['river_id'])

    op.create_table('river_stations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('station_code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('river_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('operating_agency', sa.String(100), nullable=True),
        sa.Column('data_source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('station_code'),
        sa.ForeignKeyConstraint(['river_id'], ['rivers.id']),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id']),
    )
    op.create_index('ix_river_stations_river_id', 'river_stations', ['river_id'])

    op.create_table('telegram_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('chat_id', sa.String(50), nullable=False),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('taluk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
        sa.ForeignKeyConstraint(['taluk_id'], ['taluks.id']),
    )
    op.create_index('ix_telegram_sub_district_id', 'telegram_subscriptions', ['district_id'])

    # --- Fifth tier (observations / time-series) ---

    op.create_table('feature_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('grid_cell_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('feature_date', sa.Date(), nullable=False),
        sa.Column('features', postgresql.JSON(), nullable=True),
        sa.Column('dataset_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['grid_cell_id'], ['prediction_grid_cells.id']),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['ml_dataset_versions.id']),
    )
    op.create_index('ix_feat_snap_cell_date', 'feature_snapshots', ['grid_cell_id', 'feature_date'])

    op.create_table('flood_predictions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('grid_cell_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prediction_for', sa.Date(), nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=True),
        sa.Column('probability', sa.Float(), nullable=True),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confidence_indicators', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['grid_cell_id'], ['prediction_grid_cells.id']),
        sa.ForeignKeyConstraint(['model_id'], ['ml_models.id']),
    )
    op.create_index('ix_flood_pred_cell_for', 'flood_predictions', ['grid_cell_id', 'prediction_for'])

    op.create_table('reservoir_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reservoir_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('storage_mcm', sa.Float(), nullable=True),
        sa.Column('level_m', sa.Float(), nullable=True),
        sa.Column('inflow_m3s', sa.Float(), nullable=True),
        sa.Column('outflow_m3s', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_record_id', sa.String(100), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reservoir_id'], ['reservoirs.id']),
    )
    op.create_index('ix_reservoir_obs_reservoir_observed', 'reservoir_observations', ['reservoir_id', 'observed_at'])

    op.create_table('river_forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('forecast_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('water_level_m', sa.Float(), nullable=True),
        sa.Column('discharge_m3s', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('model_method', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['station_id'], ['river_stations.id']),
    )
    op.create_index('ix_river_fcst_station_for', 'river_forecasts', ['station_id', 'forecast_for'])

    op.create_table('river_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('water_level_m', sa.Float(), nullable=True),
        sa.Column('discharge_m3s', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_record_id', sa.String(100), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('quality', sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['station_id'], ['river_stations.id']),
    )
    op.create_index('ix_river_obs_station_observed', 'river_observations', ['station_id', 'observed_at'])


def downgrade() -> None:
    # Drop in reverse dependency order.
    for table_name in _APPLICATION_TABLES:
        op.drop_table(table_name)
