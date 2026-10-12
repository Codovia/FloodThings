"""Synthetic evidence fixtures only; no research records or network writes."""
import csv
import hashlib
import json
from pathlib import Path
import socket
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_flood_label_candidates as labels
import build_flood_outcome_foundation as foundation


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network/database access permitted")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def record(**changes):
    row = {k: "fixture" for k in labels.REQUIRED}
    row.update(schema_version="1", observation_id="observation-1", spatial_unit_id="cell-1",
               start_date="2020-08-01", end_date="2020-08-01", label="FLOOD_OBSERVED",
               evidence_reference="source.json", source_sha256=hashlib.sha256(b"fixture").hexdigest(),
               coverage_status="FLOOD_OBSERVED", spatial_precision="GRID_CELL", temporal_precision="DAILY",
               mechanism="PLUVIAL_FLASH", review_status="VERIFIED", scientific_review="APPROVED",
               licence_status="INTERNAL_USE_VERIFIED", absence_method="", quality_flags="")
    row.update(changes)
    return row


def receipt(row, **changes):
    value = dict(row, observed_truth=True, reviewed=True, detection_limits="fixture reviewed limits",
                 licence_verified=True, continuous_full_interval_coverage=True)
    value.update(changes)
    return value


def run_audit(tmp_path, records, receipts=None):
    (tmp_path / "source.json").write_bytes(b"fixture")
    path = tmp_path / "candidates.csv"
    foundation.write_csv(path, records, labels.REQUIRED)
    return labels.audit(path, receipts, tmp_path)


def test_review_is_separate_from_schema(tmp_path):
    row = record()
    result = run_audit(tmp_path, [row])
    assert result["counts"]["invalid_rows"] == 0
    assert result["counts"]["eligible_rows"] == 0
    assert result["scientific_status"] == "NOT_CERTIFIED_FOR_TRAINING"
    assert run_audit(tmp_path, [row], {row["observation_id"]: receipt(row)})["counts"]["eligible_rows"] == 1


@pytest.mark.parametrize("changes", [
    {"start_date": ""}, {"start_date": "20200801"}, {"end_date": "bad"}, {"end_date": "2019-01-01"},
    {"end_date": "2020-08-02"}, {"schema_version": "2"}, {"source_sha256": "bad"},
    {"label": "0"}, {"label": ""}, {"label": "HEAVY_RAIN"},
    {"original_record_id": ""}, {"event_group": ""}, {"source_group": ""}, {"review_group": ""},
    {"geometry_reference": ""}, {"review_reference": ""}, {"evidence_reference": ""},
    {"label": "NON_FLOOD_OBSERVED", "coverage_status": "UNKNOWN"},
    {"label": "NON_FLOOD_OBSERVED", "coverage_status": "PARTIAL"},
    {"label": "NON_FLOOD_OBSERVED", "coverage_status": "FULL_UNIT_OBSERVED", "absence_method": ""},
    {"coverage_status": "PARTIAL"},
])
def test_schema_rejects_unsupported_claims(tmp_path, changes):
    assert run_audit(tmp_path, [record(**changes)])["counts"]["invalid_rows"] == 1


@pytest.mark.parametrize("changes", [
    {"scientific_review": "PENDING"}, {"review_status": "REJECTED"}, {"licence_status": "UNRESOLVED"},
    {"mechanism": "UNKNOWN"}, {"temporal_precision": "EVENT_WINDOW"}, {"spatial_precision": "UNRESOLVED"},
    {"label": "UNKNOWN", "coverage_status": "UNKNOWN"},
])
def test_valid_ineligible_evidence(tmp_path, changes):
    row = record(**changes)
    result = run_audit(tmp_path, [row], {row["observation_id"]: receipt(row)})
    assert result["counts"]["invalid_rows"] == 0
    assert result["counts"]["eligible_rows"] == 0


@pytest.mark.parametrize("changes", [
    {"spatial_unit_id": "another-cell"}, {"end_date": "2020-08-02"},
    {"source_sha256": "a" * 64}, {"reviewed": False}, {"observed_truth": False},
    {"detection_limits": ""}, {"licence_verified": False}, {"original_record_id": "other"},
])
def test_receipt_must_match_independent_evidence(tmp_path, changes):
    row = record()
    assert run_audit(tmp_path, [row], {row["observation_id"]: receipt(row, **changes)})["counts"]["eligible_rows"] == 0


def test_full_coverage_claim_is_not_absence_proof(tmp_path):
    row = record(label="NON_FLOOD_OBSERVED", coverage_status="FULL_UNIT_OBSERVED", absence_method="reviewed continuous sensor coverage")
    assert run_audit(tmp_path, [row])["counts"]["eligible_rows"] == 0
    assert run_audit(tmp_path, [row], {row["observation_id"]: receipt(row, continuous_full_interval_coverage=False)})["counts"]["eligible_rows"] == 0


def test_all_duplicates_ineligible(tmp_path):
    row = record()
    result = run_audit(tmp_path, [row, row], {row["observation_id"]: receipt(row)})
    assert result["counts"]["invalid_rows"] == 2
    assert result["counts"]["eligible_rows"] == 0


def test_duplicate_source_alias_is_not_new_observation(tmp_path):
    assert run_audit(tmp_path, [record(), record(observation_id="renamed")])["counts"]["invalid_rows"] == 2


def test_source_corruption_and_path_escape(tmp_path):
    row = record(source_sha256="a" * 64)
    assert run_audit(tmp_path, [row], {row["observation_id"]: receipt(row)})["counts"]["eligible_rows"] == 0
    row = record(evidence_reference="../outside.json")
    assert run_audit(tmp_path, [row], {row["observation_id"]: receipt(row)})["counts"]["eligible_rows"] == 0


def ready_fixture(tmp_path):
    records, features = [], []
    for number, (split, label) in enumerate([("TRAIN", "FLOOD_OBSERVED"), ("TRAIN", "NON_FLOOD_OBSERVED"),
                                           ("TEST", "FLOOD_OBSERVED"), ("TEST", "NON_FLOOD_OBSERVED")]):
        date = f"202{0 if split == 'TRAIN' else 1}-08-01"
        row = record(observation_id=str(number), original_record_id=str(number), spatial_unit_id=f"cell-{number}",
                     event_group=f"event-{number}", source_group=f"source-{number}", review_group=f"review-{number}",
                     start_date=date, end_date=date, label=label,
                     coverage_status="FULL_UNIT_OBSERVED", absence_method="reviewed sensor" if label == "NON_FLOOD_OBSERVED" else "")
        records.append(row)
        features.append(dict(observation_id=str(number), split=split, issue_time=date+"T00:00:00+00:00",
                             available_at=date+"T00:00:00+00:00", feature_valid_end=date+"T00:00:00+00:00",
                             valid_from=date+"T00:00:00+00:00", valid_to=date[:8]+"02T00:00:00+00:00",
                             source_sha256="a"*64, version="fixture", units="mm", values={"past_rain_mm": 12.0}, join_reference="fixture",
                             availability_evidence="fixture", missingness_reviewed=True, as_issued_verified=True))
    result = run_audit(tmp_path, records, {r["observation_id"]: receipt(r) for r in records})
    plan = dict(review_reference="fixture", target="FLOOD_OCCURRENCE", horizon_hours=24,
                mechanism="PLUVIAL_FLASH", spatial_unit_definition="fixture cells", quality_protocol_reference="fixture")
    return records, result, plan, features


def test_only_independent_complete_pilot_can_pass(tmp_path):
    records, result, plan, features = ready_fixture(tmp_path)
    decision = labels.training_readiness(records, result, plan, features)
    assert decision["decision"] == "GO_NON_OPERATIONAL_PILOT_ONLY"
    assert decision["operational_forecast_authorized"] is False


@pytest.mark.parametrize("field", ["event_group", "source_group", "review_group", "spatial_unit_id"])
def test_related_holdout_groups_rejected(tmp_path, field):
    records, result, plan, features = ready_fixture(tmp_path)
    records[2][field] = records[0][field]
    assert f"holdout leakage: {field}" in labels.training_readiness(records, result, plan, features)["blocking_evidence"]


@pytest.mark.parametrize("change", [
    {"available_at": "2022-08-01T00:00:00+00:00"},
    {"feature_valid_end": "2022-08-01T00:00:00+00:00"},
    {"issue_time": "2020-08-01T00:00:00"}, {"as_issued_verified": False},
    {"valid_to": "2020-08-03T00:00:00+00:00"}, {"split": "UNKNOWN"},
    {"values": {}}, {"values": {"rain": float("nan")}}, {"values": {"rain": True}},
])
def test_feature_leakage_missingness_and_parity(tmp_path, change):
    records, result, plan, features = ready_fixture(tmp_path)
    features[0].update(change)
    assert labels.training_readiness(records, result, plan, features)["decision"] == "NO-GO"


def test_duplicate_feature_join_rejected(tmp_path):
    records, result, plan, features = ready_fixture(tmp_path)
    assert "duplicate feature join" in labels.training_readiness(records, result, plan, features+[features[0]])["blocking_evidence"]


def test_missing_contract_and_test_negatives_rejected(tmp_path):
    records, result, plan, features = ready_fixture(tmp_path)
    assert labels.training_readiness(records, result)["decision"] == "NO-GO"
    features[3]["split"] = "TRAIN"
    assert labels.training_readiness(records, result, plan, features)["decision"] == "NO-GO"


def test_checksum_verification_is_read_only(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text("[]")
    expected = foundation.fingerprint(path)
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {path.name: expected}}))
    before = path.stat().st_mtime_ns
    assert foundation.checked_json(tmp_path, path.name) == []
    assert path.stat().st_mtime_ns == before
    path.write_text("[1]")
    with pytest.raises(ValueError, match="checksum"):
        foundation.checked_json(tmp_path, path.name)


def test_existing_version_never_overwritten(tmp_path):
    output = tmp_path / "data/working" / foundation.VERSION
    output.mkdir(parents=True)
    with pytest.raises(ValueError, match="never overwrite"):
        foundation.build(tmp_path)


def test_build_validate_reproduces_and_rejects_tampering(tmp_path, monkeypatch):
    report = {"version": foundation.VERSION, "scopes": [{"gfd_id": 1}]}
    candidates = [record(scientific_review="PENDING")]
    matrix = [{"district": "Fixture", "eligible": 0, "verified_negatives": 0}]
    ifi_matrix = [{"source_district_token": "Fixture", "reported_records": 1}]
    monkeypatch.setattr(foundation, "collect", lambda root: (dict(report), candidates, matrix, ifi_matrix))
    (tmp_path / "data/working").mkdir(parents=True)
    generated = foundation.build(tmp_path)
    assert generated["training_readiness"]["decision"] == "NO-GO"
    output = tmp_path / "data/working" / foundation.VERSION
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    assert foundation.validate(tmp_path) == generated
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    (output / "candidates.csv").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        foundation.validate(tmp_path)


def test_quality_flags_need_review(tmp_path):
    row = record(quality_flags="uncertain_geometry")
    result = run_audit(tmp_path, [row], {row["observation_id"]: receipt(row)})
    assert result["counts"]["eligible_rows"] == 0


def test_chronological_overlap_rejected(tmp_path):
    records, result, plan, features = ready_fixture(tmp_path)
    for row in records[2:]:
        row["start_date"] = row["end_date"] = "2020-08-01"
    assert "chronological holdout overlap" in labels.training_readiness(records, result, plan, features)["blocking_evidence"]


def test_missing_headers_rejected(tmp_path):
    path = tmp_path / "records.csv"
    path.write_text("label\nUNKNOWN\n")
    with pytest.raises(ValueError, match="Missing required"):
        labels.audit(path)


def test_duplicate_headers_rejected(tmp_path):
    path = tmp_path / "records.csv"
    path.write_text("label,label\nUNKNOWN,UNKNOWN\n")
    with pytest.raises(ValueError, match="Duplicate CSV"):
        labels.audit(path)
