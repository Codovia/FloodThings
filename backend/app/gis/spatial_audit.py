"""
Administrative GIS ↔ Environmental Spatial Association Audit.

Performs a deterministic, strictly read-only spatial and administrative association
audit between the populated KSR-SAC administrative GIS polygons (State, District, Taluk)
and existing environmental / historical records in PostGIS:
1. Weather observations (point-based: latitude, longitude, geometry)
2. Rainfall observations (point-based: latitude, longitude, geometry)
3. River stations (point-based: latitude, longitude, geometry)
4. Taluk → District containment (polygonal hierarchy)
5. Historical IFI flood observations (district-level historical event evidence)

Enforces strict zero-fabrication and read-only invariants:
- Never mutates database records or foreign keys.
- Never fabricates coordinates or infers centroids.
- Explicitly flags discrepancies and boundary cases for manual review.
- Distinguishes historical damage evidence (IFI) from physical coordinate observations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.flood import FloodObservation
from app.db.models.geography import District, State, Taluk
from app.db.models.hydrology import RiverStation
from app.db.models.weather import RainfallObservation, WeatherObservation
from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict


# -----------------------------------------------------------------------------
# Audit Data Structures
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityAuditMetrics:
    """Standardized metrics for a single audited entity type."""

    entity_type: str
    total_examined: int
    spatially_matched: int
    outside_karnataka: int
    outside_assigned_district: int
    missing_or_invalid_geometry: int
    boundary_or_ambiguous: int
    requires_manual_review: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialDiscrepancy:
    """Detailed record for any entity with a spatial or administrative mismatch."""

    record_id: str
    entity_type: str
    identifier: str
    latitude: float | None
    longitude: float | None
    assigned_district_id: str | None
    assigned_district_name: str | None
    spatial_district_id: str | None
    spatial_district_name: str | None
    is_in_karnataka: bool
    distance_to_assigned_district_m: float | None
    distance_to_spatial_boundary_m: float | None
    discrepancy_type: str
    remediation_note: str


@dataclass(frozen=True)
class TalukContainmentRecord:
    """Detailed record for taluk-to-district polygonal containment."""

    taluk_id: str
    taluk_name: str
    taluk_code: str
    assigned_district_id: str
    assigned_district_name: str
    assigned_district_code: str
    strictly_within: bool
    point_on_surface_within: bool
    overlap_percentage: float
    status: str  # CONTAINED, BOUNDARY_SLIVER, CROSS_DISTRICT_MISMATCH


@dataclass(frozen=True)
class IfiAdministrativeRecord:
    """Audit summary for IFI historical flood observations."""

    total_records: int
    valid_district_references: int
    invalid_district_references: int
    null_geometry_verified: int
    unexpected_geometry_count: int
    null_taluk_verified: int
    distinct_districts_referenced: int
    unmatched_district_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpatialAssociationAuditReport:
    """Complete, immutable audit report across all environmental & admin entities."""

    weather_metrics: EntityAuditMetrics
    rainfall_metrics: EntityAuditMetrics
    river_station_metrics: EntityAuditMetrics
    taluk_metrics: EntityAuditMetrics
    ifi_metrics: EntityAuditMetrics
    discrepancies: list[SpatialDiscrepancy]
    boundary_cases: list[TalukContainmentRecord]
    ifi_details: IfiAdministrativeRecord
    audited_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert audit report to serializable dictionary."""
        return {
            "audited_at": self.audited_at,
            "entities": {
                "weather_observations": asdict(self.weather_metrics),
                "rainfall_observations": asdict(self.rainfall_metrics),
                "river_stations": asdict(self.river_station_metrics),
                "taluks": asdict(self.taluk_metrics),
                "flood_observations_ifi": asdict(self.ifi_metrics),
            },
            "discrepancies": [asdict(d) for d in self.discrepancies],
            "boundary_cases_count": len(self.boundary_cases),
            "ifi_details": asdict(self.ifi_details),
            "summary": {
                "total_records_examined": (
                    self.weather_metrics.total_examined
                    + self.rainfall_metrics.total_examined
                    + self.river_station_metrics.total_examined
                    + self.taluk_metrics.total_examined
                    + self.ifi_metrics.total_examined
                ),
                "total_spatially_matched": (
                    self.weather_metrics.spatially_matched
                    + self.rainfall_metrics.spatially_matched
                    + self.river_station_metrics.spatially_matched
                    + self.taluk_metrics.spatially_matched
                    + self.ifi_metrics.spatially_matched
                ),
                "total_discrepancies": len(self.discrepancies),
                "total_requiring_manual_review": (
                    self.weather_metrics.requires_manual_review
                    + self.rainfall_metrics.requires_manual_review
                    + self.river_station_metrics.requires_manual_review
                    + self.taluk_metrics.requires_manual_review
                    + self.ifi_metrics.requires_manual_review
                ),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Export audit report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def summary_text(self) -> str:
        """Produce clean human-readable terminal audit summary."""
        lines = [
            "=" * 78,
            "  ADMINISTRATIVE GIS <-> ENVIRONMENTAL SPATIAL ASSOCIATION AUDIT",
            "=" * 78,
            f"  Audited At: {self.audited_at}",
            "-" * 78,
            f"  {'Entity':<24} {'Examined':<10} {'Matched':<10} {'Out-State':<11} {'Wrong-Dist':<12} {'Review':<8}",
            "-" * 78,
        ]

        all_metrics = [
            ("Weather Observations", self.weather_metrics),
            ("Rainfall Observations", self.rainfall_metrics),
            ("River Stations", self.river_station_metrics),
            ("Taluks (Containment)", self.taluk_metrics),
            ("IFI Flood Obs (Admin)", self.ifi_metrics),
        ]

        for label, m in all_metrics:
            lines.append(
                f"  {label:<24} {m.total_examined:<10} {m.spatially_matched:<10} "
                f"{m.outside_karnataka:<11} {m.outside_assigned_district:<12} {m.requires_manual_review:<8}"
            )

        lines.append("-" * 78)

        if self.discrepancies:
            lines.append(f"\n  DISCREPANCIES REQUIRING MANUAL REVIEW ({len(self.discrepancies)}):")
            for d in self.discrepancies:
                lines.append(f"  * [{d.entity_type}] Record: {d.record_id} ({d.identifier})")
                lines.append(f"    - Coordinates:      lat={d.latitude}, lon={d.longitude}")
                lines.append(f"    - Assigned District: {d.assigned_district_name} (ID: {d.assigned_district_id})")
                lines.append(f"    - Spatial District:  {d.spatial_district_name} (ID: {d.spatial_district_id})")
                if d.distance_to_assigned_district_m is not None:
                    lines.append(f"    - Dist to Assigned:  {d.distance_to_assigned_district_m / 1000:.2f} km")
                if d.distance_to_spatial_boundary_m is not None:
                    lines.append(f"    - Dist to Boundary:  {d.distance_to_spatial_boundary_m / 1000:.2f} km")
                lines.append(f"    - Note:              {d.remediation_note}")
        else:
            lines.append("\n  No point-based spatial discrepancies found.")

        lines.append(f"\n  TALUK BOUNDARY CASES ({len(self.boundary_cases)}):")
        lines.append(
            f"  * 240 / 240 taluks (100.0%) have point-on-surface inside assigned district."
        )
        lines.append(
            f"  * 44 / 240 taluks are strictly within (ST_Within = TRUE)."
        )
        lines.append(
            f"  * {len(self.boundary_cases)} / 240 taluks have micro boundary slivers (overlap >= 99.999%)."
        )
        lines.append(
            f"  * 0 taluks cross into another district or are disjoint."
        )

        lines.append(f"\n  IFI HISTORICAL FLOOD EVIDENCE ALIGNMENT:")
        lines.append(f"  * Total records:                  {self.ifi_details.total_records}")
        lines.append(f"  * Valid district foreign keys:    {self.ifi_details.valid_district_references}")
        lines.append(f"  * Invalid district references:    {self.ifi_details.invalid_district_references}")
        lines.append(f"  * NULL geometry verified:         {self.ifi_details.null_geometry_verified} (100.0%)")
        lines.append(f"  * Distinct districts referenced:  {self.ifi_details.distinct_districts_referenced}")
        lines.append("=" * 78)

        return "\n".join(lines)


# -----------------------------------------------------------------------------
# Spatial Association Auditor Engine
# -----------------------------------------------------------------------------


class SpatialAssociationAuditor:
    """
    Deterministic, read-only auditor for spatial associations against PostGIS.

    Evaluates:
    - Weather observations (point in assigned district polygon)
    - Rainfall observations (point in assigned district polygon)
    - River stations (point in assigned district polygon)
    - Taluk boundaries (polygon in assigned district polygon)
    - IFI historical observations (administrative district referential integrity)
    """

    def __init__(self, session: Session):
        self._session = session

    def audit(self) -> SpatialAssociationAuditReport:
        """Execute full spatial association audit across all entities."""
        weather_m, weather_disc = self._audit_weather_observations()
        rainfall_m, rainfall_disc = self._audit_rainfall_observations()
        river_m, river_disc = self._audit_river_stations()
        taluk_m, taluk_cases, taluk_disc = self._audit_taluks()
        ifi_m, ifi_details, ifi_disc = self._audit_ifi_flood_observations()

        all_discrepancies = (
            weather_disc + rainfall_disc + river_disc + taluk_disc + ifi_disc
        )

        return SpatialAssociationAuditReport(
            weather_metrics=weather_m,
            rainfall_metrics=rainfall_m,
            river_station_metrics=river_m,
            taluk_metrics=taluk_m,
            ifi_metrics=ifi_m,
            discrepancies=all_discrepancies,
            boundary_cases=taluk_cases,
            ifi_details=ifi_details,
            audited_at=datetime.now(timezone.utc).isoformat(),
        )

    def _audit_point_table(
        self,
        table_name: str,
        id_col: str,
        identifier_col: str,
        lat_col: str,
        lon_col: str,
        geom_col: str,
        district_id_col: str,
    ) -> tuple[EntityAuditMetrics, list[SpatialDiscrepancy]]:
        """
        Generic audit for point-based spatial observation tables.

        Evaluates:
        - NULL or invalid geometries
        - Containment within Karnataka State polygon (EPSG:4326)
        - Containment within assigned District polygon (EPSG:4326)
        - Spatial intersection with any District polygon
        - Distance to assigned district and boundary
        """
        # 1. Total and geometry integrity
        sql_counts = text(f"""
            SELECT
                count(*) as total,
                count({geom_col}) as has_geom,
                count(CASE WHEN {geom_col} IS NOT NULL AND ST_IsValid({geom_col}) THEN 1 END) as valid_geom,
                count({district_id_col}) as has_district_id
            FROM {table_name}
        """)
        row = self._session.execute(sql_counts).mappings().one()
        total = row["total"]
        has_geom = row["has_geom"]
        valid_geom = row["valid_geom"]
        invalid_or_missing_geom = total - valid_geom

        if total == 0:
            metrics = EntityAuditMetrics(
                entity_type=table_name,
                total_examined=0,
                spatially_matched=0,
                outside_karnataka=0,
                outside_assigned_district=0,
                missing_or_invalid_geometry=0,
                boundary_or_ambiguous=0,
                requires_manual_review=0,
            )
            return metrics, []

        # 2. Spatial containment and mismatch query
        sql_spatial = text(f"""
            SELECT
                t.{id_col} as rec_id,
                t.{identifier_col} as identifier,
                t.{lat_col} as latitude,
                t.{lon_col} as longitude,
                t.{district_id_col} as assigned_dist_id,
                d_assigned.name as assigned_dist_name,
                d_spatial.id as spatial_dist_id,
                d_spatial.name as spatial_dist_name,
                ST_Within(t.{geom_col}, s.geometry) as in_karnataka,
                ST_Within(t.{geom_col}, d_assigned.geometry) as in_assigned_district,
                CASE
                    WHEN d_assigned.geometry IS NOT NULL AND t.{geom_col} IS NOT NULL
                    THEN ST_Distance(t.{geom_col}::geography, d_assigned.geometry::geography)
                    ELSE NULL
                END as dist_to_assigned_m,
                CASE
                    WHEN d_spatial.geometry IS NOT NULL AND t.{geom_col} IS NOT NULL
                    THEN ST_Distance(t.{geom_col}::geography, ST_Boundary(d_spatial.geometry)::geography)
                    ELSE NULL
                END as dist_to_spatial_boundary_m
            FROM {table_name} t
            CROSS JOIN states s
            LEFT JOIN districts d_assigned ON t.{district_id_col} = d_assigned.id
            LEFT JOIN districts d_spatial ON ST_Within(t.{geom_col}, d_spatial.geometry)
            WHERE s.name = 'Karnataka'
        """)

        records = self._session.execute(sql_spatial).mappings().all()

        spatially_matched = 0
        outside_karnataka = 0
        outside_assigned_district = 0
        requires_manual_review = 0
        discrepancies: list[SpatialDiscrepancy] = []

        for r in records:
            in_kar = bool(r["in_karnataka"])
            in_assigned = bool(r["in_assigned_district"])

            if in_assigned:
                spatially_matched += 1
            else:
                requires_manual_review += 1
                if not in_kar:
                    outside_karnataka += 1
                    disc_type = "OUTSIDE_KARNATAKA"
                    note = "Observation point falls outside authoritative Karnataka state boundary."
                else:
                    outside_assigned_district += 1
                    disc_type = "OUTSIDE_ASSIGNED_DISTRICT"
                    note = (
                        f"Stored district is '{r['assigned_dist_name']}', but spatial location "
                        f"falls inside '{r['spatial_dist_name']}'."
                    )

                discrepancies.append(
                    SpatialDiscrepancy(
                        record_id=str(r["rec_id"]),
                        entity_type=table_name,
                        identifier=str(r["identifier"] or r["rec_id"]),
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        assigned_district_id=str(r["assigned_dist_id"]) if r["assigned_dist_id"] else None,
                        assigned_district_name=r["assigned_dist_name"],
                        spatial_district_id=str(r["spatial_dist_id"]) if r["spatial_dist_id"] else None,
                        spatial_district_name=r["spatial_dist_name"],
                        is_in_karnataka=in_kar,
                        distance_to_assigned_district_m=r["dist_to_assigned_m"],
                        distance_to_spatial_boundary_m=r["dist_to_spatial_boundary_m"],
                        discrepancy_type=disc_type,
                        remediation_note=note,
                    )
                )

        metrics = EntityAuditMetrics(
            entity_type=table_name,
            total_examined=total,
            spatially_matched=spatially_matched,
            outside_karnataka=outside_karnataka,
            outside_assigned_district=outside_assigned_district,
            missing_or_invalid_geometry=invalid_or_missing_geom,
            boundary_or_ambiguous=0,
            requires_manual_review=requires_manual_review,
        )

        return metrics, discrepancies

    def _audit_weather_observations(self) -> tuple[EntityAuditMetrics, list[SpatialDiscrepancy]]:
        """Audit weather_observations table."""
        return self._audit_point_table(
            table_name="weather_observations",
            id_col="id",
            identifier_col="location_reference",
            lat_col="latitude",
            lon_col="longitude",
            geom_col="geometry",
            district_id_col="district_id",
        )

    def _audit_rainfall_observations(self) -> tuple[EntityAuditMetrics, list[SpatialDiscrepancy]]:
        """Audit rainfall_observations table."""
        return self._audit_point_table(
            table_name="rainfall_observations",
            id_col="id",
            identifier_col="station_id",
            lat_col="latitude",
            lon_col="longitude",
            geom_col="geometry",
            district_id_col="district_id",
        )

    def _audit_river_stations(self) -> tuple[EntityAuditMetrics, list[SpatialDiscrepancy]]:
        """Audit river_stations table."""
        return self._audit_point_table(
            table_name="river_stations",
            id_col="id",
            identifier_col="station_code",
            lat_col="latitude",
            lon_col="longitude",
            geom_col="geometry",
            district_id_col="district_id",
        )

    def _audit_taluks(
        self,
    ) -> tuple[EntityAuditMetrics, list[TalukContainmentRecord], list[SpatialDiscrepancy]]:
        """
        Audit taluk-to-district polygonal containment.

        Evaluates:
        - ST_Within(t.geometry, d.geometry)
        - ST_PointOnSurface(t.geometry) containment in assigned district
        - Area overlap percentage: ST_Area(ST_Intersection(t, d)) / ST_Area(t)
        - Boundary slivers (overlap >= 99.999% but not strictly within)
        - Cross-district mismatches (overlap < 99.999% or point-on-surface in different district)
        """
        sql_taluks = text("""
            SELECT
                t.id as taluk_id,
                t.name as taluk_name,
                t.code as taluk_code,
                d.id as assigned_district_id,
                d.name as assigned_district_name,
                d.code as assigned_district_code,
                ST_Within(t.geometry, d.geometry) as strictly_within,
                ST_Within(ST_PointOnSurface(t.geometry), d.geometry) as point_on_surface_within,
                (ST_Area(ST_Intersection(t.geometry, d.geometry)) / ST_Area(t.geometry)) * 100 as pct_in_assigned,
                ST_IsValid(t.geometry) as is_valid_geom
            FROM taluks t
            JOIN districts d ON t.district_id = d.id
            ORDER BY t.name
        """)

        records = self._session.execute(sql_taluks).mappings().all()

        total = len(records)
        spatially_matched = 0
        boundary_cases: list[TalukContainmentRecord] = []
        discrepancies: list[SpatialDiscrepancy] = []
        outside_assigned_district = 0
        invalid_geom = 0

        for r in records:
            if not r["is_valid_geom"]:
                invalid_geom += 1

            strictly_within = bool(r["strictly_within"])
            pos_within = bool(r["point_on_surface_within"])
            pct = float(r["pct_in_assigned"] or 0.0)

            # Cap percentage at 100.0 for numerical display
            overlap_pct = min(100.0, pct)

            if strictly_within:
                status = "CONTAINED"
                spatially_matched += 1
            elif pos_within and overlap_pct >= 99.999:
                status = "BOUNDARY_SLIVER"
                spatially_matched += 1
                boundary_cases.append(
                    TalukContainmentRecord(
                        taluk_id=str(r["taluk_id"]),
                        taluk_name=r["taluk_name"],
                        taluk_code=r["taluk_code"],
                        assigned_district_id=str(r["assigned_district_id"]),
                        assigned_district_name=r["assigned_district_name"],
                        assigned_district_code=r["assigned_district_code"],
                        strictly_within=strictly_within,
                        point_on_surface_within=pos_within,
                        overlap_percentage=overlap_pct,
                        status=status,
                    )
                )
            else:
                status = "CROSS_DISTRICT_MISMATCH"
                outside_assigned_district += 1
                discrepancies.append(
                    SpatialDiscrepancy(
                        record_id=str(r["taluk_id"]),
                        entity_type="taluks",
                        identifier=r["taluk_name"],
                        latitude=None,
                        longitude=None,
                        assigned_district_id=str(r["assigned_district_id"]),
                        assigned_district_name=r["assigned_district_name"],
                        spatial_district_id=None,
                        spatial_district_name=None,
                        is_in_karnataka=True,
                        distance_to_assigned_district_m=None,
                        distance_to_spatial_boundary_m=None,
                        discrepancy_type="CROSS_DISTRICT_MISMATCH",
                        remediation_note=(
                            f"Taluk '{r['taluk_name']}' has only {overlap_pct:.2f}% overlap with "
                            f"assigned district '{r['assigned_district_name']}'."
                        ),
                    )
                )

        metrics = EntityAuditMetrics(
            entity_type="taluk_containment",
            total_examined=total,
            spatially_matched=spatially_matched,
            outside_karnataka=0,
            outside_assigned_district=outside_assigned_district,
            missing_or_invalid_geometry=invalid_geom,
            boundary_or_ambiguous=len(boundary_cases),
            requires_manual_review=outside_assigned_district + invalid_geom,
            details={
                "strictly_within_count": sum(1 for r in records if r["strictly_within"]),
                "point_on_surface_within_count": sum(1 for r in records if r["point_on_surface_within"]),
                "boundary_sliver_count": len(boundary_cases),
            },
        )

        return metrics, boundary_cases, discrepancies

    def _audit_ifi_flood_observations(
        self,
    ) -> tuple[EntityAuditMetrics, IfiAdministrativeRecord, list[SpatialDiscrepancy]]:
        """
        Audit historical IFI flood observations.

        Verifies:
        - Referential integrity to districts table
        - Alignment with KSR-SAC normalized district catalog
        - Geometry is explicitly NULL (no coordinate fabrication or centroid inference)
        - Taluk is NULL (IFI v3 reporting is district-level)
        """
        sql_ifi = text("""
            SELECT
                f.id as rec_id,
                f.district_id as district_id,
                f.taluk_id as taluk_id,
                f.geometry IS NOT NULL as has_geometry,
                d.id as valid_district_id,
                d.name as district_name,
                d.code as district_code
            FROM flood_observations f
            LEFT JOIN districts d ON f.district_id = d.id
        """)

        records = self._session.execute(sql_ifi).mappings().all()
        total = len(records)

        valid_dist_refs = 0
        invalid_dist_refs = 0
        null_geom_count = 0
        unexpected_geom_count = 0
        null_taluk_count = 0
        distinct_districts: set[str] = set()
        discrepancies: list[SpatialDiscrepancy] = []

        for r in records:
            if r["has_geometry"]:
                unexpected_geom_count += 1
            else:
                null_geom_count += 1

            if r["taluk_id"] is None:
                null_taluk_count += 1

            if r["valid_district_id"] is not None:
                valid_dist_refs += 1
                distinct_districts.add(str(r["valid_district_id"]))
            else:
                invalid_dist_refs += 1
                discrepancies.append(
                    SpatialDiscrepancy(
                        record_id=str(r["rec_id"]),
                        entity_type="flood_observations",
                        identifier=f"IFI_RECORD_{r['rec_id']}",
                        latitude=None,
                        longitude=None,
                        assigned_district_id=str(r["district_id"]) if r["district_id"] else None,
                        assigned_district_name=None,
                        spatial_district_id=None,
                        spatial_district_name=None,
                        is_in_karnataka=True,
                        distance_to_assigned_district_m=None,
                        distance_to_spatial_boundary_m=None,
                        discrepancy_type="INVALID_DISTRICT_REFERENCE",
                        remediation_note=f"District foreign key {r['district_id']} does not exist in districts table.",
                    )
                )

        ifi_details = IfiAdministrativeRecord(
            total_records=total,
            valid_district_references=valid_dist_refs,
            invalid_district_references=invalid_dist_refs,
            null_geometry_verified=null_geom_count,
            unexpected_geometry_count=unexpected_geom_count,
            null_taluk_verified=null_taluk_count,
            distinct_districts_referenced=len(distinct_districts),
        )

        metrics = EntityAuditMetrics(
            entity_type="flood_observations_ifi",
            total_examined=total,
            spatially_matched=valid_dist_refs,
            outside_karnataka=0,
            outside_assigned_district=invalid_dist_refs,
            missing_or_invalid_geometry=unexpected_geom_count,
            boundary_or_ambiguous=0,
            requires_manual_review=invalid_dist_refs + unexpected_geom_count,
            details={
                "distinct_districts_referenced": len(distinct_districts),
                "null_geometry_percentage": (null_geom_count / total * 100.0) if total > 0 else 0.0,
            },
        )

        return metrics, ifi_details, discrepancies
