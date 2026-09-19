# KSR-SAC Administrative GIS PostGIS Ingestion Design (Phase 3.1)

**Project:** FloodPulse
**Status:** DESIGN ONLY — Phase 3.1
**Created:** 2026-09-19
**Target Execution:** Phase 3.2
**Governing Documents:**
- `docs/MASTER_PROJECT_SPEC.md`
- `docs/CONSTRAINTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_CONTRACT.md`
- `docs/DATA_PIPELINE.md`
- `docs/DATA_SOURCES.md`
- `docs/DECISIONS.md` (D-014, D-019, D-022, D-032, D-033)
- `docs/HANDOVER.md`

---

## 1. Objective

The objective of Phase 3.1 is to design the safe, deterministic, and idempotent ingestion of the already validated Karnataka State Remote Sensing Applications Centre (KSR-SAC) administrative GIS boundaries into the PostgreSQL 16 / PostGIS 3.4 database.

This establishes the definitive spatial hierarchy for the FloodPulse platform:
- **1 State:** Karnataka (`code = '29'`)
- **31 Districts:** Belagavi (`01`) through Vijayanagara (`31`)
- **240 Taluks:** All constituent administrative sub-districts

### Strict Phase Boundaries (Phase 3.1)
- **DESIGN ONLY**: No GIS data is inserted into PostgreSQL during this phase.
- **ZERO SCHEMA MUTATION**: No migrations, no DDL modifications, no new database tables or columns.
- **ZERO RAW MODIFICATION**: Raw source shapefiles under `data/raw/gis/ksrsac/` remain strictly read-only and untouched.
- **ZERO GEOMETRY SIMPLIFICATION**: No `ST_Simplify`, vertex decimation, smoothing, or coordinate fabrication.

---

## 2. Current Database State

The physical PostgreSQL 16 / PostGIS 3.4 database (`floodpulse-postgres` container, port 5432) was directly inspected via system catalogs (`information_schema`, `geometry_columns`, `pg_indexes`, and table queries).

### 2.1 Table Structure & Constraints

| Table | Column | Type | Nullable | Constraints & Indexes | Current DB Row Count | Geometry Populated? |
|---|---|---|---|---|---|---|
| `states` | `id` | `UUID` | NO | PRIMARY KEY (`states_pkey`), default `gen_random_uuid()` | **1** | **NO** (0 populated, 1 NULL) |
| `states` | `name` | `VARCHAR(100)` | NO | UNIQUE (`states_name_key`) | 1 | — |
| `states` | `code` | `VARCHAR(20)` | YES | UNIQUE (`states_code_key`) | 1 | — |
| `states` | `geometry` | `GEOMETRY(MULTIPOLYGON, 4326)` | YES | GiST index (`idx_states_geometry`) | 1 | `NULL` |
| `districts` | `id` | `UUID` | NO | PRIMARY KEY (`districts_pkey`), default `gen_random_uuid()` | **31** | **NO** (0 populated, 31 NULL) |
| `districts` | `state_id` | `UUID` | NO | FOREIGN KEY -> `states.id` (`districts_state_id_fkey`) `ON DELETE NO ACTION`, BTree index (`ix_districts_state_id`) | 31 | — |
| `districts` | `name` | `VARCHAR(100)` | NO | Indexed via BTree | 31 | — |
| `districts` | `code` | `VARCHAR(20)` | YES | UNIQUE (`districts_code_key`) | 31 | — |
| `districts` | `geometry` | `GEOMETRY(MULTIPOLYGON, 4326)` | YES | GiST index (`idx_districts_geometry`) | 31 | `NULL` |
| `districts` | `centroid` | `GEOMETRY(POINT, 4326)` | YES | GiST index (`idx_districts_centroid`) | 31 | **YES** (31 points populated) |
| `taluks` | `id` | `UUID` | NO | PRIMARY KEY (`taluks_pkey`), default `gen_random_uuid()` | **0** | **NO** (0 rows) |
| `taluks` | `district_id` | `UUID` | NO | FOREIGN KEY -> `districts.id` (`taluks_district_id_fkey`) `ON DELETE NO ACTION`, BTree index (`ix_taluks_district_id`) | 0 | — |
| `taluks` | `name` | `VARCHAR(100)` | NO | Standard text | 0 | — |
| `taluks` | `code` | `VARCHAR(20)` | YES | UNIQUE (`taluks_code_key`) | 0 | — |
| `taluks` | `geometry` | `GEOMETRY(MULTIPOLYGON, 4326)` | YES | GiST index (`idx_taluks_geometry`) | 0 | `NULL` |
| `localities` | `id` | `UUID` | NO | PRIMARY KEY, FK -> `taluks.id` `ON DELETE NO ACTION` | 0 | `NULL` |

### 2.2 Active Referential Dependencies on `districts`

`VERIFIED FACT`: A comprehensive query of `information_schema.referential_constraints` revealed that 13 foreign keys across the schema point to `districts.id`. Exactly 5 active application tables currently contain **1,256 live rows** referencing `districts.id`:

| Referencing Table | Foreign Key Column | Active Row Count | Delete Action | Meaning |
|---|---|---|---|---|
| `rainfall_observations` | `district_id` | **397** | `NO ACTION` | Operational & reanalysis rainfall measurements |
| `weather_observations` | `district_id` | **397** | `NO ACTION` | Operational & reanalysis weather measurements |
| `weather_forecasts` | `district_id` | **275** | `NO ACTION` | 72-hour forward weather forecasts |
| `flood_observations` | `district_id` | **186** | `NO ACTION` | IFI v3.0 historical disaster occurrence evidence |
| `river_stations` | `district_id` | **1** | `NO ACTION` | CWC river water level gauge station |
| `taluks` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `water_bodies` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `land_covers` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `prediction_grid_cells` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `emergency_facilities` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `reservoirs` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `telegram_subscriptions` | `district_id` | 0 | `NO ACTION` | Currently empty |
| `alerts` | `district_id` | 0 | `NO ACTION` | Currently empty |

> [!CRITICAL]
> `DESIGN DECISION`: Because 1,256 active observation and forecast records reference existing `districts.id` UUIDs with `ON DELETE NO ACTION`, **districts must never be deleted, recreated, or replaced**. The ingestion pipeline must perform an in-place geometry update on the existing 31 `districts` records, strictly preserving their UUID primary keys.

---

## 3. Source State

The KSR-SAC administrative boundary files are located under `data/raw/gis/ksrsac/` and were normalized and validated during Phase 2.6 (`backend/app/gis/ksrsac.py`):

| Administrative Entity | Source File | Source Feature Count | Source CRS | Required Columns | Validity Status | Repairs Performed |
|---|---|---|---|---|---|---|
| **State** | `State.shp` | **1** | `EPSG:32643` (UTM Zone 43N) | `KGISStateI`, `KGISStateC`, `KGISStateN`, `geometry` | 100% Valid | None (0 repairs) |
| **Districts** | `District.shp` | **31** | `EPSG:32643` (UTM Zone 43N) | `KGISDistri`, `LGD_Distri`, `KGISDist_1`, `geometry` | 100% Valid | None (0 repairs) |
| **Taluks** | `Taluk.shp` | **240** | `EPSG:32643` (UTM Zone 43N) | `KGISTalukC`, `LGD_TalukC`, `KGISTalukN`, `KGISDistri`, `geometry` | 237 Valid, 3 Invalid | **3 deterministic repairs** via `shapely.make_valid()` |

### 3.1 Verified Source Features
- `VERIFIED FACT`: `State.shp` contains exactly 1 feature: `KGISStateI = 1`, `KGISStateC = '29'` (Survey of India / LGD state code), `KGISStateN = 'Karnataka'`.
- `VERIFIED FACT`: `District.shp` contains exactly 31 features: `KGISDistri` spans `'01'` through `'31'`.
- `VERIFIED FACT`: `Taluk.shp` contains exactly 240 features: `KGISTalukC` spans `'0101'` through `'3106'`.
- `VERIFIED FACT`: District 31 (Vijayanagara, `KGISDistri = '31'`) contains exactly 6 constituent taluks (`Hadagali`, `Hagaribommanahalli`, `Harapanahalli`, `Hosapete`, `Kotturu`, `Kudligi`).
- `VERIFIED FACT`: Source horizontal projection is strictly `EPSG:32643` (WGS 84 / UTM Zone 43N, metres).

---

## 4. Mapping Contract

Mapping must be 100% deterministic and authoritative. Centroid proximity and fuzzy spatial guessing are **strictly prohibited** per `CONSTRAINTS.md`.

### 4.1 State Mapping (1-to-1)
- **Source**: `NormalizedState` (`KGISStateC = '29'`, `KGISStateN = 'Karnataka'`).
- **Target**: `states` table record where `code = '29'` OR `name = 'Karnataka'`.
- **Action**: Update `geometry` column with normalized `MultiPolygon` in `EPSG:4326`.
- **Identifier**: `states.id = 4e6cc1fb-597c-40c2-ac55-567703d172c2` preserved.

### 4.2 District Mapping (31-to-31 Bijective)
There are 31 districts in KSR-SAC and 31 districts in the database.
- Exactly 26 districts match directly by exact string equality.
- Exactly 5 districts have minor name variants that are deterministically resolved using the canonical alias registry established and verified in Phase 2.7 (`backend/app/gis/ifi.py`):
  1. KSR-SAC `Kalaburgi` (`KGISDistri = '04'`) $\to$ DB `Kalaburagi` (`id = 31524635-e2c2-4ed0-8fc3-cca91afad306`)
  2. KSR-SAC `Kolara` (`KGISDistri = '19'`) $\to$ DB `Kolar` (`id = 05a5dcf8-a826-4290-bd71-83676d57f77d`)
  3. KSR-SAC `Bengaluru (Urban)` (`KGISDistri = '20'`) $\to$ DB `Bangalore Urban` (`id = b3c0245a-5603-4fd5-b430-0cb8e9864d82`)
  4. KSR-SAC `Bengaluru (Rural)` (`KGISDistri = '21'`) $\to$ DB `Bangalore Rural` (`id = 79c76689-1454-4090-a608-390cd12c70c3`)
  5. KSR-SAC `Bengaluru South` (`KGISDistri = '29'`) $\to$ DB `Ramanagara` (`id = aaaf939c-00be-4455-a099-80992717fe2c`) *(Ramanagara was formed from Bengaluru South in 2007; both represent KGIS 29 / LGD 631)*.

#### Complete Bijective District Mapping Matrix

| KGIS Code | KSR-SAC Name (`KGISDist_1`) | KSR-SAC LGD (`LGD_Distri`) | DB District Name | DB District ID (UUID) | DB Current Code | Match Type |
|---|---|---|---|---|---|---|
| `01` | Belagavi | 527 | Belagavi | `a2543a7b-88f0-4daa-8f00-d11ef4149bc6` | 527 | Direct Name |
| `02` | Bagalkote | 524 | Bagalkote | `3d1b1dce-fb79-4b34-9881-f90c51f68242` | 524 | Direct Name |
| `03` | Vijayapura | 530 | Vijayapura | `db3c427c-8daf-4fe8-b04d-f954b2bc5e6c` | 530 | Direct Name |
| `04` | Kalaburgi | 538 | Kalaburagi | `31524635-e2c2-4ed0-8fc3-cca91afad306` | 539 | Canonical Alias |
| `05` | Bidar | 529 | Bidar | `4abd3e22-c50c-4a16-9f33-64cc32313159` | 529 | Direct Name |
| `06` | Raichur | 546 | Raichur | `362691a7-9226-466e-a9a1-1114e134baea` | 547 | Direct Name |
| `07` | Koppal | 543 | Koppal | `d1aeeddc-141b-4ab0-8899-ab9844e29b8d` | 544 | Direct Name |
| `08` | Gadag | 537 | Gadag | `e9681cc6-1128-4afd-86ad-1f61fa0a25a4` | 538 | Direct Name |
| `09` | Dharwad | 536 | Dharwad | `7b21e929-a262-43f3-9c5a-22dbaa0e7c16` | 537 | Direct Name |
| `10` | Uttara Kannada | 550 | Uttara Kannada | `72c6de36-26a2-4cf4-9844-11d1061505e9` | 552 | Direct Name |
| `11` | Haveri | 540 | Haveri | `65ae4379-ec8c-47d1-9616-80a18a46caf7` | 541 | Direct Name |
| `12` | Ballari | 528 | Ballari | `eb68c297-e9c5-44ff-aea7-4b9f5d3e254f` | 528 | Direct Name |
| `13` | Chitradurga | 533 | Chitradurga | `3f72a4a9-5c08-44c5-846e-d7fd5c478244` | 534 | Direct Name |
| `14` | Davanagere | 535 | Davanagere | `4f12065b-bccb-4845-a968-6e58b3985006` | 536 | Direct Name |
| `15` | Shivamogga | 547 | Shivamogga | `8d2fd099-28bd-428c-a87a-4b9f1480be5d` | 549 | Direct Name |
| `16` | Udupi | 549 | Udupi | `f2627977-7efd-4e2e-82eb-f617b1aa5528` | 551 | Direct Name |
| `17` | Chikkamagaluru | 532 | Chikkamagaluru | `e5c3d74e-6d3a-443f-9c53-1f3fefd6fd7a` | 533 | Direct Name |
| `18` | Tumakuru | 548 | Tumakuru | `a37fab40-8393-41a9-a620-71c36de48a78` | 550 | Direct Name |
| `19` | Kolara | 542 | Kolar | `05a5dcf8-a826-4290-bd71-83676d57f77d` | 543 | Canonical Alias |
| `20` | Bengaluru (Urban) | 525 | Bangalore Urban | `b3c0245a-5603-4fd5-b430-0cb8e9864d82` | 526 | Canonical Alias |
| `21` | Bengaluru (Rural) | 526 | Bangalore Rural | `79c76689-1454-4090-a608-390cd12c70c3` | 525 | Canonical Alias |
| `22` | Mandya | 544 | Mandya | `c9065c38-f2c3-4b56-8209-1009e4faa6f7` | 545 | Direct Name |
| `23` | Hassan | 539 | Hassan | `25767999-250d-4530-b996-6de7d4ad4727` | 540 | Direct Name |
| `24` | Dakshina Kannada | 534 | Dakshina Kannada | `ddec0dd9-12c1-4db2-af31-0c165303a0db` | 535 | Direct Name |
| `25` | Kodagu | 541 | Kodagu | `206ba603-2c40-4504-8a6b-2e1492ce5425` | 542 | Direct Name |
| `26` | Mysuru | 545 | Mysuru | `df6eee1c-7235-4e23-b633-5ae8e411282c` | 546 | Direct Name |
| `27` | Chamarajanagara | 531 | Chamarajanagara | `2a22ef6f-aeca-469f-bf10-f61aecdc1087` | 531 | Direct Name |
| `28` | Chikkaballapura | 630 | Chikkaballapura | `4be38004-f261-4fc9-8703-a9015b2af7ab` | 532 | Direct Name |
| `29` | Bengaluru South | 631 | Ramanagara | `aaaf939c-00be-4455-a099-80992717fe2c` | 548 | Canonical Alias |
| `30` | Yadgir | 635 | Yadgir | `cb987642-4031-4fd8-92e8-a520b6219f92` | 553 | Direct Name |
| `31` | Vijayanagara | 738 | Vijayanagara | `3776223e-b4c8-40c3-8852-b6861635c618` | 744 | Direct Name |

> [!IMPORTANT]
> `DESIGN DECISION`: District code reconciliation:
> In the existing DB, `districts.code` holds values assigned during Phase 2.4 (which used contiguous numbers 524–553, 744). Overwriting `districts.code` in-place would violate the unique key constraint `districts_code_key` because old and new code sets overlap (e.g., Kalaburagi is 538 in KSR-SAC, but Gadag is currently 538 in DB).
> **Policy**: In Phase 3.2, `districts.code` remains untouched. Ingestion updates `districts.geometry = NormalizedDistrict.geometry` and `districts.centroid = NormalizedDistrict.centroid`. True KGIS codes (`01`–`31`) and official LGD codes (`524`–`738`) are tracked via the in-memory `KsrsacAdminNormalizer` registry and logged in the ingestion run audit.

### 4.3 Taluk Mapping (240 Entities)
- **Source**: 240 `NormalizedTaluk` entities from `KsrsacAdminNormalizer`.
- **Target**: `taluks` table (currently 0 rows).
- **Mapping Fields**:
  - `id`: Newly generated `uuid.uuid4()`.
  - `district_id`: Resolved directly by looking up `NormalizedTaluk.parent_kgis_district_code` (`01`–`31`) in the bijective district mapping matrix to retrieve the parent `districts.id` UUID.
  - `name`: `NormalizedTaluk.taluk_name`.
  - `code`: `NormalizedTaluk.lgd_taluk_code` (unique LGD taluk code).
  - `geometry`: `NormalizedTaluk.geometry` (`MULTIPOLYGON` in `EPSG:4326`).

---

## 5. CRS Contract

| Attribute | Specification | Justification |
|---|---|---|
| **Source CRS** | `EPSG:32643` (UTM Zone 43N, metres) | `VERIFIED FACT`: Ground truth projection of KSR-SAC shapefiles. |
| **Transformation** | `pyproj` / `geopandas.to_crs(TARGET_STORAGE_CRS)` | Rigorous coordinate reprojection via PROJ 9+ pipelines. |
| **Target Storage CRS** | `EPSG:4326` (WGS 84, decimal degrees) | Required by `DATA_CONTRACT.md`, `DECISIONS.md` D-019, and database schema `Geometry("MULTIPOLYGON", srid=4326)`. |
| **Expected Geometry Type** | `MULTIPOLYGON` | Strictly enforced by database column definition and `to_multipolygon()` coercion helper. |
| **Dimensionality** | 2D (`XY`) | 2 coordinate dimensions (`coord_dimension = 2` verified in PostGIS `geometry_columns`). No Z or M coordinates. |
| **Bounding Box** | Latitude: $[11.5^\circ\text{N}, 18.5^\circ\text{N}]$, Longitude: $[74.0^\circ\text{E}, 78.6^\circ\text{E}]$ | Geographically validated Karnataka extents. |

---

## 6. Geometry Validation Contract

Before executing any database insert or update, the ingestion pipeline must execute the following 12 mandatory pre-insert checks:

```text
                               IN-MEMORY VALIDATION GATE
                                           │
  ┌────────────────────────────────────────┼────────────────────────────────────────┐
  │                                        │                                        │
1. Non-Null Geometry                     5. Expected Feature Counts              9. Referential Parent
   (geom is not None)                       (State=1, Dist=31, Taluk=240)           (Every taluk parent exists)
  │                                        │                                        │
2. Topological Validity                  6. Identifier Uniqueness               10. Hierarchy Containment
   (geom.is_valid == True)                  (Unique KGIS & LGD codes)               (All taluks in parent district)
  │                                        │                                        │
3. Exact Type Constraint                 7. State Containment                   11. Vijayanagara Integrity
   (isinstance(geom, MultiPolygon))         (All districts & taluks in State)       (Exactly 6 constituent taluks)
  │                                        │                                        │
4. Correct SRID                          8. Non-Overlap Guard                   12. Zero Duplicate Records
   (SRID == 4326)                           (Relative overlap <= 1e-10)             (Bijective 1-to-1 match)
```

1. **Non-Null**: `geometry` must not be None or empty (`geom.is_empty == False`).
2. **Valid Geometry**: `geom.is_valid == True` (evaluated in source CRS and post-reprojection).
3. **Geometry Type**: Must be strictly `MultiPolygon`. Single `Polygon` instances must be coerced via `to_multipolygon()`.
4. **SRID**: Must be strictly `4326`.
5. **Exact Counts**: Exactly 1 state, 31 districts, and 240 taluks.
6. **Unique Identifiers**: Exactly 31 unique district KGIS/LGD codes and 240 unique taluk KGIS/LGD codes.
7. **State Containment**:
   - Every district geometry intersects the State geometry (`state.geometry.intersects(d.geometry)`).
   - Every district's representative point lies inside State geometry (`state.geometry.contains(d.geometry.representative_point())`).
   - Every taluk geometry intersects and has its representative point inside State geometry.
8. **Topological Non-Overlap**: No pair of districts, and no pair of taluks within the same district, may have an overlap area exceeding relative tolerance $\text{REL\_TOL} = 10^{-10}$.
9. **Referential Parent Existence**: Every taluk's parent district code resolves to a valid existing district in the mapping table.
10. **Parent-District Containment**: Every taluk intersects its parent district geometry, and its representative point lies inside its parent district geometry.
11. **Vijayanagara 6-Taluk Integrity**: District `31` must have exactly 6 constituent taluks (`Hadagali`, `Hagaribommanahalli`, `Harapanahalli`, `Hosapete`, `Kotturu`, `Kudligi`).
12. **Zero Duplicate Records**: No duplicate administrative entities may exist.

---

## 7. Geometry Integrity Policy

- `DESIGN DECISION`: **Full Survey Preservation**: Ingestion must preserve original KSR-SAC boundary coordinates at their native 1:50,000 survey precision.
- **Zero Simplification**: Under no circumstances may geometries be simplified (`ST_Simplify`, Douglas-Peucker) or smoothed (`ST_ChaikinSmoothing`).
- **Validity Repair Policy**:
  - State and all 31 districts are 100% topologically valid in source files and require zero repairs.
  - Exactly 3 taluks in the source dataset contain digitizing self-intersections (Shivamogga `1506`, Sringeri `1701`, Hosanagar `1504`).
  - These 3 geometries are repaired deterministically in source metric space (`EPSG:32643`) using `shapely.make_valid()`, as established in Phase 2.6A (`DECISIONS.md` D-032).
  - `buffer(0)` is **strictly prohibited**.
  - Area difference resulting from repair is sub-millimetric floating-point noise ($< 10^{-12}$ relative difference).
- **Raw File Immutability**: Source files on disk under `data/raw/gis/ksrsac/` are read-only and must never be overwritten or modified.

---

## 8. Idempotency Strategy

The ingestion operation must be safely executable multiple times without side effects, data duplication, or constraint violations.

### 8.1 Upsert Strategy by Entity

#### State
```sql
-- Check existing Karnataka state record
SELECT id FROM states WHERE code = '29' OR name = 'Karnataka';

-- Update existing record
UPDATE states
SET geometry = ST_GeomFromEWKT(:wkt)
WHERE id = :state_id;
```

#### Districts
```sql
-- Match by verified bijective mapping (UUID)
SELECT id, name, code, geometry FROM districts WHERE id = :matched_district_id;

-- Update geometry and centroid in place
UPDATE districts
SET geometry = ST_GeomFromEWKT(:wkt),
    centroid = ST_GeomFromEWKT(:centroid_wkt)
WHERE id = :matched_district_id;
```
*Note*: Does not modify `id`, `name`, or `code`, preserving all 1,256 active foreign keys.

#### Taluks
```sql
-- Check existing taluk by unique code OR (district_id, name)
SELECT id FROM taluks WHERE code = :lgd_taluk_code;

-- If exists: update geometry and name
UPDATE taluks
SET name = :taluk_name,
    geometry = ST_GeomFromEWKT(:wkt),
    district_id = :parent_district_id
WHERE code = :lgd_taluk_code;

-- If not exists: insert new record
INSERT INTO taluks (id, district_id, name, code, geometry)
VALUES (gen_random_uuid(), :parent_district_id, :taluk_name, :lgd_taluk_code, ST_GeomFromEWKT(:wkt));
```

### 8.2 Invariant Guarantees
- Re-running ingestion $N$ times results in identical database row counts:
  - `SELECT count(*) FROM states;` $\to$ **1**
  - `SELECT count(*) FROM districts;` $\to$ **31**
  - `SELECT count(*) FROM taluks;` $\to$ **240**
- Zero duplicate rows created.
- Zero foreign key violations.

---

## 9. Transaction and Failure Policy

`DESIGN DECISION`: **Atomic Hierarchical Boundary**:
- Administrative geography forms an indivisible spatial hierarchy: State $\to$ Districts $\to$ Taluks.
- The entire ingestion must execute within a **single database transaction** (`session.begin()`).
- If a failure occurs at any stage (e.g. 1 geometry invalid, coordinate transformation error, containment failure, unmapped entity, database error):
  - The transaction executes an immediate, complete rollback (`session.rollback()`).
  - **Zero partial ingestion**: No scenario is permitted where some districts or taluks have geometries while others remain NULL.
  - The failure is logged in `data_ingestion_runs` with `status = 'FAILED'` and the exact error traceback.
  - Database state remains 100% pristine and unaltered.

---

## 10. Provenance Strategy

All administrative GIS ingestion must be tracked using the existing `data_sources` and `data_ingestion_runs` contract (`DECISIONS.md` D-025). **No new database columns or tables are created.**

### 10.1 DataSource Registration
```python
data_source = get_or_create_data_source(
    session,
    name="Karnataka State Remote Sensing Applications Centre (KSR-SAC) - Administrative GIS",
    organization="Karnataka State Remote Sensing Applications Centre (KSR-SAC), Dept of IT, BT and S&T, Govt of Karnataka",
    description="Official administrative boundaries for Karnataka State (1), Districts (31), and Taluks (240)",
    source_url="https://kgis.ksrsac.in/kgis/downloads.aspx",
    access_method="OFFICIAL_STANDARD",
    data_type="GEOSPATIAL",
    geographic_coverage="Karnataka State",
    update_frequency="STATIC",
    license_type="Government Open Data (Karnataka)",
)
```

### 10.2 DataIngestionRun Metrics
- `started_at`: UTC timestamp of run initiation.
- `completed_at`: UTC timestamp of run completion.
- `status`: `'SUCCESS'` or `'FAILED'`.
- `records_received`: 272 (1 state + 31 districts + 240 taluks).
- `records_inserted`: 240 (taluks inserted).
- `records_updated`: 32 (1 state + 31 districts updated).
- `records_failed`: 0.
- `error_message`: Detailed error message if failed, else `None`.

### 10.3 Repair Audit Trail
The 3 deterministically repaired taluk geometries (Shivamogga, Sringeri, Hosanagar) are recorded as `GeometryRepairRecord`s and serialized into the ingestion run summary log, preserving full auditability of:
- `feature_type`: `'taluk'`
- `kgis_code`: `'1506'`, `'1701'`, `'1504'`
- `lgd_code`: `'5520'`, `'5525'`, `'5518'`
- `issue_description`: Exact GEOS self-intersection coordinate
- `repair_operation`: `'shapely.make_valid'`
- `relative_area_diff`: $< 10^{-12}$

---

## 11. Implementation Plan (Phase 3.2 Roadmap)

1. **Step 1: Implement Adapter**: Create `backend/app/ingestion/sources/ksrsac_gis.py` (`KsrsacGisAdapter`), inheriting from `BaseAdapter`.
2. **Step 2: Leverage Existing Normalizer**: Call `KsrsacAdminNormalizer` (`app/gis/ksrsac.py`) to obtain `NormalizedState`, `NormalizedDistrict`s, and `NormalizedTaluk`s.
3. **Step 3: Execute In-Memory Pre-Insert Checks**: Validate all 12 geometry validation constraints before database operations.
4. **Step 4: Execute Atomic PostGIS Ingestion**:
   - Begin transaction.
   - Update State geometry.
   - Update 31 District geometries and centroids via bijective mapping.
   - Upsert 240 Taluks.
   - Record `DataIngestionRun`.
   - Commit transaction.
5. **Step 5: CLI Integration**: Add `ksrsac-gis` command to `backend/app/ingestion/cli.py`.
6. **Step 6: Comprehensive Verification**: Add unit and integration tests verifying PostGIS row counts, spatial index usage (`ST_Intersects`, `ST_Contains`), and idempotency.

---

## 12. Explicit Non-Goals

The following activities are explicitly out of scope for Phase 3.1 and Phase 3.2:
- **No Database Migrations**: The existing 34-table schema (`7eee813798dd` / `ccfc6a6b5d06`) already contains `geometry` columns and GiST indexes on `states`, `districts`, and `taluks`. No migration is needed or permitted.
- **No Prediction Grid Generation**: Creating a spatial prediction grid (e.g. 0.05° or 1 km cells) belongs to Phase 3.3.
- **No DEM Zonal Extraction**: Extracting Copernicus DEM elevation/slope statistics per administrative polygon belongs to Phase 3.4.
- **No Locality / Village Ingestion**: Ingesting village-level boundaries is out of scope for the 30-day MVP.
- **No Geometry Simplification**: No smoothing, tolerance-based decimation, or lossy geometry transformations.

---

## 13. Open Questions & Blockers

### Open Questions / Decisions Resolved

1. **District Code Discrepancy**:
   - `VERIFIED FACT`: In Phase 2.4, `KarnatakaGeographyAdapter` seeded `districts.code` with sequential integers (524–553, 744). KSR-SAC `District.shp` contains true LGD codes (524–550, 630, 631, 635, 738).
   - `DESIGN DECISION`: Modifying `districts.code` would violate `districts_code_key` during update due to overlapping codes and would invalidate `OpenMeteoAdapter` location mappings. Therefore, `districts.code` is left unmodified. Geometries are updated in place via the bijective name/alias mapping, preserving all 1,256 foreign key links.

2. **Taluk Code Selection**:
   - `DESIGN DECISION`: `taluks.code` will store `NormalizedTaluk.lgd_taluk_code` (e.g. `5520`), ensuring consistency with `DATA_CONTRACT.md` and `DECISIONS.md` D-014. The 4-digit KGIS code (e.g. `1506`) is preserved in the ingestion audit trail.

### Blockers
- **None**: All dependencies, source shapefiles, database tables, and validation libraries are fully verified, operational, and tested.
