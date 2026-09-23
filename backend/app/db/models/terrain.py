"""
Terrain and land cover models.

Entities: LandCover, WaterBody, TerrainDataset.

Terrain rasters are stored as external GIS assets;
relational tables hold metadata and spatial boundaries.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class TerrainStatistic(Base):
    """Derived zonal terrain features (elevation & slope) for a spatial unit."""

    __tablename__ = "terrain_statistics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    terrain_dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("terrain_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'DISTRICT' or 'SUB_BASIN'
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="CASCADE"),
        nullable=True,
    )
    sub_basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sub_basins.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Elevation statistics (meters, EGM2008 geoid)
    elevation_mean: Mapped[float | None] = mapped_column(Float)
    elevation_median: Mapped[float | None] = mapped_column(Float)
    elevation_min: Mapped[float | None] = mapped_column(Float)
    elevation_max: Mapped[float | None] = mapped_column(Float)
    elevation_std: Mapped[float | None] = mapped_column(Float)

    # Slope statistics (degrees, Horn 1981 metric algorithm)
    slope_mean: Mapped[float | None] = mapped_column(Float)
    slope_median: Mapped[float | None] = mapped_column(Float)
    slope_min: Mapped[float | None] = mapped_column(Float)
    slope_max: Mapped[float | None] = mapped_column(Float)

    # Coverage and validity
    valid_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nodata_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coverage_percentage: Mapped[float] = mapped_column(Float, nullable=False)

    # Provenance tracking (DERIVED_FEATURES)
    dem_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(50), nullable=False)
    geometry_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_method: Mapped[str] = mapped_column(String(100), nullable=False)
    processing_crs: Mapped[str] = mapped_column(String(150), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    terrain_dataset: Mapped[TerrainDataset] = relationship("TerrainDataset")

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('DISTRICT', 'SUB_BASIN')",
            name="ck_terrain_stats_target_type",
        ),
        CheckConstraint(
            "(target_type = 'DISTRICT' AND district_id IS NOT NULL AND sub_basin_id IS NULL) OR "
            "(target_type = 'SUB_BASIN' AND sub_basin_id IS NOT NULL AND district_id IS NULL)",
            name="ck_terrain_stats_target_exclusivity",
        ),
        UniqueConstraint(
            "terrain_dataset_id", "target_type", "district_id",
            name="uq_terrain_stats_district",
        ),
        UniqueConstraint(
            "terrain_dataset_id", "target_type", "sub_basin_id",
            name="uq_terrain_stats_sub_basin",
        ),
        Index("ix_terrain_stats_dataset_id", "terrain_dataset_id"),
        Index("ix_terrain_stats_district_id", "district_id"),
        Index("ix_terrain_stats_sub_basin_id", "sub_basin_id"),
        Index("ix_terrain_stats_target_type", "target_type"),
    )
