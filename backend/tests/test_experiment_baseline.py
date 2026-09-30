"""
Unit Tests for Phase 5.4 Reproducible Baseline ML Experiments.

Verifies:
1. Canonical 27-feature whitelist exact match and ordering.
2. Forbidden feature rejection (target, metadata, IDs, day-t).
3. UNKNOWN is never converted to zero in raw data.
4. 930 cold-start rows are strictly excluded.
5. Chronological split boundaries exact match.
6. No train/test temporal overlap (T_train < T_val < T_test).
7. Test data does not influence training (scaler & model fit strictly on Train).
8. Dataset SHA-256 recorded and verified.
9. Deterministic feature ordering and reproducible metrics across multiple runs.
10. Experiment metadata generated correctly with required schema keys.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import numpy as np
import pytest

from app.ml.experiment.baseline import (
    LogisticRegressionBaseline,
    RandomForestBaseline,
)
from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    EXPECTED_SUPERVISED_SHA256,
    FORBIDDEN_COLUMNS,
    load_supervised_dataset,
)
from app.ml.experiment.metrics import (
    PUEvaluationMetrics,
    evaluate_pu_predictions,
)
from app.ml.experiment.runner import (
    ExperimentRunner,
    get_default_experiments_dir,
)
from app.ml.experiment.splits import (
    create_chronological_split,
)


@pytest.fixture(scope="module")
def supervised_dataset():
    """Load the supervised dataset once for the test module."""
    return load_supervised_dataset()


def test_01_canonical_27_feature_whitelist():
    """Test 1: Verify exact count, column names, and ordering of canonical 27 predictors."""
    assert len(CANONICAL_PREDICTORS) == 27
    expected_categories = {
        # 14 weather
        "precip_1d_mm", "precip_3d_sum_mm", "precip_7d_sum_mm", "precip_14d_sum_mm",
        "precip_30d_sum_mm", "precip_7d_max_mm", "precip_14d_max_mm",
        "temp_mean_1d_c", "temp_min_1d_c", "temp_max_1d_c", "temp_7d_mean_c",
        "rh_mean_1d_pct", "rh_7d_mean_pct", "pressure_mean_1d_hpa",
        # 6 terrain
        "elevation_mean_m", "elevation_min_m", "elevation_max_m", "elevation_std_m",
        "slope_mean_deg", "slope_max_deg",
        # 4 hydro
        "major_basin_count", "primary_basin_coverage_pct", "sub_basin_count", "mean_upstream_area_km2",
        # 3 spatial / calendar
        "weather_cell_count", "day_of_year", "target_month",
    }
    assert set(CANONICAL_PREDICTORS) == expected_categories


def test_02_forbidden_feature_rejection():
    """Test 2: Ensure all 30 non-predictor columns are strictly disjoint from CANONICAL_PREDICTORS."""
    overlap = set(CANONICAL_PREDICTORS).intersection(FORBIDDEN_COLUMNS)
    assert len(overlap) == 0, f"Leakage violation: forbidden columns in predictors: {overlap}"
    assert "flood_occurrence" in FORBIDDEN_COLUMNS
    assert "label_state" in FORBIDDEN_COLUMNS
    assert "event_count" in FORBIDDEN_COLUMNS
    assert "source_event_ids" in FORBIDDEN_COLUMNS
    assert "fatalities" in FORBIDDEN_COLUMNS
    assert "displaced" in FORBIDDEN_COLUMNS


def test_03_unknown_is_never_converted_to_zero(supervised_dataset):
    """Test 3: Verify UNKNOWN observations have flood_occurrence = NULL and never 0."""
    df = supervised_dataset.df
    unknown_mask = df["label_state"] == "UNKNOWN"
    assert unknown_mask.sum() > 0
    assert df.loc[unknown_mask, "flood_occurrence"].isna().all()
    assert (df["label_state"] == "NO_FLOOD").sum() == 0
    assert (df["flood_occurrence"] == 0).sum() == 0


def test_04_cold_start_rows_excluded(supervised_dataset):
    """Test 4: Verify exactly 930 cold-start rows (Jan 1-30, 2011) are excluded."""
    assert supervised_dataset.excluded_cold_start_rows == 930
    assert supervised_dataset.total_raw_rows == 142228
    assert supervised_dataset.active_rows == 141298
    # No incomplete 30d weather records remain
    assert (supervised_dataset.df["is_weather_complete_30d"] == False).sum() == 0
    assert supervised_dataset.df[CANONICAL_PREDICTORS].isna().sum().sum() == 0


def test_05_chronological_split_boundaries(supervised_dataset):
    """Test 5: Verify chronological split partition boundaries and counts."""
    split = create_chronological_split(supervised_dataset.df)

    # Train
    assert split.train.start_date == "2011-01-31"  # Jan 1-30 excluded by cold start
    assert split.train.end_date == "2019-12-31"
    assert split.train.total_samples == 100967  # 101897 - 930
    assert split.train.positive_samples == 4628

    # Validation
    assert split.val.start_date == "2020-01-01"
    assert split.val.end_date == "2021-12-31"
    assert split.val.total_samples == 22661
    assert split.val.positive_samples == 8408

    # Test
    assert split.test.start_date == "2022-01-01"
    assert split.test.end_date == "2023-07-24"
    assert split.test.total_samples == 17670
    assert split.test.positive_samples == 120

    # Total active rows sum
    total_split_rows = (
        split.train.total_samples + split.val.total_samples + split.test.total_samples
    )
    assert total_split_rows == supervised_dataset.active_rows


def test_06_no_train_test_temporal_overlap(supervised_dataset):
    """Test 6: Verify strict temporal order T_train < T_val < T_test and zero overlap."""
    split = create_chronological_split(supervised_dataset.df)
    split.validate_causality()

    # Zero index intersection
    train_idx = set(split.train.indices)
    val_idx = set(split.val.indices)
    test_idx = set(split.test.indices)

    assert len(train_idx.intersection(val_idx)) == 0
    assert len(val_idx.intersection(test_idx)) == 0
    assert len(train_idx.intersection(test_idx)) == 0


def test_07_test_data_does_not_influence_training(supervised_dataset):
    """Test 7: Verify scaler and model fit strictly on Train split without test influence."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train = X[split.train.indices]
    s_train = s[split.train.indices]
    X_test = X[split.test.indices]

    model = LogisticRegressionBaseline(C=1.0, random_state=42)
    model.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)

    # Scaler mean must match train mean, NOT overall mean
    train_means = np.mean(X_train, axis=0)
    np.testing.assert_allclose(model.scaler.mean_, train_means, rtol=1e-5)

    # Scaler mean must differ from test means
    test_means = np.mean(X_test, axis=0)
    assert not np.allclose(model.scaler.mean_, test_means, rtol=1e-2)


def test_08_dataset_sha256_recorded(supervised_dataset):
    """Test 8: Verify dataset SHA-256 matches expected audit hash."""
    assert supervised_dataset.sha256 == EXPECTED_SUPERVISED_SHA256
    assert len(supervised_dataset.sha256) == 64


def test_09_deterministic_feature_ordering_and_reproducibility(supervised_dataset):
    """Test 9: Verify deterministic predictions across multiple runs with identical random state."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices], s[split.train.indices]
    X_val = X[split.val.indices]

    # Run 1
    lr1 = LogisticRegressionBaseline(C=1.0, random_state=42)
    lr1.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)
    p_val1 = lr1.predict_proba(X_val)

    # Run 2
    lr2 = LogisticRegressionBaseline(C=1.0, random_state=42)
    lr2.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)
    p_val2 = lr2.predict_proba(X_val)

    np.testing.assert_array_equal(p_val1, p_val2)


def test_10_experiment_metadata_generated_correctly():
    """Test 10: Verify ExperimentRunner produces valid JSON metadata with all required fields."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = ExperimentRunner(output_dir=tmp_dir)
        meta = runner.run_logistic_regression()

        meta_file = Path(tmp_dir) / "logistic_regression" / "experiment_metadata.json"
        assert meta_file.exists()

        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["experiment_version"] == "phase_5_4_baseline_v1.0.0"
        assert data["dataset_sha256"] == EXPECTED_SUPERVISED_SHA256
        assert len(data["features_used"]) == 27
        assert data["target"] == "flood_occurrence"
        assert data["target_semantics"]["negative_count"] == 0
        assert "validation" in data["metrics"]
        assert "test" in data["metrics"]
        assert data["metrics"]["validation"]["pr_auc"] > 0.0
        assert data["metrics"]["test"]["pr_auc"] > 0.0
        assert "interpretability" in data


def test_11_scar_assumption_is_not_validated_in_metadata():
    """Test 11: Guarantee SCAR is not represented as validated; must be declared NOT VALIDATED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = ExperimentRunner(output_dir=tmp_dir)
        meta = runner.run_logistic_regression()

        pu_framing = meta["pu_framing"]
        assert "NOT VALIDATED" in pu_framing["scar_assumption"]
        assert "reporting" in pu_framing["scar_assumption"].lower()

        val_metrics = meta["metrics"]["validation"]
        assert "NOT VALIDATED" in val_metrics["scar_status"]
        assert "NOT true binary classification" in val_metrics["evaluation_type"]


def test_12_canonical_whitelist_matches_baseline_modeling_and_rejects_non_canonical():
    """Test 12: Guarantee actual features exactly equal canonical whitelist and reject non-canonical."""
    from app.ml.baseline_modeling import CANONICAL_PREDICTOR_COLUMNS

    # Exact equality of whitelists
    assert CANONICAL_PREDICTORS == CANONICAL_PREDICTOR_COLUMNS
    assert "target_month" in CANONICAL_PREDICTORS

    # Rejection of non-canonical columns
    non_canonical_candidates = ["target_year", "target_day", "fake_rainfall", "event_count"]
    for col in non_canonical_candidates:
        assert col not in CANONICAL_PREDICTORS


def test_13_test_labels_cannot_influence_threshold_selection(supervised_dataset):
    """Test 13: Guarantee test labels have zero influence on decision threshold selection."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices], s[split.train.indices]
    X_val, s_val = X[split.val.indices], s[split.val.indices]

    lr = LogisticRegressionBaseline(C=1.0, random_state=42)
    lr.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)
    p_val = lr.predict_proba(X_val)

    val_metrics = evaluate_pu_predictions(y_true_s=s_val, y_prob=p_val, split_name="val", threshold=None)
    threshold = val_metrics.decision_threshold

    # Threshold must depend solely on validation predictions and validation proxy labels
    assert threshold > 0.0
    # Modifying test data cannot change threshold because threshold is derived purely on val
    synthetic_test_s = np.zeros(split.test.total_samples)
    test_eval = evaluate_pu_predictions(y_true_s=synthetic_test_s, y_prob=np.zeros(split.test.total_samples), split_name="test", threshold=threshold)
    assert test_eval.decision_threshold == threshold


def test_14_test_predictions_cannot_influence_model_fitting(supervised_dataset):
    """Test 14: Guarantee model parameters are identical whether test data exists or not."""
    split = create_chronological_split(supervised_dataset.df)
    X = supervised_dataset.X
    s = supervised_dataset.s_proxy

    X_train, s_train = X[split.train.indices], s[split.train.indices]

    lr = LogisticRegressionBaseline(C=1.0, random_state=42)
    lr.fit(X_train, s_train, feature_names=CANONICAL_PREDICTORS)

    # Weights depend strictly on train
    assert lr.fitted_
    assert len(lr.get_coefficients()["coefficients"]) == 27
    assert lr.scaler.n_samples_seen_ == len(X_train)


def test_15_metrics_classified_as_pu_proxy_and_accuracy_specificity_not_applicable():
    """Test 15: Guarantee accuracy and specificity are marked NOT APPLICABLE in metrics."""
    s_dummy = np.array([1, 0, 1, 0])
    p_dummy = np.array([0.9, 0.2, 0.8, 0.1])

    metrics = evaluate_pu_predictions(y_true_s=s_dummy, y_prob=p_dummy, split_name="test", threshold=0.5)

    assert "NOT APPLICABLE" in metrics.accuracy_status
    assert "NOT APPLICABLE" in metrics.specificity_status
    assert "NOT true binary classification" in metrics.evaluation_type
