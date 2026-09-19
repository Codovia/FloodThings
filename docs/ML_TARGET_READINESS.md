# ML_TARGET_READINESS.md — Historical Flood Target Readiness Audit

**Project:** FloodPulse<br>
**Phase:** Phase 2.8 — Historical Flood Target Readiness Audit<br>
**Status:** COMPLETE (Audit & Design Only — No ML models trained, no labels generated)<br>
**Date:** 2026-09-19

---

## 1. Executive Conclusion

This audit evaluates whether the currently available real historical flood evidence in the FloodPulse repository and verified external data sources is sufficient to define a scientifically defensible machine learning (ML) prediction target.

### Strict Categorical Classification

* **[VERIFIED FACT]**: The India Flood Inventory (IFI v3.0) provides **493 valid disaster events** and **1,271 district-level historical flood observations** across Karnataka spanning **1969-07-14 to 2023-07-24**.
* **[VERIFIED FACT]**: IFI historical flood evidence is **strictly district-level**. Coordinate geometries, flood polygons, flood depth measurements, and source confidence scores are **completely absent** (`NULL`).
* **[VERIFIED FACT]**: The current PostgreSQL database stores an initial sample tranche (100 events / 186 observations from Phase 2.4) spanning **1969 to 1994**, and **does not yet contain the complete audited IFI archive** (1969–2023).
* **[VERIFIED FACT]**: The current database contains weather observations spanning **2024 to 2026**, resulting in **zero temporal overlap** between weather and flood observations in PostgreSQL today.
* **[VERIFIED FACT]**: CWC river stage telemetry provides physical water levels in metres, but **official Warning Level (WL) and Danger Level (DL) thresholds are absent** from the telemetry data.
* **[VERIFIED FACT]**: GloFAS discharge from Open-Meteo is `MODEL_OUTPUT`, not physical ground truth.
* **[VERIFIED FACT]**: KSR-SAC State, District (31), and Taluk (240) source acquisition, CRS transformation, and topological validation are **COMPLETE** (`KsrsacAdminNormalizer`). Normalized geometry exists outside the application database; loading into PostGIS tables is scheduled for Phase 3.
* **[UNAVAILABLE]**: High-resolution spatial flood inundation footprints (satellite SAR inundation polygons, depth rasters, or grid-cell inundation) are currently **completely unavailable** from open machine-readable sources for Karnataka.
* **[UNAVAILABLE]**: Explicit non-flood negative observations are **completely unavailable**; IFI is a positive-only disaster damage catalog.
* **[ASSUMPTION]**: Treating calendar days without an IFI record as "negative" flood days assumes 100% reporting completeness across 55 years, which is historically false.
* **[INFERENCE]**: Training a fine-grained grid-cell ML model (e.g. 0.05° or 0.1°) from IFI evidence would require assigning coarse district disaster labels to individual grid cells or centroids, creating massive spatial false-positive noise and violating `CONSTRAINTS.md`.
* **[BLOCKER]**: **ML training is currently BLOCKED.** No ML model can be defensibly trained until:
  1. An explicit three-state labelling policy (`POSITIVE`, `NEGATIVE`, `UNLABELLED`) and negative-sampling strategy are established.
  2. Historical weather reanalysis (ERA5) is ingested across an empirically selected historical event window.
  3. Administrative GIS boundaries (KSR-SAC) are loaded into PostGIS tables (`districts.geometry`).

---

## 2. Verified Historical Sources

The following historical sources were empirically verified during Phase 2.3 and Phase 2.7:

| Source | Category | Format | Spatial Resolution | Temporal Coverage | Legitimate ML Target? | Current Local Availability |
|---|---|---|---|---|---|---|
| **India Flood Inventory (IFI v3.0)** | `HISTORICAL_EVENT` | CSV | District level (31 KSR-SAC districts) | 1969–2023 (55 years, 493 events) | **CONDITIONALLY VIABLE (District occurrence only)** | Full raw archive present (`data/raw/ifi/`) |
| **Open-Meteo Weather Archive (ERA5)** | `REANALYSIS` | JSON | 0.1° grid (~11 km) | 1940–present (Hourly/Daily) | **NO (Environmental driver/feature)** | Verified API; historical tranche not yet ingested into DB |
| **Open-Meteo Flood API (GloFAS)** | `MODEL_OUTPUT` | JSON | 0.05° grid (~5 km river network) | 1979–present (Daily) | **NO (Model output cannot serve as ground truth)** | Verified API; not ingested |
| **NWIC CWC River Water Levels** | `OBSERVATION` | CSV | Point gauge stations (Cauvery, Krishna, Godavari) | 1961–2026 (Hourly stage in metres) | **BLOCKED PENDING AUTHORITATIVE WARNING/DANGER LEVEL METADATA** | Current tranche (2026+) in `data/raw/cwc/` |
| **NWIC Karnataka Reservoir Telemetry** | `OBSERVATION` | CSV | Point dam stations (14+ major dams) | 1990–2026 (Daily level/storage/flow) | **NO (Upstream hydrological control/driver)** | Full historical archive present (`data/raw/nwic/`) |
| **Copernicus DEM GLO-30** | `OBSERVATION` | COG (GeoTIFF) | 1 arc-second (~30 m raster) | Static baseline (2011–2015) | **NO (Static terrain feature)** | Range-read verified; not yet ingested into DB |
| **KSR-SAC Admin Boundaries** | `REFERENCE` | Shapefile | 1 State, 31 Districts, 240 Taluks | Static baseline (Current 2026) | **NO (Spatial join & aggregation framework)** | Local verified shapefiles (`data/raw/gis/ksrsac/`); normalized in-memory |

---

## 3. Current IFI Evidence Characteristics

### Raw Archive vs. Database State

It is essential to distinguish the two states of the historical evidence pipeline:
1. **Full Audited Raw IFI Archive (`data/raw/ifi/`)**:
   - Contains **6,876 raw records**, yielding **494 Karnataka events**, **493 valid events** (1 rejected: `UEI-IMD-FL-2001-0043` with empty timestamp), and **1,271 normalized district observations** spanning **1969-07-14 to 2023-07-24** across 30 districts.
2. **Current PostgreSQL Database (`flood_events`, `flood_observations`)**:
   - Contains **100 sample events** and **186 observations** spanning **1969 to 1994**, seeded as an initial verification tranche during Phase 2.4.
   - The application database does **not yet contain the complete audited IFI archive**. Loading the remaining audited observations is an ingestion task, not a data limitation.

### Detailed Evidence Metrics

* **Resolution Breakdown (Full Archive)**:
  * `DIRECT_LGD`: 1,104 raw $\to$ 5 duplicate observations skipped $\to$ **1,099** normalized observations.
  * `VERIFIED_ALIAS`: 142 raw $\to$ 2 duplicate observations skipped $\to$ **140** normalized observations.
  * `BIJAPUR_CORRECTION`: 32 raw $\to$ 0 duplicate observations skipped $\to$ **32** normalized observations.
  * *Reconciliation Invariant*: $1,099 + 140 + 32 = \mathbf{1,271}$.
* **Spatial Resolution**: Coarse administrative district level. Exactly 30 districts have evidence; Vijayanagara (KGIS 31, LGD 738) has **zero** matching observations.
* **Geometry Availability**: **EXPLICITLY UNAVAILABLE (`NULL`)**. No polygons, lines, or points exist in IFI v3.
* **Flood Depth Availability**: **EXPLICITLY UNAVAILABLE (`NULL`)**.
* **Source Confidence Availability**: **EXPLICITLY UNAVAILABLE (`NULL`)**. (Mapping certainty is tracked separately as `mapping_status="DETERMINISTIC"`).
* **Temporal Distribution by Decade**:
  * 1969–1979: 10 events, 11 observations (5 zero-record years: 1970, 1971, 1973, 1976, 1977).
  * 1980–1989: 16 events, 23 observations.
  * 1990–1999: 50 events, 78 observations.
  * 2000–2009: 93 events, 258 observations.
  * 2010–2019: 198 events, 532 observations.
  * 2020–2023: 126 events, 369 observations.
  * *Finding*: Event reporting frequency increases dramatically in recent decades (2000–2023 accounts for 417 of 493 events, or 84.6% of events, and 1,159 of 1,271 observations, or 91.2%).
* **Unresolved Evidence**: Exactly 31 occurrences across 18 distinct strings (13 OCR concatenations, 2 taluk-level tokens, 1 locality token, 2 non-district descriptors, 1 ambiguous token, 2 unmapped/corrupted strings).

---

## 4. Candidate Target Definitions

We investigate four candidate ML target definitions against project constraints:

### Candidate A: District Historical Flood Occurrence (Binary Classification)

* **Definition**: $Y_{d, t} \in \{0, 1\}$, where $Y=1$ indicates district $d$ experienced a documented flood disaster on calendar day $t$.
* **Label Source**: IFI v3.0 normalized observations (`flood_observations.flooded = True`).
* **Spatial Unit**: Administrative District (31 KSR-SAC districts).
* **Temporal Unit**: Calendar Day ($t \in \text{YYYY-MM-DD}$).
* **Prediction Horizon**: 24h, 48h, 72h forward using numerical weather prediction (NWP) precipitation forecasts.
* **Status**: **CONDITIONALLY VIABLE**.
* **Conditions for Viability**:
  District-level IFI historical occurrence can potentially become an operational prediction target ONLY after resolving:
  1. **Explicit Positive / Negative / Unlabelled Semantics**: Establishing a defensible classification policy (see Section 8).
  2. **Historical Feature Alignment**: Ingesting corresponding historical weather reanalysis (ERA5) for the selected event window.
  3. **Negative-Sampling Policy**: Formalizing an audited protocol for identifying true negative days without assuming zero reporting bias.
  4. **Rigorous Temporal Validation**: Implementing forward-in-time chronological holdout splitting.
  5. **Strict Feature Leakage Controls**: Eliminating post-disaster summary metrics from feature sets.
  *Note*: An ML target is **not currently approved**.
* **Strengths**: Grounded in real, authoritative government damage evidence; aligns directly with KSR-SAC 31-district administrative boundaries.
* **Limitations**: Coarse spatial resolution (flags entire 5,000–10,000 km² district); severe class imbalance (<0.5% positive days); positive-only reporting.

### Candidate B: District Affected Area / Severity (Regression / Multi-Class)

* **Definition**: Continuous affected area ($km^2$) or categorical severity (Class 1, 2, 3).
* **Label Source**: IFI v3 `Area Affected`, `Severity`.
* **Limitations**: `Area Affected` is recorded at the multi-district event level, not per district. For an event affecting 5 districts with 1,000 km² total, attributing area to individual districts requires arbitrary heuristics. Severity classifications in IFI are qualitative and inconsistently populated.
* **Verdict**: **UNVIABLE**. Violates `CONSTRAINTS.md` (heuristic data attribution).

### Candidate C: Grid-Cell Inundation Occurrence (Fine-Grained Spatial Binary)

* **Definition**: $Y_{g, t} \in \{0, 1\}$ for a 0.05° (~5 km) or 0.1° (~11 km) grid cell $g$.
* **Label Source**: UNAVAILABLE. IFI has no coordinate geometry.
* **Limitations**: High-resolution flood inundation ground truth (e.g. satellite SAR water masks from Sentinel-1 or NRSC NDEM) is not currently available in open machine-readable format. Assigning district-level IFI events to grid cells would require assigning the event to all cells (massive false positives) or assigning to centroids (fabricating coordinates).
* **Verdict**: **COMPLETELY BLOCKED**. Violates `CONSTRAINTS.md` (zero synthetic geometry).

### Candidate D: River Gauge Flood-Stage Exceedance (Hydrological Point Binary)

* **Definition**: $Y_{s, t} = \mathbb{I}(\text{Water Level}_{s, t} \ge \text{Danger Level}_s)$ for gauge station $s$.
* **Label Source**: NWIC CWC river telemetry.
* **Status**: **BLOCKED PENDING AUTHORITATIVE WARNING/DANGER LEVEL METADATA**.
* **Explanation**: The CWC telemetry dataset provides hourly stage in metres, but **omits official Danger Level (DL) and Warning Level (WL) metadata**. Defining an exceedance threshold without statutory CWC benchmarks requires arbitrary thresholding, violating `CONSTRAINTS.md`. This candidate is **not permanently rejected**; if authoritative DL/WL metadata are acquired, stage exceedance can be re-evaluated as a localized hydrological point target.

---

## 5. Spatial Readiness

1. **Administrative Geometry**:
   * KSR-SAC shapefiles (`State.shp`, `District.shp`, `Taluk.shp`) are verified, CRS-transformed (EPSG:32643 $\to$ EPSG:4326), and normalized in memory via `KsrsacAdminNormalizer` (Phase 2.6).
   * **Database Status**: The PostgreSQL `districts` table currently contains 31 metadata rows, but `geometry` is `NULL`.
   * **Clarification**: Source acquisition and validation are complete. Loading normalized polygons into PostGIS is an **implementation task for Phase 3**, not a source acquisition blocker.
2. **Hydrological Geometry**:
   * `rivers`, `river_stations`, and `water_bodies` tables exist in PostgreSQL, but contain only sample seed rows (2 rivers, 1 station, 0 water bodies).
3. **Historical Flood Geometry**:
   * **Zero** historical flood geometry exists. IFI v3.0 contains no coordinates, bounding boxes, or polygons.
4. **Prediction Grid Justification**:
   * The `prediction_grid_cells` table exists in PostgreSQL schema (Phase 2.2), but is currently empty.
   * **Scientific Finding**: Creating a fine regular prediction grid (e.g., 0.05° or 0.1°) for ML training is **currently unjustified** because there are no grid-level ground truth target labels. Training a grid-level model on district-level labels would create severe spatial label noise.

---

## 6. Temporal Readiness

1. **Historical Weather Window Selection**:
   * The historical weather ingestion window must be selected after computing the actual IFI event-date distribution and feature availability, rather than assuming an arbitrary cutoff.
   * As documented in Section 3, 84.6% of IFI events and 91.2% of district observations occur between 2000 and 2023. Selecting an ingestion window (e.g. 2000–2023 or 2005–2023) must balance historical sample depth against API quota limits and data acquisition costs.
2. **Feature-Target Overlap in Database**:
   * **Current State**: The PostgreSQL database currently stores weather observations for 2024–2026 and historical flood observations for 1969–1994. There is **0% temporal overlap** in the database today.
   * **Prerequisite**: A batch historical weather ingestion job (using Open-Meteo ERA5 reanalysis across the selected historical window) must be executed before feature snapshots can be constructed.
3. **Temporal Validation Strategy**:
   * Random train/test splits are strictly forbidden for time-series flood prediction (`CONSTRAINTS.md`).
   * **Forward-in-Time Holdout Split**:
     * Strict chronological splitting (e.g. training on earlier years, evaluating on later holdout years) is required to preserve causal temporal ordering and prevent multi-day event leakage.

---

## 7. Leakage Risks & Mandatory Controls

If an ML target and feature pipeline are developed in Phase 4, the following leakage vectors must be strictly controlled:

1. **Future Rainfall Leakage**:
   * Rolling precipitation features (e.g. 1h, 3h, 6h, 12h, 24h, 72h, 7d sums) must strictly compute over $[T_0 - \Delta t, T_0]$.
   * Any forward forecast precipitation features ($T_0$ to $T_0 + 72\text{h}$) must come exclusively from weather forecasts generated at or before $T_0$.
2. **Disaster Metadata Leakage**:
   * IFI event records include post-disaster summary metrics: `Duration(Days)`, `End Date`, `Human fatality`, `Human Displaced`, `Area Affected`.
   * **Mandatory Control**: These fields must **never** be used as feature inputs. They are post-event consequences, not pre-event predictors.
3. **Telemetry Latency & Staleness**:
   * CWC river stage and NWIC reservoir telemetry are reported with reporting lags (hours to days).
   * Features at prediction time $T_0$ must only access telemetry with `observed_at <= T_0`.
4. **Administrative Boundary Evolution**:
   * Karnataka's district boundaries changed during the historical period:
     * Vijayanagara (KGIS 31, LGD 738) was established in late 2021 from Ballari.
     * Yadgir (KGIS 30, LGD 637) was established in 2010 from Kalaburagi.
     * Chikkaballapura (KGIS 28) and Ramanagara (KGIS 29) were established in 2007.
   * **Mandatory Control**: Weather and terrain features must be aggregated to the consistent, authoritative 31 KSR-SAC district boundaries. For pre-bifurcation historical records, target mapping must account for parent-child relationships without duplicating counts.
5. **Autoregressive / Multi-Day Event Autocorrelation**:
   * A severe flood event often lasts 3 to 10 days, generating positive observations across consecutive days.
   * A random split would place Day 1 in Train and Day 2 in Test, causing catastrophic data leakage.
   * **Mandatory Control**: Strict time-based holdout splitting.

---

## 8. Explicit Negative-Label & Missing-Data Semantics

Per `docs/CONSTRAINTS.md` and `docs/DATA_CONTRACT.md`:

### Three-State Labelling Contract

Because the India Flood Inventory is a positive-only disaster damage catalog, the ML target framework must enforce three distinct states:

1. **`POSITIVE`**:
   * Documented flood disaster evidence exists in the verified inventory for district $d$ on calendar day $t$.
2. **`NEGATIVE`**:
   * An independently defensible observation establishes the absence of the target condition (e.g. verified zero-damage/normal operational status under complete meteorological observation during active monitoring seasons).
3. **`UNLABELLED`**:
   * No sufficient evidence exists to determine flood vs. non-flood condition (e.g. unmonitored periods, historical reporting hiatuses, missing weather data, pre-monitoring decades).

### Critical Rule

> **"No IFI event" must NOT be converted directly into a negative label.**
>
> Assuming that absence of a recorded disaster in IFI equals zero flooding conflates "no disaster reported" with "no flood occurred". Rural, agricultural, or localized inundations that caused no reported casualties or major infrastructure damage were not recorded by IMD/CWC news bulletins. Automatically treating all unrecorded days as negative introduces massive label noise.

### Zero-Evidence Districts
* Vijayanagara (KGIS 31) has zero IFI records.
* **Policy**: Vijayanagara must remain explicitly zero in historical tables. Coverage must not be synthesized.

---

## 9. Recommended Next Steps

1. **Phase 3 — GIS Ingestion & Administrative Geography**:
   * Ingest normalized KSR-SAC State, 31 District, and 240 Taluk polygons into PostGIS tables (`states`, `districts`, `taluks`).
   * Compute authoritative zonal terrain statistics (elevation, slope) using Copernicus DEM GLO-30.
2. **Phase 3.5 — Historical Feature Ingestion**:
   * Compute the exact IFI event-date distribution and determine the optimal historical weather reanalysis ingestion window (Open-Meteo ERA5) to create temporal overlap with IFI evidence.
3. **Phase 4 — Feature Store & ML Dataset Formulation**:
   * Construct `FeatureSnapshot` records combining rolling antecedent rainfall, terrain slope, and reservoir storage at the District level.
   * Formulate versioned dataset (`MLDatasetVersion`) using Candidate A (District Historical Flood Occurrence) under the three-state labelling contract with strict chronological holdout splitting.

---

## 10. Explicit Blockers Before ML Training

The following items are **HARD BLOCKERS** that prevent ML training today:

| Blocker ID | Description | Resolution Required |
|---|---|---|
| **BLK-01** | **Zero Feature-Target Overlap in DB** | Weather observations in PostgreSQL cover 2024–2026; flood observations cover 1969–1994. Must ingest ERA5 historical weather reanalysis across an empirically selected historical event window. |
| **BLK-02** | **District Geometries Missing in PostGIS** | `districts.geometry` is currently `NULL` in PostgreSQL. Must execute Phase 3 GIS ingestion from normalized KSR-SAC shapefiles (implementation task; source data verified). |
| **BLK-03** | **No Negative-Sampling Implementation** | IFI is positive-only. An explicit three-state labelling protocol (`POSITIVE`, `NEGATIVE`, `UNLABELLED`) must be implemented before creating training labels. |
| **BLK-04** | **No Grid-Level Target Feasibility** | Fine-grained grid cell prediction ($0.05^\circ$) cannot be trained on coarse district labels without violating zero-fabrication rules. ML target must be formally constrained to the District level. |
| **BLK-05** | **Missing CWC Danger Levels** | River level exceedance cannot be used as an ML target without authoritative CWC Danger Level metadata (status: blocked pending metadata). |
