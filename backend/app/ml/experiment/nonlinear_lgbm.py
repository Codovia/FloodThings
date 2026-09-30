"""
Nonlinear Tree Benchmark: LightGBM Unconstrained and Monotonically Constrained (Phase 5.5).

Implements:
1. LightGBMUnconstrained:
   - Conservative gradient-boosted decision trees.
   - Standard balanced class weighting for PU proxy labeling.
2. LightGBMMonotonic:
   - Enforces domain physical monotonicity constraints on cumulative precipitation features:
     * precip_1d_mm (+1)
     * precip_3d_sum_mm (+1)
     * precip_7d_sum_mm (+1)
     * precip_14d_sum_mm (+1)
     * precip_30d_sum_mm (+1)
     * precip_7d_max_mm (+1)
     * precip_14d_max_mm (+1)
   - All other 20 features remain strictly unconstrained (0) due to complex non-monotonic topography
     and meteorological interactions.
"""

from __future__ import annotations

import logging
from typing import Any

from lightgbm import LGBMClassifier
import numpy as np

logger = logging.getLogger(__name__)

# Features with domain physical monotonicity: higher antecedent rainfall accumulation cannot decrease flood propensity
MONOTONIC_FEATURE_CONSTRAINTS: dict[str, int] = {
    "precip_1d_mm": 1,
    "precip_3d_sum_mm": 1,
    "precip_7d_sum_mm": 1,
    "precip_14d_sum_mm": 1,
    "precip_30d_sum_mm": 1,
    "precip_7d_max_mm": 1,
    "precip_14d_max_mm": 1,
}


class LightGBMExperimentModel:
    """
    Controlled LightGBM classifier supporting optional monotonic constraints.

    Parameters
    ----------
    enforce_monotonic : bool
        If True, applies +1 monotonic constraints to cumulative precipitation features.
    n_estimators : int
        Number of boosting trees (default 100).
    learning_rate : float
        Boosting learning rate (default 0.05).
    max_depth : int
        Maximum tree depth (default 5).
    num_leaves : int
        Maximum tree leaves (default 31).
    min_child_samples : int
        Minimum data samples in leaf (default 50).
    class_weight : str | None
        Class weight setting (default 'balanced').
    random_state : int
        Deterministic random seed (default 42).
    """

    def __init__(
        self,
        enforce_monotonic: bool = False,
        n_estimators: int = 100,
        learning_rate: float = 0.05,
        max_depth: int = 5,
        num_leaves: int = 31,
        min_child_samples: int = 50,
        class_weight: str | None = "balanced",
        random_state: int = 42,
    ):
        self.enforce_monotonic = enforce_monotonic
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.min_child_samples = min_child_samples
        self.class_weight = class_weight
        self.random_state = random_state

        self.model: LGBMClassifier | None = None
        self.fitted_: bool = False
        self.feature_names_: list[str] = []
        self.constraint_vector_: list[int] = []

    def fit(
        self,
        X_train: np.ndarray,
        s_train: np.ndarray,
        feature_names: list[str],
    ) -> LightGBMExperimentModel:
        """Fit LightGBM model on training data."""
        self.feature_names_ = list(feature_names)

        # Build monotonic constraints vector matching exact feature ordering
        if self.enforce_monotonic:
            self.constraint_vector_ = [
                MONOTONIC_FEATURE_CONSTRAINTS.get(feat, 0)
                for feat in self.feature_names_
            ]
        else:
            self.constraint_vector_ = [0] * len(self.feature_names_)

        self.model = LGBMClassifier(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            num_leaves=self.num_leaves,
            min_child_samples=self.min_child_samples,
            class_weight=self.class_weight,
            monotone_constraints=self.constraint_vector_ if self.enforce_monotonic else None,
            random_state=self.random_state,
            n_jobs=-1,
            verbose=-1,
        )

        self.model.fit(X_train, s_train)
        self.fitted_ = True
        logger.info(
            "Fitted LightGBMExperimentModel (monotonic=%s) on %d samples with %d features.",
            self.enforce_monotonic,
            X_train.shape[0],
            X_train.shape[1],
        )
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict continuous probability scores P(S=1 | X)."""
        if not self.fitted_ or self.model is None:
            raise ValueError("Model is not fitted. Call fit() first.")
        return self.model.predict_proba(X)[:, 1]

    def get_feature_importances(self) -> dict[str, list[dict[str, Any]]]:
        """Return split count and gain feature importances."""
        if not self.fitted_ or self.model is None:
            raise ValueError("Model is not fitted. Call fit() first.")

        split_imps = self.model.booster_.feature_importance(importance_type="split")
        gain_imps = self.model.booster_.feature_importance(importance_type="gain")

        split_results = [
            {"feature": name, "importance": int(imp)}
            for name, imp in zip(self.feature_names_, split_imps)
        ]
        split_results.sort(key=lambda x: x["importance"], reverse=True)

        gain_results = [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in zip(self.feature_names_, gain_imps)
        ]
        gain_results.sort(key=lambda x: x["importance"], reverse=True)

        return {
            "by_split": split_results,
            "by_gain": gain_results,
        }
