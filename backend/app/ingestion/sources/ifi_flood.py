"""
India Flood Inventory (IFI v3.0) historical flood dataset source adapter.

Ingests verified historical flood disaster events for Karnataka (State Code 29):
- Source: India Flood Inventory v3.0 (HydroSenseLab / IMD)
- Columns: UEI, Start Date, End Date, Duration(Days), Main Cause, Districts,
           State_Codes, District_LGD_Codes, Severity, Human fatality, Extent of damage
- Populates FloodEvent (disaster event catalog) and FloodObservation (district-level ground truth).
- CRITICAL RULES:
    1. flood_depth is nullable — missing depth remains NULL (never 0 or estimated).
    2. No fabricated 'risk score' or ML labels created in this phase.
    3. Preserves raw source files in data/raw/ifi/.
    4. Idempotent deduplication via UEI and District LGD codes.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.flood import FloodEvent, FloodObservation
from app.db.models.geography import District
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
    parse_utc_timestamp,
    validate_float,
)

RAW_IFI_DIR = Path("data/raw/ifi")
DEFAULT_IFI_URL = (
    "https://raw.githubusercontent.com/hydrosenselab/India-Flood-Inventory/"
    "main/v3.0/India_Flood_Inventory_v3.csv"
)


class IfiFloodAdapter(BaseAdapter):
    """Adapter for India Flood Inventory historical ground truth events."""

    source_name = "India Flood Inventory (IFI v3.0)"
    organization = "HydroSenseLab / India Meteorological Department"
    source_url = "https://github.com/hydrosenselab/India-Flood-Inventory"
    access_method = "OPEN_DATA_CSV"
    data_type = "HISTORICAL_FLOOD_DISASTER"
    update_frequency = "STATIC"

    def __init__(self, session: Session, raw_dir: Path = RAW_IFI_DIR):
        super().__init__(session)
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        csv_url: str = DEFAULT_IFI_URL,
        csv_content: str | None = None,
        max_records: int | None = None,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> IngestionResult:
        """Ingest historical flood inventory for Karnataka.

        Args:
            csv_url: URL to download IFI CSV.
            csv_content: optional raw CSV string for offline/unit testing.
            max_records: optional maximum events to process.
            client: optional custom httpx.Client.
        """
        metrics = IngestionMetrics()
        started_at = datetime.now(timezone.utc)

        data_source = get_or_create_data_source(
            self.session,
            name=self.source_name,
            organization=self.organization,
            description="Historical flood inventory ground truth across India with LGD mapping",
            source_url=csv_url,
            access_method=self.access_method,
            data_type=self.data_type,
            geographic_coverage="Karnataka / Pan-India",
            update_frequency=self.update_frequency,
            license_type="Open Database License (ODbL) / Research Open Data",
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
            raw_file = self.raw_dir / f"ifi_v3_karnataka_{ts_slug}.csv"
            with open(raw_file, "w", encoding="utf-8") as f:
                f.write(raw_text)

            # 3. Cache Karnataka districts by LGD code
            dist_stmt = select(District)
            districts_by_code = {
                d.code: d for d in self.session.execute(dist_stmt).scalars() if d.code
            }

            # 4. Parse CSV with newline='' and increased field_size_limit for multi-line text fields
            import sys
            try:
                csv.field_size_limit(sys.maxsize)
            except OverflowError:
                csv.field_size_limit(2147483647)

            reader = csv.DictReader(io.StringIO(raw_text, newline=""))
            rows_processed = 0

            for raw_row in reader:
                # Handle BOM or spaces in header keys
                row = {k.strip("\ufeff ").strip(): v.strip() for k, v in raw_row.items() if k}

                state_codes_str = row.get("State_Codes", "")
                state_codes = [c.strip() for c in state_codes_str.split(",") if c.strip()]

                # Filter for Karnataka (State code 29)
                if "29" not in state_codes:
                    continue

                metrics.records_received += 1

                uei = row.get("UEI", "").strip()
                start_date_raw = row.get("Start Date")
                end_date_raw = row.get("End Date")
                main_cause = row.get("Main Cause", "Unspecified")
                districts_str = row.get("Districts", "")
                extent_damage = row.get("Extent of damage", "")
                severity = row.get("Severity") or "MODERATE"
                area_affected_raw = row.get("Area Affected")
                area_affected = validate_float(area_affected_raw, min_val=0.0)

                start_dt = parse_utc_timestamp(start_date_raw, default_tz=IST_TZ)
                end_dt = parse_utc_timestamp(end_date_raw, default_tz=IST_TZ)

                if start_dt is None:
                    metrics.records_rejected += 1
                    metrics.errors.append(f"Invalid start date '{start_date_raw}' for UEI {uei}")
                    continue

                # 1. Create or update FloodEvent
                event_name = f"Flood Event {uei} ({districts_str[:50]})" if uei else f"Flood Event {start_dt.strftime('%Y-%m-%d')}"
                event_desc = (
                    f"UEI: {uei}\nCause: {main_cause}\nDistricts: {districts_str}\n"
                    f"Damage: {extent_damage}\nHuman Fatalities: {row.get('Human fatality', 'N/A')}\n"
                    f"Human Displaced: {row.get('Human Displaced', 'N/A')}"
                )

                ev_stmt = select(FloodEvent).where(
                    FloodEvent.source_id == data_source.id,
                    FloodEvent.name == event_name,
                )
                existing_ev = self.session.execute(ev_stmt).scalar_one_or_none()

                if existing_ev is None:
                    flood_event = FloodEvent(
                        id=uuid.uuid4(),
                        name=event_name,
                        start_time=start_dt,
                        end_time=end_dt,
                        description=event_desc,
                        severity=severity,
                        affected_area=area_affected,
                        geometry=None,
                        source_id=data_source.id,
                        confidence=1.0,
                    )
                    self.session.add(flood_event)
                    self.session.flush()
                    metrics.records_inserted += 1

                # 2. Create FloodObservation for each affected Karnataka district
                district_lgds_str = row.get("District_LGD_Codes", "")
                district_lgds = [
                    d.strip() for d in district_lgds_str.split(",") if d.strip() and d.strip().isdigit()
                ]

                for d_code in district_lgds:
                    district = districts_by_code.get(d_code)
                    if district is None:
                        # District not in Karnataka or unmapped
                        continue

                    source_rec_id = f"ifi_{uei}_{d_code}"
                    obs_stmt = select(FloodObservation).where(
                        FloodObservation.source_id == data_source.id,
                        FloodObservation.source_record_id == source_rec_id,
                    )
                    existing_obs = self.session.execute(obs_stmt).scalar_one_or_none()

                    if existing_obs is None:
                        flood_obs = FloodObservation(
                            id=uuid.uuid4(),
                            observation_time=start_dt,
                            geometry=None,
                            flooded=True,
                            flood_depth=None,  # NEVER fill with 0 or estimate
                            district_id=district.id,
                            taluk_id=None,
                            basin_id=None,
                            source_id=data_source.id,
                            source_record_id=source_rec_id,
                            confidence=1.0,
                            quality_status=QualityStatus.VALID,
                            data_category=DataCategory.HISTORICAL_EVENT,
                        )
                        self.session.add(flood_obs)
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
