"""
Tests for ML Feature & Data Readiness Contracts (Phase 3.6).

Validates:
1. Temporal window leakage detection (feature_window_end <= prediction_time <= target_window_start).
2. Forecast issue-time and valid-time leakage validation.
3. Three-state labelling semantics (POSITIVE, NEGATIVE, UNLABELLED) and target value contracts.
4. Dataset sample build invariants.
5. Strict read-only invariance on database tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.flood import FloodObservation
from app.db.models.geography import District
from app.db.models.weather import WeatherObservation
from app.db.session import _get_session_factory
from app.ml.contracts import (
    DatasetContractError,
    FeatureCategory,
    FeatureProvenanceRecord,
    FeatureReadiness,
    ForecastLeakageValidator,
    MLDatasetSample,
    MLUnitReadiness,
    MLUnitType,
    SampleLabelState,
    TargetCandidateType,
    TargetReadiness,
    TemporalLeakageError,
    TemporalWindowConfig,
)


@pytest.fixture(scope="module")
def db_session():
    """Yield a database session connected to test/dev database."""
    factory = _get_session_factory()
    session = factory()
    yield session
    session.close()


class TestTemporalLeakageValidation:
    """Validate strict temporal boundary enforcement to prevent data leakage."""

    def test_valid_temporal_windows_pass(self):
        """Valid non-overlapping feature and target windows pass validation."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = TemporalWindowConfig(
            prediction_time=pred_time,
            feature_window_start=datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc),
            feature_window_end=pred_time,
            target_window_start=pred_time,
            target_window_end=datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        # Should execute cleanly
        config.validate_no_leakage()

    def test_feature_window_leaking_into_future_rejected(self):
        """Feature window ending after prediction_time must raise TemporalLeakageError."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = TemporalWindowConfig(
            prediction_time=pred_time,
            feature_window_start=datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc),
            feature_window_end=datetime(2026, 9, 17, 12, 1, 0, tzinfo=timezone.utc),  # 1 min leak
            target_window_start=pred_time,
            target_window_end=datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(TemporalLeakageError, match="Feature window end .* leaks past prediction time"):
            config.validate_no_leakage()

    def test_target_window_preceding_prediction_time_rejected(self):
        """Target window starting before prediction_time must raise TemporalLeakageError."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = TemporalWindowConfig(
            prediction_time=pred_time,
            feature_window_start=datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc),
            feature_window_end=pred_time,
            target_window_start=datetime(2026, 9, 17, 11, 59, 0, tzinfo=timezone.utc),  # 1 min early
            target_window_end=datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(TemporalLeakageError, match="Target window start .* cannot precede prediction time"):
            config.validate_no_leakage()

    def test_inverted_feature_window_rejected(self):
        """Feature window start > end must be rejected."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = TemporalWindowConfig(
            prediction_time=pred_time,
            feature_window_start=datetime(2026, 9, 17, 13, 0, 0, tzinfo=timezone.utc),
            feature_window_end=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
            target_window_start=pred_time,
            target_window_end=datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(TemporalLeakageError, match="feature_window_start .* cannot be after feature_window_end"):
            config.validate_no_leakage()


class TestForecastLeakageValidation:
    """Validate forecast issue time vs valid time rules."""

    def test_valid_forecast_timing_passes(self):
        """Forecast issued before prediction_time for future period passes."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        issued_at = datetime(2026, 9, 17, 6, 0, 0, tzinfo=timezone.utc)
        forecast_for = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

        ForecastLeakageValidator.validate_forecast_feature(
            prediction_time=pred_time,
            issued_at=issued_at,
            forecast_for=forecast_for,
        )

    def test_forecast_issued_after_prediction_time_rejected(self):
        """Forecast issued in the future relative to prediction_time must be rejected."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        issued_at = datetime(2026, 9, 17, 18, 0, 0, tzinfo=timezone.utc)  # 6h in future
        forecast_for = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(TemporalLeakageError, match="Forecast issued at .* leaks into prediction time"):
            ForecastLeakageValidator.validate_forecast_feature(
                prediction_time=pred_time,
                issued_at=issued_at,
                forecast_for=forecast_for,
            )

    def test_forecast_for_past_period_rejected(self):
        """Forecast predicting a period that has already passed must be rejected."""
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        issued_at = datetime(2026, 9, 16, 6, 0, 0, tzinfo=timezone.utc)
        forecast_for = datetime(2026, 9, 17, 6, 0, 0, tzinfo=timezone.utc)  # 6h in past

        with pytest.raises(TemporalLeakageError, match="Forecast valid time .* precedes prediction time"):
            ForecastLeakageValidator.validate_forecast_feature(
                prediction_time=pred_time,
                issued_at=issued_at,
                forecast_for=forecast_for,
            )


class TestDatasetSampleContract:
    """Validate sample schema contracts and three-state labelling rules."""

    def test_positive_sample_contract(self):
        """Valid POSITIVE sample requires target_value=1."""
        sample = MLDatasetSample(
            sample_id=uuid.uuid4(),
            prediction_time=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
            spatial_unit_type=MLUnitType.DISTRICT,
            spatial_unit_id=uuid.uuid4(),
            features={"precip_24h": 45.2, "elevation_mean": 650.0},
            target_name="district_flood_occurrence",
            label_state=SampleLabelState.POSITIVE,
            target_value=1,
            feature_provenance={
                "precip_24h": FeatureProvenanceRecord(
                    feature_name="precip_24h",
                    source_name="Open-Meteo Weather API",
                    source_data_category="MODEL_OUTPUT",
                    transformation_method="SUM_24H",
                )
            },
        )
        assert sample.label_state == SampleLabelState.POSITIVE
        assert sample.target_value == 1

    def test_negative_sample_contract(self):
        """Valid NEGATIVE sample requires target_value=0."""
        sample = MLDatasetSample(
            sample_id=uuid.uuid4(),
            prediction_time=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
            spatial_unit_type=MLUnitType.DISTRICT,
            spatial_unit_id=uuid.uuid4(),
            features={"precip_24h": 0.0, "elevation_mean": 650.0},
            target_name="district_flood_occurrence",
            label_state=SampleLabelState.NEGATIVE,
            target_value=0,
        )
        assert sample.label_state == SampleLabelState.NEGATIVE
        assert sample.target_value == 0

    def test_unlabelled_sample_contract(self):
        """Valid UNLABELLED sample requires target_value=None."""
        sample = MLDatasetSample(
            sample_id=uuid.uuid4(),
            prediction_time=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
            spatial_unit_type=MLUnitType.DISTRICT,
            spatial_unit_id=uuid.uuid4(),
            features={"precip_24h": 12.0},
            target_name="district_flood_occurrence",
            label_state=SampleLabelState.UNLABELLED,
            target_value=None,
        )
        assert sample.label_state == SampleLabelState.UNLABELLED
        assert sample.target_value is None

    def test_unlabelled_with_target_value_rejected(self):
        """UNLABELLED sample with non-None target_value must be rejected."""
        with pytest.raises(DatasetContractError, match="Sample marked UNLABELLED must have target_value=None"):
            MLDatasetSample(
                sample_id=uuid.uuid4(),
                prediction_time=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
                spatial_unit_type=MLUnitType.DISTRICT,
                spatial_unit_id=uuid.uuid4(),
                features={},
                target_name="district_flood_occurrence",
                label_state=SampleLabelState.UNLABELLED,
                target_value=0,  # Invalid!
            )

    def test_positive_with_wrong_target_value_rejected(self):
        """POSITIVE sample with target_value != 1 must be rejected."""
        with pytest.raises(DatasetContractError, match="POSITIVE sample must have target_value=1"):
            MLDatasetSample(
                sample_id=uuid.uuid4(),
                prediction_time=datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc),
                spatial_unit_type=MLUnitType.DISTRICT,
                spatial_unit_id=uuid.uuid4(),
                features={},
                target_name="district_flood_occurrence",
                label_state=SampleLabelState.POSITIVE,
                target_value=0,  # Invalid!
            )


class TestReadOnlyInvariance:
    """Ensure readiness testing performs zero database mutations."""

    def test_database_records_not_mutated(self, db_session: Session):
        """Verify record counts before and after testing remain identical."""
        c_weather = db_session.execute(select(func.count(WeatherObservation.id))).scalar()
        c_flood = db_session.execute(select(func.count(FloodObservation.id))).scalar()
        c_district = db_session.execute(select(func.count(District.id))).scalar()

        # Instantiate contracts and perform validations
        pred_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = TemporalWindowConfig(
            prediction_time=pred_time,
            feature_window_start=datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc),
            feature_window_end=pred_time,
            target_window_start=pred_time,
            target_window_end=datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        config.validate_no_leakage()

        # Verify counts unchanged
        assert db_session.execute(select(func.count(WeatherObservation.id))).scalar() == c_weather
        assert db_session.execute(select(func.count(FloodObservation.id))).scalar() == c_flood
        assert db_session.execute(select(func.count(District.id))).scalar() == c_district
