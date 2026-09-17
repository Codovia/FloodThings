"""
Administrative geography models.

Entities: State, District, Taluk, Locality.

Geometry stored in EPSG:4326 per GIS_SPEC.md.
Boundary data will come from authoritative sources (KGIS, LGD, Survey of India)
— not from this schema definition.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class State(Base):
    """Indian state. FloodPulse focuses on Karnataka."""

    __tablename__ = "states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    state_code: Mapped[str | None] = mapped_column(String(10), unique=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    districts: Mapped[list[District]] = relationship(back_populates="state")


class District(Base):
    """Administrative district within a state."""

    __tablename__ = "districts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    district_code_lgd: Mapped[str | None] = mapped_column(String(20), unique=True)
    state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("states.id"), nullable=False
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    state: Mapped[State] = relationship(back_populates="districts")
    taluks: Mapped[list[Taluk]] = relationship(back_populates="district")

    __table_args__ = (
        Index("ix_districts_state_id", "state_id"),
    )


class Taluk(Base):
    """Subdivision of a district."""

    __tablename__ = "taluks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    taluk_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=False
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    district: Mapped[District] = relationship(back_populates="taluks")
    localities: Mapped[list[Locality]] = relationship(back_populates="taluk")

    __table_args__ = (
        Index("ix_taluks_district_id", "district_id"),
    )


class Locality(Base):
    """Named locality, village, or ward within a taluk."""

    __tablename__ = "localities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    locality_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    taluk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taluks.id"), nullable=False
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    taluk: Mapped[Taluk] = relationship(back_populates="localities")

    __table_args__ = (
        Index("ix_localities_taluk_id", "taluk_id"),
    )
