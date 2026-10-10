"""Frozen notification schema, following the existing shelter migration."""
from sqlalchemy import MetaData, Table, Column, String, DateTime, Boolean, Integer, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

metadata = MetaData()
# Reference-only tables are excluded from notification DDL.
Table('shelter_admins', metadata, Column('id', UUID(as_uuid=False), primary_key=True))
Table('emergency_shelters', metadata, Column('id', UUID(as_uuid=False), primary_key=True))
notifications = Table('admin_notifications', metadata,
    Column('id', UUID(as_uuid=False), primary_key=True),
    Column('request_id', UUID(as_uuid=False), nullable=False),
    Column('created_by', UUID(as_uuid=False), ForeignKey('shelter_admins.id'), nullable=False),
    Column('destination_id', String(40), nullable=False),
    Column('destination_label', String(80), nullable=False),
    Column('destination_fingerprint', String(64), nullable=False),
    Column('kind', String(20), nullable=False),
    Column('text', String(4096), nullable=False),
    Column('content_sha256', String(64), nullable=False),
    Column('shelter_id', UUID(as_uuid=False), ForeignKey('emergency_shelters.id')),
    Column('shelter_snapshot', JSONB(none_as_null=True)),
    Column('demonstration', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('confirmed_at', DateTime(timezone=True)),
    Column('confirmed_by', UUID(as_uuid=False), ForeignKey('shelter_admins.id')),
    Column('attempted_at', DateTime(timezone=True)),
    Column('completed_at', DateTime(timezone=True)),
    Column('status', String(30), nullable=False),
    Column('result_code', String(60)),
    Column('http_status', Integer),
    Column('telegram_error_code', Integer),
    Column('telegram_message_id', Integer),
    UniqueConstraint('created_by', 'request_id', name='uq_notification_request'),
    CheckConstraint("kind IN ('informational','emergency')"),
    CheckConstraint("status IN ('draft','sending','accepted','rejected','delivery_unknown')"),
    CheckConstraint("length(trim(text)) BETWEEN 1 AND 4096"),
    CheckConstraint("(status='draft' AND confirmed_at IS NULL AND confirmed_by IS NULL AND attempted_at IS NULL AND completed_at IS NULL) OR (status<>'draft' AND confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL AND attempted_at IS NOT NULL)"),
    CheckConstraint("status NOT IN ('accepted','rejected','delivery_unknown') OR completed_at IS NOT NULL"),
    CheckConstraint("status<>'accepted' OR (telegram_message_id IS NOT NULL AND telegram_message_id > 0)"),
    CheckConstraint("(shelter_id IS NULL AND shelter_snapshot IS NULL) OR (shelter_id IS NOT NULL AND shelter_snapshot IS NOT NULL)"))
Index('ix_notification_history', notifications.c.demonstration, notifications.c.created_at)
NOTIFICATION_TABLES = [notifications]

from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex

revision = '0003_admin_notifications'
down_revision = '0002_emergency_shelters'
branch_labels = None
depends_on = None

def upgrade():
    for table in NOTIFICATION_TABLES:
        op.execute(CreateTable(table))
        for index in sorted(table.indexes, key=lambda i: i.name):
            op.execute(CreateIndex(index))

def downgrade():
    for table in reversed(NOTIFICATION_TABLES):
        op.drop_table(table.name)
