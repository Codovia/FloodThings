# IFI_LABEL_AUDIT.md — India Flood Inventory (IFI v3.0) Historical Flood Label Audit

**Project:** FloodPulse / FloodPrediction  
**Phase:** Phase 3.13 — Historical Flood Label Integration  
**Status:** COMPLETE & VERIFIED  
**Date:** 2026-09-24  
**Classification:** Technical Data Audit & Contract Specification  

---

## 1. Executive Summary

This audit establishes the authoritative, provenance-preserving historical flood label foundation for the State of Karnataka at the project's documented **District × Calendar Day** resolution. Ground truth labels are derived exclusively from the **India Flood Inventory (IFI v3.0)** co-developed by the HydroSenseLab (IIT Delhi) and the India Meteorological Department (IMD) / Ministry of Earth Sciences.

In accordance with `docs/MASTER_PROJECT_SPEC.md`, `docs/DATA_CONTRACT.md`, and `docs/DATA_SOURCES.md`:
1. **Zero Synthetic Data:** Every positive flood label traces directly to one or more verified IFI disaster event identifiers (`UEI`). Zero synthetic flood events, zero fabricated missing labels, zero invented flood dates.
2. **Three-State Labelling Contract:** Labels explicitly distinguish `FLOOD` (1), `NO_FLOOD` (0), and `UNKNOWN` (None). "No IFI record found" is never silently converted into `NO_FLOOD` unless an explicit, validated historical observation window is provided.
3. **Deterministic Overlap Consolidation:** Overlapping events affecting the same district on the same calendar day consolidate into a single row, aggregating all underlying UEIs into a sorted array and summing casualties and displaced persons.
4. **Date Anomaly Isolation:** Events with corrupted date logic (e.g. `Start Date > End Date`) are isolated in audit records without expanding inverted intervals.
5. **Authoritative Administrative Alignment:** Mapped exclusively to the 31 canonical KSR-SAC Karnataka administrative districts (`01` through `31`).

---

## 2. Dataset Classification & Verification Matrix

The audit classifies all IFI v3.0 dataset attributes and integration dimensions into four explicit categories:

### 2.1 VERIFIED
* **Source Authenticity & Provenance:**
  * Dataset: India Flood Inventory (IFI v3.0).
  * Publisher: HydroSenseLab, Department of Civil Engineering, IIT Delhi (PI: Dr. Manabendra Saharia) & India Meteorological Department (IMD).
  * Reference / DOI: Zenodo `10.5281/zenodo.10892285`.
  * Preserved Raw Archive: `data/raw/ifi/ifi_v3_karnataka_20260917_164914.csv` (MD5: `fea75a9ff9eba8fb328eaddfacd21d67`, 1,852,787 bytes).
* **Scope & State Filtering:**
  * Total national records: 6,876.
  * Karnataka state records (`State_Codes == 29`): 494.
  * Validated event records: 493 (1 rejected for empty start date).
* **Administrative Resolution & Coverage:**
  * District normalization: 1,299 out of 1,344 raw district tokens (96.65%) successfully resolved against canonical KSR-SAC boundaries.
  * 1,099 tokens resolved via direct statutory LGD codes (81.77%).
  * 200 tokens resolved via canonical name matching and verified historical aliases (14.88%).
  * 482 of 493 valid events (97.77%) successfully resolve to at least one canonical Karnataka district.
  * 30 Karnataka districts have positive flood occurrence evidence across the 54-year span.
  * Vijayanagara (`31`, LGD `738`, created 2021 from Ballari) has strictly 0 direct historical IFI records (all pre-2021 events were indexed under Ballari `528`).
* **Temporal Resolution & Spans:**
  * Continuous verified historical span: 1969-07-14 to 2023-07-24 (54 continuous years).
  * Timestamp alignment: Nominal `DD-MM-YYYY 00:00` IST converted to UTC `YYYY-MM-DD`, aligning directly with ERA5 daily aggregations (00:00–23:00 UTC).
* **Consolidation Output:**
  * 482 expanded events expand to 43,022 unconsolidated district-day occurrences.
  * Deterministic overlap consolidation produces exactly **17,501 unique positive District × Day labels**.

### 2.2 PARTIALLY VERIFIED
* **Event Damage & Impact Statistics:**
  * Human Fatalities: Available in 118 events (summing to 1,514 fatalities across Karnataka history); NULL/zero in remaining records.
  * Human Displacements: Available in 47 events (summing to 431,200 displaced persons); NULL/zero in remaining records.
  * Extent of Damage & Affected Area: Available in textual and approximate numeric form (`Area Affected`), but reporting completeness varies across historical decades (higher reporting fidelity post-2000).
* **Main Cause Attribution:**
  * Available for 481 of 493 events. Top causes: "Heavy Rain" (382 events), "Floods" (42), "Monsoon Flood" (28), "Dam Breach" (11), "Cyclonic Storm" (18).

### 2.3 UNAVAILABLE
* **Sub-District / Taluk Polygon Inundation:**
  * IFI v3.0 does not contain taluk-level or village-level inundation boundaries.
  * Point coordinates (`Latitude`, `Longitude` columns) are mostly NULL or represent coarse district centroids; they are NOT suitable for sub-district spatial overlay.
* **Continuous Flood Depth & Hydrographs:**
  * IFI v3.0 records categorical severity (`Class 1`, `Class 2`, `Class 3`) and qualitative damage, but does NOT contain continuous inundation depth (metres) or river discharge ($m^3/s$).
* **Pre-1969 Disaster Events:**
  * Historical disaster catalog begins on 1969-07-14; no validated records exist prior to this date.

### 2.4 REQUIRES MANUAL REVIEW
* **Date Anomaly Record (1 event):**
  * `UEI-IMD-FL-2018-0027`: `Start Date = 06-12-2018 00:00`, `End Date = 14-06-2018 00:00`, `Duration = 3 days`, affected district: Chikkamagaluru (`532`).
  * Root Cause: OCR digit transposition in source catalog (start date month and day inverted from `12-06-2018` to `06-12-2018`).
  * Pipeline Handling: Flagged and isolated in `date_anomalies` audit trail; excluded from interval expansion to prevent inverted date range fabrication.
* **Unresolved / Out-of-State Tokens (10 events):**
  * Corrupted OCR tokens: `10-10-1975`, `12-10-1975`, `Kasaragod` (Kerala district adjacent to Dakshina Kannada), `Sangli` (Maharashtra district adjacent to Belagavi), `Parts of Karnataka` (generic regional descriptor with no specific district).
  * Pipeline Handling: Unmapped tokens are discarded; events with zero resolvable districts are isolated in `unresolved_events_count` (10 events).

---

## 3. Source Schema & Raw Column Inventory

The preserved raw archive contains 23 RFC 4180 CSV columns:

| Column Name | Data Type | Description | Completeness (Karnataka) |
|---|---|---|---|
| `Unnamed: 0` | Integer | Source row index | 100% |
| `UEI` | String | Unique Event Identifier (`UEI-IMD-FL-YYYY-NNNN`) | 100% |
| `Start Date` | String | Initial event date (`DD-MM-YYYY 00:00`) | 99.8% (1 missing) |
| `End Date` | String | Termination event date (`DD-MM-YYYY 00:00`) | 98.6% (7 missing) |
| `Duration(Days)` | Integer | Reported event duration in days | 99.2% |
| `Main Cause` | String | Meteorological or anthropogenic trigger | 97.6% |
| `Location` | String | Local place names / landmarks | 12.4% (sparse) |
| `Districts` | String | Comma-separated list of affected district names | 99.6% |
| `State` | String | State name ('Karnataka') | 100% |
| `Latitude` | Float | Approximate centroid latitude | 8.2% (unreliable) |
| `Longitude` | Float | Approximate centroid longitude | 8.2% (unreliable) |
| `Severity` | String | Classified severity ('Class 1', 'Class 2', 'Class 3') | 98.4% |
| `Area Affected` | Float | Reported impacted area ($km^2$) | 24.1% |
| `Human fatality` | Integer | Verified fatalities attributable to event | 23.9% |
| `Human injured` | Integer | Verified injuries attributable to event | 4.2% |
| `Human Displaced`| Integer | Evacuated / displaced individuals | 9.5% |
| `Animal Fatality`| Integer | Livestock mortality | 11.2% |
| `Description of Casualties/injured` | String | Qualitative casualty details | 18.6% |
| `Extent of damage ` | String | Textual damage summary | 45.2% |
| `Event Source` | String | Upstream reporting authority (mostly 'IMD') | 100% |
| `Event Souce ID` | String | Upstream disaster catalog identifier | 99.4% |
| `District_LGD_Codes` | String | Comma-separated Local Government Directory codes | 97.8% |
| `State_Codes` | Integer | Statutory state code (`29` for Karnataka) | 100% |

---

## 4. Geographic Normalization & District Mapping Analysis

District mapping is performed by `IfiEventNormalizer` using a strict two-pass resolution hierarchy against the 31 canonical KSR-SAC administrative districts:

1. **Pass 1 — Statutory LGD Code Resolution:**
   Raw string in `District_LGD_Codes` is parsed. Each numeric token is looked up in the canonical KSR-SAC dictionary.
2. **Pass 2 — Canonical Name & Historical Alias Resolution:**
   Tokens in `Districts` string that were unmapped in Pass 1 are normalized (casefold, whitespace stripped, non-alphanumeric removed) and matched against the project's authoritative alias dictionary:
   * `Bijapur` $\to$ Vijayapura (`03`, LGD `530`)
   * `Belgaum` $\to$ Belagavi (`01`, LGD `527`)
   * `Gulbarga` $\to$ Kalaburagi (`04`, LGD `538`)
   * `Bellary` $\to$ Ballari (`12`, LGD `528`)
   * `Shimoga` $\to$ Shivamogga (`16`, LGD `547`)
   * `Chikmagalur` / `Chikkamagaluru` $\to$ Chikkamagaluru (`18`, LGD `532`)
   * `Mysore` $\to$ Mysuru (`26`, LGD `545`)
   * `Coorg` $\to$ Kodagu (`25`, LGD `541`)
   * `Bangalore` / `Bangalore Urban` $\to$ Bengaluru Urban (`20`, LGD `525`)
   * `Bangalore Rural` $\to$ Bengaluru Rural (`21`, LGD `526`)
   * `Mangalore` / `South Canara` $\to$ Dakshina Kannada (`24`, LGD `534`)
   * `North Canara` / `Karwar` $\to$ Uttara Kannada (`10`, LGD `550`)

### 4.1 Normalization Audit Results
* Total raw district tokens evaluated: **1,344**
* Successfully resolved tokens: **1,299 (96.65%)**
  * Direct LGD code matches: 1,099 (81.77%)
  * Canonical name / alias matches: 200 (14.88%)
* Discarded unmapped tokens: **38 (2.83%)**
* Filtered out-of-state tokens: **7 (0.52%)**
* Unresolvable events: **10 events (2.03%)**

---

## 5. Temporal Normalization & Daily Interval Expansion

Historical IFI event timestamps specify start and end dates with nominal midnight strings (`DD-MM-YYYY 00:00` Indian Standard Time, UTC+05:30).

### 5.1 Timezone Conversion & Reanalysis Alignment
* `00:00 IST` corresponds to `18:30 UTC` of the *previous* calendar day.
* In accordance with `IfiEventNormalizer`, timestamps are converted to UTC datetime.
* Daily interval expansion computes inclusive calendar dates in UTC:
  $$\text{dates} = \{ \text{start\_utc.date} + k \cdot \text{1 day} \mid 0 \le k \le (\text{end\_utc.date} - \text{start\_utc.date}) \}$$
* This matches the daily temporal boundaries of ERA5 reanalysis data, which aggregates hourly fields from 00:00 to 23:00 UTC.

### 5.2 Single-Day and Multi-Day Event Rules
* **Single-Day Events:** When `End Date` is identical to `Start Date` or missing, exactly 1 calendar day is generated.
* **Multi-Day Events:** When `End Date > Start Date`, each intermediate day is expanded inclusively.
* **Duration Reconciliation:** If `Duration(Days)` is provided and differs from interval length, the date interval takes precedence unless end date is missing, in which case duration is used to compute end date.
* **Date Anomaly Rule:** If `Start Date > End Date`, the event is classified as anomalous, isolated in audit, and NOT expanded.

---

## 6. Overlap Consolidation & Multi-Event Reconciliation

Disaster catalogs frequently log multiple independent flood reports for the same district during a single regional monsoon surge.

### 6.1 Consolidation Methodology
When multiple IFI events produce occurrences for the same `(kgis_district_code, date)`:
1. `flood_occurrence` is set to `1` (`FLOOD`).
2. `event_count` reflects the exact number of distinct overlapping disaster events.
3. `source_event_ids` aggregates all unique `UEI` strings in sorted alphanumeric order.
4. `main_causes` aggregates all unique triggering causes in sorted order.
5. `severities` aggregates all distinct reported severity classes in sorted order.
6. `fatalities` is the sum of all reported human fatalities (or NULL if all underlying records are NULL).
7. `displaced` is the sum of all reported displacements (or NULL if all underlying records are NULL).

### 6.2 Empirical Overlap Distribution in Karnataka
Across the 43,022 unconsolidated occurrences:
* **1 Event:** 10,090 district-days (57.65%)
* **2 Events:** 1,375 district-days (7.86%)
* **3 Events:** 1,290 district-days (7.37%)
* **4 Events:** 1,080 district-days (6.17%)
* **5 Events:** 1,236 district-days (7.06%)
* **6 Events:** 1,198 district-days (6.85%)
* **7 Events:** 1,232 district-days (7.04%)
* **Total Unique Consolidated Labels:** **17,501**
* Mathematical Invariant Check:
  $$\sum_{k=1}^{7} k \cdot N_k = 10,090 + 2,750 + 3,870 + 4,320 + 6,180 + 7,188 + 8,624 = 43,022 \quad \text{[VERIFIED]}$$

---

## 7. Three-State Labelling Contract

The ML target is defined as:
$$\text{Target A: District-level daily flood occurrence} \in \{\text{FLOOD}, \text{NO\_FLOOD}, \text{UNKNOWN}\}$$

In accordance with strict ML data integrity guidelines:
* **`FLOOD` (1):** Supported by positive disaster catalog evidence tracing directly to IFI UEI records.
* **`NO_FLOOD` (0):** Explicit absence of flood evidence *within a verified observation window* (1969-07-14 to 2023-07-24).
* **`UNKNOWN` (NULL):** Dates outside the verified archive or unmonitored baseline periods.
* **Default Pipeline Mode:** Generates exclusively evidenced positive days (`FLOOD`, 17,501 records). Negative labels are strictly rejected unless an explicit observation window within valid historical bounds is passed.

---

## 8. Database Architecture & Alembic Migration

### 8.1 Schema Definition (`district_day_flood_labels`)

| Column Name | SQL Type | Nullable | Description / Constraints |
|---|---|---|---|
| `id` | UUID | NO | Primary key (`gen_random_uuid()`) |
| `district_id` | UUID | NO | FK to `districts.id` |
| `event_date` | DATE | NO | Target calendar date (UTC) |
| `label` | VARCHAR(20) | NO | `'FLOOD'`, `'NO_FLOOD'`, or `'UNKNOWN'` |
| `flood_occurrence`| SMALLINT | YES | `1` for FLOOD, `0` for NO_FLOOD, `NULL` for UNKNOWN |
| `event_count` | INTEGER | NO | Number of consolidated IFI events ($\ge 0$) |
| `source_event_ids`| JSONB | NO | Array of source IFI UEIs (`['UEI-...']`) |
| `main_causes` | JSONB | YES | Array of causes (`['Heavy Rain', ...]`) |
| `severities` | JSONB | YES | Array of severity ratings (`['Class 2', ...]`) |
| `fatalities` | INTEGER | YES | Cumulative fatalities ($\ge 0$) |
| `displaced` | INTEGER | YES | Cumulative displaced persons ($\ge 0$) |
| `source_id` | UUID | YES | FK to `data_sources.id` |
| `data_category` | VARCHAR(30) | NO | `'HISTORICAL_EVENT'` |
| `quality_status` | VARCHAR(20) | NO | `'VALID'` |
| `mapping_status` | VARCHAR(30) | NO | `'MAPPED'` |
| `processing_version`| VARCHAR(20)| NO | `'3.13.0'` |
| `created_at` | TIMESTAMPTZ | NO | Record creation timestamp (`now()`) |
| `updated_at` | TIMESTAMPTZ | NO | Record update timestamp (`now()`) |

### 8.2 Constraints & Indexes
* `uq_district_day_flood_labels`: `UNIQUE (district_id, event_date)`
* `ck_district_day_label_val`: `CHECK (label IN ('FLOOD', 'NO_FLOOD', 'UNKNOWN'))`
* `ck_district_day_flood_occ`: `CHECK (flood_occurrence IS NULL OR flood_occurrence IN (0, 1))`
* `ck_district_day_event_count`: `CHECK (event_count >= 0)`
* `ck_district_day_fatalities`: `CHECK (fatalities IS NULL OR fatalities >= 0)`
* `ck_district_day_displaced`: `CHECK (displaced IS NULL OR displaced >= 0)`
* Indexes:
  * `ix_district_day_labels_district_id` on `district_id`
  * `ix_district_day_labels_event_date` on `event_date`
  * `ix_district_day_labels_label` on `label`

### 8.3 Migration Metadata
* **Alembic Revision ID:** `4b8c3d2e1f0a`
* **Down Revision:** `3a7b2c1d4e5f`
* **Migration File:** `backend/migrations/versions/4b8c3d2e1f0a_add_district_day_flood_labels.py`
* **Status:** Applied and verified clean with `alembic check`.

---

## 9. Downstream ML Feature Matrix Join Contract

The historical flood label dataset provides the ground-truth prediction target for Phase 4 ML training.

### 9.1 Join Keys
* **Spatial Key:** `district_id` (UUID) $\leftrightarrow$ `districts.id` / `kgis_district_code` (`'01'` to `'31'`).
* **Temporal Key:** `event_date` (Date, UTC) $\leftrightarrow$ `observation_date` (Date, UTC).

### 9.2 Deterministic Join Graph

```
[district_day_flood_labels] (Target: label, flood_occurrence, event_count)
         │
         ├── JOIN on (district_id, date) ──► [ERA5 Daily Weather Features]
         │                                   (tp_sum, 2t_mean, 2t_max, 2d_mean, sp_mean,
         │                                    wind_speed_mean, rolling_precip_3d/7d/14d)
         │
         ├── JOIN on (district_id)        ──► [District Terrain Statistics]
         │                                   (elevation_mean, elevation_std, slope_mean,
         │                                    slope_max, valid_pixel_count)
         │
         └── JOIN on (district_id)        ──► [Hydrological Basins / Stations]
                                             (upstream_catchment_area, station_count)
```

---

## 10. Audit Sign-Off & Verification Verdict

| Audit Dimension | Result | Confidence |
|---|---|---|
| IFI Source Traceability | Verified real data (no synthetic records) | High (100%) |
| District Normalization | 1,299 / 1,344 tokens resolved (96.65%) | High (100%) |
| Temporal Discretization | 482 events $\to$ 17,501 consolidated district-days | High (100%) |
| Date Anomaly Isolation | 1 event isolated (`UEI-IMD-FL-2018-0027`) | Complete |
| Database Migration | Revision `4b8c3d2e1f0a` applied cleanly | Clean |
| Test Suite Status | 16/16 flood label tests passed (100%) | Clean |
| ERA5 Isolation Check | Raw ERA5 files & manifest strictly untouched | Verified |

**Final Recommendation:** PROCEED to Phase 4 (ML Feature Matrix Construction and Validation).
