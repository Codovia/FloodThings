"""
KSR-SAC Administrative GIS PostGIS Ingestion Adapter.

Safely loads validated KSR-SAC Karnataka State, District, and Taluk geometries
into the existing PostgreSQL/PostGIS database per Phase 3.1 design contract.

Key invariants:
1. Atomic single transaction: zero partial ingestion.
2. District identity preservation: existing districts.id UUIDs and districts.code
   are preserved in place, safeguarding all active foreign key references.
3. Strict validation: 16 in-memory pre-insert geometry and hierarchy checks.
4. Idempotent: repeated executions result in 1 state, 31 districts, and 240 taluks.
5. Deterministic CRS: input EPSG:32643 transformed to storage EPSG:4326.
6. Provenance: tracked via DataSource and DataIngestionRun registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from geoalchemy2.elements import WKTElement
from shapely.geometry import MultiPolygon
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.geography import District, State, Taluk
from app.gis.ksrsac import (
    DEFAULT_RELATIVE_OVERLAP_TOLERANCE,
    EXPECTED_DISTRICT_COUNT,
    EXPECTED_STATE_COUNT,
    EXPECTED_TALUK_COUNT,
    EXPECTED_VIJAYANAGARA_TALUK_COUNT,
    VIJAYANAGARA_KGIS_CODE,
    VIJAYANAGARA_LGD_CODE,
    KsrsacAdminNormalizer,
    KsrsacNormalizationResult,
    KsrsacTopologyError,
    KsrsacValidationError,
    NormalizedDistrict,
    NormalizedState,
    NormalizedTaluk,
)
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)

# Canonical alias mapping: KSR-SAC feature name -> Existing Database district name
# Established in Phase 3.1 (docs/GIS_POSTGIS_INGESTION_DESIGN.md §4.2)
KSR_TO_DB_DISTRICT_NAMES: dict[str, str] = {
    "Kalaburgi": "Kalaburagi",
    "Kolara": "Kolar",
    "Bengaluru (Urban)": "Bangalore Urban",
    "Bengaluru (Rural)": "Bangalore Rural",
    "Bengaluru South": "Ramanagara",
}


class KsrsacGisAdapter(BaseAdapter):
    """Adapter to ingest validated KSR-SAC administrative geometries into PostGIS."""

    source_name = "Karnataka State Remote Sensing Applications Centre (KSR-SAC) - Administrative GIS"
    organization = "Karnataka State Remote Sensing Applications Centre (KSR-SAC), Dept of IT, BT and S&T, Govt of Karnataka"
    source_url = "https://kgis.ksrsac.in/kgis/downloads.aspx"
    access_method = "OFFICIAL_STANDARD"
    data_type = "GEOSPATIAL"
    update_frequency = "STATIC"
    license_type = "Government Open Data (Karnataka)"

    def __init__(
        self,
        session: Session,
        normalizer: KsrsacAdminNormalizer | None = None,
    ):
        super().__init__(session)
        self.normalizer = normalizer or KsrsacAdminNormalizer()

    def validate_pre_insert(
        self,
        state: NormalizedState,
        admin_res: KsrsacNormalizationResult,
    ) -> None:
        """
        Execute 16 mandatory pre-insert validation checks on normalized entities.

        Raises KsrsacValidationError if any invariant is violated.
        """
        # 1. State count = 1
        if state is None:
            raise KsrsacValidationError("State feature is missing")

        # 2. District count = 31
        if admin_res.district_count != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError(
                f"Expected exactly {EXPECTED_DISTRICT_COUNT} districts, found {admin_res.district_count}"
            )

        # 3. Taluk count = 240
        if admin_res.taluk_count != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError(
                f"Expected exactly {EXPECTED_TALUK_COUNT} taluks, found {admin_res.taluk_count}"
            )

        # 4 & 5. All geometries non-null and non-empty
        if state.geometry is None or state.geometry.is_empty:
            raise KsrsacValidationError("State geometry is null or empty")
        for d in admin_res.districts:
            if d.geometry is None or d.geometry.is_empty:
                raise KsrsacValidationError(f"District {d.district_name} geometry is null or empty")
        for t in admin_res.taluks:
            if t.geometry is None or t.geometry.is_empty:
                raise KsrsacValidationError(f"Taluk {t.taluk_name} geometry is null or empty")

        # 6. All geometries valid
        if not state.geometry.is_valid:
            raise KsrsacTopologyError("State geometry is invalid")
        for d in admin_res.districts:
            if not d.geometry.is_valid:
                raise KsrsacTopologyError(f"District {d.district_name} geometry is invalid")
        for t in admin_res.taluks:
            if not t.geometry.is_valid:
                raise KsrsacTopologyError(f"Taluk {t.taluk_name} geometry is invalid")

        # 7. Geometry type = MULTIPOLYGON
        if not isinstance(state.geometry, MultiPolygon):
            raise KsrsacValidationError(f"State geometry type must be MultiPolygon, got {type(state.geometry)}")
        for d in admin_res.districts:
            if not isinstance(d.geometry, MultiPolygon):
                raise KsrsacValidationError(f"District {d.district_name} geometry type must be MultiPolygon, got {type(d.geometry)}")
        for t in admin_res.taluks:
            if not isinstance(t.geometry, MultiPolygon):
                raise KsrsacValidationError(f"Taluk {t.taluk_name} geometry type must be MultiPolygon, got {type(t.geometry)}")

        # 8. SRID = 4326 (verified via target_crs)
        if admin_res.target_crs != "EPSG:4326":
            raise KsrsacValidationError(f"Target CRS must be EPSG:4326, got {admin_res.target_crs}")

        # 9. Unique district identifiers
        kgis_dists = [d.kgis_district_code for d in admin_res.districts]
        lgd_dists = [d.lgd_district_code for d in admin_res.districts]
        if len(set(kgis_dists)) != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError("District KGIS codes are not unique")
        if len(set(lgd_dists)) != EXPECTED_DISTRICT_COUNT:
            raise KsrsacValidationError("District LGD codes are not unique")

        # 10. Unique taluk identifiers
        kgis_taluks = [t.kgis_taluk_code for t in admin_res.taluks]
        lgd_taluks = [t.lgd_taluk_code for t in admin_res.taluks]
        if len(set(kgis_taluks)) != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError("Taluk KGIS codes are not unique")
        if len(set(lgd_taluks)) != EXPECTED_TALUK_COUNT:
            raise KsrsacValidationError("Taluk LGD codes are not unique")

        # 11. Every taluk has a valid parent district
        district_kgis_set = set(kgis_dists)
        for t in admin_res.taluks:
            if t.parent_kgis_district_code not in district_kgis_set:
                raise KsrsacTopologyError(
                    f"Taluk {t.taluk_name} references non-existent parent KGIS code: {t.parent_kgis_district_code}"
                )

        # 12 & 13. All districts and taluks intersect state and representative points within state
        self.normalizer.validate_state_containment(
            state, admin_res.districts, admin_res.taluks
        )

        # 14 & 15. All taluks intersect their parent district and representative points within parent
        districts_by_kgis = {d.kgis_district_code: d for d in admin_res.districts}
        for t in admin_res.taluks:
            parent = districts_by_kgis[t.parent_kgis_district_code]
            if not t.geometry.intersects(parent.geometry):
                raise KsrsacTopologyError(
                    f"Taluk {t.taluk_name} does not intersect parent district {parent.district_name}"
                )
            if not t.geometry.representative_point().within(parent.geometry):
                raise KsrsacTopologyError(
                    f"Taluk {t.taluk_name} representative point not within parent district {parent.district_name}"
                )

        # 16. Vijayanagara 6-taluk integrity and no duplicate administrative records
        vij_taluks = admin_res.get_taluks_for_district(VIJAYANAGARA_KGIS_CODE)
        if len(vij_taluks) != EXPECTED_VIJAYANAGARA_TALUK_COUNT:
            raise KsrsacTopologyError(
                f"Vijayanagara (KGIS {VIJAYANAGARA_KGIS_CODE}) must have exactly "
                f"{EXPECTED_VIJAYANAGARA_TALUK_COUNT} taluks, found {len(vij_taluks)}"
            )

    def ingest(self, **kwargs: Any) -> IngestionResult:
        """
        Execute atomic PostGIS ingestion of State, District, and Taluk geometries.

        Ensures:
        - 1 atomic transaction.
        - Existing district UUIDs and codes are strictly preserved.
        - Idempotent upserting: running multiple times leaves 1 state, 31 districts, 240 taluks.
        """
        metrics = IngestionMetrics()
        started_at = datetime.now(timezone.utc)

        data_source = get_or_create_data_source(
            self.session,
            name=self.source_name,
            organization=self.organization,
            description="Authoritative administrative boundaries and PostGIS geometries for Karnataka",
            source_url=self.source_url,
            access_method=self.access_method,
            data_type=self.data_type,
            geographic_coverage="Karnataka State",
            update_frequency=self.update_frequency,
            license_type=self.license_type,
        )

        run = start_ingestion_run(self.session, data_source.id)

        try:
            # 1. Normalize State and Administrative entities in memory
            norm_state = self.normalizer.normalize_state()
            norm_admin = self.normalizer.normalize()

            # 2. Run 16 pre-insert validation checks
            self.validate_pre_insert(norm_state, norm_admin)

            # 3. Total records received: 1 state + 31 districts + 240 taluks = 272
            metrics.records_received = 1 + norm_admin.district_count + norm_admin.taluk_count

            # 4. Ingest State (Update geometry on existing Karnataka record)
            state_stmt = select(State).where(
                (State.code == "29") | (State.name == "Karnataka")
            )
            state_entity = self.session.execute(state_stmt).scalar_one_or_none()
            if state_entity is None:
                state_entity = State(
                    id=uuid.uuid4(),
                    name="Karnataka",
                    code="29",
                    geometry=WKTElement(norm_state.raw_wkt, srid=4326),
                )
                self.session.add(state_entity)
                metrics.records_inserted += 1
            else:
                state_entity.geometry = WKTElement(norm_state.raw_wkt, srid=4326)
                metrics.records_updated += 1

            self.session.flush()
            metrics.records_valid += 1

            # 5. Pre-cache existing database districts by name for bijective matching
            db_dist_stmt = select(District).where(District.state_id == state_entity.id)
            db_districts = self.session.execute(db_dist_stmt).scalars().all()
            db_districts_by_name = {d.name: d for d in db_districts}

            if len(db_districts) != EXPECTED_DISTRICT_COUNT:
                raise KsrsacValidationError(
                    f"Expected {EXPECTED_DISTRICT_COUNT} existing database districts, found {len(db_districts)}"
                )

            # Bijective mapping: map KGIS district code -> existing DB District UUID
            kgis_to_db_district_id: dict[str, uuid.UUID] = {}

            for kd in norm_admin.districts:
                target_db_name = KSR_TO_DB_DISTRICT_NAMES.get(kd.district_name, kd.district_name)
                db_district = db_districts_by_name.get(target_db_name)

                if db_district is None:
                    raise KsrsacValidationError(
                        f"Could not map KSR-SAC district '{kd.district_name}' to existing database district "
                        f"(resolved target name '{target_db_name}' not found in database)"
                    )

                # Update geometry and centroid in place; strictly preserve UUID and existing code
                db_district.geometry = WKTElement(kd.raw_wkt, srid=4326)
                db_district.centroid = WKTElement(kd.centroid.wkt, srid=4326)

                kgis_to_db_district_id[kd.kgis_district_code] = db_district.id
                metrics.records_updated += 1
                metrics.records_valid += 1

            self.session.flush()

            # 6. Ingest Taluks (240 records)
            # Pre-cache existing taluks by code to ensure idempotent re-runs
            existing_taluks_stmt = select(Taluk)
            existing_taluks = self.session.execute(existing_taluks_stmt).scalars().all()
            existing_taluks_by_code = {t.code: t for t in existing_taluks if t.code}

            for kt in norm_admin.taluks:
                parent_db_id = kgis_to_db_district_id.get(kt.parent_kgis_district_code)
                if parent_db_id is None:
                    raise KsrsacTopologyError(
                        f"Taluk '{kt.taluk_name}' parent KGIS code '{kt.parent_kgis_district_code}' "
                        "did not resolve to any database district"
                    )

                taluk_code = kt.lgd_taluk_code
                taluk_geom = WKTElement(kt.raw_wkt, srid=4326)

                existing_taluk = existing_taluks_by_code.get(taluk_code)
                if existing_taluk is None:
                    new_taluk = Taluk(
                        id=uuid.uuid4(),
                        district_id=parent_db_id,
                        name=kt.taluk_name,
                        code=taluk_code,
                        geometry=taluk_geom,
                    )
                    self.session.add(new_taluk)
                    metrics.records_inserted += 1
                else:
                    existing_taluk.district_id = parent_db_id
                    existing_taluk.name = kt.taluk_name
                    existing_taluk.geometry = taluk_geom
                    metrics.records_updated += 1

                metrics.records_valid += 1

            self.session.flush()

            # 7. Commit atomic transaction
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
            metrics.records_rejected = metrics.records_received - metrics.records_valid
            try:
                complete_ingestion_run(
                    self.session,
                    run,
                    status="FAILED",
                    metrics=metrics,
                    error_message=err_msg,
                )
                self.session.commit()
            except Exception:
                self.session.rollback()

            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status="FAILED",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
                error_message=err_msg,
            )
