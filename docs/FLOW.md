# FLOW.md

**Project:** FloodPulse
**Status:** Planning document. These flows describe intended system behavior. None are currently implemented.

---

## End-to-end data-to-prediction flow

```
External data sources (IMD, CWC, IFI, KSNDMC, KGIS, ...)
      ↓
Source adapters (fetch → parse → validate → normalize)
      ↓
Ingestion manifest (record what was retrieved, when, from where)
      ↓
Raw data archive (data/raw/)
      ↓
Data validation (type, range, completeness, CRS, duplicates)
      ↓
Normalization (units, timestamps, district codes, CRS)
      ↓
PostgreSQL / PostGIS storage
      ↓
Feature engineering (rainfall metrics, terrain, hydrology, temporal)
      ↓
Feature snapshot (versioned feature set for a spatial unit and date)
      ↓
ML model (trained on validated historical dataset)
      ↓
Flood prediction (risk level, probability, model version, timestamp)
      ↓
Risk classification
      ↓
Map / API / Dashboard
      ↓
Alert decision engine (threshold-based, configurable)
      ↓
Telegram notification delivery
```

---

## Official warning flow (separate from predictions)

```
Official source (IMD, CWC, SDMA bulletins)
      ↓
Ingestion (if API/feed available, or manual admin entry)
      ↓
Storage with classification: OFFICIAL_WARNING
      ↓
Display — clearly labeled as "Official Warning"
      ↓
Never merged with or presented as AI prediction
```

---

## Emergency shelter flow

```
User location (GPS or manual entry)
      ↓
Current risk assessment for user's location
      ↓
Candidate shelters (within reasonable distance)
      ↓
Safety / status filtering
  - Is the shelter in a safe zone relative to current flooding?
  - Is the shelter open / operational?
      ↓
Capacity / occupancy / freshness validation
  - Is capacity data available?
  - Is occupancy data fresh?
  - Unknown occupancy ≠ available
      ↓
Ranking (distance, safety, capacity)
      ↓
Route calculation (via routing service)
      ↓
ETA and navigation directions
      ↓
User display: shelter info, route, ETA
```

---

## Community report flow

```
Citizen submits report
  - Location (GPS or manual)
  - Report type (flooding, damage, need assistance, etc.)
  - Description
  - Optional photos
      ↓
Report stored with status: UNVERIFIED
      ↓
Admin / moderator review
      ↓
Status updated: VERIFIED / REJECTED / NEEDS_INFO
      ↓
Verified reports may appear on public dashboard (clearly labeled)
      ↓
Unverified reports are NEVER automatically treated as ground truth
```

---

## Alert flow

```
New prediction generated (or official warning received)
      ↓
Alert decision engine
  - Does this exceed the configured alert threshold?
  - Is this a new alert or a duplicate of an existing active alert?
      ↓
Deduplication check
      ↓
If new alert:
  - Store alert record
  - Identify affected Telegram subscribers (by district/scope)
  - Send Telegram messages
  - Log delivery status
      ↓
Telegram delivery failures are logged but do NOT crash the application
```

---

## Data source health monitoring flow

```
Scheduled health check (APScheduler or equivalent)
      ↓
For each active data source:
  - Attempt fetch / connectivity check
  - Record response status, latency, data freshness
      ↓
Update source health status: HEALTHY / DEGRADED / UNREACHABLE
      ↓
Admin dashboard shows current source health
      ↓
Stale or unreachable sources are flagged visibly, never hidden
```
