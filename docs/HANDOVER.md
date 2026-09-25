# HANDOVER.md

**Project:** FloodPulse
**Last updated:** 2026-09-17 (Phase 2.4.1)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 5 — Baseline ML Modeling & Temporal Cross-Validation (Completed)
Previous phases:        Phase 0 — Project control (P0.1–P0.3)
                        Phase 1 — Source verification (planning/specification level)
                        Phase 2.1 — Project Foundation (FastAPI + React + PostGIS foundation)
                        Phase 2.2 — Database + Internal Data Contract (34 tables deployed)
                        Phase 2.3 — Real Source / API Validation Lab (Empirically probed)
                        Phase 2.4 — Real Data Ingestion Foundation (CLI adapters & verified ingestion)
                        Phase 2.4.1 — Data Semantics & Provenance Correction (Backfilled provenance)
                        Phase 2.5 — Automated Background Ingestion & Source Health (Completed)
                        Phase 2.6 — GIS Foundation (KSR-SAC Admin & State Normalization Ready)
                        Phase 2.7 — IFI Historical Flood Event Normalization & Evidence Audit (D-034, D-035)
                        Phase 2.8 — ML Target Readiness Definition
                        Phase 3.1 — KSR-SAC Administrative GIS PostGIS Ingestion Design (Completed)
                        Phase 3.2 — KSR-SAC Administrative GIS PostGIS Ingestion (1 State, 31 Districts, 240 Taluks)
                        Phase 3.3 — Administrative GIS ↔ Environmental Spatial Association Audit (Completed)
                        Phase 3.4A — AKKIHEBBAL River Station Provenance Investigation (Completed)
                        Phase 3.4B — Karnataka District Code Integrity Audit + Controlled River Station Correction (Completed)
                        Phase 4 — Canonical District × Day Feature Matrix & Leakage Audit (Completed)
```

## Repository

```
Local directory:        /home/pioneer/Projects/FloodPrediction
GitHub remote:          https://github.com/Codovia/FloodThings.git
Branch:                 main
Application name:       FloodPulse
```

Note: Three different names are in use (FloodPrediction, FloodThings, FloodPulse). See DECISIONS.md D-007.

## Current implementation

```
Backend:                FastAPI application with lifespan-integrated APScheduler (AsyncIOScheduler)
                        Dynamic Source Health: SourceHealthService (HEALTHY, DEGRADED, DOWN)
                        API v1 Health Endpoints:
                          - GET /api/v1/health/sources (runtime health evaluation, authority_level, last_http_status_code)
                          - GET /api/v1/health/sources/{source_id}/runs (paginated run audit history, http_status_code)
                        Legacy Health Endpoints: /health, /health/database, /health/postgis
                        Scheduler Package: app/scheduler/ (manager.py, runner.py, jobs.py)
                          - In-process concurrency locking & thread offload via asyncio.to_thread
                          - Single-instance max_instances=1, coalesce=True
                        GIS Package: app/gis/ (ksrsac.py, ifi.py, __init__.py)
                          - KsrsacAdminNormalizer: In-memory normalization of KSR-SAC State.shp, District.shp, and Taluk.shp
                          - Read-only raw preservation: zero file modifications on disk
                          - Validated single-feature State boundary (KGISStateC=29, KGISStateN=Karnataka)
                          - State containment verified across all 31 districts and 240 taluks
                          - Deterministic repair of 3 known invalid taluks via shapely.make_valid()
                          - Target output in EPSG:4326 with strict MultiPolygon typing
                          - Provenance preservation: KGIS + LGD codes for State, 31 districts, and 240 taluks
                          - IfiEventNormalizer: In-memory deterministic normalization of IFI v3.0 historical events
                          - Grounded to KSR-SAC NormalizedDistrict foundation (31 districts)
                          - Strict zero-fabrication geometry constraint (geometry = NULL, no centroid inference)
                          - Strict depth nullability (flood_depth = NULL, never 0.0 or estimated)
                          - Preserves semantic provenance (data_category = HISTORICAL_EVENT, quality_status = VALID)
                          - Confidence semantics: source confidence is NULL (unprovided by IFI); mapping_status = DETERMINISTIC
                          - Timezone semantics: raw dates preserved; UTC timestamps derived under documented IST assumption
                          - Deterministic alias resolution (142 recovered from 173 'None' tokens, 32 from Bijapur LGD 636)
                          - Unresolved token containment (31 unmapped tokens across 18 distinct strings audited without guessing)
                        SQLAlchemy models: 34 application tables across 9 domains (app/db/models/)
                        Data Category: Enforced data_category column & CHECK constraint on 5 observation tables
                        Ingestion Framework: app/ingestion/ (base.py, registry.py, validation.py, cli.py)
                        Source Adapters:
                          - KarnatakaGeographyAdapter (Karnataka State LGD 29 & 31 administrative districts)
                          - OpenMeteoAdapter (Operational forecast, MODEL_OUTPUT past obs, REANALYSIS archive)
                          - NwicRiverLevelAdapter (CWC hourly river stage in metres, OBSERVATION provenance)
                          - NwicReservoirAdapter (Daily telemetry with ft->m, TMC->MCM, OBSERVATION provenance)
                          - IfiFloodAdapter (IFI v3.0 historical disaster events & HISTORICAL_EVENT observations)
                        Raw Data Preservation: data/raw/ (<source>/, preserved JSON/CSV, .gitignore'd)
Database:               PostgreSQL 16 + PostGIS 3.4 (Docker container: floodpulse-postgres)
                        34 application tables deployed via Alembic migration ccfc6a6b5d06
                        Populated with real, verified observations with 100% semantic provenance:
                        - 397 weather_observations (325 MODEL_OUTPUT, 72 REANALYSIS)
                        - 397 rainfall_observations (325 MODEL_OUTPUT, 72 REANALYSIS)
                        - 275 weather_forecasts (72-hour forward predictions)
                        - 101 river_observations (101 OBSERVATION)
                        - 100 reservoir_observations (100 OBSERVATION)
                        - 100 flood_events (historical catalog)
                        - 186 flood_observations (186 HISTORICAL_EVENT historical evidence)
                        - 31 districts (LGD reference)
                        Zero unclassified records (0 NULLs). Zero test fixture residue.
Tests:                  115 tests — 100% passing. Guaranteed teardowns prevent test fixture leakage.
Alembic:                Current head: ccfc6a6b5d06, alembic check clean ("No new upgrade operations detected")
Docker:                 docker-compose.yml with postgres service (port 5432)
```

## Database environment

```
FloodPulse Docker database:
  Container:   floodpulse-postgres
  Image:       postgis/postgis:16-3.4
  PostgreSQL:  16.4
  PostGIS:     3.4.3
  Port:        5432
  Database:    floodpulse
  Volume:      floodprediction_postgres_data
  Status:      Running, healthy
  Schema:      34 application tables, 23 spatial columns, 23 GiST indexes, 51 check constraints

System PostgreSQL:
  Version:     18
  Port:        5433
  Status:      Running
  Usage:       NOT used by FloodPulse — may be used by other projects
```

## Verified health endpoints

```
GET /health             → {"status": "ok"}
GET /health/database    → {"status": "ok"}
GET /health/postgis     → {"status": "ok", "postgis_version": "3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1"}
```

## Frontend → Backend connection

```
Browser → http://localhost:5173 → Vite proxy /api/* → http://localhost:8001/* → FastAPI → PostgreSQL
```

Verified via curl: all three health endpoints return correct data through the Vite proxy.

## Unresolved decisions

```
D-007 — Repository naming (FloodThings → FloodPulse?)
D-008 — Orphan Docker container cleanup
D-009 — Telegram credential rotation
```

## Known issues

- Port 8000 is used by a chatbot-web container; FloodPulse backend runs on port 8001 during development
- `ai-flood-system-db-1` container in restart loop (orphan — D-008 OPEN)
- Telegram bot token in system Trash — may be compromised (see SECURITY.md)
- Python 3.14 on system vs Python 3.12 in project venv (DECISIONS.md D-005)

## Development commands

```bash
# Start database
docker start floodpulse-postgres

# Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Frontend
cd frontend && npm run dev

# Unit tests
cd backend && PYTHONPATH=. python -m pytest tests/test_health.py -v

# Integration tests (requires running postgres)
cd backend && PYTHONPATH=. python -m pytest tests/test_health_integration.py -v

# Schema & Data Contract tests
cd backend && PYTHONPATH=. python -m pytest tests/test_schema.py -v

# All tests
cd backend && PYTHONPATH=. python -m pytest tests/ -v

# Alembic commands
cd backend && PYTHONPATH=. alembic current
cd backend && PYTHONPATH=. alembic heads
cd backend && PYTHONPATH=. alembic check
```

## Next phase

```
Phase 6 — Shelter, Evacuation & Routing System / Prediction API Integration
```

## Phase 5 Artifacts Created (Baseline ML Modeling & PU Cross-Validation)

```
backend/app/ml/baseline_modeling.py          (DatasetAuditor, TemporalDataSplitter, PUDatasetPreparer, LogisticRegressionBaseline, LightGBMBaseline, PUEvaluator, ModelArtifactManager, ModelingOrchestrator)
backend/app/ml/modeling_cli.py               (CLI subcommands: audit, train, compare)
backend/tests/test_baseline_models.py        (15 focused tests covering chronological splitting, leakage prevention, PU strategies, LightGBM, serialization, Elkan-Noto calibration)
data/processed/ml_models/                    (Serialized joblib model pipelines and companion metadata JSON records)
data/processed/ml_models/feature_matrix_audit.json (Machine-readable canonical dataset audit)
data/processed/ml_models/comparison_results.json   (Full 6-way PU model benchmark results)
docs/ML_BASELINE_MODELING_AUDIT.md           (Comprehensive Phase 5 Modeling Audit and Benchmark Report)
Updated docs/DECISIONS.md                    (Added D-040 for Phase 4 and D-041 for Phase 5)
Updated docs/HANDOVER.md                     (Updated current state, artifacts, and next steps)
```

## Phase 2.7B Artifacts Created (Historical Flood Evidence Audit)

```
backend/app/gis/ifi_audit.py                 (IfiEvidenceAuditor, IfiEvidenceAuditReport, coverage & quality records)
backend/tests/test_ifi_audit.py              (Audit test suite: 31 districts, 0-evidence, yearly, metrics, zero fabrication)
Updated backend/app/gis/ifi.py               (Added resolution_method tracking to NormalizedIfiObservation & _resolve_district)
Updated backend/app/gis/__init__.py          (Exported audit classes and records)
Updated docs/DATA_PIPELINE.md                (Added Section 2.4.1 for IFI historical evidence audit contract)
Updated docs/DECISIONS.md                    (Added D-035 on historical flood evidence audit & spatial-temporal contract)
Updated docs/HANDOVER.md                     (Documented Phase 2.7B completion)
```

## Phase 3.3 Artifacts Created (Administrative GIS ↔ Environmental Spatial Association Audit)

```
backend/app/gis/spatial_audit.py             (SpatialAssociationAuditor: deterministic read-only spatial & admin audit)
backend/tests/test_spatial_audit.py          (Tests: spatial containment, discrepancy detection, read-only invariant)
Updated backend/app/ingestion/cli.py         (Added spatial-audit subcommand with text and JSON formats)
Updated docs/DECISIONS.md                    (Added D-038 on spatial association audit and discrepancy baseline)
Updated docs/DATA_PIPELINE.md                (Added Section 2.9 on spatial association audit)
Updated docs/HANDOVER.md                     (Updated current state, artifacts, and next steps)
```

## Phase 2.7A Artifacts Created (Historical Flood Normalization Foundation)

```
backend/app/gis/ifi.py                       (IfiEventNormalizer: deterministic normalization & KSR-SAC alignment)
backend/tests/test_ifi_normalization.py      (Tests: normalization, deduplication, confidence=None, geometry=None)
Updated backend/app/gis/__init__.py          (Exported IfiEventNormalizer and normalization result models)
Updated docs/DATA_PIPELINE.md                (Added Section 2.4 for IFI historical flood event normalization)
Updated docs/DECISIONS.md                    (Added D-034 on deterministic IFI normalization)
```

## Phase 2.5 Artifacts Created

```
backend/app/scheduler/manager.py            (SchedulerManager: AsyncIOScheduler lifecycle & job registration)
backend/app/scheduler/runner.py             (IngestionJobRunner: in-process concurrency locking & thread offload)
backend/app/scheduler/jobs.py               (Operational Open-Meteo ingestion job definition)
backend/app/services/source_health.py       (SourceHealthService: runtime dynamic health computation)
backend/app/schemas/source_health.py        (Pydantic schemas: SourceHealthItem, SourceRunsResponse, etc.)
backend/app/api/v1/source_health.py         (API endpoints: GET /api/v1/health/sources, GET /api/v1/health/sources/{source_id}/runs)
backend/tests/test_scheduler.py             (Tests: scheduler lifecycle, disabled config, concurrency lock, runner safety)
backend/tests/test_source_health.py         (Tests: dynamic health states, stale policy, failure escalation)
backend/tests/test_source_health_api.py     (Tests: /api/v1/health endpoints, 404, 422, pagination, legacy preserved)
backend/requirements.txt                    (Added apscheduler==3.10.4)
Updated backend/app/core/config.py          (Added scheduler_enabled, intervals, and internal freshness thresholds)
Updated backend/app/main.py                 (FastAPI lifespan context manager & /api/v1 router mount)
Updated backend/tests/conftest.py           (Added default scheduler isolation SCHEDULER_ENABLED=false)
Updated docs/DECISIONS.md                   (Recorded D-028, D-029, D-030, D-031)
Updated docs/DATA_PIPELINE.md               (Documented background automation, concurrency, and dynamic health)
Updated docs/HANDOVER.md                    (Recorded Phase 2.5 completion & handover)
```

## Phase 2.4.1 Artifacts Created

```
backend/migrations/versions/ccfc6a6b5d06_add_data_category_column_for_semantic_.py (Migration, backfill, & test cleanup)
docs/DATA_SEMANTICS_AUDIT.md                (Permanent reference for data semantics and provenance classifications)
docs/DECISIONS.md                           (Added D-027 on semantic provenance categorization)
Updated backend/app/db/models/              (Added data_category and CHECK constraints on 5 observation models)
Updated backend/app/ingestion/              (Added DataCategory constants, updated adapters to assign category)
Updated backend/tests/                      (Added data_category tests, guaranteed test teardowns)
```

Wait for project owner review before proceeding.

## Important warnings

- Do not generate synthetic rainfall, reservoir, or ML-label data at any point (`missing != 0`).
- Do not recover Trash files without explicit approval per file.
- Do not assume APIs exist — verify them (see DATA_SOURCES.md).
- See CONSTRAINTS.md before writing any code.
- Port 8001 is the current backend port (not 8000).

