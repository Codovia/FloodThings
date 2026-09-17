"""
Terrain and land cover models.

Entities: LandCover, WaterBody, TerrainDataset.

Terrain rasters are stored as external GIS assets;
relational tables hold metadata and spatial boundaries.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LandCover(Base):
    """Land use / land cover classification for a spatial unit."""

    __tablename__ = "land_covers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    class_code: Mapped[str | None] = mapped_column(String(50))
    class_name: Mapped[str | None] = mapped_column(String(100))
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    observation_year: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "observation_year IS NULL OR (observation_year >= 1900 AND observation_year <= 2100)",
            name="ck_land_covers_observation_year",
        ),
        Index("ix_land_covers_district_id", "district_id"),
        Index("ix_land_covers_source_id", "source_id"),
        Index("idx_land_covers_geometry", "geometry", postgresql_using="gist"),
    )


class WaterBody(Base):
    """Lake, reservoir, tank, or permanent water body."""

    __tablename__ = "water_bodies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(150))
    waterbody_type: Mapped[str | None] = mapped_column(String(50))
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        Index("ix_water_bodies_district_id", "district_id"),
        Index("ix_water_bodies_source_id", "source_id"),
        Index("idx_water_bodies_geometry", "geometry", postgresql_using="gist"),
    )


class TerrainDataset(Base):
    """Registered DEM or terrain derivative asset metadata."""

    __tablename__ = "terrain_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    coverage = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    file_reference: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_terrain_datasets_source_id", "source_id"),
        Index("idx_terrain_datasets_coverage", "coverage", postgresql_using="gist"),
    )
