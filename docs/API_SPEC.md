# API_SPEC.md

**Project:** FloodPulse
**Status:** Planning document. No API endpoints are currently implemented.

---

## API framework

- **Framework:** FastAPI
- **Style:** REST / OpenAPI
- **Documentation:** Auto-generated OpenAPI/Swagger via FastAPI
- **Serialization:** JSON
- **Validation:** Pydantic models

---

## Planned endpoint groups

### Health

Application and dependency health checks.

```
GET /health
GET /health/database
GET /health/postgis
```

Purpose: Verify the application, database connection, and PostGIS extension are operational. These are the first endpoints to be implemented.

---

### Weather

Weather observation and forecast data.

```
GET /api/v1/weather/observations
GET /api/v1/weather/forecasts
```

---

### Rainfall

Rainfall observations and derived metrics.

```
GET /api/v1/rainfall/observations
GET /api/v1/rainfall/features
```

---

### Flood events

Historical flood event records.

```
GET /api/v1/flood-events
GET /api/v1/flood-events/{event_id}
```

---

### Predictions

ML-generated flood risk predictions.

```
GET /api/v1/predictions
GET /api/v1/predictions/{district_id}
GET /api/v1/predictions/latest
```

---

### GIS

Geographic and spatial data.

```
GET /api/v1/gis/districts
GET /api/v1/gis/districts/{district_id}
GET /api/v1/gis/rivers
GET /api/v1/gis/hazard-zones
```

---

### Shelters

Emergency shelter information.

```
GET /api/v1/shelters
GET /api/v1/shelters/{shelter_id}
GET /api/v1/shelters/nearby
```

---

### Routing

Route calculation to shelters or facilities.

```
GET /api/v1/routing/to-shelter
```

---

### Emergency facilities

Hospitals, fire stations, police stations, etc.

```
GET /api/v1/emergency-facilities
GET /api/v1/emergency-facilities/nearby
```

---

### Community reports

Citizen-submitted flood/damage reports.

```
GET  /api/v1/community-reports
POST /api/v1/community-reports
```

---

### Alerts

Alert history and configuration.

```
GET /api/v1/alerts
GET /api/v1/alerts/active
```

---

### Admin

Administrative operations (protected).

```
GET    /api/v1/admin/data-sources
GET    /api/v1/admin/data-sources/health
POST   /api/v1/admin/shelters
PUT    /api/v1/admin/shelters/{shelter_id}
GET    /api/v1/admin/alerts/config
PUT    /api/v1/admin/alerts/config
```

---

## Notes

- All endpoints shown above are **planned**. None are currently implemented.
- Exact request/response schemas will be defined using Pydantic models during implementation.
- Authentication/authorization will be designed before admin endpoints are built.
- API versioning uses URL path prefix (`/api/v1/`).
- Health endpoints do not use the `/api/v1/` prefix — they are operational endpoints.
