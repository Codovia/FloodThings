#!/usr/bin/env python3
"""Offline SOI inspection. Originals and completed versions are always read-only.

Geometry outputs are LOCAL working copies, not cleared for redistribution.
No name substitutions, inferred codes, reprojection of outputs, or geometry repair.
Install optional dependencies from scripts/requirements-boundaries.txt.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

VERSION = "karnataka_soi_abdb2025_verification_v1"
AREA_CRS = "+proj=laea +lat_0=15 +lon_0=76 +datum=WGS84 +units=m +no_defs"
ARCHIVE_URL = "https://surveyofindia.gov.in/documents/State_District_Subdistrict_PAN%20INDIA.rar"
METADATA_URL = "https://surveyofindia.gov.in/documents/Metadata_ABDB.zip"
POLICY_URL = "https://surveyofindia.gov.in/pages/copyright-policy"
COMPONENTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fingerprint(path):
    path = Path(path)
    return {"original_name": path.name, "bytes": path.stat().st_size,
            "sha256": digest(path)}


def normalized(text):
    return " ".join(text.split()).casefold()


def unique(values, label):
    if any(count > 1 for count in Counter(values).values()):
        raise ValueError(f"Duplicate {label}")


def metadata_cells(zip_path, workbook):
    """Read the publisher's simple two-column metadata without changing XLSX bytes."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(zip_path) as outer:
        info = outer.getinfo(workbook)
        if info.file_size > 128 * 1024:
            raise ValueError("Metadata workbook exceeds bounded size")
        body = outer.read(workbook)
        archived_timestamp = list(info.date_time)
    with ZipFile(BytesIO(body)) as book:
        if sum(i.file_size for i in book.infolist()) > 2 * 1024 * 1024:
            raise ValueError("Expanded metadata exceeds bounded size")
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = ["".join(t.text or "" for t in item.findall(".//s:t", ns))
                      for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("s:si", ns)]
        cells = {}
        for cell in ET.fromstring(book.read("xl/worksheets/sheet1.xml")).findall(".//s:c", ns):
            if cell.find("s:f", ns) is not None:
                raise ValueError("Formula in source metadata requires manual inspection")
            value = cell.find("s:v", ns)
            text = value.text if value is not None else ""
            if cell.get("t") == "s":
                text = shared[int(text)]
            elif cell.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in cell.findall(".//s:t", ns))
            cells[cell.attrib["r"]] = text
    return {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "zip_entry_modification_time_not_reference_date": archived_timestamp,
            "cells": cells}


def require_components(path):
    for suffix in COMPONENTS:
        if not path.with_suffix(suffix).is_file():
            raise ValueError(f"Missing shapefile component: {path.with_suffix(suffix)}")


def read_source(path, state_field, district=False):
    path = Path(path)
    require_components(path)
    # Use actual .prj, never substitute the metadata's EPSG assertion.
    wkt = path.with_suffix(".prj").read_text()
    crs = CRS.from_wkt(wkt)
    if not crs.is_projected or any(axis.unit_conversion_factor != 1 for axis in crs.axis_info):
        raise ValueError("Source must explicitly use projected metre coordinates")
    encoding = path.with_suffix(".cpg").read_text().strip()
    with shapefile.Reader(str(path), encoding=encoding) as reader:
        fields = reader.fields[1:]
        required = {state_field} | ({"DISTRICT", "DIST_LGD", "STATE_LGD"} if district else set())
        if not required.issubset({f[0] for f in fields}):
            raise ValueError("Missing original identity fields")
        selected = []
        # Attribute filter first; do not read geometry for the rest of India.
        for record in reader.iterRecords(fields=[state_field]):
            if record[0] == "KARNATAKA":
                item = reader.shapeRecord(record.oid)
                selected.append({"source_record_index": record.oid,
                                 "attributes": item.record.as_dict(), "record": list(item.record),
                                 "shape": item.shape})
        result = {"records": selected, "fields": fields, "shape_type": reader.shapeType,
                  "national_record_count": len(reader), "wkt": wkt, "crs": crs,
                  "encoding": encoding, "path": path}
    if not selected:
        raise ValueError("No genuine Karnataka source records")
    if district:
        for item in selected:
            row = item["attributes"]
            if row["STATE_LGD"] != "29" or not row["DIST_LGD"].isdecimal() or not row["DISTRICT"].strip():
                raise ValueError("Missing or mismatched source identifiers")
        unique([r["attributes"]["DIST_LGD"] for r in selected], "source district codes")
        unique([normalized(r["attributes"]["DISTRICT"]) for r in selected], "source district names")
    return result


def reconcile(records, nic_names):
    unique([normalized(n) for n in nic_names], "NIC names: ambiguous inventory")
    unique([normalized(r["district_name_original"]) for r in records], "source district names")
    result = []
    for row in records:
        matches = [n for n in nic_names if normalized(n) == normalized(row["district_name_original"])]
        result.append({**row, "nic_exact_name": matches[0] if matches else None,
                       "name_status": "exact_name_candidate" if matches else "unresolved_original_spelling_or_rename",
                       "current_lgd_export_verified": False})
    return result


def geometry_checks(geometries, state_geometry, native_crs):
    """No simplification, snapping, buffering or validity repair. Areas are equal-area."""
    for geom in [*geometries, state_geometry]:
        if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
            raise ValueError("Invalid or empty polygon; source is not repaired")
    unique([g.wkb for g in geometries], "district geometries")
    projector = Transformer.from_crs(native_crs, CRS.from_user_input(AREA_CRS), always_xy=True).transform
    polygons = [transform(projector, g) for g in geometries]
    state = transform(projector, state_geometry)
    if not all(g.is_valid and not g.is_empty for g in [*polygons, state]):
        raise ValueError("Invalid projected polygon")
    union = unary_union(polygons)
    overlaps = [{"first_index": i, "second_index": j, "area_m2": a.intersection(b).area}
                for i, a in enumerate(polygons) for j, b in enumerate(polygons) if j > i
                and a.intersection(b).area > 0]
    return {"valid_polygons": len(polygons), "empty_polygons": 0,
            "area_crs": AREA_CRS, "district_areas_km2": [g.area / 1e6 for g in polygons],
            "union_area_km2": union.area / 1e6, "state_area_km2": state.area / 1e6,
            "positive_area_overlaps": overlaps, "pairwise_checks": len(polygons) * (len(polygons) - 1) // 2,
            "state_not_covered_m2": state.difference(union).area,
            "districts_outside_state_m2": union.difference(state).area,
            "sum_minus_union_m2_numerical_residual": sum(g.area for g in polygons) - union.area,
            "area_comparison_tolerance_m2": 1.0,
            "coverage_reference": "same SOI release state polygon; not independent ground truth",
            "analysis_dimensions": "2D; original PolygonZ coordinates retained in local subset"}


def source_geometry_report(district, state):
    if len(state["records"]) != 1 or not district["crs"].equals(state["crs"]):
        raise ValueError("State count or source CRS mismatch")
    return geometry_checks([shape(r["shape"].__geo_interface__) for r in district["records"]],
                           shape(state["records"][0]["shape"].__geo_interface__), district["crs"])


def write_subset(source, target):
    with shapefile.Writer(str(target), shapeType=source["shape_type"], encoding=source["encoding"]) as writer:
        writer.fields = source["fields"]
        for item in source["records"]:
            writer.record(*item["record"])
            writer.shape(item["shape"])  # Exact original coordinate arrays, including Z; no transform.
    for suffix in (".prj", ".cpg"):
        shutil.copyfile(source["path"].with_suffix(suffix), target.with_suffix(suffix))
    with shapefile.Reader(str(target), encoding=source["encoding"]) as reader:
        if reader.fields[1:] != source["fields"] or len(reader) != len(source["records"]):
            raise ValueError("Subset schema or record count changed")
        for saved, original in zip(reader.iterShapeRecords(), source["records"]):
            if list(saved.record) != original["record"] or any(
                getattr(saved.shape, attr, None) != getattr(original["shape"], attr, None)
                for attr in ("shapeType", "points", "parts", "z", "m")
            ):
                raise ValueError("Subset changed original coordinates or attributes")


def write_version(directory, district, state, report):
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError("Working version exists; no overwrite")
    source_geometry_report(district, state)  # Validate before creating any output.
    directory.mkdir(parents=True)
    write_subset(district, directory / "districts.shp")
    write_subset(state, directory / "state.shp")
    files = {p.name: fingerprint(p) for p in sorted(directory.iterdir()) if p.is_file()}
    manifest = {**report, "local_only_geometry": True, "files": files}
    with (directory / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
    return manifest


def validate_version(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if not manifest.get("local_only_geometry") or manifest.get("stage_1_complete") is not False:
        raise ValueError("Unreviewed working-version identity")
    expected = {f"{name}{suffix}" for name in ("districts", "state") for suffix in COMPONENTS}
    if set(manifest["files"]) != expected or {p.name for p in directory.iterdir()} != expected | {"manifest.json"}:
        raise ValueError("Unexpected working-version files")
    for name, saved in manifest["files"].items():
        if fingerprint(directory / name) != saved:
            raise ValueError(f"Working-version checksum mismatch: {name}")
    district = read_source(directory / "districts.shp", "STATE_UT", district=True)
    state = read_source(directory / "state.shp", "STATE")
    checks = source_geometry_report(district, state)
    if checks != manifest["geometry_validation"]:
        raise ValueError("Working-version geometry validation mismatch")
    identities = [(r["attributes"]["DISTRICT"], r["attributes"]["DIST_LGD"]) for r in district["records"]]
    if identities != [(r["district_name_original"], r["district_lgd_code_as_supplied_by_soi"])
                      for r in manifest["district_records"]]:
        raise ValueError("Working-version source identities mismatch")
    return checks


def build_report(district, state, metadata_zip, archive, nic_path):
    inventory = json.loads(nic_path.read_text())
    names = [r["district_name"] for r in inventory["records"]]
    checks = source_geometry_report(district, state)
    rows = [{"source_record_index": r["source_record_index"],
             "source_objectid": r["attributes"]["OBJECTID"],
             "district_name_original": r["attributes"]["DISTRICT"],
             "district_lgd_code_as_supplied_by_soi": r["attributes"]["DIST_LGD"],
             "state_lgd_code_as_supplied_by_soi": r["attributes"]["STATE_LGD"],
             "area_km2": checks["district_areas_km2"][i]}
            for i, r in enumerate(district["records"])]
    rows = reconcile(rows, names)
    book = metadata_cells(metadata_zip, "DISTRICT BOUNDARY.xlsx")
    state_book = metadata_cells(metadata_zip, "STATE BOUNDARY.xlsx")
    cells = book["cells"]
    if cells.get("B31") != "2025" or cells.get("B4") != "SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA":
        raise ValueError("Source edition changed; inspect before creating an ABDB2025 version")
    if "Karnataka" not in cells.get("B5", "") or "harmonized with ORGI in 2025" not in cells["B5"]:
        raise ValueError("Karnataka administrative reference requires explicit inspection")
    # Selected factual metadata with original cell locators; no full workbook reproduction.
    selected = ("B4", "B6", "B7", "B23", "B26", "B28", "B29", "B30", "B31", "B48", "B53", "B54", "B55")
    return {"version": VERSION, "inspected_at": datetime.now(timezone.utc).isoformat(),
            "stage_1_complete": False, "status": "verified_soi_source_not_current_lgd_reconciled",
            "sources": {"archive": {**fingerprint(archive), "url": ARCHIVE_URL, "original_retrieved_at": None},
                        "metadata_zip": {**fingerprint(metadata_zip), "url": METADATA_URL, "original_retrieved_at": None},
                        "district_components": [fingerprint(district["path"].with_suffix(s)) for s in COMPONENTS],
                        "state_components": [fingerprint(state["path"].with_suffix(s)) for s in COMPONENTS],
                        "nic_inventory": fingerprint(nic_path)},
            "metadata": {"district_workbook": {k: v for k, v in book.items() if k != "cells"},
                         "district_cells": {k: cells[k] for k in selected},
                         "state_workbook": {k: v for k, v in state_book.items() if k != "cells"},
                         "administrative_reference": "Karnataka harmonization year 2025; exact effective day unspecified",
                         "scale": "1:50000", "accuracy_status": "publisher-stated, not independently measured",
                         "publication_date": cells["B6"], "edition_year": cells["B31"]},
            "crs": {"actual_wkt": district["wkt"], "actual_authority": district["crs"].to_authority(),
                    "matches_metadata_epsg7755": district["crs"].equals(CRS.from_epsg(7755)),
                    "actual_operation_parameters": [{"name": p.name, "value": p.value, "unit": p.unit_name}
                                                    for p in district["crs"].coordinate_operation.params],
                    "epsg7755_operation_parameters": [{"name": p.name, "value": p.value, "unit": p.unit_name}
                                                      for p in CRS.from_epsg(7755).coordinate_operation.params],
                    "output_rule": "preserve actual .prj and native coordinates, never relabel EPSG:7755"},
            "original_district_fields": [[f[0], str(f[1]), f[2], f[3]] for f in district["fields"]],
            "original_state_fields": [[f[0], str(f[1]), f[2], f[3]] for f in state["fields"]],
            "national_district_record_count": district["national_record_count"],
            "karnataka_district_count": len(rows), "nic_district_count": len(names),
            "district_count_agrees_with_nic": len(rows) == len(names),
            "source_shape_type": district["shape_type"], "district_records": rows,
            "nic_exact_name_candidates": sum(r["nic_exact_name"] is not None for r in rows),
            "nic_unmatched_names": [n for n in names if n not in {r["nic_exact_name"] for r in rows}],
            "current_lgd_verified_identities": 0, "geometry_validation": checks,
            "limitations": ["Original retrieval dates unknown; archive/HTTP modification times are not administrative dates",
                            "LGD export absent; SOI supplied codes are not independently verified current LGD identities",
                            "Original legacy/transliterated names retained; no guessed letter replacements or aliases",
                            "R<managara source spelling retained; NIC Bengaluru South not automatically reconciled",
                            "Metadata EPSG assertion differs from actual shapefile WKT; publisher clarification needed"],
            "reuse": {"policy_url": POLICY_URL, "checked_on": "2026-10-04",
                      "status": "copyright; written SOI permission required for reproduction",
                      "geometry_publication_authorized": False,
                      "source_attribution": "Survey of India, Government of India",
                      "publication_scope": "processing code, tests, factual metadata and checksums only"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--official-checks", type=Path, help="Optional saved bounded official HTTP checks")
    for option in ("district", "state", "metadata-zip", "archive", "nic-inventory", "working-output", "metadata-output"):
        parser.add_argument(f"--{option}", type=Path)
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps(validate_version(args.validate_only), indent=2))
        return
    required = ("district", "state", "metadata_zip", "archive", "nic_inventory", "working_output", "metadata_output")
    if any(getattr(args, k) is None for k in required):
        parser.error("Explicit local inputs, new working-output directory and new metadata-output file required")
    if args.working_output.exists() or args.metadata_output.exists():
        raise FileExistsError("Output version exists; no overwrite")
    district = read_source(args.district, "STATE_UT", district=True)
    state = read_source(args.state, "STATE")
    report = build_report(district, state, args.metadata_zip, args.archive, args.nic_inventory)
    if args.official_checks:
        checks = json.loads(args.official_checks.read_text())
        if len(checks) != 2 or checks[0].get("url") != METADATA_URL or checks[1].get("url") != ARCHIVE_URL:
            raise ValueError("Unexpected official URL verification provenance")
        if (checks[0].get("method") != "GET" or checks[1].get("method") != "HEAD"
                or any(c.get("http_status") != 200 for c in checks)
                or checks[0].get("sha256") != digest(args.metadata_zip)):
            raise ValueError("Official metadata verification or archive availability failed")
        report["official_http_verification"] = checks
    local = write_version(args.working_output, district, state, report)
    validate_version(args.working_output)
    # Publish metadata only, never the geometry files themselves.
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    with args.metadata_output.open("x") as stream:
        json.dump(local, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"districts": report["karnataka_district_count"],
                      "nic_exact_name_candidates": report["nic_exact_name_candidates"],
                      "stage_1_complete": False, "working_output": str(args.working_output),
                      "metadata_output": str(args.metadata_output)}, indent=2))


if __name__ == "__main__":
    main()
