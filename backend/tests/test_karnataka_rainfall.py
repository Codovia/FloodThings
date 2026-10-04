"""Synthetic controlled fixtures ONLY in disposable test directories; sockets blocked."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import box

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/extract_karnataka_rainfall.py"
spec = importlib.util.spec_from_file_location("karnataka_rainfall", SCRIPT)
rain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rain)
PARAMETERS = rain.download_parameters({"crs": "EPSG:4326", "transform": rain.GRID})


def image_info():
    return {"id": rain.SOURCE + "/20250801", "version": 1,
            "bands": [{"id": "precipitation", "data_type": {"precision": "float"},
                       "dimensions": [7200, 2000], "crs": "EPSG:4326", "crs_transform": rain.GRID}],
            "properties": {"system:time_start": 1754006400000, "system:time_end": 1754092800000}}


def fixture_districts():
    return [{"identity": {"state_lgd_code_as_supplied_by_soi": "29",
                          "district_lgd_code_as_supplied_by_soi": code,
                          "district_name_original": name, "nic_exact_name": None},
             "geometry": box(73.5+i*.05, 18.95, 73.55+i*.05, 19)}
            for i, (code, name) in enumerate([("569", "Test A"), ("761", "Test B")])]


def fixture_raster(path, alter=None, nodata=None):
    values = np.full((160, 110), rain.NODATA, dtype="float32")
    valid = np.zeros_like(values)
    values[0, :2], valid[0, :2] = [0, 5], 1
    if alter:
        alter(values, valid)
    with rasterio.open(path, "w", driver="GTiff", width=110, height=160, count=2,
                       dtype="float32", crs="EPSG:4326", nodata=nodata, transform=Affine(*PARAMETERS["crs_transform"])) as stream:
        stream.write(values, 1)
        stream.write(valid, 2)


def snapshot(root):
    return {str(p): (p.read_bytes(), rain.soi.digest(p), p.stat().st_mtime_ns)
            for p in Path(root).rglob("*") if p.is_file()}


def observations():
    districts = fixture_districts()
    masks, centres = rain.district_masks(districts, "EPSG:4326", PARAMETERS)
    values = np.zeros((160, 110), dtype="float32")
    values[0, 1] = 5
    image = rain.image_record(image_info(), "2025-08-01")
    image["download"] = {"retrieved_at": "2026-10-04T00:00:00+00:00"}
    rows = rain.summarize(districts, masks, values, np.ones_like(values, dtype=bool), image, rain.soi.VERSION)
    return districts, masks, centres, values, rows


def test_scope_and_original_grid_preserved_no_region_geometry_sent():
    assert len(rain.requested_dates("smoke")) == 1
    assert len(rain.requested_dates("month")) == 31
    with pytest.raises(ValueError, match="authorized August"):
        rain.requested_dates("backfill")
    assert PARAMETERS["dimensions"] == [110, 160]
    assert PARAMETERS["crs_transform"] == [.05, 0, 73.5, 0, -.05, 19]
    assert set(PARAMETERS) == {"crs", "crs_transform", "dimensions", "format", "bands", "filePerBand"}
    image = MagicMock()
    rain.export_image(image)
    image.select.assert_called_once_with("precipitation")
    image.select.return_value.mask.assert_called_once()
    image.clip.assert_not_called()
    assert "ee.Geometry" not in SCRIPT.read_text()


@pytest.mark.parametrize("transform", [[.1, 0, -180, 0, -.1, 50], [.05, 0, -179.99, 0, -.05, 50]])
def test_resolution_or_alignment_changes_fail_closed(transform):
    with pytest.raises(ValueError, match="native grid changed"):
        rain.download_parameters({"crs": "EPSG:4326", "transform": transform})


@pytest.mark.parametrize("change", [
    lambda i: i.update(id=rain.SOURCE + "/20250802"),
    lambda i: i["bands"][0]["data_type"].update(precision="double"),
    lambda i: i["properties"].update({"system:time_start": 1}),
    lambda i: i["properties"].update({"system:time_end": 1}),
])
def test_original_image_identity_precision_and_dates_required(change):
    info = image_info()
    change(info)
    with pytest.raises(ValueError):
        rain.image_record(info, "2025-08-01")


def test_integral_json_float_asset_version_is_preserved_losslessly():
    info = image_info()
    info["version"] = 1757796890900650.0
    record = rain.image_record(info, "2025-08-01")
    assert record["image_asset_version"] == 1757796890900650
    assert record["source_asset_version_original"] == info["version"]
    assert record["source_asset_version_json_type"] == "float"


@pytest.mark.parametrize("version", [None, 1.5, float("nan"), float(2**53+2), True])
def test_missing_or_inexact_versions_are_never_guessed(version):
    info = image_info()
    info["version"] = version
    with pytest.raises(ValueError, match="inexact source asset version"):
        rain.image_record(info, "2025-08-01")


def test_centres_are_local_nonoverlapping_and_boundary_points_excluded():
    districts, masks, _, _, _ = observations()
    assert [int(m.sum()) for m in masks] == [1, 1]
    districts[0]["geometry"] = box(73.5, 18.95, 73.525, 19)
    masks, _ = rain.district_masks(districts, "EPSG:4326", PARAMETERS)
    assert masks[0].sum() == 0
    districts[0]["geometry"] = box(73.4, 18.95, 73.55, 19)
    with pytest.raises(ValueError, match="fails to cover"):
        rain.district_masks(districts, "EPSG:4326", PARAMETERS)


def test_duplicate_cell_ownership_rejected():
    districts = fixture_districts()
    districts[1]["geometry"] = districts[0]["geometry"]
    with pytest.raises(ValueError, match="multiple districts"):
        rain.district_masks(districts, "EPSG:4326", PARAMETERS)


def test_masked_pixels_excluded_while_genuine_zero_remains_valid():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "source.tif"
        fixture_raster(path)
        before = snapshot(directory)
        values, valid, meta = rain.read_raster(path, PARAMETERS)
        assert values[0, 0] == 0 and valid[0, 0]
        assert values[1, 0] == rain.NODATA and not valid[1, 0]
        assert meta["valid_window_pixels"] == 2
        assert snapshot(directory) == before


def test_infinite_geotiff_nodata_header_preserved_as_json_safe_metadata():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "source.tif"
        fixture_raster(path, nodata=-float("inf"))
        before = snapshot(directory)
        values, valid, metadata = rain.read_raster(path, PARAMETERS)
        assert metadata["geotiff_nodata"] == "-Infinity"
        assert valid[0, 0] and values[0, 0] == 0
        json.dumps(metadata, allow_nan=False)
        assert snapshot(directory) == before


@pytest.mark.parametrize("alter", [
    lambda v, m: v.__setitem__((0, 0), -1),
    lambda v, m: v.__setitem__((0, 0), np.nan),
    lambda v, m: v.__setitem__((0, 0), np.inf),
    lambda v, m: m.__setitem__((0, 0), .5),
    lambda v, m: v.__setitem__((1, 1), 0),
])
def test_invalid_rainfall_masks_and_nodata_are_rejected(alter):
    with TemporaryDirectory() as directory:
        path = Path(directory) / "source.tif"
        fixture_raster(path, alter)
        with pytest.raises(ValueError):
            rain.read_raster(path, PARAMETERS)


def test_local_statistics_independent_calculation_and_null_observations():
    districts, masks, centres, values, rows = observations()
    assert [r["mean_mm_per_day"] for r in rows] == [0, 5]
    independent = rain.independent_checks(districts, centres, values, np.ones_like(values, dtype=bool), rows)
    assert all(r["matches_vector_calculation"] for r in independent)
    image = rain.image_record(image_info(), "2025-08-01")
    image["download"] = {"retrieved_at": "2026-10-04T00:00:00+00:00"}
    rows = rain.summarize(districts, masks, values, np.zeros_like(values, dtype=bool), image, rain.soi.VERSION)
    assert all(r["mean_mm_per_day"] is None and r["status"] == "no_valid_pixels" for r in rows)
    result = rain.validate_rows(rows, [d["identity"] for d in districts], ["2025-08-01"])
    assert result["valid_records"] == 0 and len(result["missing_observations"]) == 2


@pytest.mark.parametrize("change", [
    lambda r: r.append(deepcopy(r[0])),
    lambda r: r.pop(),
    lambda r: r[0].update(units="mm/hour"),
    lambda r: r[0].update(nic_exact_name="Guessed alias"),
    lambda r: r[0].update(geometry_edition="2005"),
    lambda r: r[0].update(mean_mm_per_day=-1),
    lambda r: r[0].update(source_time_end_ms=1),
    lambda r: r[0].update(valid_fraction=.5),
])
def test_validation_rejects_incomplete_keys_aliases_units_values_or_dates(change):
    districts, _, _, _, rows = observations()
    change(rows)
    with pytest.raises(ValueError):
        rain.validate_rows(rows, [d["identity"] for d in districts], ["2025-08-01"])


def test_download_failures_withhold_signed_urls():
    session = MagicMock()
    session.get.side_effect = RuntimeError("https://earthengine.googleapis.com/download?token=fixture-secret")
    with TemporaryDirectory() as directory:
        with pytest.raises(RuntimeError) as result:
            rain.download(session, "https://earthengine.googleapis.com/download?token=fixture-secret", Path(directory)/"rain.tif")
        assert "fixture-secret" not in str(result.value)
        assert "signed URL withheld" in str(result.value)


def test_completed_versions_and_ancestors_are_not_overwritten():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "completed"
        path.mkdir()
        (path / "manifest.json").write_text("{}")
        before = snapshot(directory)
        for candidate in [path, path / "child"]:
            with pytest.raises(ValueError):
                rain.write_dataset(candidate, [], {})
        assert snapshot(directory) == before


def test_full_fixture_extraction_recalculates_read_only_and_keeps_tables_local(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        boundary_dir = root / "boundary"
        boundary_dir.mkdir()
        (boundary_dir / "manifest.json").write_text("controlled fixture")
        districts = fixture_districts()
        boundary = {"version": rain.soi.VERSION, "district_records": [d["identity"] for d in districts],
                    "sources": {"archive": {"sha256": "0"*64}, "district_components": [{"sha256": "1"*64}]},
                    "files": {"districts.shp": {"sha256": "2"*64}}}
        monkeypatch.setattr(rain, "load_boundaries", lambda _: (districts, "EPSG:4326", boundary))
        monkeypatch.setattr(rain.verification, "probe_access", lambda *_: {"initialization": "controlled fixture"})
        def fixture_download(session, url, path):
            fixture_raster(path)
            return {"retrieved_at": "2026-10-04T00:00:00+00:00", "sha256": rain.soi.digest(path), "bytes": path.stat().st_size}
        monkeypatch.setattr(rain, "download", fixture_download)
        ee = MagicMock()
        ee.Image.return_value.getInfo.return_value = image_info()
        args = SimpleNamespace(mode="smoke", boundaries=boundary_dir, output=root/"local", raw_directory=root/"raw",
                               metadata_output=root/"metadata.json", reuse_smoke=None, reuse_raw=None)
        rain.extract(args, ee, MagicMock())
        before = snapshot(root)
        assert rain.validate_dataset(args.output, args.raw_directory, boundary_dir)["valid_records"] == 2
        assert snapshot(root) == before
        before = snapshot(root)
        cached = rain.cached_images(args.raw_directory)
        assert set(cached) == {"2025-08-01"}
        assert cached["2025-08-01"]["download"]["sha256"] == rain.soi.digest(args.raw_directory / "20250801.tif")
        assert snapshot(root) == before
        published = json.loads(args.metadata_output.read_text())
        assert not any("scalar_mean_mm_per_day" in c for c in published["independent_checks"])
        assert published["reuse"]["district_aggregate_publication"].endswith("local only")
        assert published["geometry_provenance"]["external_geometry_transmission"] is False
        with pytest.raises(ValueError, match="never overwrite"):
            rain.extract(args, ee, MagicMock())
        assert snapshot(root) == before
