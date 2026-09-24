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
- **System & Auditing (4):** `data_sources` (tracks provider provenance and `authority_level`), `data_ingestion_runs` (records pipeline metrics and `http_status_code`), `users`, `audit_logs`
- **Terrain Derived (1):** `terrain_statistics` (zonal elevation and slope features per district/sub-basin)

### 2. Physical Schema Rules
- **Primary Keys:** UUIDv4 generated via `gen_random_uuid()` on every table.
- **Timestamps:** `TIMESTAMP WITH TIME ZONE` (UTC) on all datetime fields.
- **Spatial Features:** PostGIS `GEOMETRY` in `EPSG:4326`, with GiST spatial indexes active on all 23 geometry columns.
- **Provenance:** `source_id`, `source_record_id`, `retrieved_at`, and `quality_status` recorded on all observation tables.
- **Referential Integrity:** Foreign keys use `ON DELETE NO ACTION` / `RESTRICT` to prevent accidental cascading data loss.
- **Nullability / `missing ≠ 0`:** Measurement columns (`water_level`, `discharge`, `rainfall_mm`, `flood_depth`, `storage_percentage`) are nullable and never default to zero or imputed values.
- **Check Constraints (51 active):** Enforce geographic coordinates (`[-90, 90]` latitude, `[-180, 180]` longitude), probability ranges (`[0.0, 1.0]`), percentage ranges (`[0.0, 100.0]`), and controlled vocabularies.

---

## Verified Source Field-to-Contract Translation Matrix

Established during Phase 2.3 empirical testing. Adapters must strictly adhere to these field translations and unit conversions.

### 1. NWIC / CWC Reservoir Telemetry (`karnataka_man_reservoir_data.csv`)
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `Reservoir Name` | string | `reservoirs.name` | string | Trim whitespace; map known aliases (e.g. `KRS` → `Krishnarajasagara`) |
| `Basin` | string | `reservoirs.basin_name` | string | Direct string assignment |
| `Monitoring Date` | string (`DD-MM-YYYY HH:mm:ss`) | `reservoir_observations.observed_at` | `TIMESTAMPTZ` (UTC) | Parse IST (`Asia/Kolkata`) string to UTC timestamp |
| `Reservoir Level (ft)` | feet | `reservoir_observations.water_level_m` | metres (`_m`) | $\text{Level}_{\text{m}} = \text{Level}_{\text{ft}} \times 0.3048$ |
| `Gross Capacity (TMC)` | TMC | `reservoir_observations.storage_mcm` | MCM (`_mcm`) | $\text{Storage}_{\text{MCM}} = \text{Storage}_{\text{TMC}} \times 28.3168$ |
| `Percentage Full` | percentage | `reservoir_observations.storage_percentage` | percentage (`_pct`) | Direct float assignment ($[0.0, 100.0]$) |
| `Inflow (Cusecs)` | cusecs (ft³/s) | `reservoir_observations.inflow_m3s` | m³/s (`_m3s`) | $\text{Inflow}_{\text{m}^3/\text{s}} = \text{Inflow}_{\text{cusecs}} \times 0.0283168$ |
| `Outflow to River (Cusecs)` | cusecs (ft³/s) | `reservoir_observations.outflow_m3s` | m³/s (`_m3s`) | $\text{Outflow}_{\text{m}^3/\text{s}} = \text{Outflow}_{\text{cusecs}} \times 0.0283168$ |

### 2. NWIC / CWC River Water Level (`rwl_manual_hr_cwc_*.csv`)
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `Station` | string | `river_stations.name` | string | Direct string assignment |
| `River` | string | `rivers.name` | string | Direct string assignment |
| `Basin` | string | `river_basins.name` | string | Direct string assignment |
| `Latitude` | decimal degrees | `river_stations.latitude` | degrees | Validate in $[11.5, 18.5]$; construct PostGIS `geom` (EPSG:4326) |
| `Longitude` | decimal degrees | `river_stations.longitude` | degrees | Validate in $[74.0, 78.6]$; construct PostGIS `geom` (EPSG:4326) |
| `State LGD Code` | integer (`29`) | `river_stations.state_lgd_code` | integer | Reference validation against Karnataka (`29`) |
| `District LGD Code` | integer | `river_stations.district_lgd_code` | integer | Foreign key / lookup link to `districts.lgd_code` |
| `Data Acquisition Time` | string (`DD-MM-YYYY HH:mm`) | `river_observations.observed_at` | `TIMESTAMPTZ` (UTC) | Parse IST string to UTC timestamp |
| `River Water Level Manual Hourly (meter)` | metres | `river_observations.water_level_m` | metres (`_m`) | Direct float assignment |
| `Is_DischargeDataAvailable` | "Yes" / "No" | `river_observations.discharge_m3s` | m³/s (`_m3s`) | If "No" or missing, set explicitly to `NULL` (`missing ≠ 0`) |

### 3. Open-Meteo Weather API (`v1/forecast` & `v1/archive`)
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `current.time` | ISO 8601 string | `weather_observations.observed_at` | `TIMESTAMPTZ` (UTC) | Parse ISO 8601 UTC timestamp |
| `current.temperature_2m` | °C | `weather_observations.temperature_c` | °C (`_c`) | Direct float assignment |
| `current.relative_humidity_2m` | % | `weather_observations.humidity_pct` | % (`_pct`) | Direct float assignment |
| `current.precipitation` | mm | `rainfall_observations.rainfall_mm` | mm (`_mm`) | Direct float assignment ($\ge 0.0$) |
| `current.wind_speed_10m` | m/s | `weather_observations.wind_speed_mps` | m/s (`_mps`) | Direct float assignment (enforce `wind_speed_unit=ms` in query) |
| `hourly.surface_pressure` | hPa | `weather_observations.pressure_hpa` | hPa (`_hpa`) | Direct float assignment |
| `hourly.time` | ISO 8601 array | `weather_forecasts.forecast_for` | `TIMESTAMPTZ` (UTC) | Parse ISO 8601 UTC timestamp |
| `hourly.precipitation` | mm array | `weather_forecasts.rainfall_forecast_mm` | mm (`_mm`) | Direct float assignment ($\ge 0.0$) |

### 4. India Flood Inventory v3.0 (`India_Flood_Inventory_v3.csv`)
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `UEI` | string | `flood_observations.source_record_id` | string | Unique event identifier (e.g. `UEI-IMD-FL-2023-0347`) |
| `Start Date` | string (`DD-MM-YYYY HH:mm`) | `flood_events.start_date` | `TIMESTAMPTZ` (UTC) | Parse IST string to UTC timestamp |
| `End Date` | string (`DD-MM-YYYY HH:mm`) | `flood_events.end_date` | `TIMESTAMPTZ` (UTC) | Parse IST string to UTC timestamp |
| `Duration(Days)` | integer / float | `flood_events.duration_days` | integer | Cast to integer days |
| `State_Codes` | string / int (`29`) | Reference validation | int | Must equal `29` (Karnataka) |
| `District_LGD_Codes` | comma-separated ints | `flood_observations.district_id` | UUID | Join via `districts.lgd_code` |
| `Main Cause` | string | `flood_events.description` | string | Retain text |
| `Human fatality` | integer | `flood_observations.fatalities` | integer | Cast to integer ($\ge 0$) |
| Derived target | boolean | `flood_observations.flooded` | boolean | Set to `TRUE` for documented event records |

### 5. OpenStreetMap Overpass QL
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `node.id` | integer | `emergency_facilities.source_record_id` | string | Store as string identifier |
| `tags.name` | string | `emergency_facilities.name` | string | Direct string assignment (fallback to `"Unnamed Facility"`) |
| `tags.amenity` | "hospital" / "clinic" | `emergency_facilities.facility_type` | string | Map to `"hospital"` |
| `tags.amenity` | "fire_station" | `emergency_facilities.facility_type` | string | Map to `"fire_station"` |
| `lat`, `lon` | decimal degrees | `emergency_facilities.latitude`, `longitude`, `geom` | EPSG:4326 | Construct PostGIS Point `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` |
| `occupancy` | N/A | `emergency_facilities.current_occupancy` | integer | Set explicitly to `NULL` (unknown) |

### 6. Historical District × Day Flood Labels (`district_day_flood_labels`)
| Source Field Name | Source Unit | Target Schema Table & Column | Target Unit | Mandatory Conversion / Parsing Rule |
|---|---|---|---|---|
| `District_LGD_Codes` / `Districts` | string / LGD code | `district_day_flood_labels.district_id` | UUID | Resolve to canonical `districts.id` via KSR-SAC normalization |
| Date interval | `DD-MM-YYYY` (IST) | `district_day_flood_labels.event_date` | `DATE` (UTC) | Expand inclusive daily interval, convert IST midnight to UTC date |
| Label state | categorical | `district_day_flood_labels.label` | `VARCHAR(20)` | Strictly `'FLOOD'`, `'NO_FLOOD'`, or `'UNKNOWN'` |
| Occurrence | discrete binary | `district_day_flood_labels.flood_occurrence` | `SMALLINT` | `1` for FLOOD, `0` for NO_FLOOD, `NULL` for UNKNOWN |
| Event count | count | `district_day_flood_labels.event_count` | `INTEGER` | Number of distinct overlapping IFI disaster events ($\ge 0$) |
| `UEI` | string | `district_day_flood_labels.source_event_ids` | `JSONB` | Array of sorted unique source UEIs (`['UEI-...']`) |
| `Main Cause` | string | `district_day_flood_labels.main_causes` | `JSONB` | Sorted array of unique cause strings |
| `Severity` | string | `district_day_flood_labels.severities` | `JSONB` | Sorted array of unique reported severity classes |
| `Human fatality` | integer | `district_day_flood_labels.fatalities` | `INTEGER` | Cumulative sum of fatalities across consolidated events |
| `Human Displaced`| integer | `district_day_flood_labels.displaced` | `INTEGER` | Cumulative sum of displaced persons across consolidated events |

#### Downstream ML Join Interface
* **Spatial Join Key:** `district_id` (UUID) $\leftrightarrow$ `districts.id` / `kgis_district_code` (`'01'` to `'31'`)
* **Temporal Join Key:** `event_date` (Date, UTC) $\leftrightarrow$ `observation_date` (Date, UTC)
* **Join Graph:**
  * `district_day_flood_labels` (Target: `label`, `flood_occurrence`)
  * $\bowtie_{(\text{district\_id}, \text{date})}$ `era5_daily` (Weather predictors: `precipitation_sum_mm`, `temperature_max_c`, etc.)
  * $\bowtie_{(\text{district\_id})}$ `terrain_statistics` (Topographic predictors: `elevation_mean_m`, `slope_mean_deg`, etc.)
  * $\bowtie_{(\text{district\_id})}$ `district_river_basins` / hydrological stations (Catchment and river network predictors)

