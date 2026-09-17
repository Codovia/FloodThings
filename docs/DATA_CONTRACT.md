# DATA_CONTRACT.md

**Project:** FloodPulse
**Status:** Implemented in PostgreSQL/PostGIS foundation (Phase 2.2).
34 application tables, 23 spatial columns (EPSG:4326), 23 GiST indexes, 51 check constraints enforcing coordinates, probabilities, and vocabularies, full UTC TIMESTAMPTZ timestamps, explicit provenance metadata, and strict NULL preservation (`missing ≠ 0`).

---

## Time

### Internal timestamps

All internal timestamps use **UTC**.

```
stored_at:    UTC
observed_at:  UTC
retrieved_at: UTC
forecast_for: UTC
issued_at:    UTC
```

### Display timezone

User-facing display converts to **IST** (Indian Standard Time, UTC+05:30).

```
Display timezone: Asia/Kolkata (IST, UTC+05:30)
```

### Date-only fields

Observation dates without a time component use ISO 8601 date format:

```
YYYY-MM-DD
```

---

## Units

All measurements must use explicit, documented units. No implicit or ambiguous units.

| Measurement | Unit | Field suffix |
|---|---|---|
| Rainfall | millimetres | `_mm` |
| Water level | metres | `_m` |
| River discharge | cubic metres per second | `_m3s` |
| Reservoir storage | million cubic metres | `_mcm` |
| Temperature | degrees Celsius | `_c` |
| Wind speed | metres per second | `_mps` |
| Pressure | hectopascals | `_hpa` |
| Humidity | percentage | `_pct` |
| Distance | kilometres | `_km` |
| Elevation | metres | `_m` |
| Slope | degrees or percentage (must be documented) | `_deg` or `_pct` |
| Area | square kilometres | `_km2` |
| Latitude / Longitude | decimal degrees (WGS84) | `lat`, `lon` |

---

## Missingness

```
missing ≠ zero
```

- A missing rainfall observation means "no data available," not "no rain."
- A missing water level means "no reading," not "dry."
- A missing shelter occupancy means "unknown," not "empty."

Unknown values must remain explicitly unknown:
- `NULL` in the database.
- Clearly flagged in API responses.
- Visually distinct in the frontend.

Never silently replace a missing value with:
- Zero
- A median or mean
- A stale previous value presented as current
- A model-generated fill presented as an observation

---

## Provenance

All important records should retain provenance metadata:

| Field | Purpose |
|---|---|
| `source` | The data source identifier (e.g., `imd_gridded_rainfall`, `cwc_nwdp`) |
| `source_record_id` | The original record identifier from the source, if any |
| `observed_at` | When the measurement was taken (UTC) |
| `retrieved_at` | When FloodPulse retrieved the data from the source (UTC) |
| `quality` or `status` | Data quality flag or validation status |
| `processing_version` | Version of the ingestion/transformation pipeline |

---

## Data freshness

Track the age and availability of data:

| Status | Meaning |
|---|---|
| `FRESH` | Retrieved within the expected update window for this source |
| `STALE` | Older than the expected update window; still the most recent available |
| `UNAVAILABLE` | Source could not be reached or returned no data |

Freshness thresholds are source-specific and will be defined when each source adapter is implemented. Do not use arbitrary default thresholds.

A stale or unavailable status must be:
- Stored alongside the data.
- Exposed through the API.
- Displayed in the frontend.

---

## Coordinate reference system

Default CRS for point exchange (APIs, storage):

```
EPSG:4326 (WGS 84)
```

For distance and area calculations, use an appropriate projected CRS or PostGIS geography type. Document the CRS used at every spatial operation.

---

## Validation at ingestion

Every data value entering the system must pass validation:

- Type checking (numeric, date, string, geometry).
- Range checking (e.g., rainfall_mm ≥ 0, latitude within Karnataka bounds).
- Completeness checking (required fields present).
- Duplicate detection.
- CRS validation for spatial data.

Invalid data is rejected or flagged — never silently accepted.

---

## Phase 2.2 Database Schema Enforcement

The data contract is physically enforced in the PostgreSQL/PostGIS database via Alembic migration `7eee813798dd`.

### 1. Persistence Matrix (34 Tables)
- **Geography (4):** `states`, `districts`, `taluks`, `localities`
- **Hydrology (8):** `river_basins`, `sub_basins`, `rivers`, `river_stations`, `river_observations`, `river_forecasts`, `reservoirs`, `reservoir_observations`
- **Weather & Rainfall (3):** `weather_observations`, `rainfall_observations`, `weather_forecasts`
- **Flood Intelligence (3):** `flood_observations`, `flood_events`, `flood_hazard_zones`
- **Terrain & Land Cover (3):** `land_covers`, `water_bodies`, `terrain_datasets`
- **Prediction & ML (5):** `prediction_grid_cells`, `feature_snapshots`, `ml_dataset_versions`, `ml_models`, `flood_predictions`
- **Emergency Management (2):** `emergency_facilities`, `community_reports`
- **Alerts & Messaging (2):** `alerts`, `telegram_subscriptions`
- **System & Auditing (4):** `data_sources`, `data_ingestion_runs`, `users`, `audit_logs`

### 2. Physical Schema Rules
- **Primary Keys:** UUIDv4 generated via `gen_random_uuid()` on every table.
- **Timestamps:** `TIMESTAMP WITH TIME ZONE` (UTC) on all datetime fields.
- **Spatial Features:** PostGIS `GEOMETRY` in `EPSG:4326`, with GiST spatial indexes active on all 23 geometry columns.
- **Provenance:** `source_id`, `source_record_id`, `retrieved_at`, and `quality_status` recorded on all observation tables.
- **Referential Integrity:** Foreign keys use `ON DELETE NO ACTION` / `RESTRICT` to prevent accidental cascading data loss.
- **Nullability / `missing ≠ 0`:** Measurement columns (`water_level`, `discharge`, `rainfall_mm`, `flood_depth`, `storage_percentage`) are nullable and never default to zero or imputed values.
- **Check Constraints (51 active):** Enforce geographic coordinates (`[-90, 90]` latitude, `[-180, 180]` longitude), probability ranges (`[0.0, 1.0]`), percentage ranges (`[0.0, 100.0]`), and controlled vocabularies.
