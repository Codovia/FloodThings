"""
Hydrological GIS Ingestion Adapter.

Idempotent ingestion of:
  1. CWC major basins → river_basins table
  2. HydroBASINS Level-7 → sub_basins table
  3. HydroRIVERS v1.0 → rivers table
  4. District crosswalk computation → district_sub_basins, district_river_basins

Uses source feature IDs for upsert (idempotent: re-running produces identical state).

CWC major basins = authoritative statutory reference.
HydroBASINS = hydrological topology (NOT CWC hierarchy).
HydroRIVERS = reach network.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District, State
from app.db.models.hydrology import (
    DistrictRiverBasin,
    DistrictSubBasin,
    River,
    RiverBasin,
    SubBasin,
)
from app.db.models.system import DataIngestionRun, DataSource
from app.gis.hydrosheds import (
    CwcBasinNormalizer,
    HydroBasinsNormalizer,
    HydroRiversNormalizer,
    NormalizedCwcBasin,
    NormalizedHydroBasin,
    NormalizedHydroRiver,
)
from app.gis.topology_validation import (
    validate_hydrobasins_topology,
    validate_hydrorivers_topology,
)
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)

logger = logging.getLogger(__name__)

# Default paths relative to project root
# This file: backend/app/ingestion/sources/hydrosheds_gis.py → parents[4] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CWC_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "hydrosheds" / "basin_cwc_shp.zip"
DEFAULT_HYDROBASINS_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "hydrosheds" / "hybas_as_lev07_v1c.zip"
DEFAULT_HYDRORIVERS_PATH = PROJECT_ROOT / "data" / "raw" / "gis" / "hydrosheds" / "HydroRIVERS_v10_as_shp.zip"


class HydrologicalGisAdapter(BaseAdapter):
    """Ingestion adapter for hydrological GIS datasets."""

    source_name = "HydroSHEDS / CWC Hydrological GIS"
    organization = "WWF / USGS / McGill University / CWC-NWDP"
    source_url = "https://www.hydrosheds.org"
    access_method = "SHAPEFILE_ZIP"
    data_type = "GEOSPATIAL"
    update_frequency = "STATIC"

    def __init__(self, session: Session):
        super().__init__(session)

    def ingest(self, **kwargs: Any) -> IngestionResult:
        """Execute full hydrological GIS ingestion pipeline."""
        started = datetime.now(timezone.utc)
        metrics = IngestionMetrics()

        try:
            # Get or create data source
            ds = get_or_create_data_source(
                self.session,
                name=self.source_name,
                organization=self.organization,
                source_url=self.source_url,
                access_method=self.access_method,
                data_type=self.data_type,
                geographic_coverage="Karnataka / Asia",
                update_frequency=self.update_frequency,
                license_type="Free for scientific/educational use",
            )
            run = start_ingestion_run(self.session, ds.id)

            # Get Karnataka state boundary for spatial filtering
            state_boundary = self._get_karnataka_boundary()

            # Phase 1: CWC basins
            cwc_metrics = self._ingest_cwc_basins(
                kwargs.get("cwc_path", DEFAULT_CWC_PATH),
                state_boundary,
            )
            metrics.records_received += cwc_metrics.records_received
            metrics.records_inserted += cwc_metrics.records_inserted
            metrics.records_updated += cwc_metrics.records_updated

            # Phase 2: HydroBASINS
            hb_metrics = self._ingest_hydrobasins(
                kwargs.get("hydrobasins_path", DEFAULT_HYDROBASINS_PATH),
                state_boundary,
            )
            metrics.records_received += hb_metrics.records_received
            metrics.records_inserted += hb_metrics.records_inserted
            metrics.records_updated += hb_metrics.records_updated

            # Phase 3: HydroRIVERS
            hr_metrics = self._ingest_hydrorivers(
                kwargs.get("hydrorivers_path", DEFAULT_HYDRORIVERS_PATH),
                state_boundary,
            )
            metrics.records_received += hr_metrics.records_received
            metrics.records_inserted += hr_metrics.records_inserted
            metrics.records_updated += hr_metrics.records_updated

            # Phase 4: District crosswalks
            xwalk_metrics = self._compute_district_crosswalks()
            metrics.records_received += xwalk_metrics.records_received
            metrics.records_inserted += xwalk_metrics.records_inserted
            metrics.records_updated += xwalk_metrics.records_updated

            self.session.flush()
            complete_ingestion_run(self.session, run, "SUCCESS", metrics)
            self.session.commit()

            logger.info(
                "Hydrological GIS ingestion complete: %d received, %d inserted, %d updated",
                metrics.records_received, metrics.records_inserted, metrics.records_updated,
            )

            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status="SUCCESS",
                started_at=started,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
            )

        except Exception as e:
            logger.error("Hydrological GIS ingestion failed: %s", e, exc_info=True)
            self.session.rollback()
            metrics.errors.append(str(e))
            return IngestionResult(
                source_name=self.source_name,
                run_id=uuid.uuid4(),
                status="FAILED",
                started_at=started,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
                error_message=str(e),
            )

    def _get_karnataka_boundary(self) -> MultiPolygon:
        """Retrieve Karnataka state boundary from database."""
        stmt = select(State).where(State.name == "Karnataka")
        state = self.session.execute(stmt).scalar_one_or_none()
        if state is None:
            raise RuntimeError("Karnataka state not found in database")
        if state.geometry is None:
            raise RuntimeError("Karnataka state has no geometry")

        # Convert from WKB to shapely
        from geoalchemy2.shape import to_shape
        geom = to_shape(state.geometry)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        return geom

    def _ingest_cwc_basins(
        self, zip_path: Path, state_boundary: MultiPolygon
    ) -> IngestionMetrics:
        """Ingest CWC major basins into river_basins table."""
        metrics = IngestionMetrics()
        logger.info("=== Ingesting CWC Major Basins ===")

        normalizer = CwcBasinNormalizer(zip_path)
        basins, norm_result = normalizer.normalize()
        metrics.records_received = len(basins)

        logger.info(
            "CWC normalization: %d basins, %d repaired",
            norm_result.features_valid, norm_result.features_repaired,
        )

        # Determine Karnataka intersection for each basin
        for basin in basins:
            intersects_ka = basin.geometry.intersects(state_boundary)

            # Check if existing row matches by name
            existing = self.session.execute(
                select(RiverBasin).where(RiverBasin.name == basin.basin_name)
            ).scalar_one_or_none()

            # Also check by source_feature_id
            if existing is None:
                existing = self.session.execute(
                    select(RiverBasin).where(
                        RiverBasin.source_feature_id == basin.source_feature_id
                    )
                ).scalar_one_or_none()

            if existing is not None:
                # Update existing record (preserve UUID)
                existing.geometry = from_shape(basin.geometry, srid=4326)
                existing.source_agency = basin.source_agency
                existing.source_dataset = basin.source_dataset
                existing.source_version = basin.source_version
                existing.source_feature_id = basin.source_feature_id
                existing.area_km2 = basin.area_km2
                existing.intersects_karnataka = intersects_ka
                existing.updated_at = datetime.now(timezone.utc)
                if not existing.code and basin.basin_code:
                    existing.code = basin.basin_code
                metrics.records_updated += 1
                logger.debug("Updated CWC basin: %s (UUID=%s)", basin.basin_name, existing.id)
            else:
                # Insert new record
                new_basin = RiverBasin(
                    id=uuid.uuid4(),
                    name=basin.basin_name,
                    code=basin.basin_code,
                    geometry=from_shape(basin.geometry, srid=4326),
                    source_agency=basin.source_agency,
                    source_dataset=basin.source_dataset,
                    source_version=basin.source_version,
                    source_feature_id=basin.source_feature_id,
                    area_km2=basin.area_km2,
                    intersects_karnataka=intersects_ka,
                )
                self.session.add(new_basin)
                metrics.records_inserted += 1
                logger.debug("Inserted CWC basin: %s", basin.basin_name)

        self.session.flush()

        # Verify Karnataka intersection count
        ka_count = self.session.execute(
            select(func.count()).where(RiverBasin.intersects_karnataka == True)
        ).scalar()
        logger.info("CWC basins intersecting Karnataka: %d", ka_count)

        return metrics

    def _ingest_hydrobasins(
        self, zip_path: Path, state_boundary: MultiPolygon
    ) -> IngestionMetrics:
        """Ingest HydroBASINS Level-7 into sub_basins table."""
        metrics = IngestionMetrics()
        logger.info("=== Ingesting HydroBASINS Level-7 ===")

        normalizer = HydroBasinsNormalizer(zip_path)
        features, norm_result = normalizer.normalize(state_boundary)
        metrics.records_received = len(features)

        # Topology validation
        topo_result = validate_hydrobasins_topology(features)
        if not topo_result.is_dag:
            logger.error("HydroBASINS topology validation FAILED: cycles detected")
        if topo_result.duplicate_ids:
            raise RuntimeError(
                f"HydroBASINS has duplicate HYBAS_IDs: {topo_result.duplicate_ids}"
            )

        logger.info(
            "HydroBASINS topology: DAG=%s, %d unique, %d self-refs, %d missing downstream",
            topo_result.is_dag, topo_result.unique_ids,
            len(topo_result.self_references), len(topo_result.missing_downstream),
        )

        existing_sub_basins = {
            sb.hybas_id: sb
            for sb in self.session.execute(
                select(SubBasin).where(SubBasin.hybas_id.isnot(None))
            ).scalars().all()
        }

        for feat in features:
            existing = existing_sub_basins.get(feat.hybas_id)

            if existing is not None:
                existing.geometry = from_shape(feat.geometry, srid=4326)
                existing.next_down = feat.next_down
                existing.next_sink = feat.next_sink
                existing.main_bas = feat.main_bas
                existing.sub_area = feat.sub_area
                existing.up_area = feat.up_area
                existing.pfaf_id = feat.pfaf_id
                existing.endo = feat.endo
                existing.coast = feat.coast
                existing.dist_sink = feat.dist_sink
                existing.dist_main = feat.dist_main
                existing.order_ = feat.order
                existing.sort = feat.sort
                existing.source_dataset = feat.source_dataset
                existing.source_version = feat.source_version
                existing.geometry_repaired = feat.geometry_repaired
                existing.updated_at = datetime.now(timezone.utc)
                metrics.records_updated += 1
            else:
                sb = SubBasin(
                    id=uuid.uuid4(),
                    name=f"HYBAS_{feat.hybas_id}",
                    basin_id=None,  # HydroBASINS ≠ CWC sub-basin
                    geometry=from_shape(feat.geometry, srid=4326),
                    hybas_id=feat.hybas_id,
                    next_down=feat.next_down,
                    next_sink=feat.next_sink,
                    main_bas=feat.main_bas,
                    sub_area=feat.sub_area,
                    up_area=feat.up_area,
                    pfaf_id=feat.pfaf_id,
                    endo=feat.endo,
                    coast=feat.coast,
                    dist_sink=feat.dist_sink,
                    dist_main=feat.dist_main,
                    order_=feat.order,
                    sort=feat.sort,
                    source_dataset=feat.source_dataset,
                    source_version=feat.source_version,
                    geometry_repaired=feat.geometry_repaired,
                )
                self.session.add(sb)
                metrics.records_inserted += 1

        self.session.flush()
        logger.info(
            "HydroBASINS: %d inserted, %d updated",
            metrics.records_inserted, metrics.records_updated,
        )
        return metrics

    def _ingest_hydrorivers(
        self, zip_path: Path, state_boundary: MultiPolygon
    ) -> IngestionMetrics:
        """Ingest HydroRIVERS reaches into rivers table."""
        metrics = IngestionMetrics()
        logger.info("=== Ingesting HydroRIVERS ===")

        normalizer = HydroRiversNormalizer(zip_path)
        features, norm_result = normalizer.normalize(state_boundary)
        metrics.records_received = len(features)

        # Topology validation
        topo_result = validate_hydrorivers_topology(features)
        if topo_result.duplicate_ids:
            raise RuntimeError(
                f"HydroRIVERS has duplicate HYRIV_IDs: {topo_result.duplicate_ids}"
            )

        logger.info(
            "HydroRIVERS topology: DAG=%s, %d unique, %d missing downstream",
            topo_result.is_dag, topo_result.unique_ids,
            len(topo_result.missing_downstream),
        )

        existing_rivers = {
            r.hyriv_id: r
            for r in self.session.execute(
                select(River).where(River.hyriv_id.isnot(None))
            ).scalars().all()
        }

        # Batch insert for performance
        batch_size = 1000
        for i in range(0, len(features), batch_size):
            batch = features[i:i + batch_size]
            for feat in batch:
                existing = existing_rivers.get(feat.hyriv_id)

                if existing is not None:
                    existing.geometry = from_shape(feat.geometry, srid=4326)
                    existing.next_down = feat.next_down
                    existing.main_riv = feat.main_riv
                    existing.length_km = feat.length_km
                    existing.dist_dn_km = feat.dist_dn_km
                    existing.dist_up_km = feat.dist_up_km
                    existing.catch_skm = feat.catch_skm
                    existing.upland_skm = feat.upland_skm
                    existing.dis_av_cms = feat.dis_av_cms
                    existing.ord_stra = feat.ord_stra
                    existing.ord_clas = feat.ord_clas
                    existing.ord_flow = feat.ord_flow
                    existing.hybas_l12 = feat.hybas_l12
                    existing.source_dataset = feat.source_dataset
                    existing.source_version = feat.source_version
                    existing.updated_at = datetime.now(timezone.utc)
                    metrics.records_updated += 1
                else:
                    river = River(
                        id=uuid.uuid4(),
                        name=f"HYRIV_{feat.hyriv_id}",
                        geometry=from_shape(feat.geometry, srid=4326),
                        hyriv_id=feat.hyriv_id,
                        next_down=feat.next_down,
                        main_riv=feat.main_riv,
                        length_km=feat.length_km,
                        dist_dn_km=feat.dist_dn_km,
                        dist_up_km=feat.dist_up_km,
                        catch_skm=feat.catch_skm,
                        upland_skm=feat.upland_skm,
                        dis_av_cms=feat.dis_av_cms,
                        ord_stra=feat.ord_stra,
                        ord_clas=feat.ord_clas,
                        ord_flow=feat.ord_flow,
                        hybas_l12=feat.hybas_l12,
                        source_dataset=feat.source_dataset,
                        source_version=feat.source_version,
                    )
                    self.session.add(river)
                    metrics.records_inserted += 1

            self.session.flush()
            logger.info(
                "HydroRIVERS batch %d-%d: processed",
                i, min(i + batch_size, len(features))
            )

        logger.info(
            "HydroRIVERS: %d inserted, %d updated",
            metrics.records_inserted, metrics.records_updated,
        )
        return metrics

    def _compute_district_crosswalks(self) -> IngestionMetrics:
        """Compute M:N spatial intersections between districts and hydrological units."""
        metrics = IngestionMetrics()
        logger.info("=== Computing District Crosswalks ===")

        # ── District ↔ Sub-Basin crosswalk ──
        logger.info("Computing district ↔ sub-basin intersections...")
        existing_dsbs = {
            (dsb.district_id, dsb.sub_basin_id): dsb
            for dsb in self.session.execute(select(DistrictSubBasin)).scalars().all()
        }

        dsb_rows = self.session.execute(
            text("""
                SELECT
                    d.id AS district_id,
                    sb.id AS sub_basin_id,
                    ST_AsText(
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_Intersection(d.geometry, sb.geometry)),
                                3
                            )
                        )
                    ) AS intersection_geom_wkt,
                    ST_Area(
                        ST_Transform(
                            ST_MakeValid(ST_Intersection(d.geometry, sb.geometry)),
                            32643
                        )
                    ) / 1e6 AS intersection_area_km2,
                    ST_Area(ST_Transform(sb.geometry, 32643)) / 1e6 AS sb_area_km2,
                    ST_Area(ST_Transform(d.geometry, 32643)) / 1e6 AS district_area_km2
                FROM districts d
                JOIN sub_basins sb ON ST_Intersects(d.geometry, sb.geometry)
                WHERE d.geometry IS NOT NULL AND sb.geometry IS NOT NULL
            """)
        ).all()

        dsb_count = 0
        for row in dsb_rows:
            intersection_area = row.intersection_area_km2 or 0.0
            if intersection_area < 0.01:
                continue

            sb_area = row.sb_area_km2 or 1.0
            d_area = row.district_area_km2 or 1.0

            pct_sb = (intersection_area / sb_area * 100.0) if sb_area > 0 else 0.0
            pct_d = (intersection_area / d_area * 100.0) if d_area > 0 else 0.0

            geom_val = (
                WKTElement(row.intersection_geom_wkt, srid=4326)
                if row.intersection_geom_wkt
                else None
            )

            existing = existing_dsbs.get((row.district_id, row.sub_basin_id))
            if existing:
                existing.intersection_geometry = geom_val
                existing.intersection_area_km2 = intersection_area
                existing.percent_of_subbasin_in_district = pct_sb
                existing.percent_of_district_in_subbasin = pct_d
                metrics.records_updated += 1
            else:
                dsb = DistrictSubBasin(
                    id=uuid.uuid4(),
                    district_id=row.district_id,
                    sub_basin_id=row.sub_basin_id,
                    intersection_geometry=geom_val,
                    intersection_area_km2=intersection_area,
                    percent_of_subbasin_in_district=pct_sb,
                    percent_of_district_in_subbasin=pct_d,
                    derivation_method="PostGIS ST_Intersection",
                    source_description="KSR-SAC districts × HydroBASINS Level-7",
                )
                self.session.add(dsb)
                metrics.records_inserted += 1
                dsb_count += 1

        self.session.flush()
        logger.info("District ↔ sub-basin: %d relationships created", dsb_count)
        metrics.records_received += dsb_count

        # ── District ↔ River Basin crosswalk ──
        logger.info("Computing district ↔ river basin intersections...")
        existing_drbs = {
            (drb.district_id, drb.river_basin_id): drb
            for drb in self.session.execute(select(DistrictRiverBasin)).scalars().all()
        }

        drb_rows = self.session.execute(
            text("""
                SELECT
                    d.id AS district_id,
                    rb.id AS river_basin_id,
                    ST_AsText(
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_Intersection(d.geometry, rb.geometry)),
                                3
                            )
                        )
                    ) AS intersection_geom_wkt,
                    ST_Area(
                        ST_Transform(
                            ST_MakeValid(ST_Intersection(d.geometry, rb.geometry)),
                            32643
                        )
                    ) / 1e6 AS intersection_area_km2,
                    ST_Area(ST_Transform(rb.geometry, 32643)) / 1e6 AS rb_area_km2,
                    ST_Area(ST_Transform(d.geometry, 32643)) / 1e6 AS district_area_km2
                FROM districts d
                JOIN river_basins rb ON ST_Intersects(d.geometry, rb.geometry)
                WHERE d.geometry IS NOT NULL AND rb.geometry IS NOT NULL
                  AND rb.intersects_karnataka = TRUE
            """)
        ).all()

        drb_count = 0
        for row in drb_rows:
            intersection_area = row.intersection_area_km2 or 0.0
            if intersection_area < 0.01:
                continue

            rb_area = row.rb_area_km2 or 1.0
            d_area = row.district_area_km2 or 1.0

            pct_rb = (intersection_area / rb_area * 100.0) if rb_area > 0 else 0.0
            pct_d = (intersection_area / d_area * 100.0) if d_area > 0 else 0.0

            geom_val = (
                WKTElement(row.intersection_geom_wkt, srid=4326)
                if row.intersection_geom_wkt
                else None
            )

            existing = existing_drbs.get((row.district_id, row.river_basin_id))
            if existing:
                existing.intersection_geometry = geom_val
                existing.intersection_area_km2 = intersection_area
                existing.percent_of_basin_in_district = pct_rb
                existing.percent_of_district_in_basin = pct_d
                metrics.records_updated += 1
            else:
                drb = DistrictRiverBasin(
                    id=uuid.uuid4(),
                    district_id=row.district_id,
                    river_basin_id=row.river_basin_id,
                    intersection_geometry=geom_val,
                    intersection_area_km2=intersection_area,
                    percent_of_basin_in_district=pct_rb,
                    percent_of_district_in_basin=pct_d,
                    derivation_method="PostGIS ST_Intersection",
                    source_description="KSR-SAC districts × CWC major basins",
                )
                self.session.add(drb)
                metrics.records_inserted += 1
                drb_count += 1

        self.session.flush()
        logger.info("District ↔ river basin: %d relationships created", drb_count)
        metrics.records_received += drb_count

        return metrics
