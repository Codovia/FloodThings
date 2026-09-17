"""
Prediction grid and machine learning models.

Entities: PredictionGridCell, FeatureSnapshot, MLDatasetVersion,
          MLModel, FloodPrediction.

Per ML_SPEC.md & DATA_CONTRACT.md:
    No synthetic training data.
    NULL probability means "not computed", NOT "zero risk".
    Risk levels: LOW, MODERATE, HIGH, SEVERE.
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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PredictionGridCell(Base):
    """Spatial unit used for flood prediction."""

    __tablename__ = "prediction_grid_cells"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    geometry = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    district_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="NO ACTION"),
        nullable=True,
    )
    taluk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("taluks.id", ondelete="NO ACTION"),
        nullable=True,
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
    elevation: Mapped[float | None] = mapped_column(Float)
    slope: Mapped[float | None] = mapped_column(Float)
    distance_to_river: Mapped[float | None] = mapped_column(Float)
    distance_to_waterbody: Mapped[float | None] = mapped_column(Float)

    feature_snapshots: Mapped[list[FeatureSnapshot]] = relationship(
        "FeatureSnapshot", back_populates="grid_cell"
    )
    predictions: Mapped[list[FloodPrediction]] = relationship(
        "FloodPrediction", back_populates="grid_cell"
    )

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)",
            name="ck_pred_grid_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)",
            name="ck_pred_grid_longitude",
        ),
        CheckConstraint(
            "slope IS NULL OR slope >= 0.0",
            name="ck_pred_grid_slope",
        ),
        CheckConstraint(
            "distance_to_river IS NULL OR distance_to_river >= 0.0",
            name="ck_pred_grid_dist_river",
        ),
        CheckConstraint(
            "distance_to_waterbody IS NULL OR distance_to_waterbody >= 0.0",
            name="ck_pred_grid_dist_waterbody",
        ),
        Index("ix_pred_grid_district_id", "district_id"),
        Index("ix_pred_grid_taluk_id", "taluk_id"),
        Index("ix_pred_grid_basin_id", "basin_id"),
        Index("idx_pred_grid_geometry", "geometry", postgresql_using="gist"),
    )


class FeatureSnapshot(Base):
    """Engineered feature snapshot for a prediction unit at a point in time."""

    __tablename__ = "feature_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    grid_cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prediction_grid_cells.id", ondelete="NO ACTION"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    rainfall_1h: Mapped[float | None] = mapped_column(Float)
    rainfall_3h: Mapped[float | None] = mapped_column(Float)
    rainfall_6h: Mapped[float | None] = mapped_column(Float)
    rainfall_12h: Mapped[float | None] = mapped_column(Float)
    rainfall_24h: Mapped[float | None] = mapped_column(Float)
    forecast_rainfall: Mapped[float | None] = mapped_column(Float)
    river_level: Mapped[float | None] = mapped_column(Float)
    river_trend: Mapped[str | None] = mapped_column(String(20))
    reservoir_level: Mapped[float | None] = mapped_column(Float)
    reservoir_inflow: Mapped[float | None] = mapped_column(Float)
    elevation: Mapped[float | None] = mapped_column(Float)
    slope: Mapped[float | None] = mapped_column(Float)
    distance_to_river: Mapped[float | None] = mapped_column(Float)
    landcover_features: Mapped[dict | None] = mapped_column(JSONB)
    waterlogging_features: Mapped[dict | None] = mapped_column(JSONB)
    flood_hazard_features: Mapped[dict | None] = mapped_column(JSONB)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_dataset_versions.id", ondelete="NO ACTION"),
        nullable=True,
    )

    grid_cell: Mapped[PredictionGridCell] = relationship(
        "PredictionGridCell", back_populates="feature_snapshots"
    )

    __table_args__ = (
        Index("ix_feat_snap_cell_time", "grid_cell_id", "timestamp"),
        Index("ix_feat_snap_dataset_version", "dataset_version_id"),
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
    source_snapshot: Mapped[str | None] = mapped_column(Text)
    feature_schema_version: Mapped[str | None] = mapped_column(String(50))
    training_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int | None] = mapped_column(Integer)
    label_definition: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    models: Mapped[list[MLModel]] = relationship(
        "MLModel", back_populates="dataset_version"
    )


class MLModel(Base):
    """Registered trained machine learning model."""

    __tablename__ = "ml_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    model_type: Mapped[str | None] = mapped_column(String(100))
    training_dataset_version: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_dataset_versions.id", ondelete="NO ACTION"),
        nullable=True,
    )
    feature_schema_version: Mapped[str | None] = mapped_column(String(50))
    target_definition: Mapped[str | None] = mapped_column(Text)
    training_started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str | None] = mapped_column(String(50))

    dataset_version: Mapped[MLDatasetVersion | None] = relationship(
        "MLDatasetVersion", back_populates="models"
    )
    predictions: Mapped[list[FloodPrediction]] = relationship(
        "FloodPrediction", back_populates="model"
    )

    __table_args__ = (
        Index("ix_ml_models_dataset_version", "training_dataset_version"),
    )


class FloodPrediction(Base):
    """ML-generated flood risk prediction for a spatial unit."""

    __tablename__ = "flood_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    grid_cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prediction_grid_cells.id", ondelete="NO ACTION"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="NO ACTION"),
        nullable=True,
    )
    prediction_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    prediction_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    flood_probability: Mapped[float | None] = mapped_column(Float)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    top_features: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    grid_cell: Mapped[PredictionGridCell] = relationship(
        "PredictionGridCell", back_populates="predictions"
    )
    model: Mapped[MLModel | None] = relationship(
        "MLModel", back_populates="predictions"
    )

    __table_args__ = (
        CheckConstraint(
            "flood_probability IS NULL OR (flood_probability >= 0.0 AND flood_probability <= 1.0)",
            name="ck_flood_pred_probability",
        ),
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('LOW', 'MODERATE', 'HIGH', 'SEVERE')",
            name="ck_flood_pred_risk_level",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_flood_pred_confidence",
        ),
        Index("ix_flood_pred_cell_for", "grid_cell_id", "prediction_for"),
        Index("ix_flood_pred_model_id", "model_id"),
        Index("ix_flood_pred_created_at", "created_at"),
    )
