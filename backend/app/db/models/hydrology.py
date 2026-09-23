"""
Hydrology models.

Entities: RiverBasin, SubBasin, River, RiverStation, RiverObservation,
          RiverForecast, Reservoir, ReservoirObservation,
          DistrictSubBasin, DistrictRiverBasin.

Distinction: Administrative geography != Hydrological geography.
NULL represents missing real-world observations, NOT zero.

RiverBasin = CWC/NWDP statutory major basin (authoritative reference).
SubBasin   = HydroBASINS Level-7 hydrological catchment (topology layer).
River      = Named river OR HydroRIVERS reach segment.

HydroBASINS Level-7 is NOT treated as a CWC statutory sub-division.
District↔basin/sub-basin relationships are many-to-many.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
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


class RiverBasin(Base):
    """Major river basin — CWC/NWDP statutory reference layer.

    Example basins: Krishna, Cauvery, Godavari, West Flowing Rivers (Tadri to Kanyakumari).
    Source: CWC basin_cwc_shp (EPSG:7755 → stored as EPSG:4326).
    """

    __tablename__ = "river_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )

    # --- Source provenance ---
    source_agency: Mapped[str | None] = mapped_column(String(200))
    source_dataset: Mapped[str | None] = mapped_column(String(200))
    source_version: Mapped[str | None] = mapped_column(String(50))
    source_feature_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    area_km2: Mapped[float | None] = mapped_column(Float)
    intersects_karnataka: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    sub_basins: Mapped[list[SubBasin]] = relationship(
        "SubBasin", back_populates="basin"
    )
    rivers: Mapped[list[River]] = relationship(
        "River", back_populates="basin"
    )

    __table_args__ = (
        Index("idx_river_basins_geometry", "geometry", postgresql_using="gist"),
    )


class SubBasin(Base):
    """Sub-basin / HydroBASINS Level-7 hydrological catchment.

    This is NOT a CWC statutory sub-division. HydroBASINS Level-7
    represents hydrological topology derived from HydroSHEDS.
    basin_id is nullable because HydroBASINS features do not map
    directly to CWC major basins.
    """

    __tablename__ = "sub_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_basins.id", ondelete="NO ACTION"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )

    # --- HydroBASINS Level-7 topology attributes ---
    hybas_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    next_down: Mapped[int | None] = mapped_column(BigInteger)
    next_sink: Mapped[int | None] = mapped_column(BigInteger)
    main_bas: Mapped[int | None] = mapped_column(BigInteger)
    sub_area: Mapped[float | None] = mapped_column(Float)  # km²
    up_area: Mapped[float | None] = mapped_column(Float)  # km²
    pfaf_id: Mapped[int | None] = mapped_column(BigInteger)
    endo: Mapped[int | None] = mapped_column(Integer)
    coast: Mapped[int | None] = mapped_column(Integer)
    dist_sink: Mapped[float | None] = mapped_column(Float)  # km
    dist_main: Mapped[float | None] = mapped_column(Float)  # km
    order_: Mapped[int | None] = mapped_column("order", Integer)
    sort: Mapped[int | None] = mapped_column(BigInteger)

    # --- Source provenance ---
    source_dataset: Mapped[str | None] = mapped_column(String(200))
    source_version: Mapped[str | None] = mapped_column(String(50))
    geometry_repaired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    basin: Mapped[RiverBasin | None] = relationship("RiverBasin", back_populates="sub_basins")
    rivers: Mapped[list[River]] = relationship("River", back_populates="sub_basin")

    __table_args__ = (
        Index("ix_sub_basins_basin_id", "basin_id"),
        Index("idx_sub_basins_geometry", "geometry", postgresql_using="gist"),
        Index("ix_sub_basins_hybas_id", "hybas_id"),
    )


class River(Base):
    """Named river or HydroRIVERS reach segment.

    Dual-purpose table:
    - Named rivers (e.g. Cauvery, Krishna) with name and optional basin FK.
    - HydroRIVERS reach segments identified by hyriv_id with full topology.
    """

    __tablename__ = "rivers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_basins.id", ondelete="NO ACTION"),
        nullable=True,
    )
    sub_basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sub_basins.id", ondelete="NO ACTION"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    geometry = mapped_column(
        Geometry("MULTILINESTRING", srid=4326, spatial_index=False), nullable=True
    )

    # --- HydroRIVERS topology attributes ---
    hyriv_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    next_down: Mapped[int | None] = mapped_column(BigInteger)
    main_riv: Mapped[int | None] = mapped_column(BigInteger)
    length_km: Mapped[float | None] = mapped_column(Float)
    dist_dn_km: Mapped[float | None] = mapped_column(Float)
    dist_up_km: Mapped[float | None] = mapped_column(Float)
    catch_skm: Mapped[float | None] = mapped_column(Float)
    upland_skm: Mapped[float | None] = mapped_column(Float)
    dis_av_cms: Mapped[float | None] = mapped_column(Float)
    ord_stra: Mapped[int | None] = mapped_column(Integer)  # Strahler order
    ord_clas: Mapped[int | None] = mapped_column(Integer)  # classical order
    ord_flow: Mapped[int | None] = mapped_column(Integer)  # flow order
    hybas_l12: Mapped[int | None] = mapped_column(BigInteger)  # Level-12 HYBAS ref

    # --- Source provenance ---
    source_dataset: Mapped[str | None] = mapped_column(String(200))
    source_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    basin: Mapped[RiverBasin | None] = relationship("RiverBasin", back_populates="rivers")
    sub_basin: Mapped[SubBasin | None] = relationship("SubBasin", back_populates="rivers")
    stations: Mapped[list[RiverStation]] = relationship("RiverStation", back_populates="river")

    __table_args__ = (
        Index("ix_rivers_basin_id", "basin_id"),
        Index("ix_rivers_sub_basin_id", "sub_basin_id"),
        Index("idx_rivers_geometry", "geometry", postgresql_using="gist"),
        Index("ix_rivers_hyriv_id", "hyriv_id"),
    )


class RiverStation(Base):
    """Monitoring station on a river operated by CWC or state agencies."""

    __tablename__ = "river_stations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    river_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rivers.id", ondelete="NO ACTION"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    station_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    warning_level: Mapped[float | None] = mapped_column(Float)
    danger_level: Mapped[float | None] = mapped_column(Float)
    highest_flood_level: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    river: Mapped[River | None] = relationship("River", back_populates="stations")
    observations: Mapped[list[RiverObservation]] = relationship(
        "RiverObservation", back_populates="station"
    )
    forecasts: Mapped[list[RiverForecast]] = relationship(
        "RiverForecast", back_populates="station"
    )

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_river_stations_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_river_stations_longitude",
        ),
        Index("ix_river_stations_river_id", "river_id"),
        Index("ix_river_stations_district_id", "district_id"),
        Index("ix_river_stations_source_id", "source_id"),
        Index("idx_river_stations_geometry", "geometry", postgresql_using="gist"),
    )


class RiverObservation(Base):
    """Timestamped water level or discharge measurement from a river station."""

    __tablename__ = "river_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_stations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    water_level: Mapped[float | None] = mapped_column(Float)
    water_level_unit: Mapped[str | None] = mapped_column(String(10), default="m")
    discharge: Mapped[float | None] = mapped_column(Float)
    discharge_unit: Mapped[str | None] = mapped_column(String(10), default="m3s")
    trend: Mapped[str | None] = mapped_column(String(20))
    warning_level: Mapped[float | None] = mapped_column(Float)
    danger_level: Mapped[float | None] = mapped_column(Float)
    highest_flood_level: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str | None] = mapped_column(String(20))
    data_category: Mapped[str | None] = mapped_column(String(30))

    station: Mapped[RiverStation] = relationship(
        "RiverStation", back_populates="observations"
    )

    __table_args__ = (
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_river_obs_quality_status",
        ),
        CheckConstraint(
            "data_category IS NULL OR data_category IN ('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')",
            name="ck_river_obs_data_category",
        ),
        Index("ix_river_obs_station_observed", "station_id", "observed_at"),
        Index("ix_river_obs_source_id", "source_id"),
        Index("ix_river_obs_source_record", "source_id", "source_record_id"),
    )


class RiverForecast(Base):
    """Forecast of future river water level or discharge."""

    __tablename__ = "river_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_stations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    forecast_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    forecast_water_level: Mapped[float | None] = mapped_column(Float)
    forecast_discharge: Mapped[float | None] = mapped_column(Float)
    forecast_status: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    quality_status: Mapped[str | None] = mapped_column(String(20))

    station: Mapped[RiverStation] = relationship(
        "RiverStation", back_populates="forecasts"
    )

    __table_args__ = (
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_river_fcst_quality_status",
        ),
        Index("ix_river_fcst_station_for", "station_id", "forecast_for"),
        Index("ix_river_fcst_source_id", "source_id"),
    )


class Reservoir(Base):
    """Reservoir or major dam."""

    __tablename__ = "reservoirs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), unique=True)
    river_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rivers.id", ondelete="NO ACTION"),
        nullable=True,
    )
    basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_basins.id", ondelete="NO ACTION"),
        nullable=True,
    )
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    full_reservoir_level: Mapped[float | None] = mapped_column(Float)
    capacity: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    observations: Mapped[list[ReservoirObservation]] = relationship(
        "ReservoirObservation", back_populates="reservoir"
    )

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_reservoirs_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_reservoirs_longitude",
        ),
        Index("ix_reservoirs_river_id", "river_id"),
        Index("ix_reservoirs_basin_id", "basin_id"),
        Index("ix_reservoirs_district_id", "district_id"),
        Index("ix_reservoirs_source_id", "source_id"),
        Index("idx_reservoirs_geometry", "geometry", postgresql_using="gist"),
    )


class ReservoirObservation(Base):
    """Timestamped storage and level readings from a reservoir."""

    __tablename__ = "reservoir_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reservoir_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservoirs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    water_level: Mapped[float | None] = mapped_column(Float)
    storage: Mapped[float | None] = mapped_column(Float)
    storage_percentage: Mapped[float | None] = mapped_column(Float)
    inflow: Mapped[float | None] = mapped_column(Float)
    outflow: Mapped[float | None] = mapped_column(Float)
    trend: Mapped[str | None] = mapped_column(String(20))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str | None] = mapped_column(String(20))
    data_category: Mapped[str | None] = mapped_column(String(30))

    reservoir: Mapped[Reservoir] = relationship(
        "Reservoir", back_populates="observations"
    )

    __table_args__ = (
        CheckConstraint(
            "storage_percentage IS NULL OR (storage_percentage >= 0.0 AND storage_percentage <= 100.0)",
            name="ck_reservoir_obs_storage_percentage",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_reservoir_obs_quality_status",
        ),
        CheckConstraint(
            "data_category IS NULL OR data_category IN ('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')",
            name="ck_reservoir_obs_data_category",
        ),
        Index("ix_reservoir_obs_reservoir_observed", "reservoir_id", "observed_at"),
        Index("ix_reservoir_obs_source_id", "source_id"),
        Index("ix_reservoir_obs_source_record", "source_id", "source_record_id"),
    )


# ---------------------------------------------------------------------------
# Administrative ↔ Hydrological Crosswalk Tables (Many-to-Many)
# ---------------------------------------------------------------------------


class DistrictSubBasin(Base):
    """Many-to-many spatial intersection between districts and HydroBASINS Level-7 sub-basins.

    Districts may span multiple sub-basins and sub-basins may cross district boundaries.
    Each row represents a non-zero intersection with computed area and percentages.
    """

    __tablename__ = "district_sub_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=False,
    )
    sub_basin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sub_basins.id", ondelete="NO ACTION"),
        nullable=False,
    )
    intersection_geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    intersection_area_km2: Mapped[float | None] = mapped_column(Float)
    percent_of_subbasin_in_district: Mapped[float | None] = mapped_column(Float)
    percent_of_district_in_subbasin: Mapped[float | None] = mapped_column(Float)
    derivation_method: Mapped[str | None] = mapped_column(String(100))
    source_description: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("district_id", "sub_basin_id", name="uq_district_sub_basin"),
        Index("ix_district_sub_basins_district_id", "district_id"),
        Index("ix_district_sub_basins_sub_basin_id", "sub_basin_id"),
        Index("idx_district_sub_basins_geom", "intersection_geometry", postgresql_using="gist"),
    )


class DistrictRiverBasin(Base):
    """Many-to-many spatial intersection between districts and CWC major river basins.

    Districts may span multiple major basins (e.g. a district on the Krishna-Cauvery divide).
    Each row represents a non-zero intersection with computed area and percentages.
    """

    __tablename__ = "district_river_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=False,
    )
    river_basin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("river_basins.id", ondelete="NO ACTION"),
        nullable=False,
    )
    intersection_geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    intersection_area_km2: Mapped[float | None] = mapped_column(Float)
    percent_of_basin_in_district: Mapped[float | None] = mapped_column(Float)
    percent_of_district_in_basin: Mapped[float | None] = mapped_column(Float)
    derivation_method: Mapped[str | None] = mapped_column(String(100))
    source_description: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("district_id", "river_basin_id", name="uq_district_river_basin"),
        Index("ix_district_river_basins_district_id", "district_id"),
        Index("ix_district_river_basins_river_basin_id", "river_basin_id"),
        Index("idx_district_river_basins_geom", "intersection_geometry", postgresql_using="gist"),
    )
