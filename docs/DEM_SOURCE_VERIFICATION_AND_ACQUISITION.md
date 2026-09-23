# DEM Source Verification and Acquisition Report (Phase 3.4 Terrain Foundation)

**Project:** FloodPulse (Karnataka Flood Prediction Platform)  
**Status:** VERIFIED & CONTROLLED SAMPLE ACQUIRED  
**Date:** September 2026  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPEC.md`
- `docs/CONSTRAINTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_CONTRACT.md`
- `docs/DATA_SOURCE_INVENTORY.md`
- `docs/FINAL_SOURCE_SELECTION.md`
- `docs/GIS_POSTGIS_INGESTION_DESIGN.md`

---

## 1. Executive Summary & Objective

The Machine Learning readiness audit identified terrain features (elevation, slope, aspect, relief ratio) as an essential component for rainfall-runoff, flow accumulation, and inundation susceptibility modeling across Karnataka's 31 districts.

The objective of this phase was strictly to:
1. Empirically investigate and compare viable authoritative Digital Elevation Model (DEM) sources.
2. Select the optimal source grounded in technical merit, licensing, and reproducibility.
3. Acquire and empirically verify a real controlled sample tile covering Karnataka terrain.
4. Verify 100% spatial coverage over Karnataka and surrounding transboundary buffers.
5. Formulate an efficient storage architecture respecting local system constraints.
6. Guarantee absolute non-interference with ongoing ERA5 extraction and existing hydrological GIS records.

---

## 2. DEM Candidates Comparative Evaluation

Four candidates were empirically investigated:

| Evaluation Dimension | 1. Copernicus DEM GLO-30 Public (Selected) | 2. NASA SRTM (SRTMGL1 v3.0) | 3. ISRO NRSC CartoDEM | 4. JAXA ALOS AW3D30 |
|---|---|---|---|---|
| **Authoritative Provider** | European Space Agency (ESA) / Airbus Defence & Space / DLR | NASA Jet Propulsion Laboratory (JPL) / USGS | National Remote Sensing Centre (NRSC), ISRO | Japan Aerospace Exploration Agency (JAXA) |
| **Official Name** | COP-DEM_GLO-30-DGED (GLO-30 Public) | SRTM 1 Arc-Second Global (SRTMGL1) | CartoDEM Version-3 R1 | ALOS World 3D - 30m (AW3D30) |
| **Mission / Acquisition Date** | 2011–2015 (TanDEM-X radar constellation); 2021 release | February 2000 (Space Shuttle STS-99); 2015 v3 release | 2005–2019 (Cartosat-1 optical stereo) | 2006–2011 (ALOS PRISM optical stereo) |
| **Spatial Resolution** | 1 arc-second (~30m at equator) | 1 arc-second (~30m at equator) | 1 arc-second (~30m at equator) | 1 arc-second (~30m at equator) |
| **Horizontal CRS** | EPSG:4326 (WGS 84 geographic 2D) | EPSG:4326 (WGS 84 geographic 2D) | WGS 84 geographic / UTM | EPSG:4326 (WGS 84 geographic 2D) |
| **Vertical Datum** | EGM2008 geoid (EPSG:3855) | EGM96 geoid (EPSG:5773) | WGS 84 Ellipsoid / EGM96 | EGM96 geoid (EPSG:5773) |
| **Vertical Units** | Metres (`metre`, float32) | Metres (`metre`, int16) | Metres (`metre`, float32) | Metres (`metre`, int16) |
| **Model Type** | Digital Surface Model (DSM) | Digital Surface Model (DSM, C-band) | Digital Surface Model (DSM, Optical) | Digital Surface Model (DSM, Optical) |
| **Relative Vertical Accuracy** | **< 2 metres** (LE90 < 4m globally) | ~10–16 metres | ~4–8 metres | ~5 metres |
| **Void / Water Quality** | Hydrologically corrected; water bodies flattened; void-free | Voids in steep terrain (Western Ghats filled with auxiliary data in v3) | Cloud/shadow voids in heavy monsoon areas | Cloud/shadow artifacts in high relief |
| **Official Access URL** | `https://registry.opendata.aws/copernicus-dem/`<br>`https://copernicus-dem-30m.s3.amazonaws.com/` | `https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/`<br>`https://opentopography.org` | `https://bhuvan-app3.nrsc.gov.in/data/download/index.php` | `https://www.eorc.jaxa.jp/ALOS/en/aw3d30/` |
| **Access Method** | Open HTTP GET & AWS S3 CLI (`--no-sign-request`) | HTTPS download via Earthdata Login or OpenTopography API | Web portal tile download via interactive browser session | Web portal / FTP download after registration |
| **Authentication Requirement** | **NONE** (completely public bucket) | Mandatory NASA Earthdata Login / OpenTopography API Key (HTTP 401 unauthenticated) | Mandatory ISRO Bhuvan registration login & captcha | Mandatory JAXA user registration & approval |
| **Automated Pipeline Viability** | **EXCELLENT** (direct curl/rasterio/COG streaming) | BLOCKED without personal API keys | SEVERELY BLOCKED (no open programmatic REST/S3 API) | BLOCKED without interactive account |
| **Rate Limits / Quotas** | Standard AWS S3 public bandwidth | Rate limited per account / OpenTopography daily quota | **10 tiles per day per account** | Standard FTP/HTTP limits |
| **Packaging Format** | Cloud-Optimized GeoTIFF (COG), internal tiling 1024x1024, DEFLATE | Zip archive with `.hgt` or raw GeoTIFF | GeoTIFF within tar/zip | GeoTIFF within tar.gz |
| **License** | Free open access under Copernicus WorldDEM-30 terms with attribution | Public domain (US Government work) | Open data for Indian registered users | Free for non-commercial / commercial with attribution |
| **Karnataka Coverage** | **100%** (all 30 state tiles, 39 bounding box tiles verified) | 100% | 100% | 100% |

---

## 3. Decision Rationale: Why Copernicus DEM GLO-30 Was Selected

Based strictly on empirical evaluation of live endpoints and technical documentation:

1. **Superior Vertical Accuracy (<2m vs ~10-16m):**  
   Copernicus DEM was acquired between 2011 and 2015 using dual-satellite single-pass radar interferometry (TanDEM-X and TerraSAR-X), achieving an absolute vertical accuracy under 4m and relative accuracy under 2m. This is significantly more accurate than NASA SRTM (flown in 2000, >26 years ago, with ~10m vertical error) and ALOS AW3D30 (~5m).

2. **Zero-Friction, Unauthenticated Access for Reproducibility:**  
   Unlike NASA Earthdata (requires Earthdata Login), OpenTopography (returned `HTTP 401 Unauthorized`), and ISRO Bhuvan (requires interactive login, captcha, and has a 10-tile/day rate limit), Copernicus DEM GLO-30 is hosted as an **Open Data on AWS** public dataset (`copernicus-dem-30m`). It requires **zero API tokens**, **zero credentials**, and can be streamed or downloaded via standard HTTP/S3 commands.

3. **Cloud-Optimized GeoTIFF (COG) Architecture:**  
   Copernicus DEM tiles are natively formatted as COGs with 1024x1024 internal tiling, DEFLATE compression (Predictor=3), and embedded pyramid overviews ([2, 4, 8]). This allows libraries like `rasterio` and GDAL to perform partial HTTP byte-range window reads without downloading entire multi-gigabyte rasters.

4. **Contemporary Topography (2011–2015 vs 2000):**  
   SRTM reflects terrain as it existed in February 2000. Major civil works, mining, highway embankments, and reservoir impoundments created in Karnataka over the last quarter-century are absent in SRTM but reflected in Copernicus DEM.

---

## 4. Controlled Sample Acquisition & Verification

A controlled sample tile was downloaded and verified:

### Acquired Files
- **Raster Tile:** `data/raw/gis/dem/Copernicus_DSM_COG_10_N12_00_E076_00_DEM.tif`
  - **Size:** 39,759,475 bytes (~38 MB)
  - **SHA-256 Checksum:** `906c8faa9341c5426aa4394c82fab0ffd4e34485992f6d8293d6a1c61b5066f7`
- **Metadata XML:** `data/raw/gis/dem/Copernicus_DSM_10_N12_00_E076_00.xml`
  - **Size:** 44,710 bytes (~44 KB)
  - **SHA-256 Checksum:** `2c0379bf155e60ee4c7b9612188c80082e75e73ab9917876dff92c905479c287`

### Raster Properties (via Rasterio 1.5.1)
- **Format:** GTiff / Cloud-Optimized GeoTIFF (tiled=True, blocksize=1024x1024, compress=deflate)
- **Dimensions:** 3,600 columns $\times$ 3,600 rows (12,960,000 pixels)
- **Bands:** 1 (Float32)
- **Horizontal CRS:** EPSG:4326 (WGS 84 2D geographic)
- **Pixel Spacing:** $0.0002777778^\circ \times 0.0002777778^\circ = 1.0\text{ arc-second} \approx 30.87\text{ m}$
- **Bounding Box:**
  - West: $76.0000^\circ\text{E}$
  - South: $12.0000^\circ\text{N}$
  - East: $77.0000^\circ\text{E}$
  - North: $13.0000^\circ\text{N}$
- **Nodata Value:** None (land tile is 100% valid; 12,960,000 / 12,960,000 pixels valid)
- **Overviews:** 3 levels present with reduction factors $[2, 4, 8]$

### Real Terrain Statistical Validation
- **Minimum Elevation:** $626.72\text{ m}$ (Cauvery River exit near Mandya/Ramanagara border)
- **Maximum Elevation:** $1,332.03\text{ m}$ (hills on Hassan/Kodagu borders)
- **Mean Elevation:** $788.33\text{ m}$
- **Median Elevation:** $790.22\text{ m}$
- **Standard Deviation:** $83.19\text{ m}$
- **Validation Match:** The calculated min ($626.72\text{ m}$) and max ($1332.03\text{ m}$) match the official ISO XML metadata fields `<gco:Real>626.716186523</gco:Real>` and `<gco:Real>1332.02746582</gco:Real>` with floating-point precision.
- **Topographic Realism:** This tile covers the Southern Deccan / Mysore plateau, containing the Cauvery river corridor (KRS reservoir, Srirangapatna, Mandya), Mysuru city, and the Chamundi hill complex (~1060m). The values accurately reflect verified geographic reality.

---

## 5. Karnataka Coverage & Boundary Buffer Verification

Using the authoritative PostGIS geometry for Karnataka (`states.geometry`, KSR-SAC):

- **Karnataka State Bounding Extent:**
  - Longitude: $74.0855^\circ\text{E}$ to $78.5878^\circ\text{E}$
  - Latitude: $11.5950^\circ\text{N}$ to $18.4776^\circ\text{N}$

- **Tile Grid Analysis:**
  - 1x1 degree tiles intersecting Karnataka state polygon: **30 tiles**
  - Full rectangular bounding box covering Karnataka + border buffers: **39 tiles** (tiles `N11` to `N18`, `E074` to `E078`; note: `N11_E074` is open Arabian Sea)
  - Tile availability in AWS S3 bucket `tileList.txt`: **39 / 39 (100.0% available, 0 missing)**

### Complete List of Required Karnataka Tiles
```text
N11: E075, E076, E077, E078
N12: E074, E075, E076, E077, E078
N13: E074, E075, E076, E077, E078
N14: E074, E075, E076, E077, E078
N15: E074, E075, E076, E077, E078
N16: E074, E075, E076, E077, E078
N17: E074, E075, E076, E077, E078
N18: E074, E075, E076, E077, E078
```

- **Transboundary Buffer Assurance:**  
  Because all 1x1 degree tiles are retained, boundary catchments extending into Maharashtra, Goa, Kerala, Tamil Nadu, Andhra Pradesh, and Telangana are completely covered without edge-clipping.

---

## 6. CRS and Vertical Semantics

1. **Horizontal CRS:** EPSG:4326 (WGS 84 geographic 2D, coordinates in decimal degrees).
2. **Vertical Units:** Metres above the geoid (`metre`), represented as single-precision floating point (`float32`).
3. **Vertical Datum:** EGM2008 geoid (EPSG:3855 / OGP Datum 1027).
4. **Digital Surface Model (DSM) Semantics:**
   - Copernicus DEM GLO-30 measures the reflective radar surface, including forest canopy in the Western Ghats and urban building envelopes in major cities.
   - For regional flood susceptibility and macro-catchment routing, DSM macro-slopes and elevations are highly consistent with bare-earth models.
   - Micro-topographic depression filling algorithms should be applied when deriving hydrological flow direction vectors to bridge canopy artifacts.
5. **Project Target CRS & Transformations:**
   - PostGIS storage: EPSG:4326.
   - Planar slope/aspect calculation: Must project locally to UTM Zone 43N (EPSG:32643) or apply spherical trigonometric slope algorithms ($\Delta x = \Delta\lambda \cos\phi \cdot R$).

---

## 7. Storage Architecture Recommendation

| Storage Option | Technical Characteristics | Recommendation |
|---|---|---|
| **A. PostGIS Raster (`raster` type)** | Stores tiles as binary in PostgreSQL tables. | **NOT RECOMMENDED:** Adds 2–3 GB blob overhead to Postgres, bloats DB backups, impairs vacuuming, and offers poor performance compared to GDAL COG streaming. |
| **B. Raw Compressed Zip Only** | Stores zipped archives; unzips on demand. | **NOT RECOMMENDED:** High CPU decompression penalty on every zonal statistics run. |
| **C. External Cloud-Optimized GeoTIFFs (COG) with Metadata in `terrain_datasets`** | Raw GeoTIFFs stored on filesystem under `data/raw/gis/dem/`; virtual mosaic (`.vrt`) links them; metadata tracked in existing `terrain_datasets` table. | **STRONGLY RECOMMENDED:** Aligns with existing project architecture (`terrain.py`), zero Postgres bloat, allows GDAL/Rasterio fast windowed streaming. |

---

## 8. Provenance Record

```yaml
Source: Copernicus Digital Elevation Model (Copernicus DEM)
Provider: European Space Agency (ESA) / Airbus Defence and Space / DLR / Sinergise
Dataset: COP-DEM_GLO-30-DGED (GLO-30 Public instance)
Version: 2021 Release
Official URL: https://registry.opendata.aws/copernicus-dem/
Access Method: Unauthenticated AWS S3 HTTPS & COG reads (s3://copernicus-dem-30m/)
Acquisition Date: 2026-09-24
File Checksum (N12_E076.tif): 906c8faa9341c5426aa4394c82fab0ffd4e34485992f6d8293d6a1c61b5066f7
XML Checksum (N12_E076.xml): 2c0379bf155e60ee4c7b9612188c80082e75e73ab9917876dff92c905479c287
CRS: EPSG:4326 (WGS 84 horizontal)
Resolution: 1 arc-second (~30 metres)
Coverage: Global landmass (Karnataka 100% covered across 30 state tiles, 39 bounding box tiles)
Vertical Units: Metres above sea level (metre)
Vertical Datum: EGM2008 geoid (EPSG:3855)
DSM/DTM: Digital Surface Model (DSM)
Format: Cloud-Optimized GeoTIFF (COG), DEFLATE, Predictor=3, internal tile 1024x1024
License: Free open access under Copernicus WorldDEM-30 terms with attribution
Known Limitations: Surface model reflects tree canopy in dense Western Ghats; not bare-earth DTM
Validation Status: VERIFIED
```

---

## 9. Test Verification & Isolation Audit

### Automated Test Suite
Created and executed `backend/tests/test_dem_acquisition.py`:
- `TestDemSampleIntegrity`: File existence and exact SHA-256 matches (3/3 passed)
- `TestDemRasterStructure`: GTiff driver, COG tiling, EPSG:4326 CRS, 1 arc-sec resolution, bounds (3/3 passed)
- `TestDemTerrainSemantics`: 100% valid pixels, min/max/mean elevation plausibility (1/1 passed)
- `TestSpatialIntersectionWithKarnataka`: State boundary and district intersections (2/2 passed)
- `TestSystemIsolation`: PostGIS hydrological records and ERA5 directory intact (2/2 passed)
**Total: 11 / 11 tests passed.**

### Isolation Confirmation
- `git status --porcelain data/raw/era5_historical/`: Output empty (zero files touched).
- PostGIS hydrological counts: 25 river basins, 116 sub-basins, 15,371 rivers, 54 district-riverbasin pairs, 264 district-subbasin pairs preserved without alteration.
