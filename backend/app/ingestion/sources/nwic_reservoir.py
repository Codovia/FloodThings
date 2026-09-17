"""
NWIC Karnataka reservoir telemetry source adapter.

Ingests verified daily reservoir monitoring observations:
- Source: Karnataka State Major Reservoirs daily telemetry via NWIC
- Columns: Reservoir Name, Basin, Sub Basin, River, Monitoring Date,
           Percentage Full, Reservoir Level (ft), Design Gross Capacity (TMC),
           Gross Capacity (TMC), Live Capacity (TMC), Inflow (Cusecs),
           Outflow to River (Cusecs)
- Strictly enforces verified unit conversions:
    Level: feet -> metres (feet * 0.3048)
    Storage/Capacity: TMC -> MCM (TMC * 28.3168)
    Inflow/Outflow: cusecs -> m³/s (cusecs * 0.0283168)
- Zero fabrication: missing values remain NULL (missing != 0).
- Preserves raw CSV in data/raw/nwic/ before processing.
- Idempotent: deduplicates via source_record_id.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import re
from typing import Any
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.hydrology import (
    Reservoir,
    ReservoirObservation,
    River,
    RiverBasin,
)
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)
from app.ingestion.validation import (
    IST_TZ,
    DataCategory,
    QualityStatus,
    make_point_wkt,
    parse_utc_timestamp,
    validate_coordinates,
    validate_float,
)

RAW_NWIC_DIR = Path("data/raw/nwic")
DEFAULT_RESERVOIR_URL = (
    "https://nwdp.nwic.gov.in/dataset/e35dc28a-6f9c-486d-b598-87a21397018e/"
    "resource/26800982-045c-41de-821d-b1ca080a79a8/download/karnataka_man_reservoir_data.csv"
)

# Conversion factors per DATA_CONTRACT.md & DECISIONS.md
FEET_TO_METRES = 0.3048
TMC_TO_MCM = 28.3168
CUSECS_TO_CUMECS = 0.0283168

# Known metadata for major Karnataka reservoirs
KNOWN_RESERVOIRS: dict[str, dict[str, Any]] = {
    "ALMATTI": {"name": "Almatti Dam", "lat": 16.3317, "lon": 75.8872, "river": "Krishna", "basin": "Krishna"},
    "KRS": {"name": "Krishnaraja Sagara Dam", "lat": 12.5369, "lon": 76.5714, "river": "Cauvery", "basin": "Cauvery"},
    "KABINI": {"name": "Kabini Reservoir", "lat": 11.9725, "lon": 76.3533, "river": "Kabini", "basin": "Cauvery"},
    "TUNGABHADRA": {"name": "Tungabhadra Dam", "lat": 15.2608, "lon": 76.3403, "river": "Tungabhadra", "basin": "Krishna"},
    "HARANGI": {"name": "Harangi Reservoir", "lat": 12.4925, "lon": 75.9083, "river": "Harangi", "basin": "Cauvery"},
    "HEMAVATHI": {"name": "Hemavathi Reservoir", "lat": 12.7833, "lon": 76.0500, "river": "Hemavathi", "basin": "Cauvery"},
    "LINGANAMAKKI": {"name": "Linganamakki Dam", "lat": 14.1950, "lon": 74.8417, "river": "Sharavathi", "basin": "West Flowing Rivers"},
    "BHADRA": {"name": "Bhadra Reservoir", "lat": 13.7000, "lon": 75.6333, "river": "Bhadra", "basin": "Krishna"},
    "GHATAPRABHA": {"name": "Ghataprabha (Hidkal) Dam", "lat": 16.1472, "lon": 74.6361, "river": "Ghataprabha", "basin": "Krishna"},
    "MALAPRABHA": {"name": "Malaprabha (Renukasagar) Dam", "lat": 15.8236, "lon": 75.1147, "river": "Malaprabha", "basin": "Krishna"},
    "SUPA": {"name": "Supa Dam", "lat": 15.2750, "lon": 74.5333, "river": "Kali", "basin": "West Flowing Rivers"},
    "VARAHI": {"name": "Varahi Reservoir", "lat": 13.6833, "lon": 74.9833, "river": "Varahi", "basin": "West Flowing Rivers"},
}


class NwicReservoirAdapter(BaseAdapter):
    """Adapter for Karnataka Reservoir telemetry via NWIC."""

    source_name = "NWIC Karnataka Reservoir Telemetry"
    organization = "Water Resources Department, Karnataka / NWIC"
    source_url = "https://nwic.gov.in"
    access_method = "OPEN_DATA_CSV"
    data_type = "HYDROLOGICAL"
    update_frequency = "DAILY"

    def __init__(self, session: Session, raw_dir: Path = RAW_NWIC_DIR):
        super().__init__(session)
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        csv_url: str = DEFAULT_RESERVOIR_URL,
        csv_content: str | None = None,
        max_records: int | None = None,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> IngestionResult:
        """Ingest Karnataka reservoir observations.

        Args:
            csv_url: source URL if content not passed directly.
            csv_content: raw CSV string (useful for offline testing).
            max_records: optional maximum records to process.
            client: optional custom httpx.Client.
        """
        metrics = IngestionMetrics()
        started_at = datetime.now(timezone.utc)

        data_source = get_or_create_data_source(
            self.session,
            name=self.source_name,
            organization=self.organization,
            description="Daily manual monitoring data of major reservoirs in Karnataka",
            source_url=csv_url,
            access_method=self.access_method,
            data_type=self.data_type,
            geographic_coverage="Karnataka State",
            update_frequency=self.update_frequency,
            license_type="Government Open Data License - India (GODL)",
        )

        run = start_ingestion_run(self.session, data_source.id)
        retrieved_at = datetime.now(timezone.utc)

        should_close_client = False
        if csv_content is None and client is None:
            client = httpx.Client(timeout=45.0, verify=False)
            should_close_client = True

        try:
            # 1. Download or accept raw CSV
            if csv_content is None:
                assert client is not None
                resp = client.get(csv_url)
                resp.raise_for_status()
                raw_text = resp.text
            else:
                raw_text = csv_content

            # 2. Raw Data Preservation
            ts_slug = retrieved_at.strftime("%Y%m%d_%H%M%S")
            raw_file = self.raw_dir / f"nwic_reservoir_karnataka_{ts_slug}.csv"
            with open(raw_file, "w", encoding="utf-8") as f:
                f.write(raw_text)

            # 3. Cache basins, rivers, reservoirs
            basin_cache: dict[str, RiverBasin] = {}
            for b in self.session.execute(select(RiverBasin)).scalars():
                basin_cache[b.name.upper()] = b

            river_cache: dict[str, River] = {}
            for r in self.session.execute(select(River)).scalars():
                river_cache[r.name.upper()] = r

            res_cache: dict[str, Reservoir] = {}
            for r in self.session.execute(select(Reservoir)).scalars():
                if r.code:
                    res_cache[r.code.upper()] = r
                res_cache[r.name.upper()] = r

            # 4. Parse CSV
            reader = csv.DictReader(io.StringIO(raw_text))
            rows_processed = 0

            for raw_row in reader:
                metrics.records_received += 1
                # Clean keys: replace newlines and normalize whitespace
                row = {re.sub(r"\s+", " ", k.strip()): v.strip() for k, v in raw_row.items() if k}

                res_name = row.get("Reservoir Name")
                if not res_name:
                    metrics.records_rejected += 1
                    continue

                basin_name = row.get("Basin") or "Unspecified Basin"
                river_name = row.get("River") or "Unspecified River"

                # Standardize reservoir key/code
                res_code = re.sub(r"[^A-Z0-9]", "_", res_name.upper())[:30].strip("_")

                # Match known reservoir coordinates if available
                known = None
                for k_prefix, k_meta in KNOWN_RESERVOIRS.items():
                    if k_prefix in res_code:
                        known = k_meta
                        break

                lat = known["lat"] if known else None
                lon = known["lon"] if known else None
                geom = make_point_wkt(lat, lon) if (lat is not None and lon is not None) else None

                # RiverBasin entity
                b_key = basin_name.upper()
                if b_key not in basin_cache:
                    basin = RiverBasin(id=uuid.uuid4(), name=basin_name, code=b_key[:20])
                    self.session.add(basin)
                    self.session.flush()
                    basin_cache[b_key] = basin
                basin = basin_cache[b_key]

                # River entity
                r_key = river_name.upper()
                if r_key not in river_cache:
                    river = River(id=uuid.uuid4(), name=river_name, basin_id=basin.id)
                    self.session.add(river)
                    self.session.flush()
                    river_cache[r_key] = river
                river = river_cache[r_key]

                # Parse Design Gross Capacity (TMC -> MCM)
                raw_design_cap_tmc = row.get("Design Gross Capacity (TMC)")
                design_cap_tmc = validate_float(raw_design_cap_tmc, min_val=0.0)
                design_cap_mcm = design_cap_tmc * TMC_TO_MCM if design_cap_tmc is not None else None

                # Reservoir entity
                if res_code not in res_cache:
                    res_entity = Reservoir(
                        id=uuid.uuid4(),
                        name=res_name,
                        code=res_code,
                        river_id=river.id,
                        basin_id=basin.id,
                        latitude=lat,
                        longitude=lon,
                        geometry=geom,
                        capacity=design_cap_mcm,
                        source_id=data_source.id,
                        is_active=True,
                    )
                    self.session.add(res_entity)
                    self.session.flush()
                    res_cache[res_code] = res_entity
                    res_cache[res_name.upper()] = res_entity
                res_entity = res_cache[res_code]

                # Observation timestamp
                raw_date = row.get("Monitoring Date")
                obs_dt = parse_utc_timestamp(raw_date, default_tz=IST_TZ)
                if obs_dt is None:
                    metrics.records_rejected += 1
                    metrics.errors.append(f"Invalid timestamp '{raw_date}' for reservoir {res_name}")
                    continue

                # Unit Conversions
                # 1. Level (ft -> m)
                raw_level_ft = row.get("Reservoir Level (ft)")
                level_ft = validate_float(raw_level_ft, min_val=0.0, max_val=5000.0)
                level_m = (level_ft * FEET_TO_METRES) if level_ft is not None else None

                # 2. Storage / Gross Capacity (TMC -> MCM)
                raw_storage_tmc = row.get("Gross Capacity (TMC)")
                storage_tmc = validate_float(raw_storage_tmc, min_val=0.0)
                storage_mcm = (storage_tmc * TMC_TO_MCM) if storage_tmc is not None else None

                # 3. Storage percentage
                raw_pct = row.get("Percentage Full")
                pct_full = validate_float(raw_pct, min_val=0.0, max_val=100.0)

                # 4. Inflow (Cusecs -> m³/s)
                raw_inflow = row.get("Inflow (Cusecs)")
                inflow_cusecs = validate_float(raw_inflow, min_val=0.0)
                inflow_m3s = (inflow_cusecs * CUSECS_TO_CUMECS) if inflow_cusecs is not None else None

                # 5. Outflow (Cusecs -> m³/s)
                raw_outflow = row.get("Outflow to River (Cusecs)")
                outflow_cusecs = validate_float(raw_outflow, min_val=0.0)
                outflow_m3s = (outflow_cusecs * CUSECS_TO_CUMECS) if outflow_cusecs is not None else None

                # Deduplication check
                source_record_id = f"nwic_res_{res_code}_{obs_dt.strftime('%Y%m%d%H%M')}"
                obs_stmt = select(ReservoirObservation).where(
                    ReservoirObservation.source_id == data_source.id,
                    ReservoirObservation.source_record_id == source_record_id,
                )
                existing = self.session.execute(obs_stmt).scalar_one_or_none()

                quality = (
                    QualityStatus.VALID
                    if (level_m is not None or storage_mcm is not None)
                    else QualityStatus.MISSING
                )

                if existing is None:
                    obs = ReservoirObservation(
                        id=uuid.uuid4(),
                        reservoir_id=res_entity.id,
                        observed_at=obs_dt,
                        water_level=level_m,
                        storage=storage_mcm,
                        storage_percentage=pct_full,
                        inflow=inflow_m3s,
                        outflow=outflow_m3s,
                        trend=None,
                        source_id=data_source.id,
                        source_record_id=source_record_id,
                        retrieved_at=retrieved_at,
                        quality_status=quality,
                        data_category=DataCategory.OBSERVATION,
                    )
                    self.session.add(obs)
                    metrics.records_inserted += 1

                metrics.records_valid += 1
                rows_processed += 1
                if max_records and rows_processed >= max_records:
                    break

            self.session.commit()
            status = "SUCCESS" if not metrics.errors else "PARTIAL"
            complete_ingestion_run(self.session, run, status=status, metrics=metrics)
            self.session.commit()

            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status=status,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
            )

        except Exception as exc:
            self.session.rollback()
            err_msg = str(exc)
            metrics.errors.append(err_msg)
            complete_ingestion_run(
                self.session, run, status="FAILED", metrics=metrics, error_message=err_msg
            )
            self.session.commit()
            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status="FAILED",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
                error_message=err_msg,
            )
        finally:
            if should_close_client and client:
                client.close()
