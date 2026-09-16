# DECISIONS.md

**Project:** FloodPulse
**Status:** Active decision register. Entries are permanent history — never delete an entry, only add a newer one that supersedes it.

---

## Confirmed decisions

---

**D-001 — Application architecture**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** React + Vite + FastAPI + PostgreSQL/PostGIS modular monolith.
**Context:** The project needs a full-stack web application with spatial database support. The specification explicitly establishes this stack and prohibits microservices, Kubernetes, Kafka, blockchain, native mobile, chatbot, SMS, and email.
**Affected components:** All.
**Reversal conditions:** None anticipated.

---

**D-002 — Real-data requirement**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** Environmental and operational data must come from real, attributable sources. No fabricated environmental observations, ever.
**Context:** The prior FloodPrediction prototype manufactured several fields (synthetic daily rainfall from annual totals, formula-generated reservoir values, a hand-written risk score used as an ML label). This must not recur.
**Affected components:** All data ingestion, ML pipeline, feature engineering.
**Reversal conditions:** None — non-negotiable per CONSTRAINTS.md.

---

**D-003 — Initial notification channel**
**Date:** 2026-09-15
**Status:** CONFIRMED
**Decision:** Telegram is the initial and primary notification channel.
**Context:** The specification selects Telegram for alerts. SMS and email are explicitly out of scope.
**Affected components:** Alert engine, Telegram integration.
**Reversal conditions:** None anticipated for the 30-day scope.

---

**D-004 — Database strategy**
**Date:** 2026-09-16
**Status:** CONFIRMED FOR PHASE 0
**Decision:** FloodPulse development database uses the Docker PostGIS container (`floodpulse-postgres`, PostgreSQL 16, PostGIS 3.4.3, port 5432) rather than the host PostgreSQL 18 instance on port 5433.
**Context:** Two PostgreSQL instances exist on the development machine. The Docker container provides PostGIS and is isolated from the host system database. The host PostgreSQL 18 on port 5433 may be used by other projects.
**Affected components:** All database connections, `docker-compose.yml`, `.env`.
**Reversal conditions:** If the Docker approach becomes impractical, revisit.

---

**D-005 — Python runtime**
**Date:** 2026-09-16
**Status:** CONFIRMED FOR PROJECT
**Decision:** Use Python 3.12 for the project runtime (Docker images, virtual environments) unless a later evidence-based decision changes this.
**Context:** The development machine has Python 3.14.4 (system), but many ML/GIS libraries (scikit-learn, numpy, geopandas, psycopg2-binary) may have limited or no binary wheels for Python 3.14. The prior working Dockerfile used `python:3.12-slim`. Python 3.12 is stable and broadly supported.
**Affected components:** Dockerfile, virtual environments, CI.
**Reversal conditions:** If all required libraries gain confirmed Python 3.14 support, this can be revisited.

---

**D-006 — ML train/test split strategy**
**Date:** 2026-09-16
**Status:** CONFIRMED
**Decision:** All ML train/test splits are time-based, never random.
**Context:** Flood risk is a time-series problem. A random split leaks future rainfall patterns and events into training. The model must be trained on the past and evaluated on the future.
**Affected components:** ML training, ML evaluation.
**Reversal conditions:** None — this is a hard rule per CONSTRAINTS.md.

---

## Open decisions

---

**D-007 — Repository naming**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Whether the GitHub repository should be renamed from `FloodThings` to `FloodPulse`.
**Current state:** GitHub remote is `Codovia/FloodThings`. Local directory is `FloodPrediction`. Project name is `FloodPulse`. Three different names.
**Options:**
1. Rename the GitHub repo to `FloodPulse` (one-step operation in GitHub Settings).
2. Keep `FloodThings` as the repo name; use `FloodPulse` as the application name only.
3. Create a new repository named `FloodPulse` and push there.
**Impact:** Documentation, commit messages, and agent tasks will use inconsistent names until resolved.

---

**D-008 — Orphan Docker container**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Whether `ai-flood-system-db-1` and its associated volume (`ai-flood-system_postgres_data`) should be removed.
**Current state:** The container is in a restart loop because its compose project directory (`/home/pioneer/Downloads/ai-flood-system/`) was deleted. It has restart policy `unless-stopped` and consumes CPU on every restart cycle.
**Options:**
1. Stop and remove the container and volume.
2. Stop the container only, keep the volume.
3. Leave it running (not recommended).

---

**D-009 — Telegram credential rotation**
**Date:** 2026-09-16
**Status:** OPEN
**Decision required:** Rotate the Telegram bot token discovered in old Trash environment files before building Telegram integration.
**Current state:** A `TELEGRAM_BOT_TOKEN` was found in deleted `.env` files in the system Trash. The token may still be active. Trash is not secure storage.
**Action needed:** Check the token via BotFather. If active, revoke and issue a new one. The new token must only reside in `.env` (which is `.gitignore`d).
