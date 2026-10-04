#!/usr/bin/env python3
"""Bounded GIS research extraction; no flood extraction, routing, scores or labels."""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import warnings

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.errors import NotGeoreferencedWarning
from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_udupi_history as history
import extract_udupi_spatial as spatial
import verify_earth_engine as verification

ROOT = Path(__file__).resolve().parents[1]
VERSION = "udupi_drainage_gis_v1"
DEM = "COPERNICUS/DEM/GLO30_2024_1"
LAND = "ESA/WorldCover/v200"
OSM = "OpenStreetMap"
CRS = "EPSG:32643"
NODATA = -9999
SIZE = 3000
MAX_BYTES = 4 * 1024 * 1024
OVERPASS = "https://overpass-api.de/api/interpreter"
PLACE_ID = 245620117
DEM_BANDS = ["DEM", "EDM", "FLM", "HEM", "WBM"]
TO_UTM = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
TO_GEO = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
COPERNICUS_NOTICE = "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"
COPERNICUS_LIABILITY = "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30"
SOURCES = {
    DEM: {"url": "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1",
          "license": "Copernicus WorldDEM-30 free licence; attribution and liability notice required",
          "license_url": "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
          "attribution": COPERNICUS_NOTICE, "liability_notice": COPERNICUS_LIABILITY,
          "native_resolution_m": 30, "units": "metres above EGM2008 (EPSG:3855)",
          "acquisition_period": ["2010-12-01", "2020-11-13"], "release": "2024_1",
          "limitation": "Digital surface model includes buildings and vegetation; not a surveyed bare-earth drainage model."},
    LAND: {"url": "https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200",
           "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
           "attribution": "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium",
           "citation": "Zanaga et al. (2022), ESA WorldCover 10 m 2021 v200, doi:10.5281/zenodo.7254221",
           "native_resolution_m": 10, "units": "categorical land-cover class code", "period": ["2021-01-01", "2021-12-31"],
           "limitation": "2021 classification, not current land cover; local classification accuracy unverified."},
    OSM: {"url": "https://www.openstreetmap.org/copyright", "license": "ODbL 1.0",
          "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
          "attribution": "© OpenStreetMap contributors", "native_resolution_m": None,
          "units": "mapped line geometry; derived clipped lengths in metres",
          "limitation": "Volunteer mapping is incomplete. Unmapped infrastructure, capacity and condition remain unknown. Clipped OSM data retain ODbL."},
}
CLASSES = {10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"),
           30: ("Grassland", "#ffff4c"), 40: ("Cropland", "#f096ff"),
           50: ("Built-up", "#fa0000"), 60: ("Bare / sparse vegetation", "#b4b4b4"),
           70: ("Snow and ice", "#f0f0f0"), 80: ("Permanent water", "#0064c8"),
           90: ("Herbaceous wetland", "#0096a0"), 95: ("Mangroves", "#00cf75"),
           100: ("Moss and lichen", "#fae6a0")}
SLOPE_METHOD = "Horn 3x3 finite differences on the 30 m UTM DSM; dx=(z3+2*z6+z9-z1-2*z4-z7)/(8*30), dy=(z7+2*z8+z9-z1-2*z2-z3)/(8*30); degrees(atan(hypot(dx,dy))). All nine pixels must be valid; no interpolation of missing data. One-cell source padding supplies neighbours outside the study window."
PLACE_QUERY = '[out:json][timeout:10][maxsize:1048576];(node["place"~"city|town"]["name"="Udupi"](13.27,74.67,13.41,74.81);relation["boundary"="administrative"]["name"="Udupi"](13.27,74.67,13.41,74.81););out meta;'


def write_json(path, value):
    spatial.write_json(path, value)


def overpass(session, query):
    """One bounded request, no retries; any server remark means incomplete evidence."""
    with session.get(OVERPASS, params={"data": query}, stream=True, timeout=(5, 15), allow_redirects=False) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            history.require(len(raw) <= 1024 * 1024, "Overpass response exceeds 1 MiB")
    payload = json.loads(raw)
    history.require("remark" not in payload, "Incomplete Overpass query: " + str(payload.get("remark")))
    history.require(isinstance(payload.get("elements"), list), "Invalid Overpass result")
    return {"endpoint": OVERPASS, "query": query, "retrieved_at": verification.now(), "response": payload}


def study_area(discovery):
    nodes = [e for e in discovery["response"]["elements"] if e["type"] == "node" and e["id"] == PLACE_ID]
    history.require(len(nodes) == 1 and nodes[0]["tags"].get("name") == "Udupi" and nodes[0]["tags"].get("place") == "city", "Verified Udupi city anchor unavailable")
    node = nodes[0]
    history.require(74.67 < node["lon"] < 74.81 and 13.27 < node["lat"] < 13.41, "Udupi anchor outside discovery window")
    x, y = TO_UTM.transform(node["lon"], node["lat"])
    x, y = round(x / 30) * 30, round(y / 30) * 30
    bounds = [x - SIZE // 2, y - SIZE // 2, x + SIZE // 2, y + SIZE // 2]
    # Densified projected edges retain the defined UTM rectangle in geographic coordinates.
    corners = [(bounds[0], bounds[1]), (bounds[2], bounds[1]), (bounds[2], bounds[3]), (bounds[0], bounds[3]), (bounds[0], bounds[1])]
    ring = [TO_GEO.transform(a[0] + (b[0]-a[0])*i/16, a[1] + (b[1]-a[1])*i/16)
            for a, b in zip(corners, corners[1:]) for i in range(16)]
    polygon = Polygon(ring)
    # Reuse the protected real district geometry only as a containment check, never as an urban boundary.
    district_path = ROOT / "data/processed/udupi_flood_spatial_v1/udupi_boundary.geojson"
    district = json.loads(district_path.read_text())
    history.require(district["properties"]["shapeID"] == history.BOUNDARY_SHAPE_ID and shape(district["geometry"]).covers(polygon), "Study window not contained by verified Udupi district")
    properties = {"kind": "study_window", "official_municipal_boundary": False, "width_m": SIZE,
                  "definition_crs": CRS, "projected_bounds": bounds, "bounds_wgs84": list(polygon.bounds),
                  "anchor_osm_node_id": PLACE_ID, "anchor_lon_lat": [node["lon"], node["lat"]],
                  "anchor_version": node["version"], "anchor_modified_at": node["timestamp"],
                  "retrieved_at": discovery["retrieved_at"],
                  "boundary_diagnostic": "Small 3 km study window, centre snapped to 30 m UTM grid. Bounded OSM discovery returned a city point and district relation, not a verified municipal polygon. This window is not an official urban boundary.",
                  "district_containment_source": verification.BOUNDARY_ID,
                  "district_shape_id": history.BOUNDARY_SHAPE_ID,
                  "district_geometry_sha256": history.checksum(district_path)}
    return {"type": "Feature", "properties": properties, "geometry": mapping(polygon)}


def grid(study, scale, padding=0):
    left, bottom, right, top = study["properties"]["projected_bounds"]
    return {"crs": CRS, "crs_transform": [scale, 0, left-padding*scale, 0, -scale, top+padding*scale],
            "dimensions": [int((right-left)/scale)+2*padding, int((top-bottom)/scale)+2*padding],
            "format": "GEO_TIFF", "filePerBand": False}


def horn_slope(padded):
    windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3))
    valid = np.all(np.isfinite(windows) & (windows != NODATA), axis=(-1, -2))
    z = windows
    dx = (z[..., 0, 2]+2*z[..., 1, 2]+z[..., 2, 2]-z[..., 0, 0]-2*z[..., 1, 0]-z[..., 2, 0])/240
    dy = (z[..., 2, 0]+2*z[..., 2, 1]+z[..., 2, 2]-z[..., 0, 0]-2*z[..., 0, 1]-z[..., 0, 2])/240
    return np.where(valid, np.degrees(np.arctan(np.hypot(dx, dy))), NODATA).astype("float32")


def write_raster(path, array, parameters, description):
    history.require_not_completed(path.parent)
    history.require(not path.exists(), "Refusing to replace raster")
    with rasterio.open(path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1,
                       dtype="float32", crs=CRS, transform=Affine(*parameters["crs_transform"]), nodata=NODATA,
                       compress="deflate") as dst:
        dst.write(array.astype("float32"), 1)
        dst.set_band_description(1, description)


def read_raw(path, parameters, bands):
    with rasterio.open(path) as src:
        history.require(src.crs.to_epsg() == 32643 and src.transform == Affine(*parameters["crs_transform"]), "Source raster CRS/grid mismatch")
        history.require([src.width, src.height] == parameters["dimensions"] and src.count == bands, "Source raster dimensions/bands mismatch")
        return src.read()


def derived_arrays(directory, study):
    raw = read_raw(directory / "dem_source.tif", grid(study, 30, 1), 5)
    dem = raw[0].copy()
    # Source DEM mask is retained as sentinel; EDM/FLM voids and missing quality evidence stay unknown.
    valid = np.isfinite(dem) & (dem != NODATA) & (raw[1] > 0) & (raw[2] > 0)
    dem[~valid] = NODATA
    lc = read_raw(directory / "landcover_source.tif", grid(study, 10), 1)[0].copy()
    lc[(lc == 0) | ~np.isfinite(lc)] = NODATA  # Undefined/missing land-cover codes are unknown, not a class.
    history.require(np.all((lc == NODATA) | np.isin(lc, list(CLASSES))), "Unknown WorldCover class code")
    return {"elevation": dem[1:-1, 1:-1], "slope": horn_slope(dem), "land_cover": lc}


def stats(array):
    valid = np.isfinite(array) & (array != NODATA)
    n = int(valid.sum())
    return {"status": "available" if n == array.size else ("partial" if n else "unavailable"),
            "valid_pixels": n, "total_pixels": array.size, "missing_pixels": int(array.size)-n,
            "min": float(array[valid].min()) if n else None, "max": float(array[valid].max()) if n else None}


def preview_data(path, layer):
    """Warp to Web Mercator before Leaflet imageOverlay: georeferencing is not a corner approximation."""
    with rasterio.open(path) as src:
        affine, width, height = calculate_default_transform(src.crs, "EPSG:3857", src.width, src.height, *src.bounds)
        data = np.full((height, width), NODATA, dtype="float32")
        reproject(src.read(1), data, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=affine, dst_crs="EPSG:3857", src_nodata=NODATA, dst_nodata=NODATA,
                  resampling=Resampling.nearest)
    valid = data != NODATA
    rgba = np.zeros((4, height, width), dtype="uint8")
    if layer == "land_cover":
        legend = [{"value": k, "label": CLASSES[k][0], "color": CLASSES[k][1]} for k in CLASSES if np.any(data == k)]
        for item in legend:
            rgb = [int(item["color"][i:i+2], 16) for i in (1, 3, 5)]
            rgba[:3, data == item["value"]] = np.array(rgb)[:, None]
    else:
        summary = stats(data)
        low, high = summary["min"], summary["max"]
        normal = np.zeros(data.shape) if low is None else np.clip((data-low)/max(high-low, 1e-9), 0, 1)
        start, end = ((225, 240, 235), (34, 93, 85)) if layer == "elevation" else ((243, 238, 221), (115, 85, 149))
        for band in range(3):
            rgba[band] = np.round(start[band] + normal*(end[band]-start[band])).astype("uint8")
        legend = {"min": low, "max": high, "colors": ["#e1f0eb", "#225d55"] if layer == "elevation" else ["#f3eedd", "#735595"]}
    rgba[3] = valid.astype("uint8")*255
    merc_to_geo = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, south = merc_to_geo.transform(affine.c, affine.f + affine.e*height)
    east, north = merc_to_geo.transform(affine.c + affine.a*width, affine.f)
    return rgba, {"preview_bounds": [[south, west], [north, east]], "preview_crs": "EPSG:3857",
                  "preview_transform": list(affine)[:6], "preview_dimensions": [width, height],
                  "preview_resampling": "nearest neighbour, nodata transparent", "legend": legend}


def write_preview(path, rgba):
    history.require_not_completed(path.parent)
    history.require(not path.exists(), "Refusing to replace preview")
    # PNG georeferencing lives explicitly in the manifest; authoritative rasters are GeoTIFFs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", driver="PNG", width=rgba.shape[2], height=rgba.shape[1], count=4, dtype="uint8") as dst:
            dst.write(rgba)


def drain_query(study):
    west, south, east, north = study["properties"]["bounds_wgs84"]
    return f'[out:json][timeout:10][maxsize:1048576];way["waterway"~"^(drain|ditch)$"]({south:.9f},{west:.9f},{north:.9f},{east:.9f});out meta geom;'


def mapped_drains(result, study):
    polygon = shape(study["geometry"])
    features, seen = [], set()
    for element in result["response"]["elements"]:
        history.require(element["type"] == "way" and element["tags"].get("waterway") in ("drain", "ditch"), "Unexpected OSM feature type")
        history.require(element["id"] not in seen, "Duplicate OSM way")
        seen.add(element["id"])
        coords = [(p["lon"], p["lat"]) for p in element.get("geometry", [])]
        history.require(len(coords) >= 2 and all(math.isfinite(x) and math.isfinite(y) for x, y in coords), "OSM way geometry missing; coverage incomplete")
        clipped = LineString(coords).intersection(polygon)
        if clipped.is_empty:
            continue
        history.require(clipped.is_valid and clipped.geom_type in ("LineString", "MultiLineString"), "Invalid clipped OSM line")
        length = transform(TO_UTM.transform, clipped).length
        features.append({"type": "Feature", "geometry": mapping(clipped), "properties": {
            "osm_type": "way", "osm_id": element["id"], "osm_version": element["version"],
            "osm_modified_at": element["timestamp"], "waterway": element["tags"]["waterway"],
            "source_tags": element["tags"], "clipped_length_m": length,
            "retrieved_at": result["retrieved_at"], "capacity_status": "unknown"}})
    return {"type": "FeatureCollection", "features": features}, {
        "status": "available" if features else "no_mapped_features",
        "feature_count": len(features), "drain_count": sum(f["properties"]["waterway"] == "drain" for f in features),
        "ditch_count": sum(f["properties"]["waterway"] == "ditch" for f in features),
        "clipped_length_m": sum(f["properties"]["clipped_length_m"] for f in features),
        "query": result["query"], "endpoint": result["endpoint"], "retrieved_at": result["retrieved_at"],
        "osm_base_timestamp": result["response"]["osm3s"]["timestamp_osm_base"],
        "coverage_interpretation": "Mapped ways only; unmapped drains and infrastructure capacity remain unknown.",
        "geometry_crs": "OGC:CRS84 (longitude, latitude)", "geometry_file": "mapped_drains.geojson"}


def source_download(ee, session, staged, study, source):
    props = study["properties"]
    geometry = ee.Geometry(study["geometry"], proj="EPSG:4326", geodesic=False)
    collection = ee.ImageCollection(source).filterBounds(geometry)
    if source == DEM:
        w, s, e, n = props["bounds_wgs84"]
        indices = [f'N{lat:02d}_00_E{lon:03d}_00' for lat in range(math.floor(s), math.floor(n)+1) for lon in range(math.floor(w), math.floor(e)+1)]
        collection = collection.filter(ee.Filter.inList("system:index", indices))
        parameters, bands, name = grid(study, 30, 1), DEM_BANDS, "dem_source.tif"
    else:
        collection = collection.filterDate("2021-01-01", "2022-01-01")
        parameters, bands, name = grid(study, 10), ["Map"], "landcover_source.tif"
    count = collection.size().getInfo()
    history.require(0 < count <= 4, f"{source}: expected 1–4 relevant source images, received {count}")
    collection = collection.sort("system:index")
    first = ee.Image(collection.first()).select(bands)
    metadata = {"source_id": source, "image_ids": collection.aggregate_array("system:id").getInfo(),
                "native_projection": first.select(bands[0]).projection().getInfo(),
                "source_properties": first.toDictionary(["system:index", "system:time_start", "system:time_end", "tile_version", "system:version"]).getInfo(),
                "tile_selection": "Geometry filter and intersecting 1-degree DEM tile indices" if source == DEM else "Geometry and 2021 date filters",
                "processing_resampling": "nearest neighbour; source masks retained as sentinel", "download_parameters": {**parameters, "bands": bands}}
    # Include exactly one DSM neighbour cell for slope, still a small explicitly bounded download.
    left, bottom, right, top = props["projected_bounds"]
    padding = 30 if source == DEM else 0
    clip = ee.Geometry.Rectangle([left-padding, bottom-padding, right+padding, top+padding], CRS, False)
    product = (collection.mosaic().setDefaultProjection(first.select(bands[0]).projection()).select(bands)
               .toFloat().reproject(crs=CRS, crsTransform=parameters["crs_transform"]).clip(clip)
               .unmask(NODATA, sameFootprint=False))
    history.require(math.prod(parameters["dimensions"])*len(bands)*4 <= MAX_BYTES, "Source download exceeds pixel/byte budget")
    url = product.getDownloadURL(dict(metadata["download_parameters"]))
    metadata["download"] = spatial.bounded_download(session, url, staged / name)
    return metadata


def validate_version(directory):
    """Pure reads: reproduce slope, masks, map previews and OSM clipping without network."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    history.require(manifest["version"] == VERSION and manifest["project"] == "floodpulse" and manifest["sources"] == SOURCES, "GIS source/version identity mismatch")
    expected_files = {"place_query.json", "study_area.geojson", "dem_source.tif", "landcover_source.tif",
                      "drains_query.json", "mapped_drains.geojson"} | {f"{k}.{ext}" for k in ("elevation", "slope", "land_cover") for ext in ("tif", "png")}
    history.require(set(manifest["files"]) == expected_files, "GIS file inventory mismatch")
    for name, info in manifest["files"].items():
        history.require(Path(name).name == name and (directory/name).stat().st_size <= MAX_BYTES, "Unsafe GIS file")
        history.require(history.checksum(directory/name) == info["sha256"] and (directory/name).stat().st_size == info["bytes"], f"GIS checksum mismatch: {name}")
    discovery = json.loads((directory/"place_query.json").read_text())
    study = study_area(discovery)
    history.require(json.loads((directory/"study_area.geojson").read_text()) == json.loads(json.dumps(study)) and manifest["study"] == study["properties"], "Study geometry mismatch")
    arrays = derived_arrays(directory, study)
    for key, expected in arrays.items():
        item = manifest["layers"][key]
        scale = 10 if key == "land_cover" else 30
        history.require(item["source_id"] == (LAND if key == "land_cover" else DEM) and item["resolution_m"] == scale and item["crs"] == CRS and item["nodata"] == NODATA, "Layer identity/CRS/nodata mismatch")
        with rasterio.open(directory/item["raster_file"]) as src:
            history.require(src.nodata == NODATA and src.count == 1 and src.transform == Affine(*grid(study, scale)["crs_transform"]) and src.crs.to_epsg() == 32643 and np.array_equal(src.read(1), expected), "Derived raster/grid/mask mismatch")
        history.require(all(item[k] == v for k, v in stats(expected).items()), "Coverage statistics mismatch")
        if key == "land_cover":
            counts = {str(code): int((expected == code).sum()) for code in CLASSES if np.any(expected == code)}
            history.require(item["class_counts"] == counts, "Land-cover class counts mismatch")
        if key == "slope":
            history.require(item["method"] == SLOPE_METHOD and np.all((expected == NODATA) | ((expected >= 0) & (expected <= 90))), "Slope method/range mismatch")
        rgba, metadata = preview_data(directory/item["raster_file"], key)
        history.require(all(item[k] == v for k, v in metadata.items()), "Preview georeferencing mismatch")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(directory/item["preview_file"]) as png:
                history.require(np.array_equal(png.read(), rgba), "Preview pixels/transparent nodata mismatch")
    drains, details = mapped_drains(json.loads((directory/"drains_query.json").read_text()), study)
    history.require(json.loads((directory/"mapped_drains.geojson").read_text()) == json.loads(json.dumps(drains)) and manifest["osm"] == details, "OSM geometry/provenance mismatch")
    history.require(manifest["dem"]["source_id"] == DEM and manifest["landcover"]["source_id"] == LAND, "Source identity mismatch")
    for source_key, source_id, parameters, bands in (("dem", DEM, grid(study, 30, 1), DEM_BANDS), ("landcover", LAND, grid(study, 10), ["Map"])):
        source = manifest[source_key]
        history.require(source["download_parameters"] == {**parameters, "bands": bands}, "Source download parameters mismatch")
        history.require(source["native_projection"]["crs"] == "EPSG:4326" and source["download"]["retrieved_at"], "Source projection/timestamp missing")
        expected_id = f'{source_id}/{source["source_properties"]["system:index"]}'
        history.require(source["image_ids"] == [expected_id] and (source["source_properties"]["system:index"] == "2021" if source_id == LAND else source["source_properties"]["system:index"] == "N13_00_E074_00"), "Original source image identity mismatch")
    quality = read_raw(directory/"dem_source.tif", grid(study, 30, 1), 5)[:, 1:-1, 1:-1]
    quality_counts = {band: {str(float(v)): int((quality[index] == v).sum()) for v in np.unique(quality[index])} for index, band in enumerate(DEM_BANDS) if band in ("EDM", "FLM", "WBM")}
    history.require(manifest["dem"]["quality"] == quality_counts and manifest["dem"]["height_error_m"] == stats(quality[3]), "DEM quality metadata mismatch")
    return {"layers": {k: stats(v) for k, v in arrays.items()}, "mapped_drains": details}


def extract(ee, session, staged, discovery=None):
    started = verification.now()
    with verification.wall_limit(120):
        access = verification.probe_access(ee, "floodpulse")
        discovery = discovery or overpass(session, PLACE_QUERY)
        study = study_area(discovery)
        write_json(staged/"place_query.json", discovery)
        write_json(staged/"study_area.geojson", study)
        print(json.dumps({"stage": "dem", "at": verification.now()}), flush=True)
        dem = source_download(ee, session, staged, study, DEM)
        print(json.dumps({"stage": "landcover", "at": verification.now()}), flush=True)
        landcover = source_download(ee, session, staged, study, LAND)
        print(json.dumps({"stage": "mapped_drains", "at": verification.now()}), flush=True)
        drain_result = overpass(session, drain_query(study))
        drains, osm = mapped_drains(drain_result, study)
        write_json(staged/"drains_query.json", drain_result)
        write_json(staged/"mapped_drains.geojson", drains)
        arrays = derived_arrays(staged, study)
        layers = {}
        for key, array in arrays.items():
            scale = 10 if key == "land_cover" else 30
            units = "class code" if key == "land_cover" else ("degrees" if key == "slope" else "m above EGM2008")
            write_raster(staged/f"{key}.tif", array, grid(study, scale), units)
            rgba, display = preview_data(staged/f"{key}.tif", key)
            write_preview(staged/f"{key}.png", rgba)
            layers[key] = {**stats(array), **display, "resolution_m": scale, "units": units, "crs": CRS, "nodata": NODATA,
                           "source_id": LAND if key == "land_cover" else DEM,
                           "raster_file": f"{key}.tif", "preview_file": f"{key}.png"}
            if key == "slope":
                layers[key]["method"] = SLOPE_METHOD
            if key == "land_cover":
                layers[key]["class_counts"] = {str(code): int((array == code).sum()) for code in CLASSES if np.any(array == code)}
        quality = read_raw(staged/"dem_source.tif", grid(study, 30, 1), 5)[:, 1:-1, 1:-1]
        dem["quality"] = {band: {str(float(v)): int((quality[index] == v).sum()) for v in np.unique(quality[index])} for index, band in enumerate(DEM_BANDS) if band in ("EDM", "FLM", "WBM")}
        dem["height_error_m"] = stats(quality[3])
        manifest = {"version": VERSION, "project": "floodpulse", "started_at": started, "finished_at": verification.now(),
                    "earth_engine_access": access, "study": study["properties"], "sources": SOURCES, "dem": dem,
                    "landcover": landcover, "osm": osm, "layers": layers,
                    "request_limits": {"ee_deadline_ms": 10000, "overpass_server_seconds": 10, "http_connect_read_seconds": [5, 15],
                                       "earth_engine_download_connect_read_seconds": [5, 10], "retries": 0, "wall_seconds": 120, "max_file_bytes": MAX_BYTES,
                                       "max_overpass_bytes": 1048576, "dem_cells_including_padding": 10404, "landcover_cells": 90000},
                    "limitations": ["Research layers only; not validated drainage risk, current flooding or waterlogging.",
                                    "DSM surface heights and slope cannot verify underground drainage or hydrological flow paths.",
                                    "Missing raster pixels and unmapped drains remain unknown; no missing values are filled.",
                                    "2021 land cover and composite DSM acquisition dates are not synchronous with present OSM mapping."],
                    "code_sha256": {Path(__file__).name: history.checksum(Path(__file__))}}
        manifest["files"] = {p.name: {"sha256": history.checksum(p), "bytes": p.stat().st_size} for p in staged.iterdir() if p.is_file()}
        write_json(staged/"manifest.json", manifest)
        return validate_version(staged)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=["floodpulse"], default="floodpulse")
    parser.add_argument("--output", type=Path, default=ROOT/"data/processed"/VERSION)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--place-discovery", type=Path, help="Reuse a retained genuine Overpass discovery response")
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            result = validate_version(args.output)
        else:
            history.require_new_output(args.output)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".udupi-gis-", dir=args.output.parent) as temporary:
                staged = Path(temporary)
                requests, ee = importlib.import_module("requests"), importlib.import_module("ee")
                discovery = json.loads(args.place_discovery.read_text()) if args.place_discovery else None
                with requests.Session() as session:
                    session.headers["User-Agent"] = "FloodPulse bounded drainage GIS research"
                    result = extract(ee, session, staged, discovery)
                args.output.mkdir()
                try:
                    for path in sorted(staged.iterdir(), key=lambda p: p.name == "manifest.json"):
                        os.rename(path, args.output/path.name)
                    history.seal_version(args.output)
                except BaseException:
                    shutil.rmtree(args.output)
                    raise
        print(json.dumps({"status": "verified", "output": str(args.output), **result}))
        return 0
    except (Exception, verification.VerificationDeadlineExceeded) as exc:
        # Do not disclose transient signed Earth Engine download URLs in transport failures.
        message = str(exc).split("https://earthengine.googleapis.com/")[0]
        print(json.dumps({"status": "failed_no_new_version", "error": {"type": type(exc).__name__, "message": message}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
