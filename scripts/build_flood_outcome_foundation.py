#!/usr/bin/env python3
"""Reproduce Phase 12A from retained files. Offline; no new labels or model fits.

build writes a NEW ignored research version only. Public report contains aggregate
counts, source event IDs and checksums, never restricted coordinates/observations.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from audit_flood_label_candidates import REQUIRED, audit, training_readiness

ROOT = Path(__file__).resolve().parents[1]
VERSION = "karnataka_flood_outcome_foundation_v1"


def fingerprint(path):
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked_file(directory, name):
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = manifest["files"][name]
    actual = fingerprint(directory / name)
    if any(actual[k] != expected[k] for k in actual):
        raise ValueError(f"Source checksum mismatch: {directory / name}")
    return directory / name


def checked_json(directory, name):
    return json.loads(checked_file(directory, name).read_text())


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def collect(root=ROOT):
    working = root / "data/working"
    udupi = root / "data/processed/udupi_flood_spatial_v1"
    manifest = json.loads((udupi / "manifest.json").read_text())
    scopes, inputs = [], {}
    for event in manifest["events"]:
        path = checked_file(udupi, event["geometry_file"])
        features = json.loads(path.read_text())["features"]
        if len(features) != event["qualified_pixel_count"]:
            raise ValueError("Udupi feature count mismatch")
        checked_file(udupi, event["raster_file"])
        scopes.append({"gfd_id": event["event_id"], "district": "Udupi",
                       "shape_id": manifest["boundary_id"], "start": event["start_date"],
                       "end": event["end_date_inclusive"], "positive_pixels": len(features),
                       "valid_pixels": None, "region_pixels": None, "valid_fraction": None,
                       "status": "satellite_positive", "reference": str(path.relative_to(root)),
                       "sha256": fingerprint(path)["sha256"]})
        inputs[str(path.relative_to(root))] = fingerprint(path)
    for version in ("karnataka_satellite_event_evidence_v2", "karnataka_satellite_event_evidence_v3",
                    "karnataka_satellite_event_evidence_v4"):
        directory = working / version
        path = checked_file(directory, "event_evidence.json")
        inputs[str(path.relative_to(root))] = fingerprint(path)
        for event in json.loads(path.read_text()):
            if event["computation_complete"] is not True:
                raise ValueError("Incomplete retained satellite computation")
            stats = event["statistics"]
            scopes.append({"gfd_id": event["gfd_id"], "district": event["review_region"]["shapeName"],
                           "shape_id": event["review_region"]["shapeID"], "start": event["gfd_start"],
                           "end": event["gfd_end_inclusive"], "positive_pixels": stats["qualifying_pixels"],
                           "valid_pixels": stats["valid_pixels"], "region_pixels": stats["region_pixels"],
                           "valid_fraction": event["valid_fraction"], "status": event["evidence_status"],
                           "reference": str(path.relative_to(root)), "sha256": fingerprint(path)["sha256"]})
    if len({r["gfd_id"] for r in scopes}) != len(scopes):
        raise ValueError("Repeated GFD event group; do not double count versions")
    ifi_dir = working / "karnataka_flood_events_v1"
    events = checked_json(ifi_dir, "events.json")
    original_manifest = json.loads((ifi_dir / "manifest.json").read_text())
    for item in original_manifest["inputs"]:
        # Stored absolute paths are mapped to this checkout without editing originals.
        relative = item["path"].split("/FloodPrediction/")[-1]
        path = root / relative
        if fingerprint(path) != {k: item[k] for k in ("bytes", "sha256")}:
            raise ValueError(f"IFI original input mismatch: {relative}")
        inputs[relative] = fingerprint(path)
    hydro_dir = working / "karnataka_hydrology_2019_reconciled_v1"
    hydro = rows(checked_file(hydro_dir, "observation_quality.csv"))
    comparison = rows(checked_file(hydro_dir, "discharge_reconciliation.csv"))
    datum = checked_json(hydro_dir, "datum_compatibility.json")
    glofas_dir = working / "karnataka_glofas_2019_pilot_v1"
    glofas = rows(checked_file(glofas_dir, "daily_modelled_discharge.csv"))
    chirps_dir = working / "karnataka_chirps_soi2025_2025_v1"
    chirps = rows(checked_file(chirps_dir, "daily_rainfall.csv"))
    directory = checked_json(root / "data/reference/karnataka_location_directory_v2", "directory.json")
    for path in (ifi_dir / "events.json", hydro_dir / "observation_quality.csv",
                 hydro_dir / "discharge_reconciliation.csv", glofas_dir / "daily_modelled_discharge.csv",
                 chirps_dir / "daily_rainfall.csv", root / "backend/models/rainfall_logistic_v1/model.json",
                 root / "data/reference/karnataka_location_directory_v2/directory.json"):
        inputs[str(path.relative_to(root))] = fingerprint(path)
    candidates = []
    for scope in scopes:
        positive = scope["status"] == "satellite_positive"
        candidates.append(dict(zip(REQUIRED, [
            "1", f"gfd-scope:{scope['gfd_id']}:{scope['shape_id']}", f"geoboundaries6:{scope['shape_id']}",
            scope["start"], scope["end"], "FLOOD_OBSERVED" if positive else "UNKNOWN",
            "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1", scope["reference"], scope["sha256"], str(scope["gfd_id"]),
            f"gfd:{scope['gfd_id']}", f"gfd:{scope['gfd_id']}", f"gfd-review:{scope['gfd_id']}",
            "FLOOD_OBSERVED" if positive else "PARTIAL" if scope["valid_pixels"] else "UNKNOWN",
            "DISTRICT", "EVENT_WINDOW", "UNKNOWN", "VERIFIED", "PENDING", "", "INTERNAL_USE_VERIFIED",
            scope["reference"], "", f"geoboundaries6:{scope['shape_id']}",
            "event_maximum_not_daily;modern_boundary;mechanism_unknown;no_continuous_absence_proof",
        ])))
    ifi_counts = Counter(r["date_status"]["window"] for r in events)
    report = {
        "version": VERSION, "objective": "Karnataka actual flood occurrence; rainfall is supporting context",
        "scopes": scopes, "inputs": inputs,
        "ifi": {"accessible_rows": len(events), "unique_source_event_ids": len({r["ifi_source_event_id"] for r in events}),
                "date_window_status": dict(ifi_counts), "resolved_current_geometry": sum(r["current_geometry_mapping_status"] != "unresolved" for r in events),
                "label_semantics": "reported positives only; all 494 unresolved for fixed-unit daily training"},
        "gfd": {"reviewed_event_groups": len(scopes), "status_counts": dict(Counter(r["status"] for r in scopes)),
                "positive_event_pixels": sum(r["positive_pixels"] for r in scopes),
                "positive_event_groups": sum(r["status"] == "satellite_positive" for r in scopes),
                "verified_negative_labels": 0, "unknown_scope_records": sum(r["status"] != "satellite_positive" for r in scopes),
                "semantics": "at least one qualified non-permanent mapped-water cell in original event window; no daily onset"},
        "cwc": {"accessible_observations": len(hydro), "comparisons": len(comparison),
                "eligible_with_quality_caveat": sum(r["analysis_eligibility"] == "eligible_with_quality_caveat" for r in hydro),
                "per_station_variable": dict(Counter(r["canonical_cwc_station_id"] + ":" + r["variable"] for r in hydro)),
                "datum_status": {r["station_id"]: r["threshold_compatibility"] for r in datum},
                "flood_labels": 0},
        "glofas": {"accessible_modelled_rows": len(glofas), "columns": list(glofas[0]),
                   "flood_labels": 0, "role": "modelled context; historical averages are not issued forecasts or measured truth"},
        "chirps": {"accessible_annual_rows": len(chirps), "columns": list(chirps[0]), "flood_labels": 0},
        "coverage_note": "Zeros count retained records only. Unobserved district-days are unenumerated UNKNOWN, never negative; exact-name source-region matches are not historical/current administrative certification.",
    }
    # IFI district tokens remain source strings, including other states and former names.
    source_matrix = Counter()
    for event in events:
        year = event["parsed_start_date"][:4] if event["parsed_start_date"] else "UNRESOLVED"
        for name in set(x.strip() for x in event["source_districts"].split(",") if x.strip()) or {"UNRESOLVED"}:
            source_matrix[(name, year)] += 1
    ifi_matrix = [{"source_district_token": name, "year": year, "reported_records": count,
                   "mapping": "UNRESOLVED_NOT_CURRENT_DISTRICT_LABEL"} for (name, year), count in sorted(source_matrix.items())]
    dated_years = {int(r["start"][:4]) for r in scopes} | {int(r["parsed_start_date"][:4]) for r in events if r["parsed_start_date"]} | {2025}
    years = [str(year) for year in range(min(dated_years), max(dated_years) + 1)]
    matrix = []
    for district in directory["districts"]:
        for year in years:
            matches = [r for r in scopes if r["district"] == district["name"] and r["start"][:4] == year]
            matrix.append({"district_id": district["id"], "district": district["name"], "year": year,
                           "mechanism": "UNKNOWN", "positive_event_pixels": sum(r["positive_pixels"] for r in matches),
                           "positive_scopes": sum(r["status"] == "satellite_positive" for r in matches),
                           "verified_negatives": 0, "unknown_scopes": sum(r["status"] != "satellite_positive" for r in matches),
                           "event_groups": len(matches), "eligible": 0, "ineligible": len(matches),
                           "observation_coverage": "PARTIAL_EVENT_WINDOWS" if matches else "UNOBSERVED",
                           "unobserved_intervals": "UNKNOWN_NOT_ENUMERATED", "administrative_mapping": "EXACT_NAME_CONTEXT_ONLY" if matches else "UNASSESSED"})
    report["unassigned_source_regions"] = sorted({r["district"] for r in scopes} - {r["name"] for r in directory["districts"]})
    return report, candidates, matrix, ifi_matrix


def write_csv(path, records, fields=None):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def build(root=ROOT):
    output = root / "data/working" / VERSION
    if output.exists():
        raise ValueError("Completed version exists; use validate, never overwrite")
    report, candidates, matrix, ifi_matrix = collect(root)
    output.mkdir()
    write_csv(output / "candidates.csv", candidates, REQUIRED)
    result = audit(output / "candidates.csv", source_root=root)
    report["candidate_audit"] = result
    report["training_readiness"] = training_readiness(candidates, result)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    write_csv(output / "district_year_coverage.csv", matrix)
    write_csv(output / "ifi_source_year_coverage.csv", ifi_matrix)
    (output / "manifest.json").write_text(json.dumps({"version": VERSION, "files": {
        p.name: fingerprint(p) for p in output.iterdir() if p.is_file()},
        "code": {p.name: fingerprint(p) for p in (Path(__file__), Path(__file__).with_name("audit_flood_label_candidates.py"))}}, indent=2) + "\n")
    return report


def validate(root=ROOT):
    output = root / "data/working" / VERSION
    report, candidates, matrix, ifi_matrix = collect(root)
    for name in ("candidates.csv", "district_year_coverage.csv", "ifi_source_year_coverage.csv", "report.json"):
        checked_file(output, name)
    if rows(output / "candidates.csv") != candidates:
        raise ValueError("Candidate reproduction mismatch")
    for name, expected in (("district_year_coverage.csv", matrix), ("ifi_source_year_coverage.csv", ifi_matrix)):
        if rows(output / name) != [{k: str(v) for k, v in r.items()} for r in expected]:
            raise ValueError("Coverage reproduction mismatch")
    report["candidate_audit"] = audit(output / "candidates.csv", source_root=root)
    report["training_readiness"] = training_readiness(candidates, report["candidate_audit"])
    if json.loads((output / "report.json").read_text()) != report:
        raise ValueError("Report reproduction mismatch")
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["code"].items():
        if fingerprint(Path(__file__).with_name(name)) != expected:
            raise ValueError("Processing code changed; inspect before creating a new version")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    args = parser.parse_args()
    try:
        report = build() if args.command == "build" else validate()
        print(json.dumps({k: report[k] for k in ("version", "ifi", "gfd", "cwc", "training_readiness")}, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Foundation failed: {error}\n")
