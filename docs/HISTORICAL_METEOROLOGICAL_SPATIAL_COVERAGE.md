# Phase 3.7B — Gate 3 Spatial Coverage

## Objective

Determine the actual ERA5 0.25° grid cells covering the State of Karnataka and evaluate their spatial relationship to the authoritative KSR-SAC administrative boundaries (state and 31 districts) stored in PostGIS. Establish district-level intersection counts, center-point containment, boundary and coastal characteristics, and empirically verify data retrieval across representative spatial regimes.

This is a spatial validation task only. No production ingestion pipeline is created, no database records are modified, and no ML features or datasets are generated.

---

## ERA5 Grid Convention

Based on official ECMWF specifications and empirical Gate 1 / Gate 2 API responses:
- **Spacing:** Regular 0.25° latitude × 0.25° longitude grid (~27.8 km north-south, ~26.8 km east-west at 15°N latitude).
- **Coordinate Convention:** Grid points are centered at exact multiples of 0.25°:
  - Latitude: `..., 11.50°, 11.75°, 12.00°, 12.25°, ..., 18.25°, 18.50°, 18.75°`
  - Longitude: `..., 73.75°, 74.00°, 74.25°, 74.50°, ..., 78.50°, 78.75°, 79.00°`
- **Cell Representation:** Each grid coordinate $(lat_c, lon_c)$ represents the geometric center of a $0.25^\circ \times 0.25^\circ$ cell polygon defined in EPSG:4326 by:
  $$\text{Polygon}([lon_c - 0.125, lon_c + 0.125] \times [lat_c - 0.125, lat_c + 0.125])$$
- **Snapping Behavior:** When non-grid coordinates are passed to Open-Meteo with `models=era5`, the API deterministically snaps to the nearest 0.25° cell center.

---

## Grid Construction Method

1. **Bounding Box Extraction:**
   - Authoritative Karnataka state polygon geometry was queried from the `states` table in PostGIS (storage CRS EPSG:4326).
   - Authoritative Bounding Box:
     - Longitude: $[74.0855^\circ\text{E}, 78.5878^\circ\text{E}]$
     - Latitude: $[11.5950^\circ\text{N}, 18.4776^\circ\text{N}]$
2. **Grid Generation:**
   - A rectangular bounding grid encompassing Karnataka with a 0.25° safety margin was constructed:
     - Latitude: $11.25^\circ\text{N}$ to $18.75^\circ\text{N}$ (31 steps)
     - Longitude: $73.75^\circ\text{E}$ to $79.00^\circ\text{E}$ (22 steps)
   - Total generated bounding box grid cells: **682 cells**.
3. **Rigorous Spatial Intersections:**
   - Two distinct spatial criteria were evaluated for every cell:
     - **Cell Polygon Intersection:** `ST_Intersects(boundary.geometry, ST_MakeEnvelope(lon-0.125, lat-0.125, lon+0.125, lat+0.125, 4326))`
     - **Cell Center Containment:** `ST_Contains(boundary.geometry, ST_SetSRID(ST_Point(lon, lat), 4326))`
   - Boundary cells were explicitly identified as cells whose polygon intersects the boundary but is not completely contained within it (`ST_Intersects AND NOT ST_Within`).

---

## Karnataka State Intersection

| Metric | Count | Description |
| :--- | :--- | :--- |
| **Total Bounding Grid Cells** | 682 | Total candidate cells in $[11.25, 18.75] \times [73.75, 79.00]$ |
| **Grid Cells Intersecting Karnataka** | **324** | Cells whose $0.25^\circ \times 0.25^\circ$ polygon intersects Karnataka state polygon |
| **Grid Cell Centers Inside Karnataka** | **253** | Cells whose center point $(lat_c, lon_c)$ falls strictly inside Karnataka |
| **Grid Cells Completely Outside Karnataka**| 358 | Cells with zero spatial intersection with Karnataka |
| **State Boundary Cells** | 128 | Cells that intersect the Karnataka state border (`ST_Intersects AND NOT ST_Within`) |
| **Intersecting Cells Coordinate Extent** | — | Latitude: $[11.50^\circ\text{N}, 18.50^\circ\text{N}]$, Longitude: $[74.00^\circ\text{E}, 78.50^\circ\text{E}]$ |

---

## District Coverage

Spatial intersection and center containment were calculated for all 31 administrative districts in Karnataka:

| District | District Code | Intersecting Cells | Centers Inside | Boundary Cells | Zero Coverage? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bagalkote** | 524 | 20 | 9 | 20 | **NO** |
| **Ballari** | 528 | 16 | 5 | 16 | **NO** |
| **Bangalore Rural** | 526 | 12 | 3 | 12 | **NO** |
| **Bangalore Urban** | 525 | 8 | 4 | 8 | **NO** |
| **Belagavi** | 527 | 37 | 17 | 33 | **NO** |
| **Bidar** | 529 | 17 | 9 | 16 | **NO** |
| **Chamarajanagara** | 531 | 18 | 6 | 17 | **NO** |
| **Chikkaballapura** | 630 | 15 | 5 | 15 | **NO** |
| **Chikkamagaluru** | 532 | 20 | 10 | 19 | **NO** |
| **Chitradurga** | 533 | 23 | 11 | 19 | **NO** |
| **Dakshina Kannada** | 534 | 16 | 7 | 16 | **NO** |
| **Davanagere** | 535 | 17 | 6 | 17 | **NO** |
| **Dharwad** | 536 | 15 | 4 | 14 | **NO** |
| **Gadag** | 537 | 14 | 8 | 13 | **NO** |
| **Hassan** | 539 | 20 | 10 | 18 | **NO** |
| **Haveri** | 540 | 16 | 5 | 15 | **NO** |
| **Kalaburagi** | 538 | 29 | 15 | 26 | **NO** |
| **Kodagu** | 541 | 13 | 4 | 13 | **NO** |
| **Kolar** | 542 | 14 | 6 | 14 | **NO** |
| **Koppal** | 543 | 17 | 8 | 16 | **NO** |
| **Mandya** | 544 | 16 | 8 | 15 | **NO** |
| **Mysuru** | 545 | 20 | 8 | 20 | **NO** |
| **Raichur** | 546 | 21 | 12 | 18 | **NO** |
| **Ramanagara** | 631 | 14 | 4 | 14 | **NO** |
| **Shivamogga** | 547 | 24 | 12 | 22 | **NO** |
| **Tumakuru** | 548 | 29 | 12 | 26 | **NO** |
| **Udupi** | 549 | 14 | 5 | 14 | **NO** |
| **Uttara Kannada** | 550 | 26 | 13 | 23 | **NO** |
| **Vijayanagara** | 738 | 19 | 7 | 19 | **NO** |
| **Vijayapura** | 530 | 28 | 14 | 24 | **NO** |
| **Yadgir** | 635 | 18 | 6 | 17 | **NO** |

---

## Coverage Statistics

Across all 31 Karnataka administrative districts:

- **Intersecting Cells per District:**
  - Minimum: **8 cells** (Bangalore Urban)
  - Maximum: **37 cells** (Belagavi)
  - Median: **17.0 cells**
  - Mean: **18.9 cells**
- **Grid-Cell Centers Inside per District:**
  - Minimum: **3 centers** (Bangalore Rural)
  - Maximum: **17 centers** (Belagavi)
  - Median: **8.0 centers**
  - Mean: **8.2 centers**
- **Districts with Zero Intersecting Cells:** **0 (0%)**
- **Districts with Zero Cell Centers:** **0 (0%)**
- **Districts with Exactly 1 Intersecting Cell:** **0 (0%)**
- **Districts with Multiple Intersecting Cells:** **31 (100%)**

Every single district in Karnataka is represented by at least 8 intersecting cells and at least 3 interior grid centers.

---

## Boundary and Coastal Analysis

### 1. Intersecting Cells with Center Outside the State
- Exactly **71 grid cells** intersect the Karnataka state polygon but have their cell centers $(lat_c, lon_c)$ outside Karnataka.
- These 71 cells fall into two distinct geographic categories:
  1. **Terrestrial Interstate Border Cells:** Cells overlapping neighboring states (Maharashtra, Goa, Telangana, Andhra Pradesh, Tamil Nadu, Kerala).
  2. **Coastal / Marine Margin Cells:** Cells along the Arabian Sea coastline (Uttara Kannada, Udupi, Dakshina Kannada) where the western portion of the cell covers maritime waters while the eastern portion covers coastal land.

### 2. Boundary Representation Guidelines for Future Phases
- **Area-Weighted Zonal Aggregation:** When aggregating ERA5 variables to district boundaries, intersecting boundary cells must be weighted by their fractional intersection area ($A_{\text{cell} \cap \text{district}} / A_{\text{district}}$) rather than simple arithmetic averaging.
- **Centroid-Based Point Sampling:** If point sampling is used instead of polygon aggregation, sampling only grid centers strictly contained within the district (`centers_inside`) avoids interstate or marine boundary contamination.

---

## Empirical API Probes

Five representative spatial cells were probed using Open-Meteo `models=era5` for `1994-10-04` to `1994-10-05` (48 hourly timesteps):

| Spatial Regime | Location / Description | Requested (Lat, Lon) | Returned (Lat, Lon) | Elevation | HTTP Status | Precip Nulls | Temp Nulls | RH Nulls |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interior Karnataka** | Chitradurga / Davanagere | (14.25, 76.50) | (14.25, 76.50) | 647 m | `200` | 0 | 0 | 0 |
| **District Boundary** | Mandya / Mysuru Boundary | (12.50, 76.75) | (12.50, 76.75) | 730 m | `200` | 0 | 0 | 0 |
| **Coastal / Boundary** | Udupi Coast / Arabian Sea Margin | (13.25, 74.50) | (13.25, 74.75)* | 0 m | `200` | 0 | 0 | 0 |
| **Northern Karnataka** | Bidar / Aurad | (18.25, 77.25) | (18.25, 77.25) | 568 m | `200` | 0 | 0 | 0 |
| **Southern Karnataka** | Chamarajanagara / Gundlupete | (11.75, 76.75) | (11.75, 76.75) | 857 m | `200` | 0 | 0 | 0 |

*\*Note on Coastal Snapping:* Requesting coordinates `(13.25, 74.50)` (an offshore point in the Arabian Sea) resulted in Open-Meteo snapping to the nearest valid land/atmospheric cell at `(13.25, 74.75)` with elevation 0.0 m, returning 48 populated hourly records without missing values.

---

## Spatial Coverage Finding

### **Status: VERIFIED FOR NEXT VALIDATION GATE**

> [!IMPORTANT]
> **VERIFIED FOR NEXT VALIDATION GATE** indicates that the 0.25° ERA5 grid provides complete, dense spatial coverage across all 31 Karnataka administrative districts without any spatial gaps or unrepresented districts. It does **NOT** mean that production ingestion has been approved.

#### Supporting Findings:
1. **Zero Unrepresented Districts:** 100% of Karnataka's 31 districts possess multiple intersecting cells (range: 8 to 37; median: 17.0) and multiple interior centers (range: 3 to 17; median: 8.0).
2. **Dense Territorial Representation:** 324 intersecting cells cover the 191,791 km² state landmass, providing approximately one meteorological grid cell per ~590 km².
3. **Physical Elevation Consistency:** Probed grid cell elevations align accurately with known Karnataka physiography (from coastal sea level 0 m up to southern Deccan plateau 857 m).
4. **Valid Boundary Data:** Probes across interior, boundary, coastal, northern, and southern regimes all returned complete 48-hour records with zero null values.

---

## Limitations

1. **Spatial Aggregation Resolution:** While 0.25° (~28 km) provides multiple cells per district, small urban areas (e.g. Bangalore Urban) span only 8 cells. Micro-scale convective precipitation variations within an individual taluk or urban catchment cannot be resolved at 0.25° without supplementary high-resolution data.
2. **Marine Margin Snapping:** In coastal cells, offshore queries snap to the nearest terrestrial or coastal grid center. Future ingestion pipelines must explicitly specify terrestrial grid cell coordinates rather than arbitrary offshore points.
3. **Boundary Weighting Requirement:** Direct unweighted spatial averaging of intersecting cells could introduce boundary bleeding from neighboring states (e.g., Maharashtra rainfall leaking into northern Belagavi/Bidar).

---

## Phase 3.12C Resolution: Authoritative Grid vs. ERA5 Extraction-Eligible Grid

During Phase 3.12B production extraction, six coastal boundary cells were discovered where Open-Meteo ERA5 snaps requested offshore coordinates to neighboring land-side coordinates:
- `ERA5_1275_07475` (12.75°N, 74.75°E)
- `ERA5_1375_07450` (13.75°N, 74.50°E)
- `ERA5_1400_07450` (14.00°N, 74.50°E)
- `ERA5_1450_07425` (14.50°N, 74.25°E)
- `ERA5_1475_07400` (14.75°N, 74.00°E)
- `ERA5_1500_07400` (15.00°N, 74.00°E)

### Architectural Decision (Phase 3.12D Backward-Compatible Model)
- **Authoritative Grid (324 Cells):** Preserved in full across 33 permanent spatial batches. These 6 cells remain part of the canonical Karnataka state grid because their envelopes intersect the KSR-SAC state boundary polygon. They are never deleted from platform geometry.
- **ERA5 Extraction-Eligible Grid (318 Cells):** The 6 cells are excluded *within* their respective batches (Batches 004, 011, 012, 015, 016, 018 query 9 cells; all others query 10; Batch 033 queries 4 cells).
- **Documented Exclusion Reason:**
  > "Open-Meteo ERA5 archive snaps requested offshore coordinate to a neighboring land-side ERA5 coordinate, preventing one-to-one spatial identity."
- **Invariants Enforced:** Zero tolerance for coordinate drift, no coordinate rewriting, and no result deduplication.
- **Production Inventory:** 33 permanent spatial batches over 26 years (1969–1994) = **858 production chunks** (3,019,728 daily records across the 318 eligible cells).
- **Spatial Fingerprinting:** Every chunk verifies a deterministic 8-character hex cell-set fingerprint (`spatial_fingerprint`), guaranteeing that cached files match expected coordinates without batch shifting.

---

## Gate 4 Prerequisites

Before designing or executing production ingestion, Gate 4 must address:

1. **Missing / Null Analysis Across Spatial Samples:** Systematically quantify null rates across a broader sample of the 324 intersecting grid points.
2. **Precipitation Units and Accumulation Semantics:** Empirically verify whether Open-Meteo's `precipitation` variable represents hourly flux rate ($mm/hr$) or cumulative interval depth, and verify SI unit consistency.
3. **Timestamp Semantics:** Confirm UTC to IST timestamp alignment against diurnal solar temperature and relative humidity cycles.
4. **Reproducible Extraction Test:** Prove bitwise determinism across repeated API calls for identical spatial coordinates.
5. **Request Batching & Rate Limit Feasibility:** Profile request latency, batch chunk sizes, and rate limiting (staying within the 10,000 requests/day free tier) for extracting 324 cells across historical event windows.
6. **Independent Precipitation Cross-Check:** Cross-reference ERA5 precipitation against independent observational benchmarks (IMD gridded rainfall or CWC station logs) for a documented historical flood event.
