"""add authority_level to data_sources and http_status_code to data_ingestion_runs

Revision ID: 3a7b2c1d4e5f
Revises: 8c99960a165f
Create Date: 2026-09-24 20:14:00.000000

Adds the two genuinely missing fields identified in the Mission 001 gap analysis:

1. data_sources.authority_level VARCHAR(30)
   Authority/access tier vocabulary per DATA_SOURCES.md §2 Source Quality Classification:
   CORE, SECONDARY, REFERENCE, PENDING, CREDENTIAL_BLOCKED, NOT_SUITABLE

2. data_ingestion_runs.http_status_code INTEGER (nullable)
   Records the HTTP response code from the upstream source during an ingestion run.
   Nullable because not every ingestion run involves an HTTP request (e.g. file-based,
   in-memory normalization, batch CSV processing).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3a7b2c1d4e5f"
down_revision: Union[str, None] = "8c99960a165f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Authority level vocabulary per DATA_SOURCES.md §2 Source Quality Classification.
AUTHORITY_LEVEL_VALUES = (
    "CORE",
    "SECONDARY",
    "REFERENCE",
    "PENDING",
    "CREDENTIAL_BLOCKED",
    "NOT_SUITABLE",
)


def upgrade() -> None:
    # 1. Add authority_level to data_sources
    op.add_column(
        "data_sources",
        sa.Column(
            "authority_level",
            sa.String(30),
            nullable=True,
            comment=(
                "Authority/access tier per DATA_SOURCES.md §2: "
                "CORE, SECONDARY, REFERENCE, PENDING, CREDENTIAL_BLOCKED, NOT_SUITABLE"
            ),
        ),
    )
    op.create_check_constraint(
        "ck_data_source_authority_level",
        "data_sources",
        "authority_level IS NULL OR authority_level IN "
        "('CORE', 'SECONDARY', 'REFERENCE', 'PENDING', 'CREDENTIAL_BLOCKED', 'NOT_SUITABLE')",
    )

    # 2. Add http_status_code to data_ingestion_runs
    op.add_column(
        "data_ingestion_runs",
        sa.Column(
            "http_status_code",
            sa.Integer(),
            nullable=True,
            comment="HTTP response status code from the upstream source request (100-599), or NULL if not HTTP-based.",
        ),
    )
    op.create_check_constraint(
        "ck_ingestion_run_http_status_code",
        "data_ingestion_runs",
        "http_status_code IS NULL OR (http_status_code >= 100 AND http_status_code <= 599)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ingestion_run_http_status_code", "data_ingestion_runs", type_="check"
    )
    op.drop_column("data_ingestion_runs", "http_status_code")

    op.drop_constraint(
        "ck_data_source_authority_level", "data_sources", type_="check"
    )
    op.drop_column("data_sources", "authority_level")
