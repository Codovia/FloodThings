"""
Emergency response models.

Entities: EmergencyFacility, CommunityReport.

Per CONSTRAINTS.md:
    - Unknown shelter occupancy must NOT be interpreted as available capacity.
    - Community reports are always UNVERIFIED initially.
    - An unverified citizen report is never treated as ground truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmergencyFacility(Base):
    """Shelter, hospital, fire station, police station, or other facility."""

    __tablename__ = "emergency_facilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    address: Mapped[str | None] = mapped_column(Text)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    taluk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taluks.id"), nullable=True
    )
    # Capacity is nullable — unknown capacity ≠ zero capacity.
    capacity: Mapped[int | None] = mapped_column(Integer)
    contact_info: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str | None] = mapped_column(String(20))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_emergency_fac_district_id", "district_id"),
        Index("ix_emergency_fac_type", "facility_type"),
    )


class CommunityReport(Base):
    """Citizen-submitted report of flooding, damage, or need.

    Per CONSTRAINTS.md, verification_status always starts as UNVERIFIED.
    """

    __tablename__ = "community_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    report_type: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    photos: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'UNVERIFIED'")
    )
    moderator_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_community_reports_reported_at", "reported_at"),
    )
