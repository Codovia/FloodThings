# TEST_CHECKLIST.md

**Project:** FloodPulse
**Status:** Planning document. No tests are currently implemented. This checklist defines the categories of testing required before each phase is considered complete.

A phase is not "done" until its relevant rows are checked with evidence (test output, screenshot, or query result) — not just a claim.

---

## Repository and configuration

- [ ] `.gitignore` prevents secrets from being tracked
- [ ] `.env.example` is not ignored
- [ ] `.gitkeep` files are tracked
- [ ] No secrets in committed files
- [ ] No large data files accidentally committed

**Status:** PLANNED — `.gitignore` exists but has not been tested against a real `.env`

---

## Data integrity

- [ ] No fabricated environmental observations
- [ ] No fabricated ML labels
- [ ] No fabricated reservoir levels
- [ ] No fabricated river measurements
- [ ] No fabricated emergency locations
- [ ] All observations have provenance
- [ ] Units are explicit
- [ ] Timestamps are normalized (UTC)
- [ ] Coordinates are validated
- [ ] CRS is documented
- [ ] Missingness is explicit (NULL, not zero)
- [ ] Freshness is tracked

**Status:** PLANNED — no data ingestion exists yet

---

## GIS / spatial

- [ ] Official administrative boundaries (no rectangle fallback)
- [ ] Coordinates validated against Karnataka bounds
- [ ] River distance calculated geometrically
- [ ] Terrain derived from a legitimate DEM
- [ ] Geometry validity tested (ST_IsValid)
- [ ] CRS consistency at every spatial join

**Status:** PLANNED — no GIS processing exists yet

---

## Machine learning

- [ ] Target comes from legitimate historical flood events
- [ ] No synthetic target formula
- [ ] No temporal leakage
- [ ] No future-event leakage
- [ ] No spatial leakage (or documented if unavoidable)
- [ ] Dataset versioned
- [ ] Feature schema versioned
- [ ] Model versioned
- [ ] Held-out historical evaluation
- [ ] Metrics documented (precision, recall, F1, PR-AUC, confusion matrix)
- [ ] Calibration assessed

**Status:** PLANNED — no ML pipeline exists yet

---

## Unit tests

- [ ] Health endpoint returns OK
- [ ] Health endpoint reports database status honestly
- [ ] Health endpoint reports PostGIS status honestly
- [ ] Data contract validation rejects invalid input
- [ ] Source adapter parsing handles edge cases
- [ ] Feature engineering produces expected output shape

**Status:** PLANNED — no application code exists yet

---

## API tests

- [ ] All endpoints return correct status codes
- [ ] Invalid input returns 4xx with useful error messages
- [ ] Endpoints handle missing/stale data gracefully
- [ ] Authentication blocks unauthorized access to admin endpoints
- [ ] CORS configuration is correct

**Status:** PLANNED

---

## Database tests

- [ ] Migrations apply cleanly
- [ ] Migrations roll back cleanly
- [ ] Spatial queries execute correctly
- [ ] Indexes improve query performance
- [ ] Constraints prevent invalid data

**Status:** PLANNED — no schema or migrations exist yet

---

## PostGIS tests

- [ ] PostGIS extension is available
- [ ] Spatial queries return correct results
- [ ] CRS transformations work
- [ ] Geometry types match expectations

**Status:** PLANNED — PostGIS is installed but no application schema exists

---

## Prediction tests

- [ ] Prediction API returns valid responses
- [ ] Predictions include model version and timestamp
- [ ] Stale input data produces appropriate warnings

**Status:** PLANNED

---

## Shelter and routing tests

- [ ] Shelter finder returns nearby shelters by distance
- [ ] Capacity/occupancy is reported accurately
- [ ] Unknown occupancy is not presented as available
- [ ] Routing returns valid paths

**Status:** PLANNED

---

## Telegram tests

- [ ] Alerts are delivered to subscribed chats
- [ ] Alert deduplication works
- [ ] Telegram failures are isolated (don't crash the application)
- [ ] Rate limiting is respected

**Status:** PLANNED

---

## Community report tests

- [ ] Reports are stored correctly
- [ ] Reports are always marked as UNVERIFIED initially
- [ ] Location validation works
- [ ] Moderation workflow functions

**Status:** PLANNED

---

## Integration tests

- [ ] End-to-end data flow: source → adapter → validation → storage → feature → prediction
- [ ] Frontend communicates correctly with backend API
- [ ] Alert pipeline: prediction → decision → Telegram delivery

**Status:** PLANNED

---

## End-to-end tests

- [ ] Full user journey: view dashboard → see risk → find shelter → get route
- [ ] Full admin journey: monitor sources → manage shelters → configure alerts

**Status:** PLANNED

---

## Engineering

- [ ] Tests pass in CI
- [ ] Docker build works
- [ ] Database migrations reversible
- [ ] Documentation updated
- [ ] Git diff reviewed before merge

**Status:** PLANNED — no CI exists yet
