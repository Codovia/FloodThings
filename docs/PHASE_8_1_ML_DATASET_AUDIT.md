# PHASE 8.1: ML DATASET RECONCILIATION & PRE-TRAINING AUDIT

**Project:** FloodPulse — Karnataka AI Flood Intelligence & Emergency Response System  
**Phase:** Phase 8.1 — ML Dataset Reconciliation & Pre-Training Audit  
**Date:** 2026-09-30  
**Status:** COMPLETE — READY FOR MODEL DESIGN  
**Audit Artifact:** `data/processed/ml_matrix/recent/ml_dataset_reconciliation_audit.json`  

---

## 1. Executive Summary & Objective

In accordance with Phase 8.1 directives, an exhaustive empirical reconciliation and pre-training audit of the machine learning datasets was conducted. The project operates under the strict non-negotiable principles:
- **DATA AVAILABLE** $\to$ IMPLEMENT
- **DATA DERIVABLE FROM VALID DATA** $\to$ IMPLEMENT + DOCUMENT
- **DATA UNAVAILABLE** $\to$ MARK UNAVAILABLE
- **DATA UNVERIFIED** $\to$ MARK UNVERIFIED
- **DATA WOULD HAVE TO BE INVENTED** $\to$ DO NOT IMPLEMENT

Zero models were trained, zero synthetic flood labels were manufactured, zero unrecorded observation days were converted to negative labels, and zero datasets were modified or overwritten.

---

## 2. Dataset Inventory & Schema Parity

Three core Parquet matrices exist on disk, serving distinct scientific roles:

| Dataset | File Path | Temporal Range | Grain | Rows | Cols | Positive Labels (FLOOD) | Negative Labels (NO_FLOOD) | Unknown Labels (UNKNOWN) | SHA-256 Digest | Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Recent Supervised Matrix** | `data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet` | 2011-01-01 $\to$ 2023-07-24 | District $\times$ Date | 142,228 | 57 | 13,156 (9.25%) | 0 (0.00%) | 129,072 (90.75%) | `d459e4461166842e194de8f8373f227585169f124cd620160a4aea74651e5dac` | **VALIDATED & READY** |
| **Recent Weather / Forward Matrix** | `data/processed/ml_matrix/recent/district_day_weather_matrix.parquet` | 2011-01-01 $\to$ 2025-12-31 | District $\times$ Date | 169,849 | 57 | 0 (0.00%) | 0 (0.00%) | 169,849 (100.0%) | `5e081561bb2e149b12321bb9d1f7caa6600f41a5af2e5c1ac3c2c59e99ba7ff8` | **VALIDATED (Operational Inference Test-Bed)** |
| **Historical Baseline Matrix** | `data/processed/ml_matrix/district_day_feature_matrix.parquet` | 1969-01-01 $\to$ 1994-12-31 | District $\times$ Date | 294,376 | 57 | 1,152 (0.39%) | 0 (0.00%) | 293,224 (99.61%) | `849f722b4f5f6a9ee85882abf787ae3d6ea5e0abdb563f499567ede738e06d55` | **VALIDATED (Independent Benchmark)** |

### Schema Parity
All three matrices possess **100% schema parity** across all 57 columns, sharing identical column names, ordering, and PyArrow data types.

---

## 3. ERA5 Recent Dataset Recalculation (2011–2025)

Every batch Parquet file in `data/processed/era5_daily/recent/` was independently read and verified:

| Verification Metric | Expected Value | Observed Value | Result |
| :--- | :---: | :---: | :---: |
| **Annual Chunks Evaluated** | 495 | 495 | **PASS** |
| **Calendar Days Span** | 5,479 days (2011-01-01 $\to$ 2025-12-31) | 5,479 days (2011-01-01 $\to$ 2025-12-31) | **PASS** |
| **Leap Days Present (Feb 29)** | 4 (2012, 2016, 2020, 2024) | 4 (2012, 2016, 2020, 2024) | **PASS** |
| **Unique ERA5 Grid Cells** | 318 cells | 318 cells | **PASS** |
| **Total Cell-Day Records** | 1,742,322 ($5,479 \times 318$) | 1,742,322 | **PASS** |
| **Complete Records (`quality_status = 'COMPLETE'`)** | 1,742,322 (100.0%) | 1,742,322 (100.0%) | **PASS** |
| **Duplicate Cell-Day Pairs** | 0 | 0 | **PASS** |
| **Missing Cell-Days** | 0 | 0 | **PASS** |
| **Null Meteorological Values** | 0 across all 6 core variables | 0 | **PASS** |

---

## 4. District-Day Weather Matrix Audit (2011–2025)

The district-level aggregation matrix `district_day_weather_matrix.parquet` was verified:
- **Spatial Coverage**: Exactly 31 Karnataka administrative districts (KGIS 01–31, LGD 524–738).
- **Temporal Coverage**: 5,479 calendar days ($31 \times 5,479 = 169,849$ rows).
- **Duplicates / Missing**: 0 duplicate `(district_id, target_date)` rows; 0 missing pairs.
- **Label State**: 100% `label_state == 'UNKNOWN'`, `flood_occurrence == None`. Zero synthetic labels.
- **Physical Plausibility**:
  - Precipitation: $\ge 0\text{ mm}$, peak daily mean $295.4\text{ mm}$.
  - Temperature: $0.1^\circ\text{C} \le T_{\min} \le T_{\text{mean}} \le T_{\max} \le 48.2^\circ\text{C}$.
  - Relative Humidity: $10.2\% \le RH \le 99.8\%$.
  - Surface Pressure: $850.1\text{ hPa} \le P \le 1025.4\text{ hPa}$.

---

## 5. Supervised Feature Matrix & Label Audit (2011–2023)

### Label Distribution Under Three-State Contract
- $Y = 1$ (`FLOOD`): **13,156** district-days (**9.2499%**).
- $Y = 0$ (`NO_FLOOD`): **0** district-days (**0.0000%**).
- $Y = \text{NULL}$ (`UNKNOWN`): **129,072** district-days (**90.7501%**).
- **Total Rows**: **142,228** ($4,588 \text{ calendar days} \times 31 \text{ districts}$).

### Annual Distribution
| Year | Calendar Days | Total District-Days | Documented Floods (Y=1) | Unknown Days (Y=NULL) | Positive Prevalence |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **2011** | 365 | 11,315 | 11 | 11,304 | 0.10% |
| **2012** | 366 | 11,346 | 7 | 11,339 | 0.06% |
| **2013** | 365 | 11,315 | 29 | 11,286 | 0.26% |
| **2014** | 365 | 11,315 | 161 | 11,154 | 1.42% |
| **2015** | 365 | 11,315 | 212 | 11,103 | 1.87% |
| **2016** | 366 | 11,346 | 67 | 11,279 | 0.59% |
| **2017** | 365 | 11,315 | 710 | 10,605 | 6.27% |
| **2018** | 365 | 11,315 | 2,315 | 9,000 | 20.46% |
| **2019** | 365 | 11,315 | 1,116 | 10,199 | 9.86% |
| **2020** | 366 | 11,346 | 8,358 | 2,988 | **73.66%** |
| **2021** | 365 | 11,315 | 50 | 11,265 | 0.44% |
| **2022** | 365 | 11,315 | 84 | 11,231 | 0.74% |
| **2023** | 205 | 6,355 | 36 | 6,319 | 0.57% |
| **Total** | **4,588** | **142,228** | **13,156** | **129,072** | **9.25%** |

*Note*: The severe cluster in 2020 reflects catastrophic prolonged multi-basin monsoon flooding extensively documented across almost all Karnataka districts in IFI v3.0.

### District-Level Label Representation
- **Top Flood-Impacted Districts**: Dakshina Kannada (774 days), Kodagu (772 days), Uttara Kannada (768 days), Udupi (676 days), Shivamogga (676 days).
- **Districts with Sparse/Zero IFI Evidence**:
  - Chamarajanagara: 4 flood days.
  - Vijayanagara (KGIS 31, carved from Ballari in 2021): 0 flood days in historical IFI v3.0 archive.

---

## 6. Flood-Label Provenance & Three-State Contract

Every positive label ($Y=1$) traces to official disaster records:
1. **Source Organization**: HydroSenseLab / India Meteorological Department (IMD).
2. **Dataset Identity**: India Flood Inventory (IFI v3.0), pan-India disaster event database.
3. **Database Provenance**: Stored in `public.district_day_flood_labels` with `source_dataset = 'India Flood Inventory (IFI v3.0)'`, `data_category = 'HISTORICAL_EVENT'`, `quality_status = 'VALID'`.
4. **Resolution Method**: Raw events matched to KSR-SAC districts via official Government of India LGD codes (`DIRECT_LGD`), canonical aliases (`VERIFIED_ALIAS`), or Bijapur split correction (`BIJAPUR_CORRECTION`).
5. **Overlaps & Duration**: Multi-day events were expanded day-by-day. Multiple source events on the same district-day were consolidated ($Y=1$), preserving source event IDs (`source_event_ids`).
6. **Zero Negative Fabrication**: Days without recorded IFI events were assigned $Y = \text{NULL}$ (`label_state = 'UNKNOWN'`). No zero labels were manufactured.

---

## 7. Temporal Anti-Leakage Audit

The temporal integrity contract requires:
$$\text{For prediction date } t, \quad \text{Features} \subseteq [t-30, t-1], \quad \text{Day } t \text{ weather strictly excluded.}$$

Audit across all 142,228 rows:
- `lead_time_days == 1` across 100.0% of records.
- `feature_window_end == target_date - 1 day` across 100.0% of records.
- `feature_window_start == feature_window_end - 29 days` (exactly 30 calendar days) across 100.0% of records.
- **Derived Feature Breakdown**:
  - `precip_1d_mm`: Day $t-1$ rainfall.
  - `precip_3d_sum_mm`: Sum over $[t-3, t-1]$.
  - `precip_7d_sum_mm`: Sum over $[t-7, t-1]$.
  - `precip_14d_sum_mm`: Sum over $[t-14, t-1]$.
  - `precip_30d_sum_mm`: Sum over $[t-30, t-1]$.
  - `precip_7d_max_mm`: Peak daily rainfall in $[t-7, t-1]$.
  - `temp_mean_1d_c`, `temp_min_1d_c`, `temp_max_1d_c`: Day $t-1$ temperature.
  - `temp_7d_mean_c`: Mean over $[t-7, t-1]$.
  - `rh_mean_1d_pct`: Day $t-1$ relative humidity.
  - `rh_7d_mean_pct`: Mean over $[t-7, t-1]$.
  - `pressure_mean_1d_hpa`: Day $t-1$ surface pressure.
- **Result**: Exactly **0 temporal leakage violations**.

---

## 8. Cold-Start Boundary Analysis (January 2011)

- Exactly **930 rows** have `is_weather_complete_30d == False`.
- Bounded strictly to `2011-01-01` $\to$ `2011-01-30` ($30 \text{ days} \times 31 \text{ districts} = 930$).
- All 930 rows have `label_state == 'UNKNOWN'`. Zero flood events are lost.
- Cause: Daily ERA5 ingestion starts on 2011-01-01, meaning antecedent weather for early January 2011 is not in the dataset.
- Policy Decision: **Policy A (Recommended)** — Exclude these 930 incomplete-history rows from training/evaluation to guarantee 100% complete feature vectors without artificial imputation.

---

## 9. Supervised Train/Validation/Test Feasibility

Because verified flood labels end on **2023-07-24**, the maximum defensible supervised evaluation period is:
$$\mathbf{2011-01-01 \to 2023-07-24}$$

### Feasible Chronological Partition
1. **TRAIN**: `2011-01-01` $\to$ `2019-12-31` (9 years, 101,897 rows, 4,628 floods, 4.54% prevalence)
2. **VALIDATION**: `2020-01-01` $\to$ `2021-12-31` (2 years, 22,661 rows, 8,408 floods, 37.10% prevalence)
3. **TEST**: `2022-01-01` $\to$ `2023-07-24` (1.56 years, 17,670 rows, 120 floods, 0.68% prevalence)

### Critical Clarification on 2024–2025
- **2024–2025 contains ZERO verified flood ground truth labels.**
- Calling 2024–2025 a "test set" is scientifically fraudulent.
- The 2023-07-25 $\to$ 2025-12-31 period is strictly an **unlabelled operational forward inference test-bed**, NOT a supervised evaluation partition.

---

## 10. Spatial Generalization & Autocorrelation Assessment

- Predictors consist of 27 continuous physical variables (meteorology, terrain, hydrology) and seasonal indices. Zero nominal district identifiers exist in the feature whitelist.
- Spatial holdout (e.g. Leave-One-District-Out) is **PARTIALLY SUPPORTED**:
  - *Feasibility*: Models can generate predictions on unseen districts using physical covariates.
  - *Limitation*: Synoptic weather systems and 191 multi-district ERA5 boundary cells create spatial autocorrelation across neighboring districts on the same date.
- *Primary Mission*: The project specification mandates **temporal generalization on the 31 known Karnataka districts** as the primary production objective.

---

## 11. Versioning & Provenance Metadata Standards

Every future trained model artifact must record:
```json
{
  "dataset_version": "recent_district_day_2011_2023_v1.0.0",
  "dataset_sha256": "d459e4461166842e194de8f8373f227585169f124cd620160a4aea74651e5dac",
  "feature_schema_version": "karnataka_flood_canonical_27_v1.0.0",
  "model_version": "1.0.0",
  "lead_time_days": 1,
  "temporal_lookback_window": "[t-30, t-1]"
}
```

---

## 12. Formal Readiness Decision

```text
DECISION: READY FOR MODEL DESIGN
```

The dataset reconciles 100% with project contracts:
- 0 fabricated negative labels.
- 0 temporal leakage violations.
- 100% verified meteorological completeness.
- Fully documented Positive-Unlabeled (PU) framing.
- Provenance traceable to raw ERA5 and authoritative IFI v3.0 archives.
