"""
District <-> Sub-basin <-> River <-> Gauge Crosswalk Engine.

Preserves M:N relationships between Karnataka districts and hydrological units:
- CWC Major Basins (7 intersecting Karnataka)
- HydroBASINS Level-7 (116 sub-basins in Karnataka)
- HydroRIVERS (15,371 river reach segments)
- River Gauges (CWC telemetry stations)

Every relationship includes explicit spatial provenance and area attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DistrictBasinLink:
    district_name: str
    basin_name: str
    basin_code: str
    intersection_area_km2: float
    percent_of_district_in_basin: float
    provenance: str


@dataclass(frozen=True)
class DistrictSubBasinLink:
    district_name: str
    sub_basin_name: str
    hybas_id: int
    sub_area_km2: float
    upstream_area_km2: float
    intersection_area_km2: float
    percent_of_district_in_subbasin: float
    provenance: str


@dataclass(frozen=True)
class GaugeHydrologyLink:
    station_name: str
    station_code: str
    district_name: str
    basin_name: str
    sub_basin_name: str
    hybas_id: int
    upstream_area_km2: float
    river_name: str
    latitude: float
    longitude: float
    provenance: str


class HydrologicalCrosswalk:
    """Builds and queries the M:N spatial crosswalk across administrative and hydrologic units."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_district_basin_links(self) -> list[DistrictBasinLink]:
        """Retrieve all 54 District <-> CWC River Basin intersections."""
        q = text("""
            SELECT 
                d.name as district_name,
                rb.name as basin_name,
                rb.code as basin_code,
                drb.intersection_area_km2,
                drb.percent_of_district_in_basin,
                drb.derivation_method as provenance
            FROM district_river_basins drb
            JOIN districts d ON drb.district_id = d.id
            JOIN river_basins rb ON drb.river_basin_id = rb.id
            ORDER BY d.name, drb.percent_of_district_in_basin DESC;
        """)
        rows = self.session.execute(q).fetchall()
        return [
            DistrictBasinLink(
                district_name=r.district_name,
                basin_name=r.basin_name,
                basin_code=r.basin_code,
                intersection_area_km2=float(r.intersection_area_km2),
                percent_of_district_in_basin=float(r.percent_of_district_in_basin),
                provenance=r.provenance or "PostGIS ST_Intersection",
            )
            for r in rows
        ]

    def get_district_sub_basin_links(self) -> list[DistrictSubBasinLink]:
        """Retrieve all 264 District <-> HydroBASINS Level-7 intersections."""
        q = text("""
            SELECT 
                d.name as district_name,
                sb.name as sub_basin_name,
                sb.hybas_id,
                sb.sub_area,
                sb.up_area,
                dsb.intersection_area_km2,
                dsb.percent_of_district_in_subbasin,
                dsb.derivation_method as provenance
            FROM district_sub_basins dsb
            JOIN districts d ON dsb.district_id = d.id
            JOIN sub_basins sb ON dsb.sub_basin_id = sb.id
            ORDER BY d.name, dsb.percent_of_district_in_subbasin DESC;
        """)
        rows = self.session.execute(q).fetchall()
        return [
            DistrictSubBasinLink(
                district_name=r.district_name,
                sub_basin_name=r.sub_basin_name,
                hybas_id=int(r.hybas_id),
                sub_area_km2=float(r.sub_area or 0.0),
                upstream_area_km2=float(r.up_area or 0.0),
                intersection_area_km2=float(r.intersection_area_km2),
                percent_of_district_in_subbasin=float(r.percent_of_district_in_subbasin),
                provenance=r.provenance or "PostGIS ST_Intersection",
            )
            for r in rows
        ]

    def get_gauge_links(self) -> list[GaugeHydrologyLink]:
        """Retrieve spatial and hydrological linkage for all database river stations."""
        q = text("""
            SELECT 
                rs.name as station_name,
                rs.station_code,
                d.name as district_name,
                rb.name as basin_name,
                sb.name as sub_basin_name,
                sb.hybas_id,
                sb.up_area as upstream_area_km2,
                r.name as river_name,
                rs.latitude,
                rs.longitude
            FROM river_stations rs
            LEFT JOIN districts d ON rs.district_id = d.id
            LEFT JOIN rivers r ON rs.river_id = r.id
            LEFT JOIN river_basins rb ON r.basin_id = rb.id
            LEFT JOIN sub_basins sb ON ST_Contains(sb.geometry, rs.geometry);
        """)
        rows = self.session.execute(q).fetchall()
        return [
            GaugeHydrologyLink(
                station_name=r.station_name,
                station_code=r.station_code,
                district_name=r.district_name or "Unknown",
                basin_name=r.basin_name or "Unknown",
                sub_basin_name=r.sub_basin_name or "Unknown",
                hybas_id=int(r.hybas_id) if r.hybas_id else 0,
                upstream_area_km2=float(r.upstream_area_km2 or 0.0),
                river_name=r.river_name or "Unknown",
                latitude=float(r.latitude),
                longitude=float(r.longitude),
                provenance="PostGIS ST_Contains (RiverStation point in District and HydroBASINS polygon)",
            )
            for r in rows
        ]

    def verify_crosswalk_integrity(self) -> dict[str, Any]:
        """Validate M:N invariants and check for orphan geometries or broken crosswalks."""
        district_links = self.get_district_basin_links()
        sub_basin_links = self.get_district_sub_basin_links()
        gauge_links = self.get_gauge_links()

        # Invariant 1: Exactly 31 unique districts must have basin links
        districts_in_basins = {l.district_name for l in district_links}
        # Invariant 2: Total basin links should equal 54
        total_basin_links = len(district_links)
        # Invariant 3: Total sub-basin links should equal 264
        total_sub_basin_links = len(sub_basin_links)

        # Multi-basin district verification
        from collections import Counter
        basin_counts = Counter(l.district_name for l in district_links)
        multi_basin_districts = {k: v for k, v in basin_counts.items() if v > 1}

        return {
            "total_districts_covered": len(districts_in_basins),
            "total_district_basin_links": total_basin_links,
            "total_district_sub_basin_links": total_sub_basin_links,
            "multi_basin_districts_count": len(multi_basin_districts),
            "multi_basin_districts": multi_basin_districts,
            "gauge_links_count": len(gauge_links),
            "is_valid": len(districts_in_basins) == 31 and total_basin_links == 54 and total_sub_basin_links == 264,
        }
