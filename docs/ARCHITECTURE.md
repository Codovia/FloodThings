# ARCHITECTURE.md

**Project:** FloodPulse — Karnataka AI Flood Intelligence & Emergency Response System
**Status:** Planning document. No application components are currently implemented.

---

## Purpose

FloodPulse is intended to provide:

- District-level flood risk prediction for Karnataka using validated ML on real data.
- Emergency shelter location, capacity/occupancy tracking, and route finding.
- Telegram-based flood alerts.
- A citizen dashboard and an administrative dashboard.
- Integration with real weather, hydrology, and geospatial data sources.
- Transparent separation of AI predictions from official government warnings.

---

## Planned architecture

```
Real data sources (IMD, CWC, IFI, KSNDMC, KGIS, NRSC, ...)
      ↓
Source adapters (fetch → parse → validate → normalize → health_check)
      ↓
Raw data archive
      ↓
Data validation
      ↓
Normalization
      ↓
PostgreSQL / PostGIS
      ↓
Feature engineering
      ↓
ML model (trained on validated historical flood events)
      ↓
Prediction service
      ↓
Frontend dashboard / Telegram alerts
```

### Request path (planned)

```
Users
  │
  ├── React UI (citizen / admin)
  │       ↓
  │     FastAPI
  │       ↓
  │     PostgreSQL / PostGIS
  │
  └── Telegram
        ↑
      Alert engine
```

---

## Technology stack (frozen per MASTER_PROJECT_SPEC.md §2)

| Layer | Technology | Status |
|---|---|---|
| Frontend | React + Vite | Planned |
| Backend | FastAPI | Planned |
| Database | PostgreSQL 16 | Exists (Docker container, outside repo) |
| Spatial DB | PostGIS 3.4.3 | Exists (Docker container, outside repo) |
| GIS processing | GeoPandas, Shapely, PostGIS | Planned |
| Maps | Leaflet / React-Leaflet | Planned |
| Charts | Recharts | Planned |
| ML | Python (scikit-learn initially) | Planned |
| ML training | Google Colab (experimentation) | Planned |
| Background jobs | APScheduler or equivalent | Planned — to be evaluated |
| Notifications | Telegram | Planned |
| API style | REST / OpenAPI | Planned |
| Auth | Secure token-based | Planned |
| Containers | Docker / Docker Compose | Partial — DB container exists |
| Version control | Git + GitHub | Active |

---

## Major components

### Frontend (PLANNED)

React + Vite single-page application.

Responsibilities:
- Citizen dashboard: flood risk map, shelter finder, community reports.
- Admin dashboard: data source monitoring, alert management, shelter administration.
- Map visualization via Leaflet/React-Leaflet.
- Charts via Recharts.

### Backend (PLANNED)

FastAPI application.

Responsibilities:
- REST API for all frontend operations.
- Data ingestion via source adapters.
- Feature engineering pipeline.
- ML prediction service.
- Alert decision engine.
- Authentication and authorization.

### Database (PARTIAL — container exists, no application schema)

PostgreSQL 16 + PostGIS 3.4.3 via Docker.

Responsibilities:
- Relational storage for all structured data.
- Spatial storage and queries via PostGIS.
- Single database for the application — no separate document store.

### GIS (PLANNED)

Responsibilities:
- Authoritative administrative boundaries (district, taluk).
- River/waterbody geometries.
- DEM-derived terrain features (slope, elevation).
- Spatial joins for location assignment.
- Flood hazard zone mapping.

### ML (PLANNED)

Responsibilities:
- Validated dataset construction from real historical flood events.
- Feature engineering from weather, hydrology, and GIS features.
- Model training, evaluation, calibration.
- Model versioning and reproducibility.
- Prediction API.

### Alerts (PLANNED)

Responsibilities:
- Alert decision engine (based on ML prediction + configured thresholds).
- Telegram message delivery.
- Alert deduplication.
- Failure isolation (Telegram failures must not crash the application).

### Shelter / Evacuation (PLANNED)

Responsibilities:
- Shelter database with real locations and capacity.
- Occupancy tracking.
- Shelter finder by user location.
- Route calculation to nearest safe shelter.

### Community reports (PLANNED)

Responsibilities:
- Citizen-submitted flood/damage reports.
- Reports are clearly labeled as unverified — never auto-promoted to ground truth.
- Moderation workflow.

### Admin (PLANNED)

Responsibilities:
- Data source health monitoring.
- Alert configuration.
- Shelter management.
- User/role management.

---

## Architectural principles

1. **Modular monolith.** No microservices, no Kubernetes, no Kafka, no blockchain unless explicitly approved later.
2. **Real data first.** Every environmental observation must come from a legitimate, attributable source.
3. **Provenance.** Every important value carries: source, retrieval time, transformation history.
4. **Reproducibility.** Dataset versions, model versions, and configuration are traceable.
5. **Explicit validation.** Data is validated at ingestion. Invalid data is rejected or flagged, never silently accepted.
6. **No fabricated environmental data.** Not even temporarily, not even for development convenience.
7. **Separation of prediction and warnings.** AI predictions and official government warnings are never displayed as the same thing.
8. **Auditability.** Administrative actions are logged. Data lineage is preserved.
9. **Graceful degradation.** Missing or stale data is shown honestly, not hidden or crashed past.

---

## Current state

As of Phase 0:

- Repository structure exists (P0.1).
- `.gitignore` exists (P0.2).
- `MASTER_PROJECT_SPEC.md` exists (untracked).
- Docker PostGIS container (`floodpulse-postgres`) is running on port 5432, healthy, but not managed by any in-repo compose file.
- No application code, no schema, no data, no ML, no frontend, no tests exist in the repository.
