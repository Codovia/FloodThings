"""
Flood event and hazard models.

Entities: FloodObservation, FloodEvent, FloodHazardZone.

FloodObservation = a recorded historical flood from a legitimate inventory.
FloodEvent = an aggregated/normalized event derived from observations.
FloodHazardZone = a spatially defined cumulative hazard zone.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class FloodObservation(Base):
    """Recorded historical flood event from a legitimate inventory (e.g., IFI)."""

    __tablename__ = "flood_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    cause: Mapped[str | None] = mapped_column(String(200))
    severity: Mapped[str | None] = mapped_column(String(50))
    area_affected_km2: Mapped[float | None] = mapped_column(Float)
    casualties: Mapped[int | None] = mapped_column(Integer)
    damage_description: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_flood_obs_start_date", "start_date"),
        Index("ix_flood_obs_source", "source"),
    )


class FloodEvent(Base):
    """Aggregated/normalized flood event derived from observations."""

    __tablename__ = "flood_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    severity: Mapped[str | None] = mapped_column(String(50))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_flood_events_start_date", "start_date"),
    )


class FloodHazardZone(Base):
    """Spatially defined zone of cumulative flood hazard."""

    __tablename__ = "flood_hazard_zones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    hazard_level: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(100))
    methodology: Mapped[str | None] = mapped_column(Text)
    reference_period: Mapped[str | None] = mapped_column(String(50))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
