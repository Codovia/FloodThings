"""
Emergency response and community report models.

Entities: EmergencyFacility, CommunityReport.

Per CONSTRAINTS.md:
    - Community reports are NEVER automatically treated as ground truth.
    - Status starts as 'SUBMITTED', transitions through 'UNDER_REVIEW', 'VERIFIED', or 'REJECTED'.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EmergencyFacility(Base):
    """Emergency facility (hospital, police station, fire station, relief/evacuation centre)."""

    __tablename__ = "emergency_facilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
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
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str | None] = mapped_column(String(20))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    __table_args__ = (
        CheckConstraint(
            "facility_type IN ('HOSPITAL', 'POLICE_STATION', 'FIRE_STATION', 'RELIEF_CENTRE', 'EVACUATION_CENTRE')",
            name="ck_emergency_facility_type",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_emergency_facility_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_emergency_facility_longitude",
        ),
        Index("ix_emergency_fac_district_id", "district_id"),
        Index("ix_emergency_fac_taluk_id", "taluk_id"),
        Index("ix_emergency_fac_type", "facility_type"),
        Index("ix_emergency_fac_source_id", "source_id"),
        Index("idx_emergency_fac_geometry", "geometry", postgresql_using="gist"),
    )


class CommunityReport(Base):
    """Citizen-submitted report of flooding, damage, or hazard."""

    __tablename__ = "community_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=True,
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    reported_flood_depth: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(50))
    image_reference: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'SUBMITTED'")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=True,
    )
    verification_notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id]
    )

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_community_report_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_community_report_longitude",
        ),
        CheckConstraint(
            "reported_flood_depth IS NULL OR reported_flood_depth >= 0.0",
            name="ck_community_report_depth",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'UNDER_REVIEW', 'VERIFIED', 'REJECTED')",
            name="ck_community_report_status",
        ),
        Index("ix_community_reports_user_id", "user_id"),
        Index("ix_community_reports_reported_at", "reported_at"),
        Index("ix_community_reports_status", "status"),
        Index("idx_community_reports_geometry", "geometry", postgresql_using="gist"),
    )
