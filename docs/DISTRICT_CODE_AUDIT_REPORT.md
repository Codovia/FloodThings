# Karnataka District Code Integrity Audit Report

**Phase:** Phase 3.4B — Part A (District Code Integrity Audit)
**Date:** 2026-09-19
**Status:** COMPLETE (Audit Only — Zero DB Mutations)

---

## Executive Summary

This audit establishes the definitive, complete comparison between the current database district master mapping (derived from the Phase 2.4 geography seeder) and the authoritative Local Government Directory (LGD) / KSR-SAC catalog.

**Key Findings:**
1. **Master Code Mismatch**: Exactly **25 of 31 districts** in the database currently have `districts.code` differing from their authoritative Government of India LGD code. Only 6 districts matched.
2. **Root Cause of Master Code Deviation**: During Phase 2.4, `backend/app/ingestion/sources/geography.py` populated `KARNATAKA_DISTRICTS_LGD` using an unverified sequential integer list (`524` to `553`, and `744`). This omitted official renumberings (e.g. Chikkaballapura is LGD `630`, Ramanagara is LGD `631`, Yadgir is LGD `635`, Vijayanagara is LGD `738`) and swapped Bangalore Urban (`525`) and Bangalore Rural (`526`). This offset subsequent district codes by 1.
3. **Foreign Key Integrity**: All foreign keys across all application tables reference `districts.id` (UUID), **not** `districts.code`.
   - 31 / 31 district UUIDs are strictly preserved.
   - 240 / 240 taluks are spatially verified within their assigned district.
   - 397 / 397 weather observations are spatially verified within their assigned district.
   - 397 / 397 rainfall observations are spatially verified within their assigned district.
   - 275 / 275 weather forecasts are correctly attributed.
   - 101 / 101 river observations link to `station_id` (no `district_id` column on table).
   - 186 / 186 flood observations reference valid district UUIDs.
4. **Required Corrections**:
   - Update `districts.code` for the 25 mismatched districts to their authoritative LGD codes.
   - Correct `river_stations` for `AKKIHEBBAL`: update `district_id` from Koppal UUID to Mandya UUID.
   - Harden `backend/app/ingestion/sources/nwic_river.py` to validate district names and prevent erroneous code-only resolution.
   - Update `KARNATAKA_DISTRICTS_LGD` in `backend/app/ingestion/sources/geography.py` to reflect authoritative LGD codes.

---

## Complete 31-District Comparison

| District Name | Current DB Code | Auth LGD Code | KGIS Code | Status | Total FK Refs | FK Breakdown (W, R, FO, RS, T) |
|---|---|---|---|---|---|---|
| **Bagalkote** | `524` | `524` | `02` | **MATCH** | 10 | W:0, R:0, FO:0, RS:0, T:10 |
| **Ballari** | `528` | `528` | `12` | **MATCH** | 16 | W:0, R:0, FO:11, RS:0, T:5 |
| **Bangalore Rural** | `525` | `526` | `21` | **MISMATCH** | 7 | W:0, R:0, FO:3, RS:0, T:4 |
| **Bangalore Urban** | `526` | `525` | `20` | **MISMATCH** | 357 | W:137, R:137, FO:23, RS:0, T:5 |
| **Belagavi** | `527` | `527` | `01` | **MATCH** | 212 | W:65, R:65, FO:12, RS:0, T:15 |
| **Bidar** | `529` | `529` | `05` | **MATCH** | 8 | W:0, R:0, FO:0, RS:0, T:8 |
| **Chamarajanagara** | `531` | `531` | `27` | **MATCH** | 5 | W:0, R:0, FO:0, RS:0, T:5 |
| **Chikkaballapura** | `532` | `630` | `28` | **MISMATCH** | 16 | W:0, R:0, FO:8, RS:0, T:8 |
| **Chikkamagaluru** | `533` | `532` | `17` | **MISMATCH** | 13 | W:0, R:0, FO:4, RS:0, T:9 |
| **Chitradurga** | `534` | `533` | `13` | **MISMATCH** | 14 | W:0, R:0, FO:8, RS:0, T:6 |
| **Dakshina Kannada** | `535` | `534` | `24` | **MISMATCH** | 197 | W:65, R:65, FO:3, RS:0, T:9 |
| **Davanagere** | `536` | `535` | `14` | **MISMATCH** | 19 | W:0, R:0, FO:13, RS:0, T:6 |
| **Dharwad** | `537` | `536` | `09` | **MISMATCH** | 12 | W:0, R:0, FO:4, RS:0, T:8 |
| **Gadag** | `538` | `537` | `08` | **MISMATCH** | 18 | W:0, R:0, FO:11, RS:0, T:7 |
| **Hassan** | `540` | `539` | `23` | **MISMATCH** | 11 | W:0, R:0, FO:3, RS:0, T:8 |
| **Haveri** | `541` | `540` | `11` | **MISMATCH** | 17 | W:0, R:0, FO:9, RS:0, T:8 |
| **Kalaburagi** | `539` | `538` | `04` | **MISMATCH** | 203 | W:65, R:65, FO:7, RS:0, T:11 |
| **Kodagu** | `542` | `541` | `25` | **MISMATCH** | 14 | W:0, R:0, FO:9, RS:0, T:5 |
| **Kolar** | `543` | `542` | `19` | **MISMATCH** | 10 | W:0, R:0, FO:4, RS:0, T:6 |
| **Koppal** | `544` | `543` | `07` | **MISMATCH** | 14 | W:0, R:0, FO:6, RS:1, T:7 |
| **Mandya** | `545` | `544` | `22` | **MISMATCH** | 201 | W:65, R:65, FO:9, RS:0, T:7 |
| **Mysuru** | `546` | `545` | `26` | **MISMATCH** | 22 | W:0, R:0, FO:13, RS:0, T:9 |
| **Raichur** | `547` | `546` | `06` | **MISMATCH** | 17 | W:0, R:0, FO:9, RS:0, T:8 |
| **Ramanagara** | `548` | `631` | `29` | **MISMATCH** | 12 | W:0, R:0, FO:7, RS:0, T:5 |
| **Shivamogga** | `549` | `547` | `15` | **MISMATCH** | 12 | W:0, R:0, FO:5, RS:0, T:7 |
| **Tumakuru** | `550` | `548` | `18` | **MISMATCH** | 10 | W:0, R:0, FO:0, RS:0, T:10 |
| **Udupi** | `551` | `549` | `16` | **MISMATCH** | 7 | W:0, R:0, FO:0, RS:0, T:7 |
| **Uttara Kannada** | `552` | `550` | `10` | **MISMATCH** | 12 | W:0, R:0, FO:0, RS:0, T:12 |
| **Vijayanagara** | `744` | `738` | `31` | **MISMATCH** | 6 | W:0, R:0, FO:0, RS:0, T:6 |
| **Vijayapura** | `530` | `530` | `03` | **MATCH** | 18 | W:0, R:0, FO:5, RS:0, T:13 |
| **Yadgir** | `553` | `635` | `30` | **MISMATCH** | 6 | W:0, R:0, FO:0, RS:0, T:6 |

---

## Affected Tables & Scope

| Table Name | Total Rows | Rows Affected by Code Correction | Rows Affected by FK Correction |
|---|---|---|---|
| `districts` | 31 | 25 (update `districts.code` to authoritative LGD) | 0 (UUIDs preserved) |
| `river_stations` | 1 | 0 | 1 (`AKKIHEBBAL` Koppal → Mandya UUID) |
| `river_observations` | 101 | 0 | 0 (no `district_id` column; station FK preserved) |
| `weather_observations` | 397 | 0 | 0 (already 100% spatially matched to assigned district) |
| `rainfall_observations` | 397 | 0 | 0 (already 100% spatially matched to assigned district) |
| `weather_forecasts` | 275 | 0 | 0 (assigned to correct district centers) |
| `flood_observations` | 186 | 0 | 0 (district references valid; historical damage evidence) |
| `taluks` | 240 | 0 | 0 (100% point-on-surface verified inside assigned district) |
| `reservoirs` | 1 | 0 | 0 (`Almatti Dam` has `district_id = NULL`) |

---

## Controlled Correction Strategy (Phase 3.4B - Part B)

1. **Atomic Transaction**:
   - Execute in a single atomic transaction.
   - Update `districts.code` for all 25 mismatched districts to their authoritative LGD codes.
   - Update `river_stations.district_id` for `AKKIHEBBAL` to Mandya's UUID (`c9065c38-f2c3-4b56-8209-1009e4faa6f7`).
2. **Ingestion Adapter Hardening**:
   - Update `backend/app/ingestion/sources/nwic_river.py`:
     - Create canonical mapping between station names, source LGD codes, and normalized district names.
     - Cross-check source district name against district code.
     - Reject/log any conflicting source code/name combinations.
3. **Seeder Update**:
   - Update `KARNATAKA_DISTRICTS_LGD` in `backend/app/ingestion/sources/geography.py` to match authoritative LGD codes.
4. **Post-Correction Spatial Audit**:
   - Rerun `SpatialAssociationAuditor` to verify 100% spatial match (1,221 / 1,221 records).
