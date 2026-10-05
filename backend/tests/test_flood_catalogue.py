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
    assert record["satellite_verification_status"] == "not_reviewed"


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


def publisher_record(root, source, retrieval):
    """Controlled record shaped like the retained API; no live source content."""
    data = json.loads(retrieval.read_text())
    link = "https://zenodo.org/api/records/16994648/files/India_Flood_Inventory_v3.csv/content"
    record = {"id": 16994648, "metadata": {"doi": catalogue.DOI, "publication_date": "2025-08-29",
                                          "access_right": "open", "license": {"id": "cc-by-nc-4.0"}},
              "files": [{"key": source.name, "size": source.stat().st_size,
                         "checksum": "md5:" + data["publisher_md5"], "links": {"self": link}}]}
    path = root / "record.json"; path.write_text(json.dumps(record))
    data.update(url=link, record_metadata_path=str(path), record_metadata_sha256=catalogue.fingerprint(path)["sha256"])
    retrieval.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("status", [200, 206])
def test_api_provided_link_and_resumed_response_use_retained_record_provenance(monkeypatch, status):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch)
        record = publisher_record(root, source, retrieval)
        data = json.loads(retrieval.read_text()); data["http_status"] = status
        retrieval.write_text(json.dumps(data)); frozen = signatures(root)
        output = root / "version"; result = catalogue.create(source, retrieval, output)
        manifest = json.loads((output / "manifest.json").read_text())
        assert manifest["source_url"] == data["url"]
        assert manifest["record_metadata_exact"] == json.loads(record.read_text())["metadata"]
        assert manifest["record_metadata_exact"]["license"] == {"id": "cc-by-nc-4.0"}
        assert not manifest["api_version_field_present"]
        assert catalogue.validate(output) == result
        assert {name: signatures(root)[name] for name in frozen} == frozen


@pytest.mark.parametrize("change", ["link", "size", "record", "checksum", "metadata_hash", "mirror"])
def test_record_conflicts_are_rejected_before_output(monkeypatch, change):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch)
        path = publisher_record(root, source, retrieval); record = json.loads(path.read_text())
        data = json.loads(retrieval.read_text())
        if change == "link": record["files"][0]["links"]["self"] += "?different=1"
        if change == "size": record["files"][0]["size"] += 1
        if change == "record": record["id"] = 1
        if change == "checksum": record["files"][0]["checksum"] = "md5:" + "0" * 32
        if change == "metadata_hash": record["metadata"]["publication_date"] = "2000-01-01"
        if change == "mirror":
            data["url"] = "https://unofficial.invalid/fixture.csv"
            record["files"][0]["links"]["self"] = data["url"]
        path.write_text(json.dumps(record))
        if change != "metadata_hash": data["record_metadata_sha256"] = catalogue.fingerprint(path)["sha256"]
        retrieval.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="record"):
            catalogue.create(source, retrieval, root / "version")
        assert not (root / "version").exists()


def test_open_access_without_a_licence_never_invents_reuse_rights(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch)
        path = publisher_record(root, source, retrieval); record = json.loads(path.read_text())
        del record["metadata"]["license"]; path.write_text(json.dumps(record))
        data = json.loads(retrieval.read_text()); data["record_metadata_sha256"] = catalogue.fingerprint(path)["sha256"]
        retrieval.write_text(json.dumps(data)); output = root / "version"
        catalogue.create(source, retrieval, output)
        assert "license" not in json.loads((output / "manifest.json").read_text())["record_metadata_exact"]


def test_missing_reversed_and_complete_windows_keep_source_duration_separate():
    rows = [row(**{"Duration(Days)": "99"}), row(**{"Start Date": "", "End Date": ""}),
            row(**{"Start Date": "05-08-2005 00:00"}), row(**{"End Date": ""})]
    records = catalogue.build(rows, "a" * 64); result = catalogue.summary(records)
    assert records[0]["derived_event_duration_days_inclusive"] == 3
    assert records[0]["source_duration_days"] == "99"
    assert records[1]["derived_event_duration_days_inclusive"] is None
    assert records[2]["derived_event_duration_days_inclusive"] is None
    assert result["complete_parsed_date_pairs"] == 2 and result["usable_date_windows"] == 1
    assert result["partially_dated_rows"] == 1 and result["both_dates_missing_or_malformed_rows"] == 1
    assert result["reversed_date_windows"] == 1


def udupi_fixture(root):
    directory = root / "fixture_udupi"; directory.mkdir(); path = directory / "event_evidence.csv"
    previous = []
    for event, start, end, count in [(2728, "2005-09-14", "2005-09-30", 33), (3551, "2009-09-25", "2009-10-12", 23)]:
        previous.append({"event_id": str(event), "image_id": catalogue.GFD + "/FIXTURE_ONLY_" + str(event),
                         "start_date": start, "end_date_inclusive": end, "processing_scale_m": "250",
                         "positive_observed_pixels": str(count), "finding": "confirmed_mapped_nonpermanent_floodwater",
                         "extent_semantics": "event_window_maximum_not_daily_occurrence"})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(previous[0])); writer.writeheader(); writer.writerows(previous)
    manifest = {"version": "udupi_historical_v1", "files": {path.name: catalogue.fingerprint(path)},
                "query_parameters": {"events": previous}}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return path


def test_temporal_location_overlap_keeps_prior_satellite_evidence_separate():
    with TemporaryDirectory() as temporary:
        root = Path(temporary); path = udupi_fixture(root); frozen = signatures(root)
        source = row(Districts="Udupi", **{"Start Date": "01-10-2009 00:00", "End Date": "07-10-2009 00:00"})
        records = catalogue.build([source], "a" * 64)
        result = catalogue.existing_udupi_evidence(path, records)
        assert [r["matched_ifi_project_ids"] for r in result] == [[], []]
        assert result[1]["overlapping_ifi_ids_for_review_only"] == ["FIXTURE-ONLY-001"]
        assert result[0]["overlapping_ifi_ids_for_review_only"] == []
        assert records[0]["evidence_class"] == "reported_flood_event"
        assert records[0]["satellite_verification_status"] == "not_reviewed"
        assert signatures(root) == frozen


def test_independent_evidence_is_reproducible_read_only_and_rejects_corruption(monkeypatch):
    with TemporaryDirectory() as temporary:
        root = Path(temporary); source, retrieval = inputs(root, monkeypatch); prior = udupi_fixture(root)
        output = root / "version"; catalogue.create(source, retrieval, output, udupi_path=prior)
        frozen = signatures(root); catalogue.validate(output)
        assert signatures(root) == frozen
        prior.write_bytes(prior.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="checksum mismatch"):
            catalogue.validate(output)
