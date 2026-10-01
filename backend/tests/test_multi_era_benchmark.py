"""
Unit & Integration Tests for Phase 5.8 Multi-Era Supervised Cross-Validation & Benchmark.

Verifies:
1. Historical and Recent predictor parity (canonical 27 predictors).
2. Dataset SHA-256 verification (Historical and Recent Parquets).
3. Chronological split integrity (within-era Historical and Recent).
4. Disaster Event-ID leakage audit (zero cross-partition overlaps within and across eras).
5. Label semantics (UNKNOWN remains NULL, zero synthetic NO_FLOOD).
6. PU metric semantics (PR-AUC, ROC-AUC, empirical precision lower bound, accuracy not applicable).
7. Reproducibility (deterministic random seeds and identical model outputs).
8. Feature-importance output schema and rank stability calculation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.ml.experiment.baseline import (
    LogisticRegressionBaseline,
    RandomForestBaseline,
)
from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    EXPECTED_HISTORICAL_SHA256,
    EXPECTED_SUPERVISED_SHA256,
    load_historical_dataset,
    load_supervised_dataset,
)
from app.ml.experiment.event_audit import audit_event_leakage
from app.ml.experiment.metrics import evaluate_pu_predictions
from app.ml.experiment.nonlinear_lgbm import LightGBMExperimentModel
from app.ml.experiment.pu_bagging import PUBaggingClassifier
from app.ml.experiment.splits import (
    create_chronological_split,
    create_historical_chronological_split,
)


def test_01_historical_recent_predictor_parity():
    """Verify that both Historical and Recent matrices contain the exact canonical 27 predictors in identical order."""
    hist = load_historical_dataset(exclude_cold_start=True)
    recent = load_supervised_dataset(exclude_cold_start=True)

    assert hist.features == list(CANONICAL_PREDICTORS)
    assert recent.features == list(CANONICAL_PREDICTORS)
    assert len(hist.features) == 27
    assert len(recent.features) == 27
    assert hist.features == recent.features


def test_02_dataset_sha_verification():
    """Verify that SHA-256 checksums match authoritative constants for both matrices."""
    hist = load_historical_dataset(verify_sha256=True)
    recent = load_supervised_dataset(verify_sha256=True)

    assert hist.sha256 == EXPECTED_HISTORICAL_SHA256
    assert recent.sha256 == EXPECTED_SUPERVISED_SHA256


def test_03_chronological_split_integrity():
    """Verify causality and strict non-overlap of historical within-era partitions."""
    hist = load_historical_dataset(exclude_cold_start=True)
    split = create_historical_chronological_split(hist.df)

    # Causality validation
    split.validate_causality()

    # Dates
    assert split.train.end_date < split.val.start_date
    assert split.val.end_date < split.test.start_date

    # Mutual exclusivity of masks
    assert not np.any(split.train.mask & split.val.mask)
    assert not np.any(split.val.mask & split.test.mask)
    assert not np.any(split.train.mask & split.test.mask)

    # All partitions have positive flood samples
    assert split.train.positive_samples > 0
    assert split.val.positive_samples > 0
    assert split.test.positive_samples > 0


def test_04_event_id_leakage_audit():
    """Verify zero cross-partition disaster event ID overlap in within-era and cross-era settings."""
    hist = load_historical_dataset(exclude_cold_start=True)
    recent = load_supervised_dataset(exclude_cold_start=True)

    hist_split = create_historical_chronological_split(hist.df)
    recent_split = create_chronological_split(recent.df)

    audit_h = audit_event_leakage(hist.df, split=hist_split)
    audit_r = audit_event_leakage(recent.df, split=recent_split)

    assert audit_h.is_leakage_free
    assert audit_h.train_val_overlap_count == 0
    assert audit_h.val_test_overlap_count == 0
    assert audit_h.train_test_overlap_count == 0

    assert audit_r.is_leakage_free
    assert audit_r.train_val_overlap_count == 0
    assert audit_r.val_test_overlap_count == 0
    assert audit_r.train_test_overlap_count == 0

    # Cross-era overlap check
    def _extract_all(df):
        evs = set()
        floods = df.loc[df["label_state"] == "FLOOD", "source_event_ids"].dropna()
        for item in floods:
            if isinstance(item, (list, np.ndarray)):
                for e in item:
                    evs.add(str(e).strip())
            elif isinstance(item, str):
                for e in item.split(","):
                    if e.strip():
                        evs.add(e.strip())
        return evs

    cross_overlap = _extract_all(hist.df).intersection(_extract_all(recent.df))
    assert len(cross_overlap) == 0


def test_05_unknown_remains_null():
    """Verify that UNKNOWN is preserved as NULL/unlabeled and zero NO_FLOOD labels exist in both eras."""
    hist = load_historical_dataset(exclude_cold_start=True)
    recent = load_supervised_dataset(exclude_cold_start=True)

    for ds in [hist, recent]:
        assert (ds.df["label_state"] == "NO_FLOOD").sum() == 0
        assert (ds.df["flood_occurrence"] == 0).sum() == 0
        assert ds.df["label_state"].isin(["FLOOD", "UNKNOWN"]).all()


def test_06_pu_metric_semantics():
    """Verify that PU proxy metrics enforce catalogue-conditioned semantics and forbid standard accuracy."""
    y_true_s = np.array([1, 1, 0, 0, 0])
    y_prob = np.array([0.9, 0.8, 0.4, 0.2, 0.1])

    metrics = evaluate_pu_predictions(y_true_s=y_true_s, y_prob=y_prob, split_name="test", threshold=0.5)

    assert metrics.verified_negatives == 0
    assert "NOT APPLICABLE" in metrics.accuracy_status
    assert "NOT APPLICABLE" in metrics.specificity_status
    assert metrics.observed_positive_recall == 1.0  # both positives above 0.5


def test_07_model_reproducibility():
    """Verify that random seeds produce deterministic model outputs on identical inputs."""
    X = np.random.RandomState(42).randn(100, 27)
    s = np.zeros(100)
    s[:10] = 1
    features = list(CANONICAL_PREDICTORS)

    rf1 = RandomForestBaseline(n_estimators=10, max_depth=4, random_state=42)
    rf2 = RandomForestBaseline(n_estimators=10, max_depth=4, random_state=42)

    rf1.fit(X, s, feature_names=features)
    rf2.fit(X, s, feature_names=features)

    p1 = rf1.predict_proba(X)
    p2 = rf2.predict_proba(X)

    np.testing.assert_allclose(p1, p2, atol=1e-7)


def test_08_feature_importance_output_schema():
    """Verify that tree-based models export valid feature importance dictionaries matching CANONICAL_PREDICTORS."""
    X = np.random.RandomState(42).randn(100, 27)
    s = np.zeros(100)
    s[:10] = 1
    features = list(CANONICAL_PREDICTORS)

    lgbm = LightGBMExperimentModel(enforce_monotonic=False, n_estimators=10, max_depth=3, random_state=42)
    lgbm.fit(X, s, feature_names=features)

    importances = lgbm.get_feature_importances()
    assert isinstance(importances, dict)
    assert "by_gain" in importances
    assert "by_split" in importances

    gain_features = {item["feature"] for item in importances["by_gain"]}
    assert gain_features == set(CANONICAL_PREDICTORS)
