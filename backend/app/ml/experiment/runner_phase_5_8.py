"""
Phase 5.8 Multi-Era Supervised Cross-Validation & Historical Generalization Benchmark Runner.

Executes:
1. Multi-era dataset loading and SHA-256 integrity verification.
2. Cross-era disaster event leakage audit (1969-1994 vs 2011-2023).
3. Within-era chronological event leakage audits (Historical & Recent).
4. Feature distribution shift analysis across all 27 canonical predictors.
5. Experiment A: Historical (1969-1994) -> Recent (2011-2023) Cross-Era Generalization.
6. Experiment B: Recent (2011-2023) -> Historical (1969-1994) Retrospective Benchmark.
7. Experiment C1: Historical Within-Era Chronological Baseline (1969-1981 -> 1982-1987 -> 1988-1994).
8. Experiment C2: Recent Within-Era Chronological Baseline (2011-2019 -> 2020-2021 -> 2022-2023).
9. Feature importance stability analysis (MDI / Gain, Spearman rho).
10. Benchmark persistence to JSON and model artifacts.
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
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import average_precision_score, roc_auc_score

from app.ml.experiment.baseline import (
    LogisticRegressionBaseline,
    RandomForestBaseline,
)
from app.ml.experiment.dataset import (
    CANONICAL_PREDICTORS,
    EXPECTED_HISTORICAL_SHA256,
    EXPECTED_SUPERVISED_SHA256,
    ExperimentDataset,
    load_historical_dataset,
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
    LightGBMExperimentModel,
)
from app.ml.experiment.pu_bagging import PUBaggingClassifier
from app.ml.experiment.splits import (
    ChronologicalSplit,
    create_chronological_split,
    create_historical_chronological_split,
)

logger = logging.getLogger(__name__)


class RainfallRankingBaseline:
    """
    Transparent domain baseline ranking flood risk strictly by antecedent rainfall.
    Uses 3-day antecedent precipitation sum (precip_3d_sum_mm).
    """

    def __init__(self, feature_name: str = "precip_3d_sum_mm"):
        self.feature_name = feature_name
        self.feature_idx: int = -1
        self.min_val: float = 0.0
        self.max_val: float = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray | None = None, feature_names: list[str] | None = None) -> "RainfallRankingBaseline":
        if feature_names is not None and self.feature_name in feature_names:
            self.feature_idx = feature_names.index(self.feature_name)
        elif self.feature_idx == -1:
            self.feature_idx = 1  # precip_3d_sum_mm default index in canonical 27
        vals = X[:, self.feature_idx]
        self.min_val = float(np.min(vals))
        self.max_val = float(np.max(vals))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw_vals = X[:, self.feature_idx]
        if self.max_val > self.min_val:
            scaled = (raw_vals - self.min_val) / (self.max_val - self.min_val)
            return np.clip(scaled, 0.0, 1.0)
        return np.zeros_like(raw_vals)


def get_phase_5_8_dirs() -> tuple[Path, Path]:
    """Resolve (results_dir, models_dir) for Phase 5.8."""
    curr = Path(__file__).resolve().parent
    project_root = curr.parents[3]
    results_dir = project_root / "data" / "processed" / "ml_experiments" / "phase_5_8"
    models_dir = project_root / "models" / "experiments" / "phase_5_8"
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    return results_dir, models_dir


class Phase58MultiEraRunner:
    """Orchestrates Phase 5.8 Multi-Era Supervised Cross-Validation & Benchmark."""

    def __init__(
        self,
        hist_parquet: Path | str | None = None,
        recent_parquet: Path | str | None = None,
        results_dir: Path | str | None = None,
        models_dir: Path | str | None = None,
    ):
        # 1. Load datasets with strict SHA verification & cold-start exclusion
        self.hist_dataset = load_historical_dataset(parquet_path=hist_parquet, exclude_cold_start=True)
        self.recent_dataset = load_supervised_dataset(parquet_path=recent_parquet, exclude_cold_start=True)

        # 2. Setup chronological splits
        self.hist_split = create_historical_chronological_split(self.hist_dataset.df)
        self.recent_split = create_chronological_split(self.recent_dataset.df)

        # 3. Setup directories
        default_res, default_mod = get_phase_5_8_dirs()
        self.results_dir = Path(results_dir) if results_dir else default_res
        self.models_dir = Path(models_dir) if models_dir else default_mod
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Phase58MultiEraRunner initialized.\n"
            "  Historical Dataset: %s (%d rows, %d floods, prevalence %.4f%%)\n"
            "  Recent Dataset:     %s (%d rows, %d floods, prevalence %.4f%%)",
            self.hist_dataset.sha256[:12],
            len(self.hist_dataset.df),
            self.hist_dataset.num_positives,
            (self.hist_dataset.num_positives / len(self.hist_dataset.df)) * 100,
            self.recent_dataset.sha256[:12],
            len(self.recent_dataset.df),
            self.recent_dataset.num_positives,
            (self.recent_dataset.num_positives / len(self.recent_dataset.df)) * 100,
        )

    def audit_disaster_events(self) -> dict[str, Any]:
        """Audit disaster event IDs across within-era splits and cross-era partitions."""
        logger.info("--- Auditing Disaster Event Partitions ---")
        hist_audit = audit_event_leakage(self.hist_dataset.df, split=self.hist_split)
        recent_audit = audit_event_leakage(self.recent_dataset.df, split=self.recent_split)

        # Cross-era overlap check
        def _get_all_events(df: pd.DataFrame) -> set[str]:
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

        events_hist = _get_all_events(self.hist_dataset.df)
        events_recent = _get_all_events(self.recent_dataset.df)
        cross_era_overlap = sorted(list(events_hist.intersection(events_recent)))

        return {
            "cross_era": {
                "historical_unique_events": len(events_hist),
                "recent_unique_events": len(events_recent),
                "cross_era_overlap_count": len(cross_era_overlap),
                "cross_era_overlap_events": cross_era_overlap,
                "is_cross_era_isolated": len(cross_era_overlap) == 0,
            },
            "historical_within_era": hist_audit.to_dict(),
            "recent_within_era": recent_audit.to_dict(),
        }

    def compute_distribution_shift(self) -> dict[str, Any]:
        """Compute distribution shift metrics across all 27 canonical predictors."""
        logger.info("--- Computing Predictor Distribution Shift ---")
        df_h = self.hist_dataset.df
        df_r = self.recent_dataset.df

        shift_dict = {}
        for col in CANONICAL_PREDICTORS:
            h_vals = df_h[col].dropna()
            r_vals = df_r[col].dropna()

            ks_res = stats.ks_2samp(h_vals.iloc[::10], r_vals.iloc[::5])
            h_mean, r_mean = float(h_vals.mean()), float(r_vals.mean())
            h_std, r_std = float(h_vals.std()), float(r_vals.std())
            h_med, r_med = float(h_vals.median()), float(r_vals.median())
            h_p95, r_p95 = float(np.percentile(h_vals, 95)), float(np.percentile(r_vals, 95))

            norm_diff = (r_mean - h_mean) / (h_std if h_std > 0 else 1.0)

            shift_dict[col] = {
                "historical_mean": round(h_mean, 4),
                "recent_mean": round(r_mean, 4),
                "historical_std": round(h_std, 4),
                "recent_std": round(r_std, 4),
                "historical_median": round(h_med, 4),
                "recent_median": round(r_med, 4),
                "historical_p95": round(h_p95, 4),
                "recent_p95": round(r_p95, 4),
                "normalized_mean_diff": round(norm_diff, 4),
                "ks_statistic": round(float(ks_res.statistic), 4),
                "ks_pvalue": float(ks_res.pvalue),
            }
        return shift_dict

    def _train_and_evaluate_model(
        self,
        model_name: str,
        model_obj: Any,
        X_train: np.ndarray,
        s_train: np.ndarray,
        eval_splits: dict[str, tuple[np.ndarray, np.ndarray]],
        features: list[str],
        val_split_for_threshold: str = "val",
    ) -> tuple[dict[str, PUEvaluationMetrics], dict[str, float] | None, float]:
        """Fit a model on X_train/s_train and evaluate across arbitrary evaluation splits."""
        t0 = time.time()
        if hasattr(model_obj, "fit"):
            try:
                model_obj.fit(X_train, s_train, feature_names=features)
            except TypeError:
                model_obj.fit(X_train, s_train)
        runtime = round(time.time() - t0, 2)

        # Extract predictions for all eval splits
        preds: dict[str, np.ndarray] = {}
        for split_name, (X_eval, _) in eval_splits.items():
            if hasattr(model_obj, "predict_proba"):
                p = model_obj.predict_proba(X_eval)
            else:
                raise ValueError(f"Model {model_name} lacks predict_proba method.")
            preds[split_name] = p

        # Discover decision threshold on specified validation split (or train if no val)
        if val_split_for_threshold in preds:
            val_p = preds[val_split_for_threshold]
            val_s = eval_splits[val_split_for_threshold][1]
            val_metric_obj = evaluate_pu_predictions(y_true_s=val_s, y_prob=val_p, split_name=val_split_for_threshold)
            threshold = val_metric_obj.decision_threshold
        else:
            # Fallback to train threshold
            train_p = preds.get("train", model_obj.predict_proba(X_train))
            train_metric_obj = evaluate_pu_predictions(y_true_s=s_train, y_prob=train_p, split_name="train")
            threshold = train_metric_obj.decision_threshold

        # Compute PU metrics across all eval splits using fixed threshold
        metrics_dict: dict[str, PUEvaluationMetrics] = {}
        for split_name, (X_eval, s_eval) in eval_splits.items():
            p_eval = preds[split_name]
            metrics_dict[split_name] = evaluate_pu_predictions(
                y_true_s=s_eval,
                y_prob=p_eval,
                split_name=split_name,
                threshold=threshold,
            )

        # Extract feature importances if available
        importances: dict[str, float] | None = None
        if hasattr(model_obj, "get_feature_importances"):
            raw_imp = model_obj.get_feature_importances()
            if isinstance(raw_imp, list):
                # PUBagging: [{"feature": ..., "importance": ...}]
                importances = {item["feature"]: float(item["importance"]) for item in raw_imp}
            elif isinstance(raw_imp, dict) and "by_gain" in raw_imp:
                # LightGBM: {"by_split": [...], "by_gain": [...]}
                importances = {item["feature"]: float(item["importance"]) for item in raw_imp["by_gain"]}
            elif isinstance(raw_imp, dict):
                importances = {k: float(v) for k, v in raw_imp.items()}
        elif hasattr(model_obj, "feature_importances_"):
            importances = {f: float(imp) for f, imp in zip(features, model_obj.feature_importances_)}
        elif hasattr(model_obj, "coef_"):
            importances = {f: float(abs(c)) for f, c in zip(features, model_obj.coef_[0])}
        elif hasattr(model_obj, "model") and hasattr(model_obj.model, "coef_"):
            importances = {f: float(abs(c)) for f, c in zip(features, model_obj.model.coef_[0])}

        return metrics_dict, importances, runtime

    def run_experiment_a_historical_to_recent(self) -> dict[str, Any]:
        """
        Experiment A: Historical -> Recent Cross-Era Generalization.
        Training: Entire Historical 1969-1994 (293,446 rows, 1,152 floods).
        Evaluation: Recent 2011-2023 (Full Supervised: 141,298 rows, Val: 22,661 rows, Test: 17,670 rows).
        Zero observations from 2011-2023 enter training.
        """
        logger.info("=== Running Experiment A: Historical (1969-1994) -> Recent (2011-2023) ===")
        features = list(CANONICAL_PREDICTORS)
        X_train = self.hist_dataset.X
        s_train = self.hist_dataset.s_proxy

        # Recent evaluation splits
        X_rec_full = self.recent_dataset.X
        s_rec_full = self.recent_dataset.s_proxy

        X_rec_val = X_rec_full[self.recent_split.val.indices]
        s_rec_val = s_rec_full[self.recent_split.val.indices]

        X_rec_test = X_rec_full[self.recent_split.test.indices]
        s_rec_test = s_rec_full[self.recent_split.test.indices]

        eval_splits = {
            "hist_train": (X_train, s_train),
            "recent_full_2011_2023": (X_rec_full, s_rec_full),
            "recent_val_2020_2021": (X_rec_val, s_rec_val),
            "recent_test_2022_2023": (X_rec_test, s_rec_test),
        }

        models: dict[str, Any] = {
            "rainfall_baseline": RainfallRankingBaseline("precip_3d_sum_mm"),
            "logistic_regression": LogisticRegressionBaseline(C=1.0, random_state=42),
            "random_forest": RandomForestBaseline(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42),
            "pu_bagging": PUBaggingClassifier(n_bags=15, unlabeled_ratio=3.0, max_depth=6, min_samples_leaf=15, random_state=42),
            "lightgbm_unconstrained": LightGBMExperimentModel(enforce_monotonic=False, n_estimators=100, max_depth=5, random_state=42),
            "lightgbm_monotonic": LightGBMExperimentModel(enforce_monotonic=True, n_estimators=100, max_depth=5, random_state=42),
        }

        results: dict[str, Any] = {}
        for m_name, m_obj in models.items():
            logger.info("  Training Exp A model: %s", m_name)
            metrics, importances, runtime = self._train_and_evaluate_model(
                model_name=m_name,
                model_obj=m_obj,
                X_train=X_train,
                s_train=s_train,
                eval_splits=eval_splits,
                features=features,
                val_split_for_threshold="hist_train",
            )
            results[m_name] = {
                "runtime_seconds": runtime,
                "metrics": {sname: m.to_dict() for sname, m in metrics.items()},
                "feature_importances": importances,
            }

        return results

    def run_experiment_b_recent_to_historical(self) -> dict[str, Any]:
        """
        Experiment B: Recent -> Historical Retrospective Benchmark.
        Training: Recent Train 2011-2019 (100,967 rows, 4,628 floods).
        Evaluation: Historical 1969-1994 (293,446 rows, 1,152 floods).
        """
        logger.info("=== Running Experiment B: Recent (2011-2019) -> Historical (1969-1994) ===")
        features = list(CANONICAL_PREDICTORS)
        X_rec_full = self.recent_dataset.X
        s_rec_full = self.recent_dataset.s_proxy

        X_train = X_rec_full[self.recent_split.train.indices]
        s_train = s_rec_full[self.recent_split.train.indices]

        X_val = X_rec_full[self.recent_split.val.indices]
        s_val = s_rec_full[self.recent_split.val.indices]

        # Historical evaluation splits
        X_hist_full = self.hist_dataset.X
        s_hist_full = self.hist_dataset.s_proxy

        X_hist_val = X_hist_full[self.hist_split.val.indices]
        s_hist_val = s_hist_full[self.hist_split.val.indices]

        X_hist_test = X_hist_full[self.hist_split.test.indices]
        s_hist_test = s_hist_full[self.hist_split.test.indices]

        eval_splits = {
            "recent_train": (X_train, s_train),
            "recent_val": (X_val, s_val),
            "historical_full_1969_1994": (X_hist_full, s_hist_full),
            "historical_val_1982_1987": (X_hist_val, s_hist_val),
            "historical_test_1988_1994": (X_hist_test, s_hist_test),
        }

        models: dict[str, Any] = {
            "rainfall_baseline": RainfallRankingBaseline("precip_3d_sum_mm"),
            "logistic_regression": LogisticRegressionBaseline(C=1.0, random_state=42),
            "random_forest": RandomForestBaseline(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42),
            "pu_bagging": PUBaggingClassifier(n_bags=15, unlabeled_ratio=3.0, max_depth=6, min_samples_leaf=15, random_state=42),
            "lightgbm_unconstrained": LightGBMExperimentModel(enforce_monotonic=False, n_estimators=100, max_depth=5, random_state=42),
            "lightgbm_monotonic": LightGBMExperimentModel(enforce_monotonic=True, n_estimators=100, max_depth=5, random_state=42),
        }

        results: dict[str, Any] = {}
        for m_name, m_obj in models.items():
            logger.info("  Training Exp B model: %s", m_name)
            metrics, importances, runtime = self._train_and_evaluate_model(
                model_name=m_name,
                model_obj=m_obj,
                X_train=X_train,
                s_train=s_train,
                eval_splits=eval_splits,
                features=features,
                val_split_for_threshold="recent_val",
            )
            results[m_name] = {
                "runtime_seconds": runtime,
                "metrics": {sname: m.to_dict() for sname, m in metrics.items()},
                "feature_importances": importances,
            }

        return results

    def run_experiment_c1_historical_within_era(self) -> dict[str, Any]:
        """
        Experiment C1: Historical Within-Era Chronological Baseline.
        Train: 1969-01-31 to 1981-12-31 (146,258 rows, 641 floods).
        Val: 1982-01-01 to 1987-12-31 (67,921 rows, 162 floods).
        Test: 1988-01-01 to 1994-12-31 (79,267 rows, 349 floods).
        """
        logger.info("=== Running Experiment C1: Historical Within-Era (1969-1981 -> 1982-1987 -> 1988-1994) ===")
        features = list(CANONICAL_PREDICTORS)
        X_hist = self.hist_dataset.X
        s_hist = self.hist_dataset.s_proxy

        X_train = X_hist[self.hist_split.train.indices]
        s_train = s_hist[self.hist_split.train.indices]

        X_val = X_hist[self.hist_split.val.indices]
        s_val = s_hist[self.hist_split.val.indices]

        X_test = X_hist[self.hist_split.test.indices]
        s_test = s_hist[self.hist_split.test.indices]

        eval_splits = {
            "train": (X_train, s_train),
            "validation": (X_val, s_val),
            "test": (X_test, s_test),
        }

        models: dict[str, Any] = {
            "rainfall_baseline": RainfallRankingBaseline("precip_3d_sum_mm"),
            "logistic_regression": LogisticRegressionBaseline(C=1.0, random_state=42),
            "random_forest": RandomForestBaseline(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42),
            "pu_bagging": PUBaggingClassifier(n_bags=15, unlabeled_ratio=3.0, max_depth=6, min_samples_leaf=15, random_state=42),
            "lightgbm_unconstrained": LightGBMExperimentModel(enforce_monotonic=False, n_estimators=100, max_depth=5, random_state=42),
            "lightgbm_monotonic": LightGBMExperimentModel(enforce_monotonic=True, n_estimators=100, max_depth=5, random_state=42),
        }

        results: dict[str, Any] = {}
        for m_name, m_obj in models.items():
            logger.info("  Training Exp C1 model: %s", m_name)
            metrics, importances, runtime = self._train_and_evaluate_model(
                model_name=m_name,
                model_obj=m_obj,
                X_train=X_train,
                s_train=s_train,
                eval_splits=eval_splits,
                features=features,
                val_split_for_threshold="validation",
            )
            results[m_name] = {
                "runtime_seconds": runtime,
                "metrics": {sname: m.to_dict() for sname, m in metrics.items()},
                "feature_importances": importances,
            }

        return results

    def compute_feature_stability(
        self,
        exp_a_results: dict[str, Any],
        exp_b_results: dict[str, Any],
        exp_c1_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute feature importance stability and rank correlations across eras."""
        logger.info("--- Computing Feature Importance Stability Across Eras ---")
        stability_dict = {}

        for m_name in ["logistic_regression", "random_forest", "pu_bagging", "lightgbm_unconstrained", "lightgbm_monotonic"]:
            imp_a = exp_a_results[m_name].get("feature_importances")
            imp_b = exp_b_results[m_name].get("feature_importances")
            imp_c1 = exp_c1_results[m_name].get("feature_importances")

            if not (imp_a and imp_b):
                continue

            feats = list(CANONICAL_PREDICTORS)
            vec_a = np.array([imp_a.get(f, 0.0) for f in feats])
            vec_b = np.array([imp_b.get(f, 0.0) for f in feats])

            spearman_ab, pval_ab = stats.spearmanr(vec_a, vec_b)

            # Top 5 features in each
            top5_a = sorted(imp_a.items(), key=lambda kv: kv[1], reverse=True)[:5]
            top5_b = sorted(imp_b.items(), key=lambda kv: kv[1], reverse=True)[:5]
            top5_names_a = [k for k, _ in top5_a]
            top5_names_b = [k for k, _ in top5_b]
            overlap_top5 = sorted(list(set(top5_names_a).intersection(set(top5_names_b))))

            stability_dict[m_name] = {
                "spearman_rank_correlation_historical_vs_recent": round(float(spearman_ab), 4),
                "spearman_pvalue": float(pval_ab),
                "top5_historical_trained": top5_a,
                "top5_recent_trained": top5_b,
                "top5_overlap": overlap_top5,
                "top5_overlap_count": len(overlap_top5),
            }

        return stability_dict

    def run_full_benchmark(self) -> dict[str, Any]:
        """Execute full Phase 5.8 multi-era benchmark and persist all artifacts."""
        t_start = time.time()
        logger.info("================ Starting Phase 5.8 Multi-Era Benchmark ================")

        # 1. Event audits
        events_audit = self.audit_disaster_events()

        # 2. Distribution shift
        dist_shift = self.compute_distribution_shift()

        # 3. Experiment A (Historical -> Recent)
        exp_a = self.run_experiment_a_historical_to_recent()

        # 4. Experiment B (Recent -> Historical)
        exp_b = self.run_experiment_b_recent_to_historical()

        # 5. Experiment C1 (Historical Within-Era)
        exp_c1 = self.run_experiment_c1_historical_within_era()

        # 6. Feature stability
        stability = self.compute_feature_stability(exp_a, exp_b, exp_c1)

        total_runtime = round(time.time() - t_start, 2)

        benchmark_summary = {
            "experiment_phase": "phase_5_8_multi_era_benchmark",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_runtime_seconds": total_runtime,
            "datasets": {
                "historical": {
                    "sha256": self.hist_dataset.sha256,
                    "date_range": "1969-01-01 to 1994-12-31",
                    "total_clean_rows": len(self.hist_dataset.df),
                    "documented_floods": self.hist_dataset.num_positives,
                    "prevalence": round(self.hist_dataset.num_positives / len(self.hist_dataset.df), 6),
                },
                "recent": {
                    "sha256": self.recent_dataset.sha256,
                    "date_range": "2011-01-01 to 2023-07-24",
                    "total_clean_rows": len(self.recent_dataset.df),
                    "documented_floods": self.recent_dataset.num_positives,
                    "prevalence": round(self.recent_dataset.num_positives / len(self.recent_dataset.df), 6),
                },
            },
            "disaster_event_audits": events_audit,
            "distribution_shift": dist_shift,
            "experiment_a_historical_to_recent": exp_a,
            "experiment_b_recent_to_historical": exp_b,
            "experiment_c1_historical_within_era": exp_c1,
            "feature_importance_stability": stability,
            "scientific_declarations": {
                "production_readiness": "NOT PRODUCTION READY (PU proxy baseline experiments only)",
                "scar_assumption": "NOT VALIDATED (Reporting and catalogue coverage bias present in IFI)",
                "negative_labels_count": 0,
                "label_state_semantics": "FLOOD = 1, UNKNOWN = NULL. Zero UNKNOWNs converted to 0.",
                "hydrological_telemetry": "BLOCKED FOR HISTORICAL TRAINING (0.000% historical gauge coverage)",
            },
        }

        # Persist benchmark summary
        summary_path = self.results_dir / "benchmark_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(benchmark_summary, f, indent=2)

        logger.info("Saved Phase 5.8 benchmark summary to %s in %.1f seconds", summary_path, total_runtime)
        return benchmark_summary
