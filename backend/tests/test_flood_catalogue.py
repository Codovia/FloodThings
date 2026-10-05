"""Controlled IFI fixtures stay in temporary directories; no external requests."""
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/catalogue_karnataka_floods.py"
spec = importlib.util.spec_from_file_location("flood_catalogue", SCRIPT)
catalogue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalogue)


def row(**changes):
    value = dict.fromkeys(catalogue.FIELDS, "")
    value.update({"UEI": "FIXTURE-ONLY-001", "State": "Karnataka", "State_Codes": "29",
                  "Districts": "Fixture Former District", "District_LGD_Codes": "123",
                  "Start Date": "01-08-2005 00:00", "End Date": "03-08-2005 00:00",
                  "Extent of damage ": "Fixture line one\r\nFixture line two"})
    value.update(changes)
    return value


def gfd():
    return {"collection": catalogue.GFD, "image_id": catalogue.GFD + "/FIXTURE_ONLY",
            "event_id": 99999, "start_date": "2005-08-02", "end_date_inclusive": "2005-08-04",
            "bands": ["flooded", "jrc_perm_water", "clear_views"]}


def inputs(root, monkeypatch):
    source = root / "India_Flood_Inventory_v3.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=catalogue.FIELDS)
        writer.writeheader(); writer.writerow(row())
    md5 = hashlib.md5(source.read_bytes()).hexdigest()
    # The genuine publisher checksum is never changed outside this isolated fixture.
    monkeypatch.setattr(catalogue, "PUBLISHER_MD5", md5)
    retrieval = root / "retrieval.json"
    retrieval.write_text(json.dumps({"url": catalogue.SOURCE_URL, "http_status": 200,
                                    "filename": source.name, "publisher_md5": md5,
                                    "retrieved_at": "2026-10-05T00:00:00+00:00", **catalogue.fingerprint(source)}))
    return source, retrieval


def signatures(root):
    return {str(p): (p.read_bytes(), catalogue.fingerprint(p), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def test_exact_source_preservation_and_deterministic_filter():
    a = row(); a["Location"] = "Fixture original coordinates unknown"
    b = row(State="Kerala, Karnataka", State_Codes="32,29", Districts="Fixture Other, Fixture Former District")
    rows = [a, row(State="Kerala", State_Codes="32"), b]; original = deepcopy(rows)
    records = catalogue.build(rows, "a" * 64)
    assert records == catalogue.build(rows, "a" * 64)
    assert [r["source_row_ordinal"] for r in records] == [1, 3]
    assert [r["original_source_values"] for r in records] == [a, b]
    assert all(r["current_geometry_mapping_status"] == "unresolved" for r in records)
    assert rows == original
    assert all(r["source_district_lgd_codes"] == "123" for r in records)


@pytest.mark.parametrize("state,codes", [("Kerala", "29"), ("Karnataka", "32"), ("", "29")])
def test_conflicting_state_identity_fails_without_guessing(state, codes):
    with pytest.raises(ValueError, match="state"):
        catalogue.build([row(State=state, State_Codes=codes)], "a" * 64)


def test_state_name_only_is_preserved_without_invented_code():
    result = catalogue.build([row(State="karnataka", State_Codes="")], "a" * 64)[0]
    assert result["source_state_codes"] == "" and result["source_state"] == "karnataka"


@pytest.mark.parametrize("raw,status", [("", "missing"), ("31-02-2005 00:00", "malformed"),
                                       ("2005-08-01", "malformed"), ("01-08-2005 00:00", "usable")])
def test_date_parsing_retains_original_missing_or_malformed_values(raw, status):
    record = catalogue.build([row(**{"Start Date": raw})], "a" * 64)[0]
    assert record["source_start_date"] == raw and record["date_status"]["start"] == status
    assert record["satellite_verification_status"] == "unknown"


def test_reversed_dates_have_no_candidate_or_daily_label():
    record = catalogue.build([row(**{"Start Date": "05-08-2005 00:00"})], "a" * 64, [gfd()])[0]
    assert record["date_status"]["window"] == "unusable" and record["gfd_candidates"] == []
    assert "flood" not in record and record["evidence_class"] == "reported_flood_event"


def test_duplicate_source_rows_ids_are_diagnosed_and_not_collapsed_or_introduced():
    original = [row(), row()]
    result = catalogue.build(original, "a" * 64)
    assert len(result) == 2 and len({r["project_event_id"] for r in result}) == 2
    assert catalogue.inspect(original)["duplicate_row_occurrences"] == 1
    assert catalogue.summary(result)["unique_nonmissing_source_event_ids"] == 1


def test_missing_ids_districts_and_none_code_tokens_remain_unknown():
    value = row(UEI="", Districts="", District_LGD_Codes="None")
    result = catalogue.build([value], "a" * 64)[0]
    assert result["ifi_source_event_id"] is None
    assert result["source_districts"] == "" and result["source_district_lgd_codes"] == "None"
    assert catalogue.inspect([value])["unexpected_code_tokens"] == ["None"]


def test_temporal_candidates_never_become_satellite_confirmation():
    record = catalogue.build([row()], "a" * 64, [gfd()])[0]
    assert record["evidence_class"] == "reported_flood_event"
    assert record["satellite_verification_status"] == "candidate_available_spatial_review_required"
    assert record["gfd_candidates"][0]["spatial_verification_required"]
    assert not record["gfd_candidates"][0]["satellite_confirmation"]
    assert catalogue.summary([record])["satellite_confirmed_catalogue_records"] == 0


def test_bad_candidate_identity_fails():
    event = gfd(); event["collection"] = "fabricated"
    with pytest.raises(ValueError, match="source identity"):
        catalogue.build([row()], "a" * 64, [event])


def test_offline_reproduction_validation_preserves_bytes_hashes_and_mtimes(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch)
        before = signatures(root); output = root / "version"
        result = catalogue.create(source, retrieval, output)
        assert result["karnataka_source_rows"] == 1
        assert {name: signatures(root)[name] for name in before} == before
        frozen = signatures(root)
        assert catalogue.validate(output) == result and signatures(root) == frozen
        with pytest.raises(FileExistsError):
            catalogue.create(source, retrieval, output)
        with pytest.raises(FileExistsError, match="completed dataset"):
            catalogue.create(source, retrieval, output / "nested")
        assert signatures(root) == frozen


def test_publisher_checksum_mismatch_prevents_any_output(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch)
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="provenance mismatch"):
            catalogue.create(source, retrieval, root / "version")
        assert not (root / "version").exists()


def test_changed_original_columns_are_not_silently_renamed():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "fixture.csv"; path.write_text("Event,State\nfixture,Karnataka\n")
        with pytest.raises(ValueError, match="columns changed"):
            catalogue.read_source(path)


def test_tampered_evidence_fails_even_after_output_checksum_is_updated(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch); output = root / "version"
        catalogue.create(source, retrieval, output)
        events = json.loads((output / "events.json").read_text())
        events[0]["satellite_verification_status"] = "satellite_confirmed_floodwater"
        (output / "events.json").write_text(json.dumps(events))
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["files"]["events.json"] = catalogue.fingerprint(output / "events.json")
        (output / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="evidence validation"):
            catalogue.validate(output)
