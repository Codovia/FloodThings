"""Isolated discovery/evidence-contract tests; no network, original-data writes or ML."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import pytest
import shapely
from shapely.geometry import mapping
from shapely.ops import transform
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_verified_flood_event_pilot as pilot


def record(ordinal, x=0, width=1000, start="2020-01-01", end="2020-01-01", sole=True):
    geometry = shapely.box(x, 0, x+width, 1000)
    return {"ordinal": ordinal, "geometry": geometry, "start": dt.date.fromisoformat(start), "end": dt.date.fromisoformat(end),
            "payload": {"source_uuid": str(ordinal), "single_district_screening_usable": sole,
                        "definite_district_id": "source-district" if sole else None,
                        "projected_polygon_area_km2": geometry.area/1e6,
                        "reported_interval_days_inclusive_assumption": (dt.date.fromisoformat(end)-dt.date.fromisoformat(start)).days+1}}


def members(result):
    return [[result[0][i]["ordinal"] for i in group] for group in result[1]]


def test_complete_link_breaks_spatial_chain_and_retains_ambiguity():
    # A/B and B/C satisfy the pair rule; A/C do not. A chain is not one event.
    result = pilot.cluster([record(1, 0), record(2, 450), record(3, 900)])
    assert members(result) == [[1, 2], [3]]
    assert len(result[3]) == 3  # all discovery associations retained
    assert result[2][1] != result[2][2]


def test_broad_polygon_cannot_bridge_local_events():
    result = pilot.cluster([record(1, 0), record(2, 0, width=20000), record(3, 19000)])
    assert members(result) == [[1], [2], [3]]
    assert len(result[3]) == 2


def test_multiple_complete_link_choices_remain_new_ambiguous_group():
    result = pilot.cluster([record(1, 0), record(2, 900), record(3, 450)])
    assert members(result) == [[1], [2], [3]]
    assert result[4] == {2: [0, 1]}


def test_deterministic_order_and_every_original_retained():
    records = [record(1), record(2, 100), record(3, 2000)]
    assert members(pilot.cluster(records)) == members(pilot.cluster(list(reversed(records))))
    result = pilot.cluster(records)
    assert sorted(i for group in result[1] for i in group) == [0, 1, 2]
    assert [r["geometry"].wkb for r in records] == [r["geometry"].wkb for r in result[0]]


@pytest.mark.parametrize("other", [record(2, 1000), record(2, start="2020-01-03", end="2020-01-03"),
                                       record(2, sole=False), record(2, end="2020-01-05")])
def test_touching_dates_admin_or_long_intervals_do_not_merge(other):
    assert members(pilot.cluster([record(1), other])) == [[1], [2]]


def test_temporal_chain_does_not_expand_episode_transitively():
    result = pilot.cluster([record(1), record(2, start="2020-01-02", end="2020-01-02"),
                            record(3, start="2020-01-03", end="2020-01-03")])
    assert members(result) == [[1, 2], [3]]


def test_comparison_cap_fails_instead_of_publishing_partial_count(monkeypatch):
    monkeypatch.setitem(pilot.RULES, "comparison_cap", 0)
    with pytest.raises(ValueError, match="budget exceeded"):
        pilot.cluster([record(1), record(2)])


def save(root, name, value):
    path = root / name
    path.write_text(json.dumps(value, sort_keys=True) if not isinstance(value, str) else value)
    return name, hashlib.sha256(path.read_bytes()).hexdigest()


def sign_observation(root, row):
    body = {k: v for k, v in row.items() if k not in ("receipt_reference", "receipt_sha256")}
    row["receipt_reference"], row["receipt_sha256"] = save(root, "observation-review.json", {
        "decision": "APPROVED", "independent_reviewer": "ISOLATED_TEST_FIXTURE", "observation": body})


@pytest.fixture
def approved_observation(tmp_path):
    # Entirely synthetic contract fixture in tmp_path, never project labels.
    protocol = json.loads((pilot.ROOT / pilot.PROTOCOL).read_text())
    protocol.update(review_status="APPROVED", training_authorized=True)
    unit = shapely.box(500000, 1500000, 500250, 1500250)
    domain = transform(Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform,
                       shapely.box(499000, 1499000, 501000, 1501000))
    reference, digest = save(tmp_path, "domain.json", {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(domain)}]})
    protocol["geographic_unit"].update(initial_domain_reference=reference, initial_domain_sha256=digest)
    body = dict(protocol)
    protocol["approval_reference"], protocol["approval_sha256"] = save(tmp_path, "protocol-review.json", {
        "decision": "APPROVED", "independent_reviewer": "ISOLATED_TEST_FIXTURE", "protocol": body})
    row = {"protocol_id": protocol["protocol_id"], "source_role": "OBSERVED_CLASSIFICATION", "unit_crs": "EPSG:32643",
           "issue_time": "2020-01-01T00:00:00+00:00", "target_start": "2020-01-01T00:00:00+00:00", "target_end": "2020-01-02T00:00:00+00:00",
           "acquisition_time": "2020-01-01T12:00:00+00:00", "outcome": "POSITIVE",
           "quality_approved": True, "permanence_approved": True, "detection_limits_approved": True,
           "rights_approved": True, "event_identity_approved": True}
    for prefix, name, content in [("source", "source.dat", "original-classification"), ("independent_reference", "reference.dat", "independent-field-evidence")]:
        reference, digest = save(tmp_path, name, content)
        if prefix == "source":
            row.update(source_reference=reference, source_sha256=digest)
        else:
            row.update(independent_reference=reference, independent_reference_sha256=digest)
    row["unit_reference"], row["unit_sha256"] = save(tmp_path, "unit.json", mapping(unit))
    row["patch_reference"], row["patch_sha256"] = save(tmp_path, "patch.json", mapping(shapely.box(500000, 1500000, 500050, 1500050)))
    sign_observation(tmp_path, row)
    return row, protocol, tmp_path


def test_approved_fixture_observation_contract(approved_observation):
    row, protocol, root = approved_observation
    assert pilot.evaluate_window_observation(row, root, protocol)["outcome"] == "POSITIVE"


def test_proposed_target_cannot_be_self_approved_by_water_pixels(approved_observation):
    row, protocol, root = approved_observation
    protocol["review_status"] = "PROPOSED_REQUIRES_INDEPENDENT_SCIENTIFIC_REVIEW"
    result = pilot.evaluate_window_observation(row, root, protocol)
    assert result["outcome"] == "UNKNOWN"
    assert "target protocol" in result["blockers"][0]


@pytest.mark.parametrize("field,value", [("acquisition_time", "2020-01-02T00:00:00+00:00"),
                                         ("acquisition_time", "2020-01-01T12:00:00"),
                                         ("target_end", "2020-01-03T00:00:00+00:00"),
                                         ("unit_crs", "EPSG:4326"), ("quality_approved", False),
                                         ("source_role", "CONTINUOUS_BACKSCATTER")])
def test_time_unit_quality_source_contracts(approved_observation, field, value):
    row, protocol, root = approved_observation
    row[field] = value
    sign_observation(root, row)
    assert pilot.evaluate_window_observation(row, root, protocol)["outcome"] == "UNKNOWN"


def test_changed_evidence_cannot_reuse_approval(approved_observation):
    row, protocol, root = approved_observation
    row["outcome"] = "NEGATIVE"
    assert "bound" in pilot.evaluate_window_observation(row, root, protocol)["blockers"][0]


def test_changed_bytes_and_outside_root_fail(approved_observation):
    row, protocol, root = approved_observation
    (root / row["source_reference"]).write_text("changed")
    assert "checksum" in pilot.evaluate_window_observation(row, root, protocol)["blockers"][0]
    with pytest.raises(ValueError, match="outside"):
        pilot.bounded_path(root, "/etc/passwd")


def test_small_or_disconnected_water_patch_is_unknown(approved_observation):
    row, protocol, root = approved_observation
    row["patch_reference"], row["patch_sha256"] = save(root, "small.json", mapping(shapely.box(500000, 1500000, 500010, 1500010)))
    sign_observation(root, row)
    assert "patch fails" in pilot.evaluate_window_observation(row, root, protocol)["blockers"][0]


def test_one_dry_acquisition_not_full_day_negative(approved_observation):
    row, protocol, root = approved_observation
    row["outcome"] = "NEGATIVE"
    sign_observation(root, row)
    assert "full-interval" in pilot.evaluate_window_observation(row, root, protocol)["blockers"][0]


def test_negative_requires_exact_same_unit_time_and_process_bytes(approved_observation):
    row, protocol, root = approved_observation
    ref, digest = save(root, "coverage.dat", "independently reviewed continuous observation process")
    row.update(outcome="NEGATIVE", observation_process={"continuous_full_interval": True, "complete_unit": True,
               "capable_of_target_detection": True, "start": row["target_start"], "end": row["target_end"],
               "unit_sha256": row["unit_sha256"], "reference": ref, "sha256": digest})
    sign_observation(root, row)
    assert pilot.evaluate_window_observation(row, root, protocol)["outcome"] == "NEGATIVE"
    row["observation_process"]["complete_unit"] = False
    sign_observation(root, row)
    assert pilot.evaluate_window_observation(row, root, protocol)["outcome"] == "UNKNOWN"


def test_unreviewed_group_with_regional_documents_remains_unknown(tmp_path):
    row = {"group_id": "group", "outcome": "FLOOD_CONFIRMED", "official_document_ids": ["MHA", "NRSC"]}
    assert pilot.evaluate_event_review(row, tmp_path)["outcome"] == "UNKNOWN"


def test_malformed_review_receipt_fails_closed(tmp_path):
    reference, digest = save(tmp_path, "malformed.json", [])
    result = pilot.evaluate_event_review({"group_id": "group", "receipt_reference": reference, "receipt_sha256": digest}, tmp_path)
    assert result["outcome"] == "UNKNOWN" and result["blockers"]


def test_approved_group_receipt_is_bound_to_original_members_and_geography(tmp_path):
    sources = []
    for name in ("field", "satellite"):
        reference, digest = save(tmp_path, name+".dat", name+" independent evidence")
        sources.append({"source_family": name, "reference": reference, "sha256": digest})
    location, digest = save(tmp_path, "location.json", mapping(shapely.box(74, 13, 74.001, 13.001)))
    row = {"group_id": "fixture-group", "source_uuids": ["fixture-original-uuid"], "original_geometry_hashes": ["a"*64],
           "verified_location_reference": location, "verified_location_sha256": digest, "verified_start": "2020-01-01",
           "verified_end": "2020-01-02", "independent_sources": sources, "outcome": "FLOOD_CONFIRMED", "protocol_id": "fixture"}
    reference, digest = save(tmp_path, "event-review.json", {**row, "decision": "APPROVED", "independent_reviewer": "ISOLATED_TEST_FIXTURE", "reviewed_at": "2026-10-12"})
    row.update(receipt_reference=reference, receipt_sha256=digest)
    assert pilot.evaluate_event_review(row, tmp_path)["verified_group"]
    row["source_uuids"] = ["changed-original-uuid"]
    assert not pilot.evaluate_event_review(row, tmp_path)["verified_group"]


def test_single_family_does_not_establish_independent_event_confirmation(tmp_path):
    reference, digest = save(tmp_path, "same-family.dat", "same agency evidence")
    row = {"group_id": "fixture", "source_uuids": ["fixture"], "original_geometry_hashes": ["a"*64],
           "verified_start": "2020-01-01", "verified_end": "2020-01-02", "outcome": "FLOOD_CONFIRMED",
           "independent_sources": [{"source_family": "same", "reference": reference, "sha256": digest}]*2}
    reference, digest = save(tmp_path, "receipt.json", {**row, "decision": "APPROVED", "independent_reviewer": "ISOLATED_TEST_FIXTURE", "reviewed_at": "2026-10-12"})
    row.update(receipt_reference=reference, receipt_sha256=digest)
    result = pilot.evaluate_event_review(row, tmp_path)
    assert "two independently" in result["blockers"][0]


def test_build_refuses_existing_version_without_touching_it(tmp_path):
    output = tmp_path / pilot.OUTPUT
    output.mkdir(parents=True)
    marker = output / "original.txt"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="version exists"):
        pilot.build(tmp_path)
    assert marker.read_text() == "preserve"
