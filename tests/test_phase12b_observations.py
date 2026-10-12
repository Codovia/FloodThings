"""Isolated consistency tests: synthetic fixtures are never scientific labels."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_satellite_observations as observations
import build_flood_observation_feasibility as feasibility
import inspect_groundsource_metadata as metadata


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Audit tests must not access network")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def observation(tmp_path):
    source = tmp_path / "fixture.txt"
    source.write_text("isolated synthetic classification fixture")
    return {"observation_id": "fixture-1", "spatial_unit_id": "fixture-unit", "geometry_reference": "fixture-grid",
            "source_reference": source.name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "event_group": "fixture-event", "source_group": "fixture-scene", "review_group": "fixture-review",
            "target": "ACQUISITION_TEMPORARY_INUNDATION", "acquisition_time": "2025-08-01T00:00:00Z",
            "unit_pixels": 100, "valid_pixels": 100, "temporary_water_pixels": 0,
            "permanent_water_pixels": 10, "dry_pixels": 90, "unknown_pixels": 0,
            "source_type": "OBSERVED", "product_role": "ACQUISITION_CLASSIFICATION",
            **{k: "isolated fixture review" for k in ("quality_review", "detection_limits_review", "permanent_water_review",
                "rights_review", "independent_reference_review", "protocol_reference", "scientific_adjudication")},
            "issue_time": "2025-07-31T00:00:00Z", "feature_available_at": "2025-07-30T23:30:00Z",
            "scheduled_acquisition_time": "2025-08-01T00:00:00Z",
            "feature_valid_end": "2025-08-02T00:00:00Z", "feature_run_time": "2025-07-30T18:00:00Z",
            "feature_product": "AS_ISSUED_VERIFIED", "feature_availability_reference": "fixture-archive-receipt",
            "target_schedule_available_at": "2025-07-30T00:00:00Z", "target_schedule_reference": "fixture-schedule"}


def review(row, root):
    receipt = root / "independent-fixture-review.json"
    receipt.write_text(json.dumps({**row, "decision": "APPROVED"}, sort_keys=True))
    row["review_receipt_reference"] = receipt.name
    row["review_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()


def window(row):
    row.update(target="WINDOW_FLOOD_OCCURRENCE", target_start="2025-08-01T00:00:00Z", target_end="2025-08-02T00:00:00Z")


def test_dry_acquisition_does_not_become_daily_negative(observation, tmp_path):
    review(observation, tmp_path)
    result = observations.evaluate(observation, tmp_path)
    assert result["candidate_label"] == "NON_FLOOD_OBSERVED_AT_ACQUISITION_ONLY"
    assert result["forecast_eligible"]  # future-valid, already issued forecasts allowed
    window(observation)
    review(observation, tmp_path)
    result = observations.evaluate(observation, tmp_path)
    assert result["candidate_label"] == "UNKNOWN"
    assert any("one dry acquisition" in b for b in result["blocking_evidence"])


def test_partial_dry_unknown_but_reviewed_partial_positive_existential(observation, tmp_path):
    observation.update(valid_pixels=95, dry_pixels=85, unknown_pixels=5)
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"
    observation.update(temporary_water_pixels=1, dry_pixels=84)
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "FLOOD_OBSERVED"


def test_full_interval_receipt_is_required_and_bound(observation, tmp_path):
    window(observation)
    coverage = {k: observation[k] for k in ("spatial_unit_id", "geometry_reference", "target_start", "target_end")}
    coverage.update(continuous_full_interval=True, review_reference="fixture-review", observation_process_reference="fixture-monitor")
    observation["continuous_coverage_receipt"] = coverage
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "NON_FLOOD_OBSERVED"
    coverage["spatial_unit_id"] = "different-unit"
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"


@pytest.mark.parametrize("mutation", [
    {"valid_pixels": True}, {"dry_pixels": -1}, {"valid_pixels": 99}, {"dry_pixels": 89},
    {"target": "FLOOD_SUSCEPTIBILITY"}, {"target": []}, {"source_sha256": "x"}, {"event_group": ""},
])
def test_invalid_structural_evidence_ineligible(observation, tmp_path, mutation):
    observation.update(mutation)
    review(observation, tmp_path)
    result = observations.evaluate(observation, tmp_path)
    assert result["problems"] and not result["observation_eligible"]


@pytest.mark.parametrize("mutation", [
    {"acquisition_time": None}, {"acquisition_time": "2025-08-01"}, {"product_role": "EVENT_MAXIMUM"},
    {"product_role": "MONTHLY_WATER"}, {"source_type": "MODELLED"}, {"quality_review": ""},
    {"rights_review": ""}, {"source_reference": "../outside"},
])
def test_inadequate_observations_unknown(observation, tmp_path, mutation):
    observation.update(mutation)
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"


def test_nonempty_review_names_are_insufficient_and_receipt_tampering_blocks(observation, tmp_path):
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"
    review(observation, tmp_path)
    observation["acquisition_time"] = "2025-08-02T00:00:00Z"
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"
    review(observation, tmp_path)
    (tmp_path / observation["source_reference"]).write_text("tampered fixture")
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"


def test_invalid_independent_receipt_object_is_unknown(observation, tmp_path):
    review(observation, tmp_path)
    receipt = tmp_path / observation["review_receipt_reference"]
    receipt.write_text("[]")
    observation["review_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert observations.evaluate(observation, tmp_path)["candidate_label"] == "UNKNOWN"


@pytest.mark.parametrize("mutation", [
    {"issue_time": "2025-08-01T00:00:00Z"}, {"feature_available_at": "2025-07-31T00:00:01Z"},
    {"feature_product": "REANALYSIS"}, {"feature_run_time": "2025-07-31T01:00:00Z"},
    {"feature_availability_reference": ""}, {"target_schedule_available_at": "2025-08-02T00:00:00Z"},
    {"feature_product": "ANTECEDENT_OBSERVATIONS_VERIFIED"},
    {"scheduled_acquisition_time": "2025-08-01T00:16:00Z"},
])
def test_leaky_predictors_and_outcome_selected_schedule_fail_forecast_gate(observation, tmp_path, mutation):
    observation.update(mutation)
    review(observation, tmp_path)
    result = observations.evaluate(observation, tmp_path)
    assert result["observation_eligible"] and not result["forecast_eligible"]


def test_antecedent_observations_available_at_issue_can_be_used(observation, tmp_path):
    observation.update(feature_product="ANTECEDENT_OBSERVATIONS_VERIFIED", feature_valid_end="2025-07-30T23:00:00Z")
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["forecast_eligible"]


@pytest.mark.parametrize("acquisition", ["2025-07-31T23:59:59Z", "2025-08-02T00:00:00Z"])
def test_half_open_window_rejects_outside_acquisition(observation, tmp_path, acquisition):
    window(observation)
    observation["acquisition_time"] = acquisition
    review(observation, tmp_path)
    assert not observations.evaluate(observation, tmp_path)["observation_eligible"]


def test_wrong_length_window_rejected(observation, tmp_path):
    window(observation)
    observation["target_end"] = "2025-08-02T00:00:01Z"
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["problems"]


def test_window_forecast_can_be_issued_at_window_start(observation, tmp_path):
    window(observation)
    observation.update(issue_time="2025-08-01T00:00:00Z", acquisition_time="2025-08-01T01:00:00Z",
                       temporary_water_pixels=1, dry_pixels=89)
    review(observation, tmp_path)
    assert observations.evaluate(observation, tmp_path)["forecast_eligible"]


def test_all_duplicate_aliases_ineligible(observation, tmp_path):
    review(observation, tmp_path)
    alias = copy.deepcopy(observation)
    alias.update(observation_id="fixture-alias", spatial_unit_id="renamed-same-geometry")
    result = observations.audit([observation, alias], tmp_path)
    assert result["observation_eligible"] == 0
    assert all(any("duplicate" in p for p in r["problems"]) for r in result["results"])


# Small independently specified Apache Compact/FileMetaData fixture: version1,
# root + optional UTF8 byte-array uuid, zero rows, empty row groups. No event data.
FOOTER = bytes.fromhex("1502192c4806736368656d61150200150c25021804757569642500001600190c00")


def header(start, end, size, status=206):
    return f"HTTP/2 {status}\nContent-Range: bytes {start}-{end}/{size}\n"


def metadata_fixture():
    size = 1024
    record = {"id": 18647054, "metadata": {"license": {"id": "cc-by-4.0"}},
              "files": [{"key": "groundsource_2026.parquet", "size": size, "checksum": "md5:fixture"}]}
    tail = struct.pack("<I", len(FOOTER)) + b"PAR1"
    return record, tail, FOOTER, header(size-8, size-1, size), header(size-8-len(FOOTER), size-9, size)


def test_footer_schema_and_partial_checksum_claim():
    result = metadata.inspect(*metadata_fixture())
    assert [r["name"] for r in result["schema"]] == ["schema", "uuid"]
    assert result["schema"][1]["physical_type"] == "BYTE_ARRAY"
    assert result["global_parquet_rows"] == 0 and result["event_rows_downloaded"] == 0
    assert result["karnataka_records"] is None and not result["full_file_checksum_verified"]


@pytest.mark.parametrize("body", [FOOTER[:-1], FOOTER+b"\x00", b"\x0d\x00", b"\x15"+b"\xff"*10])
def test_bad_compact_metadata_rejected(body):
    with pytest.raises(ValueError):
        metadata.decode_footer(body)


@pytest.mark.parametrize("headers,body", [(header(1, 2, 10, 200), b"ab"), (header(1, 2, 11), b"ab"), (header(1, 2, 10), b"a")])
def test_range_ignored_or_wrong_rejected(headers, body):
    with pytest.raises(ValueError):
        metadata.range_receipt(headers, body, 1, 2, 10)


def test_size_and_nesting_limits():
    with pytest.raises(ValueError):
        metadata.CompactReader(b"x"*(metadata.MAX_FOOTER_BYTES+1))
    with pytest.raises(ValueError):
        metadata.CompactReader(b"").value(12, depth=33)


def test_publisher_licence_and_trailer_changes_require_review():
    args = list(metadata_fixture())
    args[0]["metadata"]["license"]["id"] = "different-terms"
    with pytest.raises(ValueError):
        metadata.inspect(*args)
    args = list(metadata_fixture())
    args[1] = args[1][:-4] + b"NOPE"
    with pytest.raises(ValueError):
        metadata.inspect(*args)


def test_immutable_build_read_only_reproduction_and_tamper_rejection(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("fixture source")
    def collect(root):
        return {"version": feasibility.VERSION, "inputs": {"source.txt": feasibility.fingerprint(source)},
                "result": "UNKNOWN"}, [{"source": "fixture", "eligible_labels": 0}]
    monkeypatch.setattr(feasibility, "collect", collect)
    feasibility.build(tmp_path)
    directory = tmp_path / "data/working" / feasibility.VERSION
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    feasibility.validate(tmp_path)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    with pytest.raises(ValueError, match="exists"):
        feasibility.build(tmp_path)
    source.write_text("changed fixture")
    with pytest.raises(ValueError, match="reproduction"):
        feasibility.validate(tmp_path)
    source.write_text("fixture source")
    (directory / "observation_coverage.csv").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        feasibility.validate(tmp_path)


def test_cmr_catalogue_is_not_pixel_truth():
    entry = {"collection_concept_id": "C2949811996-POCLOUD", "time_start": "2025-08-01T00:00:00Z",
             "time_end": "2025-08-01T00:00:20Z", "boxes": ["12 74 14 76"], "id": "fixture",
             "producer_granule_id": "fixture-product", "updated": "2025-08-02T00:00:00Z"}
    result = feasibility.opera_metadata({"feed": {"entry": [entry]}}, "HTTP/2 200\ncmr-hits: 8\n")
    assert result["total_catalogue_matches"] == 8 and not result["complete_query_metadata_page"]
    assert result["rasters_retrieved"] == 0 and result["valid_observed_pixels"] is None
    entry["collection_concept_id"] = "other"
    with pytest.raises(ValueError, match="collection"):
        feasibility.opera_metadata({"feed": {"entry": [entry]}}, "HTTP/2 200\ncmr-hits: 1\n")
