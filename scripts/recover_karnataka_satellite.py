#!/usr/bin/env python3
"""Recover only the frozen five-event Stage 3B selection; keep v1 read-only.

The demonstrated maxPixels workload includes repeated single-input reductions
across bands. Plan band-pixels, not only spatial cells. Source-native geographic
grid origins are NOT substituted for the verified Udupi 250 m UTM grid.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_karnataka_satellite as legacy

ROOT = legacy.ROOT
IDS = [3160, 2690, 4382, 3652, 4508]
BANDS = ["flooded", "duration", "clear_views", "clear_perc", "jrc_perm_water"]
METRICS = ["region_pixels", "valid_pixels", "qualifying_pixels", "mapped_water_pixels",
           "permanent_water_pixels", "clear_views_sum", "clear_perc_sum", "clear_perc_count",
           "duration_sum", "duration_count"]
TARGET_LOAD = 90000
SAFETY_FACTOR = 1.25
MAX_PARTITIONS = 128
ALIGNMENT = "nearest-neighbour data AND masks on the unchanged Udupi-compatible EPSG:32643 250 m grid; no bilinear/bicubic"
STATUSES = {"satellite_positive", "observed_no_qualifying_floodwater", "insufficient_observation",
            "candidate_mismatch", "incomplete_computation", "not_reviewed"}


def elapsed_clock():
    """Linux boottime includes suspend; monotonic/ITIMER_REAL do not.

    The wall-clock fallback is conservative if CLOCK_BOOTTIME is unavailable.
    Signal deadlines still bound active execution; acceptance/retry guards also
    account for suspension before any result is accepted or new request starts.
    """
    return time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else time.time()


def parse_projection(value):
    p = value["projection"]
    transform = p["transform"]
    legacy.require(isinstance(p["crs"], str) and len(transform) == 6 and
                   all(math.isfinite(n) for n in transform), "Invalid projection metadata")
    a, b, _, d, e, _ = transform
    legacy.require(abs(a * e - b * d) > 0 and math.isfinite(value["nominal_scale_m"]) and
                   value["nominal_scale_m"] > 0, "Invalid projection scale/affine")
    return {"crs": p["crs"], "transform": list(transform), "nominal_scale_m": value["nominal_scale_m"]}


def analysis_grid(source):
    """Derive the scale from flooded.atScale(250), align into verified UTM origin.

    This deliberately retains the published Udupi processing grid rather than
    adopting a different native CRS/origin merely because nominal scales match.
    """
    reference = parse_projection(source["flooded_at_scale_250"])
    grid = parse_projection(source["analysis"])
    legacy.require(abs(reference["nominal_scale_m"] - 250) < 1e-8, "Source analysis scale changed")
    legacy.require(grid["crs"] == legacy.CRS and grid["transform"] == legacy.TRANSFORM and
                   abs(grid["nominal_scale_m"] - 250) < 1e-8, "Udupi compatibility grid changed")
    native = {name: parse_projection(source["bands"][name]) for name in BANDS}
    return {**grid, "source_flooded_at_scale_250": reference, "source_band_projections": native,
            "mixed_source_projections": any(p != native["flooded"] for p in native.values()),
            "alignment": ALIGNMENT, "derivation": "flooded.projection().atScale(250) sets scale; flooded aligned to verified UTM grid then .projection().atScale(250) sets analysis projection"}


def planner(bounds, grid, band_count=len(METRICS), safety=SAFETY_FACTOR, target=TARGET_LOAD):
    legacy.require(type(band_count) is int and band_count > 0 and safety >= 1 and 0 < target <= TARGET_LOAD,
                   "Invalid band-pixel safety budget")
    a, b, c, d, e, f = grid["transform"]
    legacy.require(grid["crs"] == legacy.CRS and a == 250 and e == -250 and b == d == 0,
                   "Planner requires the verified axis-aligned 250 m metric grid")
    legacy.require(len(bounds) >= 4 and all(math.isfinite(n) for p in bounds for n in p), "Invalid region bounds")
    cols, rows = [(p[0] - c) / a for p in bounds], [(p[1] - f) / e for p in bounds]
    x0, x1, y0, y1 = math.floor(min(cols)), math.ceil(max(cols)), math.floor(min(rows)), math.ceil(max(rows))
    legacy.require(x0 < x1 and y0 < y1, "Empty planning region")
    side = math.floor(math.sqrt(target / (band_count * safety)))
    legacy.require(side > 0, "No safe partition size")
    parts = []
    for x in range(x0, x1, side):
        for y in range(y0, y1, side):
            window = [x, min(x + side, x1), y, min(y + side, y1)]
            spatial = (window[1] - x) * (window[3] - y)
            parts.append({"index": len(parts), "window": window, "spatial_cell_bound": spatial,
                          "band_pixel_bound": spatial * band_count, "safe_workload_bound": math.ceil(spatial * band_count * safety)})
    legacy.require(len(parts) <= MAX_PARTITIONS, "Region exceeds bounded partition count")
    report = {"analysis_crs": grid["crs"], "analysis_scale_m": 250, "transform": grid["transform"],
              "pixel_area_m2": abs(a * e), "band_count": band_count, "safety_factor": safety,
              "target_band_pixels": target, "maxPixels": legacy.MAX_PIXELS, "chunk_cells": side,
              "partitions": parts, "partition_count": len(parts),
              "maximum_expected_partition_cells": max(p["spatial_cell_bound"] for p in parts),
              "maximum_safe_workload": max(p["safe_workload_bound"] for p in parts)}
    guard(report)
    return report


def guard(report):
    legacy.require(report["maxPixels"] == 300000 and report["target_band_pixels"] <= TARGET_LOAD and
                   report["safety_factor"] >= SAFETY_FACTOR, "Preflight safety parameters changed")
    legacy.require(all(p["safe_workload_bound"] <= report["target_band_pixels"] < report["maxPixels"]
                       for p in report["partitions"]), "Unsafe preflight partition workload")
    for p in report["partitions"]:
        x0, x1, y0, y1 = p["window"]
        spatial = (x1 - x0) * (y1 - y0)
        legacy.require(spatial > 0 and p["spatial_cell_bound"] == spatial and
                       p["band_pixel_bound"] == spatial * report["band_count"] and
                       p["safe_workload_bound"] == math.ceil(spatial * report["band_count"] * report["safety_factor"]),
                       "Inconsistent preflight cell estimates")


def reducer_parameters(grid):
    # crsTransform and scale are mutually exclusive. The affine fixes both 250 m
    # resolution and phase; crs + scale alone need not document the full grid.
    return {"crs": grid["crs"], "crsTransform": grid["transform"], "maxPixels": 300000,
            "bestEffort": False, "tileScale": 2}


def outcome(parts, expected):
    good = [p["statistics"] for p in parts if "statistics" in p]
    complete = len(good) == expected and expected > 0
    if not good:
        return {"evidence_status": "incomplete_computation", "computation_complete": False,
                "counts_are_lower_bounds": True, "statistics": None, "valid_fraction": None,
                "clear_views_mean_valid": None, "clear_perc_mean_valid": None, "duration_mean_qualifying": None}
    result = legacy.finding(parts, expected)
    if not complete:
        result["evidence_status"] = "incomplete_computation"
    return result


def validate_part(part, plan):
    stats = part["statistics"]
    for name in METRICS:
        legacy.require(name in stats and stats[name] is not None and math.isfinite(stats[name]) and stats[name] >= 0,
                       "Missing/nonfinite reduction statistic")
    for name in METRICS[:5]:
        legacy.require(float(stats[name]).is_integer(), "Fractional pixel count")
    legacy.require(stats["qualifying_pixels"] <= stats["valid_pixels"] <= stats["region_pixels"] <= plan["spatial_cell_bound"],
                   "Actual cells disagree with preflight geometry/grid")
    legacy.require(stats["region_pixels"] * len(METRICS) <= plan["band_pixel_bound"], "Actual band workload exceeds plan")


def udupi_gate(directory, grid):
    """Read-only nearest alignment identity test on the actual protected grid."""
    import numpy as np
    import rasterio
    from affine import Affine
    from rasterio.warp import reproject, Resampling
    reference = legacy.regression(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    alignment_checks = {}
    for event in manifest["events"]:
        with rasterio.open(directory / event["raster_file"]) as src:
            a, b, c, d, e, f = grid["transform"]
            legacy.require(src.crs.to_string() == grid["crs"] and src.transform.a == a and src.transform.e == e,
                           "Udupi gate CRS/resolution changed")
            col, row = (src.transform.c - c) / a, (src.transform.f - f) / e
            legacy.require(col.is_integer() and row.is_integer(), "Udupi grid origin incompatible")
            target = Affine(*grid["transform"]) @ Affine.translation(col, row)
            legacy.require(target == src.transform, "Udupi grid phase changed")
            values = src.read()
            for index in range(3):
                aligned = np.full(values[index].shape, -9999, dtype=values.dtype)
                reproject(values[index], aligned, src_transform=src.transform, src_crs=src.crs, src_nodata=-9999,
                          dst_transform=target, dst_crs=grid["crs"], dst_nodata=-9999, resampling=Resampling.nearest)
                legacy.require(np.array_equal(values[index], aligned), "Udupi categorical alignment changed evidence")
            alignment_checks[str(event["event_id"])] = "three protected bands reproduced exactly in memory"
    return {"qualified_pixels": reference, "nearest_alignment": alignment_checks, "files_modified": 0}


class BoundedEE:
    def __init__(self, raw, deadline=60, total=900):
        legacy.require(1 <= deadline <= 60 and 1 <= total <= 900, "Invalid recovery request limits")
        self.raw, self.deadline, self.total, self.start = raw, deadline, total, elapsed_clock()
        os.environ["NO_GCE_CHECK"] = "true"
        import ee
        self.ee = ee

    def request(self, fn, name):
        import verify_earth_engine as verification
        import extract_karnataka_rainfall as retry
        def sleep(seconds):
            legacy.require(elapsed_clock() - self.start + seconds < self.total, "Total recovery deadline reached")
            time.sleep(seconds)
        def call():
            request_start = elapsed_clock()
            remaining = self.total - (request_start - self.start)
            legacy.require(remaining > 0, "Total recovery deadline reached")
            try:
                with verification.wall_limit(min(self.deadline, remaining)):
                    result = fn()
                legacy.require(elapsed_clock() - self.start < self.total, "Total recovery deadline reached after host pause")
                if elapsed_clock() - request_start > self.deadline:
                    raise TimeoutError("Request exceeded pause-inclusive deadline; late result rejected")
                return result
            except verification.VerificationDeadlineExceeded:
                raise TimeoutError("Recovery request exceeded deadline") from None
            except Exception as exc:
                with (self.raw / "provider_errors.jsonl").open("a") as handle:
                    handle.write(json.dumps({"operation": name, "retrieved_at": legacy.now(), **legacy.provider_error(exc)}) + "\n")
                raise
        return retry.bounded_request(call, name, self.raw / "requests.jsonl", sleep=sleep)

    def initialize(self):
        self.ee.data.setMaxRetries(0)
        self.request(lambda: self.ee.Initialize(project="floodpulse"), "initialize")
        self.request(lambda: self.ee.data.setDeadline(self.deadline * 1000), "deadline")


def projection_metadata(session, image, eid):
    ee = session.ee
    native = image.select("flooded").projection().atScale(250)
    compatibility = ee.Projection(legacy.CRS, legacy.TRANSFORM).atScale(native.nominalScale())
    aligned_flooded = image.select("flooded").reproject(crs=compatibility)
    projection = aligned_flooded.projection().atScale(250)
    def metadata(p):
        return ee.Dictionary({"projection": p, "nominal_scale_m": p.nominalScale()})
    source = session.request(lambda: ee.Dictionary({"id": image.get("id"),
        "bands": ee.Dictionary({b: metadata(image.select(b).projection()) for b in BANDS}),
        "flooded_at_scale_250": metadata(native), "analysis": metadata(projection),
        "aligned_mask_projection": metadata(aligned_flooded.mask().projection())}).getInfo(), f"projection:{eid}")
    legacy.require(source["id"] == eid, "Source event ID mismatch")
    return projection, source, analysis_grid(source)


def preflight(session, selection, projection, grid):
    ee = session.ee
    feature = ee.FeatureCollection(legacy.BOUNDARY).filter(ee.Filter.eq("shapeID", selection["review_region"]["shapeID"]))
    geom = feature.geometry()
    region = session.request(lambda: ee.Dictionary({"count": feature.size(), "geometry": geom,
        "area_km2": geom.area(1).divide(1e6), "bounds": geom.bounds(1, ee.Projection(grid["crs"])).coordinates()}).getInfo(),
        f"region:{selection['gfd_id']}")
    legacy.require(region["count"] == 1 and 0 < region["area_km2"] <= 20000, "Invalid public review region")
    plan = planner(region["bounds"][0], grid)
    coordinates = ee.Image.pixelCoordinates(projection)
    regions, owners, metadata = [], [], []
    for part in plan["partitions"]:
        x0, x1, y0, y1 = part["window"]
        a, _, c, _, e, f = grid["transform"]
        rectangle = ee.Geometry.Rectangle([c + x0 * a, f + y1 * e, c + x1 * a, f + y0 * e], proj=grid["crs"], geodesic=False)
        clipped = geom.intersection(rectangle, 1)
        regions.append(clipped)
        owners.append(coordinates.select("x").gte(x0).And(coordinates.select("x").lt(x1)).And(
            coordinates.select("y").gte(y0)).And(coordinates.select("y").lt(y1)))
        metadata.append(ee.Dictionary({"index": part["index"], "geometry": clipped, "area_m2": clipped.area(1),
                                      "outside_area_m2": clipped.difference(geom, 1).area(1)}))
    # Pairs whose closed grid rectangles touch; other pairs cannot overlap.
    pairs = []
    for i, first in enumerate(plan["partitions"]):
        for j in range(i + 1, len(regions)):
            second = plan["partitions"][j]
            x0, x1, y0, y1 = first["window"]; a0, a1, b0, b1 = second["window"]
            if max(x0, a0) <= min(x1, a1) and max(y0, b0) <= min(y1, b1):
                pairs.append(ee.Dictionary({"pair": [i, j], "area_m2": regions[i].intersection(regions[j], 1).area(1)}))
    union = ee.FeatureCollection([ee.Feature(r) for r in regions]).geometry()
    geometry_check = session.request(lambda: ee.Dictionary({"partitions": metadata, "touching_pair_overlaps": pairs,
        "gap_area_m2": geom.difference(union, 1).area(1), "excess_area_m2": union.difference(geom, 1).area(1)}).getInfo(),
        f"preflight_geometry:{selection['gfd_id']}")
    plan.update(event_id=selection["gfd_id"], region=region, geometry_check=geometry_check)
    check_geometry(plan)
    return plan, regions, owners


def check_geometry(plan):
    guard(plan)
    check = plan["geometry_check"]
    legacy.require(len(check["partitions"]) == plan["partition_count"] and
                   [p["index"] for p in check["partitions"]] == list(range(plan["partition_count"])), "Geometry/plan mismatch")
    region_area = plan["region"]["area_km2"] * 1e6
    summed = sum(p["area_m2"] for p in check["partitions"])
    legacy.require(abs(summed - region_area) <= max(1, region_area * 1e-8), "Partition area conservation failed")
    legacy.require(check["gap_area_m2"] <= 1 and check["excess_area_m2"] <= 1 and
                   all(p["outside_area_m2"] <= 1 for p in check["partitions"]) and
                   all(p["area_m2"] <= 1 for p in check["touching_pair_overlaps"]), "Partition overlap/gap/outside region")


def evidence_image(ee, image, projection):
    # reproject uses default nearest neighbour for data and masks. Never call
    # resample('bilinear')/('bicubic') on these flags or observation masks.
    aligned = {name: image.select(name).reproject(crs=projection) for name in BANDS}
    flooded, permanent, clear = [aligned[b] for b in ("flooded", "jrc_perm_water", "clear_views")]
    valid = flooded.mask().And(permanent.mask()).And(clear.mask()).And(clear.gt(0))
    qualified = flooded.eq(1).And(permanent.eq(0)).And(valid)
    def band(value, name):
        return value.unmask(0, sameFootprint=False).rename(name).reproject(crs=projection)
    return ee.Image.constant(1).rename("region_pixels").reproject(crs=projection).addBands([
        band(valid, "valid_pixels"), band(qualified, "qualifying_pixels"),
        band(flooded.eq(1).And(valid), "mapped_water_pixels"), band(permanent.eq(1).And(valid), "permanent_water_pixels"),
        band(clear.updateMask(valid), "clear_views_sum"), band(aligned["clear_perc"].updateMask(valid), "clear_perc_sum"),
        band(aligned["clear_perc"].mask().And(valid), "clear_perc_count"),
        band(aligned["duration"].updateMask(qualified), "duration_sum"),
        band(aligned["duration"].mask().And(qualified), "duration_count")])


def review_event(session, selection, record):
    ee = session.ee; eid = selection["gfd_id"]
    image = ee.Image(selection["image_id"])
    projection, source, grid = projection_metadata(session, image, eid)
    record.update(source_projection_metadata=source, analysis_grid=grid)
    plan, regions, owners = preflight(session, selection, projection, grid)
    legacy.write_new(session.raw / f"event_{eid}_preflight.json", plan)
    record["preflight"] = plan
    evidence = evidence_image(ee, image, projection)
    try:
        for index, part_plan in enumerate(plan["partitions"]):
            part = {"index": index, "window": part_plan["window"]}; record["partitions"].append(part)
            if plan["geometry_check"]["partitions"][index]["area_m2"] == 0:
                part.update(statistics=dict.fromkeys(METRICS, 0), empty_geometry_skipped=True)
            else:
                expression = evidence.updateMask(owners[index]).reduceRegion(
                    reducer=ee.Reducer.sum().unweighted(), geometry=regions[index], **reducer_parameters(grid))
                part["reduction_expression_sha256"] = hashlib.sha256(expression.serialize().encode()).hexdigest()
                result = session.request(lambda: expression.getInfo(), f"reduce:{eid}:{index}")
                # Null sums in an empty/masked band are zero counted cells, never
                # zero environmental measurements. region_pixels validates scope.
                part["statistics"] = {name: result.get(name) or 0 for name in METRICS}
            try:
                validate_part(part, part_plan)
            except Exception:
                # Retain an inconsistent provider response for diagnosis, but do
                # not accumulate it as accepted scientific evidence.
                part["rejected_statistics"] = part.pop("statistics")
                raise
            record.update(outcome(record["partitions"], plan["partition_count"]), retrieved_at=legacy.now())
            with (session.raw / "progress.jsonl").open("a") as handle:
                handle.write(json.dumps({"gfd_id": eid, "partition": part, "retrieved_at": record["retrieved_at"],
                    "event_summary": outcome(record["partitions"], plan["partition_count"])}, allow_nan=False) + "\n")
    except Exception as exc:
        if record["partitions"]:
            record["partitions"][-1]["error"] = legacy.provider_error(exc)
        record.update(outcome(record["partitions"], plan["partition_count"]), error=legacy.provider_error(exc))
        raise


def recover(previous, diagnostic, output, raw, deadline=60, total=900):
    legacy.require(not output.exists() and not raw.exists(), "Recovery version exists; never overwrite")
    legacy.require(not any((p / "manifest.json").exists() for path in [output, raw] for p in path.resolve().parents),
                   "Cannot write inside an existing completed version")
    legacy.validate(previous)
    selections = json.loads((previous / "event_evidence.json").read_text())
    legacy.require([r["gfd_id"] for r in selections] == IDS, "Frozen selection changed")
    raw.mkdir(parents=True, exist_ok=False)
    records = [{k: r[k] for k in ("gfd_id", "image_id", "ifi_project_event_id", "ifi_source_event_id", "ifi_start",
                "ifi_end_inclusive", "gfd_start", "gfd_end_inclusive", "review_region", "association_status", "ifi_confirmation", "semantics")}
               | {"evidence_status": "not_reviewed", "partitions": []} for r in selections]
    access, reference = {}, None
    try:
        session = BoundedEE(raw, deadline, total); session.initialize()
        access["initialization_succeeded"] = True
        # Before any new source flood reduction: fixed-grid identity alignment gate.
        reference = udupi_gate(ROOT / "data/processed/udupi_flood_spatial_v1",
                               {"crs": legacy.CRS, "transform": legacy.TRANSFORM})
        review_event(session, selections[0], records[0])
        legacy.require(records[0]["computation_complete"], "Event 3160 regression gate incomplete")
        reference = udupi_gate(ROOT / "data/processed/udupi_flood_spatial_v1", records[0]["analysis_grid"])
        access["both_gates_passed"] = True
        for selection, record in zip(selections[1:], records[1:]):
            review_event(session, selection, record)
            legacy.require(record["computation_complete"], "Remaining event computation incomplete")
    except Exception as exc:
        access["stopped_error"] = legacy.provider_error(exc)
        active = next((r for r in records if not r.get("computation_complete")), None)
        if active is not None and active["evidence_status"] == "not_reviewed":
            active.update(evidence_status="incomplete_computation", error=legacy.provider_error(exc))
    finally:
        access["finished_at"] = legacy.now()
        legacy.write_new(raw / "access.json", access)
    output.mkdir(parents=True, exist_ok=False)
    # Copy exact candidate bytes from v1; do not rebuild or reformat relationships.
    with (output / "candidates.json").open("xb") as handle:
        handle.write((previous / "candidates.json").read_bytes())
    legacy.write_new(output / "event_evidence.json", records)
    diag_files = {str(p.resolve()): legacy.fingerprint(p) for p in diagnostic.iterdir() if p.is_file()}
    manifest = {"version": output.name, "schema_version": 2, "created_at": legacy.now(), "project": "floodpulse",
        "source": legacy.SOURCE, "boundary_source": legacy.BOUNDARY, "source_license": "CC BY-NC 4.0",
        "attribution": "Cloud to Street / Dartmouth Flood Observatory; Tellman et al. (2021), doi:10.1038/s41586-021-03695-w; IFI Saharia et al., doi:10.5281/zenodo.16994648",
        "boundary_license": "CC BY 4.0; geoBoundaries v6.0.0, William & Mary geoLab",
        "previous": str(previous.resolve()), "previous_files": {n: legacy.fingerprint(previous / n) for n in ["candidates.json", "event_evidence.json", "manifest.json"]},
        "diagnostic_files": diag_files, "parameters": {"deadline_seconds": deadline, "total_seconds": total,
        "max_attempts": 3, "backoff_seconds": [2, 4], "scale_m": 250, "crs": legacy.CRS, "transform": legacy.TRANSFORM,
        "maxPixels": 300000, "bestEffort": False, "target_band_pixels": TARGET_LOAD, "safety_factor": SAFETY_FACTOR,
        "metric_band_count": len(METRICS), "alignment": ALIGNMENT}, "access": access, "udupi_gate": reference,
        "event_ids": IDS, "candidate_relationships_unchanged": True, "semantics": "event_window_maximum_not_daily_labels; IFI associations remain provisional",
        "summary": summarize(records), "files": {n: legacy.fingerprint(output / n) for n in ["candidates.json", "event_evidence.json"]},
        "raw_files": {str(p.resolve()): legacy.fingerprint(p) for p in raw.iterdir() if p.is_file()}}
    legacy.write_new(output / "manifest.json", manifest)
    return validate(output)


def summarize(records):
    return {"selected": len(records), "complete_events": sum(r.get("computation_complete", False) for r in records),
            "status_counts": {s: sum(r["evidence_status"] == s for r in records) for s in sorted(STATUSES)},
            "qualifying_pixel_total": sum((r.get("statistics") or {}).get("qualifying_pixels", 0) for r in records),
            "valid_observation_total": sum((r.get("statistics") or {}).get("valid_pixels", 0) for r in records),
            "ifi_confirmations": 0, "daily_labels_created": 0}


def validate(output):
    manifest = json.loads((output / "manifest.json").read_text())
    legacy.require(manifest["source"] == legacy.SOURCE and manifest["event_ids"] == IDS, "Recovery source/selection changed")
    previous = Path(manifest["previous"])
    legacy.validate(previous)
    for key in ["diagnostic_files", "raw_files"]:
        for name, expected in manifest[key].items():
            legacy.require(legacy.fingerprint(Path(name)) == expected, "Retained recovery source checksum changed")
    for key, folder in [("previous_files", previous), ("files", output)]:
        for name, expected in manifest[key].items():
            legacy.require(Path(name).name == name and legacy.fingerprint(folder / name) == expected, "Recovery file checksum changed")
    legacy.require((output / "candidates.json").read_bytes() == (previous / "candidates.json").read_bytes(), "Candidate bytes changed")
    records = json.loads((output / "event_evidence.json").read_text())
    original = json.loads((previous / "event_evidence.json").read_text())
    legacy.require([r["gfd_id"] for r in records] == IDS, "Recovery event order changed")
    for record, old in zip(records, original):
        for key in ["image_id", "ifi_project_event_id", "ifi_start", "ifi_end_inclusive", "gfd_start", "gfd_end_inclusive", "review_region"]:
            legacy.require(record[key] == old[key], "Recovery source identity/region changed")
        legacy.require(record["evidence_status"] in STATUSES and record["ifi_confirmation"] is False, "Invalid recovery status/promotion")
        if "preflight" in record:
            grid = analysis_grid(record["source_projection_metadata"])
            legacy.require(grid == record["analysis_grid"], "Analysis grid changed")
            plan = planner(record["preflight"]["region"]["bounds"][0], grid)
            for key in plan:
                legacy.require(record["preflight"][key] == plan[key], "Preflight reconstruction mismatch")
            check_geometry(record["preflight"])
            for index, part in enumerate(record["partitions"]):
                legacy.require(part["index"] == index and part["window"] == plan["partitions"][index]["window"], "Duplicate/changed ownership")
                if "statistics" in part:
                    validate_part(part, plan["partitions"][index])
            result = outcome(record["partitions"], plan["partition_count"])
            for key, value in result.items():
                legacy.require(record[key] == value, "Recovery statistics/status changed")
        if record.get("computation_complete"):
            legacy.require(manifest["udupi_gate"]["qualified_pixels"] == {"2728": 33, "3551": 23}, "Udupi gate missing")
    if manifest["udupi_gate"] is not None:
        legacy.require(udupi_gate(ROOT / "data/processed/udupi_flood_spatial_v1", {"crs": legacy.CRS, "transform": legacy.TRANSFORM}) == manifest["udupi_gate"], "Udupi recovery gate changed")
    result = summarize(records)
    legacy.require(manifest["summary"] == result, "Recovery summary mismatch")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--previous", type=Path, default=ROOT / "data/working/karnataka_satellite_event_evidence_v1")
    parser.add_argument("--diagnostic", type=Path, default=ROOT / "data/raw/flood_satellite/stage3b_grid_diagnostic_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "data/working/karnataka_satellite_event_evidence_v2")
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/flood_satellite/stage3b_grid_recovery_v1")
    parser.add_argument("--deadline", type=int, default=60)
    parser.add_argument("--total-seconds", type=int, default=900)
    args = parser.parse_args()
    result = validate(args.validate_only) if args.validate_only else recover(args.previous, args.diagnostic, args.output, args.raw, args.deadline, args.total_seconds)
    print(json.dumps(result, indent=2), flush=True)
    if not args.validate_only and json.loads((args.output / "manifest.json").read_text())["access"].get("stopped_error"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
