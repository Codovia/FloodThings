"""
Alert and notification models.

Entities: Alert, TelegramSubscription.

Per CONSTRAINTS.md & DATA_CONTRACT.md:
    - Official government warnings and AI predictions must be strictly separated.
    - Source types: OFFICIAL_WARNING, AI_PREDICTION, ADMIN_ALERT.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Alert(Base):
    """Alert issued for public or administrative warning."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flood_predictions.id", ondelete="NO ACTION"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('OFFICIAL_WARNING', 'AI_PREDICTION', 'ADMIN_ALERT')",
            name="ck_alert_source_type",
        ),
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_district_id", "district_id"),
        Index("ix_alerts_source_type", "source_type"),
        Index("ix_alerts_prediction_id", "prediction_id"),
        Index("idx_alerts_geometry", "geometry", postgresql_using="gist"),
    )


class TelegramSubscription(Base):
    """Telegram chat subscription for localized alerts."""

    __tablename__ = "telegram_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=True,
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    taluk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("taluks.id", ondelete="NO ACTION"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
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

    user: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_telegram_sub_district_id", "district_id"),
        Index("ix_telegram_sub_taluk_id", "taluk_id"),
        Index("ix_telegram_sub_user_id", "user_id"),
    )
