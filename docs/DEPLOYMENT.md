# DEPLOYMENT.md

**Project:** FloodPulse
**Status:** Planning document. No deployment configuration exists in the repository yet.

---

## Current state

```
Repository deployment configuration:  NOT YET IMPLEMENTED
docker-compose.yml in repository:     DOES NOT EXIST
Backend Dockerfile:                    DOES NOT EXIST
Frontend Dockerfile:                   DOES NOT EXIST

Docker PostGIS container:              EXISTS OUTSIDE REPOSITORY
  Container name: floodpulse-postgres
  Image: postgis/postgis:16-3.4
  Port: 5432
  Database: floodpulse
  Volume: floodprediction_postgres_data
  Status: Running, healthy
  Managed by: A docker-compose.yml that NO LONGER EXISTS in the filesystem
```

The running `floodpulse-postgres` container was started from a compose file that has since been deleted. It persists because Docker containers survive file deletion. It is not currently reproducible from the repository.

---

## Intended deployment approach

### Docker Compose

The project will use Docker Compose to define and run the application services:

```
services:
  db        — PostgreSQL 16 + PostGIS 3.4.3
  backend   — FastAPI (Python 3.12)
  frontend  — React + Vite (Node)
```

### Environment variables

All configuration will be via environment variables loaded from `.env`:

- Database credentials
- API keys / tokens
- Application secrets
- CORS origins
- Service URLs

`.env.example` will document required variables without real values.

### Persistent database volume

Database data will persist via a named Docker volume. The volume survives container restarts and recreation.

### Backup strategy

- Database backups will be automated (pg_dump or equivalent).
- Backup schedule, retention, and restore procedures will be documented when implemented.

### Health checks

- Docker Compose will define health checks for the database service.
- The FastAPI application will expose `/health`, `/health/database`, and `/health/postgis` endpoints.

### Logging

- Application logs will be written to stdout/stderr (standard Docker practice).
- Log aggregation strategy will be defined if needed.

---

## Deployment tasks remaining

- [ ] Create `docker-compose.yml` in repository root
- [ ] Create `backend/Dockerfile`
- [ ] Create `frontend/Dockerfile`
- [ ] Create `.env.example`
- [ ] Document startup procedure
- [ ] Implement health checks
- [ ] Implement database backup strategy
- [ ] Test full Docker Compose lifecycle (build, up, down, rebuild)
