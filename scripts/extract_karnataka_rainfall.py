#!/usr/bin/env python3
"""Bounded CHIRPS 2025 monthly extraction; SOI geometry NEVER leaves local processing.

Only the existing August smoke and individual 2025 months are supported. No backfill.
Tables remain local pending permission review of SOI-based aggregate publication.
"""
import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_earth_engine as verification
import verify_soi_karnataka as soi

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / "data/working/karnataka_soi_abdb2025_v1"
SOURCE = "UCSB-CHG/CHIRPS/DAILY"
SOURCE_URL = "https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY"
SOURCE_GEOMETRY = "SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA"
# Fixed geographic download window, NOT an administrative boundary or SOI export.
WINDOW = [73.5, 11.0, 79.0, 19.0]
GRID = [0.05, 0, -180, 0, -0.05, 50]
NODATA = -9999
MAX_BYTES = 1024 * 1024
DEFAULT_EE_DEADLINE_SECONDS = 10
MAX_ATTEMPTS = 3
FIELDS = ["source_state_lgd_code", "source_district_lgd_code", "district_name_original", "nic_exact_name",
          "identity_status", "geometry_edition", "geometry_source_id", "geometry_version",
          "date", "source_collection", "source_image_id", "source_time_start_ms", "source_time_end_ms",
          "image_asset_version", "units", "mean_mm_per_day", "min_mm_per_day", "max_mm_per_day",
          "expected_pixel_count", "valid_pixel_count", "valid_fraction", "status", "retrieved_at"]


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def require_new_output(path):
    path = Path(path)
    require(not path.exists(), "Output version exists; never overwrite")
    require(all(not (parent / "manifest.json").exists() for parent in path.resolve().parents),
            "Cannot write inside a completed version")


def failure_category(exc):
    """Inspect types/statuses without persisting provider messages or signed URLs."""
    # Offline validators do not require the optional live requests/EE environment.
    try:
        from requests.exceptions import ConnectionError as HTTPConnectionError, Timeout as HTTPTimeout
    except ImportError:
        HTTPConnectionError, HTTPTimeout = ConnectionError, TimeoutError
    if isinstance(exc, BoundedRequestFailure):
        return exc.category, exc.http_status
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, HTTPTimeout)):
            return "network_timeout", None
        if isinstance(current, (ConnectionError, HTTPConnectionError)):
            return "network_connection", None
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None) or getattr(getattr(current, "resp", None), "status", None)
        if status in {429, 500, 502, 503, 504}:
            return "transient_http", status
        if status == 404 or "image asset" in str(current).lower() and "not found" in str(current).lower():
            # EE's 'not found' can also mean lack of permission, not verified absence.
            return "source_unavailable_or_access_denied", status
        if status in {401, 403}:
            return "authorization_error", status
        current = current.__cause__ or current.__context__
    return "non_retryable_error", None


class BoundedRequestFailure(RuntimeError):
    def __init__(self, operation, day, attempts, category, error_type, http_status=None):
        self.operation, self.day, self.attempts = operation, day, attempts
        self.category, self.error_type, self.http_status = category, error_type, http_status
        super().__init__(f"{operation} failed after {attempts} attempt(s): {category} ({error_type}); signed URL withheld; provider error text withheld")


def bounded_request(call, operation, log, day=None, attempts=MAX_ATTEMPTS, sleep=None):
    require(type(attempts) is int and 1 <= attempts <= MAX_ATTEMPTS, "Request attempts must be 1–3")
    sleep = sleep or time.sleep
    for attempt in range(1, attempts + 1):
        event = {"operation": operation, "date": day, "attempt": attempt, "started_at": now()}
        try:
            result = call()
        except Exception as exc:
            category, status = failure_category(exc)
            error_type = exc.error_type if isinstance(exc, BoundedRequestFailure) else type(exc).__name__
            retry = category in {"network_timeout", "network_connection", "transient_http"} and attempt < attempts
            delay = 2**attempt if retry else 0
            event.update(status="failed", category=category, error_type=error_type, http_status=status,
                         retry_scheduled=retry, backoff_seconds=delay, finished_at=now())
            with log.open("a") as stream:
                stream.write(json.dumps(event) + "\n")
            if not retry:
                raise BoundedRequestFailure(operation, day, attempt, category, error_type, status) from None
            sleep(delay)
        else:
            event.update(status="succeeded", finished_at=now())
            with log.open("a") as stream:
                stream.write(json.dumps(event) + "\n")
            return result


def initialize_access(ee, deadline_seconds, log):
    require(type(deadline_seconds) is int and 1 <= deadline_seconds <= 60, "EE deadline must be 1–60 seconds")
    # Disable client discovery and request retries BEFORE initialization; one retry owner.
    ee.data.setMaxRetries(0)
    bounded_request(lambda: ee.Initialize(project="floodpulse"), "initialization", log)
    # setDeadline rebuilds the initialized transport; its discovery retries are also zero.
    bounded_request(lambda: ee.data.setDeadline(deadline_seconds * 1000), "configure_deadline", log)
    value = bounded_request(lambda: ee.Number(1).getInfo(), "constant_probe", log)
    require(value == 1, "Earth Engine constant probe returned an unexpected value")
    return {"initialization": "succeeded", "constant_probe": value, "retrieved_at": now()}


def download_with_retries(session, url, path, log, day):
    attempt = 0
    def retrieve():
        nonlocal attempt
        attempt += 1
        temporary = path.with_name(path.stem + f".attempt{attempt}.partial.tif")
        result = download(session, url, temporary)
        require(not path.exists(), "Downloaded raster already exists; never overwrite")
        temporary.rename(path)
        return result
    return bounded_request(retrieve, "raster_download", log, day)


def requested_dates(mode, month=8):
    require(mode in {"smoke", "month"}, "Only the authorized 2025 extraction is supported")
    require(type(month) is int and 1 <= month <= 12, "Invalid 2025 month")
    require(mode != "smoke" or month == 8, "Smoke is the existing August pilot only")
    return [(date(2025, month, 1) + timedelta(days=i)).isoformat()
            for i in range(1 if mode == "smoke" else calendar.monthrange(2025, month)[1])]


def download_parameters(grid):
    require(grid["crs"] == "EPSG:4326" and np.allclose(grid["transform"], GRID, rtol=0, atol=1e-12),
            "CHIRPS native grid changed; no resampling substitute")
    native = Affine(*grid["transform"])
    col0, row0 = ~native @ (WINDOW[0], WINDOW[3])
    col1, row1 = ~native @ (WINDOW[2], WINDOW[1])
    require(all(abs(v - round(v)) < 1e-9 for v in (col0, row0, col1, row1)), "Window is not native-grid aligned")
    cropped = native @ Affine.translation(round(col0), round(row0))
    return {"crs": grid["crs"], "crs_transform": list(cropped)[:6],
            "dimensions": [round(col1-col0), round(row1-row0)], "format": "GEO_TIFF",
            "bands": ["precipitation", "valid_mask"], "filePerBand": False}


def image_record(info, day):
    asset = f"{SOURCE}/{day.replace('-', '')}"
    require(info.get("id") == asset and len(info.get("bands", [])) == 1, "Wrong CHIRPS image identity/bands")
    band = info["bands"][0]
    require(band["id"] == "precipitation" and band["data_type"]["precision"] == "float", "Unexpected rainfall band precision")
    props = info["properties"]
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)
    require(props.get("system:time_start") == start and props.get("system:time_end") == start + 86400000,
            "Unexpected CHIRPS daily temporal semantics")
    grid = {"crs": band["crs"], "transform": band["crs_transform"]}
    download_parameters(grid)
    version = info.get("version")
    # EE may encode the same integer as a JSON floating-point number. Convert only
    # positive, exact integers within float's safe integer range; never invent a version.
    require(type(version) is int and version > 0 or type(version) is float and math.isfinite(version)
            and version.is_integer() and 0 < version <= 2**53, "Missing or inexact source asset version")
    return {"date": day, "source_image_id": asset, "source_time_start_ms": start,
            "source_time_end_ms": start + 86400000, "image_asset_version": int(version),
            "source_asset_version_original": version, "source_asset_version_json_type": type(version).__name__,
            "native_grid": grid, "native_dimensions": band["dimensions"], "units": "mm/day"}


def validate_image_record(record):
    day = record["date"]
    require(date.fromisoformat(day).year == 2025, "Image date outside authorized 2025 extraction")
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)
    require(record["source_image_id"] == f"{SOURCE}/{day.replace('-', '')}"
            and record["source_time_start_ms"] == start and record["source_time_end_ms"] == start + 86400000
            and isinstance(record["image_asset_version"], int) and record["image_asset_version"] > 0
            and record["units"] == "mm/day" and record["native_dimensions"] == [7200, 2000],
            "Image provenance/units/temporal semantics mismatch")
    download_parameters(record["native_grid"])
    require(datetime.fromisoformat(record["download"]["retrieved_at"]).tzinfo is not None, "Invalid retrieval date")


def export_image(image):
    rain = image.select("precipitation")
    # Sentinel encodes missingness, never invented rain. Separate source mask preserves valid zeros.
    return (rain.unmask(NODATA, sameFootprint=False)
            .addBands(rain.mask().unmask(0, sameFootprint=False).rename("valid_mask")).toFloat())


def download(session, url, path):
    require(url.startswith("https://earthengine.googleapis.com/"), "Unexpected download host")
    total, started = 0, time.monotonic()
    try:
        with session.get(url, stream=True, timeout=(5, 15), allow_redirects=False) as response:
            response.raise_for_status()
            require(not response.headers.get("Content-Length") or int(response.headers["Content-Length"]) <= MAX_BYTES,
                    "Raster exceeds 1 MiB ceiling")
            with Path(path).open("xb") as stream:
                for chunk in response.iter_content(chunk_size=65536):
                    total += len(chunk)
                    require(total <= MAX_BYTES and time.monotonic()-started <= 30, "Download byte/time ceiling exceeded")
                    stream.write(chunk)
    except Exception as exc:
        # Request exceptions may contain signed URLs. Never expose them or their tokens.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        category, _ = failure_category(exc)
        raise BoundedRequestFailure("raster_download", None, 1, category, type(exc).__name__, status) from None
    return {"retrieved_at": now(), "bytes": total, "sha256": soi.digest(path),
            "request": {"host": "earthengine.googleapis.com", "timeouts_seconds": [5, 15],
                        "elapsed_ceiling_seconds": 30, "byte_ceiling": MAX_BYTES, "retries": 0}}


def read_raster(path, parameters):
    with rasterio.open(path) as src:
        require(src.crs == rasterio.crs.CRS.from_string(parameters["crs"]), "Raster CRS mismatch")
        require(src.transform.almost_equals(Affine(*parameters["crs_transform"]), precision=1e-10), "Raster grid alignment mismatch")
        require([src.width, src.height] == parameters["dimensions"] and src.count == 2, "Raster dimensions/bands mismatch")
        require(src.dtypes == ("float32", "float32"), "Raster altered native float precision")
        values, mask = src.read(1), src.read(2)
        require(np.isin(mask, [0, 1]).all(), "Unexpected source mask values")
        valid = mask == 1
        require(np.isfinite(values[valid]).all() and (values[valid] >= 0).all(), "Nonfinite or negative valid rainfall")
        require((values[~valid] == NODATA).all(), "Missing pixels lost explicit sentinel encoding")
        metadata = {"crs": src.crs.to_string(), "transform": list(src.transform)[:6],
                    "dimensions": [src.width, src.height], "bands": 2, "dtype": "float32",
                    "geotiff_nodata": (src.nodata if src.nodata is None or math.isfinite(src.nodata)
                                       else "-Infinity" if src.nodata < 0 else "Infinity" if src.nodata > 0 else "NaN"),
                    "nodata_encoding": NODATA,
                    "mask_rule": "second band is original source mask; 0=missing, 1=valid; zeros in valid rain remain measured values",
                    "valid_window_pixels": int(valid.sum()), "window_pixels": int(valid.size)}
    return values, valid, metadata


def load_boundaries(directory):
    soi.validate_version(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["karnataka_district_count"] == 31 and manifest["nic_exact_name_candidates"] == 12
            and len(manifest["nic_unmatched_names"]) == 19 and manifest["current_lgd_verified_identities"] == 0,
            "Boundary identity baseline changed; explicit review needed")
    source = soi.read_source(directory / "districts.shp", "STATE_UT", district=True)
    districts = [{"identity": identity, "geometry": shape(record["shape"].__geo_interface__)}
                 for identity, record in zip(manifest["district_records"], source["records"])]
    return districts, source["crs"], manifest


def district_masks(districts, source_crs, parameters):
    affine = Affine(*parameters["crs_transform"])
    width, height = parameters["dimensions"]
    rows, cols = np.indices((height, width))
    longitude, latitude = affine @ (cols + .5, rows + .5)
    to_native = Transformer.from_crs(parameters["crs"], source_crs, always_xy=True)
    x, y = to_native.transform(longitude, latitude)
    to_geographic = Transformer.from_crs(source_crs, parameters["crs"], always_xy=True)
    results = []
    for district in districts:
        geometry = district["geometry"]
        require(geometry.is_valid and not geometry.is_empty, "Invalid local district geometry")
        # Bounds check in geographic coordinates, including all source vertices, never transmitted.
        from shapely.ops import transform
        bounds = transform(to_geographic.transform, geometry).bounds
        require(bounds[0] >= WINDOW[0] and bounds[1] >= WINDOW[1] and bounds[2] <= WINDOW[2] and bounds[3] <= WINDOW[3],
                "Download window fails to cover local district geometry")
        results.append(contains_xy(geometry, x, y))
    require(np.max(np.sum(results, axis=0)) <= 1, "A native cell centre belongs to multiple districts")
    return results, (x, y)


def summarize(districts, masks, values, valid, image, geometry_version):
    rows = []
    for district, membership in zip(districts, masks):
        identity = district["identity"]
        observed = values[membership & valid].astype(np.float64)
        expected, count = int(membership.sum()), int(observed.size)
        rows.append({"source_state_lgd_code": identity["state_lgd_code_as_supplied_by_soi"],
                     "source_district_lgd_code": identity["district_lgd_code_as_supplied_by_soi"],
                     "district_name_original": identity["district_name_original"], "nic_exact_name": identity["nic_exact_name"],
                     "identity_status": "soi_supplied_identifier_pending_current_lgd_verification",
                     "geometry_edition": "2025", "geometry_source_id": SOURCE_GEOMETRY, "geometry_version": geometry_version,
                     **{k: image[k] for k in ("date", "source_image_id", "source_time_start_ms", "source_time_end_ms", "image_asset_version")},
                     "source_collection": SOURCE, "units": "mm/day",
                     "mean_mm_per_day": float(observed.mean()) if count else None,
                     "min_mm_per_day": float(observed.min()) if count else None,
                     "max_mm_per_day": float(observed.max()) if count else None,
                     "expected_pixel_count": expected, "valid_pixel_count": count,
                     "valid_fraction": count / expected if expected else None,
                     "status": "no_native_cell_centres" if not expected else "no_valid_pixels" if not count else
                               "available" if count == expected else "partial_pixel_coverage",
                     "retrieved_at": image["download"]["retrieved_at"]})
    return rows


def independent_checks(districts, centres, values, valid, rows):
    """Scalar Point.within + math.fsum, independent of vector membership/NumPy reduction."""
    x, y = centres
    checks = []
    for district in districts:
        identity = district["identity"]
        if identity["district_lgd_code_as_supplied_by_soi"] not in {"569", "565", "761"}:
            continue
        row = next(r for r in rows if r["source_district_lgd_code"] == identity["district_lgd_code_as_supplied_by_soi"])
        members = [(i, j) for i, j in np.ndindex(values.shape)
                   if Point(float(x[i, j]), float(y[i, j])).within(district["geometry"])]
        samples = [float(values[i, j]) for i, j in members if valid[i, j]]
        mean = math.fsum(samples) / len(samples) if samples else None
        require(len(members) == row["expected_pixel_count"] and len(samples) == row["valid_pixel_count"],
                "Independent cell-count reconciliation failed")
        require(mean is None and row["mean_mm_per_day"] is None or mean is not None and
                math.isclose(mean, row["mean_mm_per_day"], abs_tol=1e-10, rel_tol=1e-12), "Independent rainfall mean reconciliation failed")
        checks.append({"date": row["date"], "source_district_lgd_code": row["source_district_lgd_code"],
                       "expected_pixel_count": len(members), "valid_pixel_count": len(samples),
                       "scalar_mean_mm_per_day": mean, "matches_vector_calculation": True})
    return checks


def validate_rows(rows, identities, dates):
    expected = {(r["district_lgd_code_as_supplied_by_soi"], day) for r in identities for day in dates}
    keys = [(r["source_district_lgd_code"], r["date"]) for r in rows]
    require(len(keys) == len(set(keys)) and set(keys) == expected, "Duplicate or mismatched district-date coverage")
    lookup = {r["district_lgd_code_as_supplied_by_soi"]: r for r in identities}
    for row in rows:
        identity = lookup[row["source_district_lgd_code"]]
        require(row["district_name_original"] == identity["district_name_original"] and row["nic_exact_name"] == identity["nic_exact_name"]
                and row["source_state_lgd_code"] == "29" and row["geometry_edition"] == "2025"
                and row["identity_status"] == "soi_supplied_identifier_pending_current_lgd_verification", "Unreviewed district identity")
        require(row["source_collection"] == SOURCE and row["units"] == "mm/day"
                and row["source_image_id"] == f"{SOURCE}/{row['date'].replace('-', '')}"
                and row["geometry_source_id"] == SOURCE_GEOMETRY and row["geometry_version"] == soi.VERSION,
                "Source identity/units mismatch")
        start = int(datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc).timestamp() * 1000)
        require(row["source_time_start_ms"] == start and row["source_time_end_ms"] == start+86400000,
                "Rainfall observation-time mismatch")
        require(datetime.fromisoformat(row["retrieved_at"]).tzinfo is not None, "Missing retrieval timezone")
        valid, total = row["valid_pixel_count"], row["expected_pixel_count"]
        require(isinstance(valid, int) and isinstance(total, int) and 0 <= valid <= total, "Invalid pixel counts")
        if valid:
            require(all(v is not None and math.isfinite(v) and v >= 0 for v in
                        [row["min_mm_per_day"], row["mean_mm_per_day"], row["max_mm_per_day"]]), "Invalid rainfall values")
            require(row["min_mm_per_day"] <= row["mean_mm_per_day"] <= row["max_mm_per_day"], "Invalid rainfall summary order")
        else:
            require(all(row[k] is None for k in ("min_mm_per_day", "mean_mm_per_day", "max_mm_per_day")), "Missing rainfall must stay null")
        status = "no_native_cell_centres" if not total else "no_valid_pixels" if not valid else "available" if valid == total else "partial_pixel_coverage"
        require(row["status"] == status and row["valid_fraction"] == (valid / total if total else None), "Invalid missingness state")
    return {"requested_records": len(expected), "records": len(rows),
            "valid_records": sum(r["valid_pixel_count"] > 0 for r in rows),
            "complete_pixel_coverage_records": sum(r["status"] == "available" for r in rows),
            "partial_pixel_coverage_records": sum(r["status"] == "partial_pixel_coverage" for r in rows),
            "missing_observations": [{"date": r["date"], "source_district_lgd_code": r["source_district_lgd_code"], "status": r["status"]}
                                     for r in rows if not r["valid_pixel_count"]]}


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def write_dataset(directory, rows, manifest):
    directory = Path(directory)
    require_new_output(directory)
    directory.mkdir(parents=True)
    table = directory / "daily_rainfall.csv"
    with table.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {**manifest, "files": {"daily_rainfall.csv": soi.fingerprint(table)}}
    write_json(directory / "manifest.json", manifest)
    return manifest


def read_table(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("source_time_start_ms", "source_time_end_ms", "image_asset_version", "expected_pixel_count", "valid_pixel_count"):
            row[key] = int(row[key])
        for key in ("mean_mm_per_day", "min_mm_per_day", "max_mm_per_day", "valid_fraction"):
            row[key] = float(row[key]) if row[key] else None
        row["nic_exact_name"] = row["nic_exact_name"] or None
    return rows


def validate_dataset(directory, raw_directory, boundary_directory=BOUNDARIES):
    manifest = json.loads((directory / "manifest.json").read_text())
    require(set(p.name for p in directory.iterdir()) == {"daily_rainfall.csv", "manifest.json"}, "Unexpected dataset files")
    require(soi.fingerprint(directory / "daily_rainfall.csv") == manifest["files"]["daily_rainfall.csv"], "Table checksum mismatch")
    require(soi.fingerprint(raw_directory / "retrieval.jsonl") == manifest["raw_retrieval_log"], "Retrieval provenance checksum mismatch")
    if "request_attempt_log" in manifest:
        require(soi.fingerprint(raw_directory / "request_attempts.jsonl") == manifest["request_attempt_log"],
                "Request-attempt provenance checksum mismatch")
    require(manifest["geometry_provenance"]["working_manifest_sha256"] == soi.digest(boundary_directory / "manifest.json"), "Boundary manifest changed")
    districts, crs, boundary_manifest = load_boundaries(boundary_directory)
    parameters = manifest["download_parameters"]
    require(parameters == download_parameters({"crs": "EPSG:4326", "transform": GRID}), "Download parameters changed")
    masks, centres = district_masks(districts, crs, parameters)
    rows = read_table(directory / "daily_rainfall.csv")
    regenerated = []
    dates = requested_dates(manifest["mode"], manifest.get("month", 8))
    require([i["date"] for i in manifest["images"]] == dates, "Image date coverage mismatch")
    for image in manifest["images"]:
        validate_image_record(image)
        require(image["file"] == image["date"].replace("-", "") + ".tif", "Unexpected raw raster filename")
        path = raw_directory / image["file"]
        require(soi.digest(path) == image["download"]["sha256"] and path.stat().st_size == image["download"]["bytes"], "Raw rainfall checksum mismatch")
        values, valid, metadata = read_raster(path, parameters)
        require(metadata == image["raster_metadata"], "Raw raster metadata mismatch")
        regenerated.extend(summarize(districts, masks, values, valid, image, boundary_manifest["version"]))
    require(regenerated == rows, "Recalculation differs from archived table")
    result = validate_rows(rows, boundary_manifest["district_records"], dates)
    require(result == manifest["validation"], "Coverage validation mismatch")
    return result


def public_manifest(manifest):
    result = json.loads(json.dumps(manifest))
    # Scalar means are restricted SOI-based outputs, not publication-cleared metadata.
    result["independent_checks"] = [{k: v for k, v in r.items() if k != "scalar_mean_mm_per_day"}
                                     for r in result["independent_checks"]]
    result["published_content"] = "source metadata, methods, coverage and checksums only; local district rainfall table not published"
    return result


def cached_images(raw_directory):
    """Read-only reuse of completed daily downloads from an interrupted month."""
    log = raw_directory / "retrieval.jsonl"
    require(log.stat().st_size <= MAX_BYTES, "Partial retrieval log exceeds bounded size")
    result = {}
    for line in log.read_text().splitlines():
        record = json.loads(line)
        if record.get("stage") != "validated":
            continue
        validate_image_record(record)
        day = record["date"]
        require(day not in result and record["file"] == day.replace("-", "") + ".tif", "Duplicate or invalid cached image")
        path = raw_directory / record["file"]
        require(soi.digest(path) == record["download"]["sha256"] and path.stat().st_size == record["download"]["bytes"],
                "Cached raster checksum mismatch")
        _, _, metadata = read_raster(path, download_parameters(record["native_grid"]))
        require(metadata == record["raster_metadata"], "Cached raster metadata mismatch")
        result[day] = {k: v for k, v in record.items() if k != "stage"}
    require(len(result) <= 31, "Cache exceeds authorized month")
    return result


def extract(args, ee, session):
    for path in (args.output, args.raw_directory, args.metadata_output):
        require_new_output(path)
    districts, crs, boundaries = load_boundaries(args.boundaries)
    month = getattr(args, "month", 8)
    days = requested_dates(args.mode, month)
    parameters = download_parameters({"crs": "EPSG:4326", "transform": GRID})
    masks, centres = district_masks(districts, crs, parameters)
    rows, images, checks = [], [], []
    args.raw_directory.mkdir(parents=True)
    budget = 180 if args.mode == "smoke" else 900
    deadline_seconds = getattr(args, "ee_deadline_seconds", DEFAULT_EE_DEADLINE_SECONDS)
    request_log = args.raw_directory / "request_attempts.jsonl"
    with verification.wall_limit(budget):
        access = initialize_access(ee, deadline_seconds, request_log)
        reused = None
        cache_directory = getattr(args, "reuse_partial_raw", None)
        require(cache_directory is None or args.mode == "month", "Partial cache reuse is month-only")
        cache = cached_images(cache_directory) if cache_directory else {}
        require(set(cache).issubset(days), "Partial cache contains dates outside requested month")
        if args.reuse_smoke:
            require(args.mode == "month" and month == 8 and args.reuse_raw is not None,
                    "Reuse requires the August month, validated smoke and raw directories")
            validate_dataset(args.reuse_smoke, args.reuse_raw, args.boundaries)
            reused = json.loads((args.reuse_smoke / "manifest.json").read_text())
            require(reused["mode"] == "smoke", "Reuse input is not the one-day smoke version")
        for day in days:
            path = args.raw_directory / (day.replace("-", "") + ".tif")
            if reused and day == days[0]:
                record = json.loads(json.dumps(reused["images"][0]))
                shutil.copyfile(args.reuse_raw / record["file"], path)
                record["reused_from_smoke_manifest_sha256"] = soi.digest(args.reuse_smoke / "manifest.json")
            elif day in cache:
                record = json.loads(json.dumps(cache[day]))
                shutil.copyfile(cache_directory / record["file"], path)
                record["reused_from_partial_retrieval_log_sha256"] = soi.digest(cache_directory / "retrieval.jsonl")
            else:
                image = ee.Image(f"{SOURCE}/{day.replace('-', '')}")
                info = bounded_request(image.getInfo, "image_metadata", request_log, day)
                record = image_record(info, day)
                # Export arguments have only a fixed CHIRPS grid/window, NEVER a SOI feature.
                url = bounded_request(lambda: export_image(image).getDownloadURL(dict(parameters)),
                                      "download_url", request_log, day)
                record["download"] = download_with_retries(session, url, path, request_log, day)
                record["file"] = path.name
            # Preserve retrieval provenance before local validation, even if parsing later fails.
            with (args.raw_directory / "retrieval.jsonl").open("a") as stream:
                stream.write(json.dumps({"stage": "retrieved", **record}, allow_nan=False) + "\n")
            values, valid, metadata = read_raster(path, parameters)
            validate_image_record(record)
            record["raster_metadata"] = metadata
            observations = summarize(districts, masks, values, valid, record, boundaries["version"])
            if day in {days[0], f"2025-{month:02d}-15", days[-1]}:
                checks.extend(independent_checks(districts, centres, values, valid, observations))
            rows.extend(observations)
            images.append(record)
            # Append-only original retrieval provenance also survives a later request/deadline failure.
            with (args.raw_directory / "retrieval.jsonl").open("a") as stream:
                stream.write(json.dumps({"stage": "validated", **record}, allow_nan=False) + "\n")
            print(json.dumps({"completed_date": day, "district_records": len(observations), "raw_bytes": path.stat().st_size}), flush=True)
    validation = validate_rows(rows, boundaries["district_records"], days)
    manifest = {"version": args.output.name, "mode": args.mode, "month": month,
                "raw_directory": str(args.raw_directory),
                "created_at": now(), "project": "floodpulse", "access": access,
                "stage_1_complete": False,
                "source": {"collection": SOURCE, "version": "CHIRPS v2.0 Final", "band": "precipitation", "units": "mm/day",
                           "url": SOURCE_URL, "license": "Public domain", "license_checked_on": "2026-10-04",
                           "citation": "Funk et al. (2015), doi:10.1038/sdata.2015.66", "native_resolution_degrees": 0.05},
                "dates": days, "geographic_window": WINDOW, "window_kind": "fixed geographic download window, not an administrative boundary",
                "download_parameters": parameters, "images": images,
                "geometry_provenance": {"edition": "2025", "source_id": SOURCE_GEOMETRY,
                                        "soi_archive_sha256": boundaries["sources"]["archive"]["sha256"],
                                        "original_district_shp_sha256": boundaries["sources"]["district_components"][0]["sha256"],
                                        "working_district_shp_sha256": boundaries["files"]["districts.shp"]["sha256"],
                                        "working_manifest_sha256": soi.digest(args.boundaries / "manifest.json"),
                                        "identities": boundaries["district_records"], "current_lgd_reconciled": False,
                                        "nic_exact_matches": 12, "unresolved_matches": 19, "external_geometry_transmission": False},
                "method": "unweighted arithmetic mean/min/max of valid native CHIRPS cell centres strictly inside original local SOI polygons; boundary-centre pixels excluded; no area weighting, interpolation or centroid substitution",
                "temporal_semantics": "daily accumulated precipitation in mm/day, UTC observation windows; historical estimates, not gauges or prediction-time availability",
                "geometry_temporal_limit": "2025-edition geometry used; not claimed to represent each historical observation year's boundaries",
                "identity_limit": "SOI supplied DIST_LGD identifiers pending independent current-LGD verification; NIC exact-name matches are candidates only",
                "request_limits": {"per_request_deadline_ms": deadline_seconds * 1000, "retries": 0,
                                   "client_automatic_retries": 0, "max_attempts_per_operation": MAX_ATTEMPTS,
                                   "backoff_seconds": [2, 4], "wall_seconds": budget,
                                   "max_days": len(days), "max_download_bytes": MAX_BYTES},
                "processing_code": soi.fingerprint(Path(__file__)), "csv_fields": FIELDS,
                "raw_retrieval_log": soi.fingerprint(args.raw_directory / "retrieval.jsonl"),
                "request_attempt_log": soi.fingerprint(request_log),
                "validation": validation, "independent_checks": checks,
                "reuse": {"chirps": "Public domain", "soi_policy_url": soi.POLICY_URL,
                          "district_aggregate_publication": "permission not established; local only", "geometry_publication": False}}
    manifest = write_dataset(args.output, rows, manifest)
    validate_dataset(args.output, args.raw_directory, args.boundaries)
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.metadata_output, public_manifest(manifest))
    print(json.dumps({"validation": validation, "raw_bytes": sum(i["download"]["bytes"] for i in images),
                      "output": str(args.output), "metadata_output": str(args.metadata_output)}, indent=2), flush=True)


def record_failure(args, exc):
    """Retain completed dates on failure; never persist credential-bearing errors."""
    if not args.raw_directory.is_dir() or (args.raw_directory / "failure.json").exists():
        return
    log = args.raw_directory / "retrieval.jsonl"
    completed = [json.loads(line)["date"] for line in log.read_text().splitlines()
                 if json.loads(line).get("stage") == "validated"] if log.exists() else []
    pending = [day for day in requested_dates(args.mode, getattr(args, "month", 8)) if day not in completed]
    result = {"recorded_at": now(), "completed_dates": completed,
              "failed_date": pending[0] if pending else None, "unreviewed_dates": pending[1:],
              "phase": "daily retrieval/validation" if pending else "final dataset validation/publication",
              "error_type": type(exc).__name__,
              "error": str(exc) if isinstance(exc, ValueError) and "http" not in str(exc).lower()
                       else "Request or computation failed; raw retrieval provenance preserved; external error text withheld"}
    if isinstance(exc, BoundedRequestFailure):
        result.update(operation=exc.operation, category=exc.category, attempts=exc.attempts,
                      original_error_type=exc.error_type, http_status=exc.http_status)
    if isinstance(exc, verification.VerificationDeadlineExceeded):
        result.update(category="total_runtime_limit", error=str(exc))
    write_json(args.raw_directory / "failure.json", result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "month"])
    parser.add_argument("--month", type=int, choices=range(1, 13), default=8, help="Single 2025 month; August already complete")
    parser.add_argument("--ee-deadline-seconds", type=int, default=DEFAULT_EE_DEADLINE_SECONDS,
                        help="EE request deadline, 1–60 seconds; recovery uses 60. Three attempts with 2/4s backoff; client retries disabled")
    parser.add_argument("--boundaries", type=Path, default=BOUNDARIES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-directory", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--reuse-smoke", type=Path)
    parser.add_argument("--reuse-raw", type=Path)
    parser.add_argument("--reuse-partial-raw", type=Path, help="Read-only validated daily cache from an interrupted month")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps(validate_dataset(args.output, args.raw_directory, args.boundaries), indent=2))
        return
    if not args.mode or not args.metadata_output:
        parser.error("Extraction requires authorized --mode and new --metadata-output")
    if args.mode == "month" and args.month == 8:
        parser.error("August is immutable and complete; use --validate-only, not re-extraction")
    require(type(args.ee_deadline_seconds) is int and 1 <= args.ee_deadline_seconds <= 60,
            "EE deadline must be 1–60 seconds")
    import ee
    import requests
    raw_was_present = args.raw_directory.exists()
    with requests.Session() as session:
        try:
            extract(args, ee, session)
        except (Exception, verification.VerificationDeadlineExceeded) as exc:
            if not raw_was_present:
                record_failure(args, exc)
            raise


if __name__ == "__main__":
    main()
