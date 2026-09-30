"""
Hydrological Data Auditor.

Performs a rigorous, empirical audit of all available CWC / NWIC hydrological
observations and gauge metadata across database tables and raw CSV files.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import glob
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RiverStationRecord:
    station_name: str
    station_code: str
    district_name: str
    river_name: str
    basin_name: str
    latitude: float
    longitude: float
    warning_level_m: float | None
    danger_level_m: float | None
    highest_flood_level_m: float | None
    source_agency: str
    source_type: str  # "DATABASE" or "RAW_CSV"


@dataclass(frozen=True)
class HydrologicalAuditSummary:
    database_station_count: int
    database_observation_count: int
    database_earliest_utc: str | None
    database_latest_utc: str | None
    database_water_level_null_count: int
    database_discharge_count: int
    database_warning_level_count: int
    database_danger_level_count: int
    raw_csv_file_count: int
    raw_csv_total_rows: int
    raw_csv_karnataka_station_count: int
    raw_csv_karnataka_districts: list[str]
    raw_csv_unique_years: list[str]
    historical_1969_1994_observations: int
    recent_2011_2023_observations: int
    operational_2026_observations: int


class HydrologicalDataAuditor:
    """Audits database records and raw file assets for river telemetry."""

    def __init__(self, raw_cwc_dir: Path | str = "data/raw/cwc") -> None:
        self.raw_cwc_dir = Path(raw_cwc_dir)

    def audit_database(self, session: Session) -> dict[str, Any]:
        """Audit PostgreSQL public.river_stations and public.river_observations."""
        # Station audit
        station_q = text("""
            SELECT 
                rs.id, rs.name as station_name, rs.station_code, 
                d.name as district_name, r.name as river_name,
                rs.latitude, rs.longitude,
                rs.warning_level, rs.danger_level, rs.highest_flood_level,
                rs.is_active
            FROM river_stations rs
            LEFT JOIN districts d ON rs.district_id = d.id
            LEFT JOIN rivers r ON rs.river_id = r.id;
        """)
        stations = [dict(row._mapping) for row in session.execute(station_q).fetchall()]

        # Observation audit
        obs_q = text("""
            SELECT 
                count(*) as total_count,
                min(observed_at) as earliest,
                max(observed_at) as latest,
                count(water_level) as water_level_count,
                count(*) - count(water_level) as water_level_nulls,
                min(water_level) as min_wl,
                max(water_level) as max_wl,
                avg(water_level) as avg_wl,
                count(discharge) as discharge_count,
                count(warning_level) as warning_level_count,
                count(danger_level) as danger_level_count,
                count(highest_flood_level) as hfl_count
            FROM river_observations;
        """)
        obs_summary = dict(session.execute(obs_q).fetchone()._mapping)

        # Observation counts by period
        period_q = text("""
            SELECT
                count(CASE WHEN observed_at >= '1969-01-01' AND observed_at <= '1994-12-31 23:59:59' THEN 1 END) as count_1969_1994,
                count(CASE WHEN observed_at >= '2011-01-01' AND observed_at <= '2023-07-24 23:59:59' THEN 1 END) as count_2011_2023,
                count(CASE WHEN observed_at >= '2023-07-25' AND observed_at <= '2025-12-31 23:59:59' THEN 1 END) as count_2023_2025,
                count(CASE WHEN observed_at >= '2026-01-01' THEN 1 END) as count_2026
            FROM river_observations;
        """)
        period_counts = dict(session.execute(period_q).fetchone()._mapping)

        return {
            "stations": stations,
            "observations_summary": obs_summary,
            "period_counts": period_counts,
        }

    def audit_raw_csv_files(self) -> dict[str, Any]:
        """Audit all raw CWC CSV telemetry files stored on disk."""
        pattern = str(self.raw_cwc_dir / "*.csv")
        files = sorted(glob.glob(pattern))

        total_rows = 0
        stations: dict[str, dict[str, Any]] = {}
        districts = set()
        years = set()

        for f in files:
            try:
                with open(f, mode="r", encoding="utf-8") as fp:
                    reader = csv.DictReader(fp)
                    for row in reader:
                        total_rows += 1
                        stn = row.get("Station", "").strip()
                        dist = row.get("District", "").strip()
                        state = row.get("State", "").strip()
                        river = row.get("River", "").strip()
                        basin = row.get("Basin", "").strip()
                        lat = row.get("Latitude", "").strip()
                        lon = row.get("Longitude", "").strip()
                        t = row.get("Data Acquisition Time", "").strip()

                        if dist:
                            districts.add(dist)
                        if t:
                            # e.g., '02-01-2026 08:00' -> '2026'
                            parts = t.split(" ")[0].split("-")
                            if len(parts[-1]) == 4:
                                years.add(parts[-1])
                            elif len(parts[0]) == 4:
                                years.add(parts[0])

                        if stn and stn not in stations:
                            stations[stn] = {
                                "station": stn,
                                "district": dist,
                                "state": state,
                                "river": river,
                                "basin": basin,
                                "latitude": float(lat) if lat else None,
                                "longitude": float(lon) if lon else None,
                                "obs_count": 0,
                                "min_time": t,
                                "max_time": t,
                            }
                        if stn:
                            stations[stn]["obs_count"] += 1
                            if t and (not stations[stn]["min_time"] or t < stations[stn]["min_time"]):
                                stations[stn]["min_time"] = t
                            if t and (not stations[stn]["max_time"] or t > stations[stn]["max_time"]):
                                stations[stn]["max_time"] = t
            except Exception:
                continue

        karnataka_districts_known = {
            "Mandya", "Mysore", "Chamarajanagara", "Kodagu", "Hassan",
            "Chikkamagaluru", "Ramanagar", "Ramanagara", "Mysuru"
        }
        karnataka_stations = {
            k: v for k, v in stations.items()
            if v["district"] in karnataka_districts_known or v["state"].lower() == "karnataka"
        }

        return {
            "csv_file_count": len(files),
            "total_rows": total_rows,
            "unique_stations_count": len(stations),
            "karnataka_stations_count": len(karnataka_stations),
            "karnataka_stations": karnataka_stations,
            "all_districts": sorted(list(districts)),
            "karnataka_districts": sorted(list(districts.intersection(karnataka_districts_known))),
            "unique_years": sorted(list(years)),
        }

    def generate_full_audit(self, session: Session) -> HydrologicalAuditSummary:
        """Combine DB and raw file audits into a verified summary."""
        db_res = self.audit_database(session)
        raw_res = self.audit_raw_csv_files()

        obs_sum = db_res["observations_summary"]
        periods = db_res["period_counts"]

        return HydrologicalAuditSummary(
            database_station_count=len(db_res["stations"]),
            database_observation_count=obs_sum["total_count"],
            database_earliest_utc=obs_sum["earliest"].isoformat() if obs_sum["earliest"] else None,
            database_latest_utc=obs_sum["latest"].isoformat() if obs_sum["latest"] else None,
            database_water_level_null_count=obs_sum["water_level_nulls"],
            database_discharge_count=obs_sum["discharge_count"],
            database_warning_level_count=obs_sum["warning_level_count"],
            database_danger_level_count=obs_sum["danger_level_count"],
            raw_csv_file_count=raw_res["csv_file_count"],
            raw_csv_total_rows=raw_res["total_rows"],
            raw_csv_karnataka_station_count=raw_res["karnataka_stations_count"],
            raw_csv_karnataka_districts=raw_res["karnataka_districts"],
            raw_csv_unique_years=raw_res["unique_years"],
            historical_1969_1994_observations=periods["count_1969_1994"],
            recent_2011_2023_observations=periods["count_2011_2023"],
            operational_2026_observations=periods["count_2026"] + raw_res["total_rows"],
        )
