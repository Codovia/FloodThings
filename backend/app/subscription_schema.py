"""Consent receipts for configured private Telegram destinations; no raw chat IDs."""
from sqlalchemy import MetaData, Table, Column, String, Boolean, DateTime, BigInteger, CheckConstraint
metadata=MetaData()
subscriptions=Table('telegram_subscriptions',metadata,
    Column('subscriber_key',String(64),primary_key=True),
    Column('active',Boolean,nullable=False),
    Column('command_at',DateTime(timezone=True),nullable=False),
    Column('received_at',DateTime(timezone=True),nullable=False),
    Column('update_id',BigInteger,nullable=False),
    Column('consent_version',String(60),nullable=False),
    CheckConstraint('update_id >= 0'))
subscription_audit=Table('telegram_subscription_audit',metadata,
    Column('id',String(36),primary_key=True),
    Column('subscriber_key',String(64),nullable=False),
    Column('active',Boolean,nullable=False),
    Column('command_at',DateTime(timezone=True),nullable=False),
    Column('received_at',DateTime(timezone=True),nullable=False),
    Column('update_id',BigInteger,nullable=False))
SUBSCRIPTION_TABLES=[subscriptions,subscription_audit]
