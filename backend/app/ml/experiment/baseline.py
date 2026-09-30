"""
Baseline Machine Learning Models for PU Flood Prediction (Phase 5.4).

Implements:
1. LogisticRegressionBaseline:
   - Transparent, interpretable L2-regularized linear model.
   - StandardScaler fitted strictly on Train split.
   - Deterministic random state (42).
   - Standardized coefficients and directionality.
2. RandomForestBaseline:
   - Non-linear ensemble tree baseline.
   - Deterministic random state (42).
   - Controlled complexity (n_estimators=100, max_depth=10, min_samples_leaf=5).
   - Mean decrease in impurity (MDI) feature importances.

CRITICAL: LightGBM / XGBoost / Neural networks are strictly forbidden in this phase.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class LogisticRegressionBaseline:
    """
    Standardized, L2-regularized Logistic Regression baseline under PU framing.

    Preprocessing:
    - StandardScaler fit ONLY on training split to eliminate temporal leakage.
    - Continuous features centered and scaled to unit variance.

    Interpretability:
    - Standardized regression coefficients beta_j indicate magnitude and direction of log-odds.
    """

    def __init__(
        self,
        C: float = 1.0,
        random_state: int = 42,
        class_weight: str | None = "balanced",
        max_iter: int = 1000,
    ):
        self.C = C
        self.random_state = random_state
        self.class_weight = class_weight
        self.max_iter = max_iter
        self.scaler = StandardScaler()
        self.model = LogisticRegression(
            C=self.C,
            solver="lbfgs",
            max_iter=self.max_iter,
            random_state=self.random_state,
            class_weight=self.class_weight,
        )
        self.fitted_: bool = False
        self.feature_names_: list[str] = []

    def fit(
        self,
        X_train: np.ndarray,
        s_train: np.ndarray,
        feature_names: list[str],
    ) -> LogisticRegressionBaseline:
        """
        Fit scaler and model strictly on training data.

        Parameters
        ----------
        X_train : np.ndarray
            Predictor matrix of shape (n_samples, n_features).
        s_train : np.ndarray
            Binary labeling indicator vector (1 = verified positive, 0 = unlabeled).
        feature_names : list[str]
            Ordered list of feature column names.
        """
        self.feature_names_ = list(feature_names)
        # Scaler fitted ONLY on training split
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled, s_train)
        self.fitted_ = True
        logger.info(
            "Fitted LogisticRegressionBaseline on %d samples with %d features.",
            X_train.shape[0],
            X_train.shape[1],
        )
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict continuous probability scores P(S=1 | X)."""
        if not self.fitted_:
            raise ValueError("Model is not fitted. Call fit() first.")
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]

    def get_coefficients(self) -> dict[str, Any]:
        """Return standardized coefficients, direction, and magnitude ranking."""
        if not self.fitted_:
            raise ValueError("Model is not fitted. Call fit() first.")
        coefs = self.model.coef_[0]
        results = []
        for name, c in zip(self.feature_names_, coefs):
            direction = "POSITIVE (+)" if c > 0 else "NEGATIVE (-)"
            results.append({
                "feature": name,
                "coefficient": round(float(c), 4),
                "abs_coefficient": round(abs(float(c)), 4),
                "direction": direction,
            })
        # Rank by absolute magnitude
        results.sort(key=lambda x: x["abs_coefficient"], reverse=True)
        return {
            "intercept": round(float(self.model.intercept_[0]), 4),
            "coefficients": results,
        }


class RandomForestBaseline:
    """
    Controlled Random Forest baseline under PU framing.

    Parameters:
    - n_estimators = 100
    - max_depth = 10
    - min_samples_leaf = 5
    - class_weight = 'balanced_subsample'
    - random_state = 42
    - n_jobs = -1
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 10,
        min_samples_leaf: int = 5,
        class_weight: str | None = "balanced_subsample",
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.class_weight = class_weight
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            class_weight=self.class_weight,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )
        self.fitted_: bool = False
        self.feature_names_: list[str] = []

    def fit(
        self,
        X_train: np.ndarray,
        s_train: np.ndarray,
        feature_names: list[str],
    ) -> RandomForestBaseline:
        """Fit Random Forest on training data."""
        self.feature_names_ = list(feature_names)
        self.model.fit(X_train, s_train)
        self.fitted_ = True
        logger.info(
            "Fitted RandomForestBaseline on %d samples with %d features.",
            X_train.shape[0],
            X_train.shape[1],
        )
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict continuous probability scores P(S=1 | X)."""
        if not self.fitted_:
            raise ValueError("Model is not fitted. Call fit() first.")
        return self.model.predict_proba(X)[:, 1]

    def get_feature_importances(self) -> list[dict[str, Any]]:
        """Return Gini impurity feature importances ranked in descending order."""
        if not self.fitted_:
            raise ValueError("Model is not fitted. Call fit() first.")
        importances = self.model.feature_importances_
        results = [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in zip(self.feature_names_, importances)
        ]
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results
