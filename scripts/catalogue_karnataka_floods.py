#!/usr/bin/env python3
"""Offline IFI evidence importer. Requires a checksum-verified original download.

No network, SOI geometry, rainfall join, daily labels or satellite pixel queries.
Detailed outputs remain in ignored data/working pending IFI rights verification.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOI = "10.5281/zenodo.16994648"
SOURCE_URL = "https://zenodo.org/records/16994648/files/India_Flood_Inventory_v3.csv?download=1"
PUBLISHER_MD5 = "fea75a9ff9eba8fb328eaddfacd21d67"
VERSION = "karnataka_flood_events_v1"
GFD = "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1"
FIELDS = ["Unnamed: 0", "UEI", "Start Date", "End Date", "Duration(Days)",
          "Main Cause", "Location", "Districts", "State", "Latitude", "Longitude",
          "Severity", "Area Affected", "Human fatality", "Human injured", "Human Displaced",
          "Animal Fatality", "Description of Casualties/injured", "Extent of damage ",
          "Event Source", "Event Souce ID", "District_LGD_Codes", "State_Codes"]


def fingerprint(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def parse_date(value):
    if not value.strip():
        return None, "missing"
    try:
        return datetime.strptime(value, "%d-%m-%Y %H:%M").date().isoformat(), "usable"
    except ValueError:
        return None, "malformed"


def tokens(value):
    return [x.strip() for x in value.split(",") if x.strip()]


def read_source(path):
    # utf-8-sig handles the published BOM; newline='' preserves embedded CSV newlines.
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError("Original IFI columns changed; inspect the new schema before processing")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed CSV field count")
    return rows


def verified_source(path, retrieval):
    body = path.read_bytes()
    if (retrieval.get("url") != SOURCE_URL or retrieval.get("http_status") != 200
            or retrieval.get("filename") != "India_Flood_Inventory_v3.csv"
            or not retrieval.get("retrieved_at")
            or retrieval.get("publisher_md5") != PUBLISHER_MD5
            or hashlib.md5(body).hexdigest() != PUBLISHER_MD5
            or any(retrieval.get(k) != v for k, v in fingerprint(path).items())):
        raise ValueError("Original publisher MD5, local checksum or retrieval provenance mismatch")
    datetime.fromisoformat(retrieval["retrieved_at"].replace("Z", "+00:00"))
    return read_source(path)


def state_match(row):
    names = [x.casefold() for x in tokens(row["State"])]
    codes = tokens(row["State_Codes"])
    name = "karnataka" in names
    code = "29" in codes
    if code and not name:
        raise ValueError("Ambiguous source state: code 29 without Karnataka name")
    if name and codes and not code:
        raise ValueError("Conflicting Karnataka source state name/code")
    return name


def inspect(rows):
    """Diagnostics preserve missing/malformed source values, rather than repairing them."""
    ids = Counter(row["UEI"] for row in rows if row["UEI"])
    row_counts = Counter(canonical(row) for row in rows)
    dates = Counter(parse_date(row[field])[1] for row in rows for field in ["Start Date", "End Date"])
    return {
        "original_columns": FIELDS, "source_rows": len(rows),
        "duplicate_row_occurrences": sum(n - 1 for n in row_counts.values()),
        "duplicated_event_identifiers": {k: n for k, n in sorted(ids.items()) if n > 1},
        "missing_event_identifiers": sum(not row["UEI"].strip() for row in rows),
        "date_fields": dict(dates),
        "reversed_date_windows": sum(bool(a and b and a > b) for a, b in
                                     [(parse_date(r["Start Date"])[0], parse_date(r["End Date"])[0]) for r in rows]),
        "missing_states": sum(not r["State"].strip() for r in rows),
        "missing_districts": sum(not r["Districts"].strip() for r in rows),
        "unexpected_code_tokens": sorted({x for r in rows for f in ["State_Codes", "District_LGD_Codes"]
                                          for x in tokens(r[f]) if not re.fullmatch(r"[1-9][0-9]*", x)}),
        "spelling_review": "Original name strings retained; variants are not silently canonicalised",
    }


def candidates(start, end, inventory):
    if not start or not end or start > end:
        return []
    matches = []
    for event in inventory:
        if event.get("collection") != GFD or not event.get("image_id", "").startswith(GFD + "/"):
            raise ValueError("GFD candidate source identity mismatch")
        a, b = event["start_date"], event["end_date_inclusive"]
        datetime.strptime(a, "%Y-%m-%d"); datetime.strptime(b, "%Y-%m-%d")
        if a > b or not event.get("event_id") or not isinstance(event.get("bands"), list):
            raise ValueError("Malformed GFD metadata")
        if a <= end and start <= b:
            matches.append({**event, "matching_basis": "temporal_overlap_and_query_window_footprint_only",
                            "spatial_verification_required": True,
                            "satellite_confirmation": False})
    return sorted(matches, key=lambda r: (r["start_date"], str(r["event_id"])))


def build(rows, source_sha256, inventory=()):
    result = []
    for ordinal, row in enumerate(rows, start=1):
        if not state_match(row):
            continue
        start, start_status = parse_date(row["Start Date"])
        end, end_status = parse_date(row["End Date"])
        window = "usable" if start and end and start <= end else "unusable"
        found = candidates(start, end, inventory)
        identity = hashlib.sha256((source_sha256 + ":" + str(ordinal) + ":" + canonical(row)).encode()).hexdigest()
        result.append({
            "project_event_id": "fp-ifi-" + identity, "source_row_ordinal": ordinal,
            "ifi_source_event_id": row["UEI"] or None,
            "source_start_date": row["Start Date"], "source_end_date": row["End Date"],
            "parsed_start_date": start, "parsed_end_date_inclusive": end,
            "date_status": {"start": start_status, "end": end_status, "window": window},
            "source_state": row["State"], "source_districts": row["Districts"],
            "source_state_codes": row["State_Codes"], "source_district_lgd_codes": row["District_LGD_Codes"],
            "identifier_status": "IFI source supplied; not independently current-LGD verified",
            "original_source_values": dict(row),
            "evidence_class": "reported_flood_event",
            "official_karnataka_corroboration_status": "not_reviewed",
            "gfd_candidates": found,
            "satellite_verification_status": "candidate_available_spatial_review_required" if found else "unknown",
            "current_geometry_mapping_status": "unresolved",
            "provenance_reference": {"doi": DOI, "filename": "India_Flood_Inventory_v3.csv", "sha256": source_sha256},
            "notes": "Documentary evidence only; multi-state district lists are not reassigned. No daily or negative flood label.",
        })
    return result


def summary(records):
    dates = [r["parsed_start_date"] for r in records if r["parsed_start_date"]]
    return {"karnataka_source_rows": len(records),
            "unique_nonmissing_source_event_ids": len({r["ifi_source_event_id"] for r in records if r["ifi_source_event_id"]}),
            "earliest_start": min(dates, default=None), "latest_start": max(dates, default=None),
            "distinct_source_district_tokens_including_multistate_rows": len({x for r in records for x in tokens(r["source_districts"])}),
            "usable_date_windows": sum(r["date_status"]["window"] == "usable" for r in records),
            "records_with_gfd_candidates": sum(bool(r["gfd_candidates"]) for r in records),
            "satellite_confirmed_catalogue_records": 0,
            "unresolved_current_geometry_mappings": len(records),
            "official_corroboration": "not_reviewed"}


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def create(source, retrieval_path, output, inventory_path=None):
    if output.exists():
        raise FileExistsError("Completed or interrupted version exists; validation is read-only")
    if any((parent / "manifest.json").exists() for parent in output.resolve().parents):
        raise FileExistsError("Cannot create outputs inside a completed dataset")
    if source.resolve().is_relative_to(output.resolve()) or retrieval_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("Output cannot contain source inputs")
    retrieval = json.loads(retrieval_path.read_text())
    rows = verified_source(source, retrieval)
    inventory = json.loads(inventory_path.read_text()) if inventory_path else []
    records = build(rows, fingerprint(source)["sha256"], inventory)
    if not records:
        raise ValueError("No source-verified Karnataka rows; do not create an empty catalogue")
    output.mkdir(parents=True)
    write_json(output / "events.json", records)
    write_json(output / "manifest.json", {
        "version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [{"path": str(p.resolve()), **fingerprint(p)} for p in
                   [source, retrieval_path, *([inventory_path] if inventory_path else [])]],
        "files": {"events.json": fingerprint(output / "events.json")},
        "raw_schema_inspection": inspect(rows), "summary": summary(records),
        "source_url": SOURCE_URL, "release_version": "v4", "original_filename": source.name,
        "publication": "Local only until original rights metadata has been retained and reviewed",
        "gfd_licence": "CC BY-NC 4.0", "satellite_extent_semantics": "event-window maximum, not daily flood occurrence",
        "processing_code_sha256": fingerprint(Path(__file__))["sha256"],
    })
    return validate(output)


def validate(output):
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["version"] != VERSION or set(p.name for p in output.iterdir()) != {"events.json", "manifest.json"}:
        raise ValueError("Version or file set mismatch")
    paths = [Path(record["path"]) for record in manifest["inputs"]]
    for path, recorded in zip(paths, manifest["inputs"]):
        if any(recorded[k] != v for k, v in fingerprint(path).items()):
            raise ValueError("Retained source checksum mismatch")
    if manifest["files"] != {"events.json": fingerprint(output / "events.json")}:
        raise ValueError("Catalogue output checksum mismatch")
    rows = verified_source(paths[0], json.loads(paths[1].read_text()))
    records = json.loads((output / "events.json").read_text())
    expected = build(rows, fingerprint(paths[0])["sha256"], json.loads(paths[2].read_text()) if len(paths) == 3 else [])
    if records != expected or len({r["project_event_id"] for r in records}) != len(records):
        raise ValueError("Exact source preservation or deterministic evidence validation failed")
    if manifest["summary"] != summary(records) or manifest["raw_schema_inspection"] != inspect(rows):
        raise ValueError("Summary or schema diagnostics mismatch")
    return summary(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--retrieval", type=Path)
    parser.add_argument("--gfd-inventory", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/working" / VERSION)
    args = parser.parse_args()
    if args.validate_only:
        result = validate(args.validate_only)
    elif args.source and args.retrieval:
        result = create(args.source, args.retrieval, args.output, args.gfd_inventory)
    else:
        parser.error("Provide a verified original --source and --retrieval, or --validate-only")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
