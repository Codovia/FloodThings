"""
Phase 5.5 Advanced PU Modeling & Nonlinear Benchmark Runner.

Executes:
1. Cross-partition disaster event leakage audit.
2. Dry-season candidate negative conditioning analysis (disabled for training).
3. Advanced Non-SCAR PU Bagging model.
4. Nonlinear LightGBM Unconstrained baseline.
5. Nonlinear LightGBM Monotonically Constrained baseline.
6. Temporal stability evaluation across Train, Val, and Test partitions.
7. Artifact persistence and structured benchmark comparison export.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any

import joblib
import lightgbm
import sklearn

from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    load_supervised_dataset,
)
from app.ml.experiment.event_audit import (
    EventLeakageAuditResult,
    audit_event_leakage,
)
from app.ml.experiment.metrics import (
    PUEvaluationMetrics,
    evaluate_pu_predictions,
)
from app.ml.experiment.nonlinear_lgbm import (
    MONOTONIC_FEATURE_CONSTRAINTS,
    LightGBMExperimentModel,
)
from app.ml.experiment.pu_bagging import PUBaggingClassifier
from app.ml.experiment.splits import (
    create_chronological_split,
)

logger = logging.getLogger(__name__)


def get_phase_5_5_experiments_dir() -> Path:
    """Resolve models/experiments/phase_5_5 directory."""
    curr = Path(__file__).resolve().parent
    project_root = curr.parents[3]
    return project_root / "models" / "experiments" / "phase_5_5"


class Phase55ExperimentRunner:
    """Orchestrates Phase 5.5 Advanced PU and Nonlinear experiments."""

    def __init__(
        self,
        parquet_path: Path | str | None = None,
        output_dir: Path | str | None = None,
    ):
        self.dataset = load_supervised_dataset(parquet_path=parquet_path)
        self.split = create_chronological_split(self.dataset.df)
        self.output_dir = Path(output_dir) if output_dir else get_phase_5_5_experiments_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.event_audit: EventLeakageAuditResult | None = None

    def run_event_leakage_audit(self) -> EventLeakageAuditResult:
        """Audit disaster event IDs across chronological splits."""
        self.event_audit = audit_event_leakage(self.dataset.df)
        return self.event_audit

    def audit_dry_season_conditioning(self) -> dict[str, Any]:
        """
        Audit dry-season candidate negative conditioning.

        Evaluates whether Jan-March low rainfall days can be assumed NO_FLOOD.
        Result: 1,193 documented floods occur during dry candidate days; conditioning is disabled.
        """
        df = self.dataset.df
        dry_season = df["target_month"].isin([1, 2, 3])
        dry_rainfall = (df["precip_30d_sum_mm"] <= 1.0) & (df["precip_1d_mm"] == 0.0)
        cand_neg = dry_season & dry_rainfall
        is_flood = df["label_state"] == "FLOOD"

        cand_rows = int(cand_neg.sum())
        floods_in_cand = int((cand_neg & is_flood).sum())
        prev = floods_in_cand / cand_rows if cand_rows > 0 else 0.0

        return {
            "status": "DISABLED_FOR_TRAINING",
            "candidate_name": "CONDITIONAL_NEGATIVE_CANDIDATE",
            "condition": "target_month in [1, 2, 3] AND precip_30d_sum_mm <= 1.0 AND precip_1d_mm == 0.0",
            "total_candidate_rows": cand_rows,
            "floods_in_candidate_subset": floods_in_cand,
            "prevalence_in_candidate_subset": round(prev, 6),
            "scientific_decision": (
                "REJECTED: 1,193 documented IFI flood events occurred during dry-season low-rainfall candidate days. "
                "Converting UNKNOWN -> NO_FLOOD based on dry weather constitutes severe label corruption."
            ),
        }

    def run_pu_bagging(self) -> dict[str, Any]:
        """Train and evaluate Non-SCAR PU Bagging classifier."""
        logger.info("--- Starting PU Bagging Experiment ---")
        out_dir = self.output_dir / "pu_bagging"
        out_dir.mkdir(parents=True, exist_ok=True)

        X = self.dataset.X
        s = self.dataset.s_proxy
        features = self.dataset.features

        X_train, s_train = X[self.split.train.indices], s[self.split.train.indices]
        X_val, s_val = X[self.split.val.indices], s[self.split.val.indices]
        X_test, s_test = X[self.split.test.indices], s[self.split.test.indices]

        start_time = time.time()
        model = PUBaggingClassifier(
            n_bags=15,
            unlabeled_ratio=3.0,
            max_depth=6,
            min_samples_leaf=15,
            random_state=42,
        )
        model.fit(X_train, s_train, feature_names=features)
        runtime_sec = round(time.time() - start_time, 2)

        p_train = model.predict_proba(X_train)
        p_val = model.predict_proba(X_val)
        p_test = model.predict_proba(X_test)

        train_metrics = evaluate_pu_predictions(y_true_s=s_train, y_prob=p_train, split_name="train", threshold=None)
        val_metrics = evaluate_pu_predictions(y_true_s=s_val, y_prob=p_val, split_name="validation", threshold=None)
        test_metrics = evaluate_pu_predictions(y_true_s=s_test, y_prob=p_test, split_name="test", threshold=val_metrics.decision_threshold)

        metadata = {
            "experiment_version": "phase_5_5_pu_bagging_v1.0.0",
            "model_type": "PUBagging",
            "algorithm": "Mordelet & Vert (2014) Non-SCAR PU Bagging",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
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
                "formulation": "Bootstrap Ensemble PU Bagging",
                "scar_assumption": "NOT VALIDATED (Algorithm does not require or assume SCAR)",
                "unlabeled_handling": "Repeatedly subsampled background reference subsets",
            },
            "hyperparameters": {
                "n_bags": model.n_bags,
                "unlabeled_ratio": model.unlabeled_ratio,
                "max_depth": model.max_depth,
                "min_samples_leaf": model.min_samples_leaf,
                "random_state": model.random_state,
            },
            "runtime_seconds": runtime_sec,
            "metrics": {
                "train": train_metrics.to_dict(),
                "validation": val_metrics.to_dict(),
                "test": test_metrics.to_dict(),
            },
            "interpretability": {
                "feature_importances": model.get_feature_importances(),
            },
        }

        with open(out_dir / "experiment_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        joblib.dump(
            {
                "estimators": model.estimators_,
                "features": features,
                "decision_threshold": val_metrics.decision_threshold,
            },
            out_dir / "model_pipeline.joblib",
        )

        logger.info("Saved PU Bagging artifacts to %s", out_dir)
        return metadata

    def run_lightgbm(self, enforce_monotonic: bool = False) -> dict[str, Any]:
        """Train and evaluate LightGBM (unconstrained or monotonic)."""
        tag = "lightgbm_monotonic" if enforce_monotonic else "lightgbm_unconstrained"
        logger.info("--- Starting %s Experiment ---", tag)
        out_dir = self.output_dir / tag
        out_dir.mkdir(parents=True, exist_ok=True)

        X = self.dataset.X
        s = self.dataset.s_proxy
        features = self.dataset.features

        X_train, s_train = X[self.split.train.indices], s[self.split.train.indices]
        X_val, s_val = X[self.split.val.indices], s[self.split.val.indices]
        X_test, s_test = X[self.split.test.indices], s[self.split.test.indices]

        start_time = time.time()
        model = LightGBMExperimentModel(
            enforce_monotonic=enforce_monotonic,
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            min_child_samples=50,
            class_weight="balanced",
            random_state=42,
        )
        model.fit(X_train, s_train, feature_names=features)
        runtime_sec = round(time.time() - start_time, 2)

        p_train = model.predict_proba(X_train)
        p_val = model.predict_proba(X_val)
        p_test = model.predict_proba(X_test)

        train_metrics = evaluate_pu_predictions(y_true_s=s_train, y_prob=p_train, split_name="train", threshold=None)
        val_metrics = evaluate_pu_predictions(y_true_s=s_val, y_prob=p_val, split_name="validation", threshold=None)
        test_metrics = evaluate_pu_predictions(y_true_s=s_test, y_prob=p_test, split_name="test", threshold=val_metrics.decision_threshold)

        metadata = {
            "experiment_version": f"phase_5_5_{tag}_v1.0.0",
            "model_type": "LightGBM",
            "algorithm": "Gradient-Boosted Decision Trees" + (" (Monotonic Constraints)" if enforce_monotonic else " (Unconstrained)"),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
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
                "formulation": "Balanced Class-Weighted Proxy Decision Trees",
                "scar_assumption": "NOT VALIDATED (IFI catalogue reporting bias)",
                "unlabeled_handling": "Proxy reference 0 with balanced class reweighting",
            },
            "monotonic_constraints": {
                "enabled": enforce_monotonic,
                "constrained_features": list(MONOTONIC_FEATURE_CONSTRAINTS.keys()) if enforce_monotonic else [],
                "constraint_direction": "+1 (increasing)" if enforce_monotonic else "none",
            },
            "hyperparameters": {
                "n_estimators": model.n_estimators,
                "learning_rate": model.learning_rate,
                "max_depth": model.max_depth,
                "num_leaves": model.num_leaves,
                "min_child_samples": model.min_child_samples,
                "class_weight": model.class_weight,
                "random_state": model.random_state,
            },
            "runtime_seconds": runtime_sec,
            "metrics": {
                "train": train_metrics.to_dict(),
                "validation": val_metrics.to_dict(),
                "test": test_metrics.to_dict(),
            },
            "interpretability": model.get_feature_importances(),
        }

        with open(out_dir / "experiment_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        joblib.dump(
            {
                "model": model.model,
                "features": features,
                "decision_threshold": val_metrics.decision_threshold,
                "enforce_monotonic": enforce_monotonic,
            },
            out_dir / "model_pipeline.joblib",
        )

        logger.info("Saved %s artifacts to %s", tag, out_dir)
        return metadata

    def run_full_benchmark(self) -> dict[str, Any]:
        """Execute the complete Phase 5.5 experiment benchmark."""
        event_res = self.run_event_leakage_audit()
        dry_res = self.audit_dry_season_conditioning()

        pu_bag_meta = self.run_pu_bagging()
        lgbm_uncon_meta = self.run_lightgbm(enforce_monotonic=False)
        lgbm_mono_meta = self.run_lightgbm(enforce_monotonic=True)

        # Load Phase 5.4 baselines for side-by-side comparison
        p54_dir = self.output_dir.parent / "phase_5_4"
        with open(p54_dir / "logistic_regression" / "experiment_metadata.json") as f:
            p54_lr = json.load(f)
        with open(p54_dir / "random_forest" / "experiment_metadata.json") as f:
            p54_rf = json.load(f)

        benchmark = {
            "benchmark_title": "Phase 5.5 Advanced PU Modeling & Nonlinear Benchmark",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_sha256": self.dataset.sha256,
            "event_leakage_audit": event_res.to_dict(),
            "dry_season_negative_conditioning": dry_res,
            "model_comparison": {
                "Phase_5_4_Logistic_Regression": {
                    "val_pr_auc": p54_lr["metrics"]["validation"]["pr_auc"],
                    "test_pr_auc": p54_lr["metrics"]["test"]["pr_auc"],
                    "val_roc_auc": p54_lr["metrics"]["validation"]["roc_auc"],
                    "test_roc_auc": p54_lr["metrics"]["test"]["roc_auc"],
                    "val_recall": p54_lr["metrics"]["validation"]["observed_positive_recall"],
                    "test_recall": p54_lr["metrics"]["test"]["observed_positive_recall"],
                    "val_precision": p54_lr["metrics"]["validation"]["empirical_precision_lower_bound"],
                    "test_precision": p54_lr["metrics"]["test"]["empirical_precision_lower_bound"],
                    "threshold": p54_lr["metrics"]["validation"]["decision_threshold"],
                },
                "Phase_5_4_Random_Forest": {
                    "val_pr_auc": p54_rf["metrics"]["validation"]["pr_auc"],
                    "test_pr_auc": p54_rf["metrics"]["test"]["pr_auc"],
                    "val_roc_auc": p54_rf["metrics"]["validation"]["roc_auc"],
                    "test_roc_auc": p54_rf["metrics"]["test"]["roc_auc"],
                    "val_recall": p54_rf["metrics"]["validation"]["observed_positive_recall"],
                    "test_recall": p54_rf["metrics"]["test"]["observed_positive_recall"],
                    "val_precision": p54_rf["metrics"]["validation"]["empirical_precision_lower_bound"],
                    "test_precision": p54_rf["metrics"]["test"]["empirical_precision_lower_bound"],
                    "threshold": p54_rf["metrics"]["validation"]["decision_threshold"],
                },
                "Phase_5_5_PU_Bagging": {
                    "val_pr_auc": pu_bag_meta["metrics"]["validation"]["pr_auc"],
                    "test_pr_auc": pu_bag_meta["metrics"]["test"]["pr_auc"],
                    "val_roc_auc": pu_bag_meta["metrics"]["validation"]["roc_auc"],
                    "test_roc_auc": pu_bag_meta["metrics"]["test"]["roc_auc"],
                    "val_recall": pu_bag_meta["metrics"]["validation"]["observed_positive_recall"],
                    "test_recall": pu_bag_meta["metrics"]["test"]["observed_positive_recall"],
                    "val_precision": pu_bag_meta["metrics"]["validation"]["empirical_precision_lower_bound"],
                    "test_precision": pu_bag_meta["metrics"]["test"]["empirical_precision_lower_bound"],
                    "threshold": pu_bag_meta["metrics"]["validation"]["decision_threshold"],
                    "runtime_sec": pu_bag_meta["runtime_seconds"],
                },
                "Phase_5_5_LightGBM_Unconstrained": {
                    "val_pr_auc": lgbm_uncon_meta["metrics"]["validation"]["pr_auc"],
                    "test_pr_auc": lgbm_uncon_meta["metrics"]["test"]["pr_auc"],
                    "val_roc_auc": lgbm_uncon_meta["metrics"]["validation"]["roc_auc"],
                    "test_roc_auc": lgbm_uncon_meta["metrics"]["test"]["roc_auc"],
                    "val_recall": lgbm_uncon_meta["metrics"]["validation"]["observed_positive_recall"],
                    "test_recall": lgbm_uncon_meta["metrics"]["test"]["observed_positive_recall"],
                    "val_precision": lgbm_uncon_meta["metrics"]["validation"]["empirical_precision_lower_bound"],
                    "test_precision": lgbm_uncon_meta["metrics"]["test"]["empirical_precision_lower_bound"],
                    "threshold": lgbm_uncon_meta["metrics"]["validation"]["decision_threshold"],
                    "runtime_sec": lgbm_uncon_meta["runtime_seconds"],
                },
                "Phase_5_5_LightGBM_Monotonic": {
                    "val_pr_auc": lgbm_mono_meta["metrics"]["validation"]["pr_auc"],
                    "test_pr_auc": lgbm_mono_meta["metrics"]["test"]["pr_auc"],
                    "val_roc_auc": lgbm_mono_meta["metrics"]["validation"]["roc_auc"],
                    "test_roc_auc": lgbm_mono_meta["metrics"]["test"]["roc_auc"],
                    "val_recall": lgbm_mono_meta["metrics"]["validation"]["observed_positive_recall"],
                    "test_recall": lgbm_mono_meta["metrics"]["test"]["observed_positive_recall"],
                    "val_precision": lgbm_mono_meta["metrics"]["validation"]["empirical_precision_lower_bound"],
                    "test_precision": lgbm_mono_meta["metrics"]["test"]["empirical_precision_lower_bound"],
                    "threshold": lgbm_mono_meta["metrics"]["validation"]["decision_threshold"],
                    "runtime_sec": lgbm_mono_meta["runtime_seconds"],
                },
            },
        }

        with open(self.output_dir / "benchmark_comparison.json", "w", encoding="utf-8") as f:
            json.dump(benchmark, f, indent=2)

        logger.info("Saved benchmark comparison to %s", self.output_dir / "benchmark_comparison.json")
        return benchmark


def run_phase_5_5_experiments() -> dict[str, Any]:
    """CLI / programmatic entrypoint for Phase 5.5."""
    runner = Phase55ExperimentRunner()
    return runner.run_full_benchmark()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    benchmark = run_phase_5_5_experiments()
    print("\n=== Phase 5.5 Benchmark Completed Successfully ===")
    for model, m in benchmark["model_comparison"].items():
        print(f"{model:35s} | Val PR-AUC: {m['val_pr_auc']:.4f} | Test PR-AUC: {m['test_pr_auc']:.4f} | Test ROC-AUC: {m['test_roc_auc']:.4f}")
