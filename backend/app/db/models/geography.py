"""
Administrative geography models.

Entities: State, District, Taluk, Locality.

Geometry stored in EPSG:4326 (WGS 84) per GIS_SPEC.md.
Administrative boundaries are distinct from hydrological boundaries.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class State(Base):
    """Indian state. FloodPulse primary scope is Karnataka."""

    __tablename__ = "states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )

    districts: Mapped[list[District]] = relationship(
        "District", back_populates="state"
    )

    __table_args__ = (
        Index("idx_states_geometry", "geometry", postgresql_using="gist"),
    )


class District(Base):
    """Administrative district within a state."""

    __tablename__ = "districts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("states.id", ondelete="NO ACTION"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    centroid = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )

    state: Mapped[State] = relationship("State", back_populates="districts")
    taluks: Mapped[list[Taluk]] = relationship("Taluk", back_populates="district")

    __table_args__ = (
        Index("ix_districts_state_id", "state_id"),
        Index("idx_districts_geometry", "geometry", postgresql_using="gist"),
        Index("idx_districts_centroid", "centroid", postgresql_using="gist"),
    )


class Taluk(Base):
    """Subdivision of an administrative district."""

    __tablename__ = "taluks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )

    district: Mapped[District] = relationship("District", back_populates="taluks")
    localities: Mapped[list[Locality]] = relationship(
        "Locality", back_populates="taluk"
    )

    __table_args__ = (
        Index("ix_taluks_district_id", "district_id"),
        Index("idx_taluks_geometry", "geometry", postgresql_using="gist"),
    )


class Locality(Base):
    """Named locality, village, or ward within a taluk."""

    __tablename__ = "localities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    taluk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("taluks.id", ondelete="NO ACTION"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    centroid = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )

    taluk: Mapped[Taluk] = relationship("Taluk", back_populates="localities")

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_localities_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_localities_longitude",
        ),
        Index("ix_localities_taluk_id", "taluk_id"),
        Index("idx_localities_geometry", "geometry", postgresql_using="gist"),
        Index("idx_localities_centroid", "centroid", postgresql_using="gist"),
    )
