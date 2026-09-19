# AKKIHEBBAL River Station Provenance & Spatial Association Investigation Report

**Phase:** Phase 3.4A — AKKIHEBBAL River Station Provenance Investigation
**Date:** 2026-09-19
**Status:** COMPLETE (Investigation Only — Zero DB Mutations)
**Target Station:** `AKKIHEBBAL` (`7237182a-2ada-4a12-bf7c-e4ed2a073441`)

---

## Executive Summary

During the Phase 3.3 Administrative GIS ↔ Environmental Spatial Association Audit, the `AKKIHEBBAL` river gauging station emerged as the **only spatial association discrepancy** across 1,221 environmental records:
- **Stored database assignment:** District `Koppal` (`d1aeeddc-141b-4ab0-8899-ab9844e29b8d`, Northern Karnataka).
- **Authoritative spatial containment:** District `Mandya` (`c9065c38-f2c3-4b56-8209-1009e4faa6f7`, Southern Karnataka).

This Phase 3.4A investigation was executed strictly read-only to examine raw source payloads, official Local Government Directory (LGD) standards, KSR-SAC GIS geometries, and ingestion code mechanics.

**Key Finding:** The raw Central Water Commission (CWC) source payload explicitly specified `District: Mandya` and `District LGD Code: 544`. In the official Government of India Local Government Directory (and KSR-SAC official data), Mandya's official LGD code is indeed **544**. However, during Phase 2.4, an application seeder (`backend/app/ingestion/sources/geography.py`) assigned sequential codes to districts, erroneously giving `544` to Koppal and `545` to Mandya. When the CWC adapter (`nwic_river.py`) resolved districts by looking up `District.code == row["District LGD Code"]`, it matched `544` to Koppal.

The CWC source data, the physical station location on the Hemavathi/Cauvery river, and the authoritative KSR-SAC spatial boundaries are in 100% agreement: **AKKIHEBBAL is in Mandya district, Krishnarajpet taluk**.

---

## 1. Source Provenance

- **Source Organization:** Central Water Commission (CWC) / National Water Informatics Centre (NWIC).
- **Portal / Access Method:** National Water Data Portal (NWDP) Open Data CSV (`OPEN_DATA_CSV`).
- **Dataset Resource URL:**
  `https://nwdp.nwic.gov.in/dataset/d951a09c-6cf8-470e-be77-e80116f13d34/resource/37cba82e-f745-4004-80d2-b05cad65b8e4/download/rwl_manual_hr_cwc_009_2026_2030.csv`
- **License:** Government Open Data License - India (GODL).
- **Raw Data Preservation:** Preserved on disk under `data/raw/cwc/cwc_river_stage_*.csv`.
- **Observation Period:** 2026-01-02 08:00 IST (02:30 UTC) to 2026-06-04 20:30 UTC.
- **Data Category:** `OBSERVATION` (Physical staff gauge readings by CWC field observers).
- **Quality Status:** `VALID` (101 verified hourly water level readings in metres).

---

## 2. Raw / Source Station Identity

Directly extracted from raw CWC CSV payload (`rwl_manual_hr_cwc_009_2026_2030.csv`):

| Attribute | Raw Value from CWC Source Payload |
|---|---|
| **Station Name** | `AKKIHEBBAL` |
| **Agency** | `CWC` |
| **State LGD Code** | `29` |
| **State** | `Karnataka` |
| **District LGD Code** | `544` |
| **District** | `Mandya` |
| **Tehsil / Taluk** | `KRISHNARAJPET` |
| **River** | `Cauvery` |
| **Basin** | `Cauvery` |
| **Tributary** | `Hemavathi` |
| **Latitude** | `12.59861111` |
| **Longitude** | `76.40055556` |
| **Zero Gauge RL** | `745.00` m |
| **Mean Sea Level** | `745.00` m |

The raw source payload provided complete, unambiguous administrative fields: `District: Mandya`, `Tehsil: KRISHNARAJPET`, and `District LGD Code: 544`.

---

## 3. Coordinate Verification

- **Stored Coordinates:** `latitude = 12.59861111`, `longitude = 76.40055556`.
- **CRS:** WGS 84 (`EPSG:4326`).
- **Physical Verification:**
  - Akkihebbal is a well-documented village and river gauging site on the Hemavathi River (a major tributary of the Cauvery) in K.R. Pet (Krishnarajpet) taluk, Mandya district, Karnataka.
  - Coordinates `12.5986° N, 76.4006° E` place the station precisely at the Hemavathi river crossing near Akkihebbal village.
  - Coordinates are physical station coordinates, not district centroids or synthetic points.

---

## 4. Current Database Association

Extracted from PostgreSQL `river_stations` and related tables:

- **Station ID:** `7237182a-2ada-4a12-bf7c-e4ed2a073441`
- **Station Code:** `AKKIHEBBAL`
- **Assigned District ID:** `d1aeeddc-141b-4ab0-8899-ab9844e29b8d`
- **Assigned District Name:** `Koppal`
- **Assigned District Code (`districts.code`):** `544`
- **River:** `Cauvery` (`ec4cfcb3-2dfd-4125-a004-1b38e5acd2ce`)
- **River Basin:** `Cauvery` (`709a5e8e-f151-4fe9-b94c-da60258f9f7a`)
- **Active:** `true`
- **Associated Observations:** 101 records in `river_observations`.

---

## 5. Authoritative Spatial Association

Evaluated against KSR-SAC administrative polygons (`EPSG:4326`):

- **Karnataka State Containment:** `ST_Within(point, karnataka.geometry) = TRUE`.
- **Spatial District Containment:**
  - `ST_Within(point, mandya.geometry) = TRUE`.
  - District Name: `Mandya` (`c9065c38-f2c3-4b56-8209-1009e4faa6f7`).
  - District Code in DB: `545`.
  - Official LGD Code: `544`.
- **Spatial Taluk Containment:**
  - `ST_Within(point, krishnarajpet.geometry) = TRUE`.
  - Taluk Name: `Krishnarajpet` (`ec258701-9035-4fcc-96cd-9a9c32c0b31b`).
  - Taluk Code in DB: `5546`.
- **Ellipsoidal Distances (`::geography`):**
  - Distance to assigned district (`Koppal`): **284.29 km** (Northern Karnataka).
  - Distance to spatial district boundary (`Mandya`): **2.94 km** (well inside interior).
  - Distance to spatial taluk boundary (`Krishnarajpet`): **2.94 km** (well inside interior).

---

## 6. Root Cause Analysis

The Koppal assignment was caused by an **LGD code indexing mismatch** during Phase 2.4 ingestion:

```text
CWC Source CSV:
  "District LGD Code": "544"
  "District": "Mandya"
         │
         │ (adapter looks up by District.code == "544")
         ▼
geography.py Seeder:
  {"code": "544", "name": "Koppal"}  <── ERRID: Koppal assigned 544
  {"code": "545", "name": "Mandya"}  <── ERRID: Mandya assigned 545
         │
         ▼
Resolved District:
  District(name="Koppal", id="d1aeeddc-141b-4ab0-8899-ab9844e29b8d")
```

1. **Official LGD Truth:**
   According to the official Local Government Directory of India (and KSR-SAC `District.shp`):
   - `Mandya`: Official LGD code is **`544`** (KGIS code `22`).
   - `Koppal`: Official LGD code is **`543`** (KGIS code `07`).
   - `Mysuru`: Official LGD code is **`545`** (KGIS code `26`).
2. **Phase 2.4 Geography Seeder Deviation:**
   In `backend/app/ingestion/sources/geography.py`, `KARNATAKA_DISTRICTS_LGD` was populated with an unverified sequential code list that offset several district codes:
   - It assigned `code: "544"` to `Koppal`.
   - It assigned `code: "545"` to `Mandya`.
3. **Ingestion Adapter Lookup:**
   In `backend/app/ingestion/sources/nwic_river.py` (lines 127–163):
   ```python
   districts = {d.code: d for d in self.session.execute(dist_stmt).scalars() if d.code}
   dist_lgd = row.get("District LGD Code")  # Extracted "544"
   district = districts.get(dist_lgd)       # Matched District(code="544", name="Koppal")
   ```
   The adapter matched exclusively on `d.code` and did not validate against `row.get("District")` (`"Mandya"`).
4. **Preservation in Phase 3.2:**
   During KSR-SAC PostGIS ingestion (Phase 3.2), existing district UUIDs and `districts.code` were preserved to maintain referential integrity for existing foreign keys. Thus, `Koppal` retained `code = "544"` and `Mandya` retained `code = "545"`.

---

## 7. Downstream Impact

1. **`river_observations` (101 rows):**
   - All 101 observations link to `station_id = '7237182a-2ada-4a12-bf7c-e4ed2a073441'`.
   - The `river_observations` table has **no `district_id` column**. Its administrative association is entirely derived via `river_stations.district_id`.
   - Zero observation rows need to be updated.
2. **`river_forecasts` (0 rows):**
   - No river forecasts currently exist in the database.
3. **`rivers` and `river_basins`:**
   - Station correctly links to `River: Cauvery` (`ec4cfcb3-2dfd-4125-a004-1b38e5acd2ce`), which links to `RiverBasin: Cauvery` (`709a5e8e-f151-4fe9-b94c-da60258f9f7a`).
   - Hydrological topology is 100% correct.
4. **Feature Store / Downstream Aggregations:**
   - Any spatial rollups aggregating river stage by district currently misattribute Akkihebbal's stage to Koppal instead of Mandya. Correcting `district_id` will immediately restore accurate district-level hydrological rollups.

---

## 8. Evidence Supporting the Proposed Correction

Every independent line of evidence unanimously confirms that `AKKIHEBBAL` belongs to `Mandya`:
1. **Raw CWC Source Payload:** Explicitly states `District: Mandya`, `Tehsil: KRISHNARAJPET`.
2. **Official LGD Standards:** Mandya's official Government of India LGD code is `544`, matching CWC's `District LGD Code: 544`.
3. **KSR-SAC Administrative Shapefiles:** Official KSR-SAC polygon containment places the station $2.94\text{ km}$ inside Mandya district and $2.94\text{ km}$ inside Krishnarajpet taluk.
4. **Physical Geography:** Akkihebbal village is situated on the Hemavathi River in K.R. Pet taluk, Mandya district, at $12.5986^\circ\text{ N}, 76.4006^\circ\text{ E}$. Koppal is in northern Karnataka, $> 280\text{ km}$ away in the Krishna basin.

---

## 9. Uncertainties & Unresolved Issues

- **None.** The provenance, physical coordinates, administrative records, and spatial geometry are completely unambiguous and verified across all source documents and GIS layers.

---

## 10. Recommended Phase 3.4B Remediation Plan

When approved for implementation in Phase 3.4B:

1. **Database Update (Single Atomic Statement):**
   Update `river_stations.district_id` to point to Mandya's UUID:
   ```sql
   UPDATE river_stations
   SET district_id = 'c9065c38-f2c3-4b56-8209-1009e4faa6f7'
   WHERE station_code = 'AKKIHEBBAL';
   ```
2. **Ingestion Adapter Hardening (`backend/app/ingestion/sources/nwic_river.py`):**
   Harden district resolution to prevent re-introducing the error on future ingestion runs:
   - Match by normalized district name in addition to LGD code.
   - Use canonical KSR-SAC / LGD mappings.
3. **Audit Verification:**
   Rerun `SpatialAssociationAuditor` to confirm:
   - `river_stations`: 1 examined, 1 matched, 0 discrepancies, 0 requiring manual review.
   - Statewide spatial association audit: **1,221 / 1,221 (100.0%) spatially matched**.
