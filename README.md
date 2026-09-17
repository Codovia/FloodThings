# FloodPulse

**Karnataka AI Flood Intelligence & Early-Warning System**

A Karnataka-focused flood intelligence and emergency-response decision-support system combining legitimate environmental data, GIS, machine-learning predictions, official warnings, emergency facilities, community reports, and Telegram alerts.

> **This is a decision-support system.** It does not replace official government flood warnings from IMD, CWC, KSNDMC, or any other authority.

---

## Current Phase

**Phase 2.1 — Project Foundation**

The engineering foundation has been established. Data sources, predictions, and emergency response features will be added in subsequent phases.

---

## Architecture

```
Modular monolith

Frontend (React + Vite)
    ↓
Backend (FastAPI)
    ↓
Database (PostgreSQL 16 + PostGIS 3.4)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture document.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite 6 |
| Backend | FastAPI |
| Database | PostgreSQL 16 |
| Spatial DB | PostGIS 3.4 |
| ORM | SQLAlchemy 2 |
| Migrations | Alembic |
| GIS (planned) | GeoPandas, Shapely, PostGIS |
| ML (planned) | Python, scikit-learn |
| Maps (planned) | Leaflet |
| Notifications (planned) | Telegram |
| Background jobs (planned) | APScheduler |
| Containers | Docker Compose |

---

## Repository Structure

```
FloodPulse/
├── backend/
│   ├── app/
│   │   ├── api/          # API route handlers
│   │   ├── core/         # Configuration, settings
│   │   ├── db/           # Database session, models
│   │   └── main.py       # FastAPI application entry point
│   ├── migrations/       # Alembic migration scripts
│   ├── tests/            # Backend tests
│   ├── Dockerfile
│   ├── requirements.txt
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Main application component
│   │   ├── main.jsx      # React entry point
│   │   └── index.css     # Application styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── ml/                   # ML pipeline (future)
├── gis/                  # GIS data and scripts (future)
├── data/                 # Raw/processed datasets (future)
├── models/               # Trained model artifacts (future)
├── scripts/              # Utility scripts
├── tests/                # Cross-cutting tests
├── docs/                 # Project documentation
├── docker/               # Docker support files
│
├── docker-compose.yml    # PostgreSQL + PostGIS service
├── .env.example          # Environment template
├── .gitignore
└── README.md
```

---

## Prerequisites

- **Docker** and **Docker Compose** (for PostgreSQL/PostGIS)
- **Python 3.12** (backend virtual environment)
- **Node.js 22+** and **npm** (frontend)
- **Git**

---

## Environment Setup

### 1. Clone and configure

```bash
git clone https://github.com/Codovia/FloodThings.git FloodPrediction
cd FloodPrediction
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and DATABASE_URL
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

### 3. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create backend/.env with DATABASE_URL
# Example: DATABASE_URL=postgresql+psycopg2://floodpulse:<password>@localhost:5432/floodpulse

uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

The frontend proxies `/api/*` requests to the backend at `localhost:8001`.

---

## Docker Commands

```bash
# Start database
docker compose up -d postgres

# Check status
docker compose ps

# View logs
docker compose logs postgres

# Stop
docker compose down

# PostgreSQL shell
docker exec -it floodpulse-postgres psql -U floodpulse -d floodpulse

# Verify PostGIS
docker exec floodpulse-postgres psql -U floodpulse -d floodpulse -c "SELECT PostGIS_Version();"
```

---

## Health Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | API process liveness |
| `GET /health/database` | Real database connectivity check |
| `GET /health/postgis` | Real PostGIS extension verification |

All endpoints return honest status. If the database is down, `/health/database` reports `"status": "down"` — it never returns a fake success.

---

## Testing

```bash
# Unit tests (no database required)
cd backend
source .venv/bin/activate
PYTHONPATH=. python -m pytest tests/test_health.py -v

# Integration tests (requires running PostgreSQL)
PYTHONPATH=. python -m pytest tests/test_health_integration.py -v

# All tests
PYTHONPATH=. python -m pytest tests/ -v

# Skip integration tests (e.g., in CI without database)
PYTHONPATH=. python -m pytest tests/ -v -m "not integration"
```

---

## Alembic Migrations

```bash
cd backend
source .venv/bin/activate

# Check current migration state
PYTHONPATH=. alembic current

# Generate a new migration after model changes
PYTHONPATH=. alembic revision --autogenerate -m "description"

# Apply migrations
PYTHONPATH=. alembic upgrade head

# Rollback one migration
PYTHONPATH=. alembic downgrade -1
```

---

## Development Workflow

```
INSPECT → UNDERSTAND → PLAN → IMPLEMENT → TEST → REVIEW DIFF → UPDATE DOCS → COMMIT
```

- One logical change per commit
- No fabricated environmental data — ever
- Missing data = `UNAVAILABLE`, not invented values
- AI predictions and official warnings are always separate
- See [docs/CONSTRAINTS.md](docs/CONSTRAINTS.md) for full rules

---

## Data Integrity Rules

Every environmental observation must come from a legitimate, attributable source. The system uses these data classifications:

| Classification | Meaning |
|---|---|
| `REAL` | Directly from a verified source |
| `DERIVED_FROM_REAL` | Calculated from real data; transformation documented |
| `MODEL_OUTPUT` | Generated by an ML model |
| `USER_REPORTED` | Citizen-submitted; never auto-treated as ground truth |
| `UNKNOWN / UNVERIFIED` | Cannot currently be validated |

See [docs/CONSTRAINTS.md](docs/CONSTRAINTS.md) and [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

---

## Project Documentation

All project-control documents are in [docs/](docs/):

| Document | Purpose |
|---|---|
| [MASTER_PROJECT_SPEC.md](docs/MASTER_PROJECT_SPEC.md) | Full project specification |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [CONSTRAINTS.md](docs/CONSTRAINTS.md) | Non-negotiable rules |
| [DECISIONS.md](docs/DECISIONS.md) | Architectural decision log |
| [HANDOVER.md](docs/HANDOVER.md) | Session continuity document |
| [DATA_SOURCES.md](docs/DATA_SOURCES.md) | Data source registry |
| [DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Internal data contract |
| [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Field definitions |
| [ML_SPEC.md](docs/ML_SPEC.md) | ML pipeline specification |
| [GIS_SPEC.md](docs/GIS_SPEC.md) | GIS specification |
| [API_SPEC.md](docs/API_SPEC.md) | API specification |
| [SECURITY.md](docs/SECURITY.md) | Security guidelines |
| [TEST_CHECKLIST.md](docs/TEST_CHECKLIST.md) | Testing checklist |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide |
| [FLOW.md](docs/FLOW.md) | System data flow |
| [AGENT_RULES.md](docs/AGENT_RULES.md) | Agent development rules |

---

## License

Private — Codovia
