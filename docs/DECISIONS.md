# DECISIONS.md

**Project:** FloodPulse
**Status:** Active decision register. Entries are permanent history — never delete an entry, only add a newer one that supersedes it.

---

## Confirmed decisions

---

**D-001 — Application architecture**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** React + Vite + FastAPI + PostgreSQL/PostGIS modular monolith.
**Context:** The project needs a full-stack web application with spatial database support. The specification explicitly establishes this stack and prohibits microservices, Kubernetes, Kafka, blockchain, native mobile, chatbot, SMS, and email.
**Affected components:** All.
**Reversal conditions:** None anticipated.

---

**D-002 — Real-data requirement**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** Environmental and operational data must come from real, attributable sources. No fabricated environmental observations, ever.
**Context:** The prior FloodPrediction prototype manufactured several fields (synthetic daily rainfall from annual totals, formula-generated reservoir values, a hand-written risk score used as an ML label). This must not recur.
**Affected components:** All data ingestion, ML pipeline, feature engineering.
**Reversal conditions:** None — non-negotiable per CONSTRAINTS.md.

---

**D-003 — Initial notification channel**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** Telegram is the initial and primary notification channel.
**Context:** The specification selects Telegram for alerts. SMS and email are explicitly out of scope.
**Affected components:** Alert engine, Telegram integration.
**Reversal conditions:** None anticipated for the 30-day scope.

---

**D-004 — Database strategy**
**Date:** 2026-09-16
**Status:** CONFIRMED FOR PHASE 0
**Decision:** FloodPulse development database uses the Docker PostGIS container (`floodpulse-postgres`, PostgreSQL 16, PostGIS 3.4.3, port 5432) rather than the host PostgreSQL 18 instance on port 5433.
**Context:** Two PostgreSQL instances exist on the development machine. The Docker container provides PostGIS and is isolated from the host system database. The host PostgreSQL 18 on port 5433 may be used by other projects.
**Affected components:** All database connections, `docker-compose.yml`, `.env`.
**Reversal conditions:** If the Docker approach becomes impractical, revisit.

---

**D-005 — Python runtime**
**Date:** 2026-09-16
**Status:** CONFIRMED FOR PROJECT
**Decision:** Use Python 3.12 for the project runtime (Docker images, virtual environments) unless a later evidence-based decision changes this.
**Context:** The development machine has Python 3.14.4 (system), but many ML/GIS libraries (scikit-learn, numpy, geopandas, psycopg2-binary) may have limited or no binary wheels for Python 3.14. The prior working Dockerfile used `python:3.12-slim`. Python 3.12 is stable and broadly supported.
**Affected components:** Dockerfile, virtual environments, CI.
**Reversal conditions:** If all required libraries gain confirmed Python 3.14 support, this can be revisited.

---

**D-006 — ML train/test split strategy**
**Date:** 2026-09-16
**Status:** CONFIRMED
**Decision:** All ML train/test splits are time-based, never random.
**Context:** Flood risk is a time-series problem. A random split leaks future rainfall patterns and events into training. The model must be trained on the past and evaluated on the future.
**Affected components:** ML training, ML evaluation.
**Reversal conditions:** None — this is a hard rule per CONSTRAINTS.md.

---

**D-010 — Primary ML ground-truth target source**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use the India Flood Inventory (IFI v3.0, IIT Delhi HydroSense Lab) at District × Day resolution as the primary ground truth for supervised flood occurrence modeling.
**Context:** IFI provides 494 verified historical flood events across Karnataka from 1969 to 2023 with LGD district codes, dates, and damage statistics compiled from IMD Disastrous Weather Reports. It is completely independent of rainfall feature calculation. Locality/taluk-level continuous labels do not exist and must not be fabricated.
**Affected components:** ML pipeline, `flood_observations`, `flood_events`, feature store.
**Reversal conditions:** Only if an officially gazetted, sub-district continuous disaster registry is released.

---

**D-011 — Primary operational weather source**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use Open-Meteo Weather Forecast & Archive API as the primary operational weather and forecast source; use NASA POWER as a secondary reference.
**Context:** Open-Meteo was experimentally verified (HTTP 200) with current, hourly, and 7-day forecast precipitation, temperature, humidity, and wind speed in SI units. It requires no credentials. IMD's official API requires institutional registration and a static public IP address (currently credential-blocked). All Open-Meteo data must be stored with source="open_meteo" and classified as MODEL_OUTPUT / DERIVED_FROM_REAL.
**Affected components:** Weather ingestion, `weather_observations`, `weather_forecasts`, `rainfall_observations`.
**Reversal conditions:** If official IMD API credentials and static public IP are provisioned.

---

**D-012 — Hydrological and reservoir data sources**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use NWIC National Water Data Portal open datasets for reservoir telemetry (`karnataka_man_reservoir_data.csv`) and CWC in-situ river gauge monitoring (`rwl_manual_hr_cwc_*.csv`).
**Context:** Empirical range tests verified continuous daily reservoir records (1990–2026) for major Karnataka dams and hourly river gauge water levels for Karnataka river basins. Units must follow mandatory conversion contracts: feet → metres (`× 0.3048`), TMC → MCM (`× 28.3168`), cusecs → m³/s (`× 0.0283168`). Missing river discharge must remain NULL (`missing ≠ zero`).
**Affected components:** Hydrology ingestion, `reservoirs`, `reservoir_observations`, `rivers`, `river_stations`, `river_observations`.
**Reversal conditions:** None.

---

**D-013 — Digital Elevation Model source**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use Copernicus DEM GLO-30 (30m Cloud Optimized GeoTIFF on AWS Open Data, EPSG:4326) as the authoritative terrain baseline.
**Context:** Range queries verified HTTP 200/206 access with EGM2008 elevation datum and zero authentication requirements. It provides superior vertical accuracy (<2m relative error) compared to 2000-era SRTM. Zonal slope (degrees) and elevation statistics will be dynamically extracted per district and taluk polygon.
**Affected components:** Terrain ingestion, GIS feature engineering, `terrain_datasets`.
**Reversal conditions:** If Survey of India provides an open high-resolution LiDAR DTM.

---

**D-014 — Administrative boundary and code normalization**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Standardize all administrative entities using Local Government Directory (LGD State Code 29) codes; ingest official KSRSAC boundary shapefiles with Datameet Census 2011 WGS84 shapefiles as secondary validation reference.
**Context:** LGD codes are verified in both CWC hydrology data and IFI flood event records, enabling strict referential integrity. Direct automated script downloads from KGIS legacy paths are unstable (IIS 404/403), requiring offline curated boundary ingestion.
**Affected components:** Geography models (`states`, `districts`, `taluks`), GIS pipelines.
**Reversal conditions:** If KGIS provides a stable authenticated OGC WFS service.

---

**D-015 — Emergency shelter acquisition policy**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Strictly prohibit using OpenStreetMap `amenity=shelter` as flood evacuation shelters. Populate designated evacuation shelters solely by manual curation from official published District Disaster Management Plan (DDMP) PDF annexures. Keep shelter occupancy strictly NULL.
**Context:** Phase 1 research confirmed no open machine-readable shelter API exists in Karnataka. Conflating generic OSM shelters (bus shelters, gazebos) with flood relief camps creates severe safety risks. Real-time occupancy telemetry does not exist; unknown occupancy must never be inferred as available capacity per CONSTRAINTS.md.
**Affected components:** Emergency response, `emergency_facilities`, shelter finder, routing.
**Reversal conditions:** If KSDMA launches an authoritative public API for shelter telemetry.

---

**D-016 — GloFAS credential deferral**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Mark GloFAS as CREDENTIAL_BLOCKED and defer integration until user credentials are provided in ~/.cdsapirc; exclude GloFAS from Phase 2 blocking dependencies.
**Context:** Unauthenticated CDS API calls fail under the modern ECMWF/Copernicus platform. Phase 2 can proceed with full hydrological integrity using in-situ CWC river water level telemetry from NWIC.
**Affected components:** River forecasting, `river_forecasts`.
**Reversal conditions:** When CDS user token is configured and GloFAS terms of use are accepted.

---

**D-018 — Primary key strategy: UUIDv4**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use UUIDv4 (`gen_random_uuid()`) for primary keys across all 34 application tables.
**Context:** Distributes key generation safely across distributed clients, workers, and offline sync nodes (community reports, telemetry collectors) without sequential integer ID collision risks.
**Affected components:** All SQLAlchemy models, Alembic migrations, database schema.
**Reversal conditions:** None.

---

**D-019 — Spatial representation and indexing: PostGIS EPSG:4326 + GiST**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Standardize all spatial representations as PostGIS `GEOMETRY(..., 4326)` with explicit GiST spatial indexes.
**Context:** EPSG:4326 (WGS84 lat/lon) is the native coordinate system for GPS, GeoJSON, and open environmental telemetry. Explicit GiST indexing ensures high-speed bounding-box and distance queries across Karnataka polygons, stream lines, and sensor points.
**Affected components:** All spatial tables (23 geometry columns), GIS queries, Alembic migrations.
**Reversal conditions:** None.

---

**D-020 — Controlled vocabularies via String and SQL Check Constraints**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Implement enumeration and status fields using `String(VARCHAR)` columns backed by explicit SQL `CheckConstraint`s rather than native PostgreSQL ENUM types.
**Context:** Native PostgreSQL ENUM types introduce substantial migration friction in Alembic (e.g., modifying enum values requires non-transactional `ALTER TYPE`). SQL check constraints allow transactional modifications, straightforward testing, and clear error messages while guaranteeing strict data contract enforcement.
**Affected components:** All status, severity, and quality columns across models.
**Reversal conditions:** None.

---

**D-021 — Semi-structured metadata via PostgreSQL JSONB**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Use PostgreSQL `JSONB` for auxiliary, extensible, or source-specific metadata fields (e.g., `TerrainDataset.metadata_json`, `MLModel.hyperparameters`, `MLModel.metrics`).
**Context:** Core relational attributes and physical measurements remain strictly typed in structured columns. Dynamic source attributes and ML run configs are indexed and queried via JSONB without altering schema tables.
**Affected components:** `terrain_datasets`, `ml_models`, `ml_dataset_versions`.
**Reversal conditions:** None.

---

**D-022 — Foreign key referential integrity: ON DELETE NO ACTION**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Enforce `ON DELETE NO ACTION` / `RESTRICT` on all foreign key constraints.
**Context:** Strictly prohibits cascading deletes that could unintentionally erase historical hydrologic observations, sensor telemetry, or citizen reports when a parent reference or geography is modified or decommissioned.
**Affected components:** All foreign key constraints across the schema.
**Reversal conditions:** None.

---

**D-023 — Official API validation lab verification findings**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Base all Phase 2 data acquisition strictly on empirical API testing results rather than speculative documentation assumptions:
1. IMD API Gateway (`api.imd.gov.in`) is functional but credential-gated (`HTTP 401 Unauthorized`, `{"error":"API key missing"}`) with onboarding restricted to `@gov.in` institutional domains. It is classified as `CREDENTIAL_BLOCKED` and excluded from Phase 2 blocking path.
2. NWIC National Water Data Portal (`nwdp.nwic.gov.in`) CKAN REST API is completely open (`HTTP 200 OK`) and provides 45 verified Karnataka datasets including multi-decade daily reservoir telemetry and hourly river stage telemetry.
3. NRSC NDEM portal is institutional only (requiring disaster officer login & OTP); no public REST/WFS API exists. Screen scraping is strictly prohibited.
4. Bhuvan OGC vector WMS endpoints time out from non-institutional networks; Bhuvan is restricted to human portal visualization.
5. Open-Meteo Weather, Archive, and Flood (GloFAS) REST APIs are verified (`HTTP 200 OK`) with native SI units matching `DATA_CONTRACT.md`.
**Context:** Empirical probing during Phase 2.3 provided concrete evidence of access methods, error behaviors, and real response schemas.
**Affected components:** Data acquisition adapters, `DATA_SOURCES.md`, `API_VALIDATION_LAB.md`.
**Reversal conditions:** None.

---

**D-024 — Verified ingestion source selection for Phase 2.4**
**Date:** 2026-09-17
**Status:** CONFIRMED
**Decision:** Authorize specific verified sources for Phase 2.4 adapter development:
1. `OpenMeteoAdapter`: Operational weather observations, hourly precipitation, and 7-day weather forecasts (`source="open_meteo"`, `quality="MODEL_OUTPUT"`).
2. `NwicReservoirAdapter`: Karnataka reservoir telemetry with mandatory imperial-to-metric conversions (`Level * 0.3048`, `TMC * 28.3168`, `cusecs * 0.0283168`).
3. `NwicRiverLevelAdapter`: CWC river gauge hourly water level telemetry with strict `NULL` for missing discharge (`missing ≠ zero`).
4. `IfiFloodEventLoader`: India Flood Inventory v3.0 batch loader for District × Day ground-truth flood occurrence targets ($y \in \{0, 1\}$).
5. `OsmEmergencyFacilityLoader`: OpenStreetMap Overpass QL loader strictly for hospitals and fire stations (generic `amenity=shelter` prohibited).
6. `CuratedShelterLoader`: Manual curation of designated evacuation shelters from published District Disaster Management Plan (DDMP) PDF annexures with occupancy set to `NULL`.
**Context:** Ensures 100% real, attributable data ingestion without a single synthetic or fabricated value.
**Affected components:** Phase 2.4 ingestion adapters, test suite.
**Reversal conditions:** None.

---

## Open decisions

---

**D-007 — Repository naming**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Whether the GitHub repository should be renamed from `FloodThings` to `FloodPulse`.
**Current state:** GitHub remote is `Codovia/FloodThings`. Local directory is `FloodPrediction`. Project name is `FloodPulse`. Three different names.
**Options:**
1. Rename the GitHub repo to `FloodPulse` (one-step operation in GitHub Settings).
2. Keep `FloodThings` as the repo name; use `FloodPulse` as the application name only.
3. Create a new repository named `FloodPulse` and push there.
**Impact:** Documentation, commit messages, and agent tasks will use inconsistent names until resolved.

---

**D-008 — Orphan Docker container**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Whether `ai-flood-system-db-1` and its associated volume (`ai-flood-system_postgres_data`) should be removed.
**Current state:** The container is in a restart loop because its compose project directory (`/home/pioneer/Downloads/ai-flood-system/`) was deleted. It has restart policy `unless-stopped` and consumes CPU on every restart cycle.
**Options:**
1. Stop and remove the container and volume.
2. Stop the container only, keep the volume.
3. Leave it running (not recommended).

---

**D-009 — Telegram credential rotation**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Rotate the Telegram bot token discovered in old Trash environment files before building Telegram integration.
**Current state:** A `TELEGRAM_BOT_TOKEN` was found in deleted `.env` files in the system Trash. The token may still be active. Trash is not secure storage.
**Action needed:** Check the token via BotFather. If active, revoke and issue a new one. The new token must only reside in `.env` (which is `.gitignore`d).

---

**D-017 — Backend development port**
**Date:** 2026-09-17
**Status:** CONFIRMED FOR DEVELOPMENT
**Decision:** Use port 8001 for the FastAPI backend during development.
**Context:** Port 8000 is occupied by a `chatbot-web-1` Docker container on the development machine. Using 8001 avoids the conflict. The Vite dev proxy is configured to forward `/api/*` to `localhost:8001`. Production deployment may use any appropriate port.
**Affected components:** Backend startup command, Vite proxy config, CORS origin.
**Reversal conditions:** If the chatbot container is permanently removed, port 8000 can be reclaimed.

---

**D-025 — Real Data Ingestion Foundation Architecture (CLI-First, Adapters, Raw Preservation)**
**Date:** 2026-09-17
**Status:** IMPLEMENTED (Phase 2.4)
**Decision:** Implement data ingestion using provider-independent source adapters (`BaseAdapter`), raw payload preservation under `data/raw/<source>/`, strict referential tracking in `DataSource` and `DataIngestionRun`, and manually executable CLI commands via `python -m app.ingestion.cli`.
**Context:** Phase 2.3 validated external endpoints. Phase 2.4 establishes real data ingestion. To avoid opaque black-box background tasks or tight coupling to API routes, CLI-first manual execution provides immediate debuggability, deterministic idempotency, and clean provenance.
**Affected components:** `backend/app/ingestion/`, `docs/INGESTION_RUNBOOK.md`, `data/raw/`.

---

**D-026 — Strict Unit Normalization and Separation of Forecast from Observation**
**Date:** 2026-09-17
**Status:** IMPLEMENTED (Phase 2.4)
**Decision:**
1. Forecasts and observations are stored in separate tables (`WeatherForecast` vs `WeatherObservation` / `RainfallObservation`). Under no circumstances is a forecast stored as an observation.
2. All non-SI source units are converted strictly according to verified scientific formulas:
   - Level: $\text{Level}_{\text{m}} = \text{Level}_{\text{ft}} \times 0.3048$
   - Storage/Capacity: $\text{Storage}_{\text{MCM}} = \text{Storage}_{\text{TMC}} \times 28.3168$
   - Discharge/Flow: $\text{Discharge}_{\text{m}^3/\text{s}} = \text{Flow}_{\text{cusecs}} \times 0.0283168$
3. Missing readings remain strictly `NULL`. No zero-filling or synthetic guesses are allowed (`missing ≠ 0`).
**Affected components:** `backend/app/ingestion/sources/`, database observation tables.

---

**D-027 — Semantic Provenance Categorization (data_category) & Scientific Audit**
**Date:** 2026-09-17
**Status:** IMPLEMENTED (Phase 2.4.1)
**Decision:**
1. Explicitly classify every observation record with a mandatory semantic `data_category` column constrained to `('OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE')`.
2. Categorize Open-Meteo operational weather and precipitation as `MODEL_OUTPUT` (gridded NWP model nowcasts/hindcasts, not physical station readings).
3. Categorize Open-Meteo historical archive data as `REANALYSIS` (ERA5 atmospheric reanalysis).
4. Categorize CWC river levels and WRD reservoir telemetry as `OBSERVATION` (in-situ physical gauge readings).
5. Categorize India Flood Inventory (IFI v3.0) flood occurrences as `HISTORICAL_EVENT` (curated disaster records).
6. Purge test fixtures from production database tables and enforce automated test teardown in pytest fixtures to prevent test contamination.
**Context:** Downstream ML and hydrological models must never treat gridded numerical weather model outputs as physical in-situ measurements, which would corrupt model validation and introduce hidden bias.
**Affected components:** `backend/app/db/models/`, `backend/app/ingestion/sources/`, `backend/migrations/versions/ccfc6a6b5d06_*.py`, `docs/DATA_SEMANTICS_AUDIT.md`.

---

**D-028 — In-Process Scheduler Integration via APScheduler AsyncIOScheduler**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.5)
**Decision:**
Use APScheduler 3.10.4 `AsyncIOScheduler` integrated directly into FastAPI application lifespan (`app.main:lifespan`).
**Context:** The application is a single-instance modular monolith for development and staging. Celery, Redis, and distributed workers are explicitly out of scope per MASTER_PROJECT_SPEC.md. AsyncIOScheduler runs in-process on the main Uvicorn event loop and shuts down gracefully with the application.
**Affected components:** `backend/requirements.txt`, `backend/app/scheduler/`, `backend/app/main.py`.

---

**D-029 — Group A Automation Scope & Operational Polling Frequency**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.5)
**Decision:**
1. Restrict automated background scheduling strictly to Group A: `OpenMeteoAdapter` operational weather nowcasts and forecasts.
2. Maintain the 5 verified district representative query points (Bengaluru, Belagavi, Mangaluru, Kalaburagi, Mandya) without expanding to 31 districts.
3. Schedule operational execution at a default interval of 60 minutes (`openmeteo_ingestion_interval_minutes = 60`), generating ~120 API requests/day (well within the 10,000 req/day limit).
4. Strictly prohibit recurring scheduling for static archives (IFI v3.0, LGD) or monolithic batch datasets (CWC river tranches, NWIC 2006–2008 reservoir data).
**Affected components:** `backend/app/scheduler/jobs.py`, `backend/app/core/config.py`.

---

**D-030 — Dynamic Source Health Evaluation & FloodPulse Internal Freshness Policy**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.5)
**Decision:**
1. Compute source health dynamically on request via `SourceHealthService` without adding persistent `health_status` columns to `DataSource`.
2. Derive health from `DataSource.is_active`, `DataIngestionRun` history, consecutive failure counts, and actual stored observation timestamps (`WeatherObservation.observed_at`, etc.).
3. Supported states: `HEALTHY`, `DEGRADED`, `DOWN`.
4. Freshness SLA Clarification: Upstream providers (Open-Meteo, NWIC, CWC) do NOT publish formal freshness SLAs. Therefore, the 4-hour freshness threshold (`openmeteo_freshness_threshold_hours = 4`) and the 3-failure threshold (`source_health_consecutive_failure_threshold = 3`) are explicitly defined and documented as **FloodPulse internal operational policies**, never as upstream provider requirements.
**Affected components:** `backend/app/services/source_health.py`, `backend/app/api/v1/source_health.py`, `backend/app/schemas/source_health.py`.

---

**D-031 — Concurrency Protection and Async/Sync Safety**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.5)
**Decision:**
1. Dual-layer concurrency guard: configure APScheduler jobs with `max_instances=1` and `coalesce=True`, backed by an in-process `asyncio.Lock` inside `IngestionJobRunner`.
2. If an ingestion execution is already in progress, suppress overlapping executions and log a clear warning; never fabricate fake success records for skipped executions.
3. Thread offloading: synchronous blocking network and database operations in `OpenMeteoAdapter` are offloaded via `asyncio.to_thread` to prevent blocking the main FastAPI asyncio event loop.

---

**D-032 — KSR-SAC Administrative GIS Normalization & Topologic Repair Protocol**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.6 Foundation)
**Decision:**
1. Authoritative GIS Source: Ingest official KSR-SAC / KGIS administrative boundary shapefiles (`District.shp` for 31 districts, `Taluk.shp` for 240 taluks) located at `data/raw/gis/ksrsac/`.
2. Raw Source Preservation Policy: Source files on disk are strictly read-only and must never be modified, overwritten, or repaired in-place.
3. Coordinate Transformation: Source horizontal CRS is validated as `EPSG:32643` (UTM Zone 43N, metres). Geometries are transformed to `EPSG:4326` (WGS 84, decimal degrees) with guaranteed `MultiPolygon` typing for PostGIS database storage.
4. Deterministic Topology Repair: Exactly 3 taluk geometries in the source dataset contain minor ring self-intersections (Shivamogga KGIS 1506 / LGD 5520, Sringeri KGIS 1701 / LGD 5525, Hosanagar KGIS 1504 / LGD 5518). These are repaired deterministically in source metric space using `shapely.make_valid()`. `buffer(0)` is strictly prohibited. The resulting area alteration is sub-millimetric floating-point noise ($< 10^{-14}$ relative area difference).
5. Overlap Tolerance Policy: Substantive polygon overlaps between districts or between taluks of the same district are prohibited. A relative overlap tolerance of $\text{REL\_TOL} = 10^{-10}$ ($\text{intersection\_area} / \min(\text{area}_a, \text{area}_b)$) is enforced to absorb survey digitizing edge-coincidence floating-point artifacts while guaranteeing zero substantive overlapping jurisdiction.
6. Vijayanagara 6-Taluk Verification: District KGIS 31 (Vijayanagara, LGD code 738 in KSR-SAC `District.shp`) is verified to contain exactly 6 constituent taluks (Hadagali, Hagaribommanahalli, Harapanahalli, Hosapete, Kotturu, Kudligi).
7. Provenance & Identifier Preservation: Both KGIS codes and official LGD codes are preserved across all 31 districts and 240 taluks.
**Affected components:** `backend/app/gis/ksrsac.py`, `backend/app/gis/__init__.py`, `backend/tests/test_ksrsac_gis.py`.

---

**D-033 — Karnataka State Boundary Acquisition & Hierarchical GIS Normalization**
**Date:** 2026-09-18
**Status:** IMPLEMENTED (Phase 2.6B)
**Decision:**
1. Authoritative State Source: Acquired official KSR-SAC / KGIS Karnataka State Boundary (`State.zip` -> `State.shp`) from `https://kgis.ksrsac.in/kgis/downloads.aspx`, stored under `data/raw/gis/ksrsac/`.
2. Raw Source Preservation Policy: Downloaded archive and unpacked shapefile components remain strictly read-only and unmodified on disk.
3. Verified Source Attributes: Source contains exactly 1 feature with `KGISStateI = 1`, `KGISStateC = '29'` (Survey of India / LGD state code 29), and `KGISStateN = 'Karnataka'`.
4. Coordinate Transformation & MultiPolygon Normalization: Source projection validated as `EPSG:32643` (UTM Zone 43N) and reprojected to `EPSG:4326` with guaranteed `MultiPolygon` typing and computed `centroid` point.
5. Topological Validity: State geometry is 100% topologically valid in source coordinates (no self-intersections, no repairs required).
6. Administrative Hierarchy Containment: Verified that all 31 normalized districts and all 240 normalized taluks intersect the normalized state boundary, and all representative points fall strictly within the state polygon.
7. Extension of KsrsacAdminNormalizer: Implemented `NormalizedState` dataclass, `normalize_state()`, and `validate_state_containment()` in `backend/app/gis/ksrsac.py`.
**Affected components:** `backend/app/gis/ksrsac.py`, `backend/app/gis/__init__.py`, `backend/tests/test_ksrsac_gis.py`.

---

**D-034 — Deterministic IFI Historical Flood Event Normalization & KSR-SAC GIS Alignment**
**Date:** 2026-09-19
**Status:** IMPLEMENTED (Phase 2.7A Foundation)
**Decision:**
1. In-Memory Normalization Foundation: Implement `IfiEventNormalizer` in `backend/app/gis/ifi.py` to deterministically normalize India Flood Inventory (IFI v3.0) disaster records for Karnataka (State Code 29).
2. Authoritative Administrative Alignment: Every deterministic district match links directly to a verified KSR-SAC `NormalizedDistrict` entity, preserving KGIS codes (`01`–`31`), official LGD codes (`524`–`738`), and canonical district names.
3. Strict Zero-Fabrication Geometry Rule: Raw IFI events contain no coordinate geometry. Geometries must remain strictly `NULL` (`None`). Inferring flood polygons or points from district centroids or synthetic coordinates is strictly prohibited. IFI events are historical disaster evidence, not satellite inundation ground truth.
4. Strict Depth Nullability: `flood_depth` must remain strictly `NULL` (`None`), never filled with 0.0 or estimated values.
5. Semantic Provenance & Confidence Semantics: Enforces `data_category = "HISTORICAL_EVENT"`, `quality_status = "VALID"`, `source_name = "India Flood Inventory (IFI v3.0)"`, and deterministic `source_record_id = f"ifi_{uei}_{lgd_district_code}"`. Because IFI v3 publishes no confidence score, source `confidence` must remain `NULL` (`None`) per CONSTRAINTS.md (correcting an ungrounded Phase 2.4 assumption that assigned 1.0). Administrative mapping certainty is recorded as `mapping_status = "DETERMINISTIC"`.
6. Deterministic Alias Resolution & Recovery Counts: Exactly 173 raw tokens had `District_LGD_Codes == 'None'`. Of these, exactly 142 are recovered via verified spelling/headquarters aliases (`Uttar Kashia Kannada` 71 $\to$ Uttara Kannada, `Beedar` 36 $\to$ Bidar, `Bagalkotee` 20 $\to$ Bagalkote, `Chamarajanagaraa` 9 $\to$ Chamarajanagara, `Mangalore` 6 $\to$ Dakshina Kannada). In addition, exactly 32 occurrences of `Bijapur` (misattributed as LGD 636 [Chhattisgarh] in upstream IFI) are recovered and mapped to Vijayapura (KGIS 03, LGD 530).
7. Out-of-State Non-Karnataka Filtering: Exactly 35 non-Karnataka district tokens in multi-state events (Kerala, Gujarat, AP/Telangana, Uttarakhand) are deterministically identified and excluded without raising errors.
8. Unresolved Token Containment: Exactly 31 token occurrences across 18 distinct strings cannot be deterministically mapped (OCR concatenations, sub-district taluks, regional descriptors). The normalizer never guesses; unmapped tokens are recorded in `UnresolvedDistrictTokenRecord` and reported in the audit trail.
9. Database Migration Status: Inspection of PostgreSQL 16 schema and Alembic confirms zero migrations are required. The existing 34-table schema and check constraints (`ck_flood_obs_quality_status`, `ck_flood_obs_data_category`) already fully support normalized records.
10. Timezone Semantics: Raw IFI dates lack explicit timezone offsets and mostly use nominal midnight (`00:00`), indicating calendar day resolution. Conversion to UTC assuming IST (UTC+05:30) is documented as an **operational assumption** based on reporting agencies (IMD/CWC), not an explicit source metadata fact. Both raw date strings and derived UTC datetimes are preserved.
**Affected components:** `backend/app/gis/ifi.py`, `backend/app/gis/__init__.py`, `backend/tests/test_ifi_normalization.py`, `docs/DATA_PIPELINE.md`.

---

**D-035 — Deterministic Historical Flood Evidence Audit & Spatial-Temporal Coverage Contract**
**Date:** 2026-09-19
**Status:** IMPLEMENTED (Phase 2.7B Audit)
**Decision:**
1. Pure In-Memory Audit Module: Implement `IfiEvidenceAuditor` in `backend/app/gis/ifi_audit.py` to deterministically audit normalized IFI historical flood evidence against the 31 authoritative KSR-SAC districts without database writes, migrations, or data mutations.
2. Complete 31-District Spatial Audit: Audits all 31 districts deterministically sorted by KGIS district code (`01` to `31`). Exactly 30 districts have documented evidence; exactly 1 district (**Vijayanagara**, KGIS 31, LGD 738) has zero matching IFI v3 observations in the audited archive (`unique_events = 0`, `district_observations = 0`, `has_evidence = False`). Coverage is never manufactured, and absence of evidence does not constitute proof of zero flooding.
3. True Temporal Coverage Contract: Derived directly from the real normalized records: earliest event date is `1969-07-14`, latest event date is `2023-07-24`. Exactly 5 calendar years have zero documented records: `[1970, 1971, 1973, 1976, 1977]`. Temporal gaps are never filled or interpolated.
4. Exact Quality & Recovery Reconciliation: Derived from real source records:
   - 6,876 raw records received
   - 494 Karnataka-filtered events (`State_Codes` contains `29`)
   - 493 valid events, 1 rejected event (`UEI-IMD-FL-2001-0043` with empty start timestamp)
   - 1,344 raw district tokens evaluated across the 493 valid events:
     - `DIRECT_LGD`: 1,104 raw resolutions $\to$ 5 duplicate observations skipped $\to$ 1,099 normalized observations
     - `VERIFIED_ALIAS`: 142 raw resolutions $\to$ 2 duplicate observations skipped $\to$ 140 normalized observations
     - `BIJAPUR_CORRECTION`: 32 raw resolutions $\to$ 0 duplicate observations skipped $\to$ 32 normalized observations
     - `OUT_OF_STATE`: 35 non-Karnataka tokens skipped
     - `UNMAPPED`: 31 unresolved token occurrences across 18 distinct strings (occurrence counts sum exactly to 31)
   - Total normalized district observations: $1,099 + 140 + 32 = \mathbf{1,271}$
   - 0 duplicate events, 7 duplicate observations skipped within same events
   - 493 total unique events, 1,271 total unique district-event pairs
5. Strict Source Semantics & Scientific Boundaries:
   - Source is `India Flood Inventory (IFI v3.0)`, data category `HISTORICAL_EVENT`.
   - Evidence is coarse district-level administrative disaster damage.
   - Geometry, flood depth, and source confidence are explicitly `NULL` (`None`).
   - IFI is NOT satellite inundation ground truth.
   - Absence of evidence does NOT constitute proof of no flooding.
   - This audit does NOT define an ML target, label dataset, or prediction logic.
**Affected components:** `backend/app/gis/ifi_audit.py`, `backend/app/gis/ifi.py`, `backend/app/gis/__init__.py`, `backend/tests/test_ifi_audit.py`, `docs/DATA_PIPELINE.md`.

---

**D-038 — Administrative GIS ↔ Environmental Spatial Association Audit & Discrepancy Baseline**
**Date:** 2026-09-19
**Status:** IMPLEMENTED (Phase 3.3 Audit)
**Decision:**
1. Strict Read-Only Spatial Association Audit: Implement `SpatialAssociationAuditor` in `backend/app/gis/spatial_audit.py` to evaluate spatial containment, coordinate validity, and administrative linkage between PostGIS KSR-SAC GIS geometries (State, 31 Districts, 240 Taluks) and existing environmental / historical records.
2. Point Observation Audit (Weather & Rainfall): All 397 `weather_observations` and 397 `rainfall_observations` were audited. 100% (397/397) have valid EPSG:4326 geometries, 100% fall strictly inside the Karnataka State boundary, and 100% fall strictly within their assigned district polygons (8.95 km to 32.32 km from district boundaries; 0 boundary edge cases).
3. River Station Discrepancy Baseline (Akkihebbal): Station `AKKIHEBBAL` (lat: 12.59861111, lon: 76.40055556) on the Hemavathi/Cauvery river has assigned `district_id` = Koppal (Northern Karnataka), but spatial containment is Mandya (Southern Karnataka, ~284 km from Koppal; 2.94 km from Mandya boundary). The audit flags this as `OUTSIDE_ASSIGNED_DISTRICT` and `requires_manual_review = 1`. In adherence to read-only constraints and provenance preservation, the stored foreign key is NOT silently modified.
4. Taluk Polygonal Containment & Digitization Precision Tolerance: 240 taluks evaluated. 100% (240/240) intersect their assigned district, and 100% have `ST_PointOnSurface(geometry)` strictly within their assigned district. Exactly 44 taluks satisfy `ST_Within(t.geometry, d.geometry)`. Exactly 196 taluks exhibit micro-boundary slivers (< 0.00001% area difference, overlap >= 99.999%) resulting from independent shapefile digitization in KSR-SAC source data. These are deterministically classified as `BOUNDARY_SLIVER` (0 cross-district mismatches, 0 disjoint taluks).
5. Historical IFI Flood Observations (Admin Evidence): 186 `flood_observations` evaluated. 100% (186/186) reference valid KSR-SAC districts across 23 distinct districts. 100% (186/186) have `geometry IS NULL`, preserving the strict zero-fabrication invariant (IFI is historical disaster damage evidence, not coordinate/satellite ground truth).
6. Reproducible CLI Integration: Accessible via `python -m app.ingestion.cli spatial-audit [--format text|json] [--export-path PATH]`.
**Affected components:** `backend/app/gis/spatial_audit.py`, `backend/app/ingestion/cli.py`, `backend/tests/test_spatial_audit.py`, `docs/DATA_PIPELINE.md`, `docs/HANDOVER.md`.

---

**D-039 — Karnataka District Code Integrity Audit, Controlled River Station Correction & Ingestion Hardening**
**Date:** 2026-09-19
**Status:** IMPLEMENTED (Phase 3.4B)
**Decision:**
1. Authoritative 31-District Code Alignment: A deterministic audit comparing database `districts.code` values against the authoritative KSR-SAC / Government of India Local Government Directory (LGD) catalog identified 25 code mismatches resulting from sequential numbering in the Phase 2.4 geography seeder. All 31 `districts.code` values were corrected to their official LGD codes (`524`–`738`), exactly matching KSR-SAC `District.shp` attributes (`LGD_Distri`).
2. District UUID & Foreign Key Preservation: 100% of district primary keys (`districts.id` UUIDs) were strictly preserved without modification. Because all active environmental and administrative foreign keys (`weather_observations.district_id`, `rainfall_observations.district_id`, `weather_forecasts.district_id`, `taluks.district_id`, `flood_observations.district_id`) reference `districts.id` (UUID), zero foreign keys were broken or altered during the code update.
3. Controlled AKKIHEBBAL River Station Correction: Based on authoritative CWC source evidence (`District: Mandya`, `District LGD Code: 544`) and PostGIS spatial containment, station `AKKIHEBBAL` (`station_code = 'AKKIHEBBAL'`) had its `district_id` updated from Koppal UUID (`d1aeeddc-141b-4ab0-8899-ab9844e29b8d`) to Mandya UUID (`c9065c38-f2c3-4b56-8209-1009e4faa6f7`).
4. River Observations Preservation: All 101 `river_observations` rows for `AKKIHEBBAL` remain intact and untouched. `river_observations` references `station_id` (which was preserved); no river observation FK was modified or severed.
5. Ingestion Adapter Hardening (`nwic_river.py`): The NWIC/CWC river level adapter was hardened to cross-validate source district code against the authoritative Karnataka LGD catalog and cross-check against source district name (including canonical aliases). Conflicting code/name combinations are rejected and logged rather than silently misassigned.
6. Atomic Transaction Safety: Database updates were executed in a single atomic transaction with intermediate temporary code flushes to respect the `districts_code_key` unique constraint. Dry-run rollback capability was validated in automated testing.
7. Post-Correction Spatial Association Audit: Re-running `SpatialAssociationAuditor` confirms 100.0% spatial alignment across all 1,221 audited records:
   - River stations: 1/1 matched (0 outside, 0 manual review)
   - Weather observations: 397/397 matched
   - Rainfall observations: 397/397 matched
   - Taluks: 240/240 matched
   - IFI flood observations: 186/186 valid
   - Total discrepancies: 0.
**Affected components:** `backend/app/gis/district_code_audit.py`, `backend/app/gis/controlled_correction.py`, `backend/app/ingestion/sources/nwic_river.py`, `backend/app/ingestion/sources/geography.py`, `backend/app/ingestion/cli.py`, `backend/tests/test_district_code_integrity.py`, `docs/DISTRICT_CODE_AUDIT_REPORT.md`, `docs/DATA_PIPELINE.md`, `docs/HANDOVER.md`.

---

**D-040 — Canonical Historical District × Day ML Feature Matrix Construction & Leakage Audit**
**Date:** 2026-09-25
**Status:** IMPLEMENTED (Phase 4)
**Decision:**
1. Unit of Analysis: District × Day across all 31 KSR-SAC Karnataka administrative districts.
2. Temporal Scope: 1969-07-14 to 1975-12-31 (2,362 calendar dates; 73,222 rows).
3. Spatial Area-Weighting: 0.25° ERA5 reanalysis grid cells area-weighted to district polygons with minimum coverage weight threshold ($W_{\text{valid}} \ge 0.95$).
4. Three-State Target Semantics: FLOOD (546 rows, IFI v3.0 documented disaster events), NO_FLOOD (0 rows), and UNKNOWN (72,676 rows, unevidenced dates preserved as NULL).
5. Anti-Leakage Protocol: 24-hour lead time enforced ($t-1 \to t$). Target day weather strictly prohibited from entering predictor features. Missing lookback days propagate to NaN (zero silent zero-filling).
**Affected components:** `backend/app/ml/district_feature_matrix.py`, `backend/app/ml/matrix_cli.py`, `backend/tests/test_district_feature_matrix.py`, `docs/ML_FEATURE_MATRIX_AUDIT.md`.

---

**D-041 — Baseline ML Modeling, Chronological Temporal Splitting & Positive-Unlabeled (PU) Evaluation**
**Date:** 2026-09-25
**Status:** IMPLEMENTED (Phase 5)
**Decision:**
1. Zero Negative Fabrication Policy: UNKNOWN labels are strictly never converted to NO_FLOOD. The dataset is framed and treated as Positive-Unlabeled (PU) with an empirical prevalence of 0.7457%.
2. Expanding-Window Chronological Split: Train on 1969–1973 (50,592 observations, 247 FLOOD), Validation on 1974 (11,315 observations, 203 FLOOD), and Test on 1975 (11,315 observations, 96 FLOOD). Zero temporal overlap between splits.
3. Preprocessing Isolation: Feature scalers (`StandardScaler`) are fitted strictly on training data ($X_{\text{train}}$). Decision thresholds are calibrated out-of-sample on validation data and evaluated on held-out test data.
4. Model Architectures: Transparent regularized Logistic Regression baseline with standardized coefficients ($\beta_j$) and LightGBM gradient-boosted decision trees for non-linear interactions.
5. PU Formulation Comparison: Implemented and evaluated Standard PU (SCAR assumption with class weighting), High-Confidence Negatives (filtering dry-season zero-rain days; 5,153 reliable negatives), and Bagging PU (15-estimator bootstrap subsampling ensemble).
6. Non-Accuracy Evaluation: Evaluated via PR-AUC (Average Precision), ROC-AUC, Brier score, and PU ranking score ($r^2 / P(\hat{Y}=1)$), alongside Elkan-Noto reporting frequency parameter ($c$).
7. Model Artifact Management: Serialized model pipelines (joblib) and metadata JSON records (recording hyperparameters, target semantics, PU assumptions, and SHA-256 data hash) saved to `data/processed/ml_models/`.
**Affected components:** `backend/app/ml/baseline_modeling.py`, `backend/app/ml/modeling_cli.py`, `backend/tests/test_baseline_models.py`, `docs/ML_BASELINE_MODELING_AUDIT.md`.

---

**D-042 — Full 26-Year Historical ERA5 Daily Processing & Canonical ML Feature Matrix Expansion (Phase 4.2)**
**Date:** 2026-09-25
**Status:** IMPLEMENTED (Phase 4.2)
**Decision:**
1. Complete Daily ERA5 Processing: Processed all 858 canonical raw chunks across the full 26-year historical period (1969–1994) using `DailyProcessor`. 100.0% completion (858/858 succeeded, 0 failed, 0 pending), yielding 3,019,728 daily grid cell records across 318 unique cells with full leap-year support and physical range integrity.
2. Canonical District × Day ML Feature Matrix Expansion: Expanded the canonical matrix across all 31 Karnataka administrative districts and 9,496 calendar days (1969-01-01 through 1994-12-31), producing exactly 294,376 District × Day rows.
3. Strict Ground Truth Label Preservation: Integrated real IFI v3.0 disaster observations yielding 1,152 documented `FLOOD` events. Maintained strict three-state semantics: 0 fabricated `NO_FLOOD` labels, 293,224 `UNKNOWN` rows preserved as `NULL`.
4. Strict Anti-Leakage Invariants: 24-hour lead time ($t-1 \to t$) strictly enforced across all 294,376 rows. Target-day weather strictly forbidden from entering predictor features. `feature_window_end < target_date` verified for 100.0% of records.
5. Weather and Static Completeness: 293,446 rows (99.68%) possess full 30-day antecedent weather history; exactly 930 rows with incomplete 30-day weather correspond strictly to the initialization boundary (January 1–30, 1969) before the lookback window begins. Terrain (Copernicus DEM GLO-30) and hydrological GIS (CWC Statutory + HydroBASINS Level-7) zonal statistics are 100.0% complete across all 294,376 rows.
**Affected components:** `backend/app/ingestion/historical/daily.py`, `backend/app/ingestion/historical/daily_cli.py`, `backend/app/ml/district_feature_matrix.py`, `backend/app/ml/matrix_cli.py`, `data/processed/era5_daily/`, `data/processed/ml_matrix/district_day_feature_matrix.parquet`.
