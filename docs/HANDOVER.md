# HANDOVER.md

**Project:** FloodPulse
**Last updated:** 2026-09-16 (Phase 0, P0.3)

Read this document first in every new session.

---

## Current state

```
Phase:                  Phase 0 — Clean Foundation
Current task:           P0.3 — Project-control documentation
Completed tasks:        P0.1 — Repository structure
                        P0.2 — Git protection (.gitignore)
                        P0.3 — Project-control documentation (this task)
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
Application code:       NONE — no backend, frontend, ML, or GIS code exists in the repository
Database schema:        NONE — no application tables exist
Tests:                  NONE
Docker configuration:   NOT IN REPOSITORY
```

## What exists in the repository

```
README.md               Tracked (placeholder: "# FloodThings")
docs/MASTER_PROJECT_SPEC.md  Untracked — 1805 lines
docs/ control documents  Untracked — 16 project-control documents (P0.3)
.gitignore              Untracked
Directory structure     Untracked (P0.1 — backend/, frontend/, ml/, gis/, data/, etc.)
```

Nothing has been committed since the initial "first commit" (README.md only).

## Database environment

```
FloodPulse Docker database:
  Container:   floodpulse-postgres
  Image:       postgis/postgis:16-3.4
  PostgreSQL:  16
  PostGIS:     3.4.3
  Port:        5432
  Database:    floodpulse
  Volume:      floodprediction_postgres_data
  Status:      Running, healthy
  Schema:      Empty (PostGIS system tables only)

System PostgreSQL:
  Version:     18
  Port:        5433
  Status:      Running
  Usage:       NOT used by FloodPulse — may be used by other projects

Orphan container:
  ai-flood-system-db-1 — restart loop, needs cleanup (see DECISIONS.md D-008)
```

## Unresolved decisions

```
D-007 — Repository naming (FloodThings → FloodPulse?)
D-008 — Orphan Docker container cleanup
D-009 — Telegram credential rotation
```

## Known issues

- Telegram bot token in system Trash — may be compromised (see SECURITY.md)
- Prior prototype code in Trash contains synthetic data patterns (documented in Phase 0 inspection report)
- Python 3.14 on system vs Python 3.12 target for project (DECISIONS.md D-005)

## Next task

```
P0.4 — To be assigned by project owner
```

Expected remaining Phase 0 tasks:
- Docker configuration (docker-compose.yml, .env.example)
- Backend skeleton (FastAPI, health endpoints)
- Frontend skeleton (React + Vite)
- Initial test suite
- Phase 0 Git checkpoint commit

## Important warnings

- Do not generate synthetic rainfall, reservoir, or ML-label data at any point.
- Do not recover Trash files without explicit approval per file.
- Do not assume APIs exist — verify them (see DATA_SOURCES.md).
- See CONSTRAINTS.md before writing any code.
