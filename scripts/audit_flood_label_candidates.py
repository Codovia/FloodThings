#!/usr/bin/env python3
"""Offline candidate evidence audit. Passing is not scientific certification.

CSV dates are inclusive. Unknown is never zero. Evidence receipts are reviewed
local JSON records, independently supplied rather than inferred from CSV claims.
No network, database, source mutation, model fitting or application integration.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

REQUIRED = (
    "schema_version", "observation_id", "spatial_unit_id", "start_date", "end_date",
    "label", "evidence_source", "evidence_reference", "source_sha256",
    "original_record_id", "event_group", "source_group", "review_group",
    "coverage_status", "spatial_precision", "temporal_precision", "mechanism",
    "review_status", "scientific_review", "review_reference", "licence_status",
    "coverage_reference", "absence_method", "geometry_reference", "quality_flags",
)
LABELS = {"FLOOD_OBSERVED", "NON_FLOOD_OBSERVED", "UNKNOWN"}


def validate_record(row):
    errors = []
    for field in REQUIRED:
        if field not in row or not isinstance(row[field], str):
            errors.append(f"missing or malformed {field}")
    if errors:
        return errors
    for field in REQUIRED:
        if field not in {"absence_method", "coverage_reference", "review_reference", "quality_flags"} and not row[field].strip():
            errors.append(f"blank {field}")
    enums = {
        "schema_version": {"1"}, "label": LABELS,
        "coverage_status": {"FLOOD_OBSERVED", "FULL_UNIT_OBSERVED", "PARTIAL", "UNKNOWN"},
        "review_status": {"VERIFIED", "PENDING", "REJECTED"},
        "scientific_review": {"APPROVED", "PENDING", "REJECTED"},
        "spatial_precision": {"GRID_CELL", "LOCALITY", "DISTRICT", "REACH", "UNRESOLVED"},
        "temporal_precision": {"DAILY", "EVENT_WINDOW", "UNRESOLVED"},
        "mechanism": {"RIVERINE", "PLUVIAL_FLASH", "UNKNOWN"},
        "licence_status": {"INTERNAL_USE_VERIFIED", "UNRESOLVED", "PROHIBITED"},
    }
    for field, values in enums.items():
        if row[field] not in values:
            errors.append(f"invalid {field}")
    if not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]):
        errors.append("invalid source_sha256")
    try:
        if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[k]) for k in ("start_date", "end_date")):
            raise ValueError("non-ISO date")
        start, end = (dt.date.fromisoformat(row[k]) for k in ("start_date", "end_date"))
        if end < start:
            errors.append("end_date precedes start_date")
        if row["temporal_precision"] == "DAILY" and end != start:
            errors.append("DAILY must describe exactly one date")
    except ValueError:
        errors.append("dates must use ISO YYYY-MM-DD")
    if row["label"] == "NON_FLOOD_OBSERVED":
        if row["coverage_status"] != "FULL_UNIT_OBSERVED":
            errors.append("non-flood cannot be inferred from missing or partial coverage")
        if not row["absence_method"].strip() or not row["coverage_reference"].strip():
            errors.append("non-flood needs independently reviewed absence method and coverage receipt")
    if row["label"] == "FLOOD_OBSERVED" and row["coverage_status"] not in {"FLOOD_OBSERVED", "FULL_UNIT_OBSERVED"}:
        errors.append("flood-positive needs direct evidence coverage")
    if row["scientific_review"] == "APPROVED" and not row["review_reference"].strip():
        errors.append("scientific approval requires review_reference")
    return errors


def evidence_errors(row, receipt, source_root):
    """Validate reviewed claims against a same-unit/interval independent receipt."""
    if not receipt:
        return ["independent evidence receipt absent"]
    errors = []
    for field in ("spatial_unit_id", "start_date", "end_date", "label", "source_sha256",
                  "original_record_id", "event_group", "source_group", "review_group",
                  "geometry_reference", "coverage_status", "review_reference", "absence_method",
                  "coverage_reference", "mechanism", "temporal_precision", "quality_flags"):
        if receipt.get(field) != row[field]:
            errors.append(f"receipt mismatch: {field}")
    if receipt.get("observed_truth") is not True or receipt.get("reviewed") is not True:
        errors.append("receipt lacks independently reviewed observed truth")
    if not receipt.get("detection_limits") or receipt.get("licence_verified") is not True:
        errors.append("detection limits or internal-use licence unverified")
    if row["quality_flags"] and receipt.get("quality_flags_adjudicated") is not True:
        errors.append("quality limitations not independently adjudicated")
    if row["label"] == "NON_FLOOD_OBSERVED" and receipt.get("continuous_full_interval_coverage") is not True:
        errors.append("absence does not cover the entire unit and interval")
    if source_root is None:
        errors.append("source_root absent; original bytes not verified")
    else:
        path = (source_root / row["evidence_reference"]).resolve()
        if not path.is_relative_to(source_root.resolve()) or not path.is_file():
            errors.append("evidence reference must be a local file inside source_root")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row["source_sha256"]:
            errors.append("original source checksum mismatch")
    return errors


def audit(path: Path, receipts=None, source_root=None):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError("Duplicate CSV columns")
        missing = set(REQUIRED) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    counts = Counter(rows=len(rows), invalid_rows=0, eligible_rows=0, ineligible_rows=0)
    ids = Counter(r.get("observation_id") for r in rows)
    keys = Counter((r.get("evidence_source"), r.get("original_record_id"), r.get("spatial_unit_id"),
                    r.get("start_date"), r.get("end_date")) for r in rows)
    problems, decisions = [], []
    for number, row in enumerate(rows, 2):
        errors = validate_record(row)
        if None in row:
            errors.append("malformed CSV field count")
        if ids[row.get("observation_id")] > 1 or keys[(row.get("evidence_source"), row.get("original_record_id"),
                row.get("spatial_unit_id"), row.get("start_date"), row.get("end_date"))] > 1:
            errors.append("duplicate observation or source-unit-interval; all copies ineligible")
        counts[f"label_{row.get('label', 'BLANK')}"] += 1
        blockers = list(errors)
        if not errors:
            if row["label"] == "UNKNOWN":
                blockers.append("unknown observation")
            if row["review_status"] != "VERIFIED" or row["scientific_review"] != "APPROVED":
                blockers.append("independent scientific review incomplete")
            if row["spatial_precision"] == "UNRESOLVED" or row["temporal_precision"] != "DAILY":
                blockers.append("not resolved for daily occurrence target")
            if row["licence_status"] != "INTERNAL_USE_VERIFIED":
                blockers.append("internal-use rights unverified")
            if row["mechanism"] == "UNKNOWN":
                blockers.append("mechanism unverified for separate target tracks")
            blockers += evidence_errors(row, (receipts or {}).get(row["observation_id"]), source_root)
        counts["invalid_rows"] += bool(errors)
        eligible = not blockers
        counts["eligible_rows" if eligible else "ineligible_rows"] += 1
        decisions.append({"observation_id": row.get("observation_id"), "eligible": eligible, "blockers": blockers})
        problems.extend({"row": number, "problem": error} for error in errors)
    return {"schema_version": 1, "counts": dict(sorted(counts.items())), "problems": problems,
            "event_groups": len({r.get("event_group") for r in rows}), "decisions": decisions,
            "scientific_status": "NOT_CERTIFIED_FOR_TRAINING"}


def training_readiness(rows, audit_result, plan=None, features=None):
    """Fail closed. A GO permits only a separate non-operational research pilot."""
    blockers = []
    eligible_ids = {d["observation_id"] for d in audit_result["decisions"] if d["eligible"]}
    eligible = [r for r in rows if r["observation_id"] in eligible_ids]
    if audit_result["counts"].get("invalid_rows"):
        blockers.append("invalid candidate records")
    for label in ("FLOOD_OBSERVED", "NON_FLOOD_OBSERVED"):
        if not any(r["label"] == label for r in eligible):
            blockers.append(f"no scientifically eligible {label}")
    plan = plan or {}
    if not (plan.get("review_reference") and plan.get("target") == "FLOOD_OCCURRENCE"
            and plan.get("horizon_hours") == 24 and plan.get("mechanism") in {"RIVERINE", "PLUVIAL_FLASH"}
            and plan.get("spatial_unit_definition") and plan.get("quality_protocol_reference")):
        blockers.append("reviewed fixed 24-hour flood-occurrence target/protocol absent")
    features = features or []
    feature_columns = None
    by_id = {}
    for feature in features:
        ident = feature.get("observation_id")
        if ident in by_id:
            blockers.append("duplicate feature join")
        by_id[ident] = feature
    if not eligible or set(by_id) != eligible_ids:
        blockers.append("complete one-to-one issue-time feature table absent")
    groups = {key: {} for key in ("event_group", "source_group", "review_group", "spatial_unit_id")}
    partitions = {key: [] for key in ("TRAIN", "TEST")}
    for row in eligible:
        feature = by_id.get(row["observation_id"], {})
        split = feature.get("split")
        if split not in partitions:
            blockers.append("independent train/test assignment absent")
            continue
        partitions[split].append((row, feature))
        if row["mechanism"] != plan.get("mechanism"):
            blockers.append("label mechanism differs from frozen target")
        values = feature.get("values")
        if not isinstance(values, dict) or not values or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (values or {}).values()):
            blockers.append("missing/nonfinite predictor values; no implicit imputation")
        elif feature_columns is None:
            feature_columns = set(values)
        elif set(values) != feature_columns:
            blockers.append("inconsistent predictor columns")
        for key, assignments in groups.items():
            if row[key] in assignments and assignments[row[key]] != split:
                blockers.append(f"holdout leakage: {key}")
            assignments[row[key]] = split
        try:
            times = {key: dt.datetime.fromisoformat(feature[key]) for key in
                     ("issue_time", "available_at", "feature_valid_end", "valid_from", "valid_to")}
            if any(v.tzinfo is None for v in times.values()):
                raise ValueError("timezone required")
            if not (times["available_at"] <= times["issue_time"] <= times["valid_from"]
                    and times["feature_valid_end"] <= times["issue_time"]
                    and times["valid_to"] - times["valid_from"] == dt.timedelta(hours=24)
                    and times["valid_from"].date().isoformat() == row["start_date"]
                    and times["valid_to"] == times["valid_from"] + dt.timedelta(days=1)
                    and times["valid_from"].time() == dt.time(0)):
                blockers.append("issue-time leakage or target interval mismatch")
        except (KeyError, ValueError, TypeError):
            blockers.append("missing/invalid timezone-aware feature times")
        if not (re.fullmatch(r"[0-9a-f]{64}", str(feature.get("source_sha256", ""))) and feature.get("version") and feature.get("units")
                and feature.get("join_reference") and feature.get("availability_evidence")
                and feature.get("missingness_reviewed") is True and feature.get("as_issued_verified") is True):
            blockers.append("feature provenance/availability/parity evidence incomplete")
    for split, values in partitions.items():
        if {r["label"] for r, _ in values} != {"FLOOD_OBSERVED", "NON_FLOOD_OBSERVED"}:
            blockers.append(f"{split} lacks independent positive and verified negative observations")
    try:
        if max(dt.date.fromisoformat(r["end_date"]) for r, _ in partitions["TRAIN"]) >= min(
                dt.date.fromisoformat(r["start_date"]) for r, _ in partitions["TEST"]):
            blockers.append("chronological holdout overlap")
    except ValueError:
        pass
    return {"decision": "NO-GO" if blockers else "GO_NON_OPERATIONAL_PILOT_ONLY",
            "blocking_evidence": sorted(set(blockers)), "eligible_rows": len(eligible),
            "operational_forecast_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--features", type=Path)
    args = parser.parse_args()
    try:
        read = lambda p: json.loads(p.read_text()) if p else None
        result = audit(args.csv_path, read(args.receipts), args.source_root)
        with args.csv_path.open(newline="", encoding="utf-8-sig") as handle:
            result["training_readiness"] = training_readiness(list(csv.DictReader(handle)), result, read(args.plan), read(args.features))
        print(json.dumps(result, indent=2))
        return 1 if result["counts"]["invalid_rows"] else 0
    except (ValueError, OSError, csv.Error, TypeError, KeyError) as error:
        parser.exit(2, f"Input audit failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
