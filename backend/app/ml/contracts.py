"""
ML Dataset and Feature Readiness Contracts (Phase 3.6).

Defines strict, type-safe data structures, enums, and validators for:
1. ML Unit of Analysis evaluation.
2. Target candidate evaluation and three-state labelling (POSITIVE, NEGATIVE, UNLABELLED).
3. Feature candidate readiness and semantic provenance.
4. Strict temporal leakage prevention (prediction_time, feature_window, target_window).
5. Forecast issue-time vs valid-time leakage validation.
6. Future ML dataset sample contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class MLUnitType(str, Enum):
    """Spatial unit of analysis for machine learning."""

    DISTRICT = "DISTRICT"
    TALUK = "TALUK"
    REGULAR_GRID = "REGULAR_GRID"
    RIVER_STATION = "RIVER_STATION"
    EVENT_LOCATION = "EVENT_LOCATION"


class MLUnitReadiness(str, Enum):
    """Readiness status of an ML unit candidate."""

    CURRENTLY_SUPPORTED = "CURRENTLY_SUPPORTED"
    CONDITIONALLY_SUPPORTED = "CONDITIONALLY_SUPPORTED"
    CURRENTLY_BLOCKED = "CURRENTLY_BLOCKED"


class TargetCandidateType(str, Enum):
    """Candidate machine learning prediction targets."""

    TARGET_A_DISTRICT_FLOOD_OCCURRENCE = "TARGET_A_DISTRICT_FLOOD_OCCURRENCE"
    TARGET_B_FLOOD_AFFECTED_AREA = "TARGET_B_FLOOD_AFFECTED_AREA"
    TARGET_C_SPATIAL_INUNDATION_EXTENT = "TARGET_C_SPATIAL_INUNDATION_EXTENT"
    TARGET_D_RIVER_GAUGE_THRESHOLD_EXCEEDANCE = "TARGET_D_RIVER_GAUGE_THRESHOLD_EXCEEDANCE"
    TARGET_E_FLOOD_SEVERITY_CATEGORY = "TARGET_E_FLOOD_SEVERITY_CATEGORY"


class TargetReadiness(str, Enum):
    """Strict target readiness classification."""

    SUPPORTED = "SUPPORTED"
    CONDITIONALLY_SUPPORTED = "CONDITIONALLY_SUPPORTED"
    BLOCKED = "BLOCKED"


class FeatureCategory(str, Enum):
    """Semantic category of candidate ML features."""

    WEATHER = "WEATHER"
    TEMPORAL_RAINFALL = "TEMPORAL_RAINFALL"
    HYDROLOGY = "HYDROLOGY"
    TERRAIN = "TERRAIN"
    SPATIAL = "SPATIAL"
    HISTORICAL = "HISTORICAL"
    FORECAST = "FORECAST"


class FeatureReadiness(str, Enum):
    """Strict feature availability classification."""

    AVAILABLE_NOW = "AVAILABLE_NOW"
    AVAILABLE_WITH_ADDITIONAL_REAL_DATA = "AVAILABLE_WITH_ADDITIONAL_REAL_DATA"
    BLOCKED = "BLOCKED"


class SampleLabelState(str, Enum):
    """Strict three-state labelling contract for training samples."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNLABELLED = "UNLABELLED"


class TemporalLeakageError(ValueError):
    """Raised when temporal leakage is detected in feature or target windows."""


class DatasetContractError(ValueError):
    """Raised when a dataset sample violates the ML dataset contract."""


@dataclass(frozen=True)
class TemporalWindowConfig:
    """Formal temporal alignment configuration for ML sample generation."""

    prediction_time: datetime
    feature_window_start: datetime
    feature_window_end: datetime
    target_window_start: datetime
    target_window_end: datetime

    def validate_no_leakage(self) -> None:
        """
        Validate that no temporal leakage exists across windows.

        Invariants:
        1. feature_window_start <= feature_window_end
        2. feature_window_end <= prediction_time (no future features)
        3. target_window_start >= prediction_time (target is strictly in future)
        4. target_window_end > target_window_start
        """
        if self.feature_window_start > self.feature_window_end:
            raise TemporalLeakageError(
                f"feature_window_start ({self.feature_window_start}) cannot be after "
                f"feature_window_end ({self.feature_window_end})"
            )

        if self.feature_window_end > self.prediction_time:
            raise TemporalLeakageError(
                f"Feature window end ({self.feature_window_end}) leaks past "
                f"prediction time ({self.prediction_time})"
            )

        if self.target_window_start < self.prediction_time:
            raise TemporalLeakageError(
                f"Target window start ({self.target_window_start}) cannot precede "
                f"prediction time ({self.prediction_time})"
            )

        if self.target_window_end <= self.target_window_start:
            raise TemporalLeakageError(
                f"target_window_end ({self.target_window_end}) must be strictly after "
                f"target_window_start ({self.target_window_start})"
            )


@dataclass(frozen=True)
class ForecastLeakageValidator:
    """Validates weather or hydrological forecast features for temporal integrity."""

    @staticmethod
    def validate_forecast_feature(
        prediction_time: datetime,
        issued_at: datetime,
        forecast_for: datetime,
    ) -> None:
        """
        Ensure forecast features do not leak future information.

        Invariants:
        1. issued_at <= prediction_time (forecast must have been issued at or before prediction time)
        2. forecast_for >= prediction_time (forecast must be predicting the current or future period)
        """
        if issued_at > prediction_time:
            raise TemporalLeakageError(
                f"Forecast issued at ({issued_at}) leaks into prediction time ({prediction_time})"
            )
        if forecast_for < prediction_time:
            raise TemporalLeakageError(
                f"Forecast valid time ({forecast_for}) precedes prediction time ({prediction_time})"
            )


@dataclass(frozen=True)
class FeatureProvenanceRecord:
    """Provenance metadata for an individual engineered ML feature."""

    feature_name: str
    source_name: str
    source_data_category: str  # OBSERVATION, REANALYSIS, MODEL_OUTPUT, FORECAST, REFERENCE, DERIVED
    observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    valid_at: datetime | None = None
    transformation_method: str = "DIRECT"


@dataclass(frozen=True)
class MLDatasetSample:
    """A single canonical training or evaluation sample conforming to the dataset build contract."""

    sample_id: UUID
    prediction_time: datetime
    spatial_unit_type: MLUnitType
    spatial_unit_id: UUID
    features: dict[str, float | None]
    target_name: str
    label_state: SampleLabelState
    target_value: float | int | None
    feature_provenance: dict[str, FeatureProvenanceRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate dataset contract invariants."""
        # 1. Label state semantics
        if self.label_state == SampleLabelState.UNLABELLED:
            if self.target_value is not None:
                raise DatasetContractError(
                    f"Sample marked UNLABELLED must have target_value=None, got {self.target_value}"
                )
        elif self.label_state in (SampleLabelState.POSITIVE, SampleLabelState.NEGATIVE):
            if self.target_value is None:
                raise DatasetContractError(
                    f"Sample marked {self.label_state.value} must have a non-None target_value"
                )

        # 2. Binary target consistency
        if self.label_state == SampleLabelState.POSITIVE and self.target_value != 1:
            raise DatasetContractError(
                f"POSITIVE sample must have target_value=1, got {self.target_value}"
            )
        if self.label_state == SampleLabelState.NEGATIVE and self.target_value != 0:
            raise DatasetContractError(
                f"NEGATIVE sample must have target_value=0, got {self.target_value}"
            )


@dataclass(frozen=True)
class MLUnitEvaluation:
    """Evaluation summary of an ML unit candidate."""

    unit_type: MLUnitType
    readiness: MLUnitReadiness
    available_labels: str
    available_predictors: str
    spatial_resolution: str
    temporal_resolution: str
    coverage: str
    leakage_risk: str
    missing_data_problem: str
    trainable_with_current_real_data: bool
    concrete_reasons: list[str]


@dataclass(frozen=True)
class TargetEvaluation:
    """Evaluation summary of a target candidate."""

    target_type: TargetCandidateType
    readiness: TargetReadiness
    source: str
    definition: str
    positive_label_availability: str
    negative_label_availability: str
    geometry_availability: str
    temporal_alignment_requirements: str
    leakage_controllable: bool
    concrete_reasons: list[str]
    additional_data_required: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeatureEvaluation:
    """Evaluation summary of a feature candidate."""

    feature_name: str
    category: FeatureCategory
    readiness: FeatureReadiness
    source: str
    temporal_coverage: str
    spatial_coverage: str
    missingness_summary: str
    leakage_risk: str
    concrete_reasons: list[str]
    additional_data_required: list[str] = field(default_factory=list)
