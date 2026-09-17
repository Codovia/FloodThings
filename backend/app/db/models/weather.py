"""
Weather and rainfall models.

Entities: WeatherObservation, RainfallObservation, WeatherForecast.

Units per DATA_CONTRACT.md:
    temperature_c, humidity_pct, wind_speed_mps, wind_direction_deg,
    pressure_hpa, rainfall_mm.
    NULL = missing, NOT zero.
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
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WeatherObservation(Base):
    """Timestamped weather observation from a station or gridded source."""

    __tablename__ = "weather_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_mps: Mapped[float | None] = mapped_column(Float)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        Index("ix_weather_obs_district_observed", "district_id", "observed_at"),
    )


class RainfallObservation(Base):
    """Timestamped rainfall measurement for a location."""

    __tablename__ = "rainfall_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    measurement_period: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(100))
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        Index("ix_rainfall_obs_district_date", "district_id", "observation_date"),
    )


class WeatherForecast(Base):
    """Forecast of future weather conditions."""

    __tablename__ = "weather_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    forecast_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_mps: Mapped[float | None] = mapped_column(Float)
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    model_method: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        Index("ix_weather_fcst_district_for", "district_id", "forecast_for"),
    )
