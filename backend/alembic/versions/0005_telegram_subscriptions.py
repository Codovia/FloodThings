"""Add explicit private Telegram opt-in/out receipts without changing notices."""
from alembic import op
from sqlalchemy.schema import CreateTable
from app.subscription_schema import SUBSCRIPTION_TABLES
revision='0005_telegram_subscriptions'
down_revision='0004_citizen_reports'
branch_labels=None
depends_on=None


def upgrade():
    for table in SUBSCRIPTION_TABLES:
        op.execute(CreateTable(table))


def downgrade():
    for table in reversed(SUBSCRIPTION_TABLES):
        op.drop_table(table.name)
