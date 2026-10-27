"""Add public Telegram district subscriptions and per-district alert delivery records (no change to notices)."""
from alembic import op
from sqlalchemy.schema import CreateIndex, CreateTable
from app.district_alert_schema import DISTRICT_ALERT_TABLES
revision='0007_telegram_district_alerts'
down_revision='0006_report_position_provenance'
branch_labels=None
depends_on=None


def upgrade():
    for table in DISTRICT_ALERT_TABLES:
        op.execute(CreateTable(table))
        for index in table.indexes:
            op.execute(CreateIndex(index))


def downgrade():
    for table in reversed(DISTRICT_ALERT_TABLES):
        op.drop_table(table.name)
