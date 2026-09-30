"""
Positive-Unlabeled (PU) Evaluation Metrics (Phase 5.4).

Provides mathematically grounded evaluation for positive-unlabeled settings where:
- P = Verified Positive Flood observations (S=1, Y=1)
- U = Unlabeled observations (S=0, Y in {0, 1})
- N = 0 (No verified negative ground-truth labels exist)

Key principles:
1. Accuracy is strictly prohibited as a primary evaluation metric.
2. PR-AUC and ROC-AUC are calculated on observed labeling indicator S.
   Under SCAR (Selected At Random), ranking on S is monotonic with true flood risk.
3. Observed Precision TP / (TP + FP_u) is a conservative lower bound on true precision.
4. Specificity / True Negative Rate is strictly marked "NOT APPLICABLE".
5. Reports Elkan-Noto c parameter and Lee-Liu PU ranking criterion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    fbeta_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


@dataclass
class PUEvaluationMetrics:
    """
    Standardized PU-aware proxy evaluation metrics.

    IMPORTANT SCIENTIFIC DISTINCTION:
    This evaluates positive-vs-unlabeled (PU) proxy separation, NOT true binary classification.
    True binary classification is unavailable because verified NO_FLOOD = 0 in the ground truth.
    """

    split_name: str
    total_samples: int
    verified_positives: int
    unlabeled_samples: int
    verified_negatives: int
    observed_prevalence: float
    roc_auc: float
    pr_auc: float
    brier_score_proxy: float
    decision_threshold: float
    observed_positive_recall: float
    empirical_precision_lower_bound: float
    f1_score_empirical: float
    f2_score_empirical: float
    lee_liu_pu_criterion: float
    elkan_noto_c_estimate: float
    # Counts
    true_positives: int
    false_negatives: int
    predicted_positives_in_unlabeled: int
    predicted_unlabeled_in_unlabeled: int
    # Scientific validity declarations
    evaluation_type: str = (
        "positive_vs_unlabeled_proxy_evaluation (NOT true binary classification)"
    )
    scar_status: str = (
        "NOT VALIDATED (IFI catalogue reflects reporting, detection, and media biases; SCAR cannot be assumed)"
    )
    specificity_status: str = (
        "NOT APPLICABLE: Zero verified negative labels exist. UNKNOWN cannot be treated as negative."
    )
    accuracy_status: str = (
        "NOT APPLICABLE: Standard accuracy conflates unlabeled observations with true negatives."
    )

    @property
    def recall_on_positives(self) -> float:
        """Alias for backward compatibility."""
        return self.observed_positive_recall

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_pu_predictions(
    y_true_s: np.ndarray,
    y_prob: np.ndarray,
    split_name: str = "validation",
    threshold: float | None = None,
    target_metric_for_threshold: str = "f1",
) -> PUEvaluationMetrics:
    """
    Evaluate predicted flood probabilities under the Positive-Unlabeled (PU) framework.

    Parameters
    ----------
    y_true_s : np.ndarray
        Binary indicator of observed labels (1 = verified FLOOD, 0 = UNKNOWN).
    y_prob : np.ndarray
        Continuous predicted probability / decision score from model.
    split_name : str
        Name of partition (e.g. 'validation', 'test').
    threshold : float | None
        Decision threshold. If None, computes optimal threshold maximizing target_metric.
    target_metric_for_threshold : str
        Metric to optimize threshold for ('f1' or 'f2').
    """
    n_samples = len(y_true_s)
    n_pos = int(np.sum(y_true_s == 1))
    n_unlab = int(np.sum(y_true_s == 0))
    prevalence = n_pos / n_samples if n_samples > 0 else 0.0

    # 1. Continuous Ranking Metrics
    try:
        roc_auc = float(roc_auc_score(y_true_s, y_prob))
    except Exception:
        roc_auc = 0.5

    try:
        pr_auc = float(average_precision_score(y_true_s, y_prob))
    except Exception:
        pr_auc = prevalence

    # Brier score against proxy indicator S
    brier = float(brier_score_loss(y_true_s, y_prob))

    # 2. Optimal Threshold Selection
    if threshold is None:
        precisions, recalls, thresholds = precision_recall_curve(y_true_s, y_prob)
        if target_metric_for_threshold == "f2":
            scores = np.where(
                (4 * precisions + recalls) > 0,
                (1 + 4) * (precisions * recalls) / (4 * precisions + recalls + 1e-12),
                0.0,
            )
        else:
            scores = np.where(
                (precisions + recalls) > 0,
                2 * (precisions * recalls) / (precisions + recalls + 1e-12),
                0.0,
            )
        best_idx = int(np.argmax(scores))
        if best_idx < len(thresholds):
            threshold = float(thresholds[best_idx])
        else:
            threshold = 0.5
    else:
        threshold = float(threshold)

    y_pred = (y_prob >= threshold).astype(int)

    # 3. Discrete PU Metric Computations
    tp = int(np.sum((y_true_s == 1) & (y_pred == 1)))
    fn = int(np.sum((y_true_s == 1) & (y_pred == 0)))
    fp_u = int(np.sum((y_true_s == 0) & (y_pred == 1)))
    tn_u = int(np.sum((y_true_s == 0) & (y_pred == 0)))

    recall = float(recall_score(y_true_s, y_pred, zero_division=0))
    precision_lower_bound = float(precision_score(y_true_s, y_pred, zero_division=0))
    f1 = float(fbeta_score(y_true_s, y_pred, beta=1.0, zero_division=0))
    f2 = float(fbeta_score(y_true_s, y_pred, beta=2.0, zero_division=0))

    # 4. Lee & Liu (2003) PU Ranking Criterion: Recall^2 / P(Y_hat = 1)
    p_pred_pos = float(np.mean(y_pred == 1))
    lee_liu_criterion = (recall**2) / (p_pred_pos + 1e-6)

    # 5. Elkan & Noto (2008) Label Frequency Estimator: E[g(X) | S=1]
    elkan_noto_c = float(np.mean(y_prob[y_true_s == 1])) if n_pos > 0 else 0.0

    return PUEvaluationMetrics(
        split_name=split_name,
        total_samples=n_samples,
        verified_positives=n_pos,
        unlabeled_samples=n_unlab,
        verified_negatives=0,
        observed_prevalence=round(prevalence, 6),
        roc_auc=round(roc_auc, 4),
        pr_auc=round(pr_auc, 4),
        brier_score_proxy=round(brier, 4),
        decision_threshold=round(threshold, 4),
        observed_positive_recall=round(recall, 4),
        empirical_precision_lower_bound=round(precision_lower_bound, 4),
        f1_score_empirical=round(f1, 4),
        f2_score_empirical=round(f2, 4),
        lee_liu_pu_criterion=round(lee_liu_criterion, 4),
        elkan_noto_c_estimate=round(elkan_noto_c, 4),
        true_positives=tp,
        false_negatives=fn,
        predicted_positives_in_unlabeled=fp_u,
        predicted_unlabeled_in_unlabeled=tn_u,
    )
