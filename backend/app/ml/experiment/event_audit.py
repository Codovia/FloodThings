"""
Event and Spatial Leakage Auditor (Phase 5.5).

Verifies:
1. Disaster event footprints and multi-district spans.
2. Cross-partition disaster event ID isolation between Train, Validation, and Test sets.
3. Guarantees zero cross-partition event contamination under chronological splitting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventLeakageAuditResult:
    """Findings from cross-partition disaster event audit."""

    total_unique_events: int
    train_unique_events: int
    val_unique_events: int
    test_unique_events: int
    train_val_overlap_count: int
    val_test_overlap_count: int
    train_test_overlap_count: int
    train_val_overlap_events: list[str]
    val_test_overlap_events: list[str]
    train_test_overlap_events: list[str]
    is_leakage_free: bool
    multi_district_events_count: int
    largest_event_id: str
    largest_event_district_span: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_event_leakage(df: pd.DataFrame) -> EventLeakageAuditResult:
    """
    Audit disaster event IDs across chronological train, validation, and test splits.
    """
    train_mask = df["target_date"] <= "2019-12-31"
    val_mask = (df["target_date"] >= "2020-01-01") & (df["target_date"] <= "2021-12-31")
    test_mask = (df["target_date"] >= "2022-01-01") & (df["target_date"] <= "2023-07-24")

    def _extract_events(sub_df: pd.DataFrame) -> set[str]:
        events = set()
        floods = sub_df.loc[sub_df["label_state"] == "FLOOD", "source_event_ids"].dropna()
        for item in floods:
            if isinstance(item, (list, np.ndarray)):
                for e in item:
                    events.add(str(e).strip())
            elif isinstance(item, str):
                for e in item.split(","):
                    e = e.strip()
                    if e:
                        events.add(e)
        return events

    train_events = _extract_events(df[train_mask])
    val_events = _extract_events(df[val_mask])
    test_events = _extract_events(df[test_mask])

    train_val_overlap = sorted(list(train_events.intersection(val_events)))
    val_test_overlap = sorted(list(val_events.intersection(test_events)))
    train_test_overlap = sorted(list(train_events.intersection(test_events)))

    all_events = train_events.union(val_events).union(test_events)

    # Multi-district event analysis across the entire dataset
    event_to_districts: dict[str, set[str]] = {}
    for _, row in df[df["label_state"] == "FLOOD"].iterrows():
        d_name = row["district_name"]
        raw_ids = row["source_event_ids"]
        if isinstance(raw_ids, (list, np.ndarray)):
            ids = [str(x).strip() for x in raw_ids]
        elif isinstance(raw_ids, str):
            ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
        else:
            ids = []
        for e in ids:
            event_to_districts.setdefault(e, set()).add(d_name)

    multi_dist_count = sum(1 for dset in event_to_districts.values() if len(dset) > 1)
    largest_event = max(event_to_districts.items(), key=lambda kv: len(kv[1])) if event_to_districts else ("", set())

    is_leakage_free = (
        len(train_val_overlap) == 0
        and len(val_test_overlap) == 0
        and len(train_test_overlap) == 0
    )

    logger.info(
        "Event Leakage Audit Result: %d total events (Train: %d, Val: %d, Test: %d). Overlaps: TV=%d, VT=%d, TT=%d. Leakage-free: %s",
        len(all_events),
        len(train_events),
        len(val_events),
        len(test_events),
        len(train_val_overlap),
        len(val_test_overlap),
        len(train_test_overlap),
        is_leakage_free,
    )

    return EventLeakageAuditResult(
        total_unique_events=len(all_events),
        train_unique_events=len(train_events),
        val_unique_events=len(val_events),
        test_unique_events=len(test_events),
        train_val_overlap_count=len(train_val_overlap),
        val_test_overlap_count=len(val_test_overlap),
        train_test_overlap_count=len(train_test_overlap),
        train_val_overlap_events=train_val_overlap,
        val_test_overlap_events=val_test_overlap,
        train_test_overlap_events=train_test_overlap,
        is_leakage_free=is_leakage_free,
        multi_district_events_count=multi_dist_count,
        largest_event_id=largest_event[0],
        largest_event_district_span=len(largest_event[1]),
    )
