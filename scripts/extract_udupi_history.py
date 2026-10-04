#!/usr/bin/env python3
"""Bounded real-data research extraction; never authenticates, exports or labels days."""
import argparse
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_earth_engine as verification

CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
BOUNDARY_SHAPE_ID = "76128533B4839184447445"
VERSION = "udupi_historical_v1"
EVENTS = [(2728, "2005-09-14", "2005-09-30"), (3551, "2009-09-25", "2009-10-12")]
BATCH_SIZE = 7
RAIN_PIXEL_LIMIT = 10000
WALL_SECONDS = 120
RAIN_FIELDS = ["event_id", "district", "boundary_id", "date", "source_id", "image_id",
               "source_time_start_ms", "units", "mean_mm", "min_mm", "max_mm",
               "valid_pixel_count", "expected_pixel_count", "status",
               "preceding_3d_mm", "preceding_7d_mm", "retrieved_at"]
EVENT_FIELDS = ["event_id", "district", "boundary_id", "source_id", "image_id",
                "start_date", "end_date_inclusive", "source_time_start_ms", "source_time_end_ms",
                "extent_semantics", "processing_scale_m", "partitions_completed",
                "valid_observed_pixels", "mapped_nonpermanent_pixels",
                "positive_observed_pixels", "clear_views_sum", "clear_views_count",
                "finding", "retrieved_at"]
SOURCES = {
    CHIRPS: {"producer": "UCSB Climate Hazards Center", "version": "2.0 Final",
             "url": "https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY",
             "license": "Public domain", "citation": "Funk et al. (2015), doi:10.1038/sdata.2015.66",
             "units": "mm/day", "native_resolution_degrees": 0.05},
    verification.FLOOD_ID: {"producer": "Cloud to Street / Dartmouth Flood Observatory",
             "version": "V1", "url": "https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1",
             "license": "CC BY-NC 4.0; attribution and non-commercial use required",
             "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
             "citation": "Tellman et al. (2021), doi:10.1038/s41586-021-03695-w",
             "native_classification_resolution_m": 250, "catalogue_band_grid_m": 30,
             "units": "binary water classes; counts are processing-grid pixels; clear_views is retained as a source-band sum"},
    verification.BOUNDARY_ID: {"producer": "William & Mary geoLab", "version": "6.0.0 (2023 composite)",
             "url": "https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2",
             "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/"},
}


def event_asset(event_id, start, end):
    return f"{verification.FLOOD_ID}/DFO_{event_id}_From_{start.replace('-', '')}_to_{end.replace('-', '')}"


def dates_between(start, end):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def requested_dates(start, end):
    return dates_between((date.fromisoformat(start) - timedelta(days=14)).isoformat(), end)


def plan():
    return {"project": "floodpulse", "version": VERSION, "district": "Udupi",
            "boundary_asset": verification.BOUNDARY_ID, "boundary_shape_id": BOUNDARY_SHAPE_ID,
            "events": [{"event_id": eid, "image_id": event_asset(eid, start, end),
                        "start_date": start, "end_date_inclusive": end,
                        "rainfall_start_inclusive": requested_dates(start, end)[0],
                        "rainfall_end_exclusive": (date.fromisoformat(end) + timedelta(days=1)).isoformat(),
                        "requested_daily_images": len(requested_dates(start, end))}
                       for eid, start, end in EVENTS],
            "rainfall_source": CHIRPS, "rainfall_batch_size": BATCH_SIZE,
            "rainfall_max_pixels": RAIN_PIXEL_LIMIT, "rainfall_grid": "original CHIRPS native projection/transform",
            "rainfall_reducer": "unweighted mean/min/max/count of native pixel centres inside district",
            "flood_scale_m": 250, "flood_max_pixels_per_partition": verification.PIXEL_LIMIT,
            "flood_crs": verification.GRID_CRS, "flood_transform": verification.GRID_TRANSFORM,
            "bestEffort": False, "per_request_deadline_ms": 10000, "retries": 0,
            "wall_seconds": WALL_SECONDS, "full_flood_collection_scan": False}


def add_lags(rows):
    """Sum t-N through t-1; never include today's or a future day's observation."""
    lookup = {(r["district"], r["source_id"], r["date"]): r for r in rows}
    for row in rows:
        day = date.fromisoformat(row["date"])
        for length in (3, 7):
            preceding = [lookup.get((row["district"], row["source_id"],
                         (day - timedelta(days=i)).isoformat())) for i in range(1, length + 1)]
            row[f"preceding_{length}d_mm"] = (
                sum(r["mean_mm"] for r in preceding)
                if all(r and r["status"] == "available" for r in preceding) else None)
    return rows


def extract_rainfall(ee, geometry, boundary, rows, details):
    reducer = (ee.Reducer.mean().unweighted().combine(ee.Reducer.minMax().unweighted(), sharedInputs=True)
               .combine(ee.Reducer.count().unweighted(), sharedInputs=True))
    for eid, start, end in EVENTS:
        days = requested_dates(start, end)
        collection = (ee.ImageCollection(CHIRPS).filterBounds(geometry)
                      .filterDate(days[0], (date.fromisoformat(end) + timedelta(days=1)).isoformat())
                      .sort("system:time_start"))
        count = collection.size().getInfo()
        if count > len(days):
            raise ValueError(f"CHIRPS {eid}: image count exceeds requested daily budget")
        if not count:
            details.append({"event_id": eid, "image_count": 0, "status": "unavailable"})
            continue
        first = ee.Image(collection.first()).select("precipitation")
        projection = first.projection()
        nominal_scale = projection.nominalScale().getInfo()
        # Keep the exact native transform, with no regridding to a finer district grid.
        grid = projection.getInfo()
        reduction_args = dict(geometry=geometry, crs=grid["crs"], crsTransform=grid["transform"],
                              maxPixels=RAIN_PIXEL_LIMIT, bestEffort=False)
        expected = ee.Image.constant(1).rename("pixels").reduceRegion(
            reducer=ee.Reducer.count().unweighted(), **reduction_args).getInfo()["pixels"]
        details.append({"event_id": eid, "image_count": count, "native_projection": grid,
                        "nominal_scale_m": nominal_scale, "expected_pixel_count": expected})
        images = collection.toList(count)

        def summarize(item):
            image = ee.Image(item)
            stats = image.select("precipitation").reduceRegion(reducer=reducer, **reduction_args)
            props = stats.combine(ee.Dictionary({"image_id": image.id(), "source_time_start_ms": image.get("system:time_start"),
                                                 "date": image.date().format("YYYY-MM-dd")}))
            return ee.Feature(None, props)

        for offset in range(0, count, BATCH_SIZE):
            features = ee.FeatureCollection(images.slice(offset, min(count, offset + BATCH_SIZE)).map(summarize)).getInfo()
            retrieved = verification.now()
            for feature in features["features"]:
                p = feature["properties"]
                mean, valid = p.get("precipitation_mean"), p.get("precipitation_count", 0)
                status = "unavailable" if mean is None or not valid else "available" if valid == expected else "partial_spatial_coverage"
                rows.append({"event_id": eid, "district": "Udupi", "boundary_id": boundary["properties"]["shapeID"],
                             "date": p["date"], "source_id": CHIRPS, "image_id": p["image_id"],
                             "source_time_start_ms": p["source_time_start_ms"], "units": "mm/day",
                             "mean_mm": mean, "min_mm": p.get("precipitation_min"), "max_mm": p.get("precipitation_max"),
                             "valid_pixel_count": valid, "expected_pixel_count": expected, "status": status,
                             "retrieved_at": retrieved})
    add_lags(rows)


def extract_events(ee, geometry, boundary, rows, details):
    partitions = verification.district_partitions(ee, geometry)
    reducer = ee.Reducer.sum().unweighted().combine(ee.Reducer.count().unweighted(), sharedInputs=True)
    for eid, start, end in EVENTS:
        asset = event_asset(eid, start, end)
        image = ee.Image(asset)
        properties = image.toDictionary(image.propertyNames().remove("system:footprint")).getInfo()
        if properties.get("id") != eid:
            raise ValueError(f"Unexpected flood event identity for {asset}")
        for key, expected in (("system:time_start", start), ("system:time_end", end)):
            actual = datetime.fromtimestamp(properties[key] / 1000, timezone.utc).date().isoformat()
            if actual != expected:
                raise ValueError(f"Unexpected {key} for event {eid}: {actual}")
        detail = {"image_id": asset, "properties": properties, "partitions": [], "retrieved_at": verification.now()}
        details.append(detail)
        flooded, permanent, clear = image.select("flooded"), image.select("jrc_perm_water"), image.select("clear_views")
        valid = flooded.mask().And(permanent.mask()).And(clear.mask()).And(clear.gt(0))
        raw = flooded.eq(1).And(permanent.eq(0)).rename("mapped_nonpermanent_flood")
        observed = raw.updateMask(valid).rename("observed_nonpermanent_flood")
        evidence = raw.addBands(observed).addBands(clear.updateMask(valid))
        for index, (region, ownership, window) in enumerate(partitions):
            stats = evidence.updateMask(ownership).reduceRegion(
                reducer=reducer, geometry=region, crs=ee.Projection(verification.GRID_CRS, verification.GRID_TRANSFORM),
                scale=250, maxPixels=verification.PIXEL_LIMIT, bestEffort=False, tileScale=2).getInfo()
            detail["partitions"].append({"partition": index, "half_open_window": window,
                                         "statistics": stats, "retrieved_at": verification.now()})
        detail.update(verification.partitioned_finding(detail))
        detail["retrieved_at"] = verification.now()
        stats = [p["statistics"] for p in detail["partitions"]]
        rows.append({"event_id": eid, "district": "Udupi", "boundary_id": boundary["properties"]["shapeID"],
                     "source_id": verification.FLOOD_ID, "image_id": asset, "start_date": start, "end_date_inclusive": end,
                     "source_time_start_ms": properties["system:time_start"], "source_time_end_ms": properties["system:time_end"],
                     "extent_semantics": "event_window_maximum_not_daily_occurrence", "processing_scale_m": 250,
                     "partitions_completed": len(stats), "valid_observed_pixels": detail["valid_observed_pixels"],
                     "mapped_nonpermanent_pixels": sum(p.get("mapped_nonpermanent_flood_sum") or 0 for p in stats),
                     "positive_observed_pixels": detail["positive_observed_pixels"],
                     "clear_views_sum": sum(p.get("clear_views_sum") or 0 for p in stats),
                     "clear_views_count": sum(p.get("clear_views_count") or 0 for p in stats),
                     "finding": detail["finding"], "retrieved_at": detail["retrieved_at"]})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_timestamp(value):
    return datetime.fromisoformat(value).utcoffset() is not None


def validate(rows, events):
    expected = {day: eid for eid, start, end in EVENTS for day in requested_dates(start, end)}
    seen = set()
    for r in rows:
        key = (r["date"], r["district"], r["source_id"])
        require(key not in seen, "Duplicate rainfall date/district/source key")
        seen.add(key)
        require(r["date"] in expected and r["event_id"] == expected[r["date"]], "Rainfall outside requested event window")
        require(r["district"] == "Udupi" and r["boundary_id"] == BOUNDARY_SHAPE_ID and r["source_id"] == CHIRPS, "Rainfall provenance mismatch")
        require(r["image_id"] == r["date"].replace("-", "") and r["units"] == "mm/day",
                f"Rainfall image ID/units mismatch: {r['image_id']!r}, {r['units']!r}")
        require(datetime.fromtimestamp(r["source_time_start_ms"] / 1000, timezone.utc).date().isoformat() == r["date"], "Rainfall source date mismatch")
        require(valid_timestamp(r["retrieved_at"]), "Missing rainfall retrieval timestamp")
        valid, count = r["valid_pixel_count"], r["expected_pixel_count"]
        require(valid >= 0 and valid == int(valid) and count > 0 and count == int(count) and valid <= count, "Invalid rainfall pixel counts")
        require(r["status"] in ("available", "unavailable", "partial_spatial_coverage"), "Unknown rainfall status")
        if r["status"] == "unavailable":
            require(valid == 0 and all(r[f] is None for f in ("mean_mm", "min_mm", "max_mm")), "Unavailable rainfall must remain null")
        else:
            require(all(isinstance(r[f], (int, float)) and math.isfinite(r[f]) and r[f] >= 0 for f in ("mean_mm", "min_mm", "max_mm")), "Rainfall must be finite and non-negative")
            require(r["min_mm"] <= r["mean_mm"] <= r["max_mm"], "Invalid rainfall summary range")
            require(valid > 0 and (r["status"] == "available") == (valid == count), "Rainfall availability/count mismatch")
    recomputed = add_lags([dict(r) for r in rows])
    for row, reference in zip(rows, recomputed):
        for length in (3, 7):
            actual, correct = row[f"preceding_{length}d_mm"], reference[f"preceding_{length}d_mm"]
            require(actual is None if correct is None else actual is not None and math.isfinite(actual) and math.isclose(actual, correct, rel_tol=1e-12, abs_tol=1e-9), "Incorrect or incomplete preceding rainfall window")
    require(len(events) == len(EVENTS) and len({e["event_id"] for e in events}) == len(EVENTS), "Require exactly the two distinct event-evidence records")
    for e in events:
        spec = next((x for x in EVENTS if x[0] == e["event_id"]), None)
        require(spec is not None, "Unapproved flood event")
        eid, start, end = spec
        require(e["image_id"] == event_asset(*spec) and e["source_id"] == verification.FLOOD_ID and e["boundary_id"] == BOUNDARY_SHAPE_ID and e["district"] == "Udupi", "Flood event provenance mismatch")
        require(e["start_date"] == start and e["end_date_inclusive"] == end, "Flood event dates mismatch")
        for field, day in (("source_time_start_ms", start), ("source_time_end_ms", end)):
            require(datetime.fromtimestamp(e[field] / 1000, timezone.utc).date().isoformat() == day, "Flood event source timestamp mismatch")
        require(e["processing_scale_m"] == 250 and e["partitions_completed"] == 4 and e["extent_semantics"] == "event_window_maximum_not_daily_occurrence", "Incomplete or incompatible flood computation")
        for field in ("valid_observed_pixels", "mapped_nonpermanent_pixels", "positive_observed_pixels", "clear_views_sum", "clear_views_count"):
            require(math.isfinite(e[field]) and e[field] >= 0 and e[field] == int(e[field]), "Invalid flood evidence count")
        require(e["positive_observed_pixels"] <= min(e["valid_observed_pixels"], e["mapped_nonpermanent_pixels"]), "Flood positives exceed eligible pixels")
        require(e["clear_views_count"] == e["valid_observed_pixels"] and e["clear_views_sum"] >= e["clear_views_count"], "Invalid clear-view evidence")
        finding = verification.partitioned_finding({"partitions": [{"statistics": {"observed_nonpermanent_flood_sum": e["positive_observed_pixels"], "observed_nonpermanent_flood_count": e["valid_observed_pixels"]}}] + [{"statistics": {}}] * 3})["finding"]
        require(e["finding"] == finding and valid_timestamp(e["retrieved_at"]), "Flood finding/timestamp mismatch")
    missing = sorted(set(expected) - {r["date"] for r in rows})
    unavailable = [r["date"] for r in rows if r["status"] != "available"]
    return {"rainfall_rows": len(rows), "event_rows": len(events), "requested_dates": len(expected),
            "missing_image_dates": missing, "unavailable_or_partial_dates": unavailable,
            "complete_requested_rainfall": not missing and not unavailable,
            "preceding_3d_totals_available": sum(r["preceding_3d_mm"] is not None for r in rows),
            "preceding_7d_totals_available": sum(r["preceding_7d_mm"] is not None for r in rows)}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_table(path, fields, rows):
    require_not_completed(path.parent)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def read_table(path, fields, integer_fields, float_fields):
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == fields, f"Unexpected schema: {path.name}")
        rows = list(reader)
    for row in rows:
        for key in integer_fields:
            row[key] = int(row[key])
        for key in float_fields:
            row[key] = float(row[key]) if row[key] != "" else None
    return rows


def validate_version(directory):
    """Read and check exact stored bytes; never normalize, repair or change permissions."""
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["version"] == VERSION and manifest["query_parameters"] == plan(), "Manifest version/query mismatch")
    require(manifest["sources"] == SOURCES and manifest["boundary"]["properties"]["shapeID"] == BOUNDARY_SHAPE_ID, "Manifest source/boundary mismatch")
    for name in ("daily_rainfall.csv", "event_evidence.csv"):
        require(checksum(directory / name) == manifest["files"][name]["sha256"], f"Checksum mismatch: {name}")
    rows = read_table(directory / "daily_rainfall.csv", RAIN_FIELDS,
                      ["event_id", "source_time_start_ms", "valid_pixel_count", "expected_pixel_count"],
                      ["mean_mm", "min_mm", "max_mm", "preceding_3d_mm", "preceding_7d_mm"])
    events = read_table(directory / "event_evidence.csv", EVENT_FIELDS,
                       ["event_id", "source_time_start_ms", "source_time_end_ms", "processing_scale_m", "partitions_completed",
                        "valid_observed_pixels", "mapped_nonpermanent_pixels", "positive_observed_pixels", "clear_views_sum", "clear_views_count"], [])
    result = validate(rows, events)
    require(result == manifest["validation"], "Recorded validation differs from tables")
    for e, detail in zip(events, manifest["flood_queries"]):
        require(detail["image_id"] == e["image_id"] and len(detail["partitions"]) == 4, "Event detail provenance mismatch")
        summary = verification.partitioned_finding(detail)
        require(summary["positive_observed_pixels"] == e["positive_observed_pixels"] and summary["valid_observed_pixels"] == e["valid_observed_pixels"], "Partition evidence/table mismatch")
    return result


def require_not_completed(directory):
    """A new output cannot reuse or sit inside a completed dataset, including through symlinks."""
    resolved = Path(directory).resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "manifest.json").is_file():
            raise FileExistsError(f"Writes inside completed dataset are forbidden: {candidate}")


def require_new_output(directory):
    if directory.exists():
        raise FileExistsError(f"Version already exists: {directory}; use --validate-only")
    require_not_completed(directory)


def seal_version(directory):
    """Protect newly published versions from ordinary writes and editor atomic replacement."""
    for path in directory.iterdir():
        if path.is_file():
            path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
    directory.chmod(stat.S_IMODE(directory.stat().st_mode) & ~0o222)


def publish(directory, rows, events, manifest):
    """Validate off to the side; reserve target exclusively so completed versions stay intact."""
    require_new_output(directory)
    manifest["validation"] = validate(rows, events)
    manifest["status"] = "complete_research_extraction" if manifest["validation"]["complete_requested_rainfall"] else "partial_rainfall_coverage"
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".udupi-history-", dir=directory.parent) as staging:
        staged = Path(staging)
        write_table(staged / "daily_rainfall.csv", RAIN_FIELDS, rows)
        write_table(staged / "event_evidence.csv", EVENT_FIELDS, events)
        manifest["files"] = {name: {"sha256": checksum(staged / name), "columns": fields}
                             for name, fields in (("daily_rainfall.csv", RAIN_FIELDS), ("event_evidence.csv", EVENT_FIELDS))}
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        validate_version(staged)
        directory.mkdir()  # No exist_ok: an independently created version is never replaced.
        try:
            for name in ("daily_rainfall.csv", "event_evidence.csv", "manifest.json"):
                os.rename(staged / name, directory / name)
            seal_version(directory)
        except BaseException:
            shutil.rmtree(directory)  # Only this call's newly reserved output, never existing research.
            raise
    return manifest["validation"]


def extract(ee, project):
    manifest = {"version": VERSION, "schema_version": 1, "started_at": verification.now(),
                "project": project, "query_parameters": plan(), "sources": SOURCES,
                "rainfall_queries": [], "flood_queries": [],
                "image_identifiers": "Rainfall image_id is the original collection-relative Earth Engine Image.id(); full asset is source_id/image_id. Flood image_id is the full explicitly selected asset identifier.",
                "table_semantics": {"daily_rainfall.csv": "One returned CHIRPS image per district/date/source. mean_mm/min_mm/max_mm summarize daily precipitation at native pixel centres. Preceding totals have units mm; empty cells denote unavailable values, never zero fill.",
                                    "event_evidence.csv": "One event-window maximum map per original event ID; no daily flood occurrences or negative labels. Evidence counts and clear_views_sum are integer source-band/grid statistics."},
                "observation_criteria": "flooded==1 AND jrc_perm_water==0; all three band masks valid AND clear_views>0",
                "lag_definition": "sum of complete district daily means for t-3..t-1 or t-7..t-1; null if any preceding date/image/pixel coverage is missing",
                "limitations": ["District CHIRPS summaries are gridded estimates, not locality rain-gauge measurements.",
                    "Only precipitation observation dates precede lag dates. Historical product publication times are unknown; retrospective Final values are not verified as-of predictors.",
                    "Modern geoBoundaries district geometry applied to 2005/2009; historical boundary equivalence is unverified.",
                    "Flooded is event-window maximum extent, not daily occurrence or independent ground truth.",
                    "Clouds, masks, event selection and MODIS resolution limit flood evidence; no negative or daily labels are generated.",
                    "Counts use the declared 250 m processing grid with nearest-neighbour source sampling; they are not native area measurements."]}
    rows, events = [], []
    with verification.wall_limit(WALL_SECONDS):
        manifest["access"] = verification.probe_access(ee, project)
        geometry, boundary = verification.find_boundary(ee, verification.PILOTS["Udupi"])
        require(boundary["properties"]["shapeID"] == BOUNDARY_SHAPE_ID, "Verified Udupi boundary identity changed")
        manifest["boundary"] = boundary
        extract_rainfall(ee, geometry, boundary, rows, manifest["rainfall_queries"])
        extract_events(ee, geometry, boundary, events, manifest["flood_queries"])
    manifest["finished_at"] = verification.now()
    manifest["code_sha256"] = {path.name: checksum(path) for path in (Path(__file__), Path(verification.__file__))}
    return rows, events, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="floodpulse", choices=["floodpulse"])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "processed" / VERSION)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(plan(), indent=2))
            return 0
        if args.validate_only:
            result = validate_version(args.output)
        else:
            require_new_output(args.output)
            ee = importlib.import_module("ee")
            rows, events, manifest = extract(ee, args.project)
            result = publish(args.output, rows, events, manifest)
        print(json.dumps({"output": str(args.output), "validation": result}, indent=2))
        return 0 if result["complete_requested_rainfall"] else 2
    except (Exception, verification.VerificationDeadlineExceeded) as exc:
        print(json.dumps({"status": "failed_no_version_published", "error": {"type": type(exc).__name__, "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
