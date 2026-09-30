"""
Reproducible Experiment Runner (Phase 5.4).

Executes:
1. Supervised dataset loading and SHA-256 verification.
2. Canonical 27-feature whitelist filtering and cold-start exclusion.
3. Chronological train (2011–2019), validation (2020–2021), and test (2022–2023) splitting.
4. Model 1: Logistic Regression training and evaluation.
5. Model 2: Random Forest training and evaluation.
6. Serialization of metadata JSON and model pipelines to:
   - models/experiments/phase_5_4/logistic_regression/
   - models/experiments/phase_5_4/random_forest/
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

import joblib

from app.ml.experiment.baseline import (
    LogisticRegressionBaseline,
    RandomForestBaseline,
)
from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    load_supervised_dataset,
)
from app.ml.experiment.metrics import (
    PUEvaluationMetrics,
    evaluate_pu_predictions,
)
from app.ml.experiment.splits import (
    create_chronological_split,
)

logger = logging.getLogger(__name__)


def get_default_experiments_dir() -> Path:
    """Resolve models/experiments/phase_5_4 directory."""
    curr = Path(__file__).resolve().parent
    project_root = curr.parents[3]
    return project_root / "models" / "experiments" / "phase_5_4"


class ExperimentRunner:
    """Orchestrates end-to-end reproducible baseline ML experiments."""

    def __init__(
        self,
        parquet_path: Path | str | None = None,
        output_dir: Path | str | None = None,
    ):
        self.dataset = load_supervised_dataset(parquet_path=parquet_path)
        self.split = create_chronological_split(self.dataset.df)
        self.output_dir = Path(output_dir) if output_dir else get_default_experiments_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_logistic_regression(self) -> dict[str, Any]:
        """Train and evaluate standardized L2 Logistic Regression baseline."""
        logger.info("--- Starting Logistic Regression Experiment ---")
        lr_dir = self.output_dir / "logistic_regression"
        lr_dir.mkdir(parents=True, exist_ok=True)

        X = self.dataset.X
        s = self.dataset.s_proxy
        features = self.dataset.features

        # Partition slices
        X_train, s_train = X[self.split.train.indices], s[self.split.train.indices]
        X_val, s_val = X[self.split.val.indices], s[self.split.val.indices]
        X_test, s_test = X[self.split.test.indices], s[self.split.test.indices]

        # Fit model strictly on Train
        model = LogisticRegressionBaseline(C=1.0, random_state=42, class_weight="balanced")
        model.fit(X_train, s_train, feature_names=features)

        # Predict continuous probabilities
        p_val = model.predict_proba(X_val)
        p_test = model.predict_proba(X_test)

        # Evaluate on validation (find optimal threshold maximizing F1 on observed positives)
        val_metrics = evaluate_pu_predictions(
            y_true_s=s_val,
            y_prob=p_val,
            split_name="validation",
            threshold=None,
        )

        # Evaluate on held-out test using the threshold discovered from validation
        test_metrics = evaluate_pu_predictions(
            y_true_s=s_test,
            y_prob=p_test,
            split_name="test",
            threshold=val_metrics.decision_threshold,
        )

        coefficients = model.get_coefficients()

        # Build experiment metadata
        metadata = {
            "experiment_version": "phase_5_4_baseline_v1.0.0",
            "model_type": "LogisticRegression",
            "model_id": "lr_l2_balanced_baseline",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_path": "data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet",
            "dataset_sha256": self.dataset.sha256,
            "feature_schema_version": "canonical_27_predictors_v1",
            "features_used": features,
            "target": "flood_occurrence",
            "target_semantics": {
                "positive_definition": "FLOOD (verified IFI v3.0)",
                "unknown_definition": "UNKNOWN (unrecorded district-day)",
                "negative_definition": "NO_FLOOD (none in dataset)",
                "negative_count": 0,
            },
            "pu_framing": {
                "formulation": "Positive-vs-Unlabeled (PU) Proxy Evaluation",
                "scar_assumption": "NOT VALIDATED (IFI catalogue reflects reporting, detection, and media biases; Selected At Random cannot be assumed)",
                "labeling_indicator_s": "1 = FLOOD (verified IFI v3.0), 0 = UNKNOWN (unrecorded district-day)",
                "elkan_noto_c_val": val_metrics.elkan_noto_c_estimate,
                "elkan_noto_c_test": test_metrics.elkan_noto_c_estimate,
            },
            "partitions": {
                "train_period": f"{self.split.train.start_date} to {self.split.train.end_date}",
                "train_samples": self.split.train.total_samples,
                "train_positives": self.split.train.positive_samples,
                "train_prevalence": self.split.train.prevalence,
                "validation_period": f"{self.split.val.start_date} to {self.split.val.end_date}",
                "val_samples": self.split.val.total_samples,
                "val_positives": self.split.val.positive_samples,
                "val_prevalence": self.split.val.prevalence,
                "test_period": f"{self.split.test.start_date} to {self.split.test.end_date}",
                "test_samples": self.split.test.total_samples,
                "test_positives": self.split.test.positive_samples,
                "test_prevalence": self.split.test.prevalence,
                "forward_inference_period": "2023-07-25 to 2025-12-31",
            },
            "hyperparameters": {
                "penalty": "l2",
                "C": model.C,
                "solver": "lbfgs",
                "max_iter": model.max_iter,
                "class_weight": model.class_weight,
                "random_state": model.random_state,
                "scaler": "StandardScaler(fit_on_train_only)",
            },
            "metrics": {
                "validation": val_metrics.to_dict(),
                "test": test_metrics.to_dict(),
            },
            "interpretability": coefficients,
        }

        # Save artifacts
        meta_path = lr_dir / "experiment_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        model_path = lr_dir / "model_pipeline.joblib"
        joblib.dump(
            {
                "model": model.model,
                "scaler": model.scaler,
                "features": features,
                "decision_threshold": val_metrics.decision_threshold,
            },
            model_path,
        )

        logger.info("Saved Logistic Regression artifacts to %s", lr_dir)
        return metadata

    def run_random_forest(self) -> dict[str, Any]:
        """Train and evaluate Random Forest baseline."""
        logger.info("--- Starting Random Forest Experiment ---")
        rf_dir = self.output_dir / "random_forest"
        rf_dir.mkdir(parents=True, exist_ok=True)

        X = self.dataset.X
        s = self.dataset.s_proxy
        features = self.dataset.features

        # Partition slices
        X_train, s_train = X[self.split.train.indices], s[self.split.train.indices]
        X_val, s_val = X[self.split.val.indices], s[self.split.val.indices]
        X_test, s_test = X[self.split.test.indices], s[self.split.test.indices]

        # Fit Random Forest strictly on Train
        model = RandomForestBaseline(
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, s_train, feature_names=features)

        # Predict continuous probabilities
        p_val = model.predict_proba(X_val)
        p_test = model.predict_proba(X_test)

        # Evaluate on validation
        val_metrics = evaluate_pu_predictions(
            y_true_s=s_val,
            y_prob=p_val,
            split_name="validation",
            threshold=None,
        )

        # Evaluate on test with threshold discovered on validation
        test_metrics = evaluate_pu_predictions(
            y_true_s=s_test,
            y_prob=p_test,
            split_name="test",
            threshold=val_metrics.decision_threshold,
        )

        importances = model.get_feature_importances()

        # Build experiment metadata
        metadata = {
            "experiment_version": "phase_5_4_baseline_v1.0.0",
            "model_type": "RandomForest",
            "model_id": "rf_100_depth10_baseline",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_path": "data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet",
            "dataset_sha256": self.dataset.sha256,
            "feature_schema_version": "canonical_27_predictors_v1",
            "features_used": features,
            "target": "flood_occurrence",
            "target_semantics": {
                "positive_definition": "FLOOD (verified IFI v3.0)",
                "unknown_definition": "UNKNOWN (unrecorded district-day)",
                "negative_definition": "NO_FLOOD (none in dataset)",
                "negative_count": 0,
            },
            "pu_framing": {
                "formulation": "Positive-vs-Unlabeled (PU) Proxy Evaluation",
                "scar_assumption": "NOT VALIDATED (IFI catalogue reflects reporting, detection, and media biases; Selected At Random cannot be assumed)",
                "labeling_indicator_s": "1 = FLOOD (verified IFI v3.0), 0 = UNKNOWN (unrecorded district-day)",
                "elkan_noto_c_val": val_metrics.elkan_noto_c_estimate,
                "elkan_noto_c_test": test_metrics.elkan_noto_c_estimate,
            },
            "partitions": {
                "train_period": f"{self.split.train.start_date} to {self.split.train.end_date}",
                "train_samples": self.split.train.total_samples,
                "train_positives": self.split.train.positive_samples,
                "train_prevalence": self.split.train.prevalence,
                "validation_period": f"{self.split.val.start_date} to {self.split.val.end_date}",
                "val_samples": self.split.val.total_samples,
                "val_positives": self.split.val.positive_samples,
                "val_prevalence": self.split.val.prevalence,
                "test_period": f"{self.split.test.start_date} to {self.split.test.end_date}",
                "test_samples": self.split.test.total_samples,
                "test_positives": self.split.test.positive_samples,
                "test_prevalence": self.split.test.prevalence,
                "forward_inference_period": "2023-07-25 to 2025-12-31",
            },
            "hyperparameters": {
                "n_estimators": model.n_estimators,
                "max_depth": model.max_depth,
                "min_samples_leaf": model.min_samples_leaf,
                "class_weight": model.class_weight,
                "random_state": model.random_state,
            },
            "metrics": {
                "validation": val_metrics.to_dict(),
                "test": test_metrics.to_dict(),
            },
            "interpretability": {
                "feature_importances": importances,
            },
        }

        # Save artifacts
        meta_path = rf_dir / "experiment_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        model_path = rf_dir / "model_pipeline.joblib"
        joblib.dump(
            {
                "model": model.model,
                "features": features,
                "decision_threshold": val_metrics.decision_threshold,
            },
            model_path,
        )

        logger.info("Saved Random Forest artifacts to %s", rf_dir)
        return metadata


def run_phase_5_4_experiments() -> dict[str, Any]:
    """Execute both Logistic Regression and Random Forest baseline experiments."""
    runner = ExperimentRunner()
    lr_meta = runner.run_logistic_regression()
    rf_meta = runner.run_random_forest()
    return {
        "logistic_regression": lr_meta,
        "random_forest": rf_meta,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_phase_5_4_experiments()
    print("\n=== Phase 5.4 Baseline ML Experiments Completed Successfully ===")
    print(f"LR Validation PR-AUC: {results['logistic_regression']['metrics']['validation']['pr_auc']}")
    print(f"LR Test PR-AUC:       {results['logistic_regression']['metrics']['test']['pr_auc']}")
    print(f"RF Validation PR-AUC: {results['random_forest']['metrics']['validation']['pr_auc']}")
    print(f"RF Test PR-AUC:       {results['random_forest']['metrics']['test']['pr_auc']}")
