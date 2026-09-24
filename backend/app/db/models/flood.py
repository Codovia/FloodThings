"""
Flood observation, event, hazard zone, and District x Day label models.

Entities: FloodObservation, FloodEvent, FloodHazardZone, DistrictDayFloodLabel.

Critical distinctions:
    FloodHazardZone != FloodObservation != FloodPrediction != OfficialWarning.
    flood_depth is nullable — missing depth must NEVER be filled with zeros or estimates.
    DistrictDayFloodLabel represents consolidated District x Day ML training targets
    derived from IFI v3.0 with strict Three-State labelling ('FLOOD', 'NO_FLOOD', 'UNKNOWN').
"""

from __future__ import annotations

from datetime import date as dt_date, datetime
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    data_category: Mapped[str | None] = mapped_column(String(30))

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
        CheckConstraint(
            "data_category IS NULL OR data_category IN ('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')",
            name="ck_flood_obs_data_category",
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


class DistrictDayFloodLabel(Base):
    """
    Historical District x Day flood occurrence label for ML dataset construction.

    Derived deterministically from India Flood Inventory (IFI v3.0, HydroSenseLab / IMD).
    Represents the ground truth target for the ML unit of analysis (Karnataka District x Calendar Day).
    Preserves full semantic provenance back to source event UEIs.
    """

    __tablename__ = "district_day_flood_labels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=False,
    )
    event_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    flood_occurrence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    source_event_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    main_causes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    severities: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    fatalities: Mapped[int | None] = mapped_column(Integer, nullable=True)
    displaced: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    data_category: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'HISTORICAL_EVENT'")
    )
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'VALID'")
    )
    mapping_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'MAPPED'")
    )
    processing_version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'3.13.0'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("district_id", "event_date", name="uq_district_day_flood_labels"),
        CheckConstraint(
            "label IN ('FLOOD', 'NO_FLOOD', 'UNKNOWN')",
            name="ck_district_day_label_val",
        ),
        CheckConstraint(
            "flood_occurrence IS NULL OR flood_occurrence IN (0, 1)",
            name="ck_district_day_flood_occ",
        ),
        CheckConstraint(
            "event_count >= 0",
            name="ck_district_day_event_count",
        ),
        CheckConstraint(
            "fatalities IS NULL OR fatalities >= 0",
            name="ck_district_day_fatalities",
        ),
        CheckConstraint(
            "displaced IS NULL OR displaced >= 0",
            name="ck_district_day_displaced",
        ),
        CheckConstraint(
            "quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_district_day_quality_status",
        ),
        CheckConstraint(
            "data_category IN ('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')",
            name="ck_district_day_data_category",
        ),
        Index("ix_district_day_labels_district_id", "district_id"),
        Index("ix_district_day_labels_event_date", "event_date"),
        Index("ix_district_day_labels_label", "label"),
    )
