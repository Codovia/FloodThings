"""
Prediction and ML models.

Entities: PredictionGridCell, FeatureSnapshot, MLDatasetVersion,
          MLModel, FloodPrediction.

Per ML_SPEC.md:
    - Prediction spatial unit is district polygon.
    - Labels from legitimate historical flood records only.
    - No random/synthetic data.
    - No hardcoded risk values.

Per DATA_CONTRACT.md:
    - NULL prediction probability means "not computed", not "zero risk".
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
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PredictionGridCell(Base):
    """Spatial unit used for prediction (typically district or sub-district)."""

    __tablename__ = "prediction_grid_cells"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True
    )
    taluk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taluks.id"), nullable=True
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    feature_snapshots: Mapped[list[FeatureSnapshot]] = relationship(
        back_populates="grid_cell"
    )

    __table_args__ = (
        Index("ix_pred_grid_district_id", "district_id"),
    )


class FeatureSnapshot(Base):
    """Engineered features for a prediction unit at a point in time."""

    __tablename__ = "feature_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    grid_cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_grid_cells.id"), nullable=False
    )
    feature_date: Mapped[date] = mapped_column(Date, nullable=False)
    features: Mapped[dict | None] = mapped_column(JSON)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ml_dataset_versions.id"), nullable=True
    )

    grid_cell: Mapped[PredictionGridCell] = relationship(
        back_populates="feature_snapshots"
    )

    __table_args__ = (
        Index("ix_feat_snap_cell_date", "grid_cell_id", "feature_date"),
    )


class MLDatasetVersion(Base):
    """Versioned ML dataset constructed from feature snapshots and labels."""

    __tablename__ = "ml_dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    feature_schema: Mapped[dict | None] = mapped_column(JSON)
    label_definition: Mapped[str | None] = mapped_column(Text)
    temporal_range_start: Mapped[date | None] = mapped_column(Date)
    temporal_range_end: Mapped[date | None] = mapped_column(Date)
    spatial_coverage: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    class_balance: Mapped[dict | None] = mapped_column(JSON)
    provenance: Mapped[str | None] = mapped_column(Text)


class MLModel(Base):
    """Registered trained ML model."""

    __tablename__ = "ml_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    algorithm: Mapped[str | None] = mapped_column(String(100))
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ml_dataset_versions.id"), nullable=True
    )
    hyperparameters: Mapped[dict | None] = mapped_column(JSON)
    training_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluation_metrics: Mapped[dict | None] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    feature_schema: Mapped[dict | None] = mapped_column(JSON)


class FloodPrediction(Base):
    """ML-generated flood risk prediction for a spatial unit."""

    __tablename__ = "flood_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    grid_cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_grid_cells.id"), nullable=False
    )
    prediction_for: Mapped[date] = mapped_column(Date, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    probability: Mapped[float | None] = mapped_column(Float)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ml_models.id"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    confidence_indicators: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_flood_pred_cell_for", "grid_cell_id", "prediction_for"),
    )
