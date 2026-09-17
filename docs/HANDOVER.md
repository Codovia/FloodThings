# HANDOVER.md

**Project:** FloodPulse
**Last updated:** 2026-09-17 (Phase 2.1)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 2.1 — Project Foundation (COMPLETE)
Previous phases:        Phase 0 — Project control (P0.1–P0.3)
                        Phase 1 — Source verification (planning/specification level)
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
                        app/main.py, app/api/health.py, app/core/config.py, app/db/session.py
Frontend:               React + Vite — health status display, API proxy
                        src/App.jsx, src/main.jsx, src/index.css
Database:               PostgreSQL 16 + PostGIS 3.4 (Docker container)
                        Empty schema (alembic_version + spatial_ref_sys only)
Tests:                  8 unit tests + 6 integration tests — all passing
Alembic:                Foundation verified — autogenerate works, PostGIS filtering works
Docker:                 docker-compose.yml with postgres service
```

## Database environment

```
FloodPulse Docker database:
  Container:   floodpulse-postgres
  Image:       postgis/postgis:16-3.4
  PostgreSQL:  16.4
  PostGIS:     3.4
  Port:        5432
  Database:    floodpulse
  Volume:      floodprediction_postgres_data
  Status:      Running, healthy
  Schema:      Empty foundation (no application tables)

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

## Untracked Phase 1 work (preserved, not committed)

```
backend/app/db/models/     10 domain model files (premature for Phase 2.1)
backend/migrations/versions/_phase1_backup/   premature migration (backed up)
backend/tests/test_schema.py                  premature schema tests
docs/DATA_ACQUISITION_SPEC.md                 Phase 1 data spec
docs/DATA_SOURCE_INVENTORY.md                 Phase 1 inventory
docs/DATA_SOURCE_VERIFICATION.md              Phase 1 verification
docs/FINAL_SOURCE_SELECTION.md                Phase 1 selection
docs/SCHEMA_AUDIT.md                          Schema audit
```

These files are preserved in the working directory but intentionally not staged for the Phase 2.1 commit.

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

# All tests
cd backend && PYTHONPATH=. python -m pytest tests/ -v

# Alembic
cd backend && PYTHONPATH=. alembic current
```

## Next phase

```
Phase 3 — Authentication + Users
```

Wait for project owner review before proceeding.

## Important warnings

- Do not generate synthetic rainfall, reservoir, or ML-label data at any point.
- Do not recover Trash files without explicit approval per file.
- Do not assume APIs exist — verify them (see DATA_SOURCES.md).
- See CONSTRAINTS.md before writing any code.
- Port 8001 is the current backend port (not 8000).
