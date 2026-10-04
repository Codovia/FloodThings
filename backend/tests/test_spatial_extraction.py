"""Georeferencing/quality tests use tiny controlled rasters only in disposable directories."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import shape

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/extract_udupi_spatial.py"
spec = importlib.util.spec_from_file_location("spatial_extraction", SCRIPT)
spatial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spatial)


def controlled_raster(path, invalid=None, crs="EPSG:32643", shift=0):
    affine = Affine(250, 0, 475000 + shift, 0, -250, 1495000)
    values = np.full((5, 2, 2), spatial.NODATA, dtype="float32")
    values[:, 0, 0] = [1, 0, 2, 1, 1]
    if invalid is not None:
        values[invalid[0], 0, 0] = invalid[1]
    with rasterio.open(path, "w", driver="GTiff", height=2, width=2, count=5, dtype="float32", crs=crs, transform=affine) as dst:
        dst.write(values)
    parameters = {"crs_transform": [250, 0, 475000, 0, -250, 1495000], "dimensions": [2, 2]}
    # A controlled boundary cuts the true first cell in half but retains its centre.
    corners = [(475000,1495000),(475200,1495000),(475200,1494500),(475000,1494500),(475000,1495000)]
    ring = [spatial.TO_WGS84.transform(*p) for p in corners]
    boundary = {"type": "Feature", "properties": {"shapeID": spatial.history.BOUNDARY_SHAPE_ID},
                "geometry": {"type": "Polygon", "coordinates": [ring]}}
    return parameters, boundary


def test_exact_cell_edges_district_clipping_and_coordinate_order():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "controlled.tif"
        params, boundary = controlled_raster(path)
        geojson, metadata = spatial.raster_features(path, params, boundary, 2728, 1)
        feature = geojson["features"][0]
        assert feature["properties"]["grid_col"] == 1900
        assert feature["properties"]["grid_row"] == -5980
        assert feature["properties"]["clear_views"] == 2
        polygon = shape(feature["geometry"])
        assert polygon.difference(shape(boundary["geometry"])).area < 1e-15
        lon, lat = polygon.exterior.coords[0]
        assert 74 < lon < 76 and 13 < lat < 14
        assert metadata["qualified_pixels"] == 1 and metadata["crs"] == "EPSG:32643"
        assert metadata["unavailable_sentinel"] == -9999


@pytest.mark.parametrize("invalid", [(0,0),(1,1),(2,0),(3,0),(4,0),(0,-9999),(2,float("nan"))])
def test_missing_masks_permanent_water_or_no_clear_view_are_rejected(invalid):
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "controlled.tif"
        params, boundary = controlled_raster(path, invalid=invalid)
        with pytest.raises(ValueError, match="criteria|masks|Non-finite"):
            spatial.raster_features(path, params, boundary, 2728, 1)


@pytest.mark.parametrize("crs,shift,error", [("EPSG:4326",0,"CRS"),("EPSG:32643",125,"alignment")])
def test_projection_and_grid_mismatch_fail_instead_of_adjusting(crs, shift, error):
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "controlled.tif"
        params, boundary = controlled_raster(path, crs=crs, shift=shift)
        with pytest.raises(ValueError, match=error):
            spatial.raster_features(path, params, boundary, 2728, 1)


def test_count_mismatch_is_explicit_and_not_filled():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "controlled.tif"
        params, boundary = controlled_raster(path)
        with pytest.raises(ValueError, match="expected 33, exported 1"):
            spatial.raster_features(path, params, boundary, 2728, 33)


def test_boundary_overlap_cells_are_reported_and_original_raster_is_preserved():
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "controlled.tif"
        params, _ = controlled_raster(path)
        with rasterio.open(path, "r+") as src:
            data = src.read()
            data[:,0,1] = [1,0,2,1,1]
            src.write(data)
        before = path.read_bytes()
        ring = [spatial.TO_WGS84.transform(*p) for p in [(475000,1495000),(475300,1495000),(475300,1494500),(475000,1494500),(475000,1495000)]]
        boundary = {"type":"Feature", "properties":{}, "geometry":{"type":"Polygon","coordinates":[ring]}}
        geojson, metadata = spatial.raster_features(path,params,boundary,2728,1)
        assert len(geojson["features"]) == 1
        assert metadata["download_qualifying_pixels"] == 2
        assert metadata["excluded_boundary_overlap_cells"] == [(0,1)]
        assert path.read_bytes() == before


def test_download_dimensions_keep_verified_grid_and_budget():
    params, windows = spatial.download_parameters([[454750,1546250],[521750,1546250],[521750,1452500],[454750,1452500]])
    assert params["crs_transform"] == [250,0,454750,0,-250,1546250]
    assert params["dimensions"] == [268,375]
    assert len(windows) == 4
    assert params["bands"] == spatial.BANDS
    with pytest.raises(ValueError, match="pixel ceiling"):
        spatial.download_parameters([[0,0],[1000000,0],[1000000,1000000],[0,1000000]])


def test_bounded_download_deadlines_and_size_cap(monkeypatch):
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.headers = {}
    response.iter_content.return_value = [b"actual-test-fixture"]
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "download.tif"
        result = spatial.bounded_download(session, "https://earthengine.googleapis.com/test-fixture", path)
        assert result["bytes"] == 19
        assert session.get.call_args.kwargs["timeout"] == (5,10)
        assert session.get.call_args.kwargs["allow_redirects"] is False
        monkeypatch.setattr(spatial, "MAX_BYTES", 1)
        with pytest.raises(ValueError, match="ceiling"):
            spatial.bounded_download(session, "https://earthengine.googleapis.com/test-fixture", Path(temporary)/"overlimit.tif")
        with pytest.raises(ValueError, match="host"):
            spatial.bounded_download(session, "https://unrelated.example/test", Path(temporary)/"bad.tif")


def test_existing_version_refused_without_authenticated_import(monkeypatch,capsys):
    def forbidden(*args):
        raise AssertionError("No live queries permitted in isolated tests")
    monkeypatch.setattr(spatial.importlib,"import_module",forbidden)
    with TemporaryDirectory() as temporary:
        assert spatial.main(["--output",temporary]) == 2
        assert "Version already exists" in capsys.readouterr().out
        assert list(Path(temporary).iterdir()) == []


def test_spatial_validation_and_api_preserve_all_dataset_bytes_hashes_and_mtimes(monkeypatch,capsys):
    from app import historical as api
    monkeypatch.setattr(spatial,"EXPECTED",{2728:1,3551:1})
    monkeypatch.setattr(api,"EVENTS",{eid:(start,end,1) for eid,start,end in spatial.history.EVENTS})
    with TemporaryDirectory() as temporary:
        directory=Path(temporary)/"spatial"
        directory.mkdir()
        evidence=[]
        for eid,start,end in spatial.history.EVENTS:
            params,boundary=controlled_raster(directory/f"event_{eid}.tif")
            geojson,metadata=spatial.raster_features(directory/f"event_{eid}.tif",params,boundary,eid,1)
            spatial.write_json(directory/f"event_{eid}.geojson",geojson)
            evidence.append({"event_id":eid,"image_id":spatial.history.event_asset(eid,start,end),
                "start_date":start,"end_date_inclusive":end,"processing_scale_m":250,"qualified_pixel_count":1,
                "raster_file":f"event_{eid}.tif","geometry_file":f"event_{eid}.geojson","raster_metadata":metadata,
                "download":{"retrieved_at":"2026-10-03T00:00:00+00:00"}})
        spatial.write_json(directory/"udupi_boundary.geojson",boundary)
        spatial.write_json(directory/"manifest.json",{"version":spatial.VERSION,"project":"floodpulse",
            "source_id":spatial.verification.FLOOD_ID,"boundary_id":spatial.history.BOUNDARY_SHAPE_ID,
            "sources":{k:spatial.history.SOURCES[k] for k in (spatial.verification.FLOOD_ID,spatial.verification.BOUNDARY_ID)},
            "extent_semantics":"historical_event_window_maximum_not_daily_occurrence",
            "download_parameters":params,"events":evidence,
            "files":{p.name:{"sha256":spatial.history.checksum(p)} for p in directory.iterdir()}})
        spatial.history.seal_version(directory)
        def snapshot():
            return (directory.stat().st_mtime_ns,{p.name:(p.read_bytes(),spatial.history.checksum(p),p.stat().st_mtime_ns) for p in directory.iterdir()})
        before=snapshot()
        assert spatial.validate_version(directory)=={2728:1,3551:1}
        assert spatial.main(["--validate-only","--output",str(directory)])==0
        catalogue,geometries=api.HistoricalStore(directory).load()
        assert len(catalogue["events"])==2 and len(geometries[2728]["features"])==1
        with pytest.raises(FileExistsError,match="completed dataset"):
            spatial.bounded_download(object(),"https://earthengine.googleapis.com/unused",directory/"new.tif")
        capsys.readouterr()
        assert snapshot()==before
