"""
Karnataka administrative geography seeder and adapter.

Seeds Karnataka State (LGD code: 29) and its 31 administrative districts
with official LGD codes and verified centroid coordinates (EPSG:4326).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.geography import District, State
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)
from app.ingestion.validation import make_point_wkt

# Authoritative Karnataka Districts with official Government of India LGD codes and centroid coordinates
KARNATAKA_DISTRICTS_LGD: list[dict[str, Any]] = [
    {"code": "524", "name": "Bagalkote", "lat": 16.18, "lon": 75.69},
    {"code": "526", "name": "Bangalore Rural", "lat": 13.28, "lon": 77.56},
    {"code": "525", "name": "Bangalore Urban", "lat": 12.97, "lon": 77.59},
    {"code": "527", "name": "Belagavi", "lat": 15.85, "lon": 74.50},
    {"code": "528", "name": "Ballari", "lat": 15.14, "lon": 76.92},
    {"code": "529", "name": "Bidar", "lat": 17.91, "lon": 77.52},
    {"code": "530", "name": "Vijayapura", "lat": 16.83, "lon": 75.71},
    {"code": "531", "name": "Chamarajanagara", "lat": 11.92, "lon": 76.94},
    {"code": "630", "name": "Chikkaballapura", "lat": 13.43, "lon": 77.73},
    {"code": "532", "name": "Chikkamagaluru", "lat": 13.32, "lon": 75.77},
    {"code": "533", "name": "Chitradurga", "lat": 14.22, "lon": 76.40},
    {"code": "534", "name": "Dakshina Kannada", "lat": 12.87, "lon": 75.25},
    {"code": "535", "name": "Davanagere", "lat": 14.46, "lon": 75.92},
    {"code": "536", "name": "Dharwad", "lat": 15.46, "lon": 75.01},
    {"code": "537", "name": "Gadag", "lat": 15.43, "lon": 75.63},
    {"code": "538", "name": "Kalaburagi", "lat": 17.33, "lon": 76.83},
    {"code": "539", "name": "Hassan", "lat": 13.01, "lon": 76.10},
    {"code": "540", "name": "Haveri", "lat": 14.80, "lon": 75.40},
    {"code": "541", "name": "Kodagu", "lat": 12.42, "lon": 75.74},
    {"code": "542", "name": "Kolar", "lat": 13.14, "lon": 78.13},
    {"code": "543", "name": "Koppal", "lat": 15.35, "lon": 76.15},
    {"code": "544", "name": "Mandya", "lat": 12.52, "lon": 76.90},
    {"code": "545", "name": "Mysuru", "lat": 12.30, "lon": 76.65},
    {"code": "546", "name": "Raichur", "lat": 16.20, "lon": 77.36},
    {"code": "631", "name": "Ramanagara", "lat": 12.72, "lon": 77.28},
    {"code": "547", "name": "Shivamogga", "lat": 13.93, "lon": 75.57},
    {"code": "548", "name": "Tumakuru", "lat": 13.34, "lon": 77.10},
    {"code": "549", "name": "Udupi", "lat": 13.34, "lon": 74.74},
    {"code": "550", "name": "Uttara Kannada", "lat": 14.80, "lon": 74.13},
    {"code": "635", "name": "Yadgir", "lat": 16.77, "lon": 77.14},
    {"code": "738", "name": "Vijayanagara", "lat": 15.27, "lon": 76.39},
]


class KarnatakaGeographyAdapter(BaseAdapter):
    """Adapter to establish authoritative administrative geography foundation."""

    source_name = "Local Government Directory (LGD) - Karnataka"
    organization = "Ministry of Panchayati Raj / Survey of India"
    source_url = "https://lgdirectory.gov.in"
    access_method = "OFFICIAL_STANDARD"
    data_type = "GEOSPATIAL"
    update_frequency = "STATIC"

    def ingest(self, **kwargs: Any) -> IngestionResult:
        metrics = IngestionMetrics()
        started_at = datetime.now(timezone.utc)

        data_source = get_or_create_data_source(
            self.session,
            name=self.source_name,
            organization=self.organization,
            description="Authoritative administrative boundaries and LGD codes for Karnataka",
            source_url=self.source_url,
            access_method=self.access_method,
            data_type=self.data_type,
            geographic_coverage="Karnataka State",
            update_frequency=self.update_frequency,
            license_type="Government Open Data",
        )

        run = start_ingestion_run(self.session, data_source.id)

        try:
            # 1. State: Karnataka
            stmt = select(State).where((State.code == "29") | (State.name == "Karnataka"))
            karnataka = self.session.execute(stmt).scalar_one_or_none()
            if karnataka is None:
                karnataka = State(
                    id=uuid.uuid4(),
                    name="Karnataka",
                    code="29",
                )
                self.session.add(karnataka)
                self.session.flush()
                metrics.records_inserted += 1
            else:
                if karnataka.code != "29":
                    karnataka.code = "29"
                    self.session.flush()
                    metrics.records_updated += 1
            metrics.records_valid += 1
            metrics.records_received += 1

            # 2. Districts
            for dist_info in KARNATAKA_DISTRICTS_LGD:
                metrics.records_received += 1
                code = dist_info["code"]
                name = dist_info["name"]
                lat = dist_info["lat"]
                lon = dist_info["lon"]
                centroid_geom = make_point_wkt(lat, lon)

                d_stmt = select(District).where(
                    (District.code == code) | ((District.name == name) & (District.state_id == karnataka.id))
                )
                district = self.session.execute(d_stmt).scalar_one_or_none()

                if district is None:
                    district = District(
                        id=uuid.uuid4(),
                        state_id=karnataka.id,
                        name=name,
                        code=code,
                        centroid=centroid_geom,
                    )
                    self.session.add(district)
                    self.session.flush()
                    metrics.records_inserted += 1
                else:
                    changed = False
                    if district.code != code:
                        district.code = code
                        changed = True
                    if district.centroid is None:
                        district.centroid = centroid_geom
                        changed = True
                    if changed:
                        self.session.flush()
                        metrics.records_updated += 1

                metrics.records_valid += 1

            self.session.commit()
            status = "SUCCESS"
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
