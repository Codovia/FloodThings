"""Read-only, local GIS research layers. Runtime never queries Earth Engine or OSM."""
import hashlib
import json
import math
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

DATASET = Path(__file__).resolve().parents[2] / "data/processed/udupi_drainage_gis_v1"
VERSION = "udupi_drainage_gis_v1"
DEM = "COPERNICUS/DEM/GLO30_2024_1"
LAND = "ESA/WorldCover/v200"
NOTICE = "Drainage Research Layers: surface elevation, derived slope, 2021 land cover and mapped infrastructure. Missing data and unmapped drains are unknown. These layers do not establish drainage risk or live waterlogging."
FILES = {"place_query.json", "study_area.geojson", "dem_source.tif", "landcover_source.tif",
         "drains_query.json", "mapped_drains.geojson", "elevation.tif", "slope.tif", "land_cover.tif",
         "elevation.png", "slope.png", "land_cover.png"}


class DrainageUnavailable(Exception):
    pass


def require(condition, message):
    if not condition:
        raise DrainageUnavailable(message)


class DrainageStore:
    def __init__(self, directory=DATASET):
        self.directory = Path(directory)

    def load(self):
        try:
            require((self.directory/"manifest.json").stat().st_size <= 1024*1024, "GIS manifest exceeds bound")
            manifest = json.loads((self.directory/"manifest.json").read_text())
            require(manifest["version"] == VERSION and manifest["project"] == "floodpulse", "GIS dataset identity mismatch")
            require(set(manifest["sources"]) == {DEM, LAND, "OpenStreetMap"}, "GIS source inventory mismatch")
            require(manifest["sources"][LAND]["license"] == "CC BY 4.0" and manifest["sources"]["OpenStreetMap"]["license"] == "ODbL 1.0" and "liability_notice" in manifest["sources"][DEM], "GIS licences unavailable")
            require(set(manifest["files"]) == FILES, "GIS file inventory mismatch")
            content = {}
            for name in FILES:
                path = self.directory/name
                require(path.stat().st_size <= 4*1024*1024, "GIS file exceeds bound")
                raw = path.read_bytes()
                require(hashlib.sha256(raw).hexdigest() == manifest["files"][name]["sha256"] and len(raw) == manifest["files"][name]["bytes"], f"GIS checksum mismatch: {name}")
                content[name] = raw
            study = json.loads(content["study_area.geojson"])
            require(study["type"] == "Feature" and study["geometry"]["type"] == "Polygon" and study["properties"] == manifest["study"], "GIS study area unavailable")
            props = study["properties"]
            require(props["kind"] == "study_window" and props["official_municipal_boundary"] is False and props["width_m"] == 3000 and props["definition_crs"] == "EPSG:32643" and props["anchor_osm_node_id"] == 245620117, "Study window definition mismatch")
            west, south, east, north = props["bounds_wgs84"]
            require(all(math.isfinite(v) for v in (west, south, east, north)) and 74.6 < west < east < 74.9 and 13.2 < south < north < 13.5, "Study bounds outside Udupi")
            require(set(manifest["layers"]) == {"elevation", "slope", "land_cover"}, "GIS layer inventory mismatch")
            for key, item in manifest["layers"].items():
                require(item["source_id"] == (LAND if key == "land_cover" else DEM) and item["resolution_m"] == (10 if key == "land_cover" else 30) and item["crs"] == "EPSG:32643" and item["nodata"] == -9999, "GIS layer metadata mismatch")
                require(item["raster_file"] == f"{key}.tif" and item["preview_file"] == f"{key}.png" and item["preview_crs"] == "EPSG:3857", "GIS map alignment metadata missing")
                require(item["status"] in ("available", "partial", "unavailable") and item["valid_pixels"] + item["missing_pixels"] == item["total_pixels"] and 0 <= item["valid_pixels"] <= item["total_pixels"], "GIS availability metadata inconsistent")
                require((item["status"] == "unavailable") == (item["valid_pixels"] == 0), "GIS unavailable state inconsistent")
                bounds = item["preview_bounds"]
                require(len(bounds) == 2 and all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in bounds) and south-.001 < bounds[0][0] < bounds[1][0] < north+.001 and west-.001 < bounds[0][1] < bounds[1][1] < east+.001, "GIS layer bounds inconsistent")
                require(content[item["preview_file"]].startswith(b"\x89PNG\r\n\x1a\n"), "GIS preview unavailable")
            drains = json.loads(content["mapped_drains.geojson"])
            osm = manifest["osm"]
            require(drains["type"] == "FeatureCollection" and len(drains["features"]) == osm["feature_count"], "Mapped drain count inconsistent")
            require(osm["status"] in ("available", "no_mapped_features") and (osm["status"] == "no_mapped_features") == (osm["feature_count"] == 0), "Mapped drain availability inconsistent")
            ids = set()
            for feature in drains["features"]:
                p = feature["properties"]
                require(feature["geometry"]["type"] in ("LineString", "MultiLineString") and p["osm_type"] == "way" and p["waterway"] in ("drain", "ditch") and p["osm_id"] not in ids and p["capacity_status"] == "unknown", "Invalid mapped infrastructure")
                ids.add(p["osm_id"])
            return {"status": "available", "dataset_version": VERSION, "notice": NOTICE, "study_area": study,
                    "sources": manifest["sources"], "layers": {key: {**item, "url": f"/api/drainage-research/layers/{key}.png",
                         "retrieved_at": manifest["landcover" if key == "land_cover" else "dem"]["download"]["retrieved_at"]} for key, item in manifest["layers"].items()},
                    "mapped_drains": drains, "osm": osm, "dem_quality": manifest["dem"]["quality"], "height_error_m": manifest["dem"]["height_error_m"],
                    "finished_at": manifest["finished_at"]}, content
        except DrainageUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise DrainageUnavailable("Local GIS dataset is missing or invalid") from exc


router = APIRouter(prefix="/api/drainage-research")


def get_store():
    return DrainageStore()


def unavailable(exc):
    return JSONResponse(status_code=503, content={"status": "unavailable", "message": str(exc), "notice": NOTICE})


@router.get("")
def catalog(store: DrainageStore = Depends(get_store)):
    try:
        return store.load()[0]
    except DrainageUnavailable as exc:
        return unavailable(exc)


@router.get("/layers/{layer}.png")
def preview(layer: str, store: DrainageStore = Depends(get_store)):
    if layer not in ("elevation", "slope", "land_cover"):
        return JSONResponse(status_code=404, content={"status": "unavailable", "message": "Unknown research layer"})
    try:
        _, content = store.load()
        return Response(content=content[f"{layer}.png"], media_type="image/png", headers={"Cache-Control": "no-cache"})
    except DrainageUnavailable as exc:
        return unavailable(exc)
