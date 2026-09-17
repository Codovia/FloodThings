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

