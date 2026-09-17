# FloodPulse — Data Ingestion Runbook

This runbook guides operators and developers on executing, verifying, and troubleshooting the FloodPulse data ingestion foundation implemented in **Phase 2.4**.

---

## 1. Architecture Overview

```text
External Source (Open-Meteo / NWIC / CWC / IFI)
                    ↓
   Raw Data Preservation (data/raw/<source>/)
                    ↓
   Validation (Schema, Type, Units, Coordinates, Timestamps)
                    ↓
   Normalization (SI / Contract Units: m, MCM, m³/s, mm, °C, m/s)
                    ↓
   PostgreSQL / PostGIS (EPSG:4326)
                    ↓
   DataIngestionRun & DataSource Provenance Tracking
```

---

## 2. Prerequisites

1. PostgreSQL 16 + PostGIS 3.4 container active:
   ```bash
   docker compose up -d postgres
   ```
2. Python virtual environment initialized with dependencies:
   ```bash
   source backend/.venv/bin/activate
   ```
3. Network access to verified endpoints:
   - Open-Meteo Forecast: `https://api.open-meteo.com/v1/forecast`
   - Open-Meteo Archive: `https://archive-api.open-meteo.com/v1/archive`
   - NWIC CWC River Stage: `https://nwdp.nwic.gov.in/...`
   - NWIC Karnataka Reservoir Telemetry: `https://nwdp.nwic.gov.in/...`
   - HydroSenseLab IFI v3.0: `https://raw.githubusercontent.com/...`

---

## 3. Manual Ingestion Commands

All ingestion operations are executed via `app.ingestion.cli`. Always set `PYTHONPATH=backend` or run from repository root with `backend/.venv/bin/python`.

### Step 1: Seed Administrative Geography (Mandatory First Step)
Seeds Karnataka state (LGD code: `29`) and all 31 administrative districts with official LGD codes and centroid coordinates.
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli geography
```

### Step 2: Ingest Open-Meteo Weather & Precipitation
- **Operational & Forecast**:
  ```bash
  PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli open-meteo --mode operational
  ```
- **Historical Reanalysis**:
  ```bash
  PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli open-meteo --mode historical --start-date 2024-07-01 --end-date 2024-07-07
  ```

### Step 3: Ingest NWIC / CWC River Gauge Observations
Downloads hourly CWC river stage telemetry for Karnataka basins, validates stage in metres, links stations to rivers and districts:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli nwic-river --max-records 100
```

### Step 4: Ingest NWIC Reservoir Telemetry
Downloads daily major reservoir monitoring observations for Karnataka, converts units (feet → m, TMC → MCM, cusecs → m³/s):
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli nwic-reservoir --max-records 100
```

### Step 5: Ingest India Flood Inventory (IFI v3.0) Historical Events
Imports historical flood events and district ground truth observations without creating premature ML labels:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli ifi --max-records 100
```

### Full Pipeline Ingestion
Runs all Tier-1 sources sequentially with run metrics and status summary:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli ingest-all --max-records 100
```

---

## 4. Inspection & Status Verification

Check table counts, timestamp ranges, and quality distributions across the database:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli status
```

Sample output:
```text
  Entity / Table               Row Count 
  ----------------------------------------
  States                       1         
  Districts                    31        
  River Basins                 2         
  Rivers                       2         
  River Stations               1         
  River Observations           100       
  Reservoirs                   1         
  Reservoir Observations       100       
  Weather Observations         137       
  Rainfall Observations        137       
  Weather Forecasts            55        
  Flood Events                 100       
  Flood Observations           190       
  Data Sources                 5         
  Data Ingestion Runs          ...       
```

---

## 5. Idempotency & Provenance Rules

- **Zero Duplicates**: Every observation table enforces deduplication by checking `(source_id, source_record_id)`. Re-running ingestion commands with identical source data results in `records_inserted = 0`.
- **Raw Data Preservation**: Raw HTTP JSON and CSV payloads are persisted under:
  - `data/raw/open_meteo/`
  - `data/raw/cwc/`
  - `data/raw/nwic/`
  - `data/raw/ifi/`
- **Run Tracking**: Every run creates a `data_ingestion_runs` row with timestamps, record counts, and status (`RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED`).
