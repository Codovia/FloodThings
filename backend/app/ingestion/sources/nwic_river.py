"""
NWIC / Central Water Commission (CWC) river stage observations adapter.

Ingests verified CWC manual hourly river stage records from NWIC DP:
- Schema: SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,
          River,Basin,Latitude,Longitude,Data Acquisition Time,
          River Water Level Manual Hourly (meter)
- Raw CSV is preserved under data/raw/cwc/ before processing.
- Automatically links to RiverBasin, River, District (by LGD code), and RiverStation.
- Strictly idempotent via source_record_id deduplication.
- Water level units: metres (m).
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

from app.db.models.geography import District
from app.db.models.hydrology import River, RiverBasin, RiverObservation, RiverStation
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)
from app.ingestion.sources.geography import KARNATAKA_DISTRICTS_LGD
from app.ingestion.validation import (
    IST_TZ,
    DataCategory,
    QualityStatus,
    make_point_wkt,
    parse_utc_timestamp,
    validate_coordinates,
    validate_float,
)

RAW_CWC_DIR = Path("data/raw/cwc")
DEFAULT_CWC_RIVER_URL = (
    "https://nwdp.nwic.gov.in/dataset/d951a09c-6cf8-470e-be77-e80116f13d34/"
    "resource/37cba82e-f745-4004-80d2-b05cad65b8e4/download/rwl_manual_hr_cwc_009_2026_2030.csv"
)

AUTH_LGD_TO_DISTRICT_NAME: dict[str, str] = {
    d["code"]: d["name"] for d in KARNATAKA_DISTRICTS_LGD
}

DISTRICT_NAME_ALIASES: dict[str, str] = {
    "bengaluruurban": "Bangalore Urban",
    "bangaloreurban": "Bangalore Urban",
    "bengaluru": "Bangalore Urban",
    "bangalore": "Bangalore Urban",
    "bengalururural": "Bangalore Rural",
    "bangalorerural": "Bangalore Rural",
    "ramanagara": "Ramanagara",
    "ramanagar": "Ramanagara",
    "bengalurusouth": "Ramanagara",
    "kalaburagi": "Kalaburagi",
    "kalaburgi": "Kalaburagi",
    "gulbarga": "Kalaburagi",
    "kolar": "Kolar",
    "kolara": "Kolar",
    "chamarajanagar": "Chamarajanagara",
    "chamarajanagara": "Chamarajanagara",
    "chamarajnagar": "Chamarajanagara",
    "chikkamagaluru": "Chikkamagaluru",
    "chikmagalur": "Chikkamagaluru",
    "chikkamagalur": "Chikkamagaluru",
    "chikkaballapur": "Chikkaballapura",
    "chikkaballapura": "Chikkaballapura",
    "chikballapur": "Chikkaballapura",
    "shivamogga": "Shivamogga",
    "shimoga": "Shivamogga",
    "ballari": "Ballari",
    "bellary": "Ballari",
    "belagavi": "Belagavi",
    "belgaum": "Belagavi",
    "vijayapura": "Vijayapura",
    "bijapur": "Vijayapura",
    "uttarakannada": "Uttara Kannada",
    "northcanara": "Uttara Kannada",
    "dakshinakannada": "Dakshina Kannada",
    "southcanara": "Dakshina Kannada",
    "tumakuru": "Tumakuru",
    "tumkur": "Tumakuru",
    "mysuru": "Mysuru",
    "mysore": "Mysuru",
    "davanagere": "Davanagere",
    "davangere": "Davanagere",
    "dharwad": "Dharwad",
    "dharwar": "Dharwad",
    "vijayanagara": "Vijayanagara",
    "vijayanagar": "Vijayanagara",
    "yadgir": "Yadgir",
    "yadgiri": "Yadgir",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


class NwicRiverLevelAdapter(BaseAdapter):
    """Adapter for Central Water Commission (CWC) river level observations via NWIC."""

    source_name = "NWIC Central Water Commission River Gauge Telemetry"
    organization = "Central Water Commission (CWC) / National Water Informatics Centre (NWIC)"
    source_url = "https://nwic.gov.in"
    access_method = "OPEN_DATA_CSV"
    data_type = "HYDROLOGICAL"
    update_frequency = "HOURLY"

    def __init__(self, session: Session, raw_dir: Path | None = None):
        super().__init__(session)
        self.raw_dir = raw_dir or RAW_CWC_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_district(
        self,
        *,
        dist_lgd: str | None,
        dist_name_raw: str | None,
        station_name: str,
        districts_by_name: dict[str, District],
        districts_by_code: dict[str, District],
        metrics: IngestionMetrics,
    ) -> District | None:
        """
        Safely resolve a station's administrative district without blindly trusting
        the source code or database code.

        Validates source district code against the authoritative Karnataka LGD catalog,
        cross-checks source district name when provided, and rejects/logs conflicting
        code/name combinations to prevent silent misassignment.
        """
        auth_name_from_code: str | None = None
        if dist_lgd:
            auth_name_from_code = AUTH_LGD_TO_DISTRICT_NAME.get(dist_lgd)
            if not auth_name_from_code:
                metrics.errors.append(
                    f"Station '{station_name}': source district LGD code '{dist_lgd}' "
                    "not recognized in authoritative Karnataka LGD catalog."
                )

        canonical_name_from_name: str | None = None
        if dist_name_raw:
            norm_name = _normalize_name(dist_name_raw)
            canonical_name_from_name = DISTRICT_NAME_ALIASES.get(norm_name)
            if not canonical_name_from_name:
                for db_name in districts_by_name:
                    if _normalize_name(db_name) == norm_name:
                        canonical_name_from_name = db_name
                        break

        # Cross-validation
        if dist_lgd and dist_name_raw:
            if auth_name_from_code and canonical_name_from_name:
                if auth_name_from_code != canonical_name_from_name:
                    # Conflicting code and name: REJECT to prevent silent misassignment
                    metrics.errors.append(
                        f"Station '{station_name}': CONFLICT between source district code '{dist_lgd}' "
                        f"({auth_name_from_code}) and source district name '{dist_name_raw}' "
                        f"({canonical_name_from_name}). District assignment rejected."
                    )
                    return None
                # Both agree
                return districts_by_name.get(canonical_name_from_name)

            if canonical_name_from_name:
                return districts_by_name.get(canonical_name_from_name)

            if auth_name_from_code:
                return districts_by_name.get(auth_name_from_code)

            return None

        if dist_name_raw:
            if canonical_name_from_name:
                return districts_by_name.get(canonical_name_from_name)
            metrics.errors.append(
                f"Station '{station_name}': unresolvable district name '{dist_name_raw}'."
            )
            return None

        if dist_lgd:
            if auth_name_from_code:
                return districts_by_name.get(auth_name_from_code)
            return districts_by_code.get(dist_lgd)

        return None

    def ingest(
        self,
        csv_url: str = DEFAULT_CWC_RIVER_URL,
        csv_content: str | None = None,
        client: httpx.Client | None = None,
        karnataka_only: bool = True,
        max_records: int | None = None,
    ) -> IngestionResult:
        """
        Download and ingest CWC manual hourly river stage data.

        Args:
            csv_url: Target URL for CWC hourly stage CSV.
            csv_content: Optional in-memory CSV string (bypasses network fetch).
            client: Optional httpx.Client for dependency injection in tests.
            karnataka_only: Filter records by State LGD Code 29 (Karnataka).
            max_records: Maximum rows to process (useful for smoke tests).
        """
        started_at = datetime.now(timezone.utc)
        metrics = IngestionMetrics()

        data_source = get_or_create_data_source(
            session=self.session,
            name=self.source_name,
            organization=self.organization,
            source_url=self.source_url,
            access_method=self.access_method,
            data_type=self.data_type,
            update_frequency=self.update_frequency,
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
            raw_file = self.raw_dir / f"cwc_river_stage_{ts_slug}.csv"
            with open(raw_file, "w", encoding="utf-8") as f:
                f.write(raw_text)

            # 3. Cache administrative districts and hydrological entities
            dist_stmt = select(District)
            all_districts = list(self.session.execute(dist_stmt).scalars().all())
            districts_by_name = {d.name: d for d in all_districts}
            districts_by_code = {d.code: d for d in all_districts if d.code}

            basin_cache: dict[str, RiverBasin] = {}
            for b in self.session.execute(select(RiverBasin)).scalars():
                basin_cache[b.name.upper()] = b

            river_cache: dict[str, River] = {}
            for r in self.session.execute(select(River)).scalars():
                river_cache[r.name.upper()] = r

            station_cache: dict[str, RiverStation] = {}
            for s in self.session.execute(select(RiverStation)).scalars():
                station_cache[s.station_code.upper()] = s

            # 4. Parse CSV
            reader = csv.DictReader(io.StringIO(raw_text))
            rows_processed = 0

            for raw_row in reader:
                metrics.records_received += 1
                row = {k.strip(): v.strip() for k, v in raw_row.items() if k}

                # Geography filter
                state_lgd = row.get("State LGD Code", "")
                state_name = row.get("State", "")
                if karnataka_only and state_lgd != "29" and state_name.lower() != "karnataka":
                    continue

                station_name = row.get("Station")
                if not station_name:
                    metrics.records_rejected += 1
                    continue

                basin_name = row.get("Basin") or "Unspecified Basin"
                river_name = row.get("River") or "Unspecified River"
                dist_lgd = row.get("District LGD Code")
                dist_name = row.get("District")
                district = self._resolve_district(
                    dist_lgd=dist_lgd,
                    dist_name_raw=dist_name,
                    station_name=station_name,
                    districts_by_name=districts_by_name,
                    districts_by_code=districts_by_code,
                    metrics=metrics,
                )

                # Coordinates
                coords = validate_coordinates(
                    row.get("Latitude"), row.get("Longitude"), karnataka_only=False
                )
                lat = coords[0] if coords else None
                lon = coords[1] if coords else None
                geom = make_point_wkt(lat, lon) if (lat is not None and lon is not None) else None

                # RiverBasin entity
                b_key = basin_name.upper()
                if b_key not in basin_cache:
                    basin = RiverBasin(
                        id=uuid.uuid4(),
                        name=basin_name,
                        code=b_key[:20],
                    )
                    self.session.add(basin)
                    self.session.flush()
                    basin_cache[b_key] = basin
                basin = basin_cache[b_key]

                # River entity
                r_key = river_name.upper()
                if r_key not in river_cache:
                    river = River(
                        id=uuid.uuid4(),
                        name=river_name,
                        basin_id=basin.id,
                    )
                    self.session.add(river)
                    self.session.flush()
                    river_cache[r_key] = river
                river = river_cache[r_key]

                # RiverStation entity
                stn_key = station_name.strip().upper()
                if stn_key not in station_cache:
                    stn = RiverStation(
                        id=uuid.uuid4(),
                        name=station_name.strip(),
                        station_code=stn_key,
                        river_id=river.id,
                        district_id=district.id if district else None,
                        latitude=lat,
                        longitude=lon,
                        geometry=geom,
                        source_id=data_source.id,
                        is_active=True,
                    )
                    self.session.add(stn)
                    self.session.flush()
                    station_cache[stn_key] = stn
                stn = station_cache[stn_key]

                # Timestamp parsing
                raw_time = row.get("Data Acquisition Time")
                obs_dt = parse_utc_timestamp(raw_time, default_tz=IST_TZ)
                if obs_dt is None:
                    metrics.records_rejected += 1
                    metrics.errors.append(f"Invalid timestamp '{raw_time}' for station {station_name}")
                    continue

                # Water Level (meters)
                raw_level = row.get("River Water Level Manual Hourly (meter)")
                water_level_m = validate_float(raw_level, min_val=0.0, max_val=3000.0)

                # Zero gauge RL if available
                raw_zero = row.get("RL_of_zeroGauge")
                validate_float(raw_zero, min_val=-100.0, max_val=3000.0)

                # Deduplication check
                source_record_id = f"cwc_{stn_key}_{obs_dt.strftime('%Y%m%d%H%M')}"
                obs_stmt = select(RiverObservation).where(
                    RiverObservation.source_id == data_source.id,
                    RiverObservation.source_record_id == source_record_id,
                )
                existing = self.session.execute(obs_stmt).scalar_one_or_none()

                quality = QualityStatus.VALID if water_level_m is not None else QualityStatus.MISSING

                if existing is None:
                    obs = RiverObservation(
                        id=uuid.uuid4(),
                        station_id=stn.id,
                        observed_at=obs_dt,
                        water_level=water_level_m,
                        water_level_unit="m",
                        discharge=None,  # Not in manual hourly stage sheet
                        discharge_unit="m3s",
                        trend=None,
                        warning_level=stn.warning_level,
                        danger_level=stn.danger_level,
                        highest_flood_level=stn.highest_flood_level,
                        source_id=data_source.id,
                        source_record_id=source_record_id,
                        retrieved_at=retrieved_at,
                        quality_status=quality,
                        data_category=DataCategory.OBSERVATION,
                    )
                    self.session.add(obs)
                    metrics.records_inserted += 1
                else:
                    metrics.records_updated += 0  # Idempotent skip

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
