# HANDOVER.md

**Project:** FloodPulse
**Last updated:** 2026-09-30 (Phase 5.3 Scientific Audit)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 5.4 — Baseline ML Training & Validation (Completed)
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
                        Phase 4.1 — Canonical District × Day Feature Matrix Sample & Leakage Audit (Completed)
                        Phase 4.2 — Full Historical ERA5 Daily Processing & Canonical Feature Matrix Construction (Completed)
                        Phase 5 — Baseline ML Modeling & Temporal Validation (Historical Baseline Completed)
                        Phase 5.1 — Recent-Data & ARCO Meteorological Audit (Completed)
                        Phase 5.2 — Full Recent-Period ERA5 Ingestion & Audit (Completed)
                        Phase 5.3 — ML Dataset Scientific Audit & Experiment Preparation (Completed)
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
Tests:                  416 tests — 100% passing. Guaranteed teardowns prevent test fixture leakage.
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

## Phase 5.3 Artifacts Created (Recent ERA5 District-Day Analysis Dataset & Supervised ML Matrix)

```
data/processed/era5_district_daily/recent/ (15 annual Parquet partitions year=2011 to year=2025; 169,849 rows)
data/processed/era5_district_daily/recent/district_daily_2011_2025.parquet (Unified meteorological dataset; 2.18 MB)
data/processed/era5_district_daily/recent/processing_manifest.json (100% complete processing & quality manifest)
data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet (Canonical supervised ML feature matrix; 142,228 rows x 57 columns, 6.56 MB)
data/processed/ml_matrix/recent/district_day_matrix_2011_2023_audit.json (Comprehensive Phase 5.3 quality and leakage audit)
data/processed/ml_matrix/recent/ml_dataset_reconciliation_audit.json (Comprehensive Phase 5.3 / 8.1 statistical and anti-leakage audit)
data/processed/ml_matrix/recent/district_day_weather_matrix.parquet (Full 2011–2025 meteorological feature matrix; 169,849 rows x 57 columns)
docs/PHASE_8_1_ML_DATASET_AUDIT.md            (Comprehensive pre-training scientific audit report)
backend/app/ingestion/historical/district_daily_aggregator.py (Production district-level aggregation pipeline)
backend/app/gis/recent_mapping_audit.py (GIS & 318-cell spatial mapping audit engine)
backend/app/ml/recent_matrix_builder.py (Recent district-day supervised ML matrix builder with IFI v3.0 join)
backend/tests/test_district_daily_aggregation.py (11 comprehensive tests: cardinality, physical bounds, immutability, schema)
backend/tests/test_recent_district_matrix.py (11 comprehensive tests: 318 cells, GIS, 142k supervised matrix, 3-state labels, anti-leakage, spatial weights normalization, predictor separation)
Updated docs/DECISIONS.md                     (Added D-044 on district-day aggregation; D-045 on recent supervised matrix; D-046 on scientific audit & experiment contract)
Updated docs/HANDOVER.md                      (Documented Phase 5.3 scientific audit completion, audit results, and artifacts)
```

## Phase 5.2 Artifacts Created (Recent ERA5 Data Ingestion Foundation & Date Bounds)


```
data/raw/era5_recent/                         (528/528 raw JSON.gz payloads + .meta.json for 2011–2026; 261MB)
data/raw/era5_recent/extraction_manifest.json (100% SUCCEEDED manifest across all 528 canonical chunks)
data/processed/era5_daily/recent/             (528/528 daily Parquet chunks for 2011–2026; 1,826,274 cell-days; 34MB)
data/processed/era5_daily/recent/processing_manifest.json (100% SUCCEEDED manifest across all 528 processed chunks)
data/processed/ml_matrix/recent/              (Segregated recent feature matrix directory reserved for Phase 5.3)
backend/app/ingestion/historical/recent_cli.py (Dedicated recent pipeline CLI: extract, process, status)
backend/app/ingestion/historical/recent_audit.py (Dedicated quality and integrity audit engine for 2011–2026)
backend/tests/test_era5_recent_bounds.py      (6 unit tests covering bounded extraction, partial years, and CLI guards)
Updated backend/app/ingestion/historical/models.py (Added start_date and end_date to ExtractionChunk)
Updated backend/app/ingestion/historical/client.py (Supported custom start_date/end_date query parameters and auto-cooldown)
Updated backend/app/ingestion/historical/validator.py (Hour count and date bounds validation for partial years)
Updated backend/app/ingestion/historical/daily_validator.py (Supported expected_start_date/expected_end_date)
Updated backend/app/ingestion/historical/daily_processor.py (Automated metadata date bounds discovery)
Updated backend/app/ingestion/historical/grid.py (Supported final_end_date for partial final years)
Updated docs/DECISIONS.md                     (Added D-043 on Phase 5.2 recent ingestion & partial-year support)
Updated docs/HANDOVER.md                      (Documented Phase 5.2 completion, audit metrics, & artifacts)
```

## Phase 4.2 Artifacts Created (Full 26-Year Historical ERA5 Processing & Feature Matrix)

```
data/processed/era5_daily/                   (858/858 daily Parquet chunks for years 1969–1994; 3,019,728 cell-days)
data/processed/era5_daily/processing_manifest.json (100% SUCCEEDED manifest across all 858 canonical chunks)
data/processed/ml_matrix/district_day_feature_matrix.parquet (Full 26-year canonical feature matrix; 294,376 rows x 57 columns)
backend/app/ml/matrix_cli.py                 (Updated default temporal bounds to full 1969–1994 scope)
Updated docs/DECISIONS.md                    (Added D-042 on Phase 4.2 full historical processing & matrix expansion)
Updated docs/HANDOVER.md                     (Updated current state, artifacts, and next steps)
```

## Phase 5 Artifacts Created (Baseline ML Modeling & Temporal Validation)

```
backend/app/ml/baseline_modeling.py          (DatasetAuditor, TemporalDataSplitter, PUDatasetPreparer, LogisticRegressionBaseline, LightGBMBaseline, PUEvaluator, ModelArtifactManager, ModelingOrchestrator)
backend/app/ml/modeling_cli.py               (CLI subcommands: audit, train, compare with multi-year temporal split arguments)
backend/tests/test_baseline_models.py        (21 focused tests covering chronological splitting, leakage prevention, PU strategies, LightGBM, serialization, Elkan-Noto calibration, zero negative fabrication, reproducibility)
data/processed/ml_models/                    (Serialized joblib model pipelines and companion metadata JSON records)
data/processed/ml_models/logistic_regression_standard_pu_1df92880_pipeline.joblib (Trained baseline on 26-year matrix)
data/processed/ml_models/logistic_regression_standard_pu_1df92880_metadata.json (Auditable evaluation metrics & parameters)
docs/ML_BASELINE_MODELING_AUDIT.md           (Comprehensive Phase 5 Modeling Audit and Benchmark Report)
Updated docs/DECISIONS.md                    (Updated D-041 for 26-year historical matrix partitioning)
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

## Phase 5.4 Artifacts Created

```
backend/app/ml/experiment/__init__.py        (Experiment harness public API)
backend/app/ml/experiment/dataset.py         (SHA-256 verification, canonical 27 predictors, 930 cold-start exclusion)
backend/app/ml/experiment/splits.py          (Strict chronological Train/Val/Test partitions)
backend/app/ml/experiment/metrics.py         (PU metrics: PR-AUC, ROC-AUC, Elkan-Noto c, Lee-Liu criterion, Brier)
backend/app/ml/experiment/baseline.py        (Standardized Logistic Regression and Random Forest baselines)
backend/app/ml/experiment/runner.py          (Experiment orchestrator and artifact persistence)
backend/tests/test_experiment_baseline.py    (15 rigorous unit tests: whitelist, leakage, splits, SCAR audit, threshold isolation)
models/experiments/phase_5_4/logistic_regression/ (LR metadata JSON and pipeline joblib)
models/experiments/phase_5_4/random_forest/       (RF metadata JSON and pipeline joblib)
docs/PHASE_5_4_BASELINE_MODEL_REPORT.md      (Comprehensive scientific evaluation report with PU Proxy distinction & SCAR NOT VALIDATED declaration)
docs/DECISIONS.md                            (Recorded Decision D-047)
docs/HANDOVER.md                             (Updated current state)
```

## Phase 5.5 Artifacts Created (Advanced PU Modeling & Nonlinear Benchmark)

```
backend/app/ml/experiment/pu_bagging.py        (PUBaggingClassifier: 15 bags, unlabeled ratio 3.0, non-SCAR formulation)
backend/app/ml/experiment/nonlinear_lgbm.py    (LightGBMExperimentModel: unconstrained and monotonic constraint tree models)
backend/app/ml/experiment/event_audit.py        (DisasterEventAuditor: cross-partition event lineage audit & multi-district analysis)
backend/app/ml/experiment/runner_phase_5_5.py  (Phase 5.5 benchmark orchestrator comparing all 5 models)
backend/tests/test_experiment_phase_5_5.py     (10 unit tests: whitelist, no UNKNOWN->0, SCAR check, splits, 0 event leak, test isolation, deterministic config, SHA preservation, metadata, monotonic vector)
models/experiments/phase_5_5/pu_bagging/       (PUBagging pipeline joblib and metadata JSON)
models/experiments/phase_5_5/lightgbm_unconstrained/ (LightGBM Unconstrained pipeline joblib and metadata JSON)
models/experiments/phase_5_5/lightgbm_monotonic/     (LightGBM Monotonic pipeline joblib and metadata JSON)
models/experiments/phase_5_5/benchmark_comparison.json (Comprehensive 5-model benchmark comparison and audit data)
docs/PHASE_5_5_ADVANCED_PU_MODEL_REPORT.md     (Comprehensive Phase 5.5 report across all 18 required sections)
Updated docs/DECISIONS.md                     (Recorded Decision D-048)
Updated docs/HANDOVER.md                      (Recorded Phase 5.5 completion & handover)
```

## Phase 5.6 Artifacts Created (Hydrological Feature Integration & Multi-Scale Audit)

```
backend/app/ml/hydrology/__init__.py           (Hydrology ML integration package exports)
backend/app/ml/hydrology/audit.py              (HydrologicalDataAuditor: DB and raw CSV audit, 29 Karnataka stations)
backend/app/ml/hydrology/crosswalk.py          (HydrologicalCrosswalk: M:N spatial crosswalk across 31 districts, 7 basins, 116 sub-basins)
backend/app/ml/hydrology/features.py           (HydrologicalFeatureEngine: 10 candidate features, anti-leakage filter, NaN preservation)
backend/app/ml/hydrology/coverage.py           (HistoricalCoverageGate: coverage evaluation per year, station, district; BLOCKED status)
backend/tests/test_hydrological_features.py    (10 unit tests: anti-leakage, missing!=0, timezone, crosswalk, M:N links, staleness, coverage gate)
docs/PHASE_5_6_HYDROLOGICAL_FEATURE_AUDIT.md   (Comprehensive scientific report across all 13 required sections)
Updated docs/DECISIONS.md                      (Recorded Decision D-049)
Updated docs/HANDOVER.md                       (Recorded Phase 5.6 completion & handover)
```

## Phase 5.7 Artifacts Created (Historical ERA5 Completion & Feature-Readiness Audit)

```
backend/app/ml/historical_readiness.py         (Feature contract, ERA5 manifest auditor, resume checklist generator)
backend/tests/test_historical_feature_readiness.py (10 unit tests: whitelist, units, lookback, zero leakage, cold-start, weights, missing!=0, hydrology isolation)
docs/PHASE_5_7_HISTORICAL_FEATURE_READINESS_AUDIT.md (Authoritative scientific audit report across all 11 required sections)
Updated docs/DECISIONS.md                      (Recorded Decision D-050)
Updated docs/HANDOVER.md                       (Recorded Phase 5.7 completion & handover)
```

Scientific Status:
- Historical ERA5 Extraction (1969–1994): Exactly 858/858 chunks SUCCEEDED (100.0%). 0 RETRYABLE, 0 PENDING, 0 RUNNING. 858 raw `.json.gz` (356.1 MB compressed) and 858 `.meta.json` files intact on disk.
- Historical Daily Parquets: Exactly 858 historical daily parquets on disk; `data/processed/ml_matrix/district_day_feature_matrix.parquet` (294,376 rows, SHA-256 `849f722b...`) intact.
- Spatial Weights: Exactly 318 eligible cells across 31 districts, weights sum to 1.000000, 6 offshore cells excluded.
- Temporal Anti-Leakage: Zero day-$t$ weather observation leakage; feature window strictly bounded to $[t-30, t-1]$.
- Cold-Start Handling: 930 initialization rows (Jan 1–30) flagged and excluded from training without synthetic imputation.
- Authoritative Feature Contract: 27 canonical active predictors (`READY`); 10 operational in-situ river telemetry features (`BLOCKED_FOR_HISTORICAL_TRAINING`).
- ML Production Readiness: PU proxy baseline models only; NOT PRODUCTION READY.

Wait for project owner review before proceeding to Phase 5.8 (Multi-Era Historical & Recent Supervised Cross-Validation / Operational Forward Architecture).

## Important warnings

- Do not generate synthetic rainfall, reservoir, or ML-label data at any point (`missing != 0`).
- Do not recover Trash files without explicit approval per file.
- Do not assume APIs exist — verify them (see DATA_SOURCES.md).
- See CONSTRAINTS.md before writing any code.
- Port 8001 is the current backend port (not 8000).

