"""
Ensemble Positive-Unlabeled (PU) Bagging (Phase 5.5).

Implements the non-SCAR-aware PU Bagging algorithm (Mordelet & Vert, 2014).

Key properties:
1. SCAR is NOT required: Does not attempt to estimate or rescale by a global label frequency c.
2. Contamination mitigation: Repeatedly draws random bootstrap subsamples of the unlabeled set U
   to form balanced pseudo-background reference sets, reducing the influence of hidden positives in U.
3. Ranking score: Aggregates probability scores across K base tree estimators to produce an empirical
   PU ranking score.
4. Calibration note: Predictions are continuous ranking scores, NOT calibrated physical flood probabilities.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)


class PUBaggingClassifier:
    """
    Ensemble PU Bagging classifier.

    Parameters
    ----------
    n_bags : int
        Number of bootstrap bagging iterations (default 15).
    unlabeled_ratio : float
        Ratio of unlabeled instances sampled relative to the number of positives (default 3.0).
    max_depth : int
        Maximum depth of base DecisionTreeClassifier estimators (default 6).
    min_samples_leaf : int
        Minimum samples per leaf in base estimators (default 15).
    random_state : int
        Base random state for deterministic reproduction (default 42).
    """

    def __init__(
        self,
        n_bags: int = 15,
        unlabeled_ratio: float = 3.0,
        max_depth: int = 6,
        min_samples_leaf: int = 15,
        random_state: int = 42,
    ):
        self.n_bags = n_bags
        self.unlabeled_ratio = unlabeled_ratio
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state

        self.estimators_: list[DecisionTreeClassifier] = []
        self.fitted_: bool = False
        self.feature_names_: list[str] = []

    def fit(
        self,
        X_train: np.ndarray,
        s_train: np.ndarray,
        feature_names: list[str],
    ) -> PUBaggingClassifier:
        """
        Fit ensemble of base estimators across bootstrap subsamples of unlabeled data.

        Parameters
        ----------
        X_train : np.ndarray
            Training features (n_samples, n_features).
        s_train : np.ndarray
            Binary labeling indicator (1 = verified positive, 0 = unlabeled).
        feature_names : list[str]
            Canonical feature column names.
        """
        self.feature_names_ = list(feature_names)
        pos_indices = np.where(s_train == 1)[0]
        unlab_indices = np.where(s_train == 0)[0]

        n_pos = len(pos_indices)
        n_unlab_sample = int(np.clip(n_pos * self.unlabeled_ratio, 1, len(unlab_indices)))

        rng = np.random.RandomState(self.random_state)
        self.estimators_ = []

        X_pos = X_train[pos_indices]
        y_pos = np.ones(n_pos, dtype=np.int32)

        for b in range(self.n_bags):
            # Draw random subsample of unlabeled background without replacement
            bag_unlab_idx = rng.choice(unlab_indices, size=n_unlab_sample, replace=False)
            X_bag_unlab = X_train[bag_unlab_idx]
            y_bag_unlab = np.zeros(n_unlab_sample, dtype=np.int32)

            X_bag = np.vstack([X_pos, X_bag_unlab])
            y_bag = np.concatenate([y_pos, y_bag_unlab])

            clf = DecisionTreeClassifier(
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.random_state + b,
            )
            clf.fit(X_bag, y_bag)
            self.estimators_.append(clf)

        self.fitted_ = True
        logger.info(
            "Fitted PUBaggingClassifier with %d bags (each: %d Positives, %d Unlabeled subsamples).",
            self.n_bags,
            n_pos,
            n_unlab_sample,
        )
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict average probability score across all ensemble bags."""
        if not self.fitted_:
            raise ValueError("PUBaggingClassifier is not fitted. Call fit() first.")

        probs = np.zeros(len(X), dtype=np.float64)
        for clf in self.estimators_:
            probs += clf.predict_proba(X)[:, 1]
        return probs / len(self.estimators_)

    def get_feature_importances(self) -> list[dict[str, Any]]:
        """Return average feature importances across all base estimators."""
        if not self.fitted_:
            raise ValueError("PUBaggingClassifier is not fitted. Call fit() first.")

        importances = np.mean([clf.feature_importances_ for clf in self.estimators_], axis=0)
        results = [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in zip(self.feature_names_, importances)
        ]
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results
