"""Separate manual/GPS position provenance without altering prior report records."""
from alembic import op
from sqlalchemy.schema import CreateTable
from app.report_position_schema import POSITION_TABLES
revision='0006_report_position_provenance'
down_revision='0005_telegram_subscriptions'
branch_labels=None
depends_on=None


def upgrade():
    for table in POSITION_TABLES:op.execute(CreateTable(table))


def downgrade():
    for table in reversed(POSITION_TABLES):op.drop_table(table.name)
