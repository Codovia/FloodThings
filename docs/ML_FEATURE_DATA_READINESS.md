# Phase 3.6: ML Feature & Data Readiness Design

**Project:** FloodPulse
**Phase:** Phase 3.6 — ML Feature & Data Readiness Design
**Date:** 2026-09-19
**Status:** COMPLETE (Design & Contract Specification Only — Zero Models Trained, Zero Data Mutated)

---

## 1. Executive Summary

Phase 3.6 establishes the leakage-safe machine learning (ML) feature and data readiness architecture for FloodPulse. Based on the empirical environmental data audit conducted in Phase 3.5, this design determines exactly which ML units of analysis, prediction targets, and feature sets are legitimately supportable from **real data**, without fabricating synthetic observations, imputing missing values, or compromising causal temporal integrity.

### Critical Findings

1. **No Spatial Unit Is Currently Trainable from Database Data Today:**
   In the PostgreSQL database today, weather observations exist for **2024–2026** (at only 5 discrete points), while historical flood observations exist for **1969–1994** (at the district level). There is **0% temporal overlap** between features and target labels in the database today. Consequently, **no spatial unit can currently be trained** without backfilling historical atmospheric reanalysis (ERA5).
2. **District Is the Only Conditionally Viable Spatial Unit:**
   Upon backfilling historical weather reanalysis, the **Administrative District** (31 KSR-SAC districts) is the only unit supported by verified historical flood evidence (India Flood Inventory v3.0). All finer-grained units (Taluk, 0.05°/0.1° Regular Grid, River Station, Inundation Footprints) are **BLOCKED** due to absence of corresponding ground truth labels.
3. **Only One Target Candidate Is Conditionally Viable:**
   **Target A (District Flood Occurrence: $Y_{d, t} \in \{0, 1\}$)** is `CONDITIONALLY_SUPPORTED`. Targets B (Affected Area), C (Spatial Inundation Extent), D (River Gauge Threshold Exceedance), and E (Severity Category) are strictly `BLOCKED` due to unviable multi-district attribution heuristics, complete absence of satellite SAR inundation masks, missing statutory CWC danger levels, or qualitative label sparsity.
4. **Strict Three-State Labelling Policy:**
   Because IFI is a positive-only disaster damage archive, treating all unrecorded district-days as "negative" introduces severe false-negative bias. A formal three-state contract (`POSITIVE`, `NEGATIVE`, `UNLABELLED`) is required, pairing positive disaster events with meteorological non-event background sampling.
5. **Zero Model Training & Zero Data Mutation:**
   In adherence to project constraints, zero ML models were trained, zero synthetic observations were created, zero database records were altered, and zero migrations were generated.

---

## 2. Current ML Unit Options

We evaluate five candidate spatial units of analysis against Project Constraints, verified data availability, and ML methodology requirements:

| Candidate Unit | Available Labels | Available Predictors | Spatial Resolution | Temporal Resolution | Karnataka Coverage | Leakage Risk | Missing-Data Problem | Trainable with Current Real Data? |
|---|---|---|---|---|---|---|---|---|
| **A. District** | IFI v3.0 historical disaster observations (`flood_observations`) | Open-Meteo weather/rainfall (5 points currently); KSR-SAC zonal GIS; static terrain | Coarse administrative ($3,000 \text{ to } 16,000 \text{ km}^2$) | Daily ($t \in \text{YYYY-MM-DD}$) | 31 districts (30 with historical IFI events; 5 with weather obs) | Low (if temporal split & post-disaster metadata excluded) | Severe (26 districts lack weather; 0% feature-target overlap in DB) | **NO** (0% DB temporal overlap; requires ERA5 backfill) |
| **B. Taluk** | None (`taluk_id` is 100% NULL in `flood_observations`) | None (weather observations have no taluk mapping; 5 points statewide) | Sub-district ($500 \text{ to } 2,500 \text{ km}^2$, 240 taluks) | Daily | 240 taluks | High (attributing district disaster to taluks fabricates labels) | Fatal (zero taluk flood labels; zero taluk weather stations) | **NO (BLOCKED)** |
| **C. Regular Spatial Grid (0.05° / 0.1°)** | None (zero coordinate geometries in IFI; satellite SAR masks unavailable) | Open-Meteo ERA5 / NWP can be queried at grid centroids | Fine-grained ($5 \times 5 \text{ km}$ to $11 \times 11 \text{ km}$) | Hourly to Daily | Full statewide grid (~1,600 to ~6,400 cells) | Extreme (assigning district disaster to grid cells creates massive false-positive label noise) | Fatal (zero grid-level ground truth target labels) | **NO (BLOCKED)** |
| **D. River Station** | None (no flood damage labels at gauge points; danger levels NULL) | Hourly stage at 1 station (Akkihebbal); discharge is 100% NULL | Point gauge location | Hourly | 1 station in 1 district (Cauvery basin only) | Moderate (upstream-downstream temporal lag) | Fatal (1 station statewide; 30 districts have zero river telemetry) | **NO (BLOCKED)** |
| **E. Event / Location Observation** | Positive disaster damage events only | None (no micro-location weather or terrain) | Variable polygon / point | Event-based | Episodic (100 events in DB tranche) | Severe (selection bias towards major infrastructure damage) | Fatal (positive-only; spatial footprint undefined) | **NO (BLOCKED)** |

### Unit Classification Summary

- **CURRENTLY SUPPORTED ML UNIT:** **NONE**.
  *Reason:* With current database records, zero temporal overlap exists between 1969–1994 flood observations and 2024–2026 weather observations. No defensible model can be trained today.
- **CONDITIONALLY SUPPORTED ML UNIT (Pending ERA5 Reanalysis Backfill):** **District**.
  *Reason:* The only unit supported by legitimate, authoritative disaster damage evidence (IFI v3.0) and verified administrative polygons (KSR-SAC).
- **CURRENTLY BLOCKED ML UNITS:** **Taluk**, **Regular Spatial Grid**, **River Station**, **Event/Location Observation**.
  *Reason:* Absence of ground truth target labels at these resolutions. Assigning district disaster labels to sub-district taluks or grid cells violates `CONSTRAINTS.md` (zero synthetic geometry and zero label fabrication).

---

## 3. Target Definitions

We evaluate five potential target formulations:

### Target A: District Flood Occurrence / Event Condition
- **Mathematical Definition:** $Y_{d, t} \in \{0, 1\}$, where:
  $$Y_{d, t} = \begin{cases} 1 & \text{if a verified flood disaster occurred in district } d \text{ on calendar day } t \\ 0 & \text{if verified non-flood / dry baseline condition is established} \end{cases}$$
- **Exact Source:** India Flood Inventory (IFI v3.0) normalized observations (`flood_observations.flooded = TRUE`) joined with meteorological non-event background sampling.
- **Positive-Label Availability:** 186 district-event records in DB (1,271 in audited full raw archive across 30 districts).
- **Negative-Label Availability:** Unavailable in raw IFI (positive-only); must be constructed via audited background sampling.
- **Geometry Availability:** District boundary polygons (`districts.geometry`, EPSG:4326).
- **Temporal Alignment Requirements:** Daily calendar day ($t \in \text{YYYY-MM-DD}$).
- **Leakage Controllability:** Controllable via strict chronological splitting and exclusion of post-disaster summary metrics (`Duration`, `Fatalities`, `Area Affected`).

### Target B: Flood Affected Area
- **Mathematical Definition:** $Y_{d, t} \in \mathbb{R}^+$, continuous area flooded in square kilometres.
- **Exact Source:** IFI v3.0 `Area Affected`.
- **Positive-Label Availability:** Present only for a subset of multi-district events as a single aggregate number.
- **Negative-Label Availability:** Absent.
- **Geometry Availability:** None.
- **Temporal Alignment Requirements:** Event duration (multi-day).
- **Leakage Controllability:** Unviable. Distributing a multi-district total (e.g. $1,000 \text{ km}^2$ across 5 districts) requires arbitrary heuristic allocation, violating `CONSTRAINTS.md`.

### Target C: Spatial Inundation / Flood Extent
- **Mathematical Definition:** $Y_{i, t} \in \{0, 1\}$ for pixel/cell $i$, or continuous water depth $h_{i, t} \ge 0.3 \text{ m}$.
- **Exact Source:** High-resolution satellite SAR water masks (Sentinel-1 / RISAT) or aerial surveys.
- **Positive-Label Availability:** **Zero**. Open machine-readable SAR flood inundation archives for Karnataka are completely unavailable in the repository or public open APIs.
- **Negative-Label Availability:** Zero.
- **Geometry Availability:** MultiPolygon / Raster.
- **Temporal Alignment Requirements:** Satellite pass overpass timestamps (6–12 day repeat cycle).
- **Leakage Controllability:** N/A (data absent).

### Target D: River Gauge Threshold Exceedance
- **Mathematical Definition:** $Y_{s, t} = \mathbb{I}(\text{Water Level}_{s, t} \ge \text{Danger Level}_s)$.
- **Exact Source:** NWIC / Central Water Commission (CWC) river stage telemetry (`river_observations.water_level`).
- **Positive-Label Availability:** 101 observations at Akkihebbal, but **Danger Level is NULL**.
- **Negative-Label Availability:** Continuous stage is available, but exceedance cannot be evaluated without statutory danger levels.
- **Geometry Availability:** Point station (`river_stations.geometry`, EPSG:4326).
- **Temporal Alignment Requirements:** Hourly.
- **Leakage Controllability:** Controllable via lag filtering.

### Target E: Flood Severity Category
- **Mathematical Definition:** $Y_{d, t} \in \{\text{Class 1 (Minor)}, \text{Class 2 (Moderate)}, \text{Class 3 (Severe)}\}$.
- **Exact Source:** IFI v3.0 `Severity`.
- **Positive-Label Availability:** Sparsely and qualitatively populated; lacks standardized physical criteria (e.g. return period or discharge volume).
- **Negative-Label Availability:** Absent.
- **Geometry Availability:** District boundary.
- **Temporal Alignment Requirements:** Event-level.
- **Leakage Controllability:** Unviable due to subjective reporting inconsistency.

---

## 4. Target Readiness

| Target Candidate | Source | Target Type | Current Status | Concrete Blocker / Reason | Additional Real Data Required |
|---|---|---|---|---|---|
| **Target A: District Flood Occurrence** | IFI v3.0 | Binary Classification ($Y \in \{0, 1\}$) | `CONDITIONALLY_SUPPORTED` | 0% temporal overlap with weather in DB; positive-only catalog | Historical weather reanalysis (ERA5 1969–1994 or modern tranche); audited negative-sampling protocol |
| **Target B: Flood Affected Area** | IFI v3.0 | Regression ($Y \in \mathbb{R}^+$) | `BLOCKED` | Multi-district event aggregation prevents defensible district attribution | District-disaggregated surveyed flood area records |
| **Target C: Spatial Inundation Extent** | Remote Sensing | Pixel / Polygon Binary | `BLOCKED` | High-resolution satellite SAR water masks completely absent | Sentinel-1 / NISAR / NRSC SAR flood inundation polygons |
| **Target D: River Gauge Exceedance** | CWC / NWIC | Point Binary | `BLOCKED PENDING METADATA` | CWC telemetry omits official Danger Level (DL) and Warning Level (WL) | Official CWC Danger Level and Warning Level statutory benchmarks |
| **Target E: Flood Severity Category** | IFI v3.0 | Multi-Class Categorical | `BLOCKED` | Qualitative, non-standardized, sparse severity reporting in historical catalog | Standardized hydrological return period or damage severity metrics |

---

## 5. Feature Inventory

Every candidate feature is evaluated against actual stored/source data and classified as `AVAILABLE_NOW`, `AVAILABLE_WITH_ADDITIONAL_REAL_DATA`, or `BLOCKED`:

### 5.1 Weather Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `temperature_mean_24h` | WEATHER | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo ERA5 (`REANALYSIS`) / NWP (`MODEL_OUTPUT`) | 5 points; 2024 & 2026 tranches (803d gap) | 0% NULL in current rows | Covers only 5 districts; zero overlap with historical flood target | Ingest ERA5 across all 31 districts for historical target window |
| `humidity_mean_24h` | WEATHER | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo ERA5 / NWP | 5 points; 803d gap | 0% NULL | Same spatial and temporal constraints as temperature | Ingest ERA5 across all 31 districts |
| `pressure_mean_24h` | WEATHER | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo ERA5 / NWP | 5 points; 803d gap | 0% NULL | Same spatial and temporal constraints | Ingest ERA5 across all 31 districts |
| `wind_speed_mean_24h` | WEATHER | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo ERA5 / NWP | 5 points; 803d gap | 0% NULL | Same spatial and temporal constraints | Ingest ERA5 across all 31 districts |
| `wind_direction_mean_24h`| WEATHER | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo ERA5 / NWP | 5 points; 803d gap | 0% NULL | Same spatial and temporal constraints | Ingest ERA5 across all 31 districts |

### 5.2 Temporal Rainfall Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `rainfall_1h` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Model-derived; 26 districts missing; 803d gap | Ingest continuous gridded rainfall (IMD / ERA5) statewide |
| `rainfall_3h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Rolling window requires continuous hourly series | Continuous hourly rainfall across target window |
| `rainfall_6h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Same constraints | Continuous hourly rainfall |
| `rainfall_12h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Same constraints | Continuous hourly rainfall |
| `rainfall_24h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Same constraints | Continuous daily rainfall |
| `rainfall_48h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Same constraints | Continuous daily rainfall |
| `rainfall_72h_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Same constraints | Continuous daily rainfall |
| `rainfall_7d_sum` | TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo Precipitation | 5 points; 803d gap | 0% NULL | Requires 7 consecutive days of prior data | Continuous daily rainfall |
| `antecedent_precip_index`| TEMPORAL_RAINFALL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Derived from daily rainfall | $\text{API}_t = \sum_{k=1}^{30} k^{-0.5} P_{t-k}$ | Requires 30d continuous history | 803-day gap breaks API calculation | 30-day continuous prior rainfall |

### 5.3 Hydrological Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `river_stage_current` | HYDROLOGY | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | CWC / NWIC (`OBSERVATION`) | 1 station (Akkihebbal, Mandya); Jan–Jun 2026 | 0% NULL at Akkihebbal | Covers 1 of 31 districts; 149d gap; zero overlap with 1969–1994 | Ingest 95+ CWC river stations across Karnataka |
| `river_stage_relative` | HYDROLOGY | `BLOCKED` | CWC / NWIC | 1 station | 100% NULL (Danger level NULL) | Relative freeboard ($\text{Stage} - \text{Danger Level}$) cannot be computed | Authoritative CWC Danger Level metadata |
| `river_discharge_current`| HYDROLOGY | `BLOCKED` | CWC / NWIC | 1 station | **100% NULL (101/101)** | Volumetric flow ($Q \text{ m}^3/\text{s}$) not recorded in telemetry | Direct discharge observations or rating curves |
| `reservoir_storage_pct` | HYDROLOGY | `BLOCKED` | NWIC Karnataka Dam Telemetry | 1 dam (Almatti); 2006–2008 only | **100% NULL (100/100)** | 18-year-old archive; zero operational telemetry; 13 dams missing | Operational dam telemetry across 14 Karnataka dams |
| `reservoir_release_flow`| HYDROLOGY | `BLOCKED` | NWIC Dam Telemetry | 1 dam; 2006–2008 only | 0% NULL in 2006–2008 rows | Completely unpopulated for modern or target period | Operational daily reservoir release data |

### 5.4 Terrain Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `elevation_mean_district`| TERRAIN | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Copernicus DEM GLO-30 (`OBSERVATION`) | Statewide static raster | Not yet ingested into DB | Range-read verified in Phase 2.3; zonal statistics pipeline not run | Ingest DEM raster & compute district zonal statistics |
| `slope_mean_district` | TERRAIN | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Copernicus DEM GLO-30 | Statewide static raster | Not yet ingested into DB | Derived from DEM gradient; zonal aggregation not run | Compute slope raster & zonal district mean/std |
| `topographic_wetness_idx`| TERRAIN | `BLOCKED` | Derived from DEM | None | 0 records | Requires flow accumulation and upstream drainage area routing | Hydrologically conditioned DEM & flow routing |

### 5.5 Spatial & GIS Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `district_area_sqkm` | SPATIAL | `AVAILABLE_NOW` | KSR-SAC `districts.geometry` (`REFERENCE`) | 31 districts (100% valid PostGIS MultiPolygon) | 0% NULL | Deterministically computed via `ST_Area(geography)` | None |
| `basin_membership` | SPATIAL | `BLOCKED` | `river_basins` | 2 rows (Cauvery, Krishna) | **100% NULL geometry** | RiverBasin boundary geometries are unpopulated | Ingest WRIS / CWC basin boundary polygons |
| `distance_to_river` | SPATIAL | `BLOCKED` | `rivers` | 2 rows (Cauvery, Krishna) | **100% NULL geometry** | River centerlines have no spatial coordinates | Ingest CWC / NWIC river stream network vectors |
| `drainage_density` | SPATIAL | `BLOCKED` | Derived from river network | None | 0 records | Total stream length per unit area cannot be computed | Complete river centerline vector network |
| `land_use_imperviousness`| SPATIAL | `BLOCKED` | Satellite LULC | None | 0 records | LULC layer (NRSC / ESA WorldCover) not in database | Ingest high-resolution LULC raster |

### 5.6 Historical Flood Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `historical_event_count_10y`| HISTORICAL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | IFI v3.0 (`HISTORICAL_EVENT`) | 30 districts; 1969–2023 | 0% NULL in raw archive | Must be computed strictly from prior years ($t < T_{\text{pred}}$) to prevent target leakage | Load full 1969–2023 audited IFI archive into PostgreSQL |
| `monsoon_month_frequency` | HISTORICAL | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | IFI v3.0 | 30 districts; 1969–2023 | 0% NULL in raw archive | Empirical historical monthly flood probability ($P(\text{Flood} \mid \text{District}, \text{Month})$) | Load full audited IFI archive into PostgreSQL |

### 5.7 Forecast Features
| Feature Name | Category | Readiness | Source & Provenance | Spatial / Temporal Coverage | Missingness | Concrete Reason / Limitations | Additional Data Required |
|---|---|---|---|---|---|---|---|
| `forecast_rainfall_24h` | FORECAST | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo 72h NWP (`FORECAST`) | 5 district centers; 55h horizon snapshot | 0% NULL in 5 centers | Single snapshot from Sept 2026; 26 districts missing; cannot pair with historical events | Rolling daily forecast ingestion across 31 districts |
| `forecast_rainfall_48h` | FORECAST | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo 72h NWP | 5 district centers; 55h horizon | 0% NULL in 5 centers | Same constraints | Rolling daily forecast ingestion |
| `forecast_temp_mean` | FORECAST | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Open-Meteo 72h NWP | 5 district centers; 55h horizon | 0% NULL in 5 centers | Same constraints | Rolling daily forecast ingestion |
| `forecast_rain_probability`| FORECAST | `BLOCKED` | Open-Meteo | 5 district centers | **100% NULL (275/275)** | Open-Meteo hourly product in this pipeline does not publish rain probability | Alternative ensemble forecast API providing calibrated probability |

---

## 6. Temporal Leakage Rules

### 6.1 Formal Prediction Timestamp
All feature generation and sample construction must be anchored to an explicit prediction timestamp:
$$T_{\text{pred}} \in \text{TIMESTAMPTZ}$$

For daily district flood prediction, $T_{\text{pred}}$ is conventionally set to morning issue time:
$$T_{\text{pred}} = \text{YYYY-MM-DD 06:00:00 IST} = \text{YYYY-MM-DD 00:30:00 UTC}$$

### 6.2 Strict Temporal Invariants

1. **Past Observations Rule:**
   Every historical feature derived from physical observations, reanalysis, or model outputs must satisfy:
   $$\text{observed\_at} \le T_{\text{pred}}$$
   Any feature utilizing observations where $\text{observed\_at} > T_{\text{pred}}$ constitutes catastrophic future data leakage.

2. **Forecast Timing Invariant:**
   Forecast features represent predictions of future atmospheric conditions. To prevent leakage:
   $$T_{\text{issue}} \le T_{\text{pred}} < T_{\text{valid}}$$
   - The forecast must have been **issued at or before** the prediction timestamp ($T_{\text{issue}} \le T_{\text{pred}}$).
   - The forecast must be predicting conditions **strictly after** the prediction timestamp ($T_{\text{valid}} > T_{\text{pred}}$).
   - Under no circumstances may a forecast issued at $T_{\text{issue}} > T_{\text{pred}}$ be used.

3. **Disaster Metadata Exclusion Invariant:**
   IFI historical disaster event records include fields recorded *after* the flood has concluded:
   - `End Date`
   - `Duration(Days)`
   - `Human fatality`
   - `Human Displaced`
   - `Area Affected`
   **Mandatory Rule:** These fields must **never** enter any feature vector. They are post-event consequences, not pre-event predictors.

### 6.3 Historical Window Supportability Analysis

| Window Code | Nominal Duration | Supportable by Current 2024/2026 DB Data? | Reason / Failure Mode |
|---|---|---|---|
| **T-1h** | 1 hour prior to $T_{\text{pred}}$ | **Yes** (during active operational monitoring) | 1-hour sampling interval supports T-1h during active monitoring windows. |
| **T-3h** | 3 hours prior to $T_{\text{pred}}$ | **Yes** (during active operational monitoring) | Supported during active monitoring windows. |
| **T-6h** | 6 hours prior to $T_{\text{pred}}$ | **Yes** (during active operational monitoring) | Supported during active monitoring windows. |
| **T-12h** | 12 hours prior to $T_{\text{pred}}$ | **Yes** (during active operational monitoring) | Supported during active monitoring windows. |
| **T-24h** | 24 hours prior to $T_{\text{pred}}$ | **Yes** (during active operational monitoring) | Supported during active monitoring windows. |
| **T-48h** | 48 hours prior to $T_{\text{pred}}$ | **Partially** (breaks at tranche transitions) | Fails across the 803-day gap between 2024-07-03 and 2026-09-15. |
| **T-72h** | 72 hours prior to $T_{\text{pred}}$ | **Partially** (breaks at tranche transitions) | Fails across the 803-day gap. |
| **T-30d (API)**| 30 days antecedent rainfall | **NO (BLOCKED)** | The 803-day gap makes 30-day continuous rolling calculations impossible for current data. |

---

## 7. Spatial Association Design

### 7.1 Authoritative Spatial Reference
All spatial associations must use the authoritative KSR-SAC administrative geometries ingested into PostGIS in Phase 3.2:
- `states.geometry` (1 feature, MultiPolygon, EPSG:4326)
- `districts.geometry` (31 features, MultiPolygon, EPSG:4326)
- `taluks.geometry` (240 features, MultiPolygon, EPSG:4326)

### 7.2 Point-to-Polygon Association Rules
For any environmental observation point $P = (\text{lon}, \text{lat})$:
1. **Coordinate Verification:** Coordinate must be in WGS 84 (`EPSG:4326`). Latitude must satisfy $[-90, 90]$ and longitude $[-180, 180]$.
2. **PostGIS Point Generation:** `geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)`.
3. **State Containment Guard:**
   $$\text{ST\_Contains}(\text{state.geometry}, geom) = \text{TRUE}$$
   Points falling outside the Karnataka State boundary must be rejected or flagged as `OUT_OF_STATE`.
4. **District Association:**
   $$\text{ST\_Contains}(\text{district.geometry}, geom) = \text{TRUE}$$
   If a point falls precisely on a boundary edge (`ST_Touches`), assignment defaults to the district with the lowest administrative LGD code to guarantee determinism.
5. **Boundary Integrity:** As proven in Phase 3.3 and Phase 3.4B, 100% of stored weather points (397/397) and river stations (1/1) fall strictly inside their assigned district polygons with zero boundary ambiguities.

### 7.3 Boundary Slivers and Taluk Containment
Phase 3.3 and Phase 3.5 established that 44 taluks are strictly within their parent district (`ST_Within = TRUE`), while 196 taluks exhibit minor boundary slivers (< 0.00001% area discrepancy, overlap $\ge 99.999\%$) due to independent source digitization:
- **Rule:** Taluks must **never** have their geometry clipped or modified.
- **Rule:** Taluk-to-district assignment is established exclusively via the authoritative foreign key (`taluks.district_id`), which preserves 100.0% administrative integrity.
- **Rule:** Point-in-taluk queries must use `ST_Intersects(taluk.geometry, geom)`. If a point intersects a micro-sliver shared by adjacent polygons, the primary parent district's taluk takes precedence.

---

## 8. Negative Label Requirements

### 8.1 The Positive-Only Nature of Disaster Catalogs
The India Flood Inventory (IFI v3.0) is compiled from official government disaster damage bulletins (IMD, CWC, Ministry of Home Affairs) and media reports. It is fundamentally an **episodic disaster damage inventory**, not a systematic meteorological monitoring log.

### 8.2 Why Naive Negation Is Scientifically Invalid
A common but catastrophic flaw in disaster ML is the **Closed-World Assumption**:
$$\text{No IFI record on day } t \text{ in district } d \implies Y_{d, t} = 0 \quad \text{(FATALLY FLAWED)}$$

**Scientific Reasons Why Naive Negation Fails:**
1. **Reporting Threshold Bias:** IFI records severe flood disasters (loss of life, thousands displaced, major crop destruction). Moderate, agricultural, or localized inundations that caused no reported casualties or major infrastructure damage were not captured by national news bulletins.
2. **Historical Reporting Completeness:** As proven in Phase 2.7, reporting frequency increases by an order of magnitude over time: 1969–1979 has only 10 events, while 2010–2019 has 198 events. Assuming zero flooding on unrecorded days in 1970 assumes 100% reporting completeness across 55 years, which is historically false.
3. **Severe Class Imbalance Artifacts:** Karnataka has 31 districts $\times 365 \text{ days} \times 55 \text{ years} = 622,325 \text{ district-days}$. With only 1,271 positive observations, naive negation yields an artificial positive prevalence of **0.20%**, burying models in massive false-negative noise.

### 8.3 Candidate Negative / Background Sampling Criteria — NOT YET APPROVED

To construct scientifically valid negative training instances without fabricating labels, FloodPulse must develop an audited **Meteorological Non-Event Background Sampling Strategy**.

Candidate criteria under consideration may include:
1. **Verified Meteorological Observation Completeness:** Sample must fall within a period of documented, active, and complete meteorological observation (e.g., uninterrupted daily rainfall records).
2. **Low Antecedent Rainfall Relative to a Historical Baseline:** Antecedent rainfall over an appropriate accumulation window must indicate a confirmed dry baseline relative to an appropriately constructed, seasonally adjusted historical distribution.
3. **Verified Hydrological Non-Event Conditions:** Absence of high river stage or major upstream reservoir discharges, where authoritative thresholds exist.
4. **Temporal Buffer from Documented Flood Events:** Samples must be separated by an adequate temporal buffer (e.g., several days) from any documented IFI disaster events in that district or hydrologically connected catchments to avoid transition or receding flood periods.

> [!WARNING]
> **Status: NOT YET APPROVED / NOT IMPLEMENTED**
> - **Percentile thresholds have NOT yet been validated:** Specific numerical thresholds (such as fixed rainfall percentiles or accumulation windows) have not undergone empirical sensitivity analysis and are NOT approved project rules.
> - **No fixed rainfall percentile is currently an approved label rule:** Any specific percentile cutoff requires empirical validation against historical weather distributions.
> - **No fixed river-stage offset is currently an approved label rule:** The current database does not possess statutory river warning or danger levels (they are `NULL`), making any fixed stage offset ungrounded.
> - **Current river warning/danger thresholds are unavailable:** As established in Phase 3.5, CWC warning and danger levels are completely unpopulated.
> - **Negative-label generation is therefore NOT IMPLEMENTED in Phase 3.6.**
>
> All negative-label criteria must be rigorously established from real source data, documented, and formally validated before any supervised model training can occur in future phases.

### 8.4 The Three-State Labelling Contract
Every potential sample in the training universe must be explicitly assigned to one of three states:
1. **`POSITIVE` ($Y = 1$):** Documented flood disaster evidence in IFI v3.0 for district $d$ on calendar day $t$.
2. **`NEGATIVE` ($Y = 0$):** Validated by an authoritative, empirically verified background sampling protocol (to be established and validated prior to training).
3. **`UNLABELLED` ($Y = \text{NULL}$):** All remaining district-days where non-flood status cannot be rigorously proven from real data. **Must be excluded from supervised loss computation.**

---

## 9. Feature Provenance

To guarantee scientific auditability and prevent subtle operational failures, every engineered feature must retain complete semantic provenance:

### 9.1 Minimum Required Metadata Schema
Every feature record stored in the future feature store must track:
```json
{
  "feature_name": "rainfall_24h_sum",
  "source_name": "Open-Meteo Weather API",
  "source_data_category": "MODEL_OUTPUT",
  "source_record_id": "openmeteo_hourly_2026-09-17T12:00:00Z",
  "observed_at": "2026-09-17T12:00:00+00:00",
  "retrieved_at": "2026-09-17T16:44:12+00:00",
  "valid_at": "2026-09-17T12:00:00+00:00",
  "transformation_method": "ROLLING_SUM_24H",
  "spatial_aggregation": "ZONAL_MEAN_DISTRICT"
}
```

### 9.2 Provenance Categories
Features must explicitly declare their fundamental nature:
- `OBSERVATION`: Physical in-situ gauge readings (CWC river stage, rain gauge).
- `REANALYSIS`: Historical gridded atmospheric reanalysis (ERA5).
- `MODEL_OUTPUT`: Numerical weather prediction simulation runs.
- `FORECAST`: Forward-looking predictive simulation.
- `HISTORICAL_EVENT`: Curated disaster damage inventory.
- `REFERENCE`: Authoritative boundary or identifier reference (KSR-SAC).
- `DERIVED`: Computed feature combining multiple source records (e.g. Antecedent Precipitation Index, Slope).

---

## 10. Future Training Dataset Contract

The conceptual schema for the future machine learning dataset table (`ml_dataset_samples`):

### 10.1 Schema Definition

| Column Name | Data Type | Nullable? | Units / Allowed Values | Description |
|---|---|---|---|---|
| `sample_id` | `UUID` | No | UUID v4 | Unique identifier for each training sample |
| `prediction_time` | `TIMESTAMPTZ` | No | ISO 8601 UTC | Anchor timestamp for prediction |
| `spatial_unit_type` | `VARCHAR(30)` | No | `DISTRICT` | Spatial unit of analysis |
| `spatial_unit_id` | `UUID` | No | FK to `districts.id` | Target district identifier |
| `feature_window_start`| `TIMESTAMPTZ` | No | UTC | Earliest timestamp included in features |
| `feature_window_end` | `TIMESTAMPTZ` | No | UTC | Latest timestamp (must be $\le \text{prediction\_time}$) |
| `target_window_start` | `TIMESTAMPTZ` | No | UTC | Start of target period (must be $\ge \text{prediction\_time}$) |
| `target_window_end` | `TIMESTAMPTZ` | No | UTC | End of target period (e.g. $T_{\text{pred}} + 24\text{h}$) |
| `label_state` | `VARCHAR(20)` | No | `POSITIVE`, `NEGATIVE`, `UNLABELLED` | Strict label classification |
| `target_value` | `INTEGER` | **Yes** | `1`, `0`, or `NULL` | Binary target (must be `NULL` if `UNLABELLED`) |
| `target_name` | `VARCHAR(100)`| No | e.g. `district_flood_occurrence_24h` | Formal target name |
| `features` | `JSONB` | No | Key-value pairs | Feature vector with numeric values |
| `feature_provenance` | `JSONB` | No | JSON object | Provenance records for every feature |
| `split_assignment` | `VARCHAR(20)` | No | `TRAIN`, `VALIDATION`, `TEST` | Designated evaluation split |

### 10.2 Strict Invariants
1. `label_state == 'UNLABELLED' \iff target_value IS NULL`.
2. `label_state == 'POSITIVE' \iff target_value == 1`.
3. `label_state == 'NEGATIVE' \iff target_value == 0`.
4. `feature_window_end <= prediction_time`.
5. `target_window_start >= prediction_time`.
6. `target_window_end > target_window_start`.

---

## 11. Evaluation Split Design

### 11.1 Prohibition of Random Splitting
Random $k$-fold cross-validation or random train/test splitting is **strictly prohibited** for flood time-series prediction:
- Severe flood events typically span multiple consecutive days (3 to 10 days).
- A random split would place Day 1 in Train and Day 2 in Test, allowing the model to memorize the ongoing event rather than learning predictive hydrological dynamics.
- Weather patterns exhibit strong spatial and temporal autocorrelation across adjacent districts.

### 11.2 The Three Evaluation Regimes

```
+-----------------------------------------------------------------------------------------------+
| EVALUATION SPLIT REGIMES                                                                      |
+-----------------------------------------------------------------------------------------------+
| 1. TEMPORAL HOLDOUT (Primary Validation):                                                     |
|    - Evaluates forward-in-time generalization (predicting the future from the past).          |
|    - Split Strategy:                                                                          |
|        Train:      Earliest 70% of historical period (e.g. 1969–2010)                         |
|        Validation: Middle 15% of historical period   (e.g. 2011–2017)                         |
|        Test:       Latest 15% of historical period   (e.g. 2018–2023)                         |
|                                                                                               |
| 2. SPATIAL HOLDOUT (Clustered District Cross-Validation):                                     |
|    - Evaluates generalization to unmonitored or geographically distinct regions.              |
|    - Split Strategy: Group districts by River Basin (Krishna Basin vs. Cauvery Basin vs.      |
|      West-Flowing Coastal Rivers). Train on 2 basins; evaluate on the held-out basin.         |
|                                                                                               |
| 3. SPATIOTEMPORAL HOLDOUT (Production Stress Test):                                          |
|    - Evaluates forward-in-time generalization on geographically held-out districts.           |
|    - Both time and space are disjoint between training and test sets.                         |
+-----------------------------------------------------------------------------------------------+
```

---

## 12. Current Readiness Matrix

Comprehensive factual status across all FloodPulse data sources and potential ML components:

| Data Source / Entity | Component | Spatial Coverage | Temporal Coverage | Provenance | Missingness | Leakage Risk | ML Status | Additional Real Data Required |
|---|---|---|---|---|---|---|---|---|
| **Open-Meteo Weather** | Weather Features (`temperature`, `humidity`, etc.) | 5 points (5/31 districts) | July 2024 & Sept 2026 (803d gap) | `REANALYSIS` (72), `MODEL_OUTPUT` (325) | 0% in current rows | Low (if $t \le T_{\text{pred}}$) | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Ingest ERA5 across all 31 districts for historical event window |
| **Open-Meteo Precipitation** | Rainfall Features (`rainfall_24h`, `API`) | 5 points (5/31 districts) | July 2024 & Sept 2026 (803d gap) | `REANALYSIS` (72), `MODEL_OUTPUT` (325) | 0% in current rows | Low (if $t \le T_{\text{pred}}$) | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Continuous daily rainfall across all 31 districts |
| **Open-Meteo Forecast** | Forecast Features (`forecast_rainfall_24h`) | 5 district centers | 55-hour snapshot (Sept 2026) | `FORECAST` (275) | `rainfall_prob` is 100% NULL | High (if $T_{\text{issue}} > T_{\text{pred}}$) | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Daily rolling forecast ingestion pipeline |
| **NWIC CWC River Levels** | River Stage (`water_level`) | 1 station (Akkihebbal, Mandya) | Jan–Jun 2026 (101 obs, 149d gap) | `OBSERVATION` | `discharge` is 100% NULL | Low | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Ingest 95+ CWC river stations across Karnataka |
| **NWIC CWC River Levels** | River Exceedance Target (Target D) | 1 station | Jan–Jun 2026 | `OBSERVATION` | Danger level is NULL | Low | `BLOCKED PENDING METADATA` | Authoritative CWC Danger Level benchmarks |
| **NWIC Dam Telemetry** | Reservoir Storage / Release | 1 dam (Almatti, Krishna) | 2006–2008 (100 obs) | `OBSERVATION` (Historical archive) | 100% missing for modern period | Low | `BLOCKED` | Operational dam telemetry across 14 major Karnataka dams |
| **India Flood Inventory** | District Flood Occurrence (Target A) | 23 districts in DB (30 in raw archive) | 1969–1994 in DB (1969–2023 in archive) | `HISTORICAL_EVENT` (186 in DB) | `geometry` 100% NULL; `depth` 100% NULL | High (if post-disaster metrics used) | `CONDITIONALLY_SUPPORTED` | ERA5 historical reanalysis backfill; negative-sampling protocol |
| **KSR-SAC Administrative GIS**| Spatial Unit & Aggregation | 1 State, 31 Districts, 240 Taluks | Static baseline (2026) | `REFERENCE` (100% valid PostGIS MultiPolygon) | 0% NULL | Zero | `AVAILABLE_NOW` | None |
| **Copernicus DEM GLO-30** | Terrain Features (`elevation`, `slope`) | Statewide 30m raster | Static baseline (2011–2015) | `OBSERVATION` (Satellite radar) | Not yet in DB | Zero | `AVAILABLE_WITH_ADDITIONAL_REAL_DATA` | Ingest DEM & compute district zonal statistics |
| **Hydrological Vectors** | Basin / Stream Network Features | 2 Basins, 2 Rivers in DB | Static | `REFERENCE` | **100% NULL geometry** | Zero | `BLOCKED` | Ingest CWC/WRIS river centerlines and basin polygons |

---

## 13. Blocked Items

The following items are definitively **BLOCKED** and must not be used for ML feature engineering until their specific prerequisites are met:

1. **Target B (Flood Affected Area):** Blocked because multi-district aggregate damage cannot be heuristically attributed to individual districts without violating `CONSTRAINTS.md`.
2. **Target C (Spatial Inundation Extent):** Blocked because high-resolution satellite SAR inundation ground truth is completely unavailable in the repository.
3. **Target D (River Gauge Exceedance):** Blocked pending authoritative CWC Warning Level and Danger Level metadata.
4. **Target E (Flood Severity Category):** Blocked due to qualitative reporting inconsistency in historical records.
5. **Reservoir Release Features:** Blocked because current reservoir telemetry is completely unpopulated (data is 18 years old).
6. **River Discharge Features:** Blocked because `river_observations.discharge` is 100% NULL.
7. **Hydrological Distance Metrics:** Blocked because river centerlines and basin boundaries have `geometry IS NULL`.
8. **Fine-Grained Grid-Cell Modeling (0.05°):** Blocked because assigning coarse district disaster labels to individual grid cells creates severe label noise.

---

## 14. Required Real Data Before Model Training

Before Phase 4 (Model Development & Training) can be initiated, the following **real datasets** must be ingested into the FloodPulse database:

1. **Historical Atmospheric Reanalysis (ERA5):**
   - Ingest continuous daily precipitation, temperature, humidity, and pressure across all 31 Karnataka districts for the selected historical event window (e.g. 2000–2023 or 1969–1994).
   - This is the primary blocker: without it, zero temporal overlap exists with historical flood labels.
2. **Full Audited IFI Archive (1969–2023):**
   - Ingest the remaining audited IFI v3.0 records (bringing total district observations from 186 to 1,271) to maximize positive training samples.
3. **Zonal Terrain Statistics:**
   - Ingest Copernicus DEM GLO-30 raster and compute mean elevation, standard deviation of elevation, and mean slope for each of the 31 KSR-SAC district polygons.
4. **Statutory River Gauge Thresholds:**
   - Acquire and populate official CWC Warning Levels, Danger Levels, and Highest Flood Levels for Karnataka river stations.

---

## 15. Phase 3.7 Prerequisites

Phase 3.7 (Historical Reanalysis Backfill & Feature Store Construction) requires:
1. Approval of the **District** unit of analysis and **Target A** formulation.
2. Approval of the **Three-State Labelling Contract** (`POSITIVE`, `NEGATIVE`, `UNLABELLED`).
3. Selection of the primary historical training window (e.g. 2000–2023 vs. 1969–1994).
4. Automated verification that the feature store pipeline enforces the `TemporalWindowConfig` leakage guards defined in `backend/app/ml/contracts.py`.

---
*Document formulated strictly under zero-mutation, zero-synthetic, and read-only scientific integrity constraints.*
