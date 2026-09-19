"""
Controlled Database Correction for District Codes and River Station (Phase 3.4B - Part B).

Performs a deterministic, atomic correction:
1. Updates all 31 districts.code values to their authoritative Government of India LGD codes.
2. Preserves 100% of district UUIDs (districts.id).
3. Corrects river_stations for AKKIHEBBAL: updates district_id from Koppal UUID to Mandya UUID.
4. Preserves 100% of river_observations rows and their station_id foreign keys.
5. Executes inside a single atomic database transaction with full rollback capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.geography import District
from app.db.models.hydrology import RiverObservation, RiverStation
from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict
from app.ingestion.sources.ksrsac_gis import KSR_TO_DB_DISTRICT_NAMES


@dataclass(frozen=True)
class CorrectionResult:
    """Summary of changes executed in the controlled correction transaction."""

    executed_at: str
    districts_updated_count: int
    river_stations_updated_count: int
    district_uuids_preserved: bool
    akkihebbal_new_district_name: str
    akkihebbal_new_district_code: str
    river_observations_count_intact: int
    transaction_committed: bool


class ControlledDistrictCorrector:
    """
    Executes atomic correction of district codes and AKKIHEBBAL station association.
    """

    def __init__(self, session: Session):
        self._session = session

    def execute_correction(self, dry_run: bool = False) -> CorrectionResult:
        """
        Execute atomic correction of districts.code and river_stations.district_id.

        Args:
            dry_run: If True, executes all statements and rolls back instead of committing.

        Returns:
            CorrectionResult summarizing the outcome.
        """
        # 1. Fetch authoritative KSR-SAC / LGD mappings
        norm = KsrsacAdminNormalizer().normalize()
        ksr_by_name = {d.district_name: d for d in norm.districts}

        db_districts = list(self._session.execute(select(District)).scalars().all())
        assert len(db_districts) == 31, f"Expected 31 districts, found {len(db_districts)}"

        # Build mapping: district_id -> authoritative_lgd_code
        auth_code_by_id: dict[UUID, str] = {}
        mandya_uuid: UUID | None = None
        koppal_uuid: UUID | None = None

        for d in db_districts:
            ksr_match = None
            for ksr_name, mapped_db_name in KSR_TO_DB_DISTRICT_NAMES.items():
                if mapped_db_name == d.name:
                    ksr_match = ksr_by_name.get(ksr_name)
                    break
            if not ksr_match:
                ksr_match = ksr_by_name.get(d.name)

            assert ksr_match is not None, f"No KSR-SAC match found for '{d.name}'"
            auth_code_by_id[d.id] = ksr_match.lgd_district_code

            if d.name == "Mandya":
                mandya_uuid = d.id
            elif d.name == "Koppal":
                koppal_uuid = d.id

        assert mandya_uuid is not None, "Mandya UUID not found"
        assert koppal_uuid is not None, "Koppal UUID not found"

        # Capture counts before
        obs_count_before = self._session.execute(
            select(func.count()).select_from(RiverObservation)
        ).scalar() or 0

        # Step 2: Update districts.code
        # To avoid transient unique constraint collision on districts_code_key during intermediate rows,
        # we assign temporary codes then set final authoritative codes.
        for d in db_districts:
            d.code = f"TMP_{d.id.hex[:8]}"
        self._session.flush()

        districts_updated = 0
        for d in db_districts:
            target_code = auth_code_by_id[d.id]
            d.code = target_code
            districts_updated += 1
        self._session.flush()

        # Step 3: Update AKKIHEBBAL river station
        rs_stmt = select(RiverStation).where(RiverStation.station_code == "AKKIHEBBAL")
        rs = self._session.execute(rs_stmt).scalar_one()
        rs.district_id = mandya_uuid
        self._session.flush()

        # Step 4: Validate in-transaction invariants
        # District count still 31
        dist_count = self._session.execute(select(func.count()).select_from(District)).scalar()
        assert dist_count == 31, f"Expected 31 districts, found {dist_count}"

        # AKKIHEBBAL district is Mandya
        mandya_row = self._session.execute(select(District).where(District.id == mandya_uuid)).scalar_one()
        assert rs.district_id == mandya_uuid
        assert mandya_row.code == "544", f"Expected Mandya code 544, found {mandya_row.code}"

        # 101 river observations still intact
        obs_count_after = self._session.execute(
            select(func.count()).select_from(RiverObservation)
        ).scalar() or 0
        assert obs_count_after == obs_count_before == 101, (
            f"Observation count changed from {obs_count_before} to {obs_count_after}"
        )

        if dry_run:
            self._session.rollback()
            committed = False
        else:
            self._session.commit()
            committed = True

        return CorrectionResult(
            executed_at=datetime.now(timezone.utc).isoformat(),
            districts_updated_count=districts_updated,
            river_stations_updated_count=1,
            district_uuids_preserved=True,
            akkihebbal_new_district_name="Mandya",
            akkihebbal_new_district_code="544",
            river_observations_count_intact=obs_count_after,
            transaction_committed=committed,
        )


if __name__ == "__main__":
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    with factory() as session:
        corrector = ControlledDistrictCorrector(session)
        # Test dry-run first
        res = corrector.execute_correction(dry_run=True)
        print("Dry run result:", res)
