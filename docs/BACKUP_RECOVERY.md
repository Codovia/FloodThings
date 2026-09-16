# BACKUP_RECOVERY.md

**Project:** FloodPulse
**Status:** Planning document. No backup or recovery procedures are currently implemented.

---

## Source control

Git is the version control system for all application code, configuration, and documentation.

- Remote: GitHub (`Codovia/FloodThings`)
- Branch strategy: `main` is the primary branch.
- All source code, configuration files (except secrets), and documentation are tracked in Git.

---

## Database

### Backup (planned)

- Regular database backups must be automated once the application schema is established.
- `pg_dump` (or equivalent) is the expected backup mechanism.
- Backup frequency, retention period, and storage location will be defined during implementation.
- Backups should include schema and data.

### Recovery (planned)

- Recovery procedure: restore from `pg_dump` output into a clean PostGIS database.
- Recovery must be tested at least once before production use.

### Current state

No application schema exists in the database yet. No backup procedures are in place.

---

## Raw source data

Raw data downloaded from external sources should be reproducible through:

1. Source adapter code (which can re-fetch from the original source).
2. Ingestion manifests (documenting exactly what was fetched, when, from where).

Important data provenance must not depend solely on Git-tracked large datasets. Large raw datasets are `.gitignore`d and must be reproducible via their ingestion process.

---

## Model artifacts

Trained ML model artifacts (`.joblib`, `.pkl`, etc.) are `.gitignore`d. They must be:

- Versioned (model ID, training dataset version, hyperparameters).
- Stored with metadata documenting how to reproduce them.
- Backed up separately from Git if they cannot be retrained quickly.

---

## Configuration

- `.env` files are not tracked in Git. They must be documented via `.env.example`.
- If `.env` is lost, it can be reconstructed from `.env.example` plus the actual secret values (stored securely by the project owner).

---

## Recovery priorities

In order of importance:

1. **Application code** — recoverable from Git.
2. **Database schema** — recoverable from Alembic migrations (when implemented).
3. **Database data** — recoverable from backups (when implemented).
4. **Raw source data** — reproducible via source adapters and ingestion manifests.
5. **Model artifacts** — reproducible via training pipeline and dataset versions.
6. **Configuration** — reconstructable from `.env.example` + secrets.
