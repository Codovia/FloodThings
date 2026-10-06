#!/usr/bin/env python3
"""Offline, immutable hydrology foundation; public probes never imply full coverage.

PDF table caches and visually reviewed cells remain local. Station metadata,
forecast thresholds and measured observations have distinct source semantics.
No live requests occur during build/validate or module import.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/reference/stage4a_v1"
OUTPUT = ROOT / "data/working/karnataka_hydrology_stations_v1"
REFERENCE = ROOT / "data/reference/karnataka_hydrology_stations_v1"
VARIABLES = {"gauge_level", "discharge", "reservoir_inflow", "reservoir_outflow",
             "reservoir_storage", "reservoir_level", "rainfall", "sediment", "water_quality", "velocity"}
TYPES = {"G": ["gauge_level"], "GD": ["gauge_level", "discharge"],
         "GQ": ["gauge_level", "water_quality"],
         "GDQ": ["gauge_level", "discharge", "water_quality"],
         "GDS": ["gauge_level", "discharge", "sediment"],
         "GDSQ": ["gauge_level", "discharge", "sediment", "water_quality"]}
COORDINATES = {"verified_source_coordinate", "source_coordinate_conflict", "coordinate_missing",
               "geographic_assignment_unresolved"}
RELATIONSHIPS = {"same_river_or_basin_supported", "upstream_supported", "nearby_only", "relationship_unresolved"}
READINESS = {"measured_hydrology_ready", "station_registry_ready_data_access_partial",
             "station_registry_ready_data_access_blocked", "hydrology_foundation_incomplete"}
METHOD = {
    "identity": "Exact source codes/cells retained; visible PDF names separately reviewed, not geocoded or fuzzy matched",
    "coordinates": "Published decimal degrees N/E; datum unstated. WGS84 assumption only for local SOI2025 plausibility screening; no coordinate repair",
    "river_alignment": "Published river/basin and coarse official Krishna network map; no surveyed river-centreline or station entrance validation",
    "coverage": "Commissioning dates and catalogue partition labels are not verified continuous observation coverage",
    "availability": "No publication-time or zero-delay assumption; historical availability_semantics_unverified",
    "thresholds": "SOP levels in m, datum unstated; inflow table FRL/MWL/thresholds remain distinct from warning/danger levels",
    "table_vintages": "April2025 SOP: level/monitoring headers say flood season2025; inflow table header says flood season2024. Do not present either as current2026 operations",
    "publication": "Detailed station records, thresholds, source PDFs/HTML/API responses and SOI screening inputs stay local; code/schema/counts/checksums/provenance only",
    "nrsc": "machine_readable_reference_unavailable; no Stage3E5 services probed",
    "labels": None, "modelling": False,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def read(path):
    return json.loads(Path(path).read_bytes())


def compact(value):
    return "".join(value.split())


def coordinate_status(latitude, longitude, *, conflict=False, state_consistent=None):
    if latitude is None or longitude is None:
        return "coordinate_missing"
    require(not isinstance(latitude, bool) and not isinstance(longitude, bool), "Boolean coordinate")
    require(math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90
            and -180 <= longitude <= 180, "Invalid source coordinate")
    if conflict:
        return "source_coordinate_conflict"
    if state_consistent is False:
        return "geographic_assignment_unresolved"
    return "verified_source_coordinate"


def parse_metadata(tables, reviewed):
    """Retain all raw cells. Reviewed display cells correct PDF encoding artefacts only."""
    rows = []
    for table in tables:
        for cells in table["rows"]:
            if len(cells) != 12 or cells[2] not in {"Karnataka", "Maharashtra"}:
                continue
            raw_id = cells[11] or ""
            # A leading backtick/spaced glyphs are explicitly reviewed, never an inferred code.
            key = compact(raw_id).lstrip("`")
            if key not in reviewed:
                require(cells[2] != "Karnataka", "Unreviewed Karnataka station")
                continue
            review = reviewed[key]
            require(review["page"] == table["page"] and review["source_id_cell"] == raw_id
                    and review["source_name_cell"] == cells[1], "Review does not match original cells")
            require(re.fullmatch(r"CW1[A-Z]{3}\d{6}", key), "Malformed source site code")
            require(cells[5] in TYPES, "Unrecognized source station type")
            lat, lon = float(compact(cells[7])), float(compact(cells[8]))
            coordinate_status(lat, lon)
            rows.append({"source_record_key": key, "source_station_id": key,
                         "official_name": review["visible_name"], "project_alias": None,
                         "source_state": cells[2], "source_district": cells[3],
                         "source_river": cells[4], "source_basin": review["basin"],
                         "source_sub_basin": None, "source_type": cells[5],
                         "variables": deepcopy(TYPES[cells[5]]),
                         "variable_units": {v: None for v in TYPES[cells[5]]},
                         "latitude": lat, "longitude": lon,
                         "coordinate_status": "verified_source_coordinate",
                         "coordinate_datum": "not_documented", "coordinate_precision": "3 decimal degrees",
                         "source_purpose": cells[10], "source_start_dates_cell": cells[6],
                         "temporal_coverage": {"earliest_verified_observation": None,
                                               "latest_verified_observation": None,
                                               "continuity": "unverified", "missing_periods": "unknown"},
                         "source_page": table["page"], "source_reference_date": "2025-01-01",
                         "publication_edition": "April 2025", "source_cells": deepcopy(cells),
                         "upstream_context": review.get("upstream_context")})
    validate_registry(rows)
    require(set(reviewed) == {r["source_station_id"] for r in rows}, "Missing reviewed source record")
    return sorted(rows, key=lambda r: r["source_record_key"])


def metadata_pdf_tables(pdf_path, pages):
    """Optional pdfplumber0.11.9 dependency; returns caches without writing PDFs."""
    import pdfplumber
    require(pdfplumber.__version__ == "0.11.9", "Use the declared table parser version")
    require(len(pages) <= 20 and len(set(pages)) == len(pages), "Bound the inspected PDF pages")
    tables = []
    with pdfplumber.open(pdf_path) as doc:
        for number in pages:
            require(1 <= number <= len(doc.pages), "Invalid source PDF page")
            for table in doc.pages[number-1].extract_tables():
                if any(c and "SITE CODE" in c for c in table[0]):
                    tables.append({"page": number, "bbox": None, "rows": table})
    return tables


def sop_pdf_rows(pdf_path, layouts):
    """Poppler XML in memory; original source and completed outputs never rewritten."""
    result = subprocess.run(["pdftotext", "-bbox-layout", str(pdf_path), "-"],
                            check=True, capture_output=True, timeout=60)
    return parse_bbox_rows(result.stdout, layouts)


def parse_bbox_rows(xml_bytes, layouts):
    """Fixed published table columns, actual serial-row centres; no OCR/value inference.

    Keep empty numeric cells empty. Ordinals are document row identifiers, not
    CWC station IDs. Layouts are explicit for the inspected SOP edition.
    """
    require(b"<!ENTITY" not in xml_bytes.upper() and b"<!DOCTYPE" not in xml_bytes.upper().replace(b'<!DOCTYPE HTML', b''),
            "Unsafe XML")
    pages = ET.fromstring(xml_bytes).findall(".//{*}page")
    result = []
    for layout in layouts:
        words = [{"text": w.text or "", "x": float(w.attrib["xMin"]),
                  "y": (float(w.attrib["yMin"]) + float(w.attrib["yMax"])) / 2}
                 for w in pages[layout["page"] - 1].findall(".//{*}word")]
        edges = layout["columns"]
        serials = sorted([w for w in words if edges[0] <= w["x"] < edges[1]
                          and re.fullmatch(r"\d+", w["text"])
                          and layout["first"] <= int(w["text"]) <= layout["last"]], key=lambda w: w["y"])
        require(len(serials) == layout["last"] - layout["first"] + 1, "Missing SOP serial row")
        for i, serial in enumerate(serials):
            lo = (serials[i-1]["y"] + serial["y"])/2 if i else serial["y"] - 12
            hi = (serials[i+1]["y"] + serial["y"])/2 if i+1 < len(serials) else serial["y"] + 12
            cells = []
            for x1, x2 in zip(edges, edges[1:]):
                selected = [w for w in words if lo <= w["y"] < hi and x1 <= w["x"] < x2]
                selected.sort(key=lambda w: (round(w["y"]/3), w["x"]))
                cells.append(" ".join(w["text"] for w in selected))
            require(cells[0] == serial["text"], "SOP row association failed")
            result.append({"page": layout["page"], "kind": layout["kind"],
                           "source_ordinal": serial["text"], "cells": cells})
    return result


def parse_sop(rows):
    result = []
    for row in rows:
        c = row["cells"]
        if c[3] != "Karnataka":
            continue
        inflow = row["kind"] == "inflow_forecast"
        r = {"source_record_key": f'sop_april2025:{row["kind"]}:{c[0]}',
             "source_station_id": None, "source_ordinal": c[0], "official_name": c[2],
             "source_state": c[3], "source_district": c[4], "source_river": c[1],
             "source_page": row["page"], "status": row["kind"], "source_cells": c,
             "publication_edition": "April2025 SOP",
             "source_table_reference": "flood season2024" if inflow else "flood season2025",
             "warning_level": None, "danger_level": None, "highest_flood_level": None,
             "highest_flood_level_date_cell": None, "datum": "not_documented", "units": "m"}
        if inflow:
            r.update(full_reservoir_level_cell=c[5], maximum_water_level_cell=c[6],
                     inflow_threshold_cell=c[7], inflow_threshold_units="cumec",
                     actual_reservoir_observations_retrieved=False)
        else:
            for field, index in [("warning_level",5), ("danger_level",6), ("highest_flood_level",7)]:
                r[field] = float(c[index]) if c[index] else None
            r["highest_flood_level_date_cell"] = c[8] or None
        r["quality_flags"] = threshold_flags(r)
        result.append(r)
    require(len({r["source_record_key"] for r in result}) == len(result), "Duplicate SOP source row")
    return result


def threshold_flags(row):
    flags = []
    for field in ["warning_level", "danger_level", "highest_flood_level"]:
        value = row.get(field)
        require(value is None or math.isfinite(value), "Nonfinite threshold")
    warning, danger, highest = (row.get(k) for k in ["warning_level", "danger_level", "highest_flood_level"])
    if warning is not None and danger is not None and warning >= danger:
        flags.append("warning_not_below_danger; source_value_retained")
    if highest is not None and danger is not None and highest < danger:
        flags.append("recorded_hfl_below_danger; source_value_retained")
    flags.append("vertical_datum_unverified")
    return flags


def validate_registry(rows):
    seen = {}
    for r in rows:
        require(r.get("source_station_id") and r.get("official_name"), "Missing source identity")
        key = r["source_station_id"]
        if key in seen:
            require(seen[key] == r, "Conflicting duplicate station ID")
            raise ValueError("Duplicate station ID")
        seen[key] = r
        require(set(r["variables"]) <= VARIABLES and len(set(r["variables"])) == len(r["variables"]), "Invalid variable vocabulary")
        coordinate_status(r.get("latitude"), r.get("longitude"))
        require(r["coordinate_status"] in COORDINATES, "Unknown coordinate status")
        coverage = r["temporal_coverage"]
        first, last = coverage["earliest_verified_observation"], coverage["latest_verified_observation"]
        require(first is None or last is None or first <= last, "Reversed temporal coverage")
    return True


def check_geography(rows, directory):
    """Local screening in the supplied SOI CRS. Nothing is sent to a service."""
    import shapefile
    from pyproj import Transformer
    from shapely.geometry import Point, shape
    directory = Path(directory)
    state = shapefile.Reader(str(directory / "state.shp"))
    districts = shapefile.Reader(str(directory / "districts.shp"))
    projection = (directory / "state.prj").read_text()
    tf = Transformer.from_crs(4326, projection, always_xy=True)
    area = shape(state.shape(0).__geo_interface__)
    polygons = [(str(v.record.as_dict()["DISTRICT"]), shape(v.shape.__geo_interface__))
                for v in districts.iterShapeRecords()]
    require(area.is_valid and all(p.is_valid for _,p in polygons), "Invalid screening geometry")
    result = deepcopy(rows)
    for r in result:
        point = Point(*tf.transform(r["longitude"], r["latitude"]))
        inside = area.covers(point)
        r["geographic_screening"] = {"state_contains_point": inside,
                                    "containing_soi2025_district_names": [n for n,p in polygons if p.covers(point)],
                                    "district_identity_match": "not_inferred_from_names",
                                    "datum_assumption": "WGS84 solely for screening; CWC datum unknown",
                                    "river_proximity_m": None}
        r["coordinate_status"] = coordinate_status(r["latitude"], r["longitude"],
                                                   state_consistent=inside if r["source_state"] == "Karnataka" else None)
    return result


def parse_response(body, max_rows):
    response = json.loads(body)
    require(response.get("success") is True, "Source application failure")
    require(isinstance(response.get("result", {}).get("records"), list), "Missing source records")
    require(len(response["result"]["records"]) <= max_rows, "Source response exceeds row bound")
    return response["result"]


def readiness(station_count, pilot_counts, public_history_probe_count):
    require(station_count >= 0 and public_history_probe_count >= 0
            and all(v >= 0 for v in pilot_counts), "Invalid coverage counts")
    if not station_count:
        return "hydrology_foundation_incomplete"
    if pilot_counts and all(pilot_counts):
        return "measured_hydrology_ready"
    if any(pilot_counts) or public_history_probe_count > 0:
        return "station_registry_ready_data_access_partial"
    return "station_registry_ready_data_access_blocked"


def normalize_observation(record, variable, value_field, units, *, station_id, source,
                          start, end, availability_time=None, availability_evidence=None):
    """Units are publisher-supplied, not inferred. Keep datum/time zone unknown."""
    require(variable in VARIABLES and source["kind"] == "measured", "Not an allowed measured variable")
    require(units and value_field in record, "Missing source units/field")
    require(not isinstance(record[value_field], bool), "Boolean measured value")
    when = datetime.strptime(record["Data Acquisition Time"], "%d-%m-%Y %H:%M")
    require(start <= when.date().isoformat() <= end, "Observation outside requested event context")
    value = None if record[value_field] in {None, "", "-"} else float(record[value_field])
    require(value is None or math.isfinite(value), "Nonfinite observed value")
    if variable in {"discharge", "reservoir_inflow", "reservoir_outflow", "reservoir_storage"}:
        require(value is None or value >= 0, "Negative flow/storage")
    require(availability_time is None or availability_evidence, "Availability time lacks evidence")
    return {"source_station_id": station_id, "source_station_name": record["Station"],
            "observation_time": when.isoformat(), "source_observation_time": record["Data Acquisition Time"],
            "observation_timezone": "not_documented", "availability_time": availability_time,
            "availability_status": "availability_time_verified" if availability_time else "availability_semantics_unverified",
            "availability_evidence": availability_evidence, "variable": variable, "value": value,
            "units": units, "datum": "not_documented", "kind": "measured", "source": deepcopy(source),
            "source_record": deepcopy(record)}


def validate_relationship(row):
    require(row["relationship"] in RELATIONSHIPS, "Unknown event-station relationship")
    require(row["event_start"] <= row["event_end"], "Reversed event interval")
    require(row.get("event_source") and row.get("station_source"), "Missing relationship evidence")
    require("observation_time" not in row and not row.get("daily_flood_label"), "Documentary window is not an observation/label")
    return True


def file_record(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path), "bytes": path.stat().st_size}


def summarize(stations, sop, pilot, public_history_probe_count=0):
    ka = [r for r in stations if r["source_state"] == "Karnataka"]
    return {"karnataka_metadata_stations": len(ka),
            "selected_upstream_metadata_stations": len(stations) - len(ka),
            "source_station_types": dict(sorted(Counter(r["source_type"] for r in ka).items())),
            "metadata_gauge_configured": sum("gauge_level" in r["variables"] for r in ka),
            "metadata_discharge_configured": sum("discharge" in r["variables"] for r in ka),
            "metadata_purpose_codes": dict(sorted(Counter(r["source_purpose"] for r in ka).items())),
            "basins": dict(sorted(Counter(r["source_basin"] for r in ka).items())),
            "coordinate_statuses": dict(sorted(Counter(r["coordinate_status"] for r in ka).items())),
            "sop_forecast_stations": sum(r["status"] in {"level_forecast", "inflow_forecast"} for r in sop),
            "sop_level_forecast_stations": sum(r["status"] == "level_forecast" for r in sop),
            "sop_inflow_forecast_stations": sum(r["status"] == "inflow_forecast" for r in sop),
            "sop_monitoring_only_stations": sum(r["status"] == "monitoring_only" for r in sop),
            "sop_stations_with_warning": sum(r["warning_level"] is not None for r in sop),
            "sop_stations_with_danger": sum(r["danger_level"] is not None for r in sop),
            "sop_stations_with_hfl": sum(r["highest_flood_level"] is not None for r in sop),
            "pilot_stations": len(pilot), "pilot_observations": sum(r["observations_retrieved"] for r in pilot),
            "public_access_probe_observations_outside_pilot": public_history_probe_count,
            "readiness": readiness(len(ka), [r["observations_retrieved"] for r in pilot], public_history_probe_count)}


def assemble(raw=RAW):
    raw = Path(raw)
    reviewed = read(raw / "reviewed_station_cells.json")
    stations = parse_metadata(read(raw / "cwc_metadata_tables.json"), reviewed)
    stations = check_geography(stations, ROOT / "data/working/karnataka_soi_abdb2025_v1")
    sop = parse_sop(read(raw / "cwc_sop_rows.json"))
    require(sop_pdf_rows(raw / "cwc_sop_april2025.pdf", read(raw / "cwc_sop_layouts.json"))
            == read(raw / "cwc_sop_rows.json"), "Official SOP-to-cache reproduction failed")
    pilot = read(raw / "pilot_availability.json")
    for r in pilot:
        require(r["source_station_id"] in reviewed, "Unverified pilot station")
        validate_relationship(r["event_relationship"])
        for probe in r["probes"]:
            require(digest(ROOT / probe["file"]) == probe["sha256"], "Probe checksum mismatch")
            result = parse_response((ROOT / probe["file"]).read_bytes(), 32)
            require(not result["records"], "Nonempty response needs observation validation before freeze")
        require(r["observations_retrieved"] == 0 and r["status"] == "measured_historical_data_access_unavailable", "Unverified pilot status")
    sources = read(raw / "source_index.json")
    for s in sources:
        require(digest(ROOT / s["file"]) == s["sha256"], "Source checksum mismatch")
    probe = parse_response((raw / "nwdp_discharge_one_row.json").read_bytes(), 1)
    require(len(probe["records"]) == 1, "Expected actual measured access probe")
    record = probe["records"][0]
    field = "Manual Daily River Water Discharge (m3/sec)"
    require(field in record and math.isfinite(float(record[field])) and float(record[field]) >= 0,
            "Unusable source discharge access probe")
    datetime.strptime(record["Data Acquisition Time"], "%d-%m-%Y %H:%M")
    availability = []
    for r in stations:
        availability.append({"source_station_id": r["source_station_id"], "source": "CWC metadata January2025",
                             "variables_configured": r["variables"], "units": r["variable_units"],
                             "earliest_verified_observation": None, "latest_verified_observation": None,
                             "source_start_dates_cell": r["source_start_dates_cell"],
                             "frequency": "station-specific verified series unavailable; SOP generic manual discharge daily/gauge hourly during monsoon",
                             "missing_periods": "unknown", "provisional_final_status": "not_documented",
                             "access_method": "official publication and public NWIC catalogue",
                             "retrieval_status": "station_metadata_retrieved; history_not_established"})
    return {"station_registry.json": stations, "flood_station_inventory.json": sop,
            "source_availability.json": {"stations": availability, "pilot": pilot,
                                         "public_access_probe_observations_outside_pilot": len(probe["records"]),
                                         "sources": sources, "interpretation": METHOD["coverage"]}}


def freeze(output=OUTPUT, raw=RAW, *, created_at=None):
    output = Path(output)
    require(not output.exists(), "Immutable output already exists")
    artifacts = assemble(raw)
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    files = {name: {"sha256": hashlib.sha256(json_bytes(value)).hexdigest(), "bytes": len(json_bytes(value))}
             for name, value in artifacts.items()}
    manifest = {"version": "karnataka_hydrology_stations_v1", "created_at": created_at, "method": METHOD,
                "files": files, "sources": artifacts["source_availability.json"]["sources"],
                "summary": summarize(artifacts["station_registry.json"], artifacts["flood_station_inventory.json"],
                                     artifacts["source_availability.json"]["pilot"],
                                     artifacts["source_availability.json"]["public_access_probe_observations_outside_pilot"]),
                "inputs": [file_record(p) for p in sorted(Path(raw).iterdir()) if p.is_file()],
                "processing_code": file_record(Path(__file__)),
                "geometry_screening_inputs": [file_record(p) for p in sorted((ROOT / "data/working/karnataka_soi_abdb2025_v1").iterdir()) if p.is_file()],
                "pilot_observation_file": None}
    require(manifest["summary"]["readiness"] in READINESS, "Invalid readiness")
    output.mkdir(parents=True)
    for name, value in artifacts.items():
        (output / name).write_bytes(json_bytes(value))
    (output / "manifest.json").write_bytes(json_bytes(manifest))
    return validate(output)


def validate(output=OUTPUT):
    """Read only: reproduce all station records and counters from retained inputs."""
    output = Path(output)
    manifest = read(output / "manifest.json")
    for name, expected in manifest["files"].items():
        require(Path(name).name == name, "Unsafe artifact path")
        p = output / name
        require(digest(p) == expected["sha256"] and p.stat().st_size == expected["bytes"], "Output checksum mismatch")
    for s in manifest["inputs"] + manifest["geometry_screening_inputs"] + [manifest["processing_code"]]:
        p = ROOT / s["path"]
        require(digest(p) == s["sha256"] and p.stat().st_size == s["bytes"], "Input integrity mismatch")
    artifacts = assemble(Path(ROOT / manifest["inputs"][0]["path"]).parent)
    for name, value in artifacts.items():
        require(json_bytes(value) == (output / name).read_bytes(), "Offline source-to-registry reproduction failed")
    summary = summarize(artifacts["station_registry.json"], artifacts["flood_station_inventory.json"], artifacts["source_availability.json"]["pilot"], artifacts["source_availability.json"]["public_access_probe_observations_outside_pilot"])
    require(summary == manifest["summary"], "Summary mismatch")
    return summary


def public_manifest(output=OUTPUT):
    """Explicit allowlist: no source bodies, coordinates, station rows or observation values."""
    m = read(Path(output) / "manifest.json")
    allowed = {k: m[k] for k in ["version", "created_at", "method", "summary", "files", "processing_code"]}
    allowed["local_manifest_sha256"] = digest(Path(output) / "manifest.json")
    allowed["sources"] = [{k: s.get(k) for k in ["source_url", "retrieved_at", "sha256", "bytes", "status", "http_status", "edition", "access", "reuse", "diagnostic"]} for s in m["sources"]]
    allowed["schema"] = {"station_registry": "Exact CWC source ID, visible name/raw cells, published river/basin/state/district/type/dates/coordinates, units unknown where absent, screening flags",
                         "flood_station_inventory": "SOP ordinal (not station ID), level/inflow/monitoring status, original source values; FRL/MWL/inflow not warning/danger",
                         "source_availability": "Configured variables versus actual access/verified temporal coverage; three bounded pilot results and independent event windows"}
    return allowed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "validate"])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--raw", type=Path, default=RAW)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output, args.raw) if args.command == "build" else validate(args.output), indent=2))
