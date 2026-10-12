#!/usr/bin/env python3
"""Offline Phase 12D review discovery. No download, geometry export or model fit.

Only the frozen Karnataka subset is read; complete-link review groups are NOT
certified independent physical events. All record-level products remain local.
"""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sqlite3

import shapely
from shapely.geometry import Polygon, shape
from shapely.ops import transform

from audit_groundsource_karnataka import load_boundaries, fingerprint
from build_flood_outcome_foundation import checked_file

ROOT = Path(__file__).resolve().parents[1]
INPUT = Path("data/working/karnataka_groundsource_2026_v1")
OUTPUT = Path("data/working/karnataka_verified_event_pilot_v1")
PROTOCOL = Path("docs/phase12d/target_protocol.json")
RULES = {"max_area_km2": 10, "max_report_days": 3, "max_gap_days": 1,
         "max_start_difference_days": 2, "max_combined_days": 7,
         "min_iou": 0.3, "min_smaller_overlap": 0.5, "max_area_ratio": 4,
         "max_centroid_distance_m": 2000, "comparison_cap": 250000,
         "pilot_groups_per_context": 4}


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + "\n"


def csv_text(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def bounded_path(root, reference):
    if not isinstance(reference, str) or not reference:
        raise ValueError("missing file reference")
    path = (root / reference).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("source absent or outside root")
    return path


def verify_file(root, reference, digest):
    path = bounded_path(root, reference)
    if fingerprint(path)["sha256"] != digest:
        raise ValueError("source checksum mismatch: " + reference)
    return path


def geojson_geometry(value):
    if value.get("type") == "FeatureCollection":
        if len(value["features"]) != 1:
            raise ValueError("reference must contain exactly one geographic feature")
        value = value["features"][0]
    return shape(value["geometry"] if value.get("type") == "Feature" else value)


def evaluate_event_review(row, root):
    """Consistency gate for externally adjudicated GROUP identity, not labels.

    Documentary regional corroboration does not approve a news group. We never
    manufacture approval receipts. Authorship/independence require human review.
    """
    blockers = []
    try:
        receipt = json.loads(verify_file(root, row["receipt_reference"], row["receipt_sha256"]).read_text())
        bound = ("group_id", "source_uuids", "original_geometry_hashes", "verified_location_reference", "verified_location_sha256",
                 "verified_start", "verified_end", "independent_sources", "outcome", "protocol_id")
        if receipt.get("decision") != "APPROVED" or any(receipt.get(k) != row.get(k) for k in bound):
            raise ValueError("approval is absent or group/source/location/time binding differs")
        if not receipt.get("independent_reviewer") or not receipt.get("reviewed_at"):
            raise ValueError("independent reviewer/time absent")
        if (not row.get("source_uuids") or len(set(row["source_uuids"])) != len(row["source_uuids"])
                or len(row["source_uuids"]) != len(row.get("original_geometry_hashes", []))):
            raise ValueError("original membership absent")
        if row.get("outcome") != "FLOOD_CONFIRMED":
            raise ValueError("physical flood outcome not confirmed")
        a, b = dt.date.fromisoformat(row["verified_start"]), dt.date.fromisoformat(row["verified_end"])
        if b < a:
            raise ValueError("reversed verified dates")
        if len({s["source_family"] for s in row["independent_sources"]}) < 2:
            raise ValueError("two independently reviewed source families required for this pilot")
        if len({s["sha256"] for s in row["independent_sources"]}) != len(row["independent_sources"]):
            raise ValueError("repeated source bytes cannot count as independent evidence")
        for field in ("group_id", "protocol_id", "verified_location_reference"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("missing " + field)
        import re
        if any(not isinstance(v, str) or not v.strip() for v in row["source_uuids"]):
            raise ValueError("invalid original UUID")
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in row["original_geometry_hashes"]):
            raise ValueError("invalid original geometry checksum")
        for source in row["independent_sources"]:
            verify_file(root, source["reference"], source["sha256"])
        location = geojson_geometry(json.loads(verify_file(root, row["verified_location_reference"], row["verified_location_sha256"]).read_text()))
        if location.is_empty or not location.is_valid:
            raise ValueError("verified geographic support invalid")
    except (KeyError, ValueError, TypeError, OSError, AttributeError, shapely.errors.ShapelyError) as error:
        blockers.append(str(error))
    return {"group_id": row.get("group_id"), "verified_group": not blockers,
            "outcome": "FLOOD_CONFIRMED" if not blockers else "UNKNOWN", "blockers": blockers,
            "status": "CONSISTENCY_GATE_REQUIRES_EXTERNAL_SCIENTIFIC_ADJUDICATION"}


def evaluate_window_observation(row, root, protocol):
    """Fail-closed daily outcome gate; a dry acquisition is never a daily dry label."""
    blockers = []
    try:
        if protocol.get("review_status") != "APPROVED" or protocol.get("training_authorized") is not True:
            raise ValueError("target protocol not independently approved")
        approval = json.loads(verify_file(root, protocol["approval_reference"], protocol["approval_sha256"]).read_text())
        body = {k: v for k, v in protocol.items() if k not in ("approval_reference", "approval_sha256")}
        if approval.get("decision") != "APPROVED" or approval.get("protocol") != body or not approval.get("independent_reviewer"):
            raise ValueError("independent protocol approval not bound to this protocol")
        receipt = json.loads(verify_file(root, row["receipt_reference"], row["receipt_sha256"]).read_text())
        body = {k: v for k, v in row.items() if k not in ("receipt_reference", "receipt_sha256")}
        if receipt.get("decision") != "APPROVED" or receipt.get("observation") != body or not receipt.get("independent_reviewer"):
            raise ValueError("independent observation approval not bound to exact evidence")
        if row["protocol_id"] != protocol["protocol_id"] or row["source_role"] != "OBSERVED_CLASSIFICATION":
            raise ValueError("protocol/source role mismatch")
        if protocol["geographic_unit"].get("cell_side_m") != 250 or protocol["geographic_unit"].get("grid_origin_m") != [0, 0]:
            raise ValueError("this validator supports only the specified v1 grid")
        if (protocol.get("horizon_hours") != 24 or protocol.get("minimum_contiguous_patch_area_m2") != 2500
                or protocol.get("issue_clock_utc") != "00:00:00"):
            raise ValueError("this validator supports only the specified v1 target definition")
        verify_file(root, row["source_reference"], row["source_sha256"])
        verify_file(root, row["independent_reference"], row["independent_reference_sha256"])
        if row["source_sha256"] == row["independent_reference_sha256"]:
            raise ValueError("reference is not independent of source")
        geometry_path = verify_file(root, row["unit_reference"], row["unit_sha256"])
        unit = shape(json.loads(geometry_path.read_text()))
        domain_path = verify_file(root, protocol["geographic_unit"]["initial_domain_reference"],
                                  protocol["geographic_unit"]["initial_domain_sha256"])
        # Domain is WGS84 GeoJSON; units are explicitly UTM geometry objects.
        from pyproj import Transformer
        domain_json = json.loads(domain_path.read_text())
        domain = geojson_geometry(domain_json)
        domain = transform(Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform, domain)
        x0, y0, x1, y1 = unit.bounds
        if row["unit_crs"] != "EPSG:32643" or x1-x0 != 250 or y1-y0 != 250 or x0 % 250 or y0 % 250:
            raise ValueError("unit not a frozen 250m origin-aligned target cell")
        if not unit.equals(shapely.box(x0, y0, x1, y1)) or not domain.covers(unit):
            raise ValueError("unit invalid or outside frozen target domain")
        issue = dt.datetime.fromisoformat(row["issue_time"])
        start, end = (dt.datetime.fromisoformat(row[k]) for k in ("target_start", "target_end"))
        if any(t.tzinfo is None or t.utcoffset() != dt.timedelta(0) for t in (issue, start, end)):
            raise ValueError("UTC timestamps required")
        if issue != start or issue.time().replace(tzinfo=None) != dt.time(0) or end-start != dt.timedelta(hours=24):
            raise ValueError("issue/window differs from daily target")
        for field in ("quality_approved", "permanence_approved", "detection_limits_approved", "rights_approved", "event_identity_approved"):
            if row.get(field) is not True:
                raise ValueError("unapproved " + field)
        if row.get("outcome") == "POSITIVE":
            acquisition = dt.datetime.fromisoformat(row["acquisition_time"])
            if acquisition.tzinfo is None or not start <= acquisition < end:
                raise ValueError("acquisition outside target interval or unknown timezone")
            patch = shape(json.loads(verify_file(root, row["patch_reference"], row["patch_sha256"]).read_text()))
            if patch.geom_type != "Polygon" or not patch.is_valid or not unit.covers(patch) or patch.area < 2500:
                raise ValueError("temporary-water patch fails area/contiguity/unit gate")
        elif row.get("outcome") == "NEGATIVE":
            coverage = row.get("observation_process", {})
            if not (coverage.get("continuous_full_interval") is True and coverage.get("complete_unit") is True
                    and coverage.get("capable_of_target_detection") is True
                    and coverage.get("start") == row["target_start"] and coverage.get("end") == row["target_end"]
                    and coverage.get("unit_sha256") == row["unit_sha256"]):
                raise ValueError("complete same-unit full-interval negative observation absent")
            verify_file(root, coverage["reference"], coverage["sha256"])
        else:
            raise ValueError("unresolved observed outcome")
    except (KeyError, TypeError, ValueError, OSError, AttributeError, shapely.errors.ShapelyError) as error:
        blockers.append(str(error))
    return {"outcome": row.get("outcome") if not blockers else "UNKNOWN", "eligible": not blockers,
            "blockers": blockers, "status": "CONSISTENCY_GATE_NOT_AUTOMATED_CERTIFICATION"}


def groupable(row):
    return bool(row.get("single_district_screening_usable") and row["projected_polygon_area_km2"] > 0
                and row["projected_polygon_area_km2"] <= RULES["max_area_km2"]
                and row["reported_interval_days_inclusive_assumption"] <= RULES["max_report_days"])


def near_dates(a, b):
    return max(a["start"], b["start"]) <= min(a["end"], b["end"]) + dt.timedelta(days=RULES["max_gap_days"])


def compatible(a, b, intersection):
    pa, pb = a["payload"], b["payload"]
    aa, ab = a["geometry"].area, b["geometry"].area
    return bool(groupable(pa) and groupable(pb) and pa["definite_district_id"] == pb["definite_district_id"]
                and near_dates(a, b) and abs((a["start"]-b["start"]).days) <= RULES["max_start_difference_days"]
                and (max(a["end"], b["end"])-min(a["start"], b["start"])).days+1 <= RULES["max_combined_days"]
                and intersection/(aa+ab-intersection) >= RULES["min_iou"]
                and intersection/min(aa, ab) >= RULES["min_smaller_overlap"]
                and max(aa, ab)/min(aa, ab) <= RULES["max_area_ratio"]
                and a["geometry"].centroid.distance(b["geometry"].centroid) <= RULES["max_centroid_distance_m"])


def cluster(records):
    """Deterministic complete-link grouping; never union overlapping polygons."""
    records = sorted(records, key=lambda r: r["ordinal"])
    tree = shapely.STRtree([r["geometry"] for r in records])
    edges, pairs, comparisons = defaultdict(set), [], 0
    for i, a in enumerate(records):
        for j in sorted(int(v) for v in tree.query(a["geometry"]) if int(v) > i):
            b = records[j]
            if not near_dates(a, b):
                continue
            comparisons += 1
            if comparisons > RULES["comparison_cap"]:
                raise ValueError("comparison budget exceeded; no complete version may be published")
            intersection = a["geometry"].intersection(b["geometry"]).area
            if intersection <= 0:
                continue
            accepted = compatible(a, b, intersection)
            pairs.append((i, j, accepted))
            if accepted:
                edges[i].add(j)
                edges[j].add(i)
    groups, assigned, alternatives = [], {}, {}
    for i in range(len(records)):
        nearby = {assigned[j] for j in edges[i] if j in assigned}
        eligible = sorted(g for g in nearby if all(j in edges[i] for j in groups[g]))
        if len(eligible) == 1:
            g = eligible[0]
            groups[g].append(i)
        else:
            g = len(groups)
            groups.append([i])
            if len(eligible) > 1:
                alternatives[g] = eligible
        assigned[i] = g
    # Date rules must also hold across the entire complete-link group.
    for members in groups:
        if len(members) > 1 and (max(records[i]["end"] for i in members)-min(records[i]["start"] for i in members)).days+1 > RULES["max_combined_days"]:
            raise ValueError("group temporal span invariant failed")
    return records, groups, assigned, pairs, alternatives, comparisons


SOURCE_FACTS = [
    {"id": "mha-2020", "url": "https://ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=NEW308",
     "publisher": "Ministry of Home Affairs / National Disaster Management Division", "family": "OFFICIAL_STATE_REPORT",
     "pages": [1, 5, 6], "document_date": "2020-09-22", "evidence_date": "2020-09-21",
     "type": "REGIONAL_RESPONSE_CONTEXT", "finding": "Udupi named in affected coastal districts and rescue response; enclosure received September 21, not a new September 22 observation",
     "limits": "Flood/heavy-rainfall regional report; exact Udupi flood footprint, onset and each candidate association UNKNOWN; coastal totals not assigned to Udupi"},
    {"id": "mha-2021", "url": "https://ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=D322",
     "publisher": "Ministry of Home Affairs / National Disaster Management Division", "family": "OFFICIAL_STATE_REPORT",
     "pages": [1, 2, 3], "document_date": "2021-07-27", "evidence_date": "2021-07-27",
     "type": "REGIONAL_FLOOD_OUTCOME", "finding": "Karnataka flood section reports villages flooded along rivers in Belagavi, Bagalkot and Gadag; attributed to Upper Krishna reservoir discharge",
     "limits": "Regional event evidence, no exact cell geometry or onset; mechanism is official reported context, not a verified mechanism for each news group"},
    {"id": "nrsc-2021-26", "url": "https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/Karnataka_floods_26jul_VAP_tile1.pdf",
     "publisher": "National Remote Sensing Centre / ISRO", "family": "OFFICIAL_REMOTE_SENSING",
     "pages": [1], "document_date": "2021-07-29", "evidence_date": "2021-07-26",
     "type": "SATELLITE_DOCUMENTARY_INUNDATION", "sensor": "WorldView-3", "map_id": "2021/01",
     "finding": "Official map labels inundation around Hulagabali/Halyal/Sankaratti in parts of Belgaum",
     "limits": "Acquisition date only; cloud occlusion, no validated target-grid mask, for-official-use notice and external imagery rights"},
    {"id": "nrsc-2021-28", "url": "https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/Maharashtra_floods_28jul_VAP_tile6.pdf",
     "publisher": "National Remote Sensing Centre / ISRO", "family": "OFFICIAL_REMOTE_SENSING",
     "pages": [1], "document_date": "2021-07-29", "evidence_date": "2021-07-28",
     "type": "SATELLITE_DOCUMENTARY_INUNDATION", "sensor": "Resourcesat-2A LISS-III", "map_id": "2021/06",
     "finding": "Official inundation map with flood annotations in Maharashtra/Karnataka near Hulagabali and Kudachi",
     "limits": "Acquisition date only; clouds, map viewport is not flood extent, no validated target-grid mask; for official use"}
]


def receipts(root):
    results = []
    for fact in SOURCE_FACTS:
        path = root / "data/raw/flood_event_pilot_phase12d_v1" / (fact["id"] + ".pdf")
        headers = path.with_suffix(".headers").read_text().splitlines()
        status = [v for v in headers if v.startswith("HTTP/")][-1]
        if " 200" not in status or not path.read_bytes().startswith(b"%PDF-"):
            raise ValueError("unverified PDF response")
        result = dict(fact, reference=str(path.relative_to(root)), **fingerprint(path),
                      inspection="ANALYST_TEXT_AND_RENDER_INSPECTED_NOT_SCIENTIFIC_APPROVAL",
                      rights="LOCAL_ONLY; source and imagery permissions unresolved for redistribution",
                      publisher_checksum="NOT_PUBLISHED_IN_RESPONSE", http_status=200,
                      response_date=next(v.partition(":")[2].strip() for v in headers if v.lower().startswith("date:")))
        results.append(result)
    return results


def calculate(root):
    directory = root / INPUT
    manifest = json.loads((directory / "manifest.json").read_text())
    # Hash the frozen database, manifests and source bytes without re-extracting.
    sources = {str((INPUT / "manifest.json")): fingerprint(directory / "manifest.json")}
    for relative in (INPUT / "audit.sqlite", PROTOCOL,
                     Path("data/working/belagavi_2021_sentinel1_anchor_v1/anchor.json"),
                     Path("data/working/belagavi_2021_incidence_audit_v1/audit.json"),
                     Path("data/working/karnataka_flood_outcome_foundation_v1/report.json"),
                     Path("data/processed/udupi_drainage_gis_v1/study_area.geojson")):
        sources[str(relative)] = fingerprint(root / relative)
    if sources[str(INPUT / "audit.sqlite")] != manifest["files"]["audit.sqlite"]:
        raise ValueError("frozen Groundsource database differs")
    for relative, expected in manifest["sources"].items():
        if fingerprint(root / relative) != expected:
            raise ValueError("frozen original source differs: " + relative)
        sources[relative] = expected
    for name, expected in manifest["code"].items():
        relative = Path("scripts") / name
        if fingerprint(root / relative) != expected:
            raise ValueError("frozen extraction code differs: " + name)
        sources[str(relative)] = expected
    connection = sqlite3.connect(f"file:{directory / 'audit.sqlite'}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA cache_size=-32768")
    records = []
    for ordinal, blob, payload in connection.execute("SELECT ordinal,geometry,payload FROM candidates ORDER BY ordinal"):
        p = json.loads(payload)
        geometry = shapely.from_wkb(blob)
        if not geometry.is_valid or geometry.is_empty or geometry.area <= 0:
            raise ValueError("invalid frozen candidate geometry")
        records.append({"ordinal": ordinal, "payload": p, "geometry": geometry,
                        "start": dt.date.fromisoformat(p["source_start_date"]), "end": dt.date.fromisoformat(p["source_end_date"])})
    if len(records) != 19854 or len({r["payload"]["source_uuid"] for r in records}) != len(records):
        raise ValueError("frozen candidate count/UUID invariant differs")
    records, groups, assigned, pairs, alternatives, comparisons = cluster(records)
    group_ids = ["review-" + hashlib.sha256("\n".join(sorted(records[i]["payload"]["source_uuid"] for i in members)).encode()).hexdigest()[:24] for members in groups]
    if len(set(group_ids)) != len(groups):
        raise ValueError("group ID collision")
    links = defaultdict(list)
    for ordinal, source, event_id, method in connection.execute("SELECT ordinal,source,event_id,method FROM possible_matches ORDER BY ordinal,source,event_id,method"):
        links[ordinal].append({"source": source, "event_id": event_id, "method": method, "association": "POSSIBLE_NOT_CONFIRMED"})
    connection.close()
    ifi_records = json.loads((root / "data/working/karnataka_flood_events_v1/events.json").read_text())
    ifi_precision = []
    for row in ifi_records:
        days = row.get("derived_event_duration_days_inclusive")
        usable = row["date_status"]["window"] == "usable" and isinstance(days, int) and days > 0
        ifi_precision.append({"source_event_id": row["ifi_source_event_id"], "source_start_date": row["source_start_date"],
                              "source_end_date": row["source_end_date"], "retained_parsed_start": row["parsed_start_date"],
                              "retained_parsed_end": row["parsed_end_date_inclusive"], "reported_window_days": days,
                              "date_screen_usable": usable, "exact_event_timing_verified": False,
                              "precision": "BROAD_WINDOW_REQUIRES_DATE_MEANING_REVIEW" if usable and days>7 else "UNVERIFIED_EVENT_TIME"})
    ambiguous = set(alternatives)
    for i, j, accepted in pairs:
        if assigned[i] != assigned[j]:
            ambiguous.update((assigned[i], assigned[j]))
    group_rows, member_rows, linkage_rows = [], [], []
    district_year, years = Counter(), Counter()
    for g, members in enumerate(groups):
        items = [records[i]["payload"] for i in members]
        districts = sorted({d for p in items for d in p["district_ids"]})
        start = min(p["source_start_date"] for p in items)
        end = max(p["source_end_date"] for p in items)
        row = {"group_id": group_ids[g], "source_uuids": [p["source_uuid"] for p in items],
               "member_count": len(items), "source_district_ids": districts, "reported_start": start, "reported_end": end,
               "grouping_precision": "ELIGIBLE_REPORTED_SUPPORT" if all(groupable(p) for p in items) else "BROAD_OR_ADMIN_AMBIGUOUS_SINGLETON",
               "smallest_reported_area_km2": min(p["projected_polygon_area_km2"] for p in items),
               "largest_reported_area_km2": max(p["projected_polygon_area_km2"] for p in items),
               "max_member_report_days": max(p["reported_interval_days_inclusive_assumption"] for p in items),
               "cross_group_possible_relationship": g in ambiguous,
               "alternative_complete_link_groups": [group_ids[n] for n in alternatives.get(g, [])],
               "physical_event_identity": "UNADJUDICATED", "training_label": "UNKNOWN",
               "possible_ifi_ids": sorted({l["event_id"] for i in members for l in links[records[i]["ordinal"]] if l["source"] == "IFI"}),
               "possible_gfd_ids": sorted({l["event_id"] for i in members for l in links[records[i]["ordinal"]] if l["source"] == "GFD"})}
        group_rows.append(row)
        years[start[:4]] += 1
        for d in districts:
            district_year[(d, start[:4])] += 1
        for i in members:
            p = records[i]["payload"]
            member_rows.append(dict(group_id=group_ids[g], **p, original_geometry_storage="IMMUTABLE_ARCHIVE_WGS84_WKB; native SQLite geometry is derived only",
                                    original_archive_reference="data/raw/groundsource/zenodo_18647054_v1/groundsource_2026.parquet",
                                    original_archive_sha256=manifest["sources"]["data/raw/groundsource/zenodo_18647054_v1/groundsource_2026.parquet"]["sha256"]))
            for l in links[records[i]["ordinal"]]:
                linkage_rows.append(dict(group_id=group_ids[g], source_uuid=p["source_uuid"], **l))
    evidence = receipts(root)
    for source in evidence:
        sources[source["reference"]] = {k: source[k] for k in ("bytes", "sha256")}
        header = str(Path(source["reference"]).with_suffix(".headers"))
        sources[header] = fingerprint(root / header)
    boundaries = load_boundaries(root / "data/working/karnataka_soi_abdb2025_v1")
    udupi = checked_file(root / "data/processed/udupi_flood_spatial_v1", "udupi_boundary.geojson")
    sources[str(udupi.relative_to(root))] = fingerprint(udupi)
    ujson = json.loads(udupi.read_text())
    ugeometry = geojson_geometry(ujson)
    ugeography = transform(boundaries["to_native"], ugeometry)
    anchor = json.loads((root / "data/working/belagavi_2021_sentinel1_anchor_v1/anchor.json").read_text())
    viewport = next(v for v in anchor["corroborating_map"]["viewports"] if v["name"] == "Postflood")
    bgeography = transform(boundaries["to_native"], Polygon(viewport["geographic_registration_lon_lat"]))
    contexts = [
        ("Udupi_2020_coastal_response", "2020-09-19", "2020-09-22", ugeography, ["mha-2020"], "PUBLIC_RESEARCH_DISTRICT_REFERENCE_NOT_EVENT_YEAR_IDENTITY"),
        ("Belagavi_2021_official_inundation", "2021-07-22", "2021-07-29", bgeography, ["mha-2021", "nrsc-2021-26", "nrsc-2021-28"], "SOURCE_MAP_VIEWPORT_FOR_PRIORITIZATION_NOT_INUNDATION_BOUNDARY")
    ]
    review_rows, selection_counts = [], {}
    for name, start, end, geography, source_ids, basis in contexts:
        choices = []
        for g, members in enumerate(groups):
            candidates = [records[i] for i in members if records[i]["payload"]["source_start_date"] <= end
                          and records[i]["payload"]["source_end_date"] >= start and records[i]["geometry"].intersection(geography).area > 0]
            if candidates:
                choices.append((not all(groupable(r["payload"]) for r in candidates),
                                max(r["payload"]["reported_interval_days_inclusive_assumption"] for r in candidates),
                                max(r["geometry"].area for r in candidates), group_ids[g], g))
        choices.sort()
        selection_counts[name] = len(choices)
        for *_, g in choices[:RULES["pilot_groups_per_context"]]:
            row = group_rows[g]
            review = {"review_id": "pilot-" + row["group_id"], "group_id": row["group_id"],
                      "context": name, "review_status": "EVIDENCE_INSPECTED_GROUP_OUTCOME_UNKNOWN", "original_report_reference": "UNKNOWN_NOT_SUPPLIED_BY_RELEASE",
                      "source_uuids": row["source_uuids"], "original_geometry_hashes": [records[i]["payload"]["raw_geometry_sha256"] for i in groups[g]],
                      "original_dates": [{"uuid": records[i]["payload"]["source_uuid"], "start": records[i]["payload"]["source_start_date"], "end": records[i]["payload"]["source_end_date"]} for i in groups[g]],
                      "official_document_ids": source_ids, "geographic_selection_basis": basis,
                      "verified_start": None, "verified_end": None, "verified_location_reference": None,
                      "geographic_accuracy": "UNKNOWN; reported polygon support is not measured accuracy",
                      "temporal_accuracy": "UNKNOWN; original dates retained, exact occurrence time unverified",
                      "satellite_linkage": "REGIONAL_CONTEXT_ONLY" if name.startswith("Belagavi") else "NONE_FOR_THIS_EPISODE",
                      "flood_mechanism": "Official regional reservoir-discharge context, candidate-specific mechanism UNKNOWN" if name.startswith("Belagavi") else "UNKNOWN",
                      "outcome": "UNKNOWN", "protocol_id": json.loads((root / PROTOCOL).read_text())["protocol_id"],
                      "inspected_on": "2026-10-12", "inspection_scope": "Original member metadata and source geometry pointers, official regional documents and available satellite context; no external scientific approval",
                      "independent_sources": [], "blockers": ["Original news reference absent", "No independently verified candidate-specific flood location/time", "No target-cell observation or scientific adjudication"]}
            review["validation"] = evaluate_event_review(review, root)
            review_rows.append(review)
    foundation = json.loads((root / "data/working/karnataka_flood_outcome_foundation_v1/report.json").read_text())
    for scope in foundation["scopes"]:
        path = verify_file(root, scope["reference"], scope["sha256"])
        sources[scope["reference"]] = fingerprint(path)
    controls = []
    for scope in foundation["scopes"]:
        if scope["district"] == "Udupi" and scope["status"] == "satellite_positive":
            hits = sum(r["payload"]["source_start_date"] <= scope["end"] and r["payload"]["source_end_date"] >= scope["start"]
                       and r["geometry"].intersection(ugeography).area > 0 for r in records)
            controls.append({"reference_id": "gfd-"+str(scope["gfd_id"]), "district": "Udupi", "start": scope["start"], "end": scope["end"],
                             "positive_composite_cells": scope["positive_pixels"], "groundsource_reports_in_reference_window": hits,
                             "outcome_for_daily_target": "UNKNOWN", "reason": "Multi-day maximum composite; exact acquisition, target-cell permanence/quality and independent event adjudication missing"})
    if len(review_rows)+len(controls) > 50:
        raise ValueError("manual pilot budget exceeded")
    observation_rows = [{"observation_id": "gfd-context-"+str(s["gfd_id"]), "family": "GFD_COMPOSITE", "source_reference": s["reference"],
                         "source_sha256": s["sha256"], "district_context": s["district"], "reported_start": s["start"], "reported_end": s["end"],
                         "source_status": s["status"], "positive_pixels": s["positive_pixels"], "valid_fraction": s["valid_fraction"],
                         "target_outcome": "UNKNOWN", "reason": "Composite cannot establish exact observation time or full-day absence; target unit and independent review unresolved"} for s in foundation["scopes"]]
    incidence = json.loads((root / "data/working/belagavi_2021_incidence_audit_v1/audit.json").read_text())
    # Record the frozen acquisition contexts; valid backscatter is not classified water.
    observation_rows += [{"observation_id": scene["id"], "family": "SENTINEL1_CONTINUOUS_BACKSCATTER",
                          "source_reference": "data/working/belagavi_2021_incidence_audit_v1/audit.json",
                          "reported_start": scene["acquisition_utc"][:10], "reported_end": scene["acquisition_utc"][:10],
                          "acquisition_utc": scene["acquisition_utc"], "valid_backscatter_cells": scene["valid_vv_vh_cells"],
                          "target_outcome": "UNKNOWN",
                          "reason": "VV/VH/angle valid coverage is unclassified; no approved flood mask or permanent-water assessment"} for scene in incidence["incidence"]["scenes"]]
    if not incidence:
        raise ValueError("empty retained satellite audit")
    observation_rows += [{"observation_id": s["id"], "family": s["family"], "source_reference": s["reference"],
                          "reported_start": s["evidence_date"], "reported_end": s["evidence_date"], "target_outcome": "UNKNOWN",
                          "reason": s["limits"]} for s in evidence]
    protocol = json.loads((root / PROTOCOL).read_text())
    for row in observation_rows:
        row["validation"] = evaluate_window_observation(row, root, protocol)
    district_names = {d["id"]: d["name"] for d in boundaries["districts"]}
    for year in range(int(min(years)), int(max(years))+1):
        years.setdefault(str(year), 0)
    coverage = [{"source_district_id": d, "source_name_unresolved": district_names[d], "start_year": year,
                 "review_groups_intersecting": district_year[(d, year)], "eligible_positive_labels": 0, "eligible_negative_labels": 0}
                for d in sorted(district_names) for year in sorted(years)]
    district_coverage = [{"source_district_id": d, "source_name_unresolved": district_names[d],
                          "review_groups_intersecting": sum(d in r["source_district_ids"] for r in group_rows),
                          "groups_with_ambiguous_relationships": sum(d in r["source_district_ids"] and r["cross_group_possible_relationship"] for r in group_rows),
                          "current_lgd_identity_verified": False, "eligible_positive_labels": 0, "eligible_negative_labels": 0}
                         for d in sorted(district_names)]
    report = {"version": OUTPUT.name, "target_status": protocol["review_status"], "rules": RULES,
              "news_reports": len(records), "candidate_review_groups": len(groups),
              "group_size_counts": dict(sorted(Counter(len(g) for g in groups).items())),
              "multiple_report_groups": sum(len(g)>1 for g in groups), "maximum_group_members": max(map(len, groups)),
              "reported_support_groupable_records": sum(groupable(r["payload"]) for r in records),
              "broad_or_admin_ambiguous_singleton_groups": sum(r["grouping_precision"] != "ELIGIBLE_REPORTED_SUPPORT" for r in group_rows),
              "ambiguous_relationship_groups": len(ambiguous), "multiple_complete_link_alternative_groups": len(alternatives),
              "spatial_date_related_pairs": len(pairs), "cross_group_related_pairs": sum(assigned[i] != assigned[j] for i,j,_ in pairs),
              "exact_geometry_comparisons": comparisons, "pair_search_exhaustive_within_rules": True,
              "independently_certified_physical_group_count": 0, "actual_physical_event_count": "UNKNOWN",
              "manual_news_group_reviews": len(review_rows), "manual_gfd_reference_controls": len(controls),
              "manual_confirmed_group_outcomes": 0, "manual_unknown_group_outcomes": len(review_rows),
              "regional_officially_documented_flood_episodes": 1,
              "regional_flood_episode_context": "Belagavi July 2021; MHA regional flooding plus NRSC July26/28 observations, not three independent floods",
              "other_regional_response_contexts": 1, "new_official_satellite_documentary_observations": 2,
              "retained_udupi_positive_composites": 2, "retained_udupi_positive_composite_cells": 56,
              "context_candidate_group_counts": selection_counts,
              "groups_with_possible_ifi_links": sum(bool(r["possible_ifi_ids"]) for r in group_rows),
              "groups_with_possible_gfd_links": sum(bool(r["possible_gfd_ids"]) for r in group_rows),
              "distinct_possible_ifi_ids": len({x for r in group_rows for x in r["possible_ifi_ids"]}),
              "distinct_possible_gfd_ids": len({x for r in group_rows for x in r["possible_gfd_ids"]}),
              "ifi_retained_rows": len(ifi_precision), "ifi_date_usable_rows": sum(r["date_screen_usable"] for r in ifi_precision),
              "ifi_windows_longer_than_seven_days": sum(r["date_screen_usable"] and r["reported_window_days"]>7 for r in ifi_precision),
              "ifi_windows_longer_than_31_days": sum(r["date_screen_usable"] and r["reported_window_days"]>31 for r in ifi_precision),
              "confirmed_ifi_gfd_same_event_links": 0,
              "observation_contexts": len(observation_rows), "observation_outcomes": {"POSITIVE": 0, "NEGATIVE": 0, "UNKNOWN": len(observation_rows)},
              "eligible_positive_labels": 0, "defensible_negative_labels": 0, "training_decision": "NO-GO",
              "source_district_units_with_candidates": len({d for r in group_rows for d in r["source_district_ids"]}),
              "verified_current_lgd_districts": 0, "group_start_year_counts": dict(sorted(years.items())),
              "all_groups_need_physical_event_adjudication": len(groups),
              "blockers": ["Proposed target lacks independent scientific approval", "Original per-report news references unavailable",
                           "No candidate-specific independently adjudicated physical flood groups", "No approved target-cell/time positive labels",
                           "No complete same-cell/full-day absence evidence", "IFI broad raw date windows and source district identity unresolved",
                           "Sensor detection/permanence/registration and rights reviews incomplete", "As-issued feature history, independent event/space/time evaluation and sample-power review incomplete"],
              "rights": "Record-level groups, members, links, reviews, originals and all source geometry stay ignored/local; public factual counts and code only",
              "original_geometry_preservation": "Original WGS84 WKB remains in immutable checksum-bound archive, addressed by original ordinal/UUID/raw geometry hash; no union or reconstructed geometry exported"}
    outputs = {"report.json": encoded(report), "source_receipts.json": encoded(evidence), "manual_reviews.json": encoded(review_rows),
               "ifi_temporal_precision.json": encoded(ifi_precision),
               "reference_controls.json": encoded(controls), "observation_quality.json": encoded(observation_rows),
               "candidate_event_groups.jsonl": "".join(json.dumps(r, sort_keys=True, allow_nan=False)+"\n" for r in group_rows),
               "group_members.jsonl": "".join(json.dumps(r, sort_keys=True, allow_nan=False)+"\n" for r in member_rows),
               "source_linkage.jsonl": "".join(json.dumps(r, sort_keys=True, allow_nan=False)+"\n" for r in linkage_rows),
               "possible_group_relationships.csv": csv_text([{"left_group": group_ids[assigned[i]], "right_group": group_ids[assigned[j]],
                         "left_uuid": records[i]["payload"]["source_uuid"], "right_uuid": records[j]["payload"]["source_uuid"],
                         "complete_link_pair_eligible": accepted, "association": "POSSIBLE_NOT_PHYSICAL_EVENT_CONFIRMATION"} for i,j,accepted in pairs],
                         ["left_group", "right_group", "left_uuid", "right_uuid", "complete_link_pair_eligible", "association"]),
               "district_year_coverage.csv": csv_text(coverage, list(coverage[0])),
               "district_coverage.csv": csv_text(district_coverage, list(district_coverage[0])),
               "year_coverage.csv": csv_text([{"start_year": year, "candidate_review_groups": n, "eligible_positive_labels": 0, "eligible_negative_labels": 0} for year,n in sorted(years.items())],
                                           ["start_year", "candidate_review_groups", "eligible_positive_labels", "eligible_negative_labels"])}
    return outputs, sources


def build(root=ROOT):
    destination = root / OUTPUT
    if destination.exists():
        raise ValueError("version exists; validate it or create a reviewed new version")
    outputs, sources = calculate(root)
    destination.mkdir()
    for name, value in outputs.items():
        (destination / name).write_text(value)
    manifest = {"version": OUTPUT.name, "sources": sources,
                "code": {"scripts/"+name: fingerprint(Path(__file__).with_name(name)) for name in
                         ("build_verified_flood_event_pilot.py", "audit_groundsource_karnataka.py", "build_flood_outcome_foundation.py", "verify_soi_karnataka.py")},
                "runtime": {"shapely": shapely.__version__, "geos": shapely.geos_version_string},
                "files": {name: fingerprint(destination/name) for name in outputs}}
    (destination / "manifest.json").write_text(encoded(manifest))
    return json.loads(outputs["report.json"])


def validate(root=ROOT, replay=False, public=None):
    destination = root / OUTPUT
    manifest = json.loads((destination / "manifest.json").read_text())
    for category in ("sources", "code", "files"):
        for name, expected in manifest[category].items():
            path = destination/name if category == "files" else root/name
            if fingerprint(path) != expected:
                raise ValueError(category + " checksum differs: " + name)
    if manifest["runtime"] != {"shapely": shapely.__version__, "geos": shapely.geos_version_string}:
        raise ValueError("scientific geometry runtime differs")
    if replay:
        actual, sources = calculate(root)
        if sources != manifest["sources"]:
            raise ValueError("source receipt replay differs")
        for name, text in actual.items():
            if (destination/name).read_text() != text:
                raise ValueError("local subset replay differs: " + name)
    if public:
        for name in ("report.json", "district_year_coverage.csv", "district_coverage.csv", "year_coverage.csv"):
            if (public/name).read_bytes() != (destination/name).read_bytes():
                raise ValueError("public aggregate differs: " + name)
    return json.loads((destination / "report.json").read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--replay", action="store_true", help="recompute from frozen Karnataka subset only")
    parser.add_argument("--public", type=Path)
    args = parser.parse_args()
    try:
        result = build() if args.command == "build" else validate(replay=args.replay, public=args.public)
        print(encoded(result), end="")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Verified event pilot failed: {error}\n")
