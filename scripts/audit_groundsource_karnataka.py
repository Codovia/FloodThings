#!/usr/bin/env python3
"""Bounded, offline Groundsource Karnataka screening, never flood-label creation.

Full event register and geometries remain ignored/local. SOI identities are used
exactly as supplied, without inferred current LGD names/codes. Completed versions
are immutable. SQLite keeps global duplicate state on disk, not in Python RAM.
"""
import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import resource
import sqlite3
import sys

import shapely
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

import acquire_groundsource as acquisition
import verify_soi_karnataka as soi
from build_flood_outcome_foundation import checked_file, validate as foundation_validate

ROOT = Path(__file__).resolve().parents[1]
VERSION = "karnataka_groundsource_2026_v1"
OUTPUT = ROOT / "data/working" / VERSION
BOUNDARIES = ROOT / "data/working/karnataka_soi_abdb2025_v1"
RUNTIME = ROOT / "data/working/groundsource_runtime_v1"
SCHEMA = ["uuid", "area_km2", "geometry", "start_date", "end_date", "__index_level_0__"]
BATCH_SIZE = 1024
PAIR_LIMIT = 250000
EXPECTED_ROWS = 2646302
CODE = ("audit_groundsource_karnataka.py", "acquire_groundsource.py", "verify_soi_karnataka.py")


def fingerprint(path):
    result = acquisition.file_hashes(path)
    return {k: result[k] for k in ("bytes", "sha256")}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def date_status(start, end):
    try:
        if not all(isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in (start, end)):
            raise ValueError("not ISO date strings")
        a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except ValueError:
        return "MISSING_OR_INVALID_DATE", None
    if a > b:
        return "REVERSED_INTERVAL", None
    if b > dt.date(2026, 10, 12):
        return "FUTURE_DATE_REQUIRES_REVIEW", None
    return "USABLE_REPORTED_DATE_RANGE", (b - a).days + 1


def load_boundaries(directory=BOUNDARIES):
    soi.validate_version(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    district_source = soi.read_source(directory / "districts.shp", "STATE_UT", district=True)
    state_source = soi.read_source(directory / "state.shp", "STATE")
    state = shapely.force_2d(shape(state_source["records"][0]["shape"].__geo_interface__))
    districts = []
    for item, original in zip(district_source["records"], manifest["district_records"], strict=True):
        districts.append({"id": f"soi-abdb2025:objectid:{original['source_objectid']}",
                          "name": original["district_name_original"], "nic_exact_name": original["nic_exact_name"],
                          "supplied_lgd_code_unverified": original["district_lgd_code_as_supplied_by_soi"],
                          "geometry": shapely.force_2d(shape(item["shape"].__geo_interface__))})
    to_native = Transformer.from_crs("EPSG:4326", state_source["crs"], always_xy=True).transform
    to_wgs84 = Transformer.from_crs(state_source["crs"], "EPSG:4326", always_xy=True).transform
    state_wgs84 = transform(to_wgs84, state)
    if not state_wgs84.is_valid:
        raise ValueError("Reprojected state invalid; do not repair")
    return {"state": state, "districts": districts, "to_native": to_native,
            "wgs84_bounds": state_wgs84.bounds, "manifest": manifest,
            "tree": shapely.STRtree([d["geometry"] for d in districts])}


def bbox_overlap(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def geometry_screen(blob, boundaries):
    """Return global geometry status and local candidate; never buffer/repair."""
    if not isinstance(blob, bytes):
        return "MISSING_WKB", None
    geom = shapely.from_wkb(blob, on_invalid="ignore")
    if geom is None:
        return "INVALID_WKB", None
    if geom.is_empty:
        return "EMPTY_GEOMETRY", None
    bounds = geom.bounds
    finite = len(bounds) == 4 and all(math.isfinite(v) for v in bounds)
    possible = finite and bbox_overlap(bounds, boundaries["wgs84_bounds"])
    if not finite or bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -90 or bounds[3] > 90:
        status = "INVALID_COORDINATES"
    elif geom.geom_type not in ("Polygon", "MultiPolygon"):
        status = "NON_AREAL_GEOMETRY"
    elif not geom.is_valid:
        status = "INVALID_GEOMETRY"
    elif bounds[2] - bounds[0] > 180:
        status = "AMBIGUOUS_ANTIMERIDIAN"
    else:
        status = "VALID_AREAL_GEOMETRY"
    if not possible:
        return status, None
    raw_hash = hashlib.sha256(blob).hexdigest()
    if status != "VALID_AREAL_GEOMETRY":
        return status, {"state_status": "INVALID_OR_AMBIGUOUS_BBOX_SCREEN", "geometry_status": status,
                        "raw_geometry_sha256": raw_hash, "normalized_geometry_sha256": None,
                        "projected_polygon_area_km2": None, "state_area_fraction": None,
                        "district_ids": [], "definite_district_id": None, "native_geometry": None}
    native = transform(boundaries["to_native"], shapely.force_2d(geom))
    if not native.is_valid or native.is_empty or not math.isfinite(native.area) or native.area <= 0:
        return status, {"state_status": "INVALID_OR_AMBIGUOUS_BBOX_SCREEN", "geometry_status": "INVALID_AFTER_PROJECTION",
                        "raw_geometry_sha256": raw_hash, "normalized_geometry_sha256": None,
                        "projected_polygon_area_km2": None, "state_area_fraction": None,
                        "district_ids": [], "definite_district_id": None, "native_geometry": None}
    state = boundaries["state"]
    if not state.intersects(native):
        return status, None
    intersection = state.intersection(native)
    state_status = ("DEFINITE_WITHIN_SOURCE_STATE" if state.covers(native) else
                    "STATE_BOUNDARY_TOUCH_ONLY" if intersection.area == 0 else "CROSS_STATE_INTERSECTION")
    indices = boundaries["tree"].query(native, predicate="intersects")
    positives = sorted(int(i) for i in indices if boundaries["districts"][int(i)]["geometry"].intersection(native).area > 0)
    definite = [i for i in positives if boundaries["districts"][i]["geometry"].covers(native)]
    return status, {"state_status": state_status, "geometry_status": status,
                    "raw_geometry_sha256": raw_hash,
                    "normalized_geometry_sha256": hashlib.sha256(shapely.normalize(shapely.force_2d(geom)).wkb).hexdigest(),
                    "projected_polygon_area_km2": native.area / 1e6,
                    "state_area_fraction": intersection.area / native.area,
                    "district_ids": [boundaries["districts"][i]["id"] for i in positives],
                    "definite_district_id": boundaries["districts"][definite[0]]["id"] if len(definite) == 1 else None,
                    "native_geometry": native}


def record_candidate(row, ordinal, screening):
    spatial = {k: v for k, v in screening.items() if k != "native_geometry"}
    temporal, duration = date_status(row.get("start_date"), row.get("end_date"))
    supplied_area = row.get("area_km2")
    if isinstance(supplied_area, bool) or not isinstance(supplied_area, (int, float)) or not math.isfinite(supplied_area) or supplied_area < 0:
        supplied_area = None
    usable = spatial["state_status"] == "DEFINITE_WITHIN_SOURCE_STATE" and temporal == "USABLE_REPORTED_DATE_RANGE"
    return {"source_row_ordinal": ordinal, "source_uuid": row.get("uuid"), "stored_index": row.get("__index_level_0__"),
            "source_start_date": row.get("start_date"), "source_end_date": row.get("end_date"),
            "date_status": temporal, "reported_interval_days_inclusive_assumption": duration,
            "supplied_polygon_area_km2": supplied_area, **spatial,
            "geographic_temporal_screening_usable": usable,
            "single_district_screening_usable": usable and spatial["definite_district_id"] is not None,
            "evidence_type": "NEWS_REPORTED_LOCATION_UNVERIFIED_NOT_INUNDATION_EXTENT",
            "source_confidence": "NOT_SUPPLIED", "manual_verification_required": True,
            "flood_label_eligible": False, "negative_label": False}


def parquet_batches(archive, batch_size=BATCH_SIZE):
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 4096:
        raise ValueError("Batch size must be 1..4096")
    import pyarrow.parquet as pq
    file = pq.ParquetFile(archive, memory_map=False, pre_buffer=False)
    if file.schema_arrow.names != SCHEMA:
        raise ValueError("Groundsource schema changed; review before processing")
    geo = json.loads(file.schema_arrow.metadata[b"geo"])
    column = geo["columns"][geo["primary_column"]]
    if geo["primary_column"] != "geometry" or column["encoding"] != "WKB" or column["crs"]["id"] != {"authority": "EPSG", "code": 4326}:
        raise ValueError("Groundsource geometry CRS/encoding changed")
    yield from file.iter_batches(batch_size=batch_size, columns=SCHEMA, use_threads=False)


def database(path, readonly=False):
    db = sqlite3.connect(f"file:{path}?mode=ro" if readonly else str(path), uri=readonly)
    db.execute("PRAGMA cache_size=-32768")
    db.execute("PRAGMA temp_store=FILE")
    if readonly:
        db.execute("PRAGMA query_only=ON")
    else:
        db.executescript("""
        CREATE TABLE global_ids(uuid TEXT PRIMARY KEY, rows INTEGER NOT NULL, first_hash TEXT, conflicting INTEGER NOT NULL);
        CREATE TABLE candidates(ordinal INTEGER PRIMARY KEY, uuid TEXT, geom_hash TEXT, start TEXT, end TEXT,
            usable INTEGER, single_district INTEGER, state_status TEXT, geometry BLOB, payload TEXT NOT NULL);
        CREATE TABLE district_hits(ordinal INTEGER, district_id TEXT, definite INTEGER, PRIMARY KEY(ordinal,district_id));
        CREATE TABLE possible_matches(ordinal INTEGER, source TEXT, event_id TEXT, method TEXT);
        CREATE VIRTUAL TABLE spatial_index USING rtree(ordinal,minx,maxx,miny,maxy);
        CREATE INDEX candidate_geom_dates ON candidates(geom_hash,start,end);
        CREATE INDEX candidate_uuid ON candidates(uuid);
        CREATE INDEX district_identifier ON district_hits(district_id,ordinal);
        CREATE INDEX inventory_match_counts ON possible_matches(ordinal,source);
        """)
    return db


def scan(records, db, boundaries):
    counters, ordinal = Counter(), 0
    for row in records:
        uuid = row.get("uuid")
        valid_uuid = isinstance(uuid, str) and bool(uuid.strip())
        raw = row.get("geometry")
        geometry_digest = hashlib.sha256(raw).hexdigest() if isinstance(raw, bytes) else "MISSING"
        payload_hash = hashlib.sha256(canonical([geometry_digest, row.get("start_date"), row.get("end_date"), repr(row.get("area_km2"))]).encode()).hexdigest()
        if valid_uuid:
            db.execute("INSERT INTO global_ids VALUES(?,1,?,0) ON CONFLICT(uuid) DO UPDATE SET rows=rows+1, conflicting=conflicting OR first_hash!=excluded.first_hash", (uuid, payload_hash))
        else:
            counters["missing_uuid"] += 1
        status, screening = geometry_screen(raw, boundaries)
        counters[status] += 1
        if screening:
            candidate = record_candidate(row, ordinal, screening)
            geom = screening["native_geometry"]
            db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?)", (ordinal, uuid if valid_uuid else None,
                       candidate["normalized_geometry_sha256"], candidate["source_start_date"], candidate["source_end_date"],
                       candidate["geographic_temporal_screening_usable"], candidate["single_district_screening_usable"],
                       candidate["state_status"], geom.wkb if geom is not None else None, canonical(candidate)))
            for district_id in candidate["district_ids"]:
                db.execute("INSERT INTO district_hits VALUES(?,?,?)", (ordinal, district_id, district_id == candidate["definite_district_id"]))
            if geom is not None:
                x0,y0,x1,y1 = geom.bounds
                db.execute("INSERT INTO spatial_index VALUES(?,?,?,?,?)", (ordinal,x0,x1,y0,y1))
        ordinal += 1
        if ordinal % 16384 == 0:
            db.commit()
            print(f"Rows scanned: {ordinal}; candidates: {db.execute('SELECT count(*) FROM candidates').fetchone()[0]}", flush=True)
    db.commit()
    return {"rows_scanned": ordinal, "global_geometry_status_counts": dict(counters)}


def overlap_screen(db, limit=PAIR_LIMIT):
    if limit <= 0:
        raise ValueError("Overlap comparison limit must be positive")
    comparisons, positive_pairs, sample = 0, 0, []
    for ordinal, start, end, blob in db.execute("SELECT ordinal,start,end,geometry FROM candidates WHERE geometry IS NOT NULL AND start<=end ORDER BY ordinal"):
        payload = json.loads(db.execute("SELECT payload FROM candidates WHERE ordinal=?", (ordinal,)).fetchone()[0])
        if payload["date_status"] != "USABLE_REPORTED_DATE_RANGE":
            continue
        geom = shapely.from_wkb(blob)
        x0,y0,x1,y1 = geom.bounds
        pairs = db.execute("""SELECT c.ordinal,c.geometry,c.payload FROM spatial_index s JOIN candidates c ON c.ordinal=s.ordinal
            WHERE s.ordinal>? AND s.minx<=? AND s.maxx>=? AND s.miny<=? AND s.maxy>=?
            AND c.start<=? AND c.end>=? ORDER BY c.ordinal""", (ordinal,x1,x0,y1,y0,end,start))
        for other, other_blob, other_payload in pairs:
            if json.loads(other_payload)["date_status"] != "USABLE_REPORTED_DATE_RANGE":
                continue
            if comparisons >= limit:
                return {"comparisons": comparisons, "positive_area_date_overlap_pairs": positive_pairs,
                        "exhaustive": False, "limit": limit, "sample_row_pairs": sample,
                        "count_status": "LOWER_BOUND_BOUNDED_SCREEN_NOT_PHYSICAL_EVENT_DUPLICATES"}
            comparisons += 1
            if geom.intersection(shapely.from_wkb(other_blob)).area > 0:
                positive_pairs += 1
                if len(sample) < 25:
                    sample.append([ordinal,other])
    return {"comparisons": comparisons, "positive_area_date_overlap_pairs": positive_pairs,
            "exhaustive": True, "limit": limit, "sample_row_pairs": sample,
            "count_status": "EXACT_RECORD_PAIR_COUNT_NOT_CONFIRMED_PHYSICAL_EVENT_DUPLICATES"}


def compare_inventories(db, boundaries, root=ROOT):
    foundation = foundation_validate(root)
    events = json.loads(checked_file(root / "data/working/karnataka_flood_events_v1", "events.json").read_text())
    normalize = lambda s: " ".join(s.split()).casefold()
    existing, unresolved_gfd = [], []
    for e in events:
        if e["date_status"]["window"] == "usable":
            existing.append(("IFI",e["ifi_source_event_id"],e["parsed_start_date"],e["parsed_end_date_inclusive"],
                             {normalize(t) for t in e["source_districts"].split(",") if t.strip()}))
    source_names = {normalize(d["name"]) for d in boundaries["districts"]}
    for s in foundation["scopes"]:
        tokens = {normalize(s["district"])}
        existing.append(("GFD",str(s["gfd_id"]),s["start"],s["end"],tokens))
        if not tokens & source_names:
            unresolved_gfd.append(s["gfd_id"])
    names = {d["id"]: normalize(d["name"]) for d in boundaries["districts"]}
    temporal_counts = Counter()
    for ordinal,start,end,payload in db.execute("SELECT ordinal,start,end,payload FROM candidates ORDER BY ordinal"):
        row = json.loads(payload)
        if row["date_status"] != "USABLE_REPORTED_DATE_RANGE":
            continue
        districts = {names[d] for d in row["district_ids"]}
        for source,event_id,a,b,tokens in existing:
            if start <= b and end >= a:
                temporal_counts[source] += 1
                if districts & tokens:
                    db.execute("INSERT INTO possible_matches VALUES(?,?,?,?)", (ordinal,source,event_id,
                               "EXACT_SOURCE_DISTRICT_TOKEN_AND_DATE_OVERLAP_NOT_CONFIRMED_EVENT"))
    # Two checksum-verified Udupi event pixel sets support an additional actual
    # spatial screen. The other reviewed GFD scopes remain coarse name matches.
    udupi = root / "data/processed/udupi_flood_spatial_v1"
    manifest = json.loads((udupi / "manifest.json").read_text())
    for event in manifest["events"]:
        path = checked_file(udupi,event["geometry_file"])
        features = json.loads(path.read_text())["features"]
        pixels = [transform(boundaries["to_native"],shape(f["geometry"])) for f in features]
        water = shapely.union_all(pixels)
        for ordinal,blob,payload in db.execute("SELECT ordinal,geometry,payload FROM candidates WHERE start<=? AND end>=? AND geometry IS NOT NULL", (event["end_date_inclusive"],event["start_date"])):
            row = json.loads(payload)
            if row["date_status"] == "USABLE_REPORTED_DATE_RANGE" and shapely.from_wkb(blob).intersection(water).area > 0:
                db.execute("INSERT INTO possible_matches VALUES(?,?,?,?)",(ordinal,"GFD_PIXEL",str(event["event_id"]),
                           "REPORTED_LOCATION_INTERSECTS_RETAINED_EVENT_WATER_PIXEL_NOT_EVENT_CONFIRMATION"))
    db.commit()
    summary = {}
    for source in ("IFI","GFD","GFD_PIXEL"):
        pairs, candidates, ids = db.execute("SELECT count(*),count(DISTINCT ordinal),count(DISTINCT event_id) FROM possible_matches WHERE source=?",(source,)).fetchone()
        summary[source] = {"possible_pairs":pairs,"candidate_records":candidates,"distinct_existing_ids":ids,
                           "confirmed_same_physical_events":None}
    summary["date_only_pairs_without_spatial_certification"] = dict(temporal_counts)
    summary["gfd_scopes_with_unresolved_exact_source_name_links"] = unresolved_gfd
    summary["limitation"] = "IFI geometry unresolved; raw-name-only comparison incomplete for unreconciled identities. No alias substitutions or automatic merging. GFD_PIXEL covers only two Udupi events."
    return summary


def summarize(db, scan_result, boundaries, overlap, inventory, integrity):
    rows = list(db.execute("SELECT state_status,count(*) FROM candidates GROUP BY state_status"))
    temporal, years, precision, intervals = Counter(), Counter(), Counter(), Counter()
    earliest = latest = None
    for payload, in db.execute("SELECT payload FROM candidates"):
        r = json.loads(payload)
        temporal[r["date_status"]] += 1
        if r["date_status"] == "USABLE_REPORTED_DATE_RANGE":
            years[r["source_start_date"][:4]] += 1
            date = r["source_start_date"]
            earliest = min(earliest,date) if earliest else date
            latest = max(latest,date) if latest else date
            duration = r["reported_interval_days_inclusive_assumption"]
            intervals["1 day" if duration == 1 else "2-7 days" if duration <= 7 else "8-30 days" if duration <= 30 else ">30 days"] += 1
        area = r["projected_polygon_area_km2"]
        precision["UNKNOWN" if area is None else "<1 km2" if area < 1 else "1-10 km2" if area < 10 else "10-100 km2" if area < 100 else "100-1000 km2" if area < 1000 else ">=1000 km2"] += 1
    count = sum(n for _,n in rows)
    global_duplicates = db.execute("SELECT count(*),coalesce(sum(rows-1),0),coalesce(sum(conflicting),0) FROM global_ids WHERE rows>1").fetchone()
    candidate_duplicates = db.execute("SELECT count(*),coalesce(sum(n-1),0) FROM (SELECT uuid,count(*) n FROM candidates WHERE uuid IS NOT NULL GROUP BY uuid HAVING n>1)").fetchone()
    identical = db.execute("SELECT count(*),coalesce(sum(n-1),0) FROM (SELECT geom_hash,start,end,count(*) n FROM candidates WHERE geom_hash IS NOT NULL GROUP BY geom_hash,start,end HAVING n>1)").fetchone()
    distinct_candidate_ids = db.execute("SELECT count(DISTINCT uuid) FROM candidates").fetchone()[0]
    single = db.execute("SELECT coalesce(sum(single_district),0) FROM candidates").fetchone()[0]
    usable = db.execute("SELECT coalesce(sum(usable),0) FROM candidates").fetchone()[0]
    assignments = Counter()
    for payload, in db.execute("SELECT payload FROM candidates"):
        row = json.loads(payload)
        assignments["SOLE_SOURCE_DISTRICT_CONTAINMENT" if row["definite_district_id"] else
                    "MULTIPLE_SOURCE_DISTRICT_INTERSECTIONS" if len(row["district_ids"]) > 1 else
                    "SINGLE_PARTIAL_SOURCE_DISTRICT_INTERSECTION" if row["district_ids"] else
                    "NO_CERTIFIED_POSITIVE_AREA_DISTRICT_INTERSECTION"] += 1
    return {"version":VERSION,"archive":integrity,**scan_result,
            "candidate_records":count,"candidate_count_definition":"all valid state intersects plus separately counted invalid/ambiguous bounding-box screens; records are not unique physical events",
            "state_status_counts":dict(rows),"valid_state_intersection_candidates":sum(n for k,n in rows if k!="INVALID_OR_AMBIGUOUS_BBOX_SCREEN"),
            "geographic_temporal_screening_usable":usable,"unambiguous_single_district_screening_usable":single,
            "district_assignment_counts":dict(assignments),"independently_verified_physical_event_count":None,
            "date_status_counts":dict(temporal),"start_year_counts":dict(sorted(years.items())),
            "earliest_candidate_start":earliest,"latest_candidate_start":latest,
            "reported_interval_length_counts":dict(intervals),"reported_polygon_area_bins_not_accuracy":dict(precision),
            "duplicates":{"global_repeated_uuid_groups":global_duplicates[0],"global_excess_uuid_rows":global_duplicates[1],
                          "global_conflicting_uuid_groups":global_duplicates[2],"candidate_distinct_nonempty_uuids":distinct_candidate_ids,
                          "candidate_repeated_uuid_groups":candidate_duplicates[0],"candidate_excess_uuid_rows":candidate_duplicates[1],
                          "candidate_normalized_geometry_date_groups":identical[0],"candidate_excess_geometry_date_rows":identical[1]},
            "overlap_screen":overlap,"inventory_comparison":inventory,"manual_verification_required":count,
            "boundary_basis":{"source":"Survey of India ABDB2025 retained release","districts":len(boundaries['districts']),
                              "current_lgd_verified_identities":boundaries['manifest']['current_lgd_verified_identities'],
                              "nic_exact_name_candidates":boundaries['manifest']['nic_exact_name_candidates'],
                              "geometry_verified":True,"native_crs_from_actual_prj":True,"geometry_publication_authorized":False,
                              "interpretation":"fixed source-release spatial assignments, not event-year or independently current administrative certification"},
            "confidence":"No per-record confidence or article URL supplied. News polygon is reported location, not confirmed inundation extent.",
            "training_readiness":{"decision":"NO-GO","eligible_positive_labels":0,"defensible_negative_labels":0,"model_trained":False,
                                  "blocking_evidence":["no independently adjudicated fixed-unit acquisition/daily flood labels",
                                                       "no verified same-unit full-interval absence evidence",
                                                       "issue-time features, scientific protocol approval and independent held-out labels absent"]}}


def coverage(db, boundaries):
    years = list(range(2000,2027))
    matrix, districts, yearly = [], [], []
    for d in boundaries["districts"]:
        summary = {"source_district_id":d["id"],"source_district_name":d["name"],"nic_exact_name_candidate":d["nic_exact_name"] or "",
                   "supplied_lgd_code_unverified":d["supplied_lgd_code_unverified"],"current_lgd_verified":False}
        totals = Counter()
        for year in years:
            values = db.execute("""SELECT count(*),coalesce(sum(h.definite),0),coalesce(sum(c.single_district),0)
                FROM district_hits h JOIN candidates c ON c.ordinal=h.ordinal
                WHERE h.district_id=? AND substr(c.start,1,4)=? AND json_extract(c.payload,'$.date_status')='USABLE_REPORTED_DATE_RANGE'""", (d["id"],str(year))).fetchone()
            row = {**summary,"year":year,"intersecting_report_records":values[0],"fully_contained_report_records":values[1],
                   "single_district_temporally_usable_records":values[2],"eligible_positive_labels":0,"verified_negative_labels":0,
                   "unreported_unit_days":"UNKNOWN_NOT_NEGATIVE"}
            matrix.append(row)
            totals.update(dict(zip(("intersecting_report_records","fully_contained_report_records","single_district_temporally_usable_records"),values)))
        districts.append({**summary,**totals})
    for year in years:
        result = db.execute("SELECT count(*),coalesce(sum(usable),0),coalesce(sum(single_district),0) FROM candidates WHERE substr(start,1,4)=? AND json_extract(payload,'$.date_status')='USABLE_REPORTED_DATE_RANGE'",(str(year),)).fetchone()
        yearly.append({"start_year":year,"reported_candidates":result[0],"state_contained_temporally_usable":result[1],
                       "single_district_temporally_usable":result[2],"eligible_positive_labels":0,"verified_negative_labels":0})
    return matrix,districts,yearly


def write_csv(path, records):
    iterator = iter(records)
    first = next(iterator,None)
    if first is None:
        path.write_text("")
        return
    with path.open("w",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(first),lineterminator="\n")
        writer.writeheader()
        writer.writerow(first)
        writer.writerows(iterator)


def register_rows(db):
    for ordinal,payload in db.execute("SELECT ordinal,payload FROM candidates ORDER BY ordinal"):
        row = json.loads(payload)
        row["district_ids"] = ";".join(row["district_ids"])
        uuid = db.execute("SELECT rows,conflicting FROM global_ids WHERE uuid=?",(row["source_uuid"],)).fetchone()
        row["global_uuid_rows"] = uuid[0] if uuid else 0
        row["global_uuid_conflict"] = bool(uuid[1]) if uuid else False
        for source in ("IFI","GFD","GFD_PIXEL"):
            row[source.lower()+"_possible_matches"] = db.execute("SELECT count(*) FROM possible_matches WHERE ordinal=? AND source=?",(ordinal,source)).fetchone()[0]
        yield row


def metadata_sample(db, integrity, limit=25):
    """Small ordinal sample, no boundary geometry or per-record district hits."""
    for payload, in db.execute("SELECT payload FROM candidates ORDER BY ordinal LIMIT ?", (limit,)):
        row = json.loads(payload)
        yield {"archive_url": acquisition.URL, "archive_sha256": integrity["sha256"],
               **{key: row[key] for key in ("source_row_ordinal", "source_uuid", "stored_index",
                    "source_start_date", "source_end_date", "state_status", "date_status",
                    "geographic_temporal_screening_usable", "evidence_type", "source_confidence",
                    "manual_verification_required", "flood_label_eligible", "negative_label")},
               "sample_basis": "first 25 candidate source-row ordinals; not representative or adjudicated"}


def build(output=OUTPUT, archive=acquisition.RAW / "groundsource_2026.parquet", batch_size=BATCH_SIZE):
    if output.exists():
        raise ValueError("Completed/partial output exists; never overwrite")
    integrity = acquisition.verify(archive)
    boundaries = load_boundaries()
    output.mkdir(parents=True)
    db = database(output / "audit.sqlite")
    batch_metrics = {"batches":0,"max_batch_rows":0,"max_batch_bytes":0}
    def records():
        for batch in parquet_batches(archive,batch_size):
            batch_metrics["batches"] += 1
            batch_metrics["max_batch_rows"] = max(batch_metrics["max_batch_rows"],batch.num_rows)
            batch_metrics["max_batch_bytes"] = max(batch_metrics["max_batch_bytes"],batch.nbytes)
            yield from batch.to_pylist()
    scanned = scan(records(),db,boundaries)
    if scanned["rows_scanned"] != EXPECTED_ROWS:
        raise ValueError("Pinned archive row count differs")
    overlap = overlap_screen(db)
    inventory = compare_inventories(db,boundaries)
    report = summarize(db,scanned,boundaries,overlap,inventory,integrity)
    matrix,districts,years = coverage(db,boundaries)
    write_csv(output / "candidate_events.csv",register_rows(db))
    write_csv(output / "candidate_metadata_sample.csv",metadata_sample(db,integrity))
    write_csv(output / "district_year_coverage.csv",matrix)
    write_csv(output / "district_coverage.csv",districts)
    write_csv(output / "year_coverage.csv",years)
    write_csv(output / "possible_inventory_matches.csv",({"source_row_ordinal":a,"source":b,"existing_source_id":c,"method":d} for a,b,c,d in db.execute("SELECT * FROM possible_matches ORDER BY ordinal,source,event_id")))
    db.close()
    report["bounded_reader"] = {**batch_metrics,"batch_size":batch_size,"sqlite_cache_mib":32,
                               "peak_process_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                               "all_global_rows_loaded_into_ram":False,"threaded_prefetch":False}
    report["derived_files"] = {p.name:fingerprint(p) for p in output.iterdir() if p.is_file()}
    (output / "report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    sources = {str(archive.relative_to(ROOT)):fingerprint(archive)}
    for p in BOUNDARIES.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))] = fingerprint(p)
    for name in ("data/working/karnataka_flood_events_v1/events.json","data/working/karnataka_flood_outcome_foundation_v1/report.json","data/processed/udupi_flood_spatial_v1/manifest.json","data/processed/udupi_flood_spatial_v1/event_2728.geojson","data/processed/udupi_flood_spatial_v1/event_3551.geojson"):
        sources[name] = fingerprint(ROOT/name)
    import pyarrow,pyproj
    manifest = {"version":VERSION,"files":{p.name:fingerprint(p) for p in output.iterdir() if p.is_file()},
                "sources":sources,"code":{name:fingerprint(Path(__file__).with_name(name)) for name in CODE},
                "runtime":{"pyarrow":pyarrow.__version__,"shapely":shapely.__version__,"pyproj":pyproj.__version__,"geos":shapely.geos_version_string}}
    (output / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return report


def validate(output=OUTPUT, replay=False, public=None):
    manifest = json.loads((output / "manifest.json").read_text())
    import pyarrow,pyproj
    actual_runtime={"pyarrow":pyarrow.__version__,"shapely":shapely.__version__,"pyproj":pyproj.__version__,"geos":shapely.geos_version_string}
    if manifest["runtime"]!=actual_runtime:raise ValueError("Scientific runtime changed; review before replay")
    for name,expected in manifest["files"].items():
        if fingerprint(output/name) != expected:raise ValueError("Derived checksum mismatch: "+name)
    for name,expected in manifest["sources"].items():
        if fingerprint(ROOT/name) != expected:raise ValueError("Original source checksum mismatch: "+name)
    for name,expected in manifest["code"].items():
        if fingerprint(Path(__file__).with_name(name)) != expected:raise ValueError("Processing code changed: "+name)
    acquisition.verify(acquisition.RAW / "groundsource_2026.parquet")
    boundaries = load_boundaries()
    db = database(output / "audit.sqlite",readonly=True)
    report = json.loads((output / "report.json").read_text())
    if db.execute("SELECT count(*) FROM candidates").fetchone()[0] != report["candidate_records"]:
        raise ValueError("Candidate count mismatch")
    matrix,districts,years = coverage(db,boundaries)
    for name,expected in (("district_year_coverage.csv",matrix),("district_coverage.csv",districts),("year_coverage.csv",years)):
        buffer = io.StringIO(newline="");writer=csv.DictWriter(buffer,fieldnames=list(expected[0]),lineterminator="\n");writer.writeheader();writer.writerows(expected)
        if (output/name).read_text()!=buffer.getvalue():raise ValueError("Coverage reproduction mismatch: "+name)
    if replay:
        counts,ordinal,candidates = Counter(),0,0
        for batch in parquet_batches(acquisition.RAW / "groundsource_2026.parquet"):
            for row in batch.to_pylist():
                if not isinstance(row.get("uuid"),str) or not row["uuid"].strip():counts["missing_uuid"]+=1
                status,screening = geometry_screen(row.get("geometry"),boundaries);counts[status]+=1
                stored = db.execute("SELECT payload FROM candidates WHERE ordinal=?",(ordinal,)).fetchone() if screening else None
                if screening:
                    candidates += 1
                    if stored is None or stored[0]!=canonical(record_candidate(row,ordinal,screening)):
                        raise ValueError("Original row-to-candidate replay mismatch")
                ordinal+=1
        if ordinal!=report["rows_scanned"] or candidates!=report["candidate_records"] or dict(counts)!=report["global_geometry_status_counts"]:
            raise ValueError("Global source exclusion/count replay differs")
    db.close()
    if public:
        for name in ("district_year_coverage.csv","district_coverage.csv","year_coverage.csv","report.json","candidate_metadata_sample.csv"):
            if (public/name).read_bytes()!=(output/name).read_bytes():raise ValueError("Public aggregate differs: "+name)
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("build","validate"))
    parser.add_argument("--runtime",type=Path,default=RUNTIME)
    parser.add_argument("--replay",action="store_true",help="read-only full global row/predicate replay")
    parser.add_argument("--public",type=Path)
    args=parser.parse_args()
    if args.runtime.is_dir():sys.path.insert(0,str(args.runtime.resolve()))
    try:
        report=build() if args.command=="build" else validate(replay=args.replay,public=args.public)
        print(json.dumps({k:report[k] for k in ("candidate_records","state_status_counts","geographic_temporal_screening_usable","unambiguous_single_district_screening_usable","duplicates","inventory_comparison","training_readiness")},indent=2))
    except (ValueError,OSError,KeyError,sqlite3.Error) as error:
        parser.exit(2,f"Groundsource audit failed: {error}\n")
