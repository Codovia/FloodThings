# HANDOVER.md

**Project:** FloodPulse
**Last updated:** 2026-09-17 (Phase 2.4.1)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 2.4.1 — Data Semantics & Provenance Correction (COMPLETE)
Previous phases:        Phase 0 — Project control (P0.1–P0.3)
                        Phase 1 — Source verification (planning/specification level)
                        Phase 2.1 — Project Foundation (FastAPI + React + PostGIS foundation)
                        Phase 2.2 — Database + Internal Data Contract (34 tables deployed)
                        Phase 2.3 — Real Source / API Validation Lab (Empirically probed)
                        Phase 2.4 — Real Data Ingestion Foundation (CLI adapters & verified ingestion)
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
Backend:                FastAPI application — health endpoints verified
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
                        - 186 flood_observations (186 HISTORICAL_EVENT ground truth)
                        - 31 districts (LGD reference)
                        Zero unclassified records (0 NULLs). Zero test fixture residue.
Tests:                  52 tests — 100% passing. Guaranteed teardowns prevent test fixture leakage.
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
Phase 2.5 — Automated Background Ingestion & Source-Health Monitoring (APScheduler, health metrics, alerting hooks)
```

## Phase 2.4 Artifacts Created

```
backend/app/ingestion/base.py               (BaseAdapter, IngestionMetrics, IngestionResult)
backend/app/ingestion/registry.py           (DataSource & DataIngestionRun lifecycle)
backend/app/ingestion/validation.py         (UTC standardization, coordinate bounds, float checks, EPSG:4326 WKT)
backend/app/ingestion/sources/geography.py  (Karnataka State LGD 29 & 31 districts with centroids)
backend/app/ingestion/sources/open_meteo.py (Operational weather, rainfall obs, weather forecast, historical reanalysis)
backend/app/ingestion/sources/nwic_river.py (CWC hourly river stage in metres, river basins & stations)
backend/app/ingestion/sources/nwic_reservoir.py (Daily reservoir telemetry with ft->m, TMC->MCM, cusecs->m³/s)
backend/app/ingestion/sources/ifi_flood.py  (IFI v3.0 historical disaster events & district observations)
backend/app/ingestion/cli.py                (CLI runner with geography, open-meteo, nwic-river, nwic-reservoir, ifi, ingest-all, status)
backend/tests/test_ingestion_validation.py  (Timestamp, coordinate, range, quality status tests)
backend/tests/test_ingestion_adapters.py    (Unit conversions, field mapping, observation/forecast separation tests)
backend/tests/test_ingestion_idempotency.py (Zero-duplicate idempotency tests across all adapters)
docs/INGESTION_RUNBOOK.md                   (Operator guide for manual CLI ingestion and status checks)
Updated docs/DATA_PIPELINE.md, docs/DATA_SOURCES.md, docs/DATA_CONTRACT.md, docs/DECISIONS.md (D-025, D-026)
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

