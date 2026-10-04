#!/usr/bin/env python3
"""Read-only, bounded metadata/pixel checks. Never authenticates, exports or writes data."""
import argparse
import importlib
import json
import os
import math
import signal
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

BOUNDARY_ID = "WM/geoLab/geoBoundaries/600/ADM2"
PILOTS = {
    "Bengaluru Urban": ["Bengaluru Urban", "Bangalore Urban", "Bangalore"],
    "Udupi": ["Udupi", "Udipi"],
}
COLLECTIONS = {
    "UCSB-CHG/CHIRPS/DAILY": {"bands": ["precipitation"], "scale_m": 5566, "temporal": True},
    "NASA/GPM_L3/IMERG_V07": {
        "bands": ["precipitation", "randomError", "MWprecipSource", "IRinfluence"],
        "scale_m": 11132, "temporal": True,
    },
    "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1": {
        "bands": ["flooded", "duration", "clear_views", "clear_perc", "jrc_perm_water"],
        "scale_m": 250, "temporal": False,
    },
    "COPERNICUS/DEM/GLO30_2024_1": {
        "bands": ["DEM", "HEM", "EDM", "FLM", "WBM"], "scale_m": 30, "temporal": False,
    },
}
FLOOD_ID = "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1"
EVENT_LIMIT = 20
PIXEL_LIMIT = 300000
DEM_ID = "COPERNICUS/DEM/GLO30_2024_1"
UDUPI_BATCH = [2049, 2728, 3551]
GRID_CRS = "EPSG:32643"  # UTM zone 43N covers Udupi; metre-based 250 m grid.
GRID_TRANSFORM = [250, 0, 0, 0, -250, 0]


class VerificationDeadlineExceeded(BaseException):
    """The total budget is exhausted; collection error handling must not swallow it."""


def now():
    return datetime.now(timezone.utc).isoformat()


def plan(day):
    start = date.fromisoformat(day)
    return {
        "boundary_asset": BOUNDARY_ID,
        "boundary_filters": {"shapeGroup": "IND", "shapeType": "ADM2", "shapeName_candidates": PILOTS},
        "rainfall_start_inclusive": start.isoformat(),
        "rainfall_end_exclusive": (start + timedelta(days=1)).isoformat(),
        "collections": COLLECTIONS,
        "event_limit_per_pilot": EVENT_LIMIT,
        "flood_scan_dates": "Entire published event collection; no rainfall-day filter",
        "flood_scale_m": 250, "max_pixels_per_reduction": PIXEL_LIMIT,
        "max_pilot_area_km2": 20000,
        "per_request_deadline_ms": 10000, "retries": 0, "wall_seconds": 120,
        "coverage_scope": "One rainfall day and one centroid pixel; not a completeness audit",
    }


@contextmanager
def wall_limit(seconds):
    """Linux CLI wall bound, including initialization and all synchronous queries."""
    def expired(*_):
        raise VerificationDeadlineExceeded(f"Verification exceeded {seconds} seconds")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def probe_access(ee, project):
    # Initialize first: setDeadline requires an initialized client transport.
    ee.Initialize(project=project)
    ee.data.setDeadline(10000)
    ee.data.setMaxRetries(0)
    value = ee.Number(1).getInfo()
    if value != 1:
        raise ValueError("Earth Engine constant probe returned an unexpected value")
    return {"initialization": "succeeded", "constant_probe": value, "retrieved_at": now()}


def find_boundary(ee, names):
    features = (ee.FeatureCollection(BOUNDARY_ID)
                .filter(ee.Filter.eq("shapeGroup", "IND"))
                .filter(ee.Filter.eq("shapeType", "ADM2"))
                .filter(ee.Filter.inList("shapeName", names)))
    count = features.size().getInfo()
    if count != 1:
        raise ValueError(f"Boundary match count {count}; require exactly one genuine ADM2 feature")
    feature = ee.Feature(features.first())
    geometry = feature.geometry()
    metadata = ee.Dictionary({
        "properties": feature.toDictionary(["shapeID", "shapeName", "shapeGroup", "shapeType"]),
        "area_km2": geometry.area(maxError=100).divide(1e6),
        "bounds": geometry.bounds(maxError=100).coordinates(),
    }).getInfo()
    if not 0 < metadata["area_km2"] <= 20000:
        raise ValueError("Boundary area exceeds pilot budget or is empty")
    return geometry, {"source_id": BOUNDARY_ID, **metadata, "retrieved_at": now()}


def flood_finding(stats):
    """Positive raster evidence only; missing/zero data never becomes a negative label."""
    value = stats.get("nonpermanent_flood_max")
    count = stats.get("nonpermanent_flood_count")
    if value is None or not count:
        return "unknown_no_valid_pixels"
    if value > 0:
        return "satellite_mapped_nonpermanent_water_present"
    return "no_positive_pixel_in_this_event_map_not_a_nonflood_label"


def inspect_collection(ee, source_id, geometry, query):
    result = {"source_id": source_id, "retrieved_at": now(), "status": "available"}
    try:
        return _inspect_collection(ee, source_id, geometry, query, result)
    except VerificationDeadlineExceeded:
        raise
    except Exception as exc:
        result["status"] = "partial" if "footprint_image_count" in result else "unavailable"
        result["finding"] = "query_failed_evidence_incomplete"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        result["retrieved_at"] = now()
        return result


def _inspect_collection(ee, source_id, geometry, query, result):
    spec = COLLECTIONS[source_id]
    collection = ee.ImageCollection(source_id).filterBounds(geometry)
    if spec["temporal"]:
        collection = collection.filterDate(query["rainfall_start_inclusive"], query["rainfall_end_exclusive"])
    count = collection.size().getInfo()
    result["footprint_image_count"] = count
    if count == 0:
        result["finding"] = "no_matching_images_not_evidence_of_no_flood"
        if source_id == DEM_ID:
            result.update(sample_status="unavailable", centroid_sample=None, tile_ids_used=[],
                          diagnostic="No DEM tile footprint intersects the pilot district; elevation is missing.")
        return result
    if source_id == DEM_ID:
        return inspect_dem(ee, collection, geometry, result, count)
    first = ee.Image(collection.sort("system:time_start").first())
    metadata = ee.Dictionary({
        "bands": first.bandNames(),
        "properties": first.toDictionary(first.propertyNames().remove("system:footprint")),
        "first_time_ms": collection.aggregate_min("system:time_start"),
        "last_time_ms": collection.aggregate_max("system:time_start"),
        "nominal_scale_m": first.select(spec["bands"][0]).projection().nominalScale(),
    }).getInfo()
    result["metadata"] = metadata
    if source_id != FLOOD_ID:
        # A genuine boundary centroid, not an invented geographic polygon or profile.
        result["centroid_sample"] = first.select(spec["bands"]).reduceRegion(
            reducer=ee.Reducer.first(), geometry=geometry.centroid(maxError=100),
            scale=spec["scale_m"], maxPixels=100, bestEffort=False,
        ).getInfo()
        result["sample_status"] = (
            "available" if any(v is not None for v in result["centroid_sample"].values()) else "unavailable"
        )
        result["finding"] = "inspect_sample_nulls_and_masks_before_use"
        result["retrieved_at"] = now()
        return result
    events = collection.sort("system:time_start").limit(EVENT_LIMIT)
    image_list = events.toList(EVENT_LIMIT)
    result["events"] = []
    result["truncated"] = count > EVENT_LIMIT
    for index in range(min(count, EVENT_LIMIT)):
        image = ee.Image(image_list.get(index))
        # filterBounds checks footprints only; pixels are needed to establish mapped water.
        positive = (image.select("flooded").eq(1)
                    .And(image.select("jrc_perm_water").eq(0)).rename("nonpermanent_flood"))
        observed = positive.And(image.select("clear_views").gt(0)).rename("observed_nonpermanent_flood")
        reducer = (ee.Reducer.max().combine(ee.Reducer.mean(), sharedInputs=True)
                   .combine(ee.Reducer.count(), sharedInputs=True))
        stats = image.select(spec["bands"]).addBands(positive).addBands(observed).reduceRegion(
            reducer=reducer, geometry=geometry, scale=250,
            maxPixels=PIXEL_LIMIT, bestEffort=False, tileScale=2,
        )
        # Preserve the failed event's dates/ID as well as earlier successful reductions.
        event = {"properties": image.toDictionary(image.propertyNames().remove("system:footprint")).getInfo(),
                 "statistics": None}
        result["events"].append(event)
        event["statistics"] = stats.getInfo()
        event["finding"] = flood_finding(event["statistics"])
        event["observation_assessment"] = (
            "mapped_nonpermanent_water_has_clear_view_support"
            if (event["statistics"].get("observed_nonpermanent_flood_max") or 0) > 0
            else "no_clear_view_supported_positive_evidence_not_a_nonflood_label"
        )
    result["finding"] = "bounded_event_review_not_complete" if result["truncated"] else "event_maps_reviewed"
    result["retrieved_at"] = now()
    return result


def inspect_dem(ee, collection, geometry, result, count):
    """Sample a masked mosaic, retaining the actual source tile for the sampled pixel."""
    if count > 512:
        raise ValueError("DEM tile inventory exceeds the bounded 512-tile budget")
    tiles = collection.sort("system:index")
    point = geometry.centroid(maxError=100)
    result["sampling_point"] = point.coordinates().getInfo()
    result["tile_ids_used"] = tiles.aggregate_array("system:index").getInfo()
    images = tiles.toList(count)

    def tag_tile(index):
        image = ee.Image(images.get(index)).select(COLLECTIONS[DEM_ID]["bands"])
        tag = ee.Image.constant(index).toInt().updateMask(image.select("DEM").mask()).rename("tile_index")
        return image.addBands(tag)

    mosaic = ee.ImageCollection.fromImages(ee.List.sequence(0, count - 1).map(tag_tile)).mosaic()
    projection = ee.Image(tiles.first()).select("DEM").projection()
    mosaic = mosaic.setDefaultProjection(projection)
    dem_mask = mosaic.select("DEM").mask().unmask(0).rename("dem_valid_mask")
    sample = mosaic.addBands(dem_mask).reduceRegion(
        reducer=ee.Reducer.first(), geometry=point, scale=30, crs=projection,
        maxPixels=100, bestEffort=False,
    ).getInfo()
    result["centroid_sample"] = sample
    valid = sample.get("DEM") is not None and (sample.get("dem_valid_mask") or 0) > 0
    result["sample_status"] = "available" if valid else "unavailable"
    result["finding"] = "unmasked_dem_pixel_at_centroid" if valid else "missing_dem_pixel_at_centroid"
    result["diagnostic"] = None if valid else "The district-filtered mosaic has no unmasked DEM value at the recorded point at 30 m. No elevation was substituted."
    index = sample.get("tile_index")
    result["sample_tile_id"] = result["tile_ids_used"][int(index)] if valid and index is not None else None
    result["retrieved_at"] = now()
    return result


def partition_windows(bounds):
    """Four half-open pixel windows covering a projected district bounding box."""
    xs, ys = zip(*bounds)
    x0, x1 = math.floor(min(xs) / 250), math.ceil(max(xs) / 250)
    y0, y1 = math.floor(-max(ys) / 250), math.ceil(-min(ys) / 250)
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ValueError("District bounds too small for four partitions")
    xm, ym = (x0 + x1) // 2, (y0 + y1) // 2
    return [(a, b, c, d) for a, b in ((x0, xm), (xm, x1)) for c, d in ((y0, ym), (ym, y1))]


def district_partitions(ee, geometry):
    projection = ee.Projection(GRID_CRS, GRID_TRANSFORM)
    bounds = geometry.bounds(maxError=1, proj=ee.Projection(GRID_CRS)).coordinates().getInfo()[0]
    coordinates = ee.Image.pixelCoordinates(projection)
    partitions = []
    for x0, x1, y0, y1 in partition_windows(bounds):
        rectangle = ee.Geometry.Rectangle([x0 * 250, -y1 * 250, x1 * 250, -y0 * 250],
                                          proj=GRID_CRS, geodesic=False)
        region = geometry.intersection(rectangle, maxError=1)
        ownership = (coordinates.select("x").gte(x0).And(coordinates.select("x").lt(x1))
                     .And(coordinates.select("y").gte(y0)).And(coordinates.select("y").lt(y1)))
        partitions.append((region, ownership, [x0, x1, y0, y1]))
    return partitions


def partitioned_finding(event):
    stats = [part["statistics"] for part in event["partitions"] if "statistics" in part]
    positives = sum((part.get("observed_nonpermanent_flood_sum") or 0) for part in stats)
    valid = sum((part.get("observed_nonpermanent_flood_count") or 0) for part in stats)
    complete = len(stats) == 4
    return {
        "computation_complete": complete, "valid_observed_pixels": valid,
        "positive_observed_pixels": positives,
        "finding": ("confirmed_mapped_nonpermanent_floodwater" if positives > 0 else
                    "incomplete_computation" if not complete else
                    "no_valid_observed_pixels" if valid == 0 else
                    "no_positive_pixels_in_reviewed_map_not_a_nonflood_label"),
    }


def review_udupi_batch(ee, geometry, result, requested):
    collection = ee.ImageCollection(FLOOD_ID).filterBounds(geometry).sort("system:time_start")
    count = collection.size().getInfo()
    result["footprint_image_count"] = count
    if count > 64:
        raise ValueError("Flood inventory exceeds the bounded 64-event metadata budget")
    inventory = collection.toList(count).map(lambda image: ee.Image(image).toDictionary(
        ["id", "system:id", "system:index", "system:time_start", "system:time_end"])).getInfo()
    result["event_inventory"] = inventory
    result["unreviewed_event_ids"] = [event["id"] for event in inventory]
    result["requested_event_ids"] = requested
    result["events"] = []
    missing = set(requested) - set(result["unreviewed_event_ids"])
    if missing:
        raise ValueError(f"Requested events do not intersect the district footprint: {sorted(missing)}")
    partitions = district_partitions(ee, geometry)
    result["partition_grid"] = {"crs": GRID_CRS, "transform": GRID_TRANSFORM,
                                "half_open_windows": [part[2] for part in partitions]}
    for event_id in requested:
        image = ee.Image(collection.filter(ee.Filter.eq("id", event_id)).first())
        metadata = next(event for event in inventory if event["id"] == event_id)
        event = {"properties": metadata, "footprint_intersects": True, "partitions": []}
        result["events"].append(event)
        flooded, permanent, clear = image.select("flooded"), image.select("jrc_perm_water"), image.select("clear_views")
        valid = flooded.mask().And(permanent.mask()).And(clear.mask()).And(clear.gt(0))
        raw = flooded.eq(1).And(permanent.eq(0)).rename("mapped_nonpermanent_flood")
        observed = raw.updateMask(valid).rename("observed_nonpermanent_flood")
        evidence = raw.addBands(observed).addBands(clear.updateMask(valid))
        reducer = ee.Reducer.sum().unweighted().combine(ee.Reducer.count().unweighted(), sharedInputs=True)
        try:
            for index, (region, ownership, _) in enumerate(partitions):
                part = {"partition": index}
                event["partitions"].append(part)
                try:
                    part["statistics"] = evidence.updateMask(ownership).reduceRegion(
                        reducer=reducer, geometry=region, crs=ee.Projection(GRID_CRS, GRID_TRANSFORM),
                        scale=250, maxPixels=PIXEL_LIMIT, bestEffort=False, tileScale=2,
                    ).getInfo()
                except VerificationDeadlineExceeded:
                    raise
                except Exception as exc:
                    part["error"] = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            event.update(partitioned_finding(event))
            result["retrieved_at"] = now()
            if event["computation_complete"]:
                result["unreviewed_event_ids"].remove(event_id)
        if not event["computation_complete"]:
            result["status"] = "partial"
    result["finding"] = "explicit_event_batch_reviewed_remaining_events_unreviewed"
    return result


def verify_corrections(ee, project, query, requested):
    """Only the two requested corrections; rainfall and Bengaluru flood queries are skipped."""
    report = {"started_at": now(), "project_requested": project, "query_parameters": query,
              "access": {"initialization": "not_verified"}, "pilots": {}, "training_dataset_ready": False}
    stage = "access"
    try:
        report["access"] = probe_access(ee, project)
        for pilot, names in PILOTS.items():
            stage = f"boundary:{pilot}"
            geometry, boundary = find_boundary(ee, names)
            collections = {}
            report["pilots"][pilot] = {"boundary": boundary, "collections": collections}
            sources = [DEM_ID] + ([FLOOD_ID] if pilot == "Udupi" else [])
            for source in sources:
                stage = f"collection:{pilot}:{source}"
                result = {"source_id": source, "retrieved_at": now(), "status": "available"}
                collections[source] = result  # Shared result survives total deadline exceptions.
                try:
                    if source == DEM_ID:
                        _inspect_collection(ee, source, geometry, query, result)
                    else:
                        review_udupi_batch(ee, geometry, result, requested)
                except VerificationDeadlineExceeded:
                    result["status"] = "partial"
                    raise
                except Exception as exc:
                    result.update(status="partial", error={"type": type(exc).__name__, "message": str(exc)})
        report["status"] = "partial" if any(c["status"] == "partial" for p in report["pilots"].values()
                                             for c in p["collections"].values()) else "completed_bounded_checks"
    except (Exception, VerificationDeadlineExceeded) as exc:
        report.update(status="stopped", error={"stage": stage, "type": type(exc).__name__, "message": str(exc)})
    report["finished_at"] = now()
    return report


def verify(ee, project, query):
    report = {
        "started_at": now(), "project_requested": project,
        "query_parameters": query, "access": {"initialization": "not_verified"},
        "pilots": {}, "training_dataset_ready": False,
        "absence_policy": "Unrecorded or unobserved floods are unknown, never verified nonflood labels.",
    }
    stage = "access"
    partial = False
    try:
        report["access"] = probe_access(ee, project)
        for pilot, names in PILOTS.items():
            stage = f"boundary:{pilot}"
            try:
                geometry, boundary = find_boundary(ee, names)
            except VerificationDeadlineExceeded:
                raise
            except Exception as exc:
                report["pilots"][pilot] = {"boundary": None, "collections": {},
                                           "error": {"type": type(exc).__name__, "message": str(exc)}}
                partial = True
                continue
            report["pilots"][pilot] = {"boundary": boundary, "collections": {}}
            for source_id in COLLECTIONS:
                stage = f"collection:{pilot}:{source_id}"
                result = inspect_collection(ee, source_id, geometry, query)
                report["pilots"][pilot]["collections"][source_id] = result
                partial = partial or "error" in result
        report["status"] = "partial" if partial else "completed_bounded_checks"
    except (Exception, VerificationDeadlineExceeded) as exc:
        report["status"] = "stopped"
        report["error"] = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
    report["finished_at"] = now()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("EE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
                        help="Existing authorized Google Cloud project ID; otherwise use SDK configuration")
    parser.add_argument("--day", default="2018-08-15", help="One historical rainfall day (YYYY-MM-DD)")
    parser.add_argument("--plan", action="store_true", help="Print query parameters without importing EE or using credentials")
    parser.add_argument("--pilot-corrections", action="store_true", help="Only DEM mosaics and a partitioned Udupi flood batch")
    parser.add_argument("--udupi-event-ids", default=",".join(map(str, UDUPI_BATCH)),
                        help="At most three original event IDs, comma-separated")
    args = parser.parse_args(argv)
    try:
        query = plan(args.day)
        requested = [int(value) for value in args.udupi_event_ids.split(",")]
        if not 1 <= len(requested) <= 3 or len(set(requested)) != len(requested):
            raise ValueError("Specify one to three distinct Udupi event IDs")
        if args.pilot_corrections:
            query.update(mode="pilot_corrections", udupi_event_ids=requested,
                         flood_partitions=4, grid_crs=GRID_CRS, grid_transform=GRID_TRANSFORM,
                         dem_scale_m=30, dem_tile_limit=512, flood_inventory_limit=64)
    except ValueError as exc:
        parser.error(str(exc))
    if args.plan:
        print(json.dumps(query, indent=2))
        return 0
    try:
        ee = importlib.import_module("ee")
    except ImportError as exc:
        print(json.dumps({"status": "stopped", "retrieved_at": now(), "error": str(exc),
                          "install": "Install scripts/requirements-earthengine.txt in a separate environment"}, indent=2))
        return 2
    with wall_limit(query["wall_seconds"]):
        report = (verify_corrections(ee, args.project, query, requested) if args.pilot_corrections
                  else verify(ee, args.project, query))
    report["earthengine_api_version"] = ee.__version__
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "completed_bounded_checks" else 2


if __name__ == "__main__":
    raise SystemExit(main())
