#!/usr/bin/env python3
"""Offline Phase 12B receipts and retained-source coverage; no data acquisition.

Completed versions are immutable. Public outputs omit footprints, coordinates,
restricted observation values and original source tokens. No labels are inferred
from catalogue entries or incomplete observations.
"""
import argparse
import csv
import json
from pathlib import Path
import re

from audit_satellite_observations import audit, timestamp
from build_flood_outcome_foundation import ROOT, checked_file, checked_json, fingerprint, rows, validate as validate_foundation
from inspect_groundsource_metadata import inspect

VERSION = "karnataka_flood_observation_feasibility_v1"
RECEIPTS = "data/recovery/phase12b_v1"
CODE = ("build_flood_observation_feasibility.py", "audit_satellite_observations.py",
        "inspect_groundsource_metadata.py", "build_flood_outcome_foundation.py", "audit_flood_label_candidates.py")


def opera_metadata(body, headers):
    statuses = re.findall(r"^HTTP/\S+ (\d+)", headers, re.MULTILINE)
    hits = re.findall(r"^cmr-hits:\s*(\d+)\s*$", headers, re.MULTILINE | re.IGNORECASE)
    if not statuses or statuses[-1] != "200" or len(hits) != 1:
        raise ValueError("CMR successful response/total-hit receipt missing")
    entries = body["feed"]["entry"]
    if not isinstance(entries, list) or len(entries) > 5 or int(hits[0]) < len(entries):
        raise ValueError("CMR page violates bounded query contract")
    result = []
    for entry in entries:
        if entry["collection_concept_id"] != "C2949811996-POCLOUD":
            raise ValueError("CMR product collection differs")
        start, end = timestamp(entry["time_start"]), timestamp(entry["time_end"])
        if start > end or start.year != 2025 or start.month != 8:
            raise ValueError("CMR observation time outside requested month")
        if not any(len(b.split()) == 4 and float(b.split()[0]) <= 13.3282357461
                   and float(b.split()[1]) <= 74.7335742992 and float(b.split()[2]) >= 13.3553905029
                   and float(b.split()[3]) >= 74.7613053322 for b in entry.get("boxes", [])):
            raise ValueError("CMR metadata box does not contain public pilot query box")
        result.append({"id": entry["id"], "product_id": entry["producer_granule_id"],
                       "acquisition_start": entry["time_start"], "acquisition_end": entry["time_end"],
                       "catalogue_updated": entry["updated"]})
    if len({r["id"] for r in result}) != len(result):
        raise ValueError("Repeated CMR catalogue identifier")
    return {"total_catalogue_matches": int(hits[0]), "metadata_records_inspected": len(result),
            "complete_query_metadata_page": int(hits[0]) == len(result), "products": result,
            "query_scope": "retained public 3 km Udupi pilot box, August 2025; not district coverage",
            "rasters_retrieved": 0, "valid_observed_pixels": None,
            "affected_period_reprocessing_status": "UNVERIFIED_FOR_THESE_PRODUCTS",
            "labels": "UNKNOWN_METADATA_ONLY"}


def collect(root=ROOT):
    foundation = validate_foundation(root)
    inputs = dict(foundation["inputs"])
    recovery = root / RECEIPTS
    receipt_names = ("groundsource-record.json", "groundsource-tail.bin", "groundsource-footer.bin",
                     "groundsource-tail-headers.txt", "groundsource-footer-headers.txt",
                     "opera-cmr-with-headers.json", "opera-cmr-headers.txt", "opera-product-page.html")
    for name in receipt_names:
        inputs[str((recovery / name).relative_to(root))] = fingerprint(recovery / name)
    ground = inspect(json.loads((recovery / receipt_names[0]).read_text()),
                     (recovery / receipt_names[1]).read_bytes(), (recovery / receipt_names[2]).read_bytes(),
                     (recovery / receipt_names[3]).read_text(), (recovery / receipt_names[4]).read_text())
    opera = opera_metadata(json.loads((recovery / "opera-cmr-with-headers.json").read_text()),
                           (recovery / "opera-cmr-headers.txt").read_text())
    page = (recovery / "opera-product-page.html").read_text()
    if not all(term in page for term in ("May 20, 2025", "Nov 7, 2025", "Dec 9, 2025", "Jan. 2026")):
        raise ValueError("Retained OPERA processing alert no longer matches reviewed evidence")
    historical = root / "data/processed/udupi_historical_v1"
    path = historical / "event_evidence.csv"
    manifest = json.loads((historical / "manifest.json").read_text())
    if fingerprint(path)["sha256"] != manifest["files"][path.name]["sha256"]:
        raise ValueError("Historical Udupi event evidence checksum mismatch")
    inputs[str(path.relative_to(root))] = fingerprint(path)
    evidence = {int(r["event_id"]): r for r in rows(path)}
    matrix = []
    for scope in foundation["scopes"]:
        valid = scope["valid_pixels"]
        if scope["district"] == "Udupi":
            r = evidence[scope["gfd_id"]]
            if int(r["positive_observed_pixels"]) != scope["positive_pixels"] or r["start_date"] != scope["start"]:
                raise ValueError("Independent retained Udupi summaries disagree")
            valid = int(r["valid_observed_pixels"])
        matrix.append({"source": "GFD", "district_context": scope["district"], "source_id": str(scope["gfd_id"]),
                       "time_start": scope["start"], "time_end": scope["end"],
                       "time_semantics": "INCLUSIVE_EVENT_WINDOW_NOT_ACQUISITION", "processing_grid_m": 250,
                       "unit_pixels": scope["region_pixels"], "valid_pixels": valid,
                       "qualifying_event_pixels": scope["positive_pixels"], "observed_status": scope["status"],
                       "eligible_acquisition_labels": 0, "eligible_24h_labels": 0,
                       "blocker": "event maximum; exact acquisitions and continuous absence not retained; independent daily review absent"})
    sar_dir = root / "data/working/belagavi_2021_incidence_audit_v1"
    sar = checked_json(sar_dir, "audit.json")
    diagnostics_dir = root / "data/working/belagavi_2021_sentinel1_anchor_v1"
    diagnostics = checked_json(diagnostics_dir, "continuous_diagnostics.json")
    for directory, name in ((sar_dir, "audit.json"), (diagnostics_dir, "continuous_diagnostics.json")):
        inputs[str((directory / name).relative_to(root))] = fingerprint(directory / name)
    if diagnostics["flood_label"] is not None or diagnostics["threshold_analysis_performed"] is not False:
        raise ValueError("Continuous SAR source role changed; scientific review required")
    sar_rows = []
    for scene in sar["incidence"]["scenes"]:
        timestamp(scene["acquisition_utc"])
        sar_rows.append({"acquisition": scene["acquisition_utc"], "valid_vv_vh_cells": scene["valid_vv_vh_cells"],
                         "valid_angle_intersection_cells": scene["intersection_cells"]})
        matrix.append({"source": "SENTINEL1", "district_context": "Belagavi", "source_id": scene["acquisition_utc"],
                       "time_start": scene["acquisition_utc"], "time_end": scene["acquisition_utc"],
                       "time_semantics": "ACQUISITION", "processing_grid_m": 10, "unit_pixels": 40000,
                       "valid_pixels": scene["valid_vv_vh_cells"], "qualifying_event_pixels": None,
                       "observed_status": "CONTINUOUS_BACKSCATTER_NOT_FLOOD_CLASSIFICATION",
                       "eligible_acquisition_labels": 0, "eligible_24h_labels": 0,
                       "blocker": "categorical independently matched inundation/absence truth unavailable"})
    for product in opera["products"]:
        matrix.append({"source": "OPERA_DSWX_S1", "district_context": "Udupi pilot box only", "source_id": product["id"],
                       "time_start": product["acquisition_start"], "time_end": product["acquisition_end"],
                       "time_semantics": "CATALOGUE_ACQUISITION_INTERVAL", "processing_grid_m": 30,
                       "unit_pixels": None, "valid_pixels": None, "qualifying_event_pixels": None,
                       "observed_status": "UNKNOWN_METADATA_ONLY", "eligible_acquisition_labels": 0,
                       "eligible_24h_labels": 0, "blocker": "water/quality/permanent-water rasters absent; affected-period reprocessing unverified"})
    # There are no reviewed acquisition classification records to pass to the
    # new contract. Missing records are not zero-water records or negatives.
    acquisition_audit = audit([], root)
    readiness = {"decision": "NO-GO", "eligible_positive_labels": 0, "eligible_negative_labels": 0,
                 "independent_eligible_events": 0, "eligible_24h_labels": 0, "eligible_forecast_examples": 0,
                 "positive_research_source_event_groups": foundation["gfd"]["positive_event_groups"],
                 "blocking_evidence": foundation["training_readiness"]["blocking_evidence"] + [
                     "no independently adjudicated acquisition-time categorical labels",
                     "satellite revisit cannot establish full 24-hour absence",
                     "OPERA pixel coverage and product-specific corrected provenance unverified",
                     "no event/spatial/temporal disjoint held-out labelled flood dataset"],
                 "model_trained": False, "operational_forecast_authorized": False}
    return {"version": VERSION, "groundsource": ground, "gfd": foundation["gfd"], "ifi": foundation["ifi"],
            "sentinel1": {"scenes": sar_rows, "processing_grid_m": 10, "unit_area_km2": 4,
                          "permanent_water_cells": diagnostics["permanent_water_cells"],
                          "permanent_water_status_unknown_cells": diagnostics["permanent_water_status_unknown_cells"],
                          "monthly_product_is_absence_evidence": False, "classification_available": False},
            "opera": opera, "riverine": {"cwc": foundation["cwc"], "glofas": foundation["glofas"],
                                        "decision": "NO-GO_UNRESOLVED_DATUM_TIME_QC_REACH_RIGHTS_ISSUANCE"},
            "acquisition_audit": acquisition_audit, "training_readiness": readiness,
            "coverage_note": "Retained source scopes and catalogue products only; unenumerated unit-days UNKNOWN. No Karnataka-wide observation coverage inferred.",
            "inputs": inputs}, matrix


def csv_bytes(matrix):
    import io
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(matrix[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(matrix)
    return handle.getvalue().encode()


def public_report(report):
    return {k: v for k, v in report.items() if k != "inputs"}


def build(root=ROOT):
    output = root / "data/working" / VERSION
    if output.exists():
        raise ValueError("Completed version exists; validate instead of overwrite")
    report, matrix = collect(root)
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (output / "observation_coverage.csv").write_bytes(csv_bytes(matrix))
    code = {name: fingerprint(Path(__file__).with_name(name)) for name in CODE}
    (output / "manifest.json").write_text(json.dumps({"version": VERSION, "code": code,
        "files": {p.name: fingerprint(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    return report


def validate(root=ROOT, public=None):
    output = root / "data/working" / VERSION
    report, matrix = collect(root)
    for name in ("report.json", "observation_coverage.csv"):
        checked_file(output, name)
    if json.loads((output / "report.json").read_text()) != report or (output / "observation_coverage.csv").read_bytes() != csv_bytes(matrix):
        raise ValueError("Feasibility reproduction differs")
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["code"] != {name: fingerprint(Path(__file__).with_name(name)) for name in CODE}:
        raise ValueError("Processing code changed; scientific version review required")
    if public is not None:
        if json.loads((public / "report.json").read_text()) != public_report(report) or (public / "observation_coverage.csv").read_bytes() != csv_bytes(matrix):
            raise ValueError("Public aggregates differ from local validated results")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--public", type=Path, help="read-only public aggregate reproduction check")
    args = parser.parse_args()
    try:
        report = build() if args.command == "build" else validate(public=args.public)
        print(json.dumps({"version": VERSION, "training_readiness": report["training_readiness"],
                          "groundsource_karnataka_records": report["groundsource"]["karnataka_records"]}, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f"Feasibility failed: {error}\n")
