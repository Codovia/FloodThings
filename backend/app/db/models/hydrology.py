"""
Hydrology models.

Entities: RiverBasin, SubBasin, River, RiverStation, RiverObservation,
          RiverForecast, Reservoir, ReservoirObservation.

Units per DATA_CONTRACT.md:
    water_level_m, discharge_m3s, storage_mcm, level_m, inflow_m3s, outflow_m3s.
    NULL = missing, NOT zero.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
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


class RiverBasin(Base):
    """Major river basin (e.g., Krishna, Cauvery, Godavari)."""

    __tablename__ = "river_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    basin_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    sub_basins: Mapped[list[SubBasin]] = relationship(back_populates="basin")


class SubBasin(Base):
    """Sub-basin within a major river basin."""

    __tablename__ = "sub_basins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_basin_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    basin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("river_basins.id"), nullable=False
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    basin: Mapped[RiverBasin] = relationship(back_populates="sub_basins")
    rivers: Mapped[list[River]] = relationship(back_populates="sub_basin")

    __table_args__ = (
        Index("ix_sub_basins_basin_id", "basin_id"),
    )


class River(Base):
    """Named river or stream."""

    __tablename__ = "rivers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_basin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sub_basins.id"), nullable=True
    )
    geom = mapped_column(Geometry("MULTILINESTRING", srid=4326), nullable=True)

    sub_basin: Mapped[SubBasin | None] = relationship(back_populates="rivers")
    stations: Mapped[list[RiverStation]] = relationship(back_populates="river")

    __table_args__ = (
        Index("ix_rivers_sub_basin_id", "sub_basin_id"),
    )


class RiverStation(Base):
    """Monitoring station on a river, operated by CWC or state agencies."""

    __tablename__ = "river_stations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    river_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rivers.id"), nullable=True
    )
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    operating_agency: Mapped[str | None] = mapped_column(String(100))
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True
    )

    river: Mapped[River | None] = relationship(back_populates="stations")
    observations: Mapped[list[RiverObservation]] = relationship(back_populates="station")
    forecasts: Mapped[list[RiverForecast]] = relationship(back_populates="station")

    __table_args__ = (
        Index("ix_river_stations_river_id", "river_id"),
    )


class RiverObservation(Base):
    """Timestamped water level or discharge measurement from a river station."""

    __tablename__ = "river_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("river_stations.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    water_level_m: Mapped[float | None] = mapped_column(Float)
    discharge_m3s: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str | None] = mapped_column(String(20))

    station: Mapped[RiverStation] = relationship(back_populates="observations")

    __table_args__ = (
        Index("ix_river_obs_station_observed", "station_id", "observed_at"),
    )


class RiverForecast(Base):
    """Forecast of future river water level or discharge."""

    __tablename__ = "river_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("river_stations.id"), nullable=False
    )
    forecast_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    water_level_m: Mapped[float | None] = mapped_column(Float)
    discharge_m3s: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    model_method: Mapped[str | None] = mapped_column(String(100))

    station: Mapped[RiverStation] = relationship(back_populates="forecasts")

    __table_args__ = (
        Index("ix_river_fcst_station_for", "station_id", "forecast_for"),
    )


class Reservoir(Base):
    """Reservoir or major dam."""

    __tablename__ = "reservoirs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    reservoir_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    full_reservoir_level_m: Mapped[float | None] = mapped_column(Float)
    capacity_mcm: Mapped[float | None] = mapped_column(Float)
    river_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rivers.id"), nullable=True
    )
    operating_agency: Mapped[str | None] = mapped_column(String(100))

    observations: Mapped[list[ReservoirObservation]] = relationship(
        back_populates="reservoir"
    )

    __table_args__ = (
        Index("ix_reservoirs_river_id", "river_id"),
    )


class ReservoirObservation(Base):
    """Timestamped storage/level reading from a reservoir."""

    __tablename__ = "reservoir_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reservoir_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservoirs.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_mcm: Mapped[float | None] = mapped_column(Float)
    level_m: Mapped[float | None] = mapped_column(Float)
    inflow_m3s: Mapped[float | None] = mapped_column(Float)
    outflow_m3s: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reservoir: Mapped[Reservoir] = relationship(back_populates="observations")

    __table_args__ = (
        Index("ix_reservoir_obs_reservoir_observed", "reservoir_id", "observed_at"),
    )
