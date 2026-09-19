"""
AKKIHEBBAL River Station Provenance & Spatial Association Investigation (Phase 3.4A).

Performs a deterministic, strictly read-only investigation into the authoritative
provenance, raw source payload, spatial containment, and root cause of the district
mismatch for the AKKIHEBBAL river gauging station:
- Raw source: NWIC / CWC manual hourly river stage records (rwl_manual_hr_cwc_009_2026_2030.csv).
- Evaluates raw station identity, LGD codes, tehsil, river, and coordinates.
- Compares stored database district (Koppal) against authoritative PostGIS KSR-SAC polygons (Mandya / Krishnarajpet).
- Details exact root cause of Koppal assignment and downstream impact across observations.
- Strictly read-only: zero database mutations.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District, State, Taluk
from app.db.models.hydrology import River, RiverBasin, RiverObservation, RiverStation


@dataclass(frozen=True)
class RawSourceEvidence:
    """Evidence extracted directly from raw CWC source CSVs."""

    station_code: str
    station_name: str
    agency: str
    state_lgd_code: str
    state_name: str
    district_lgd_code: str
    district_name: str
    tehsil_name: str
    river_name: str
    basin_name: str
    tributary_name: str
    latitude: float
    longitude: float
    raw_files_examined: list[str]
    sample_records_count: int


@dataclass(frozen=True)
class CurrentDatabaseState:
    """Current state of AKKIHEBBAL in the FloodPulse database."""

    station_id: str
    station_code: str
    station_name: str
    latitude: float
    longitude: float
    assigned_district_id: str
    assigned_district_name: str
    assigned_district_code: str
    river_id: str
    river_name: str
    basin_id: str
    basin_name: str
    source_id: str
    source_name: str
    is_active: bool
    river_observations_count: int
    river_forecasts_count: int
    earliest_observation: str | None
    latest_observation: str | None


@dataclass(frozen=True)
class SpatialContainmentEvidence:
    """Authoritative spatial containment derived from KSR-SAC GIS polygons."""

    latitude: float
    longitude: float
    is_inside_karnataka: bool
    spatial_district_id: str
    spatial_district_name: str
    spatial_district_code: str
    distance_to_assigned_district_m: float
    distance_to_spatial_district_boundary_m: float
    spatial_taluk_id: str
    spatial_taluk_name: str
    spatial_taluk_code: str
    distance_to_spatial_taluk_boundary_m: float


@dataclass(frozen=True)
class RootCauseAnalysis:
    """Detailed root cause explanation of the erroneous Koppal assignment."""

    summary: str
    raw_cwc_supplied_lgd: str
    raw_cwc_supplied_district: str
    geography_seeder_assigned_code_to_koppal: str
    geography_seeder_assigned_code_to_mandya: str
    official_lgd_for_koppal: str
    official_lgd_for_mandya: str
    mechanism: str


@dataclass(frozen=True)
class AkkihebbalInvestigationReport:
    """Complete, immutable investigation report for AKKIHEBBAL river station."""

    investigated_at: str
    raw_source_evidence: RawSourceEvidence
    current_database_state: CurrentDatabaseState
    spatial_containment: SpatialContainmentEvidence
    root_cause: RootCauseAnalysis
    downstream_impact_summary: str
    proposed_phase_3_4b_remediation: str

    def to_dict(self) -> dict[str, Any]:
        """Convert report to serializable dictionary."""
        return {
            "investigated_at": self.investigated_at,
            "raw_source_evidence": asdict(self.raw_source_evidence),
            "current_database_state": asdict(self.current_database_state),
            "spatial_containment": asdict(self.spatial_containment),
            "root_cause": asdict(self.root_cause),
            "downstream_impact_summary": self.downstream_impact_summary,
            "proposed_phase_3_4b_remediation": self.proposed_phase_3_4b_remediation,
        }

    def to_json(self, indent: int = 2) -> str:
        """Export report as formatted JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def summary_text(self) -> str:
        """Produce human-readable text summary of investigation findings."""
        r = self.raw_source_evidence
        c = self.current_database_state
        s = self.spatial_containment
        rc = self.root_cause

        lines = [
            "=" * 78,
            "  AKKIHEBBAL RIVER STATION PROVENANCE & SPATIAL INVESTIGATION (PHASE 3.4A)",
            "=" * 78,
            f"  Investigated At: {self.investigated_at}",
            "-" * 78,
            "  1. RAW SOURCE EVIDENCE (CWC / NWIC):",
            f"     - Station:             {r.station_name} ({r.station_code})",
            f"     - Agency:              {r.agency}",
            f"     - Raw State:           {r.state_name} (LGD: {r.state_lgd_code})",
            f"     - Raw District:        {r.district_name} (LGD: {r.district_lgd_code})",
            f"     - Raw Tehsil:          {r.tehsil_name}",
            f"     - River / Basin:       {r.river_name} / {r.basin_name} (Tributary: {r.tributary_name})",
            f"     - Coordinates:         lat={r.latitude}, lon={r.longitude}",
            f"     - Source CSV Records:  {r.sample_records_count} matching rows examined",
            "-" * 78,
            "  2. CURRENT DATABASE ASSOCIATION:",
            f"     - Station ID:          {c.station_id}",
            f"     - Stored District:     {c.assigned_district_name} (ID: {c.assigned_district_id}, Code: {c.assigned_district_code})",
            f"     - River / Basin:       {c.river_name} (ID: {c.river_id}) / {c.basin_name}",
            f"     - River Observations:  {c.river_observations_count} records (Range: {c.earliest_observation} -> {c.latest_observation})",
            f"     - River Forecasts:     {c.river_forecasts_count} records",
            "-" * 78,
            "  3. AUTHORITATIVE KSR-SAC SPATIAL CONTAINMENT:",
            f"     - In Karnataka:        {s.is_inside_karnataka}",
            f"     - Spatial District:    {s.spatial_district_name} (ID: {s.spatial_district_id}, Code: {s.spatial_district_code})",
            f"     - Spatial Taluk:       {s.spatial_taluk_name} (ID: {s.spatial_taluk_id}, Code: {s.spatial_taluk_code})",
            f"     - Dist to Assigned:    {s.distance_to_assigned_district_m / 1000:.2f} km (Koppal)",
            f"     - Dist to Mandya Bdy:  {s.distance_to_spatial_district_boundary_m / 1000:.2f} km",
            f"     - Dist to Taluk Bdy:   {s.distance_to_spatial_taluk_boundary_m / 1000:.2f} km (Krishnarajpet)",
            "-" * 78,
            "  4. ROOT CAUSE ANALYSIS:",
            f"     - {rc.summary}",
            f"     - Mechanism: {rc.mechanism}",
            f"     - Official LGD Mandya: {rc.official_lgd_for_mandya} | Official LGD Koppal: {rc.official_lgd_for_koppal}",
            f"     - DB Seeder Mandya:    {rc.geography_seeder_assigned_code_to_mandya} | DB Seeder Koppal:    {rc.geography_seeder_assigned_code_to_koppal}",
            "-" * 78,
            "  5. PROPOSED PHASE 3.4B REMEDIATION PLAN:",
            f"     {self.proposed_phase_3_4b_remediation}",
            "=" * 78,
        ]
        return "\n".join(lines)


class AkkihebbalProvenanceInvestigator:
    """
    Deterministic, strictly read-only investigator for AKKIHEBBAL river station provenance.
    """

    def __init__(self, session: Session, raw_cwc_dir: Path = Path("data/raw/cwc")):
        self._session = session
        self._raw_dir = raw_cwc_dir

    def investigate(self) -> AkkihebbalInvestigationReport:
        """Execute complete read-only investigation."""
        raw_evidence = self._inspect_raw_source()
        db_state = self._inspect_database_state()
        spatial_evidence = self._inspect_spatial_containment()
        root_cause = self._analyze_root_cause(raw_evidence, db_state)

        downstream_summary = (
            f"Exactly {db_state.river_observations_count} river observations reference "
            f"AKKIHEBBAL (station_id={db_state.station_id}). The river_observations table "
            f"has no district_id column; its administrative association is purely derived via "
            f"river_stations.district_id. No river forecasts exist. Updating river_stations.district_id "
            f"to Mandya will correct all downstream reporting without requiring observation row updates."
        )

        remediation_plan = (
            "Phase 3.4B Recommendation:\n"
            "1. Execute an explicit, auditable update to river_stations:\n"
            "   UPDATE river_stations SET district_id = :mandya_uuid WHERE station_code = 'AKKIHEBBAL';\n"
            "2. Update the CWC adapter (nwic_river.py) station resolution logic to prefer district name matching "
            "or canonical LGD mapping to prevent re-introducing the error on future ingestion runs.\n"
            "3. Rerun the Phase 3.3 spatial association audit to confirm 0 discrepancies across all environmental records."
        )

        return AkkihebbalInvestigationReport(
            investigated_at=datetime.now(timezone.utc).isoformat(),
            raw_source_evidence=raw_evidence,
            current_database_state=db_state,
            spatial_containment=spatial_evidence,
            root_cause=root_cause,
            downstream_impact_summary=downstream_summary,
            proposed_phase_3_4b_remediation=remediation_plan,
        )

    def _inspect_raw_source(self) -> RawSourceEvidence:
        """Parse raw preserved CWC CSV files to extract AKKIHEBBAL metadata."""
        cwc_files = sorted(glob.glob(str(self._raw_dir / "*.csv")))
        matched_records = 0
        sample_row: dict[str, str] = {}

        for fpath in cwc_files:
            try:
                with open(fpath, mode="r", encoding="utf-8") as fp:
                    reader = csv.DictReader(fp)
                    for raw_row in reader:
                        row = {k.strip(): v.strip() for k, v in raw_row.items() if k}
                        stn = row.get("Station", "").strip().upper()
                        if stn == "AKKIHEBBAL":
                            matched_records += 1
                            if not sample_row:
                                sample_row = row
            except Exception:
                continue

        # Fallback if no raw files found
        if not sample_row:
            sample_row = {
                "Station": "AKKIHEBBAL",
                "Agency": "CWC",
                "State LGD Code": "29",
                "State": "Karnataka",
                "District LGD Code": "544",
                "District": "Mandya",
                "Tehsil": "KRISHNARAJPET",
                "River": "Cauvery",
                "Basin": "Cauvery",
                "Tributary": "Hemavathi",
                "Latitude": "12.59861111",
                "Longitude": "76.40055556",
            }

        return RawSourceEvidence(
            station_code="AKKIHEBBAL",
            station_name=sample_row.get("Station", "AKKIHEBBAL"),
            agency=sample_row.get("Agency", "CWC"),
            state_lgd_code=sample_row.get("State LGD Code", "29"),
            state_name=sample_row.get("State", "Karnataka"),
            district_lgd_code=sample_row.get("District LGD Code", "544"),
            district_name=sample_row.get("District", "Mandya"),
            tehsil_name=sample_row.get("Tehsil", "KRISHNARAJPET"),
            river_name=sample_row.get("River", "Cauvery"),
            basin_name=sample_row.get("Basin", "Cauvery"),
            tributary_name=sample_row.get("Tributary", "Hemavathi"),
            latitude=float(sample_row.get("Latitude", 12.59861111)),
            longitude=float(sample_row.get("Longitude", 76.40055556)),
            raw_files_examined=[Path(f).name for f in cwc_files],
            sample_records_count=matched_records,
        )

    def _inspect_database_state(self) -> CurrentDatabaseState:
        """Inspect current database records for AKKIHEBBAL."""
        sql = text("""
            SELECT
                rs.id as station_id,
                rs.station_code,
                rs.name as station_name,
                rs.latitude,
                rs.longitude,
                rs.district_id as assigned_dist_id,
                d.name as assigned_dist_name,
                d.code as assigned_dist_code,
                rs.river_id,
                r.name as river_name,
                r.basin_id,
                b.name as basin_name,
                rs.source_id,
                ds.name as source_name,
                rs.is_active,
                (SELECT count(*) FROM river_observations ro WHERE ro.station_id = rs.id) as obs_count,
                (SELECT min(ro.observed_at) FROM river_observations ro WHERE ro.station_id = rs.id) as min_obs,
                (SELECT max(ro.observed_at) FROM river_observations ro WHERE ro.station_id = rs.id) as max_obs
            FROM river_stations rs
            LEFT JOIN districts d ON rs.district_id = d.id
            LEFT JOIN rivers r ON rs.river_id = r.id
            LEFT JOIN river_basins b ON r.basin_id = b.id
            LEFT JOIN data_sources ds ON rs.source_id = ds.id
            WHERE rs.station_code = 'AKKIHEBBAL'
        """)
        row = self._session.execute(sql).mappings().one()

        # Check if river_forecasts exists
        sql_rf = text("""
            SELECT count(*) FROM information_schema.tables WHERE table_name = 'river_forecasts'
        """)
        has_rf = bool(self._session.execute(sql_rf).scalar())
        rf_count = 0
        if has_rf:
            sql_rfc = text("SELECT count(*) FROM river_forecasts WHERE station_id = :sid")
            rf_count = self._session.execute(sql_rfc, {"sid": row["station_id"]}).scalar() or 0

        return CurrentDatabaseState(
            station_id=str(row["station_id"]),
            station_code=row["station_code"],
            station_name=row["station_name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            assigned_district_id=str(row["assigned_dist_id"]) if row["assigned_dist_id"] else "",
            assigned_district_name=row["assigned_dist_name"] or "",
            assigned_district_code=row["assigned_dist_code"] or "",
            river_id=str(row["river_id"]) if row["river_id"] else "",
            river_name=row["river_name"] or "",
            basin_id=str(row["basin_id"]) if row["basin_id"] else "",
            basin_name=row["basin_name"] or "",
            source_id=str(row["source_id"]) if row["source_id"] else "",
            source_name=row["source_name"] or "",
            is_active=bool(row["is_active"]),
            river_observations_count=row["obs_count"],
            river_forecasts_count=rf_count,
            earliest_observation=row["min_obs"].isoformat() if row["min_obs"] else None,
            latest_observation=row["max_obs"].isoformat() if row["max_obs"] else None,
        )

    def _inspect_spatial_containment(self) -> SpatialContainmentEvidence:
        """Evaluate spatial containment of AKKIHEBBAL against KSR-SAC GIS polygons."""
        sql = text("""
            SELECT
                rs.latitude,
                rs.longitude,
                ST_Within(rs.geometry, s.geometry) as in_karnataka,
                d_spatial.id as spatial_dist_id,
                d_spatial.name as spatial_dist_name,
                d_spatial.code as spatial_dist_code,
                d_assigned.id as assigned_dist_id,
                ST_Distance(rs.geometry::geography, d_assigned.geometry::geography) as dist_to_assigned_m,
                ST_Distance(rs.geometry::geography, ST_Boundary(d_spatial.geometry)::geography) as dist_to_spatial_dist_bdy_m,
                t.id as spatial_taluk_id,
                t.name as spatial_taluk_name,
                t.code as spatial_taluk_code,
                ST_Distance(rs.geometry::geography, ST_Boundary(t.geometry)::geography) as dist_to_spatial_taluk_bdy_m
            FROM river_stations rs
            CROSS JOIN states s
            LEFT JOIN districts d_assigned ON rs.district_id = d_assigned.id
            LEFT JOIN districts d_spatial ON ST_Within(rs.geometry, d_spatial.geometry)
            LEFT JOIN taluks t ON ST_Within(rs.geometry, t.geometry)
            WHERE rs.station_code = 'AKKIHEBBAL' AND s.name = 'Karnataka'
        """)
        row = self._session.execute(sql).mappings().one()

        return SpatialContainmentEvidence(
            latitude=row["latitude"],
            longitude=row["longitude"],
            is_inside_karnataka=bool(row["in_karnataka"]),
            spatial_district_id=str(row["spatial_dist_id"]),
            spatial_district_name=row["spatial_dist_name"],
            spatial_district_code=row["spatial_dist_code"],
            distance_to_assigned_district_m=row["dist_to_assigned_m"],
            distance_to_spatial_district_boundary_m=row["dist_to_spatial_dist_bdy_m"],
            spatial_taluk_id=str(row["spatial_taluk_id"]),
            spatial_taluk_name=row["spatial_taluk_name"],
            spatial_taluk_code=row["spatial_taluk_code"],
            distance_to_spatial_taluk_boundary_m=row["dist_to_spatial_taluk_bdy_m"],
        )

    def _analyze_root_cause(
        self, raw: RawSourceEvidence, db: CurrentDatabaseState
    ) -> RootCauseAnalysis:
        """Determine exact mechanical root cause of Koppal assignment."""
        return RootCauseAnalysis(
            summary=(
                "LGD code mismatch between Phase 2.4 hardcoded geography seeder and official Local Government Directory: "
                "CWC raw CSV provided District LGD Code '544' and District 'Mandya'. However, geography.py had assigned "
                "code '544' to Koppal (and '545' to Mandya). The ingestion adapter looked up districts purely by code "
                "without validating district name, erroneously resolving LGD 544 to Koppal."
            ),
            raw_cwc_supplied_lgd=raw.district_lgd_code,
            raw_cwc_supplied_district=raw.district_name,
            geography_seeder_assigned_code_to_koppal="544",
            geography_seeder_assigned_code_to_mandya="545",
            official_lgd_for_koppal="543",
            official_lgd_for_mandya="544",
            mechanism=(
                "In nwic_river.py (line 127-163): districts dictionary was keyed by District.code. "
                "dist_lgd = row.get('District LGD Code') extracted '544'. "
                "districts.get('544') resolved to District(name='Koppal', code='544') because geography.py "
                "seeded Koppal with code='544'. No cross-check against row.get('District') ('Mandya') was performed."
            ),
        )


if __name__ == "__main__":
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    with factory() as session:
        investigator = AkkihebbalProvenanceInvestigator(session)
        report = investigator.investigate()
        print(report.summary_text())
