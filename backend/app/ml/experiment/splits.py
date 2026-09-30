"""
Chronological Temporal Splitting (Phase 5.4).

Implements strict chronological train / validation / test partitioning:
- Train: 2011-01-01 to 2019-12-31
- Validation: 2020-01-01 to 2021-12-31
- Held-Out Test: 2022-01-01 to 2023-07-24
- Forward Inference: 2023-07-25 to 2025-12-31 (Unlabeled, not evaluated here)

Enforces:
1. Strict temporal causality (T_train < T_val < T_test).
2. Zero row overlap across splits.
3. No random row shuffling or k-fold cross-validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as dt_date
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SplitPartition:
    """Metadata and indices for a single temporal partition."""

    name: str
    mask: np.ndarray
    indices: np.ndarray
    start_date: str
    end_date: str
    total_samples: int
    positive_samples: int
    unlabeled_samples: int
    prevalence: float


@dataclass(frozen=True)
class ChronologicalSplit:
    """Container for the three chronological partitions."""

    train: SplitPartition
    val: SplitPartition
    test: SplitPartition

    def validate_causality(self) -> None:
        """Validate non-overlapping chronological order."""
        t_end = dt_date.fromisoformat(self.train.end_date)
        v_start = dt_date.fromisoformat(self.val.start_date)
        v_end = dt_date.fromisoformat(self.val.end_date)
        test_start = dt_date.fromisoformat(self.test.start_date)

        if t_end >= v_start:
            raise ValueError(
                f"Train end ({t_end}) must strictly precede Validation start ({v_start})"
            )
        if v_end >= test_start:
            raise ValueError(
                f"Validation end ({v_end}) must strictly precede Test start ({test_start})"
            )


def create_chronological_split(
    df: pd.DataFrame,
    train_end_date: str = "2019-12-31",
    val_start_date: str = "2020-01-01",
    val_end_date: str = "2021-12-31",
    test_start_date: str = "2022-01-01",
    test_end_date: str = "2023-07-24",
) -> ChronologicalSplit:
    """
    Partition dataset into strictly chronological Train, Validation, and Test subsets.
    """
    dates = df["target_date"].astype(str)
    labels = df["label_state"].astype(str)

    train_mask = (dates <= train_end_date).to_numpy()
    val_mask = ((dates >= val_start_date) & (dates <= val_end_date)).to_numpy()
    test_mask = ((dates >= test_start_date) & (dates <= test_end_date)).to_numpy()

    # Verify mutual exclusivity
    if np.any(train_mask & val_mask):
        raise ValueError("Overlap detected between Train and Validation splits.")
    if np.any(val_mask & test_mask):
        raise ValueError("Overlap detected between Validation and Test splits.")
    if np.any(train_mask & test_mask):
        raise ValueError("Overlap detected between Train and Test splits.")

    def _build_partition(name: str, mask: np.ndarray) -> SplitPartition:
        indices = np.where(mask)[0]
        sub_dates = dates.iloc[indices]
        sub_labels = labels.iloc[indices]

        n_tot = len(indices)
        n_pos = int((sub_labels == "FLOOD").sum())
        n_unlab = int((sub_labels == "UNKNOWN").sum())
        prev = n_pos / n_tot if n_tot > 0 else 0.0

        return SplitPartition(
            name=name,
            mask=mask,
            indices=indices,
            start_date=str(sub_dates.min()),
            end_date=str(sub_dates.max()),
            total_samples=n_tot,
            positive_samples=n_pos,
            unlabeled_samples=n_unlab,
            prevalence=round(prev, 6),
        )

    train_part = _build_partition("train", train_mask)
    val_part = _build_partition("validation", val_mask)
    test_part = _build_partition("test", test_mask)

    split = ChronologicalSplit(
        train=train_part,
        val=val_part,
        test=test_part,
    )
    split.validate_causality()

    logger.info(
        "ChronologicalSplit created:\n"
        "  Train: %s to %s (%d rows, %d pos, %.2f%%)\n"
        "  Val:   %s to %s (%d rows, %d pos, %.2f%%)\n"
        "  Test:  %s to %s (%d rows, %d pos, %.2f%%)",
        train_part.start_date,
        train_part.end_date,
        train_part.total_samples,
        train_part.positive_samples,
        train_part.prevalence * 100,
        val_part.start_date,
        val_part.end_date,
        val_part.total_samples,
        val_part.positive_samples,
        val_part.prevalence * 100,
        test_part.start_date,
        test_part.end_date,
        test_part.total_samples,
        test_part.positive_samples,
        test_part.prevalence * 100,
    )
    return split
