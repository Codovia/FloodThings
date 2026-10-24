"""Serve verified local historical evidence only; no Earth Engine calls or predictions."""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

DATASET = Path(__file__).resolve().parents[2] / "data/processed/udupi_flood_spatial_v1"
VERSION = "udupi_flood_spatial_v1"
BOUNDARY_ID = "76128533B4839184447445"
SOURCE_ID = "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1"
EVENTS = {2728: ("2005-09-14", "2005-09-30", 33), 3551: ("2009-09-25", "2009-10-12", 23)}
NOTICE = "Historical event-window maximum satellite observations. Not current flooding, predicted risk, flooded roads or evacuation advice. Does not establish flooding on every event date."
SOURCE = {"id": SOURCE_ID, "name": "Global Flood Database V1 — Cloud to Street / Dartmouth Flood Observatory",
          "url": "https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1",
          "citation": "Tellman et al. (2021), doi:10.1038/s41586-021-03695-w",
          "license": "CC BY-NC 4.0", "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
          "conditions": "Attribution and non-commercial use required"}


class HistoricalUnavailable(Exception):
    pass


def require(condition, message):
    if not condition:
        raise HistoricalUnavailable(message)


class HistoricalStore:
    def __init__(self, directory=DATASET):
        self.directory = Path(directory)

    def load(self):
        try:
            require((self.directory / "manifest.json").stat().st_size <= 1024 * 1024, "Manifest exceeds bound")
            manifest = json.loads((self.directory / "manifest.json").read_text())
            require(manifest["version"] == VERSION and manifest["source_id"] == SOURCE_ID and manifest["boundary_id"] == BOUNDARY_ID, "Dataset identity mismatch")
            require(manifest["extent_semantics"] == "historical_event_window_maximum_not_daily_occurrence", "Extent semantics mismatch")
            require(manifest["sources"][SOURCE_ID]["license"].startswith("CC BY-NC 4.0"), "Source licence mismatch")
            names = {"udupi_boundary.geojson", "event_2728.tif", "event_2728.geojson", "event_3551.tif", "event_3551.geojson"}
            require(set(manifest["files"]) == names, "Unexpected spatial inventory")
            content = {}
            for name in names:
                path = self.directory / name
                require(path.stat().st_size <= 4 * 1024 * 1024, "Spatial file exceeds bound")
                raw = path.read_bytes()
                require(hashlib.sha256(raw).hexdigest() == manifest["files"][name]["sha256"], "Spatial checksum mismatch")
                if name.endswith(".geojson"):
                    content[name] = json.loads(raw)
            boundary = content["udupi_boundary.geojson"]
            require(boundary["type"] == "Feature" and boundary["properties"]["shapeID"] == BOUNDARY_ID and boundary["geometry"]["type"] in ("Polygon", "MultiPolygon"), "Boundary unavailable")
            require(len(manifest["events"]) == 2 and {e["event_id"] for e in manifest["events"]} == set(EVENTS), "Event inventory mismatch")
            events, geometries = [], {}
            for event in manifest["events"]:
                eid = event["event_id"]
                start, end, count = EVENTS[eid]
                asset = f"{SOURCE_ID}/DFO_{eid}_From_{start.replace('-', '')}_to_{end.replace('-', '')}"
                require(event["image_id"] == asset and event["start_date"] == start and event["end_date_inclusive"] == end, "Event identity/dates mismatch")
                require(event["geometry_file"] == f"event_{eid}.geojson" and event["raster_file"] == f"event_{eid}.tif", "Event file mismatch")
                require(event["qualified_pixel_count"] == count and event["processing_scale_m"] == 250, "Event count/resolution mismatch")
                geometry = content[event["geometry_file"]]
                require(geometry["type"] == "FeatureCollection" and len(geometry["features"]) == count, "Geometry/count mismatch")
                seen = set()
                for feature in geometry["features"]:
                    props = feature["properties"]
                    key = (props["grid_row"], props["grid_col"])
                    require(key not in seen, "Duplicate raster cell")
                    seen.add(key)
                    require(feature["type"] == "Feature" and feature["geometry"]["type"] in ("Polygon", "MultiPolygon"), "Unsupported map geometry")
                    require(props["event_id"] == eid and props["flooded"] == 1 and props["jrc_perm_water"] == 0 and props["clear_views"] > 0 and props["observation_valid"] == 1, "Observation evidence invalid")
                events.append({"event_id": eid, "image_id": asset, "start_date": start, "end_date_inclusive": end,
                               "qualified_pixel_count": count, "processing_scale_m": 250,
                               "extent_semantics": manifest["extent_semantics"],
                               "retrieved_at": event["download"]["retrieved_at"],
                               "geometry_sha256": manifest["files"][event["geometry_file"]]["sha256"],
                               "geometry_url": f"/api/historical-floods/{eid}"})
                geometries[eid] = geometry
            return {"status": "available", "dataset_version": VERSION, "district": "Udupi", "notice": NOTICE,
                    "source": SOURCE, "boundary_source": manifest["sources"]["WM/geoLab/geoBoundaries/600/ADM2"],
                    "boundary": boundary, "events": events}, geometries
        except HistoricalUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HistoricalUnavailable("Historical spatial dataset is unavailable or invalid") from exc


def get_historical_store():
    return HistoricalStore()


def unavailable():
    return JSONResponse(status_code=503, content={"status": "unavailable", "source": SOURCE, "notice": NOTICE,
        "message": "Historical flood geometry is unavailable or failed validation. No flood-absence conclusion can be drawn."})


router = APIRouter(prefix="/api/historical-floods", tags=["historical flood evidence"])


@router.get("")
def historical_events(store: HistoricalStore = Depends(get_historical_store)):
    try:
        catalogue, _ = store.load()
        return catalogue
    except HistoricalUnavailable:
        return unavailable()


@router.get("/{event_id}")
def historical_event(event_id: int, store: HistoricalStore = Depends(get_historical_store)):
    if event_id not in EVENTS:
        return JSONResponse(status_code=404, content={"status": "unavailable", "message": "Event was not reviewed in this spatial dataset", "notice": NOTICE, "source": SOURCE})
    try:
        catalogue, geometries = store.load()
        return {"status": "available", "dataset_version": VERSION, "notice": NOTICE, "source": SOURCE,
                "event": next(e for e in catalogue["events"] if e["event_id"] == event_id),
                "floodwater": geometries[event_id]}
    except HistoricalUnavailable:
        return unavailable()
