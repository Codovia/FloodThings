"""
FloodPulse Data Ingestion Command-Line Interface (CLI).

Usage:
    python -m app.ingestion.cli geography
    python -m app.ingestion.cli open-meteo [--mode operational|historical] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
    python -m app.ingestion.cli nwic-river [--max-records N]
    python -m app.ingestion.cli nwic-reservoir [--max-records N]
    python -m app.ingestion.cli ifi [--max-records N]
    python -m app.ingestion.cli ingest-all [--max-records N]
    python -m app.ingestion.cli status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import _get_session_factory
from app.db.models.flood import FloodEvent, FloodObservation
from app.db.models.geography import District, State
from app.db.models.hydrology import (
    Reservoir,
    ReservoirObservation,
    River,
    RiverBasin,
    RiverObservation,
    RiverStation,
)
from app.db.models.system import DataIngestionRun, DataSource
from app.db.models.weather import (
    RainfallObservation,
    WeatherForecast,
    WeatherObservation,
)
from app.gis.controlled_correction import ControlledDistrictCorrector
from app.gis.district_code_audit import DistrictCodeAuditor
from app.gis.environmental_audit import EnvironmentalDataAuditor
from app.gis.spatial_audit import SpatialAssociationAuditor
from app.ingestion.sources.geography import KarnatakaGeographyAdapter
from app.ingestion.sources.ifi_flood import IfiFloodAdapter
from app.ingestion.sources.ksrsac_gis import KsrsacGisAdapter
from app.ingestion.sources.nwic_reservoir import NwicReservoirAdapter
from app.ingestion.sources.nwic_river import NwicRiverLevelAdapter
from app.ingestion.sources.open_meteo import OpenMeteoAdapter
from app.ingestion.sources.hydrosheds_gis import HydrologicalGisAdapter


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(res: Any) -> None:
    print(f"  Source:   {res.source_name}")
    print(f"  Status:   {res.status}")
    print(f"  Run ID:   {res.run_id}")
    print(f"  Received: {res.metrics.records_received}")
    print(f"  Valid:    {res.metrics.records_valid}")
    print(f"  Inserted: {res.metrics.records_inserted}")
    print(f"  Updated:  {res.metrics.records_updated}")
    print(f"  Rejected: {res.metrics.records_rejected}")
    if res.metrics.errors:
        print(f"  Errors ({len(res.metrics.errors)}):")
        for err in res.metrics.errors[:5]:
            print(f"    - {err}")
    print("-" * 70)


def cmd_ksrsac_gis(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting KSR-SAC Administrative Boundaries (State, District, Taluk)")
    adapter = KsrsacGisAdapter(session)
    res = adapter.ingest()
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_hydro_gis(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting Hydrological GIS (CWC, HydroBASINS, HydroRIVERS)")
    adapter = HydrologicalGisAdapter(session)
    res = adapter.ingest()
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_geography(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting Karnataka Administrative Geography (LGD)")
    adapter = KarnatakaGeographyAdapter(session)
    res = adapter.ingest()
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_open_meteo(session: Session, args: argparse.Namespace) -> int:
    mode = args.mode or "operational"
    print_header(f"Ingesting Open-Meteo Weather Data (Mode: {mode.upper()})")
    adapter = OpenMeteoAdapter(session)
    res = adapter.ingest(
        mode=mode,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_nwic_river(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting NWIC / CWC Manual River Gauge Telemetry")
    adapter = NwicRiverLevelAdapter(session)
    res = adapter.ingest(max_records=args.max_records)
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_nwic_reservoir(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting NWIC Karnataka Major Reservoir Telemetry")
    adapter = NwicReservoirAdapter(session)
    res = adapter.ingest(max_records=args.max_records)
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_ifi(session: Session, args: argparse.Namespace) -> int:
    print_header("Ingesting India Flood Inventory (IFI v3.0) Historical Events")
    adapter = IfiFloodAdapter(session)
    res = adapter.ingest(max_records=args.max_records)
    print_result(res)
    return 0 if res.status in ("SUCCESS", "PARTIAL") else 1


def cmd_ingest_all(session: Session, args: argparse.Namespace) -> int:
    print_header("Executing FloodPulse Tier-1 Comprehensive Ingestion")
    max_rec = args.max_records or 200

    # 1. Geography first (foundation for foreign keys)
    print("\n[Step 1/5] Karnataka Administrative Geography")
    geo_res = KarnatakaGeographyAdapter(session).ingest()
    print_result(geo_res)

    # 2. Open-Meteo operational
    print("\n[Step 2/5] Open-Meteo Operational & Forecast")
    meteo_res = OpenMeteoAdapter(session).ingest(mode="operational")
    print_result(meteo_res)

    # 3. NWIC River
    print("\n[Step 3/5] NWIC / CWC River Telemetry")
    river_res = NwicRiverLevelAdapter(session).ingest(max_records=max_rec)
    print_result(river_res)

    # 4. NWIC Reservoir
    print("\n[Step 4/5] NWIC Karnataka Reservoir Telemetry")
    res_res = NwicReservoirAdapter(session).ingest(max_records=max_rec)
    print_result(res_res)

    # 5. IFI Historical Flood Events
    print("\n[Step 5/5] India Flood Inventory (IFI v3.0)")
    ifi_res = IfiFloodAdapter(session).ingest(max_records=max_rec)
    print_result(ifi_res)

    print_status(session)
    return 0


def cmd_status(session: Session, args: argparse.Namespace) -> int:
    print_status(session)
    return 0


def cmd_spatial_audit(session: Session, args: argparse.Namespace) -> int:
    auditor = SpatialAssociationAuditor(session)
    report = auditor.audit()

    if args.format == "json":
        print(report.to_json())
    else:
        print(report.summary_text())

    if args.export_path:
        p = Path(args.export_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report.to_json(), encoding="utf-8")
    return 0


def cmd_district_code_audit(session: Session, args: argparse.Namespace) -> int:
    auditor = DistrictCodeAuditor(session)
    report = auditor.audit()

    if args.format == "json":
        print(report.to_json())
    else:
        print(report.summary_text())

    if args.export_path:
        p = Path(args.export_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report.to_json(), encoding="utf-8")
        print(f"\n  Exported district code audit report to: {p.resolve()}")

    return 0


def cmd_district_code_correct(session: Session, args: argparse.Namespace) -> int:
    print_header("Executing Controlled District Code & AKKIHEBBAL Station Correction (Phase 3.4B)")
    corrector = ControlledDistrictCorrector(session)
    res = corrector.execute_correction(dry_run=args.dry_run)

    print(f"  Executed At:                  {res.executed_at}")
    print(f"  Districts Updated:            {res.districts_updated_count}")
    print(f"  River Stations Updated:       {res.river_stations_updated_count}")
    print(f"  District UUIDs Preserved:     {res.district_uuids_preserved}")
    print(f"  AKKIHEBBAL New District Name: {res.akkihebbal_new_district_name}")
    print(f"  AKKIHEBBAL New District Code: {res.akkihebbal_new_district_code}")
    print(f"  River Observations Intact:    {res.river_observations_count_intact}")
    print(f"  Transaction Committed:        {res.transaction_committed}")
    print("-" * 70)
    return 0


def cmd_environmental_audit(session: Session, args: argparse.Namespace) -> int:
    auditor = EnvironmentalDataAuditor(session)
    report = auditor.audit()

    if args.format == "json":
        print(report.to_json())
    else:
        print(report.summary_text())

    if args.export_path:
        p = Path(args.export_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report.to_json(), encoding="utf-8")
        print(f"\n  Exported environmental data audit report to: {p.resolve()}")

    return 0


def print_status(session: Session) -> None:
    print_header("FloodPulse Database Observation & Provenance Status")

    tables = [
        ("States", State),
        ("Districts", District),
        ("River Basins", RiverBasin),
        ("Rivers", River),
        ("River Stations", RiverStation),
        ("River Observations", RiverObservation),
        ("Reservoirs", Reservoir),
        ("Reservoir Observations", ReservoirObservation),
        ("Weather Observations", WeatherObservation),
        ("Rainfall Observations", RainfallObservation),
        ("Weather Forecasts", WeatherForecast),
        ("Flood Events", FloodEvent),
        ("Flood Observations", FloodObservation),
        ("Data Sources", DataSource),
        ("Data Ingestion Runs", DataIngestionRun),
    ]

    print(f"  {'Entity / Table':<28} {'Row Count':<10}")
    print("  " + "-" * 40)
    for name, model in tables:
        count = session.execute(select(func.count()).select_from(model)).scalar() or 0
        print(f"  {name:<28} {count:<10}")

    print("\n  --- Observation Timestamps & Quality Breakdown ---")
    obs_configs = [
        ("River Observations", RiverObservation, RiverObservation.observed_at, RiverObservation.quality_status),
        ("Reservoir Observations", ReservoirObservation, ReservoirObservation.observed_at, ReservoirObservation.quality_status),
        ("Weather Observations", WeatherObservation, WeatherObservation.observed_at, WeatherObservation.quality_status),
        ("Rainfall Observations", RainfallObservation, RainfallObservation.observed_at, RainfallObservation.quality_status),
        ("Flood Observations", FloodObservation, FloodObservation.observation_time, FloodObservation.quality_status),
    ]

    for label, model, ts_col, qual_col in obs_configs:
        min_ts = session.execute(select(func.min(ts_col))).scalar()
        max_ts = session.execute(select(func.max(ts_col))).scalar()
        # Quality distribution
        q_rows = session.execute(
            select(qual_col, func.count()).group_by(qual_col)
        ).all()
        q_dist = ", ".join(f"{q or 'NONE'}:{cnt}" for q, cnt in q_rows)
        print(f"  {label}:")
        print(f"    Range: {min_ts} -> {max_ts}")
        print(f"    Quality: {q_dist or 'N/A'}")

    print("=" * 70 + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion.cli",
        description="FloodPulse Data Ingestion CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # geography
    subparsers.add_parser("geography", help="Seed Karnataka administrative geography (LGD)")

    # ksrsac-gis
    subparsers.add_parser("ksrsac-gis", help="Ingest KSR-SAC administrative geometries into PostGIS")

    # open-meteo
    p_meteo = subparsers.add_parser("open-meteo", help="Ingest Open-Meteo weather data")
    p_meteo.add_argument("--mode", choices=["operational", "historical"], default="operational")
    p_meteo.add_argument("--start-date", help="Start date (YYYY-MM-DD) for historical mode")
    p_meteo.add_argument("--end-date", help="End date (YYYY-MM-DD) for historical mode")

    # nwic-river
    p_river = subparsers.add_parser("nwic-river", help="Ingest NWIC / CWC river stage observations")
    p_river.add_argument("--max-records", type=int, default=None, help="Max records to process")

    # nwic-reservoir
    p_res = subparsers.add_parser("nwic-reservoir", help="Ingest NWIC reservoir observations")
    p_res.add_argument("--max-records", type=int, default=None, help="Max records to process")

    # ifi
    p_ifi = subparsers.add_parser("ifi", help="Ingest India Flood Inventory events")
    p_ifi.add_argument("--max-records", type=int, default=None, help="Max records to process")

    # ingest-all
    p_all = subparsers.add_parser("ingest-all", help="Ingest all Tier-1 real data sources")
    p_all.add_argument("--max-records", type=int, default=200, help="Max records per dataset")

    # status
    subparsers.add_parser("status", help="Show database observation counts and quality metrics")

    # spatial-audit
    p_audit = subparsers.add_parser(
        "spatial-audit",
        help="Run read-only spatial association audit (Administrative GIS <-> Environmental Records)",
    )
    p_audit.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_audit.add_argument("--export-path", help="Optional path to export audit report as JSON")

    # district-code-audit
    p_d_audit = subparsers.add_parser(
        "district-code-audit",
        help="Run read-only district code integrity audit against KSR-SAC / LGD",
    )
    p_d_audit.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_d_audit.add_argument("--export-path", help="Optional path to export audit report as JSON")

    # district-code-correct
    p_d_correct = subparsers.add_parser(
        "district-code-correct",
        help="Execute controlled correction of district codes and AKKIHEBBAL station",
    )
    p_d_correct.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute in transaction and rollback without committing",
    )

    # environmental-audit
    p_env_audit = subparsers.add_parser(
        "environmental-audit",
        help="Run read-only environmental data spatial association & source coverage audit (Phase 3.5)",
    )
    p_env_audit.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_env_audit.add_argument("--export-path", help="Optional path to export audit report as JSON")

    # hydro-gis
    subparsers.add_parser(
        "hydro-gis",
        help="Ingest hydrological GIS data (CWC basins, HydroBASINS L7, HydroRIVERS, crosswalks)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    factory = _get_session_factory()
    with factory() as session:
        cmd_map = {
            "geography": cmd_geography,
            "ksrsac-gis": cmd_ksrsac_gis,
            "hydro-gis": cmd_hydro_gis,
            "open-meteo": cmd_open_meteo,
            "nwic-river": cmd_nwic_river,
            "nwic-reservoir": cmd_nwic_reservoir,
            "ifi": cmd_ifi,
            "ingest-all": cmd_ingest_all,
            "status": cmd_status,
            "spatial-audit": cmd_spatial_audit,
            "district-code-audit": cmd_district_code_audit,
            "district-code-correct": cmd_district_code_correct,
            "environmental-audit": cmd_environmental_audit,
        }
        handler = cmd_map.get(args.command)
        if handler is None:
            parser.print_help()
            sys.exit(1)
        code = handler(session, args)
        sys.exit(code)


if __name__ == "__main__":
    main()
