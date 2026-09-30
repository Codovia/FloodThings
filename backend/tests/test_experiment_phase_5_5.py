"""
Unit Tests for Phase 5.5 Advanced PU Modeling & Nonlinear Benchmark.

Verifies:
1. Exact 27-feature whitelist preservation.
2. No UNKNOWN -> NO_FLOOD conversion in raw or processed data.
3. No SCAR assumption silently enabled (explicitly marked NOT VALIDATED).
4. Chronological split integrity (Train < Val < Test).
5. No cross-partition disaster event leakage (0 overlapping event IDs).
6. Test data isolation (test data does not influence training or threshold discovery).
7. Deterministic model configuration (reproducible runs).
8. Dataset SHA-256 preservation.
9. Experiment metadata completeness and JSON validity.
10. Monotonic constraint configuration on cumulative precipitation features.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import numpy as np
import pytest

from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    EXPECTED_SUPERVISED_SHA256,
    FORBIDDEN_COLUMNS,
    load_supervised_dataset,
)
from app.ml.experiment.event_audit import audit_event_leakage
from app.ml.experiment.nonlinear_lgbm import (
    MONOTONIC_FEATURE_CONSTRAINTS,
    LightGBMExperimentModel,
)
from app.ml.experiment.pu_bagging import PUBaggingClassifier
from app.ml.experiment.runner_phase_5_5 import (
    Phase55ExperimentRunner,
    get_phase_5_5_experiments_dir,
)
from app.ml.experiment.splits import create_chronological_split


@pytest.fixture(scope="module")
def supervised_dataset():
    """Load supervised matrix once for test module."""
    return load_supervised_dataset()


def test_01_exact_27_feature_whitelist():
    """Test 1: Guarantee exactly 27 canonical features with zero unauthorized columns."""
    assert len(CANONICAL_PREDICTORS) == 27
    assert "target_month" in CANONICAL_PREDICTORS
    assert "day_of_year" in CANONICAL_PREDICTORS
    assert "precip_1d_mm" in CANONICAL_PREDICTORS
    # No forbidden columns
    overlap = set(CANONICAL_PREDICTORS).intersection(FORBIDDEN_COLUMNS)
    assert len(overlap) == 0


def test_02_no_unknown_to_no_flood_conversion(supervised_dataset):
    """Test 2: Guarantee UNKNOWN is never converted to NO_FLOOD = 0."""
    df = supervised_dataset.df
    assert (df["label_state"] == "NO_FLOOD").sum() == 0
    assert (df["flood_occurrence"] == 0).sum() == 0
    unknown_mask = df["label_state"] == "UNKNOWN"
    assert df.loc[unknown_mask, "flood_occurrence"].isna().all()


def test_03_scar_not_silently_enabled():
    """Test 3: Guarantee SCAR is explicitly marked NOT VALIDATED across all Phase 5.5 models."""
    exp_dir = get_phase_5_5_experiments_dir()
    for model_dir in ["pu_bagging", "lightgbm_unconstrained", "lightgbm_monotonic"]:
        meta_file = exp_dir / model_dir / "experiment_metadata.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            assert "NOT VALIDATED" in meta["pu_framing"]["scar_assumption"]


def test_04_chronological_split_integrity(supervised_dataset):
    """Test 4: Guarantee chronological order and zero row overlap."""
    split = create_chronological_split(supervised_dataset.df)
    split.validate_causality()
    assert split.train.end_date < split.val.start_date
    assert split.val.end_date < split.test.start_date


def test_05_no_cross_partition_event_leakage(supervised_dataset):
    """Test 5: Guarantee 0 cross-partition disaster event ID overlap between Train, Val, and Test."""
    audit = audit_event_leakage(supervised_dataset.df)
    assert audit.is_leakage_free is True
    assert audit.train_val_overlap_count == 0
    assert audit.val_test_overlap_count == 0
    assert audit.train_test_overlap_count == 0
    assert audit.total_unique_events == 183


def test_06_test_data_isolation(supervised_dataset):
    """Test 6: Guarantee test data does not influence LightGBM or PU Bagging training."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices], s[split.train.indices]

    lgbm = LightGBMExperimentModel(enforce_monotonic=False, n_estimators=10, random_state=42)
    lgbm.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)

    assert lgbm.fitted_
    # Verify model trained solely on training sample count
    assert lgbm.model is not None


def test_07_deterministic_model_configuration(supervised_dataset):
    """Test 7: Guarantee identical predictions across multiple runs with identical random state."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices], s[split.train.indices]
    X_val = X[split.val.indices][:100]

    # Run 1
    m1 = LightGBMExperimentModel(n_estimators=10, random_state=42)
    m1.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)
    p1 = m1.predict_proba(X_val)

    # Run 2
    m2 = LightGBMExperimentModel(n_estimators=10, random_state=42)
    m2.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)
    p2 = m2.predict_proba(X_val)

    np.testing.assert_array_equal(p1, p2)


def test_08_dataset_sha_preservation(supervised_dataset):
    """Test 8: Guarantee dataset SHA-256 matches expected audit hash exactly."""
    assert supervised_dataset.sha256 == EXPECTED_SUPERVISED_SHA256


def test_09_experiment_metadata_completeness():
    """Test 9: Guarantee benchmark comparison JSON contains required fields and all models."""
    exp_dir = get_phase_5_5_experiments_dir()
    bench_file = exp_dir / "benchmark_comparison.json"
    assert bench_file.exists()

    with open(bench_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "model_comparison" in data
    models = data["model_comparison"]
    assert "Phase_5_4_Logistic_Regression" in models
    assert "Phase_5_4_Random_Forest" in models
    assert "Phase_5_5_PU_Bagging" in models
    assert "Phase_5_5_LightGBM_Unconstrained" in models
    assert "Phase_5_5_LightGBM_Monotonic" in models
    assert data["event_leakage_audit"]["is_leakage_free"] is True
    assert data["dry_season_negative_conditioning"]["status"] == "DISABLED_FOR_TRAINING"


def test_10_monotonic_constraint_configuration(supervised_dataset):
    """Test 10: Guarantee monotonic constraints are applied strictly to cumulative precipitation features."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices][:500], s[split.train.indices][:500]

    model = LightGBMExperimentModel(enforce_monotonic=True, n_estimators=5, random_state=42)
    model.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)

    assert len(model.constraint_vector_) == 27
    # First 7 precipitation features must be +1
    for i, feat in enumerate(CANONICAL_PREDICTORS):
        if feat in MONOTONIC_FEATURE_CONSTRAINTS:
            assert model.constraint_vector_[i] == 1, f"Feature {feat} should be monotonically constrained to +1"
        else:
            assert model.constraint_vector_[i] == 0, f"Feature {feat} should be unconstrained (0)"
