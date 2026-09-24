"""add terrain statistics table

Revision ID: 8c99960a165f
Revises: f75e4ffc014c
Create Date: 2026-09-24 01:20:25.763295
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c99960a165f"
down_revision: Union[str, None] = "f75e4ffc014c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "terrain_statistics",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("terrain_dataset_id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("district_id", sa.UUID(), nullable=True),
        sa.Column("sub_basin_id", sa.UUID(), nullable=True),
        sa.Column("elevation_mean", sa.Float(), nullable=True),
        sa.Column("elevation_median", sa.Float(), nullable=True),
        sa.Column("elevation_min", sa.Float(), nullable=True),
        sa.Column("elevation_max", sa.Float(), nullable=True),
        sa.Column("elevation_std", sa.Float(), nullable=True),
        sa.Column("slope_mean", sa.Float(), nullable=True),
        sa.Column("slope_median", sa.Float(), nullable=True),
        sa.Column("slope_min", sa.Float(), nullable=True),
        sa.Column("slope_max", sa.Float(), nullable=True),
        sa.Column("valid_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("nodata_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("coverage_percentage", sa.Float(), nullable=False),
        sa.Column("dem_version", sa.String(length=50), nullable=False),
        sa.Column("processing_version", sa.String(length=50), nullable=False),
        sa.Column("geometry_version", sa.String(length=50), nullable=False),
        sa.Column("processing_method", sa.String(length=100), nullable=False),
        sa.Column("processing_crs", sa.String(length=150), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("target_type IN ('DISTRICT', 'SUB_BASIN')", name="ck_terrain_stats_target_type"),
        sa.CheckConstraint(
            "(target_type = 'DISTRICT' AND district_id IS NOT NULL AND sub_basin_id IS NULL) OR "
            "(target_type = 'SUB_BASIN' AND sub_basin_id IS NOT NULL AND district_id IS NULL)",
            name="ck_terrain_stats_target_exclusivity",
        ),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"], ondelete="NO ACTION"),
        sa.ForeignKeyConstraint(["sub_basin_id"], ["sub_basins.id"], ondelete="NO ACTION"),
        sa.ForeignKeyConstraint(["terrain_dataset_id"], ["terrain_datasets.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("terrain_dataset_id", "target_type", "district_id", name="uq_terrain_stats_district"),
        sa.UniqueConstraint("terrain_dataset_id", "target_type", "sub_basin_id", name="uq_terrain_stats_sub_basin"),
    )
    op.create_index("ix_terrain_stats_dataset_id", "terrain_statistics", ["terrain_dataset_id"], unique=False)
    op.create_index("ix_terrain_stats_district_id", "terrain_statistics", ["district_id"], unique=False)
    op.create_index("ix_terrain_stats_sub_basin_id", "terrain_statistics", ["sub_basin_id"], unique=False)
    op.create_index("ix_terrain_stats_target_type", "terrain_statistics", ["target_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_terrain_stats_target_type", table_name="terrain_statistics")
    op.drop_index("ix_terrain_stats_sub_basin_id", table_name="terrain_statistics")
    op.drop_index("ix_terrain_stats_district_id", table_name="terrain_statistics")
    op.drop_index("ix_terrain_stats_dataset_id", table_name="terrain_statistics")
    op.drop_table("terrain_statistics")
