#!/usr/bin/env python3
"""First bounded GFD batch; temporal candidates are never IFI confirmations.

Retained official IFI/GFD metadata can be reprocessed entirely offline. Only
public geoBoundaries geometry is sent to EE. Completed outputs are read-only.
Detailed evidence stays local under data/working (CC BY-NC 4.0).
"""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1"
BOUNDARY = "WM/geoLab/geoBoundaries/600/ADM2"
COVERAGE = ("2000-02-17", "2018-12-10")
WINDOW = [73.5, 11, 79, 19]  # Public search window, not an administrative polygon.
CRS = "EPSG:32643"
TRANSFORM = [250, 0, 0, 0, -250, 0]
MAX_PIXELS = 300000
CELL_CHUNK = 300  # <=90,000 grid cells per partition, fixed 250 m grid.
MIN_VALID_FRACTION = 0.95  # Conservative research gate; NOT a validated negative label.
EVIDENCE = {"satellite_positive", "observed_no_qualifying_floodwater",
            "insufficient_observation", "candidate_mismatch", "not_reviewed"}
CANDIDATE = {"strong_temporal_candidate", "possible_temporal_candidate", "ambiguous",
             "no_candidate", "outside_gfd_coverage", "invalid_ifi_window"}
SELECTION = ("Eligible: IFI Karnataka-only, original exact comma-separated district token "
             "has one public geoBoundaries feature, IFI temporal coverage >=80%; exclude "
             "reference IDs 2728/3551. Greedy prefer new years then new regions, fewer "
             "Jaccard temporal overlap, fewer source district tokens, greater IFI overlap fraction, "
             "shorter GFD window; tie-break GFD ID, IFI ID, exact region name. "
             "One region per new GFD ID; no raster outcomes enter selection.")


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def packed(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def write_new(path, value):
    path = Path(path)
    require(not any((p / "manifest.json").exists() for p in path.parents),
            "Cannot write within a completed version")
    with path.open("xb") as handle:
        handle.write(packed(value))


def window_status(row):
    a, b = row["parsed_start_date"], row["parsed_end_date_inclusive"]
    if not a or not b:
        return "undated"
    date.fromisoformat(a); date.fromisoformat(b)
    if a > b:
        return "invalid_reversed"
    return "within_gfd_coverage" if a <= COVERAGE[1] and b >= COVERAGE[0] else "outside_gfd_coverage"


def overlap(a, b, c, d):
    dates = [date.fromisoformat(v) for v in (a, b, c, d)]
    a, b, c, d = dates
    require(a <= b and c <= d, "Reversed event window")
    days = max(0, (min(b, d) - max(a, c)).days + 1)
    return {"days": days, "ifi_fraction": days / ((b - a).days + 1),
            "jaccard": days / ((max(b, d) - min(a, c)).days + 1)}


def metadata_events(inventory):
    require(inventory["source"] == SOURCE and inventory["window"] == WINDOW, "Wrong GFD metadata scope")
    response = inventory["response"]
    require(response["count"] == len(response["images"]) <= inventory["limit"] <= 128,
            "Truncated or oversized metadata inventory")
    result = []
    for props in response["images"]:
        match = re.fullmatch(r"DFO_(\d+)_From_(\d{8})_to_(\d{8})", props["system:index"])
        require(match and int(match[1]) == props["id"], "GFD image identity mismatch")
        a, b = [datetime.strptime(match[i], "%Y%m%d").date().isoformat() for i in (2, 3)]
        require(a <= b, "Reversed GFD dates")
        for key, value in [("system:time_start", a), ("system:time_end", b)]:
            require(datetime.fromtimestamp(props[key] / 1000, timezone.utc).date().isoformat() == value,
                    "GFD metadata timestamp differs from original image ID")
        result.append({"gfd_id": props["id"], "image_id": SOURCE + "/" + props["system:index"],
                       "gfd_start": a, "gfd_end_inclusive": b, "original_properties": props})
    require(len({r["gfd_id"] for r in result}) == len(result), "Duplicate GFD IDs")
    return sorted(result, key=lambda r: r["gfd_id"])


def candidates(rows, inventory):
    events = metadata_events(inventory)
    require(len({r["project_event_id"] for r in rows}) == len(rows), "Duplicate IFI project IDs")
    output = []
    for row in rows:
        base = {"ifi_project_event_id": row["project_event_id"], "ifi_source_event_id": row["ifi_source_event_id"],
                "ifi_original_start": row["source_start_date"], "ifi_original_end": row["source_end_date"],
                "ifi_start": row["parsed_start_date"], "ifi_end_inclusive": row["parsed_end_date_inclusive"],
                "ifi_district_tokens_original": row["source_districts"], "ifi_state_original": row["source_state"],
                "satellite_confirmation": False, "association_status": "provisional_temporal_only"}
        status = window_status(row)
        matches = []
        if status == "within_gfd_coverage":
            for event in events:
                props = event["original_properties"]
                # Country metadata identifies India, never a verified district extent.
                if "IND" not in {s.strip() for s in str(props.get("cc", "")).split(",")}:
                    continue
                timing = overlap(base["ifi_start"], base["ifi_end_inclusive"], event["gfd_start"], event["gfd_end_inclusive"])
                if timing["days"]:
                    matches.append({**base, **event, "temporal_overlap": timing})
        for match in matches:
            strength = "strong_temporal_candidate" if match["temporal_overlap"]["ifi_fraction"] >= 0.8 else "possible_temporal_candidate"
            match.update(temporal_strength=strength, candidate_status="ambiguous" if len(matches) > 1 else strength,
                         reason="India metadata + public-window footprint + inclusive temporal overlap; spatial IFI association unverified")
        if not matches:
            label = {"within_gfd_coverage": "no_candidate", "outside_gfd_coverage": "outside_gfd_coverage",
                     "undated": "invalid_ifi_window", "invalid_reversed": "invalid_ifi_window"}[status]
            matches = [{**base, "gfd_id": None, "candidate_status": label,
                        "reason": status + "; absence of candidate is never a non-flood observation"}]
        output.extend(matches)
    return output


def select_batch(table, boundaries, limit=5):
    require(1 <= limit <= 10, "At most ten new reviews")
    require(boundaries["source"] == BOUNDARY and boundaries["window"] == WINDOW, "Wrong public boundary source")
    features = boundaries["response"]["features"]
    require(boundaries["response"]["count"] == len(features) <= 80, "Incomplete boundary metadata")
    names = Counter(f["shapeName"] for f in features)
    exact = {f["shapeName"]: f for f in features if names[f["shapeName"]] == 1}
    pool = []
    for candidate in table:
        if candidate["gfd_id"] in {None, 2728, 3551} or candidate.get("temporal_strength") != "strong_temporal_candidate":
            continue
        if candidate["ifi_state_original"] != "Karnataka":
            continue
        tokens = [s.strip() for s in candidate["ifi_district_tokens_original"].split(",")]
        for token in sorted(set(tokens) & set(exact)):
            pool.append({**candidate, "review_region": exact[token], "source_token_count": len(tokens)})
    selected, years, regions, ids = [], set(), set(), set()
    while pool and len(selected) < limit:
        def rank(value):
            year, region = value["gfd_start"][:4], value["review_region"]["shapeName"]
            timing = value["temporal_overlap"]
            duration = (date.fromisoformat(value["gfd_end_inclusive"]) - date.fromisoformat(value["gfd_start"])).days
            return (year in years, region in regions, -timing["jaccard"], value["source_token_count"],
                    -timing["ifi_fraction"], duration, value["gfd_id"], value["ifi_project_event_id"], region)
        value = min(pool, key=rank)
        selected.append(value); ids.add(value["gfd_id"])
        years.add(value["gfd_start"][:4]); regions.add(value["review_region"]["shapeName"])
        pool = [r for r in pool if r["gfd_id"] not in ids]
    return selected


def partition_windows(bounds, chunk=CELL_CHUNK):
    require(type(chunk) is int and 0 < chunk <= CELL_CHUNK, "Invalid partition budget")
    require(len(bounds) >= 4 and all(math.isfinite(v) for point in bounds for v in point), "Invalid bounds")
    xs, ys = zip(*bounds)
    x0, x1 = math.floor(min(xs) / 250), math.ceil(max(xs) / 250)
    y0, y1 = math.floor(-max(ys) / 250), math.ceil(-min(ys) / 250)
    require(x0 < x1 and y0 < y1, "Empty bounds")
    result = [[x, min(x + chunk, x1), y, min(y + chunk, y1)]
              for x in range(x0, x1, chunk) for y in range(y0, y1, chunk)]
    require(len(result) <= 24, "Review region exceeds bounded 24-partition budget")
    return result


def owns(window, col, row):
    return window[0] <= col < window[1] and window[2] <= row < window[3]


def qualifies(flooded, permanent, clear, masks):
    """Scalar oracle for band/mask semantics, also applied to retained Udupi pixels."""
    valid = all(masks) and clear is not None and math.isfinite(clear) and clear > 0
    return valid and flooded == 1 and permanent == 0


def provider_error(exc):
    """Keep actionable computation errors, withholding URLs and credential fields."""
    message = re.sub(r"https?://\S+", "[URL withheld]", str(exc))
    message = re.sub(r"(?i)(access_token|refresh_token|client_secret|authorization)[=: ]+\S+",
                     r"\1=[withheld]", message)
    message = re.sub(r"(?i)Bearer\s+\S+", "Bearer [withheld]", message)
    return {"type": type(exc).__name__, "message": message[:4096]}


def finding(parts, expected_parts):
    good = [p["statistics"] for p in parts if "statistics" in p]
    keys = ("region_pixels", "valid_pixels", "qualifying_pixels", "mapped_water_pixels",
            "permanent_water_pixels", "clear_views_sum", "clear_perc_sum", "clear_perc_count",
            "duration_sum", "duration_count")
    totals = {k: sum(float(p.get(k) or 0) for p in good) for k in keys}
    for key in keys[:5]:
        require(totals[key].is_integer() and totals[key] >= 0, "Non-integer/negative pixel count")
        totals[key] = int(totals[key])
    require(totals["qualifying_pixels"] <= totals["valid_pixels"] <= totals["region_pixels"], "Inconsistent observation counts")
    complete = len(good) == expected_parts and expected_parts > 0
    fraction = totals["valid_pixels"] / totals["region_pixels"] if totals["region_pixels"] else None
    if totals["qualifying_pixels"] > 0:
        status = "satellite_positive"
    elif complete and fraction is not None and fraction >= MIN_VALID_FRACTION:
        status = "observed_no_qualifying_floodwater"
    else:
        status = "insufficient_observation"
    return {"evidence_status": status, "computation_complete": complete,
            "counts_are_lower_bounds": not complete, "statistics": totals, "valid_fraction": fraction,
            "clear_views_mean_valid": totals["clear_views_sum"] / totals["valid_pixels"] if totals["valid_pixels"] else None,
            "clear_perc_mean_valid": totals["clear_perc_sum"] / totals["clear_perc_count"] if totals["clear_perc_count"] else None,
            "duration_mean_qualifying": totals["duration_sum"] / totals["duration_count"] if totals["duration_count"] else None}


def regression(directory):
    """Read-only original raster oracle: centre-in-district, same input-band rule."""
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from shapely.geometry import Point, shape
    manifest = json.loads((directory / "manifest.json").read_text())
    boundary = shape(json.loads((directory / "udupi_boundary.geojson").read_text())["geometry"])
    transform = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    result = {}
    for event in manifest["events"]:
        eid = event["event_id"]
        require(eid in {2728, 3551}, "Unexpected Udupi reference")
        path = directory / event["raster_file"]
        require(fingerprint(path) == manifest["files"][event["raster_file"]], "Protected Udupi raster changed")
        count = 0
        with rasterio.open(path) as src:
            require(src.crs.to_string() == CRS and src.transform.a == 250 and src.transform.e == -250, "Udupi grid changed")
            values = src.read(); masks = src.read_masks() > 0
            for row, col in np.argwhere(values[0] == 1):
                valid_masks = [bool(masks[i, row, col]) and values[i, row, col] != -9999 for i in range(3)]
                if qualifies(float(values[0, row, col]), float(values[1, row, col]), float(values[2, row, col]), valid_masks):
                    x, y = src.xy(int(row), int(col))
                    if boundary.covers(Point(*transform.transform(x, y))):
                        count += 1
        require(count == {2728: 33, 3551: 23}[eid], "Udupi regression mismatch; stop")
        result[str(eid)] = count
    require(set(result) == {"2728", "3551"}, "Incomplete Udupi regression")
    return result


def summary(rows, table, selected, reviewed):
    by_ifi = {}
    for r in table:
        by_ifi.setdefault(r["ifi_project_event_id"], []).append(r)
    return {"ifi_temporal_counts": dict(sorted(Counter(window_status(r) for r in rows).items())),
            "ifi_with_candidates": sum(any(v["gfd_id"] is not None for v in values) for values in by_ifi.values()),
            "ambiguous_ifi_events": sum(any(v["candidate_status"] == "ambiguous" for v in values) for values in by_ifi.values()),
            "no_candidate_ifi_events": sum(values[0]["candidate_status"] == "no_candidate" for values in by_ifi.values()),
            "candidate_relationships": sum(v["gfd_id"] is not None for v in table),
            "selected_gfd_ids": [r["gfd_id"] for r in selected],
            "reviewed_gfd_ids": [r["gfd_id"] for r in reviewed if r["partitions"]],
            "status_counts": {s: sum(r["evidence_status"] == s for r in reviewed) for s in sorted(EVIDENCE)},
            "qualifying_pixel_total": sum(r.get("statistics", {}).get("qualifying_pixels", 0) for r in reviewed),
            "ifi_confirmations": 0, "daily_labels_created": 0}


def live_review(selected, raw, deadline=60, total_seconds=900):
    """One request retry owner; time budget includes initialization and backoff."""
    require(1 <= deadline <= 60 and 1 <= total_seconds <= 900, "Invalid time limits")
    require(1 <= len(selected) <= 10, "At most ten new reviews")
    os.environ["NO_GCE_CHECK"] = "true"
    sys.path.insert(0, str(ROOT / "scripts"))
    import ee
    import verify_earth_engine as verification
    import extract_karnataka_rainfall as requests
    raw.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    reviewed = [{"gfd_id": r["gfd_id"], "ifi_project_event_id": r["ifi_project_event_id"],
                 "ifi_source_event_id": r["ifi_source_event_id"], "ifi_start": r["ifi_start"],
                 "ifi_end_inclusive": r["ifi_end_inclusive"], "gfd_start": r["gfd_start"],
                 "gfd_end_inclusive": r["gfd_end_inclusive"], "image_id": r["image_id"],
                 "review_region": r["review_region"], "association_status": "provisional_temporal_only",
                 "ifi_confirmation": False, "evidence_status": "not_reviewed", "partitions": [],
                 "processing_scale_m": 250, "semantics": "event_window_maximum_not_daily_occurrence"} for r in selected]
    def request(fn, name):
        def sleep(seconds):
            require(time.monotonic() - started + seconds < total_seconds, "Total satellite batch time limit reached")
            time.sleep(seconds)
        def bounded():
            remaining = total_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise RuntimeError("Total satellite batch time limit reached")
            try:
                with verification.wall_limit(min(deadline, remaining)):
                    return fn()
            except verification.VerificationDeadlineExceeded:
                raise TimeoutError("Bounded Earth Engine request exceeded deadline") from None
        def captured():
            try:
                return bounded()
            except Exception as exc:
                with (raw / "provider_errors.jsonl").open("a") as handle:
                    handle.write(json.dumps({"operation": name, "retrieved_at": now(), **provider_error(exc)}) + "\n")
                raise
        return requests.bounded_request(captured, name, raw / "requests.jsonl", sleep=sleep)
    def checkpoint():
        # Append-only completed/partial evidence journal, never a completed version.
        with (raw / "progress.jsonl").open("a") as handle:
            handle.write(json.dumps({"retrieved_at": now(), "events": reviewed}, allow_nan=False) + "\n")
    access = {"initialization_succeeded": False, "metadata_succeeded": False}
    try:
        ee.data.setMaxRetries(0)
        request(lambda: ee.Initialize(project="floodpulse"), "batch_initialization")
        access["initialization_succeeded"] = True
        request(lambda: ee.data.setDeadline(deadline * 1000), "batch_deadline")
        first = ee.Image(ee.ImageCollection(SOURCE).sort("system:time_start").first())
        access["minimal_metadata"] = request(lambda: first.toDictionary(["id", "system:index"]).getInfo(), "batch_minimal_metadata")
        access["metadata_succeeded"] = True
        for event in reviewed:
            feature = ee.FeatureCollection(BOUNDARY).filter(ee.Filter.eq("shapeID", event["review_region"]["shapeID"]))
            geom = feature.geometry()
            details = request(lambda: ee.Dictionary({"count": feature.size(), "area_km2": geom.area(1).divide(1e6),
                "bounds": geom.bounds(maxError=1, proj=ee.Projection(CRS)).coordinates()}).getInfo(), f"region:{event['gfd_id']}")
            require(details["count"] == 1 and 0 < details["area_km2"] <= 20000, "Ambiguous/oversized public region")
            event["region_metadata"] = details
            windows = partition_windows(details["bounds"][0]); event["partition_windows"] = windows
            image = ee.Image(event["image_id"])
            flooded, permanent, clear = [image.select(b) for b in ("flooded", "jrc_perm_water", "clear_views")]
            valid = flooded.mask().And(permanent.mask()).And(clear.mask()).And(clear.gt(0))
            qualified = flooded.eq(1).And(permanent.eq(0)).And(valid)
            def band(value, name):
                return value.unmask(0, sameFootprint=False).rename(name)
            evidence = ee.Image.constant(1).rename("region_pixels").addBands([
                band(valid, "valid_pixels"), band(qualified, "qualifying_pixels"),
                band(flooded.eq(1).And(valid), "mapped_water_pixels"), band(permanent.eq(1).And(valid), "permanent_water_pixels"),
                band(clear.updateMask(valid), "clear_views_sum"),
                band(image.select("clear_perc").updateMask(valid), "clear_perc_sum"),
                band(image.select("clear_perc").mask().And(valid), "clear_perc_count"),
                band(image.select("duration").updateMask(qualified), "duration_sum"),
                band(image.select("duration").mask().And(qualified), "duration_count")])
            coordinates = ee.Image.pixelCoordinates(ee.Projection(CRS, TRANSFORM))
            try:
                for index, (x0, x1, y0, y1) in enumerate(windows):
                    rectangle = ee.Geometry.Rectangle([x0 * 250, -y1 * 250, x1 * 250, -y0 * 250], proj=CRS, geodesic=False)
                    region = geom.intersection(rectangle, maxError=1)
                    ownership = coordinates.select("x").gte(x0).And(coordinates.select("x").lt(x1)).And(
                        coordinates.select("y").gte(y0)).And(coordinates.select("y").lt(y1))
                    part = {"index": index, "window": windows[index]}; event["partitions"].append(part)
                    part["statistics"] = request(lambda: evidence.updateMask(ownership).reduceRegion(
                        reducer=ee.Reducer.sum().unweighted(), geometry=region,
                        crs=ee.Projection(CRS, TRANSFORM), scale=250,
                        maxPixels=MAX_PIXELS, bestEffort=False, tileScale=2).getInfo(), f"reduce:{event['gfd_id']}:{index}")
                    event.update(finding(event["partitions"], len(windows))); event["retrieved_at"] = now(); checkpoint()
            except Exception as exc:
                event["partitions"][-1]["error"] = {"type": type(exc).__name__, "message": str(exc)}
                event.update(finding(event["partitions"], len(windows))); raise
            checkpoint()
    except Exception as exc:
        access["stopped_error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        access["finished_at"] = now(); checkpoint(); write_new(raw / "access.json", access)
    return reviewed, access


def create(catalogue, inventory_path, boundaries_path, access_path, output, raw, limit=5, deadline=60, total=900):
    require(not output.exists(), "Version exists; never overwrite")
    rows = json.loads(catalogue.read_text()); inventory = json.loads(inventory_path.read_text())
    boundaries = json.loads(boundaries_path.read_text()); probe = json.loads(access_path.read_text())
    require(probe["initialization_succeeded"] and probe["metadata_succeeded"], "Access prerequisite failed")
    table = candidates(rows, inventory); selected = select_batch(table, boundaries, limit)
    require(5 <= len(selected) <= 10, "Not enough defensible first-batch selections")
    reference = regression(ROOT / "data/processed/udupi_flood_spatial_v1")  # Before new raster queries.
    reviewed, access = live_review(selected, raw, deadline, total)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "candidates.json", table); write_new(output / "event_evidence.json", reviewed)
    inputs = {str(p.resolve()): fingerprint(p) for p in (catalogue, inventory_path, boundaries_path, access_path)}
    manifest = {"version": output.name, "schema_version": 1, "created_at": now(), "project": "floodpulse",
        "source": SOURCE, "source_url": "https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1",
        "license": "CC BY-NC 4.0", "attribution": "Cloud to Street / Dartmouth Flood Observatory; Tellman et al. (2021), doi:10.1038/s41586-021-03695-w",
        "ifi_license": "CC BY-NC 4.0; Saharia et al., India Flood Inventory, doi:10.5281/zenodo.16994648",
        "boundary_source": BOUNDARY, "boundary_license": "CC BY 4.0; William & Mary geoLab, geoBoundaries v6.0.0 (2023 composite)",
        "inputs": inputs, "raw_directory": str(raw.resolve()), "selection_rule": SELECTION, "selection_limit": limit,
        "parameters": {"scale_m": 250, "crs": CRS, "transform": TRANSFORM, "maxPixels": MAX_PIXELS,
                       "bestEffort": False, "tileScale": 2, "cell_chunk": CELL_CHUNK, "max_partitions_per_event": 24,
                       "deadline_seconds": deadline, "max_attempts": 3, "backoff_seconds": [2, 4], "total_seconds": total,
                       "zero_evidence_valid_fraction_gate": MIN_VALID_FRACTION},
        "qualification": "flooded==1 AND jrc_perm_water==0 AND all three input masks valid AND clear_views>0",
        "partition_rule": "250 m anchored UTM grid, half-open integer column/row windows, genuine public district intersections, centre-in-region unweighted sum",
        "semantics": "Event-window maximum evidence; duration is source 3-day-composite evidence, never daily labels. Temporal IFI associations remain provisional.",
        "limitations": ["Modern public review boundaries are not historical district identities or current-LGD reconciliation.",
                        "Search window includes neighbouring states; footprint or date overlap alone does not establish Karnataka floodwater.",
                        "95% observation gate is a conservative research criterion, not validated non-flood evidence.",
                        "GFD 250 m classification; catalogue storage grid does not imply finer accuracy."],
        "access": access, "udupi_regression": reference, "summary": summary(rows, table, selected, reviewed),
        "files": {name: fingerprint(output / name) for name in ("candidates.json", "event_evidence.json")},
        "raw_files": {str(p.resolve()): fingerprint(p) for p in raw.iterdir() if p.is_file()}}
    write_new(output / "manifest.json", manifest)
    return validate(output)


def validate(output):
    """Read-only checksum + offline candidate/selection/statistics reconstruction."""
    manifest = json.loads((output / "manifest.json").read_text())
    require(manifest["source"] == SOURCE and manifest["license"] == "CC BY-NC 4.0", "Source/licence mismatch")
    p = manifest["parameters"]
    require((p["scale_m"], p["crs"], p["transform"], p["maxPixels"], p["bestEffort"]) ==
            (250, CRS, TRANSFORM, MAX_PIXELS, False), "Processing method changed")
    for name, expected in {**manifest["inputs"], **manifest["raw_files"]}.items():
        require(fingerprint(Path(name)) == expected, "Input/raw checksum mismatch")
    for name, expected in manifest["files"].items():
        require(Path(name).name == name and fingerprint(output / name) == expected, "Output checksum mismatch")
    # Sorted JSON keys change dictionary order; select inputs explicitly by filename.
    paths = {Path(name).name: Path(name) for name in manifest["inputs"]}
    rows = json.loads(paths["events.json"].read_text())
    table = candidates(rows, json.loads(paths["gfd_inventory.json"].read_text()))
    require(table == json.loads((output / "candidates.json").read_text()), "Candidate reconstruction mismatch")
    selected = select_batch(table, json.loads(paths["public_boundary_inventory.json"].read_text()), manifest["selection_limit"])
    reviewed = json.loads((output / "event_evidence.json").read_text())
    require([r["gfd_id"] for r in reviewed] == [r["gfd_id"] for r in selected], "Selection changed")
    for record, selection in zip(reviewed, selected):
        require(record["evidence_status"] in EVIDENCE and record["ifi_confirmation"] is False, "Invalid evidence promotion")
        for key in ("ifi_project_event_id", "gfd_start", "gfd_end_inclusive", "ifi_start", "ifi_end_inclusive", "image_id", "review_region"):
            require(record[key] == selection[key], "Evidence source identity changed")
        if record["partitions"]:
            windows = partition_windows(record["region_metadata"]["bounds"][0])
            require(record["partition_windows"] == windows, "Partition grid changed")
            require([r["index"] for r in record["partitions"]] == list(range(len(record["partitions"]))), "Duplicate partition")
            for part in record["partitions"]:
                require(part["window"] == windows[part["index"]], "Partition ownership changed")
            for key, value in finding(record["partitions"], len(windows)).items():
                require(record[key] == value, "Evidence counts/status changed")
        else:
            require(record["evidence_status"] == "not_reviewed", "Evidence without raster computation")
    require(regression(ROOT / "data/processed/udupi_flood_spatial_v1") == manifest["udupi_regression"], "Reference regression changed")
    result = summary(rows, table, selected, reviewed)
    require(result == manifest["summary"], "Summary mismatch")
    return result


def discover(catalogue, destination, deadline=60):
    """Optional reproducible metadata discovery, before any raster processing.

    One bounded window (128-map ceiling) and exact public name inventory (80
    features). Failure stops discovery; retained source bytes are never rewritten.
    """
    require(1 <= deadline <= 60 and not destination.exists(), "Invalid deadline or existing metadata version")
    rows = json.loads(catalogue.read_text())
    temporal = dict(sorted(Counter(window_status(row) for row in rows).items()))  # OFFLINE first.
    destination.mkdir(parents=True, exist_ok=False)
    write_new(destination / "offline_subset.json", {"counts": temporal, "coverage": COVERAGE,
        "source": fingerprint(catalogue), "ifi_project_event_ids": [r["project_event_id"] for r in rows
                                                                 if window_status(r) == "within_gfd_coverage"]})
    os.environ["NO_GCE_CHECK"] = "true"
    sys.path.insert(0, str(ROOT / "scripts"))
    import ee
    import verify_earth_engine as verification
    import extract_karnataka_rainfall as requests
    access = {"project": "floodpulse", "NO_GCE_CHECK": "true", "deadline_seconds": deadline,
              "max_attempts": 3, "initialization_succeeded": False, "metadata_succeeded": False,
              "started_at": now(), "raster_processing_started": False}
    started = time.monotonic()
    def request(fn, name):
        def bounded():
            remaining = 900 - (time.monotonic() - started)
            require(remaining > 0, "Total discovery time limit reached")
            try:
                with verification.wall_limit(min(deadline, remaining)):
                    return fn()
            except verification.VerificationDeadlineExceeded:
                raise TimeoutError("Bounded metadata request exceeded deadline") from None
        def sleep(seconds):
            require(time.monotonic() - started + seconds < 900, "Total discovery time limit reached")
            time.sleep(seconds)
        return requests.bounded_request(bounded, name, destination / "requests.jsonl", sleep=sleep)
    try:
        ee.data.setMaxRetries(0)
        request(lambda: ee.Initialize(project="floodpulse"), "initialization")
        access["initialization_succeeded"] = True
        request(lambda: ee.data.setDeadline(deadline * 1000), "configure_deadline")
        image = ee.Image(ee.ImageCollection(SOURCE).sort("system:time_start").first())
        value = request(lambda: image.toDictionary(["id", "system:id", "system:index", "system:time_start", "system:time_end"]).set(
            "bands", image.bandNames()).getInfo(), "minimal_gfd_metadata")
        access["metadata_succeeded"] = True; write_new(destination / "minimal_gfd_metadata.json", value)
        c = ee.ImageCollection(SOURCE).filterBounds(ee.Geometry.Rectangle(WINDOW, geodesic=False)).sort("system:time_start")
        props = ["id", "system:index", "system:time_start", "system:time_end", "cc", "countries", "dfo_country", "dfo_other_country", "dfo_main_cause"]
        value = request(lambda: ee.Dictionary({"count": c.size(), "images": c.limit(128).toList(128).map(
            lambda im: ee.Image(im).toDictionary(props))}).getInfo(), "bounded_public_window_metadata")
        write_new(destination / "gfd_inventory.json", {"source": SOURCE, "window": WINDOW, "limit": 128, "retrieved_at": now(), "response": value})
        names = sorted({n.strip() for row in rows for n in row["source_districts"].split(",") if n.strip()})
        c = ee.FeatureCollection(BOUNDARY).filter(ee.Filter.eq("shapeGroup", "IND")).filter(ee.Filter.eq("shapeType", "ADM2")).filter(
            ee.Filter.inList("shapeName", names)).filterBounds(ee.Geometry.Rectangle(WINDOW, geodesic=False))
        value = request(lambda: ee.Dictionary({"count": c.size(), "features": c.limit(80).toList(80).map(
            lambda f: ee.Feature(f).toDictionary(["shapeName", "shapeID", "shapeGroup", "shapeType"]))}).getInfo(), "exact_public_name_metadata")
        write_new(destination / "public_boundary_inventory.json", {"source": BOUNDARY, "window": WINDOW, "query_exact_names": names,
            "limit": 80, "retrieved_at": now(), "response": value})
        access["status"] = "available"
    except Exception as exc:
        access.update(status="unavailable", error={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        access["finished_at"] = now(); write_new(destination / "access.json", access)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--discover-metadata", type=Path, help="New local metadata version; no rasters reviewed")
    parser.add_argument("--catalogue", type=Path, default=ROOT / "data/working/karnataka_flood_events_v1/events.json")
    parser.add_argument("--metadata", type=Path, default=ROOT / "data/raw/flood_satellite/stage3b_access_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "data/working/karnataka_satellite_event_evidence_v1")
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/flood_satellite/stage3b_review_v1")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--deadline", type=int, default=60)
    parser.add_argument("--total-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.discover_metadata:
        discover(args.catalogue, args.discover_metadata, args.deadline)
        return
    if args.validate_only:
        result = validate(args.validate_only)
    else:
        result = create(args.catalogue, args.metadata / "gfd_inventory.json", args.metadata / "public_boundary_inventory.json",
                        args.metadata / "access.json", args.output, args.raw, args.limit, args.deadline, args.total_seconds)
    print(json.dumps(result, indent=2), flush=True)
    if not args.validate_only:
        manifest = json.loads((args.output / "manifest.json").read_text())
        if manifest["access"].get("stopped_error"):
            raise SystemExit(2)  # Valid retained checkpoint is not a successful raster batch.


if __name__ == "__main__":
    main()
