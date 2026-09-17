"""add data_category column for semantic provenance classification

Revision ID: ccfc6a6b5d06
Revises: 7eee813798dd
Create Date: 2026-09-17 23:01:17.981317
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
import geoalchemy2



# revision identifiers, used by Alembic.
revision: str = 'ccfc6a6b5d06'
down_revision: Union[str, None] = '7eee813798dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VALID_CATEGORIES = "('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')"
TABLES_WITH_CATEGORY = [
    'weather_observations',
    'rainfall_observations',
    'river_observations',
    'reservoir_observations',
    'flood_observations',
]


def upgrade() -> None:
    # 1. Add data_category column to all five observation tables
    for table in TABLES_WITH_CATEGORY:
        op.add_column(table, sa.Column('data_category', sa.String(length=30), nullable=True))

    # 2. Add CHECK constraints
    for table in TABLES_WITH_CATEGORY:
        short = table.replace('_observations', '_obs')
        op.create_check_constraint(
            f"ck_{short}_data_category",
            table,
            f"data_category IS NULL OR data_category IN {VALID_CATEGORIES}",
        )

    # 3. Backfill existing records with scientifically correct data_category
    conn = op.get_bind()

    # 3a. Open-Meteo operational past → MODEL_OUTPUT (NWP model nowcast/hindcast)
    conn.execute(sa.text(
        "UPDATE weather_observations SET data_category = 'MODEL_OUTPUT' "
        "WHERE source_record_id LIKE 'openmeteo_obs_%'"
    ))
    conn.execute(sa.text(
        "UPDATE rainfall_observations SET data_category = 'MODEL_OUTPUT' "
        "WHERE source_record_id LIKE 'openmeteo_rain_%'"
    ))

    # 3b. Open-Meteo historical archive → REANALYSIS (ERA5 reconstruction)
    conn.execute(sa.text(
        "UPDATE weather_observations SET data_category = 'REANALYSIS' "
        "WHERE source_record_id LIKE 'openmeteo_hist_obs_%'"
    ))
    conn.execute(sa.text(
        "UPDATE rainfall_observations SET data_category = 'REANALYSIS' "
        "WHERE source_record_id LIKE 'openmeteo_hist_rain_%'"
    ))

    # 3c. CWC river gauge → OBSERVATION (physical in-situ measurement)
    conn.execute(sa.text(
        "UPDATE river_observations SET data_category = 'OBSERVATION' "
        "WHERE source_record_id LIKE 'cwc_%'"
    ))

    # 3d. NWIC reservoir telemetry → OBSERVATION (physical manual reading)
    conn.execute(sa.text(
        "UPDATE reservoir_observations SET data_category = 'OBSERVATION' "
        "WHERE source_record_id LIKE 'nwic_res_%'"
    ))

    # 3e. IFI v3.0 flood records → HISTORICAL_EVENT (documented disaster occurrence)
    conn.execute(sa.text(
        "UPDATE flood_observations SET data_category = 'HISTORICAL_EVENT' "
        "WHERE source_record_id LIKE 'ifi_%'"
    ))

    # 4. Clean test residue from production tables
    # Remove test fixture records that leaked from integration tests
    conn.execute(sa.text(
        "DELETE FROM weather_observations WHERE location_reference IN ('Test Loc', 'Idemp Loc')"
    ))
    conn.execute(sa.text(
        "DELETE FROM rainfall_observations WHERE station_id IN ('Test Loc', 'Idemp Loc')"
    ))
    conn.execute(sa.text(
        "DELETE FROM river_observations WHERE source_record_id LIKE '%IDEMP%'"
    ))
    conn.execute(sa.text(
        "DELETE FROM reservoir_observations WHERE source_record_id LIKE '%IDEMP%'"
    ))
    conn.execute(sa.text(
        "DELETE FROM reservoirs WHERE name = 'IDEMP_RES'"
    ))
    conn.execute(sa.text(
        "DELETE FROM river_stations WHERE station_code = 'IDEMP_STN'"
    ))


def downgrade() -> None:
    # Drop CHECK constraints first
    for table in TABLES_WITH_CATEGORY:
        short = table.replace('_observations', '_obs')
        op.drop_constraint(f"ck_{short}_data_category", table, type_='check')

    # Drop columns
    for table in TABLES_WITH_CATEGORY:
        op.drop_column(table, 'data_category')
