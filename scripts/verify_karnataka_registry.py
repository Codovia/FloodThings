#!/usr/bin/env python3
"""Provisional NIC name inventory; never assigns LGD codes or exports polygons.

Offline inputs are the original NIC HTML, its retrieval metadata, and bounded
Earth Engine metadata. Existing output versions are never overwritten.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import importlib
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_earth_engine as verification

NIC_URL = "https://igod.gov.in/sg/KA/E042/organizations"
STATE_SOURCE = "WM/geoLab/geoBoundaries/600/ADM1"
# Original spelling/identifier inspected in the source, not an LGD identifier.
STATE_SHAPE_ID = "1811400B56841107211215"
STATE_SOURCE_NAME = "Karn?taka"
VERSION = "karnataka_nic_provisional_v1"


def normalized(name):
    # No fuzzy matching, accent stripping, aliases, or rename substitution.
    return " ".join(name.split()).casefold()


def unique(values, label):
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}")


def validate_registry(rows, require_lgd=True):
    if not rows:
        raise ValueError("Empty district inventory")
    names, codes = [], []
    for row in rows:
        name = row.get("district_name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing district name")
        names.append(normalized(name))
        code, state = row.get("lgd_district_code"), row.get("lgd_state_code")
        if require_lgd and (not isinstance(code, str) or not code.isdecimal()
                            or not isinstance(state, str) or not state.isdecimal()):
            raise ValueError("Missing or invalid official LGD identifiers")
        if code is not None:
            codes.append(code)
        if not require_lgd and (code is not None or state is not None):
            raise ValueError("Provisional NIC inventory must not assign LGD identifiers")
    unique(names, "district names")
    unique(codes, "LGD codes")
    if require_lgd and len({row["lgd_state_code"] for row in rows}) != 1:
        raise ValueError("Mismatched state identifiers")


def validate_coverage(expected_names, actual_names):
    expected, actual = [normalized(n) for n in expected_names], [normalized(n) for n in actual_names]
    unique(expected, "expected names")
    unique(actual, "actual names")
    if set(expected) != set(actual):
        raise ValueError(f"Mismatched district coverage: missing={sorted(set(expected)-set(actual))}, "
                         f"extra={sorted(set(actual)-set(expected))}")


class NICParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.records, self.parts, self.active, self.link = [], [], False, None
        self.divs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            self.divs.append("search-result-row" in attrs.get("class", "").split())
        if tag == "a" and any(self.divs) and "search-title" in attrs.get("class", "").split():
            if self.active:
                raise ValueError("Nested NIC district links")
            self.active, self.parts, self.link = True, [], attrs.get("href")

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active:
            name = " ".join(" ".join(self.parts).split())
            parsed = urlparse(self.link or "")
            if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".nic.in"):
                raise ValueError("Unexpected NIC district website URL")
            self.records.append({"district_name": name, "district_website": self.link,
                                 "lgd_district_code": None, "lgd_state_code": None,
                                 "identity_status": "provisional_nic_name_lgd_unresolved"})
            self.active = False
        if tag == "div" and self.divs:
            self.divs.pop()


def parse_nic(body, pages=()):
    text = body.decode("utf-8", errors="strict")
    if "Districts - Karnataka" not in text:
        raise ValueError("Response is not the Karnataka district directory")
    parser = NICParser()
    parser.feed(text)
    for page in pages:
        parser.feed(page.decode("utf-8", errors="strict"))
    if parser.active:
        raise ValueError("Truncated NIC district link")
    # Reconcile the parsed list with the page's own published count.
    import re
    counts = re.findall(r"\b(\d+)\s+Results\b", text)
    if len(counts) != 1 or len(parser.records) != int(counts[0]):
        raise ValueError("NIC declared district count differs from parsed coverage")
    validate_registry(parser.records, require_lgd=False)
    return parser.records


def assess_matches(rows, candidates):
    """Return candidates only. Name agreement never establishes official identity."""
    unique([c["shapeID"] for c in candidates], "source shape identifiers")
    results = []
    for row in rows:
        matches = [c for c in candidates if c.get("centroid_within_state") is True
                   and normalized(c["shapeName"]) == normalized(row["district_name"])]
        status = "name_candidate_not_officially_reconciled" if len(matches) == 1 else "unmatched"
        if len(matches) > 1:
            status = "ambiguous"
        results.append({**row, "boundary_match_status": status,
                        "boundary_source_id": verification.BOUNDARY_ID,
                        "boundary_source_version": "6.0.0; 2023-09-13 CGAZ composite",
                        "boundary_candidates": matches, "verified_boundary_id": None})
    return results


def validate_geometry(geometry, crs="EPSG:4326"):
    """Fail closed for future boundary inputs; never repair or manufacture shapes."""
    if crs != "EPSG:4326":
        raise ValueError("Expected explicitly declared EPSG:4326 coordinates")
    from shapely.geometry import shape
    try:
        result = shape(geometry)
    except Exception as exc:
        raise ValueError("Invalid geometry structure") from exc
    if result.geom_type not in {"Polygon", "MultiPolygon"} or result.is_empty or not result.is_valid:
        raise ValueError("Invalid district polygon geometry")
    west, south, east, north = result.bounds
    if not all(math.isfinite(v) for v in result.bounds) or not (-180 <= west <= east <= 180
                                                              and -90 <= south <= north <= 90):
        raise ValueError("Invalid geographic coordinate bounds")
    return result


def inspect_boundaries(ee):
    query = {"country": "IND", "state_shape_id": STATE_SHAPE_ID,
             "state_original_name": STATE_SOURCE_NAME, "district_level": "ADM2",
             "max_features": 80, "geometry_error_m": 100,
             "per_request_deadline_ms": 10000, "retries": 0, "wall_seconds": 90,
             "selection": "filterBounds(actual ADM1 geometry); centroid containment metadata",
             "polygon_export": False}
    report = {"source_id": verification.BOUNDARY_ID, "state_source_id": STATE_SOURCE,
              "version": "6.0.0; 2023-09-13 CGAZ composite", "project": "floodpulse",
              "retrieved_at": verification.now(), "query_parameters": query,
              "status": "unavailable", "geometry_validation": "not_run_metadata_only"}
    try:
        with verification.wall_limit(90):
            report["access"] = verification.probe_access(ee, "floodpulse")
            states = (ee.FeatureCollection(STATE_SOURCE).filter(ee.Filter.eq("shapeGroup", "IND"))
                      .filter(ee.Filter.eq("shapeID", STATE_SHAPE_ID)))
            if states.size().getInfo() != 1:
                raise ValueError("Require exactly one inspected state shape identifier")
            state = ee.Feature(states.first())
            report["state_properties"] = state.toDictionary().getInfo()
            if report["state_properties"]["shapeName"] != STATE_SOURCE_NAME:
                raise ValueError("State source name changed; explicit review required")
            geometry = state.geometry()
            report["state_bounds"] = geometry.bounds(maxError=100).coordinates().getInfo()
            districts = (ee.FeatureCollection(verification.BOUNDARY_ID)
                         .filter(ee.Filter.eq("shapeGroup", "IND"))
                         .filter(ee.Filter.eq("shapeType", "ADM2")).filterBounds(geometry))

            def metadata(feature):
                centroid = feature.geometry().centroid(maxError=100)
                return ee.Feature(None, feature.toDictionary().set(
                    "centroid_within_state", geometry.contains(centroid, maxError=100)))

            info = districts.limit(81).map(metadata).getInfo()
            if len(info["features"]) > 80:
                raise ValueError("District metadata exceeds bounded 80-feature limit")
            report["boundary_candidates"] = [f["properties"] for f in info["features"]]
            report["asset_version"] = info.get("version")
            report["status"] = "available_metadata_only"
    except (Exception, verification.VerificationDeadlineExceeded) as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    report["completed_at"] = verification.now()
    return report


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def build_inventory(body, retrieval, boundary_metadata, pages=()):
    if retrieval.get("url") != NIC_URL or retrieval.get("http_status") != 200:
        raise ValueError("Require successful official NIC retrieval")
    if retrieval.get("sha256") != sha256(body) or retrieval.get("bytes") != len(body):
        raise ValueError("NIC original-response checksum/size mismatch")
    stamp = datetime.fromisoformat(retrieval["retrieved_at"])
    if stamp.tzinfo is None:
        raise ValueError("Retrieval timestamp must include timezone")
    page_metadata = retrieval.get("pages", [])
    if len(page_metadata) != len(pages):
        raise ValueError("Missing NIC pagination response provenance")
    for page, metadata in zip(pages, page_metadata):
        if (metadata.get("http_status") != 200 or metadata.get("sha256") != sha256(page)
                or metadata.get("bytes") != len(page)
                or not metadata.get("url", "").startswith(
                    "https://igod.gov.in/sg/KA/E042/organizations_more/")):
            raise ValueError("NIC pagination source/checksum mismatch")
        if datetime.fromisoformat(metadata["retrieved_at"]).tzinfo is None:
            raise ValueError("Pagination timestamp must include timezone")
    rows = parse_nic(body, pages)
    candidates = boundary_metadata.get("boundary_candidates", [])
    if boundary_metadata.get("status") != "available_metadata_only":
        candidates = []
    return {"version": VERSION, "status": "provisional_not_lgd_not_ready_for_extraction",
            "stage_1_complete": False, "state_name": "Karnataka", "lgd_state_code": None,
            "records": assess_matches(rows, candidates), "boundary_inspection": boundary_metadata,
            "spatial_validation": "not_run_no_officially_reconciled_polygons"}


def write_version(output, inventory, retrieval):
    """Create a new version exclusively; inputs and completed versions stay read-only."""
    output = Path(output)
    if any((parent / "manifest.json").exists() for parent in output.resolve().parents):
        raise ValueError("Cannot write inside an existing manifested dataset version")
    output.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(inventory, indent=2, ensure_ascii=False) + "\n").encode()
    (output / "district_names.json").write_bytes(payload)
    manifest = {"version": VERSION, "status": inventory["status"], "stage_1_complete": False,
                "created_at": datetime.now(timezone.utc).isoformat(), "sources": {
                    "nic": {**retrieval, "attribution": "National Informatics Centre, Government of India",
                            "reuse": "Small factual name/URL inventory only; source HTML not redistributed; no blanket document licence asserted"},
                    "boundaries": {"source_id": verification.BOUNDARY_ID, "state_source_id": STATE_SOURCE,
                                   "version": "6.0.0 CGAZ; 2023-09-13 composite, not current LGD",
                                   "attribution": "William & Mary geoLab / geoBoundaries",
                                   "license": "CC BY 4.0",
                                   "url": "https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2"}},
                "files": {"district_names.json": {"sha256": sha256(payload), "bytes": len(payload)}},
                "lgd_export": "unavailable; no original LGD file found",
                "canonical_districts": 0, "verified_polygons": 0,
                "name_count": len(inventory["records"])}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return validate_version(output)


def validate_version(output):
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text())
    body = (output / "district_names.json").read_bytes()
    if manifest["files"]["district_names.json"] != {"sha256": sha256(body), "bytes": len(body)}:
        raise ValueError("Inventory checksum mismatch")
    inventory = json.loads(body)
    validate_registry(inventory["records"], require_lgd=False)
    if inventory.get("stage_1_complete") is not False or manifest.get("stage_1_complete") is not False:
        raise ValueError("Provisional inventory cannot complete Stage 1")
    if len(inventory["records"]) != manifest["name_count"]:
        raise ValueError("Manifest district coverage mismatch")
    if any(row.get("verified_boundary_id") is not None for row in inventory["records"]):
        raise ValueError("NIC name inventory cannot publish verified polygons")
    return {"status": "valid_provisional_inventory", "name_count": len(inventory["records"]),
            "lgd_codes": 0, "verified_polygons": 0, "stage_1_complete": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-boundaries", action="store_true", help="Bounded live metadata only; JSON to stdout")
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--nic-html", type=Path)
    parser.add_argument("--nic-page", type=Path, action="append", default=[])
    parser.add_argument("--retrieval-json", type=Path)
    parser.add_argument("--boundary-metadata", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.inspect_boundaries:
        result = inspect_boundaries(importlib.import_module("ee"))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "available_metadata_only" else 1
    if args.validate_only:
        print(json.dumps(validate_version(args.validate_only), indent=2))
        return 0
    if not all([args.nic_html, args.retrieval_json, args.boundary_metadata, args.output_dir]):
        parser.error("Provide NIC HTML, retrieval metadata, boundary metadata and a new output directory")
    retrieval = json.loads(args.retrieval_json.read_text())
    inventory = build_inventory(args.nic_html.read_bytes(), retrieval,
                                json.loads(args.boundary_metadata.read_text()),
                                [page.read_bytes() for page in args.nic_page])
    print(json.dumps(write_version(args.output_dir, inventory, retrieval), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
