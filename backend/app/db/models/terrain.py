"""
Terrain and land cover models.

Entities: LandCover, WaterBody, TerrainDataset.

Terrain data must come from legitimate DEMs (e.g., SRTM) per GIS_SPEC.md.
No hand-entered elevation or slope values.
"""

from __future__ import annotations

import uuid
from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import Date, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LandCover(Base):
    """Land use / land cover classification for a spatial unit."""

    __tablename__ = "land_covers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    classification: Mapped[str | None] = mapped_column(String(100))
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(100))
    reference_date: Mapped[date | None] = mapped_column(Date)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)


class WaterBody(Base):
    """Lake, tank, or other water body."""

    __tablename__ = "water_bodies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(150))
    water_body_type: Mapped[str | None] = mapped_column(String(50))
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    __table_args__ = (
        Index("ix_water_bodies_district_id", "district_id"),
    )


class TerrainDataset(Base):
    """Registered DEM or terrain derivative dataset."""

    __tablename__ = "terrain_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    resolution: Mapped[str | None] = mapped_column(String(50))
    crs: Mapped[str | None] = mapped_column(String(20))
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    processing_method: Mapped[str | None] = mapped_column(Text)
    spatial_extent = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
