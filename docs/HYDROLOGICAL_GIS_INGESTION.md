# Hydrological GIS Ingestion Foundation

**Project:** FloodPulse (Karnataka Flood Prediction Platform)  
**Status:** Ingestion & Schema Implemented  
**Date:** September 2026  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPEC.md`
- `docs/CONSTRAINTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_CONTRACT.md`
- `docs/GIS_POSTGIS_INGESTION_DESIGN.md`

---

## 1. Overview & Objectives

The Hydrological GIS Ingestion Foundation provides the authoritative spatial and topological framework for hydrological modeling, rainfall-runoff routing, and flood risk analysis across Karnataka.

It ingests three empirically verified hydrological GIS datasets into PostGIS (PostgreSQL 16 / PostGIS 3.4), extends the relational schema with domain-specific hydrological and topological attributes, and computes many-to-many spatial crosswalks between administrative districts and hydrological units.

### Three Distinct Hydrological Layers

| Layer | Source / Agency | Conceptual Role | Target Table | Features (KA) |
|---|---|---|---|---|
| **CWC Major Basins** | Central Water Commission / NWDP | Statutory national basin boundaries (authoritative governance reference) | `river_basins` | 25 national (7 intersect KA) |
| **HydroBASINS Level-7** | HydroSHEDS / WWF & USGS | Hydrological sub-catchment topology (drainage DAG, Pfafstetter coding) | `sub_basins` | 116 catchments intersecting KA |
| **HydroRIVERS v1.0** | HydroSHEDS / WWF & USGS | Hydrographic river reach network (Strahler order, discharge, reach routing) | `rivers` | 15,369 reaches intersecting KA |

> [!IMPORTANT]
> **Statutory vs Hydrological Distinction:**  
> CWC major basins represent statutory jurisdiction defined by the Government of India. HydroBASINS Level-7 polygons are hydrologically delineated watershed boundaries based on digital elevation models (SRTM). HydroBASINS Level-7 features do **not** nest cleanly inside CWC statutory basins. Therefore, the schema decouples `sub_basins.basin_id` (made nullable) and instead maps district and basin overlaps through explicit spatial crosswalk tables (`district_sub_basins` and `district_river_basins`).

---

## 2. Source Archives & Provenance

All source archives are stored under `data/raw/gis/hydrosheds/` and are read directly without unzipping to disk:

| Dataset | File Path | Archive SHA-256 | Native CRS | Native Features |
|---|---|---|---|---|
| **CWC Major Basins** | `data/raw/gis/hydrosheds/basin_cwc_shp.zip` | `9d81ea8052d19213fb46a8ca8c772c69435607db58064c585586ae5fba1ce790` | EPSG:7755 (Kalianpur 1975 / India Zone I) | 25 national basins |
| **HydroBASINS L7** | `data/raw/gis/hydrosheds/hybas_as_lev07_v1c.zip` | `3ad218066cc15fa9ab5a69ee01d9df502bb113ec4cf043f114c000d667c4852e` | EPSG:4326 (WGS 84) | 8,811 (Asia) |
| **HydroRIVERS v1.0** | `data/raw/gis/hydrosheds/HydroRIVERS_v10_as_shp.zip` | `29780b0a75f9180775d78fa1b490db7f9aa5408892795ecb5fa4b4baeb23769c` | EPSG:4326 (WGS 84) | 845,953 (Asia) |

---

## 3. Schema Architecture & Extensions

Alembic migration `f75e4ffc014c_add_hydrological_gis_foundation_tables_` introduced the following schema enhancements:

### 3.1 `river_basins` (Extended)
- `id` (UUID, PK) — existing placeholder UUIDs for Cauvery and Krishna preserved.
- `name` (VARCHAR(100), NOT NULL) — CWC basin name (`ba_name` in source).
- `code` (VARCHAR(20), NULL) — CWC basin code (`bacode` in source).
- `geometry` (GEOMETRY(MULTIPOLYGON, 4326)) — transformed from EPSG:7755 to EPSG:4326.
- `source_agency` (VARCHAR(200)) — `"CWC/NWDP"`.
- `source_dataset` (VARCHAR(200)) — `"basin_cwc_shp"`.
- `source_version` (VARCHAR(50)) — `"1.0"`.
- `source_feature_id` (VARCHAR(100), UNIQUE) — CWC basin code.
- `area_km2` (FLOAT) — reported basin area.
- `intersects_karnataka` (BOOLEAN) — `TRUE` for the 7 basins intersecting Karnataka:
  - Krishna
  - Cauvery
  - West Flowing Rivers from Tadri to Kanyakumari
  - Godavari
  - Pennar
  - Minor Rivers draining into Myanmar (non-KA, flag False)
  - East Flowing Rivers between Pennar and Cauvery
  - West Flowing Rivers from Tapi to Tadri

### 3.2 `sub_basins` (Extended for HydroBASINS)
- `id` (UUID, PK).
- `basin_id` (UUID, NULL) — altered to nullable (decoupling HydroBASINS from CWC basins).
- `name` (VARCHAR(100), NOT NULL) — format: `"HYBAS_{hybas_id}"`.
- `geometry` (GEOMETRY(MULTIPOLYGON, 4326)).
- `hybas_id` (BIGINT, UNIQUE) — HydroBASINS unique identifier.
- `next_down` (BIGINT) — ID of the downstream neighbor (0 = sink / coast).
- `next_sink` (BIGINT) — ID of final terminal sink / outlet.
- `main_bas` (BIGINT) — ID of the major river basin.
- `sub_area` (FLOAT) — sub-basin catchment area in km².
- `up_area` (FLOAT) — cumulative upstream drainage area in km².
- `pfaf_id` (BIGINT) — Pfafstetter hierarchical watershed code.
- `endo` (INTEGER) — 1 if endorheic (inland sink), 0 if exorheic (flows to ocean).
- `coast` (INTEGER) — 1 if coastal catchment, 0 otherwise.
- `dist_sink` (FLOAT) — distance along flow path to sink (km).
- `dist_main` (FLOAT) — distance to main channel (km).
- `order_` (INTEGER) — stream order indicator.
- `sort` (BIGINT) — topological sort order.
- `source_dataset` — `"hybas_as_lev07_v1c"`.
- `geometry_repaired` (BOOLEAN) — tracks if self-intersecting source rings were repaired via `ST_MakeValid`.

### 3.3 `rivers` (Extended for HydroRIVERS)
- `id` (UUID, PK) — existing placeholder UUIDs preserved.
- `name` (VARCHAR(100), NOT NULL) — format: `"HYRIV_{hyriv_id}"`.
- `geometry` (GEOMETRY(MULTILINESTRING, 4326)).
- `hyriv_id` (BIGINT, UNIQUE) — HydroRIVERS reach ID.
- `next_down` (BIGINT) — downstream reach ID (0 = terminal outlet).
- `main_riv` (BIGINT) — identifier of main stem river.
- `length_km` (FLOAT) — reach length in km.
- `dist_dn_km` (FLOAT) — distance to outlet / ocean (km).
- `dist_up_km` (FLOAT) — distance from headwaters (km).
- `catch_skm` (FLOAT) — sub-catchment area of reach (km²).
- `upland_skm` (FLOAT) — total upstream catchment area (km²).
- `dis_av_cms` (FLOAT) — long-term average discharge (m³/s).
- `ord_stra` (INTEGER) — Strahler stream order.
- `ord_clas` (INTEGER) — classic Shreve/Horton stream order.
- `ord_flow` (INTEGER) — flow-connectivity order.
- `hybas_l12` (BIGINT) — corresponding HydroBASINS Level-12 sub-basin ID.

### 3.4 Spatial Crosswalk Tables
Because administrative districts and watershed units overlap non-hierarchically, two crosswalk tables capture exact spatial intersections:

#### `district_sub_basins`
- `district_id` (FK → `districts.id`).
- `sub_basin_id` (FK → `sub_basins.id`).
- `intersection_geometry` (GEOMETRY(MULTIPOLYGON, 4326)).
- `intersection_area_km2` (FLOAT) — calculated using EPSG:32643 projection.
- `percent_of_subbasin_in_district` (FLOAT) — percentage of sub-basin area falling in district.
- `percent_of_district_in_subbasin` (FLOAT) — percentage of district area falling in sub-basin.
- `derivation_method` — `"PostGIS ST_Intersection"`.

#### `district_river_basins`
- `district_id` (FK → `districts.id`).
- `river_basin_id` (FK → `river_basins.id`).
- `intersection_geometry` (GEOMETRY(MULTIPOLYGON, 4326)).
- `intersection_area_km2` (FLOAT) — calculated using EPSG:32643 projection.
- `percent_of_basin_in_district` (FLOAT).
- `percent_of_district_in_basin` (FLOAT).
- `derivation_method` — `"PostGIS ST_Intersection"`.

---

## 4. Geometry Normalization & Repair Policy

1. **Non-destructive read:** Archives are inspected and read directly into memory via GeoPandas and Shapely (`zip://...`).
2. **Coordinate Transformation:** CWC shapefile (`basin_cwc_shp.zip`) native coordinate reference system is EPSG:7755. It is transformed to EPSG:4326 using standard Proj transformations.
3. **Polygon Repair:** HydroBASINS Level-7 has 3 known self-intersecting polygon rings in Asia Level-7 (`4071118950`, `4071142370`, `4070030670`). When detected, `shapely.validation.make_valid` repairs the topology, extracts the polygon component, and sets `geometry_repaired = True`.
4. **Transboundary Catchment Integrity:** HydroBASINS catchments that cross Karnataka's border are **not clipped** to the state border. Preserving the complete catchment geometry is critical so that total upstream rainfall and drainage area calculations remain hydrologically accurate.
5. **Sliver Elimination in Crosswalks:** Spatial intersections between districts and sub-basins with areas $< 0.01\text{ km}^2$ (boundary artifacts) are filtered out.

---

## 5. Topology Validation

The module `app.gis.topology_validation` enforces strict mathematical rules prior to persistence:
- **Uniqueness:** All `HYBAS_ID` and `HYRIV_ID` values must be strictly unique.
- **DAG Verification:** The drainage network directed graph ($u \to v$ where $v = \text{next\_down}$) is traversed using cycle-detection algorithms (DFS / Tarjan's). Cycles are disallowed.
- **Self-reference Guard:** Features cannot point downstream to themselves ($\text{next\_down} \neq \text{id}$).
- **Terminal Sinks:** Nodes pointing to downstream targets of `0` or nodes outside Karnataka are classified as valid terminal boundary outlets.

---

## 6. Execution & Verification

### Running Ingestion via CLI
```bash
# Ingest all hydrological layers and compute crosswalks
python -m app.ingestion.cli hydro-gis

# Ingest specific layers
python -m app.ingestion.cli hydro-gis --layer cwc
python -m app.ingestion.cli hydro-gis --layer hydrobasins
python -m app.ingestion.cli hydro-gis --layer hydrorivers
python -m app.ingestion.cli hydro-gis --layer crosswalk
```

### Running Automated Test Suite
```bash
pytest backend/tests/test_hydrological_gis.py -v
```
