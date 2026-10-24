"""Add private moderated citizen evidence; preserve existing tables."""
from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex
from app.report_schema import REPORT_TABLES

revision = '0004_citizen_reports'
down_revision = '0003_admin_notifications'
branch_labels = None
depends_on = None


def upgrade():
    for table in REPORT_TABLES:
        op.execute(CreateTable(table))
        for index in sorted(table.indexes, key=lambda i: i.name):
            op.execute(CreateIndex(index))


def downgrade():
    for table in reversed(REPORT_TABLES):
        op.drop_table(table.name)
