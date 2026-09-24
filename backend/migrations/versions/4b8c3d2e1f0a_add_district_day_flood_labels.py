"""add district_day_flood_labels table for Phase 3.13 historical flood label integration

Revision ID: 4b8c3d2e1f0a
Revises: 3a7b2c1d4e5f
Create Date: 2026-09-24 23:50:00.000000

Creates the district_day_flood_labels table representing consolidated
historical District x Day flood occurrence labels for ML dataset construction,
derived from India Flood Inventory (IFI v3.0, HydroSenseLab / IMD).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4b8c3d2e1f0a"
down_revision: Union[str, None] = "3a7b2c1d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "district_day_flood_labels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "district_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("districts.id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("flood_occurrence", sa.SmallInteger(), nullable=True),
        sa.Column("event_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "source_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("main_causes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("severities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fatalities", sa.Integer(), nullable=True),
        sa.Column("displaced", sa.Integer(), nullable=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="NO ACTION"),
            nullable=True,
        ),
        sa.Column(
            "data_category",
            sa.String(length=30),
            server_default=sa.text("'HISTORICAL_EVENT'"),
            nullable=False,
        ),
        sa.Column(
            "quality_status",
            sa.String(length=20),
            server_default=sa.text("'VALID'"),
            nullable=False,
        ),
        sa.Column(
            "mapping_status",
            sa.String(length=30),
            server_default=sa.text("'MAPPED'"),
            nullable=False,
        ),
        sa.Column(
            "processing_version",
            sa.String(length=20),
            server_default=sa.text("'3.13.0'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("district_id", "event_date", name="uq_district_day_flood_labels"),
        sa.CheckConstraint(
            "label IN ('FLOOD', 'NO_FLOOD', 'UNKNOWN')",
            name="ck_district_day_label_val",
        ),
        sa.CheckConstraint(
            "flood_occurrence IS NULL OR flood_occurrence IN (0, 1)",
            name="ck_district_day_flood_occ",
        ),
        sa.CheckConstraint(
            "event_count >= 0",
            name="ck_district_day_event_count",
        ),
        sa.CheckConstraint(
            "fatalities IS NULL OR fatalities >= 0",
            name="ck_district_day_fatalities",
        ),
        sa.CheckConstraint(
            "displaced IS NULL OR displaced >= 0",
            name="ck_district_day_displaced",
        ),
        sa.CheckConstraint(
            "quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_district_day_quality_status",
        ),
        sa.CheckConstraint(
            "data_category IN ('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')",
            name="ck_district_day_data_category",
        ),
    )
    op.create_index(
        "ix_district_day_labels_district_id",
        "district_day_flood_labels",
        ["district_id"],
        unique=False,
    )
    op.create_index(
        "ix_district_day_labels_event_date",
        "district_day_flood_labels",
        ["event_date"],
        unique=False,
    )
    op.create_index(
        "ix_district_day_labels_label",
        "district_day_flood_labels",
        ["label"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_district_day_labels_label", table_name="district_day_flood_labels")
    op.drop_index("ix_district_day_labels_event_date", table_name="district_day_flood_labels")
    op.drop_index("ix_district_day_labels_district_id", table_name="district_day_flood_labels")
    op.drop_table("district_day_flood_labels")
