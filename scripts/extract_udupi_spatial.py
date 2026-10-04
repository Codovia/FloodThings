#!/usr/bin/env python3
"""Small, read-only Earth Engine raster downloads; exact cell polygons, no flood labels."""
import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_udupi_history as history
import verify_earth_engine as verification

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data/processed/udupi_historical_v1"
VERSION = "udupi_flood_spatial_v1"
EXPECTED = {2728: 33, 3551: 23}
BANDS = ["flooded", "jrc_perm_water", "clear_views", "observation_valid", "qualified_floodwater"]
NODATA = -9999
MAX_BYTES = 4 * 1024 * 1024
TO_WGS84 = Transformer.from_crs(verification.GRID_CRS, "EPSG:4326", always_xy=True)


def read_history():
    """Require intact source bytes; normalization and automatic repair are never processing steps."""
    history.validate_version(HISTORY)
    original_manifest = json.loads((HISTORY / "manifest.json").read_text())
    with (HISTORY / "event_evidence.csv").open("r", newline="", encoding="utf-8") as handle:
        events = list(csv.DictReader(handle))
    history.require({int(e["event_id"]): int(e["positive_observed_pixels"]) for e in events} == EXPECTED,
                    "Previous evidence differs from the approved 33/23 counts")
    return events, {"event_csv_formatting_changed": False,
                    "canonical_event_csv_sha256": original_manifest["files"]["event_evidence.csv"]["sha256"],
                    "note": "Exact raw input bytes match the original manifest. Input files were only read."}


def download_parameters(bounds):
    windows = verification.partition_windows(bounds)
    x0, x1 = min(w[0] for w in windows), max(w[1] for w in windows)
    y0, y1 = min(w[2] for w in windows), max(w[3] for w in windows)
    width, height = x1 - x0, y1 - y0
    history.require(width * height <= verification.PIXEL_LIMIT, "Export exceeds the existing pixel ceiling")
    history.require(width * height * len(BANDS) * 4 < MAX_BYTES, "Export exceeds the 4 MiB application ceiling")
    return {"crs": verification.GRID_CRS, "crs_transform": [250, 0, x0 * 250, 0, -250, -y0 * 250],
            "dimensions": [width, height], "format": "GEO_TIFF", "filePerBand": False,
            "bands": BANDS}, windows


def qualified_export(ee, image, geometry):
    flooded, permanent, clear = image.select("flooded"), image.select("jrc_perm_water"), image.select("clear_views")
    valid = flooded.mask().And(permanent.mask()).And(clear.mask()).And(clear.gt(0))
    qualified = flooded.eq(1).And(permanent.eq(0)).updateMask(valid).rename("qualified_floodwater")
    product = image.select(BANDS[:3]).addBands(valid.rename("observation_valid")).addBands(qualified)
    # Reproject the qualification and source bands to the same verified grid before district clipping.
    return (product.updateMask(qualified).toFloat()
            .reproject(crs=verification.GRID_CRS, crsTransform=verification.GRID_TRANSFORM)
            .clip(geometry).unmask(NODATA, sameFootprint=False))


def bounded_download(session, url, path):
    history.require_not_completed(path.parent)
    # Signed download URLs are transient credentials: never store or log them.
    history.require(url.startswith("https://earthengine.googleapis.com/"), "Unexpected download host")
    with session.get(url, stream=True, timeout=(5, 10), allow_redirects=False) as response:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        history.require(not length or int(length) <= MAX_BYTES, "Download Content-Length exceeds ceiling")
        total = 0
        with path.open("xb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                history.require(total <= MAX_BYTES, "Download exceeds ceiling")
                handle.write(chunk)
    return {"bytes": total, "retrieved_at": verification.now()}


def cell_geometry(affine, row, col, boundary):
    # These are the actual raster cell edges, not boxes approximating flood features.
    corners = [(col, row), (col + 1, row), (col + 1, row + 1), (col, row + 1), (col, row)]
    edges = []
    for a, b in zip(corners, corners[1:]):
        # Preserve straight projected edges accurately when transformed to geographic coordinates.
        for step in range(8):
            f = step / 8
            edges.append(affine @ (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
    polygon = transform(TO_WGS84.transform, Polygon(edges))
    return polygon.intersection(boundary)


def raster_features(path, parameters, boundary_feature, event_id, expected_count):
    boundary = shape(boundary_feature["geometry"])
    history.require(boundary.is_valid and not boundary.is_empty, "Invalid genuine district geometry")
    history.require(path.stat().st_size <= MAX_BYTES, "Raster file exceeds ceiling")
    with rasterio.open(path) as src:
        affine = Affine(*parameters["crs_transform"])
        history.require(src.crs.to_epsg() == 32643, "Raster CRS mismatch")
        history.require(src.transform == affine, "Export-grid alignment mismatch")
        history.require([src.width, src.height] == parameters["dimensions"] and src.count == len(BANDS), "Raster dimensions/bands mismatch")
        data = src.read()
        history.require(np.all(np.isfinite(data)), "Non-finite raster values")
        retained = np.any(data != NODATA, axis=0)
        history.require(np.all(np.all(data[:, retained] != NODATA, axis=0)), "Incomplete observation masks in retained pixels")
        values = data[:, retained]
        history.require(np.all((values[0] == 1) & (values[1] == 0) & (values[2] > 0) &
                               (values[3] == 1) & (values[4] == 1)), "Flood/clear-view/permanent-water criteria violated")
        positions = list(zip(*np.nonzero(retained)))
        outside = [(int(row), int(col)) for row, col in positions if not boundary.covers(Point(*TO_WGS84.transform(*(affine @ (col + 0.5, row + 0.5)))))]
        history.require(all(cell_geometry(affine, row, col, boundary).area > 0 for row, col in outside),
                        "Download retained cells wholly outside district; clipping investigation required")
        history.require(len(positions) - len(outside) == expected_count,
                        f"Spatial reconciliation failed for {event_id}: expected {expected_count}, exported {int(retained.sum())}; centres inside district {len(positions)-len(outside)}; outside-centre raster row/cols {outside}; investigate grid/masks, do not alter counts")
        features = []
        for row, col in positions:
            if (int(row), int(col)) in outside:
                continue  # Match the previous unweighted centre-in-district reduction exactly.
            centre = TO_WGS84.transform(*(affine @ (col + 0.5, row + 0.5)))
            history.require(boundary.covers(Point(*centre)), "Qualifying pixel centre outside district")
            polygon = cell_geometry(affine, int(row), int(col), boundary)
            history.require(not polygon.is_empty and polygon.is_valid and polygon.geom_type in ("Polygon", "MultiPolygon"), "Invalid clipped cell geometry")
            history.require(polygon.difference(boundary).area < 1e-15, "Cell geometry outside district beyond floating-point tolerance")
            features.append({"type": "Feature", "geometry": mapping(polygon), "properties": {
                "event_id": event_id, "grid_col": int(affine.c / 250) + int(col),
                "grid_row": int(-affine.f / 250) + int(row), "flooded": 1, "jrc_perm_water": 0,
                "clear_views": float(data[2, row, col]), "observation_valid": 1,
                "processing_scale_m": 250, "evidence": "historical_event_window_maximum"}})
        metadata = {"crs": src.crs.to_string(), "transform": list(affine)[:6],
                    "dimensions": [src.width, src.height], "bands": BANDS, "dtypes": list(src.dtypes),
                    "nodata_in_file": src.nodata, "unavailable_sentinel": NODATA,
                    "qualified_pixels": len(features), "geojson_crs": "OGC:CRS84 (longitude, latitude)",
                    "download_qualifying_pixels": len(positions), "excluded_boundary_overlap_cells": outside,
                    "reconciliation": "Earth Engine clip retains edge-overlap cells; map includes only centres within district, matching prior unweighted reduction. Original download bytes are retained unchanged.",
                    "district_clipping": "qualified pixel centres inside genuine district; exact cell polygons intersected with district"}
    return {"type": "FeatureCollection", "features": features}, metadata


def write_json(path, value):
    history.require_not_completed(path.parent)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"), allow_nan=False)
        handle.write("\n")


def stage(name):
    print(json.dumps({"query_stage": name, "timestamp": verification.now()}), flush=True)


def validate_version(directory):
    """Reconstruct geometry in memory from read-only rasters; never write to the version."""
    manifest = json.loads((directory / "manifest.json").read_text())
    history.require(manifest["version"] == VERSION and manifest["project"] == "floodpulse", "Spatial manifest version/project mismatch")
    history.require(manifest["source_id"] == verification.FLOOD_ID and manifest["boundary_id"] == history.BOUNDARY_SHAPE_ID,
                    "Spatial manifest source/boundary mismatch")
    history.require(manifest["sources"] == {k: history.SOURCES[k] for k in (verification.FLOOD_ID, verification.BOUNDARY_ID)}, "Spatial source licensing mismatch")
    history.require({e["event_id"] for e in manifest["events"]} == set(EXPECTED) and len(manifest["events"]) == 2, "Spatial event inventory mismatch")
    for name, metadata in manifest["files"].items():
        history.require(Path(name).name == name and history.checksum(directory / name) == metadata["sha256"], f"Spatial checksum mismatch: {name}")
    boundary = json.loads((directory / "udupi_boundary.geojson").read_text())
    history.require(boundary["properties"]["shapeID"] == history.BOUNDARY_SHAPE_ID, "Boundary feature identity mismatch")
    counts = {}
    for event in manifest["events"]:
        eid = event["event_id"]
        approved = next(spec for spec in history.EVENTS if spec[0] == eid)
        history.require(event["image_id"] == history.event_asset(*approved) and event["start_date"] == approved[1] and event["end_date_inclusive"] == approved[2], "Spatial event identity/dates mismatch")
        geojson, raster = raster_features(directory / event["raster_file"], manifest["download_parameters"], boundary, eid, EXPECTED[eid])
        saved = json.loads((directory / event["geometry_file"]).read_text())
        history.require(saved == json.loads(json.dumps(geojson)), "GeoJSON differs from raster cell geography/evidence")
        history.require(json.loads(json.dumps(raster)) == event["raster_metadata"] and event["qualified_pixel_count"] == EXPECTED[eid], "Raster metadata/count mismatch")
        counts[eid] = len(geojson["features"])
    return counts


def extract(ee, session, staged):
    history.require_not_completed(staged)
    previous, input_validation = read_history()
    started = verification.now()
    with verification.wall_limit(120):
        stage("access")
        access = verification.probe_access(ee, "floodpulse")
        stage("udupi_boundary")
        geometry, boundary_metadata = verification.find_boundary(ee, verification.PILOTS["Udupi"])
        history.require(boundary_metadata["properties"]["shapeID"] == history.BOUNDARY_SHAPE_ID, "Verified boundary identity changed")
        boundary = {"type": "Feature", "properties": boundary_metadata["properties"], "geometry": geometry.getInfo()}
        write_json(staged / "udupi_boundary.geojson", boundary)
        bounds = geometry.bounds(maxError=1, proj=ee.Projection(verification.GRID_CRS)).coordinates().getInfo()[0]
        parameters, windows = download_parameters(bounds)
        manifest = {"version": VERSION, "schema_version": 1, "project": "floodpulse", "started_at": started,
                    "access": access, "source_id": verification.FLOOD_ID, "boundary_id": history.BOUNDARY_SHAPE_ID,
                    "boundary": boundary_metadata, "download_parameters": parameters,
                    "partition_windows": windows, "reference_grid_transform": verification.GRID_TRANSFORM,
                    "request_deadline_ms": 10000, "download_connect_read_timeouts_seconds": [5, 10],
                    "retries": 0, "wall_seconds": 120, "max_download_bytes": MAX_BYTES,
                    "max_pixels": verification.PIXEL_LIMIT, "bestEffort": False,
                    "sources": {k: history.SOURCES[k] for k in (verification.FLOOD_ID, verification.BOUNDARY_ID)},
                    "observation_criteria": "flooded==1 AND jrc_perm_water==0; flooded/permanent/clear masks valid AND clear_views>0",
                    "extent_semantics": "historical_event_window_maximum_not_daily_occurrence",
                    "geometry_method": "Each qualifying raster cell's projected edges transformed to longitude/latitude (8 segments per edge), then intersected with the genuine district polygon; no centroids/circles or flood bounding boxes.",
                    "limitations": ["Historical evidence only; not current flooding, flood prediction, flooded roads or evacuation advice.",
                                    "Source cloud/mask coverage and selected event maps do not establish daily flood occurrence or flood absence.",
                                    "250 m processing grid; MODIS classification is 250 m although catalogue storage grid is 30 m.",
                                    "Modern geoBoundaries v6 geometry is not verified as the historical administrative boundary."],
                    "historical_dataset_sha256": {p.name: history.checksum(p) for p in HISTORY.iterdir() if p.is_file()},
                    "historical_input_validation": input_validation,
                    "events": []}
        for old in previous:
            eid = int(old["event_id"])
            stage(f"event_{eid}_identity")
            image = ee.Image(old["image_id"])
            properties = image.toDictionary(["id", "system:id", "system:index", "system:time_start", "system:time_end", "system:version"]).getInfo()
            history.require(properties["id"] == eid and properties["system:time_start"] == int(old["source_time_start_ms"]) and properties["system:time_end"] == int(old["source_time_end_ms"]), "Original flood event properties changed")
            raster_file, geometry_file = f"event_{eid}.tif", f"event_{eid}.geojson"
            stage(f"event_{eid}_download_url")
            # The SDK injects an Image into its params dict; keep manifest parameters serializable.
            url = qualified_export(ee, image, geometry).getDownloadURL(dict(parameters))
            stage(f"event_{eid}_bounded_download")
            downloaded = bounded_download(session, url, staged / raster_file)
            stage(f"event_{eid}_raster_reconciliation")
            geojson, raster_metadata = raster_features(staged / raster_file, parameters, boundary, eid, EXPECTED[eid])
            write_json(staged / geometry_file, geojson)
            manifest["events"].append({"event_id": eid, "image_id": old["image_id"], "start_date": old["start_date"],
                "end_date_inclusive": old["end_date_inclusive"], "original_properties": properties,
                "qualified_pixel_count": len(geojson["features"]), "previous_verified_pixel_count": EXPECTED[eid],
                "processing_scale_m": 250, "raster_file": raster_file, "geometry_file": geometry_file,
                "raster_metadata": raster_metadata, "download": downloaded})
    manifest["finished_at"] = verification.now()
    manifest["code_sha256"] = {p.name: history.checksum(p) for p in (Path(__file__), Path(verification.__file__), Path(history.__file__))}
    manifest["files"] = {p.name: {"sha256": history.checksum(p), "bytes": p.stat().st_size} for p in staged.iterdir() if p.is_file()}
    write_json(staged / "manifest.json", manifest)
    return validate_version(staged)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=["floodpulse"], default="floodpulse")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed" / VERSION)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            counts = validate_version(args.output)
        else:
            history.require_new_output(args.output)
            ee, requests = importlib.import_module("ee"), importlib.import_module("requests")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".udupi-spatial-", dir=args.output.parent) as temporary:
                staged = Path(temporary)
                with requests.Session() as session:
                    counts = extract(ee, session, staged)
                args.output.mkdir()
                try:
                    for path in sorted(staged.iterdir(), key=lambda p: p.name == "manifest.json"):
                        os.rename(path, args.output / path.name)
                    history.seal_version(args.output)
                except BaseException:
                    shutil.rmtree(args.output)  # Only this invocation's newly reserved output.
                    raise
        print(json.dumps({"status": "verified", "output": str(args.output), "qualified_pixel_counts": counts}))
        return 0
    except (Exception, verification.VerificationDeadlineExceeded) as exc:
        print(json.dumps({"status": "failed_no_new_version", "error": {"type": type(exc).__name__, "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
