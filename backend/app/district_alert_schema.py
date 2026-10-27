"""Public Telegram district alerts: subscriptions made by the subscriber's own /start command.

The chat ID is stored only because it is needed to deliver an administrator-approved alert; /stop (or blocking
the bot) deletes the subscriber row and its districts. The audit log keeps only the keyed subscriber hash.
Existing admin_notifications rows are referenced, not altered.
"""
from sqlalchemy import MetaData, Table, Column, String, DateTime, BigInteger, Boolean, Integer, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()
# Reference-only table; excluded from this module's DDL.
Table('admin_notifications', metadata, Column('id', UUID(as_uuid=False), primary_key=True))

subscribers = Table('telegram_district_subscribers', metadata,
    Column('subscriber_key', String(64), primary_key=True),
    Column('chat_id', String(20), nullable=False),
    Column('consent_version', String(60), nullable=False),
    Column('demonstration', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint("chat_id ~ '^[1-9][0-9]{0,19}$'", name='ck_district_subscriber_private_chat'))

district_subscriptions = Table('telegram_district_subscriptions', metadata,
    Column('subscriber_key', String(64), ForeignKey('telegram_district_subscribers.subscriber_key', ondelete='CASCADE'), primary_key=True),
    Column('district_id', String(100), primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint("district_id LIKE 'nic:%'", name='ck_district_subscription_district'))
Index('ix_district_subscriptions_district', district_subscriptions.c.district_id)

district_audit = Table('telegram_district_audit', metadata,
    Column('id', String(36), primary_key=True),
    Column('subscriber_key', String(64), nullable=False),
    Column('action', String(20), nullable=False),
    Column('district_id', String(100)),
    Column('command_at', DateTime(timezone=True), nullable=False),
    Column('received_at', DateTime(timezone=True), nullable=False),
    Column('update_id', BigInteger, nullable=False),
    CheckConstraint("action IN ('subscribe','unsubscribe','stop','blocked')", name='ck_district_audit_action'))
Index('ix_district_audit_subscriber', district_audit.c.subscriber_key, district_audit.c.command_at)

district_notices = Table('district_notifications', metadata,
    Column('notification_id', UUID(as_uuid=False), ForeignKey('admin_notifications.id'), primary_key=True),
    Column('district_id', String(100), nullable=False),
    Column('district_name', String(200), nullable=False),
    Column('recipients', Integer),
    Column('accepted', Integer),
    Column('rejected', Integer),
    Column('uncertain', Integer),
    CheckConstraint("district_id LIKE 'nic:%'", name='ck_district_notice_district'))

deliveries = Table('telegram_district_deliveries', metadata,
    Column('notification_id', UUID(as_uuid=False), ForeignKey('admin_notifications.id'), primary_key=True),
    Column('subscriber_key', String(64), primary_key=True),
    Column('status', String(30), nullable=False),
    Column('result_code', String(60), nullable=False),
    Column('http_status', Integer),
    Column('telegram_error_code', Integer),
    Column('telegram_message_id', Integer),
    Column('completed_at', DateTime(timezone=True), nullable=False),
    CheckConstraint("status IN ('accepted','rejected','delivery_unknown')", name='ck_district_delivery_status'))

DISTRICT_ALERT_TABLES = [subscribers, district_subscriptions, district_audit, district_notices, deliveries]
