"""
Flood observation, event, and hazard zone models.

Entities: FloodObservation, FloodEvent, FloodHazardZone.

Critical distinctions:
    FloodHazardZone != FloodObservation != FloodPrediction != OfficialWarning.
    flood_depth is nullable — missing depth must NEVER be filled with zeros or estimates.
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FloodObservation(Base):
    """Recorded flood observation from verified ground truth or satellite inventory."""

    __tablename__ = "flood_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    observation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    flooded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    flood_depth: Mapped[float | None] = mapped_column(Float)
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
    basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_basins.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    quality_status: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_flood_obs_confidence",
        ),
        CheckConstraint(
            "flood_depth IS NULL OR flood_depth >= 0.0",
            name="ck_flood_obs_depth",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_flood_obs_quality_status",
        ),
        Index("ix_flood_obs_observation_time", "observation_time"),
        Index("ix_flood_obs_district_id", "district_id"),
        Index("ix_flood_obs_taluk_id", "taluk_id"),
        Index("ix_flood_obs_basin_id", "basin_id"),
        Index("ix_flood_obs_source_id", "source_id"),
        Index("ix_flood_obs_source_record", "source_id", "source_record_id"),
        Index("idx_flood_obs_geometry", "geometry", postgresql_using="gist"),
    )


class FloodEvent(Base):
    """Officially declared flood disaster event catalog."""

    __tablename__ = "flood_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(50))
    affected_area: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_flood_event_confidence",
        ),
        CheckConstraint(
            "affected_area IS NULL OR affected_area >= 0.0",
            name="ck_flood_event_affected_area",
        ),
        Index("ix_flood_events_start_time", "start_time"),
        Index("ix_flood_events_source_id", "source_id"),
        Index("idx_flood_events_geometry", "geometry", postgresql_using="gist"),
    )


class FloodHazardZone(Base):
    """Spatially defined zone of cumulative flood hazard."""

    __tablename__ = "flood_hazard_zones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    hazard_class: Mapped[str | None] = mapped_column(String(50))
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_flood_hazard_source_id", "source_id"),
        Index("idx_flood_hazard_geometry", "geometry", postgresql_using="gist"),
    )
