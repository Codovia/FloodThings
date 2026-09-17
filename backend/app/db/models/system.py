"""
System models.

Entities: DataSource, DataIngestionRun, User, AuditLog.

DataSource and DataIngestionRun track provenance per DATA_CONTRACT.md.
User and AuditLog provide system administration and auditing support.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DataSource(Base):
    """Registered external data source."""

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    organization: Mapped[str | None] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    access_method: Mapped[str | None] = mapped_column(String(50))
    data_type: Mapped[str | None] = mapped_column(String(50))
    geographic_coverage: Mapped[str | None] = mapped_column(String(100))
    update_frequency: Mapped[str | None] = mapped_column(String(50))
    license: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    ingestion_runs: Mapped[list[DataIngestionRun]] = relationship(
        "DataIngestionRun", back_populates="source"
    )


class DataIngestionRun(Base):
    """Record of a data ingestion pipeline execution for provenance tracking."""

    __tablename__ = "data_ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    records_received: Mapped[int | None] = mapped_column(Integer)
    records_inserted: Mapped[int | None] = mapped_column(Integer)
    records_updated: Mapped[int | None] = mapped_column(Integer)
    records_rejected: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[DataSource] = relationship("DataSource", back_populates="ingestion_runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')",
            name="ck_ingestion_run_status",
        ),
        Index("ix_ingestion_runs_source_id", "source_id"),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )


class User(Base):
    """System user (citizen, admin, data manager)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'USER'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    audit_logs: Mapped[list[AuditLog]] = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_user_role"),
    )


class AuditLog(Base):
    """Log of important administrative actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="NO ACTION"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )
