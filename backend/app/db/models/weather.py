"""
Weather and rainfall models.

Entities: WeatherObservation, RainfallObservation, WeatherForecast.

Units per DATA_CONTRACT.md:
    temperature in Celsius, humidity in %, pressure in hPa,
    wind_speed in m/s, wind_direction in degrees, rainfall in mm.
    NULL = missing observation, NOT zero.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
    location_type: Mapped[str | None] = mapped_column(String(50))
    location_reference: Mapped[str | None] = mapped_column(String(100))
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    temperature: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    pressure: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    wind_direction: Mapped[float | None] = mapped_column(Float)
    weather_condition: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_weather_obs_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_weather_obs_longitude",
        ),
        CheckConstraint(
            "humidity IS NULL OR (humidity >= 0.0 AND humidity <= 100.0)",
            name="ck_weather_obs_humidity",
        ),
        CheckConstraint(
            "wind_speed IS NULL OR wind_speed >= 0.0",
            name="ck_weather_obs_wind_speed",
        ),
        CheckConstraint(
            "wind_direction IS NULL OR (wind_direction >= 0.0 AND wind_direction <= 360.0)",
            name="ck_weather_obs_wind_direction",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_weather_obs_quality_status",
        ),
        Index("ix_weather_obs_district_observed", "district_id", "observed_at"),
        Index("ix_weather_obs_source_id", "source_id"),
        Index("ix_weather_obs_source_record", "source_id", "source_record_id"),
        Index("idx_weather_obs_geometry", "geometry", postgresql_using="gist"),
    )


class RainfallObservation(Base):
    """Timestamped rainfall measurement for a location."""

    __tablename__ = "rainfall_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    station_id: Mapped[str | None] = mapped_column(String(100))
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(
            "rainfall_mm IS NULL OR rainfall_mm >= 0.0",
            name="ck_rainfall_obs_rainfall_mm",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="ck_rainfall_obs_duration",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_rainfall_obs_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_rainfall_obs_longitude",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_rainfall_obs_quality_status",
        ),
        Index("ix_rainfall_obs_district_observed", "district_id", "observed_at"),
        Index("ix_rainfall_obs_source_id", "source_id"),
        Index("ix_rainfall_obs_source_record", "source_id", "source_record_id"),
        Index("idx_rainfall_obs_geometry", "geometry", postgresql_using="gist"),
    )


class WeatherForecast(Base):
    """Forecast of future weather conditions."""

    __tablename__ = "weather_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    location_type: Mapped[str | None] = mapped_column(String(50))
    location_reference: Mapped[str | None] = mapped_column(String(100))
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    forecast_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    temperature: Mapped[float | None] = mapped_column(Float)
    rainfall_probability: Mapped[float | None] = mapped_column(Float)
    forecast_rainfall_mm: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    weather_condition: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="NO ACTION"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    quality_status: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(
            "rainfall_probability IS NULL OR (rainfall_probability >= 0.0 AND rainfall_probability <= 1.0)",
            name="ck_weather_fcst_rainfall_prob",
        ),
        CheckConstraint(
            "forecast_rainfall_mm IS NULL OR forecast_rainfall_mm >= 0.0",
            name="ck_weather_fcst_rainfall_mm",
        ),
        CheckConstraint(
            "humidity IS NULL OR (humidity >= 0.0 AND humidity <= 100.0)",
            name="ck_weather_fcst_humidity",
        ),
        CheckConstraint(
            "wind_speed IS NULL OR wind_speed >= 0.0",
            name="ck_weather_fcst_wind_speed",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VALID', 'SUSPECT', 'INVALID', 'MISSING', 'STALE')",
            name="ck_weather_fcst_quality_status",
        ),
        Index("ix_weather_fcst_district_for", "district_id", "forecast_for"),
        Index("ix_weather_fcst_source_id", "source_id"),
    )
