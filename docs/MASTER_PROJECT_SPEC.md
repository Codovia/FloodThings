# 30-Day Execution Plan — Karnataka AI Flood Intelligence & Early-Warning System

We should **restart cleanly**, but not restart the knowledge. The existing specifications become the contract, while the implementation starts from a clean repository. Your master specification explicitly requires this sequence and says the system must be defensible from source → data validation → GIS → ML → prediction → alert. 

With only **30 days**, the strategy should be:

> **Build a smaller, complete, demonstrable, scientifically defensible system rather than attempting every possible feature.**

The project will use **Agentic AI as the development team**, but you remain the technical owner and reviewer.

---

# 1. Final 30-Day Target

By the end of Day 30, we should have:

```text
                    KARNATAKA FLOODPULSE
                           │
             ┌─────────────┴─────────────┐
             │                           │
          CITIZEN                     ADMIN
             │                           │
      ┌──────┴───────┐          ┌────────┴────────┐
      │              │          │                 │
   Dashboard      Shelter     Monitoring       Management
      │            Finder         │                 │
      │              │            │                 │
      └──────┬───────┘            │                 │
             │                     │                 │
          FastAPI API ─────────────┴─────────────────┘
             │
       PostgreSQL/PostGIS
             │
    ┌────────┼───────────┐
    │        │           │
 Weather   Hydrology    GIS
    │        │           │
    └────────┼───────────┘
             │
      Feature Pipeline
             │
       Validated ML Model
             │
       Flood Prediction
             │
      Alert Decision Engine
             │
          Telegram
```

The **core demonstration flow** should be:

```text
Real weather/hydrology data
        ↓
Data validation
        ↓
GIS location
        ↓
Feature engineering
        ↓
ML prediction
        ↓
Risk level
        ↓
Affected area
        ↓
Find safe shelter
        ↓
Check occupancy/capacity
        ↓
Calculate route
        ↓
User navigation
        ↓
Telegram alert
```

That gives you a much stronger project presentation than simply showing a prediction dashboard.

---

# 2. Technology Stack — Freeze This

Do **not** keep changing technologies during the 30 days.

| Layer               | Technology                                               |
| ------------------- | -------------------------------------------------------- |
| Frontend            | React + Vite                                             |
| Backend             | FastAPI                                                  |
| Database            | PostgreSQL                                               |
| Spatial DB          | PostGIS                                                  |
| ML                  | Python + scikit-learn initially                          |
| GIS                 | GeoPandas + Shapely + PostGIS                            |
| Maps                | Leaflet                                                  |
| Routing             | GraphHopper/OSRM-type routing service after verification |
| Notifications       | Telegram                                                 |
| Background jobs     | APScheduler                                              |
| API testing         | Postman                                                  |
| ML training         | Google Colab                                             |
| Containers          | Docker Compose                                           |
| Version control     | Git + GitHub                                             |
| Documentation       | Markdown                                                 |
| Agentic development | Antigravity/your coding agent                            |

The master specification already establishes React, FastAPI, PostgreSQL/PostGIS, Python GIS/ML, REST/OpenAPI, token authentication, Telegram, Docker and a modular monolith. 

**Do not introduce Kafka, Kubernetes, microservices, blockchain, chatbot, SMS or email during these 30 days.** The specification explicitly excludes them from the initial scope. 

---

# 3. How We Will Use Agentic AI

This is important.

Do **not** tell the agent:

> "Build my entire flood project."

That is how the repository gets destroyed again.

Instead, we create an **Agent Operating System** for the project.

## Agent hierarchy

```text
                    YOU
                     │
              Project Owner
                     │
             ┌───────┴───────┐
             │               │
        Planning Agent    Review Agent
             │
      ┌──────┼─────────┐
      │      │         │
   Backend   GIS       ML
   Agent     Agent     Agent
      │      │         │
      └──────┼─────────┘
             │
        Frontend Agent
             │
        Integration Agent
             │
        Testing Agent
```

You don't actually need six independent AI systems. We can use **one strong coding agent with specialized roles/prompts** and strict handoffs.

---

# 4. Agent Rules

Every agent must begin by reading:

```text
docs/MASTER_PROJECT_SPEC.md
docs/CONSTRAINTS.md
docs/ARCHITECTURE.md
docs/HANDOVER.md
```

Then the relevant specification.

This exact reading order is already required by your project specification. 

Then:

```text
INSPECT
   ↓
PLAN
   ↓
IMPLEMENT ONE LOGICAL CHANGE
   ↓
TEST
   ↓
INSPECT DIFF
   ↓
UPDATE DOCS
   ↓
UPDATE HANDOVER
   ↓
COMMIT
```

If an agent encounters missing information:

```text
STOP
 ↓
REPORT
 ↓
DO NOT INVENT
```

This is particularly important because your project prohibits fabricated environmental data and unverified APIs. 

---

# 5. The 30-Day Schedule

## PHASE 0 — PROJECT CONTROL

### Days 1–2

### Day 1 — Freeze the project

Tasks:

* clean repository
* create Git strategy
* create project-control documents
* freeze architecture
* freeze scope
* define user/admin roles
* define MVP
* define stretch features
* create decision log
* create agent instructions

Repository:

```text
FloodPulse/
├── backend/
├── frontend/
├── ml/
├── gis/
├── data/
├── models/
├── scripts/
├── tests/
├── docs/
├── docker/
└── .github/
```

Documents:

```text
docs/
├── MASTER_PROJECT_SPEC.md
├── ARCHITECTURE.md
├── CONSTRAINTS.md
├── DATA_SOURCES.md
├── DATA_DICTIONARY.md
├── DATA_CONTRACT.md
├── GIS_SPEC.md
├── ML_SPEC.md
├── API_SPEC.md
├── SECURITY.md
├── TEST_CHECKLIST.md
├── DEPLOYMENT.md
├── BACKUP_RECOVERY.md
├── DECISIONS.md
├── FLOW.md
├── HANDOVER.md
└── AGENT_RULES.md
```

Your specification explicitly identifies these project-control documents as part of the engineering system. 

---

### Day 2 — Environment + foundation

Build only:

```text
Docker
PostgreSQL
PostGIS
FastAPI
React
Git
Testing
```

Verify:

```text
Frontend → Backend
Backend → PostgreSQL
PostgreSQL → PostGIS
```

Endpoints:

```text
GET /health
GET /health/database
GET /health/postgis
```

**Day-2 exit condition:**

```text
React works
FastAPI works
DB works
PostGIS works
Git works
Docker works
Tests work
```

No ML.

No flood prediction.

No complicated dashboard.

---

# PHASE 1 — DATA FOUNDATION

## Days 3–6

This is the most important phase.

Your project should never reach ML before this.

### Day 3 — Data-source verification

Create:

```text
DATA_SOURCES.md
```

For every source:

```text
Source
Provider
Dataset/API
Purpose
Access method
License
Coverage
Temporal resolution
Spatial resolution
Units
Authentication
Status
Last tested
Known limitations
```

Statuses:

```text
CONFIRMED
ACCESS_PENDING
VALIDATION_PENDING
UNAVAILABLE
REJECTED
```

Candidate sources:

```text
IMD
KSNDMC
CWC
Karnataka Government
NRSC/Bhuvan
India-WRIS
Open-Meteo
OSM
Authoritative DEM
```

The specification specifically requires source verification before implementation. 

---

### Day 4 — API testing laboratory

This is where your learning goal fits perfectly.

Use **Postman**.

Create a collection:

```text
FloodPulse API Research
├── Weather
├── Rainfall
├── Hydrology
├── Forecast
├── GIS
└── Emergency
```

For every API:

```text
Request
↓
Response
↓
Headers
↓
Authentication
↓
Rate limit
↓
Fields
↓
Units
↓
Timestamp
↓
Location
```

Save the responses for **schema/reference testing**, not as fake production data.

Create:

```text
docs/api-tests/
```

---

### Day 5 — Database data model

Implement core tables.

Start with:

```text
data_sources
ingestion_runs

states
districts
taluks
localities

rivers
river_stations
river_observations

reservoirs
reservoir_observations

weather_observations
weather_forecasts
rainfall_observations

flood_events
flood_observations

prediction_grid_cells
feature_snapshots
ml_dataset_versions
ml_models
flood_predictions

emergency_facilities
shelters
shelter_occupancy

community_reports

alerts
telegram_subscriptions

users
audit_logs
```

Use Alembic migrations.

---

### Day 6 — Data validation framework

Build reusable validation.

For example:

```text
validate_timestamp()
validate_coordinates()
validate_crs()
validate_units()
validate_required_fields()
validate_duplicates()
validate_source()
validate_freshness()
```

Data states:

```text
REAL
DERIVED_FROM_REAL
MODEL_OUTPUT
USER_REPORTED
UNKNOWN
```

The existing rebuild specification requires exactly this distinction. 

---

# PHASE 2 — WEATHER + HYDROLOGY

## Days 7–10

### Day 7 — Weather ingestion

Implement only verified sources.

Pipeline:

```text
API
 ↓
adapter
 ↓
raw response
 ↓
validation
 ↓
normalization
 ↓
PostgreSQL
```

Example:

```text
temperature_c
rainfall_mm
humidity_pct
wind_speed_mps
pressure_hpa
observed_at
retrieved_at
latitude
longitude
source_id
```

---

### Day 8 — Rainfall feature pipeline

Create:

```text
1h rainfall
3h rainfall
6h rainfall
12h rainfall
24h rainfall
72h rainfall
7d rainfall
14d rainfall
```

**Only calculate a feature if the underlying data exists.**

Missing:

```text
NULL
```

not:

```text
0
```

and not:

```text
median
```

The old prototype's synthetic rainfall and inappropriate median fallback are specifically identified for removal. 

---

### Day 9 — River/reservoir

Implement whatever authoritative data access actually works.

Potential fields:

```text
water_level_m
discharge_m3s
observed_at
station_id
source
quality
```

Reservoir:

```text
water_level
storage
inflow
outflow
observed_at
source
```

Unavailable source:

```text
UNAVAILABLE
```

Not fake values.

---

### Day 10 — Source-health system

Build:

```text
source status
last successful ingestion
last record
freshness
failure reason
```

Dashboard:

```text
IMD        FRESH
Rainfall   FRESH
CWC        STALE
Reservoir  UNAVAILABLE
```

This will score well academically because it demonstrates engineering maturity.

---

# PHASE 3 — GIS

## Days 11–13

### Day 11 — Karnataka GIS

Load verified:

```text
Karnataka boundary
Districts
Taluks
Rivers
Reservoirs
Water bodies
```

PostGIS.

Implement:

```text
point → district
point → taluk
point → locality
```

using spatial operations.

Not:

```text
if city == ...
```

---

### Day 12 — Terrain

Use an actual DEM.

Generate:

```text
elevation
slope
distance_to_river
terrain-related features
```

The existing specification explicitly says slope must be derived from real terrain rather than arbitrary values. 

---

### Day 13 — Flood GIS

Implement map layers:

```text
Districts
Rivers
Reservoirs
Rainfall
Flood observations
Flood hazard
AI predictions
Shelters
Hospitals
Police
Fire stations
```

Every layer gets:

```text
name
legend
source
freshness
visibility
```

as required by the specification. 

---

# PHASE 4 — HISTORICAL FLOOD DATA

## Days 14–16

This is where we decide whether the ML target is actually feasible.

### Day 14 — Historical dataset investigation

Search/obtain:

```text
historical rainfall
historical flood events
historical inundation
river observations
```

Create:

```text
data/raw/
data/manifests/
```

Every dataset gets:

```text
source
download date
coverage
license
checksum
schema
processing version
```

---

### Day 15 — Target engineering

First target:

```text
Flood event occurred
```

rather than pretending we can predict exact street-level water depth.

Possible target:

```text
district/grid_cell
+
time window
=
flood / no flood
```

The specification explicitly recommends a documented flood event within a spatial unit and prediction window as the first defensible target. 

---

### Day 16 — ML dataset

Produce:

```text
features
target
location
timestamp
event_id
dataset_version
```

Perform:

```text
missing-value analysis
class balance
duplicates
temporal leakage checks
spatial leakage checks
```

**ML does not start until this passes review.**

---

# PHASE 5 — MACHINE LEARNING

## Days 17–20

### Day 17 — Colab training environment

Use Google Colab.

Repository:

```text
ml/
├── preprocessing/
├── features/
├── training/
├── evaluation/
└── inference/
```

Notebook:

```text
01_dataset_validation.ipynb
02_baseline.ipynb
03_model_training.ipynb
04_evaluation.ipynb
```

---

### Day 18 — Baseline

Start simple.

Candidates:

```text
Logistic Regression
Random Forest
Gradient Boosting
```

Do not immediately jump to:

```text
LSTM
Transformer
CNN
Graph Neural Network
```

unless the dataset genuinely supports it.

This gives you an academically defensible comparison.

---

### Day 19 — Model evaluation

Evaluate:

```text
Precision
Recall
F1
PR-AUC
ROC-AUC
Confusion matrix
Calibration
```

Flood detection should prioritize recall, while still measuring false alarms.

Document:

```text
Model
Dataset
Features
Split
Metrics
Results
Limitations
```

---

### Day 20 — Model → API

Export:

```text
model.pkl
```

or appropriate serialized artifact.

Create:

```text
POST /predictions
GET /predictions/{location}
GET /predictions/latest
```

Prediction response:

```json
{
  "probability": 0.82,
  "risk_level": "HIGH",
  "prediction_window": "...",
  "model_version": "...",
  "dataset_version": "...",
  "input_quality": "FRESH"
}
```

The actual response structure should follow your finalized API contract.

---

# PHASE 6 — SHELTER + EVACUATION

## Days 21–23

This is the feature we recently researched and should make your project stand out.

### Day 21 — Shelter database

Implement:

```text
shelter_id
name
type
latitude
longitude
district
taluk

capacity_total
occupancy_current
capacity_available

status
managing_authority
contact

water
toilets
food
electricity
medical
women
children
elderly
disabled_access

flood_risk
safe_for_flood
last_verified_at
occupancy_updated_at
```

Occupancy must never be invented.

Statuses:

```text
OPEN
FULL
CLOSED
TEMPORARILY_UNAVAILABLE
UNKNOWN
```

---

### Day 22 — Shelter finder

User:

```text
Allow GPS
     ↓
current coordinates
     ↓
FloodPulse API
     ↓
find shelters
     ↓
remove unsafe/full shelters
     ↓
rank remaining shelters
```

Ranking should consider:

```text
route safety
flood risk
capacity
distance
ETA
accessibility
freshness
```

Not simply:

```text
nearest shelter
```

---

### Day 23 — Navigation

Implement:

```text
Current location
       ↓
Safe shelter
       ↓
Routing engine
       ↓
distance
ETA
route
```

Frontend:

```text
FIND SAFE SHELTER
        ↓
Shelter A
1.8 km
12 min
Available: 120
        ↓
NAVIGATE
```

Important:

> **Shortest route ≠ safest route.**

If a road is inside a dangerous flood area or officially reported blocked, it should not be treated as a normal route.

---

# PHASE 7 — APPLICATION

## Days 24–26

### Day 24 — Citizen dashboard

Main screen:

```text
┌──────────────────────────────────┐
│ Karnataka FloodPulse             │
├──────────────────────────────────┤
│ Current Risk: MODERATE           │
│                                  │
│ Rainfall: 48 mm / 24h            │
│ Forecast: Heavy Rain              │
│                                  │
│ [OPEN FLOOD MAP]                 │
│ [FIND SAFE SHELTER]              │
│ [REPORT FLOOD]                   │
└──────────────────────────────────┘
```

---

### Day 25 — Map

Layers:

```text
Flood risk
Rainfall
River
Reservoir
Shelter
Hospital
Police
Fire
```

Popup:

```text
District: Mysuru

Flood Risk
HIGH

Probability
82%

Data
Fresh

Model
v1.0
```

---

### Day 26 — Community reports

User can submit:

```text
Location
Report type
Description
Photo
Timestamp
```

Status:

```text
SUBMITTED
UNDER_REVIEW
VERIFIED
REJECTED
```

Never automatically convert a citizen report into ML ground truth.

---

# PHASE 8 — ALERTS + ADMIN

## Days 27–28

### Day 27 — Telegram alert engine

Pipeline:

```text
Prediction
    ↓
Risk transition
    ↓
Alert rules
    ↓
Telegram
```

Example:

```text
LOW → MODERATE
MODERATE → HIGH
HIGH → EXTREME
```

Avoid:

```text
HIGH → HIGH
HIGH → HIGH
HIGH → HIGH
```

repeated notifications.

Telegram:

```text
⚠ FloodPulse Alert

High flood risk detected.

Location:
Mysuru

Risk:
HIGH

Prediction:
82%

Nearest suitable shelter:
ABC Relief Centre

Available capacity:
120

Open FloodPulse:
[View Shelter & Route]
```

Actual production wording should clearly distinguish AI prediction from official warnings.

---

### Day 28 — Admin dashboard

Admin sees:

```text
SYSTEM STATUS

Data Sources
├── Weather       FRESH
├── Rainfall      FRESH
├── River         STALE
└── Reservoir     AVAILABLE

FLOOD STATUS

HIGH RISK         7
MODERATE         13
LOW              11

SHELTERS

OPEN             31
FULL              4
CLOSED            2

ALERTS

Telegram Sent    142
Failed             3
```

Admin functions:

```text
manage shelters
update occupancy
verify reports
manage alerts
inspect data sources
view audit logs
```

---

# PHASE 9 — INTEGRATION + HARDENING

## Days 29–30

### Day 29 — Full-system testing

Run:

```text
Frontend tests
Backend tests
API tests
Database tests
GIS tests
ML tests
Alert tests
Shelter tests
Security tests
```

End-to-end:

```text
API data
 ↓
DB
 ↓
features
 ↓
ML
 ↓
prediction
 ↓
map
 ↓
shelter
 ↓
route
 ↓
Telegram
```

Test failures deliberately:

```text
API unavailable
DB unavailable
missing rainfall
stale rainfall
invalid coordinates
no shelter
shelter full
route unavailable
Telegram failure
```

The specification specifically requires resilience to unavailable sources and explicit stale/unavailable states. 

---

### Day 30 — Final freeze

No major features.

Only:

```text
bug fixing
UI cleanup
documentation
README
architecture diagram
ER diagram
API documentation
ML report
test report
limitations
deployment
presentation
demo script
```

Create:

```text
FINAL/
├── project_report/
├── presentation/
├── demo_script.md
├── viva_questions.md
├── architecture.png
├── er_diagram.png
├── ml_results.png
└── test_report.md
```

---

# 6. What We Absolutely Must NOT Build

With 30 days, these are distractions:

```text
❌ AI chatbot
❌ Blockchain
❌ Kubernetes
❌ Microservices
❌ SMS
❌ Email
❌ WhatsApp
❌ Mobile native app
❌ Complex IoT hardware
❌ Automated ML retraining
❌ Huge LLM pipeline
❌ Custom routing engine from scratch
❌ Full hydraulic simulation
❌ Nationwide flood prediction
```

Your specification itself recommends cutting advanced/nonessential features before sacrificing data validation, provenance, target validation, leakage prevention, tests and security. 

---

# 7. What Gets Highest Priority for Marks

I would organize the final project around **8 demonstrable pillars**:

### 1. Real Data

```text
Official/verified sources
↓
API
↓
validation
↓
database
```

### 2. GIS

```text
Karnataka
↓
District
↓
Locality
↓
Flood-risk map
```

### 3. Machine Learning

```text
Historical data
↓
features
↓
target
↓
model
↓
evaluation
↓
prediction
```

### 4. Explainability

Show:

```text
Why is this location HIGH risk?

Rainfall       ↑
River level    ↑
Terrain        ↓
Historical flood events
Forecast rainfall
```

### 5. Shelter Intelligence

```text
GPS
↓
safe shelters
↓
capacity
↓
occupancy
↓
route
↓
ETA
```

### 6. Alerting

```text
risk transition
↓
Telegram
```

### 7. Admin

```text
data
shelters
occupancy
reports
alerts
audit
```

### 8. Provenance

Every important number can answer:

```text
Where did this come from?
When was it measured?
When was it retrieved?
Is it fresh?
Was it derived?
Which model produced it?
```

That is exactly the kind of defensibility your master specification is designed around. 

---

# 8. The Most Important Change From Our Previous Attempt

Previously we were trying to solve:

```text
DATA
+ GIS
+ ML
+ APIs
+ Docker
+ Frontend
+ Shelter
+ Routing
+ Alerts
```

all at once.

We will now work like this:

```text
                    DAY 1
                     │
                 FOUNDATION
                     │
                     ▼
                  DATA
                     │
                     ▼
                   GIS
                     │
                     ▼
             HISTORICAL DATA
                     │
                     ▼
                    ML
                     │
                     ▼
                PREDICTION
                     │
             ┌───────┴───────┐
             ▼               ▼
          SHELTER          ALERT
             │               │
             └───────┬───────┘
                     ▼
                 DASHBOARD
                     │
                     ▼
                  ADMIN
                     │
                     ▼
                   TEST
                     │
                     ▼
                  DEPLOY
```

This follows the project's approved development order. 

---

# 9. Daily Agent Workflow

Every day we use this cycle:

```text
08:00
│
├── Read HANDOVER
│
├── Read relevant specification
│
├── Check Git status
│
├── Define today's objective
│
├── Agent implements
│
├── Agent tests
│
├── We inspect output
│
├── Fix
│
├── Commit
│
└── Update HANDOVER
```

At the end of every day:

```text
git status
git diff
git log
```

and update:

```text
HANDOVER.md
DECISIONS.md
TEST_CHECKLIST.md
```

---

# 10. Daily Deliverables

| Day | Deliverable                             |
| --: | --------------------------------------- |
|   1 | Clean repository + project control      |
|   2 | Docker + DB + PostGIS + React + FastAPI |
|   3 | Verified data-source register           |
|   4 | Postman API laboratory                  |
|   5 | Database schema                         |
|   6 | Data validation framework               |
|   7 | Weather ingestion                       |
|   8 | Rainfall features                       |
|   9 | River/reservoir                         |
|  10 | Source health                           |
|  11 | Karnataka GIS                           |
|  12 | Terrain                                 |
|  13 | Flood GIS                               |
|  14 | Historical dataset                      |
|  15 | Flood target                            |
|  16 | ML dataset                              |
|  17 | Colab pipeline                          |
|  18 | Baseline model                          |
|  19 | Evaluation                              |
|  20 | Prediction API                          |
|  21 | Shelter DB                              |
|  22 | Shelter finder                          |
|  23 | GPS routing                             |
|  24 | Citizen dashboard                       |
|  25 | Flood map                               |
|  26 | Community reports                       |
|  27 | Telegram                                |
|  28 | Admin                                   |
|  29 | Integration testing                     |
|  30 | Final freeze + presentation             |

---

# 11. MVP vs Stretch

This distinction will protect us.

## MUST WORK

```text
✓ Karnataka GIS
✓ real weather/rainfall data
✓ historical flood dataset
✓ validated ML model
✓ prediction API
✓ flood-risk map
✓ shelter finder
✓ GPS
✓ capacity/occupancy
✓ routing
✓ Telegram
✓ authentication
✓ admin
✓ community reporting
✓ provenance
✓ tests
✓ Docker
```

## ONLY IF TIME REMAINS

```text
○ advanced terrain modelling
○ more flood types
○ sophisticated route hazard avoidance
○ advanced analytics
○ additional GIS layers
○ model comparison dashboard
○ automated retraining
○ advanced shelter allocation
```

---

# 12. Our Agentic AI Command Structure

For each development task, we will give the coding agent a **small, controlled mission**.

For example:

> **Mission 001 — Initialize database foundation**
>
> Read `MASTER_PROJECT_SPEC.md`, `CONSTRAINTS.md`, `ARCHITECTURE.md`, and `HANDOVER.md`.
>
> Inspect the repository before changing anything.
>
> Implement only PostgreSQL/PostGIS connectivity and health checks.
>
> Do not implement weather, ML, GIS, shelters or frontend features.
>
> Run tests.
>
> Inspect the git diff.
>
> Update `HANDOVER.md`.
>
> Report:
>
> * files changed
> * commands executed
> * tests
> * problems
> * assumptions
> * next recommended task.
>
> Do not fabricate data.

That is how we will use the agent for the entire 30 days.

---

# 13. One Rule for You

You do **not** need to become an expert in everything in 30 days.

You need to understand enough to explain:

```text
Why this source?
Why this dataset?
Why this target?
Why this model?
How was it evaluated?
How does GIS work?
How does GPS find the shelter?
How is shelter capacity calculated?
How does the alert trigger?
What happens when data is unavailable?
How do we prevent false claims?
```

The project specification explicitly says you should be able to explain the AI-generated changes yourself before accepting them. 

---

# 14. Starting Point — Today

Since today is **15 September 2026**, I recommend we treat today as:

## DAY 1 — CLEAN RESTART

We should **not start writing application features yet**.

Today's sequence should be:

```text
1. Inspect current FloodPulse/FloodPrediction repository
        ↓
2. Preserve old work in a backup branch
        ↓
3. Decide final repository name
        ↓
4. Create clean project structure
        ↓
5. Copy the master specifications into docs/
        ↓
6. Create AGENT_RULES.md
        ↓
7. Create HANDOVER.md
        ↓
8. Create DECISIONS.md
        ↓
9. Initialize clean Git baseline
        ↓
10. Verify Docker/PostGIS
        ↓
11. Commit
```

**Tomorrow begins the actual source/API investigation.**

This is the correct restart because your master specification explicitly identifies **Phase 2 — Clean Project Foundation** as the immediate next implementation task and says not to implement ML or external data ingestion during that foundation task. 

### The 30-day success criterion

We are **not** trying to build the world's most advanced flood system.

We are trying to produce this:

> **A Karnataka-focused, AI-assisted flood-risk and emergency-response system whose data, GIS, ML, shelter recommendation, routing, alerts, and limitations can all be demonstrated and defended during the project evaluation.**

That is achievable in 30 days if we enforce the sequence above and let the coding agent handle repetitive implementation while we control architecture, data validity, testing, and decisions.
