#!/usr/bin/env python3
"""Audit observation semantics without manufacturing full-window dry labels.

This contract is separate from the frozen Phase12A candidate version. A nominated
label still requires independent scientific adjudication. No network/model/API.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

TARGETS = {"ACQUISITION_TEMPORARY_INUNDATION", "WINDOW_FLOOD_OCCURRENCE"}
PIXELS = ("unit_pixels", "valid_pixels", "temporary_water_pixels", "permanent_water_pixels", "dry_pixels", "unknown_pixels")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp absent")
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(dt.timezone.utc)


def evaluate(row, root=None):
    problems, blockers = [], []
    target = row.get("target")
    if not isinstance(target, str) or target not in TARGETS:
        problems.append("unsupported target; susceptibility/discharge is not inundation")
    for field in ("observation_id", "spatial_unit_id", "geometry_reference", "source_reference",
                  "event_group", "source_group", "review_group"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            problems.append(f"missing {field}")
    digest = row.get("source_sha256", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        problems.append("invalid source_sha256")
    for field in PIXELS:
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            problems.append(f"invalid {field}")
    if not any(p.startswith("invalid ") and p[8:] in PIXELS for p in problems):
        if row["unit_pixels"] <= 0 or row["valid_pixels"] + row["unknown_pixels"] != row["unit_pixels"]:
            problems.append("invalid unit/valid/unknown pixel partition")
        if row["temporary_water_pixels"] + row["permanent_water_pixels"] + row["dry_pixels"] != row["valid_pixels"]:
            problems.append("invalid temporary/permanent/dry pixel partition")
    acquisition = None
    try:
        acquisition = timestamp(row.get("acquisition_time"))
    except ValueError:
        blockers.append("exact acquisition time unknown")
    start = end = None
    if target == "WINDOW_FLOOD_OCCURRENCE":
        try:
            start, end = timestamp(row.get("target_start")), timestamp(row.get("target_end"))
            if end - start != dt.timedelta(hours=24):
                problems.append("occurrence target must be exactly 24 hours, half-open")
            if acquisition is not None and not start <= acquisition < end:
                blockers.append("acquisition outside target window")
        except ValueError:
            problems.append("missing/invalid target interval")
    if row.get("source_type") != "OBSERVED" or row.get("product_role") != "ACQUISITION_CLASSIFICATION":
        blockers.append("source is not acquisition-time categorical observed evidence")
    for field in ("quality_review", "detection_limits_review", "permanent_water_review", "rights_review",
                  "independent_reference_review", "protocol_reference", "scientific_adjudication"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            blockers.append(f"missing independent {field}")
    if root is None:
        blockers.append("original source bytes not verified")
    elif isinstance(row.get("source_reference"), str):
        source = (root / row["source_reference"]).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            blockers.append("source path absent/outside supplied root")
        elif hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            blockers.append("original source checksum mismatch")
    # A set of nonempty review names is not independent evidence. Verify the
    # separately supplied receipt and its exact source/unit/time/count bindings.
    if root is not None:
        try:
            receipt = (root / row["review_receipt_reference"]).resolve()
            source = (root / row["source_reference"]).resolve()
            if not receipt.is_relative_to(root.resolve()) or receipt == source:
                raise ValueError("receipt outside root or identical to source")
            body = receipt.read_bytes()
            if hashlib.sha256(body).hexdigest() != row.get("review_receipt_sha256"):
                raise ValueError("receipt checksum mismatch")
            review = json.loads(body)
            if not isinstance(review, dict):
                raise ValueError("receipt must be a JSON object")
            bound = ("spatial_unit_id", "geometry_reference", "source_sha256", "acquisition_time", "target",
                     *PIXELS, "quality_review", "detection_limits_review", "permanent_water_review", "rights_review",
                     "independent_reference_review", "protocol_reference", "scientific_adjudication")
            if target == "WINDOW_FLOOD_OCCURRENCE":
                bound += ("target_start", "target_end", "continuous_coverage_receipt")
            if review.get("decision") != "APPROVED" or any(review.get(k) != row.get(k) for k in bound):
                raise ValueError("receipt not approved or source/unit/time/interpretation differs")
        except (KeyError, TypeError, ValueError, OSError) as error:
            blockers.append(f"independent receipt unverified: {error}")
    label = "UNKNOWN"
    if not problems and not blockers:
        if row["temporary_water_pixels"] > 0:
            label = "FLOOD_OBSERVED"
        elif row["unknown_pixels"]:
            blockers.append("partial unit coverage cannot establish absence")
        elif target == "ACQUISITION_TEMPORARY_INUNDATION":
            label = "NON_FLOOD_OBSERVED_AT_ACQUISITION_ONLY"
        else:
            coverage = row.get("continuous_coverage_receipt", {})
            if not isinstance(coverage, dict) or not (coverage.get("spatial_unit_id") == row["spatial_unit_id"]
                    and coverage.get("geometry_reference") == row["geometry_reference"]
                    and coverage.get("target_start") == row["target_start"]
                    and coverage.get("target_end") == row["target_end"]
                    and isinstance(coverage.get("review_reference"), str) and coverage["review_reference"].strip()
                    and isinstance(coverage.get("observation_process_reference"), str) and coverage["observation_process_reference"].strip()
                    and coverage.get("continuous_full_interval") is True):
                blockers.append("one dry acquisition is not 24-hour absence; independently reviewed continuous coverage required")
            else:
                label = "NON_FLOOD_OBSERVED"
    forecast_blockers = []
    try:
        issue = timestamp(row.get("issue_time"))
        available = timestamp(row.get("feature_available_at"))
        if available > issue:
            forecast_blockers.append("predictor not available by issue time")
        if row.get("feature_product") == "ANTECEDENT_OBSERVATIONS_VERIFIED":
            if timestamp(row.get("feature_valid_end")) > issue:
                forecast_blockers.append("antecedent observation extends past issue time")
        elif row.get("feature_product") == "AS_ISSUED_VERIFIED":
            if timestamp(row.get("feature_run_time")) > issue:
                forecast_blockers.append("forecast run initialized after issue time")
            # A genuine issued forecast can describe future valid times. Its
            # initialization/publication/availability, not valid time, gates use.
            timestamp(row.get("feature_valid_end"))
        else:
            forecast_blockers.append("reanalysis or unverified forcing is not an archived issued forecast")
        forecast_start = start if target == "WINDOW_FLOOD_OCCURRENCE" else acquisition
        if forecast_start is None or (issue > forecast_start if target == "WINDOW_FLOOD_OCCURRENCE" else issue >= forecast_start):
            forecast_blockers.append("issue time must precede acquisition/not follow window start")
        if target == "ACQUISITION_TEMPORARY_INUNDATION":
            scheduled = timestamp(row.get("scheduled_acquisition_time"))
            if scheduled - issue != dt.timedelta(hours=24):
                forecast_blockers.append("pilot issue time must be 24 hours before scheduled acquisition")
            if acquisition is None or abs(acquisition - scheduled) > dt.timedelta(minutes=15):
                forecast_blockers.append("acquisition outside predeclared schedule tolerance")
    except ValueError:
        forecast_blockers.append("verified issue-time feature timestamps absent")
    if not isinstance(row.get("feature_availability_reference"), str) or not row["feature_availability_reference"].strip():
        forecast_blockers.append("feature availability receipt absent")
    try:
        if timestamp(row.get("target_schedule_available_at")) > timestamp(row.get("issue_time")):
            forecast_blockers.append("target sampling schedule unavailable at issue time")
        if not isinstance(row.get("target_schedule_reference"), str) or not row["target_schedule_reference"].strip():
            forecast_blockers.append("target sampling schedule receipt absent")
    except ValueError:
        forecast_blockers.append("target schedule availability unknown")
    return {"observation_id": row.get("observation_id"), "target": target,
            "candidate_label": label, "observation_eligible": label != "UNKNOWN",
            "forecast_eligible": label != "UNKNOWN" and not forecast_blockers,
            "problems": problems, "blocking_evidence": blockers, "forecast_blockers": forecast_blockers,
            "scientific_status": "CONSISTENCY_AUDIT_NOT_AUTOMATED_CERTIFICATION"}


def audit(records, root=None):
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("Observation input must be a JSON array of objects")
    def key(row, fields):
        return tuple(json.dumps(row.get(f), sort_keys=True, allow_nan=False) for f in fields)
    id_fields = ("observation_id",)
    source_fields = ("source_sha256", "geometry_reference", "acquisition_time", "target", "target_start", "target_end")
    counts = Counter(key(r, id_fields) for r in records)
    source_keys = Counter(key(r, source_fields) for r in records)
    results = []
    for row in records:
        result = evaluate(row, root)
        if counts[key(row, id_fields)] > 1 or source_keys[key(row, source_fields)] > 1:
            result["problems"].append("duplicate observation/source-unit-time; all copies ineligible")
            result.update(candidate_label="UNKNOWN", observation_eligible=False, forecast_eligible=False)
        results.append(result)
    return {"records": len(results), "label_counts": dict(Counter(r["candidate_label"] for r in results)),
            "observation_eligible": sum(r["observation_eligible"] for r in results),
            "forecast_eligible": sum(r["forecast_eligible"] for r in results), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        result = audit(json.loads(args.observations.read_text()), args.source_root)
        print(json.dumps(result, indent=2, allow_nan=False))
        raise SystemExit(1 if any(r["problems"] for r in result["results"]) else 0)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f"Observation audit failed: {error}\n")
