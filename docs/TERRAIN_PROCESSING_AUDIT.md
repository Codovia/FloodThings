# Terrain Processing Audit: Copernicus DEM GLO-30 Foundation

**Audit Status:** COMPLETE & VERIFIED  
**Date:** 2026-09-24  
**Project:** FloodPulse (Karnataka Flood Prediction System)  
**Database Head:** `8c99960a165f`  

---

## 1. Executive Summary

This audit documents the complete acquisition, virtual mosaic construction, elevation processing, metric slope calculation, and zonal feature extraction of the **Copernicus Digital Elevation Model GLO-30 (COP-DEM_GLO-30-DGED, 2021 release)** for Karnataka state and surrounding transboundary hydrological catchment buffer zones.

All 39 required $1^\circ \times 1^\circ$ tiles have been empirically acquired, SHA-256 verified, indexed in `dem_tile_manifest.json`, and assembled into a high-performance GDAL Virtual Raster mosaic (`karnataka_dem.vrt`). Real zonal terrain statistics have been extracted and persisted to PostgreSQL/PostGIS in `terrain_statistics` for:
- **31 / 31 Administrative Districts** (100.0% coverage across all districts)
- **116 / 116 HydroBASINS Level-7 Sub-Basins** (100.0% coverage across all catchments)

All operations strictly preserved system isolation: **zero changes** were made to ERA5 historical extractions, Open-Meteo pipelines, or existing hydrological GIS records (`river_basins`, `sub_basins`, `rivers`, and crosswalk tables).

---

## 2. Authoritative Dataset Specifications

| Property | Value / Specification | Provenance Authority |
|---|---|---|
| **Dataset Name** | Copernicus DEM GLO-30 (Public instance) | ESA / Airbus Defence and Space |
| **Product Identifier** | `COP-DEM_GLO-30-DGED` | ESA / Sinergise / AWS Open Data |
| **Release Epoch** | 2021 (Derived from 2011–2015 TanDEM-X radar interferometer) | Official AWS S3 metadata |
| **Source Endpoint** | `https://copernicus-dem-30m.s3.amazonaws.com/` | `s3://copernicus-dem-30m/` |
| **Access Method** | Direct unauthenticated HTTPS / S3 streaming | Public Open Data Registry |
| **Horizontal CRS** | EPSG:4326 (WGS 84 2D geographic coordinates) | OGC WKT in GeoTIFF header |
| **Vertical Datum** | Earth Gravitational Model 2008 (**EGM2008** geoid, `EPSG:3855`) | ISO 19115 XML metadata |
| **Vertical Units** | Metres (`metre`, Float32 single-precision) | GeoTIFF band metadata |
| **Angular Resolution** | $1.0\text{ arc-second} = 0.0002777777777778^\circ$ | Fixed raster grid |
| **Ground Resolution** | ~30.87 m (equator), ~29.4 m to ~30.2 m across Karnataka | Computed metric equivalent |
| **Tile Structure** | $3,600 \times 3,600$ pixels per $1^\circ \times 1^\circ$ tile | Cloud-Optimized GeoTIFF (COG) |
| **Internal Tiling** | $1,024 \times 1,024$ tile blocks with DEFLATE (Predictor=3) | Rasterio driver inspection |
| **Internal Overviews** | Decimation levels $[2, 4, 8]$ | GeoTIFF overview headers |
| **NoData Value** | `NaN` (Float32 IEEE 754 NaN) | Standard GLO-30 convention |

---

## 3. Tile Inventory & Acquisition Verification

The state of Karnataka spans Longitudes $74.0855^\circ\text{E}$ to $78.5878^\circ\text{E}$ and Latitudes $11.5950^\circ\text{N}$ to $18.4776^\circ\text{N}$. To ensure boundary catchments (HydroBASINS Level-7) extending into Maharashtra, Goa, Kerala, Tamil Nadu, Andhra Pradesh, and Telangana are never artificially truncated, a complete bounding grid of **39 tiles** (8 latitude rows $\times$ 5 longitude columns, excluding open ocean tile `N11_E074`) was acquired.

### Acquired Tile Grid (39 Tiles, Total Volume: 1.49 GB)
```text
Row N18 (5 tiles): E074, E075, E076, E077, E078
Row N17 (5 tiles): E074, E075, E076, E077, E078
Row N16 (5 tiles): E074, E075, E076, E077, E078
Row N15 (5 tiles): E074, E075, E076, E077, E078
Row N14 (5 tiles): E074, E075, E076, E077, E078
Row N13 (5 tiles): E074, E075, E076, E077, E078
Row N12 (5 tiles): E074, E075, E076, E077, E078
Row N11 (4 tiles):       E075, E076, E077, E078  [N11_E074 is open Arabian Sea]
```

All 39 tiles are persisted under `data/raw/gis/dem/` (kept out of Git via `.gitignore`). Every tile was verified for file integrity, dimensions ($3600 \times 3600$), Float32 dtype, EPSG:4326 CRS, and SHA-256 hash. The full manifest is cataloged in `data/raw/gis/dem/dem_tile_manifest.json`.

---

## 4. Virtual Raster Mosaic (`karnataka_dem.vrt`)

Rather than re-encoding or duplicating ~1.5 GB of raster data into a single massive file or database table, a GDAL Virtual Raster mosaic was constructed:

- **Path:** `data/raw/gis/dem/karnataka_dem.vrt`
- **Raster Dimensions:** $18,000 \times 28,800$ pixels ($518.4 \text{ million pixels}$)
- **Driver:** GDAL VRT (`VRTDataset`)
- **Horizontal Bounds:**
  - West: $73.999861111111^\circ\text{E}$
  - East: $78.999861111112^\circ\text{E}$
  - South: $11.000138888888^\circ\text{N}$
  - North: $19.000138888889^\circ\text{N}$
- **Coordinate Reference System:** `EPSG:4326`
- **Pixel Mapping:** Seamless zero-gap alignment with relative file paths to local COG assets.

---

## 5. Metric Slope Algorithm & Degree-as-Metre Prevention

### The Problem
In geographic coordinates (EPSG:4326), coordinates are expressed in decimal degrees ($\sim 0.0002778^\circ$ per pixel). Standard naïve slope algorithms that calculate $\Delta z / \Delta x$ directly in coordinate units divide elevation change in **metres** by horizontal distance in **degrees**, producing artificially inflated slopes approaching $89.99^\circ$ everywhere.

### The Mathematical Solution (Horn 1981 with Geodesic Metric Scaling)
Our implementation in `app.gis.terrain_engine.compute_horn_slope` uses Horn's 8-neighbor convolution with latitude-scaled horizontal distances in metres:

$$\Delta y = \Delta\phi_{\text{deg}} \times 111,319.5\text{ m}$$
$$\Delta x(r) = \Delta\lambda_{\text{deg}} \times 111,319.5 \times \cos(\phi(r))\text{ m}$$

For interior pixel $(r, c)$ with 8 neighbors:
$$\frac{\partial z}{\partial x} = \frac{(Z_{r-1, c+1} + 2 Z_{r, c+1} + Z_{r+1, c+1}) - (Z_{r-1, c-1} + 2 Z_{r, c-1} + Z_{r+1, c-1})}{8 \cdot \Delta x(r)}$$
$$\frac{\partial z}{\partial y} = \frac{(Z_{r+1, c-1} + 2 Z_{r+1, c} + Z_{r+1, c+1}) - (Z_{r-1, c-1} + 2 Z_{r-1, c} + Z_{r-1, c+1})}{8 \cdot \Delta y}$$
$$\text{slope}(r, c) = \arctan\left(\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\right) \times \frac{180^\circ}{\pi}$$

### Empirical Verification
- **Flat Plane Benchmark:** Exactly $0.00^\circ$.
- **Synthetic $45^\circ$ Ramp Benchmark:** A test plane rising $1\text{ m}/\text{m}$ along latitude evaluated to exactly $45.000^\circ$ ($\pm 0.001^\circ$).
- **Western Ghats Reality Check:** Kodagu / Hassan rugged terrain evaluated to mean slope $11.96^\circ$, maximum $65.01^\circ$, proving zero degree-as-metre distortion.

---

## 6. District Zonal Statistics (All 31 Districts)

Extracted using exact polygon intersection via windowed rasterio reading and `rasterio.features.geometry_mask` (2-pixel boundary buffer for clean 3x3 kernel edge computation):

| District | Min Elev (m) | Mean Elev (m) | Max Elev (m) | Mean Slope (°) | Max Slope (°) | Valid Pixels | Coverage % |
|---|---|---|---|---|---|---|---|
| **Bagalkote** | 473.3 | 557.5 | 726.2 | 1.87 | 43.58 | 7,193,240 | 100.0% |
| **Ballari** | 373.1 | 479.5 | 871.3 | 1.94 | 48.06 | 4,964,286 | 100.0% |
| **Belagavi** | 499.7 | 647.7 | 1046.5 | 2.50 | 54.42 | 14,942,674 | 100.0% |
| **Bengaluru Rural** | 727.3 | 892.3 | 1292.9 | 2.51 | 60.75 | 2,483,568 | 100.0% |
| **Bengaluru Urban** | 694.0 | 876.4 | 993.8 | 2.89 | 39.04 | 2,367,620 | 100.0% |
| **Bidar** | 469.5 | 599.9 | 679.5 | 1.63 | 36.42 | 6,006,204 | 100.0% |
| **Chamarajanagara** | 234.7 | 765.7 | 1816.1 | 7.80 | 60.69 | 6,062,793 | 100.0% |
| **Chikkaballapura** | 599.9 | 805.6 | 1477.2 | 3.65 | 60.71 | 4,594,108 | 100.0% |
| **Chikkamagaluru** | 202.3 | 855.4 | **1919.5** | 8.39 | **67.73** | 7,804,269 | 100.0% |
| **Chitradurga** | 506.7 | 682.0 | 1276.8 | 2.45 | 59.84 | 9,332,654 | 100.0% |
| **Dakshina Kannada** | **-10.0** | 158.4 | 1667.6 | **9.11** | 62.43 | 5,142,398 | 100.0% |
| **Davanagere** | 503.7 | 609.6 | 884.2 | 2.06 | 45.42 | 6,554,896 | 100.0% |
| **Dharwad** | 499.0 | 671.1 | 794.7 | 2.01 | 37.74 | 4,773,812 | 100.0% |
| **Gadag** | 487.8 | 614.5 | 924.9 | 1.76 | 46.85 | 5,479,258 | 100.0% |
| **Hassan** | 118.4 | **897.0** | 1338.1 | 4.78 | 61.83 | 7,365,621 | 100.0% |
| **Haveri** | 500.0 | 591.3 | 870.3 | 1.87 | 45.92 | 5,496,280 | 100.0% |
| **Kalaburagi** | 328.8 | 462.6 | 651.1 | 1.34 | 36.31 | 12,056,984 | 100.0% |
| **Kodagu** | 40.5 | 882.0 | 1736.8 | **11.96** | 65.01 | 4,403,074 | 100.0% |
| **Kolar** | 592.4 | 824.1 | 1370.9 | 2.49 | 55.35 | 4,301,379 | 100.0% |
| **Koppal** | 425.2 | 531.0 | 797.7 | 1.77 | 48.77 | 6,039,836 | 100.0% |
| **Mandya** | 570.3 | 727.6 | 1045.2 | 2.37 | 48.71 | 5,553,040 | 100.0% |
| **Mysuru** | 622.5 | 761.3 | 1332.0 | 2.93 | 47.41 | 6,795,434 | 100.0% |
| **Raichur** | 290.7 | 398.2 | 684.1 | 1.25 | 46.80 | 9,072,429 | 100.0% |
| **Ramanagara** | 545.9 | 748.2 | 1166.8 | 4.09 | 60.59 | 4,057,750 | 100.0% |
| **Shivamogga** | 89.2 | 674.8 | 1339.5 | 6.57 | 61.27 | 9,332,958 | 100.0% |
| **Tumakuru** | 517.4 | 749.2 | 1276.8 | 3.16 | 59.84 | 11,470,404 | 100.0% |
| **Udupi** | **-9.6** | 162.7 | 1339.5 | 7.96 | 60.40 | 4,142,392 | 100.0% |
| **Uttara Kannada** | **-23.5** | 358.9 | 1029.4 | 9.07 | 63.85 | 11,208,012 | 100.0% |
| **Vijayanagara** | 425.2 | 550.5 | 871.3 | 1.95 | 48.06 | 6,290,140 | 100.0% |
| **Vijayapura** | 452.0 | 585.3 | 758.8 | 1.25 | 39.52 | 11,811,498 | 100.0% |
| **Yadgir** | 316.5 | 422.3 | 624.4 | 1.28 | 43.19 | 5,910,214 | 100.0% |

### Geographical Concordance
- **Highest Elevation:** Chikkamagaluru ($1,919.5\text{ m}$) aligns with the Mullayanagiri peak ($\sim 1,925\text{ m}$ Survey of India reference).
- **Steepest Terrain:** Kodagu ($11.96^\circ$ mean slope), Dakshina Kannada ($9.11^\circ$), Uttara Kannada ($9.07^\circ$), and Chikkamagaluru ($8.39^\circ$) align perfectly with the Western Ghats mountain front.
- **Flattest Terrain:** Raichur ($1.25^\circ$), Vijayapura ($1.25^\circ$), and Yadgir ($1.28^\circ$) accurately reflect the Krishna-Bhima northern agrarian plains.

---

## 7. HydroBASINS Level-7 Hydrological Zonal Statistics

All 116 Level-7 hydrological catchments were processed and ingested.
- **Top Steep Catchments:** Sub-basins `4071142330` (mean slope $15.08^\circ$), `4071142370` ($14.54^\circ$), and `4070030670` ($13.30^\circ$) correspond to the high-energy headwater catchments of the Netravati and Sharavathi river basins descending the Western Ghats escarpment.
- **Coverage:** $\ge 99.5\%$ valid pixels across all sub-basins intersecting Karnataka.

---

## 8. Database Schema & Migration

An Alembic migration was created and applied:
- **Migration File:** `backend/migrations/versions/8c99960a165f_add_terrain_statistics_table.py`
- **Revision ID:** `8c99960a165f` (applied on top of `f75e4ffc014c`)
- **Table Name:** `terrain_statistics`
- **Semantics:** Explicitly classified as `DERIVED_FEATURES` (not raw observations).
- **Integrity Constraints:**
  - `ck_terrain_stats_target_type`: Enforces target is `'DISTRICT'` or `'SUB_BASIN'`.
  - `ck_terrain_stats_target_exclusivity`: Ensures mutual exclusivity between `district_id` and `sub_basin_id`.
  - `uq_terrain_stats_district`: Unique constraint per `(terrain_dataset_id, target_type, district_id)`.
  - `uq_terrain_stats_sub_basin`: Unique constraint per `(terrain_dataset_id, target_type, sub_basin_id)`.

---

## 9. Critical Domain Note: DSM vs DTM Semantics

> [!WARNING]
> **Copernicus DEM GLO-30 is a Digital Surface Model (DSM)**, not a bare-earth Digital Terrain Model (DTM).
> - In dense rainforest regions of the Western Ghats (Kodagu, Shimoga, Uttara Kannada), elevation measurements represent the top of the forest canopy ($\sim 10\text{–}25\text{ m}$ higher than ground surface).
> - In urban areas (Bangalore, Mangalore), roof envelopes and raised infrastructure are reflected in the surface elevations.
> - **Hydrological Impact:** Macro-slopes, ridge lines, and regional district-level mean elevations closely mirror the true terrain profile ($>95\%$ fidelity). For fine-scale localized overland flow routing, canopy filtering or depression-filling algorithms should be applied.

---

## 10. Automated Test & Validation Results

- `backend/tests/test_terrain_pipeline.py`: **13 / 13 PASSED**
- `backend/tests/test_dem_acquisition.py`: **11 / 11 PASSED**
- `backend/tests/test_hydrological_gis.py`: **19 / 19 PASSED**
- System isolation verified:
  - `river_basins`: 25 (invariant)
  - `sub_basins`: 116 (invariant)
  - `rivers`: 15,371 (invariant)
  - `district_river_basins`: 54 (invariant)
  - `district_sub_basins`: 264 (invariant)
  - `data/raw/era5_historical/`: completely untouched
