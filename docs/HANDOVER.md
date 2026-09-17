# HANDOVER.md

**Project:** FloodPulse
**Project:** FloodPulse
**Last updated:** 2026-09-17 (Phase 2.4)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 2.4 — Real Data Ingestion Foundation (COMPLETE)
Previous phases:        Phase 0 — Project control (P0.1–P0.3)
                        Phase 1 — Source verification (planning/specification level)
                        Phase 2.1 — Project Foundation (FastAPI + React + PostGIS foundation)
                        Phase 2.2 — Database + Internal Data Contract (34 tables deployed)
                        Phase 2.3 — Real Source / API Validation Lab (Empirically probed)
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
                        Ingestion Framework: app/ingestion/ (base.py, registry.py, validation.py, cli.py)
                        Source Adapters:
                          - KarnatakaGeographyAdapter (Karnataka State LGD 29 & 31 administrative districts)
                          - OpenMeteoAdapter (Operational forecast, past observations, historical reanalysis)
                          - NwicRiverLevelAdapter (CWC hourly river stage in metres, river basins & stations)
                          - NwicReservoirAdapter (Daily telemetry with verified ft->m, TMC->MCM, cusecs->m³/s conversions)
                          - IfiFloodAdapter (IFI v3.0 historical disaster events & district observations, depth=NULL)
                        Raw Data Preservation: data/raw/ (<source>/, preserved JSON/CSV, .gitignore'd)
Database:               PostgreSQL 16 + PostGIS 3.4 (Docker container: floodpulse-postgres)
                        34 application tables deployed via Alembic migration 7eee813798dd
                        Populated with real, verified observations (102 river, 101 reservoir, 399 weather,
                        399 rainfall, 276 forecast, 102 flood events, 188 flood observations, 5 data sources,
                        43 tracked ingestion runs). Zero fabricated records.
Tests:                  51 tests (8 health unit + 6 health live + 15 schema + 17 validation/adapters/idempotency + 5 integration) — 100% passing
Alembic:                Current head: 7eee813798dd, alembic check clean ("No new upgrade operations detected")
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

Wait for project owner review before proceeding.

## Important warnings

- Do not generate synthetic rainfall, reservoir, or ML-label data at any point (`missing != 0`).
- Do not recover Trash files without explicit approval per file.
- Do not assume APIs exist — verify them (see DATA_SOURCES.md).
- See CONSTRAINTS.md before writing any code.
- Port 8001 is the current backend port (not 8000).

