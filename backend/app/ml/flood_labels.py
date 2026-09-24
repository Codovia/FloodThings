"""
India Flood Inventory (IFI v3.0) Historical District x Day Flood Label Pipeline.

Transforms normalized historical flood disaster events from the India Flood Inventory
(IFI v3.0, HydroSenseLab / IMD) into validated, provenance-preserving ML labels at the
project's documented District x Day resolution.

Design Principles:
1. Grounded in Real Evidence: Labels are derived exclusively from actual IFI records.
   Zero synthetic flood events, zero fabricated missing labels, zero invented flood dates.
2. Canonical Administrative Alignment: Maps directly to the 31 authoritative KSR-SAC
   districts (KGIS codes 01-31).
3. Overlap Consolidation: When multiple IFI events impact the same district on the same date,
   they consolidate into a single District x Day target row with flood_occurrence = 1,
   preserving references to all underlying source events (sorted unique source_event_ids),
   summing casualties/displacements, and collecting unique causes and severities.
4. No Silent Negative-Label Generation: Unrecorded dates do NOT automatically become
   flood_occurrence = 0. Under the three-state labelling contract, negative labels (0) are
   only generated when an explicit, validated observation window within the authoritative
   historical archive (1969-07-14 to 2023-07-24) is provided. Outside this window, negative
   label generation is strictly rejected. By default, only evidenced positive days are output.
5. Date Anomaly Isolation: Events with inconsistent dates (start_date > end_date, e.g.
   UEI-IMD-FL-2018-0027) are flagged and isolated in audit records without expanding inverted
   date ranges, preventing date fabrication.
6. Provenance Preservation: Preserves source UEIs, LGD district codes, KGIS district codes,
   processing version, data category ('HISTORICAL_EVENT'), and quality status ('VALID').
7. Deterministic Serialization: Outputs to partitioned or single Parquet datasets with PyArrow.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date as dt_date, datetime, timedelta
import io
import logging
from pathlib import Path
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.gis.ifi import (
    IfiEventNormalizer,
    IfiNormalizationResult,
    NormalizedIfiEvent,
    NormalizedIfiObservation,
)
from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict
from app.ml.contracts import SampleLabelState

logger = logging.getLogger(__name__)

PROCESSING_VERSION: str = "3.13.0"
SOURCE_NAME: str = "India Flood Inventory (IFI v3.0)"
DATA_CATEGORY: str = "HISTORICAL_EVENT"
QUALITY_STATUS: str = "VALID"

# Authoritative IFI v3.0 temporal boundaries for Karnataka
IFI_EARLIEST_VALID_DATE: dt_date = dt_date(1969, 7, 14)
IFI_LATEST_VALID_DATE: dt_date = dt_date(2023, 7, 24)

# -----------------------------------------------------------------------------
# Data Containers
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DistrictDayFloodLabel:
    """A consolidated District x Day historical flood occurrence label."""

    kgis_district_code: str
    lgd_district_code: str
    district_name: str
    district_id: str | None
    date: str  # ISO YYYY-MM-DD
    flood_occurrence: int | None  # 1 for POSITIVE, 0 for NEGATIVE, None for UNLABELLED
    label_state: SampleLabelState
    event_count: int
    source_event_ids: list[str]
    main_causes: list[str]
    severities: list[str]
    fatalities: int | None
    displaced: int | None
    source_dataset: str = SOURCE_NAME
    data_category: str = DATA_CATEGORY
    quality_status: str = QUALITY_STATUS
    processing_version: str = PROCESSING_VERSION

    @property
    def label(self) -> str:
        """
        Categorical three-state label per Phase 3.13 specification:
        - 'FLOOD': Positive evidenced flood occurrence (flood_occurrence = 1).
        - 'NO_FLOOD': Verified absence of flood within explicit observation window (flood_occurrence = 0).
        - 'UNKNOWN': Unevidenced or outside observation window (flood_occurrence is None).
        """
        if self.flood_occurrence == 1:
            return "FLOOD"
        elif self.flood_occurrence == 0:
            return "NO_FLOOD"
        return "UNKNOWN"


@dataclass(frozen=True)
class DateAnomalyRecord:
    """Audit record for an event with invalid or inconsistent date logic."""

    uei: str
    start_date_raw: str
    end_date_raw: str | None
    duration_days: int | None
    reason: str
    affected_districts: list[str]


@dataclass(frozen=True)
class DistrictDayLabelResult:
    """Complete result of the historical District x Day flood label pipeline."""

    labels: list[DistrictDayFloodLabel]
    date_anomalies: list[DateAnomalyRecord]
    total_raw_records_received: int
    karnataka_records_filtered: int
    valid_events_processed: int
    invalid_records_rejected: int
    anomalous_events_count: int
    unresolved_events_count: int
    events_expanded_count: int
    total_unconsolidated_district_days: int
    unique_positive_district_days: int
    unique_negative_district_days: int
    unique_unlabelled_district_days: int
    earliest_date: str | None
    latest_date: str | None
    districts_represented: int


# -----------------------------------------------------------------------------
# PyArrow Schema Definition
# -----------------------------------------------------------------------------

ARROW_DISTRICT_DAY_LABEL_SCHEMA = pa.schema(
    [
        ("kgis_district_code", pa.string()),
        ("lgd_district_code", pa.string()),
        ("district_name", pa.string()),
        ("district_id", pa.string()),
        ("date", pa.string()),
        ("flood_occurrence", pa.int8()),
        ("label_state", pa.string()),
        ("event_count", pa.int32()),
        ("source_event_ids", pa.list_(pa.string())),
        ("main_causes", pa.list_(pa.string())),
        ("severities", pa.list_(pa.string())),
        ("fatalities", pa.int32()),
        ("displaced", pa.int32()),
        ("source_dataset", pa.string()),
        ("data_category", pa.string()),
        ("quality_status", pa.string()),
        ("processing_version", pa.string()),
    ]
)


# -----------------------------------------------------------------------------
# Pipeline Engine
# -----------------------------------------------------------------------------


class IfiDistrictDayLabelPipeline:
    """
    Deterministic District x Day label generator for India Flood Inventory (IFI v3.0).

    Takes raw IFI CSV data, resolves Karnataka district observations to canonical KSR-SAC
    administrative districts, expands event durations into discrete daily occurrences,
    consolidates overlapping occurrences on identical (district, date) coordinates,
    isolates date anomalies, and strictly enforces the three-state labelling contract
    preventing silent negative-label generation.
    """

    def __init__(
        self,
        ksrsac_districts: list[NormalizedDistrict] | None = None,
        district_id_map: dict[str, str] | None = None,
    ):
        """
        Initialize the label pipeline.

        Args:
            ksrsac_districts: Optional pre-normalized KSR-SAC districts.
            district_id_map: Optional mapping of KGIS district code ('01'-'31') to database UUID string.
        """
        if ksrsac_districts is not None:
            self._districts = ksrsac_districts
        else:
            admin_result = KsrsacAdminNormalizer().normalize()
            self._districts = admin_result.districts

        self.normalizer = IfiEventNormalizer(self._districts)
        self._by_kgis: dict[str, NormalizedDistrict] = {
            d.kgis_district_code.strip().zfill(2): d for d in self._districts
        }
        self._district_id_map = district_id_map or {}

    def generate_labels(
        self,
        csv_source: str | Path | io.StringIO,
        observation_start: dt_date | str | None = None,
        observation_end: dt_date | str | None = None,
        generate_negatives: bool = False,
        include_unlabelled: bool = False,
        max_records: int | None = None,
    ) -> DistrictDayLabelResult:
        """
        Generate consolidated District x Day labels from IFI source.

        Args:
            csv_source: File path, CSV text string, or StringIO.
            observation_start: Optional start date for observation window.
            observation_end: Optional end date for observation window.
            generate_negatives: If True, generate explicit negative labels (flood_occurrence=0)
                                for unevidenced district-days in the validated observation window.
                                (Requires observation_start and observation_end within 1969-2023).
            include_unlabelled: If True, generate UNLABELLED records (flood_occurrence=None)
                                for unevidenced district-days in the observation window.
            max_records: Optional maximum raw records to process.

        Returns:
            DistrictDayLabelResult with validated labels, date anomalies, and audit metrics.
        """
        # Parse observation window if provided
        start_d: dt_date | None = None
        end_d: dt_date | None = None
        if observation_start is not None:
            start_d = (
                dt_date.fromisoformat(observation_start)
                if isinstance(observation_start, str)
                else observation_start
            )
        if observation_end is not None:
            end_d = (
                dt_date.fromisoformat(observation_end)
                if isinstance(observation_end, str)
                else observation_end
            )

        # Validation: If negative labels or unlabelled generation requested, window must be defined
        if (generate_negatives or include_unlabelled) and (start_d is None or end_d is None):
            raise ValueError(
                "Negative or unlabelled label generation requires both observation_start and "
                "observation_end to be explicitly specified."
            )

        if start_d is not None and end_d is not None:
            if start_d > end_d:
                raise ValueError(
                    f"observation_start ({start_d}) cannot be after observation_end ({end_d})"
                )

            # Strict guard against false-negative generation outside validated observation window
            if generate_negatives or include_unlabelled:
                if start_d < IFI_EARLIEST_VALID_DATE or end_d > IFI_LATEST_VALID_DATE:
                    raise ValueError(
                        f"Requested observation window [{start_d}, {end_d}] extends outside "
                        f"the validated IFI historical observation bounds "
                        f"[{IFI_EARLIEST_VALID_DATE}, {IFI_LATEST_VALID_DATE}]. "
                        "Negative labels must never be generated outside verified observation periods."
                    )

        # 1. Normalize IFI records
        norm_result: IfiNormalizationResult = self.normalizer.normalize(
            csv_source, max_records=max_records
        )

        # Index observations by UEI
        obs_by_uei: dict[str, list[NormalizedIfiObservation]] = defaultdict(list)
        for obs in norm_result.observations:
            obs_by_uei[obs.uei].append(obs)

        # 2. Date expansion and anomaly isolation
        date_anomalies: list[DateAnomalyRecord] = []
        events_expanded_count = 0
        total_unconsolidated = 0

        # Map (kgis_district_code, date_iso) -> list of raw occurrence tuples
        # Tuple: (NormalizedIfiEvent, NormalizedIfiObservation)
        occurrences_by_key: dict[
            tuple[str, str], list[tuple[NormalizedIfiEvent, NormalizedIfiObservation]]
        ] = defaultdict(list)

        for event in norm_result.events:
            ev_obs_list = obs_by_uei.get(event.uei, [])
            if not ev_obs_list:
                continue

            ev_start_d = event.start_time.date()
            ev_end_d = event.end_time.date() if event.end_time is not None else ev_start_d

            # Anomaly check: start date after end date (e.g. UEI-IMD-FL-2018-0027)
            if ev_start_d > ev_end_d:
                date_anomalies.append(
                    DateAnomalyRecord(
                        uei=event.uei,
                        start_date_raw=event.start_date_raw,
                        end_date_raw=event.end_date_raw,
                        duration_days=event.duration_days,
                        reason="START_DATE_AFTER_END_DATE",
                        affected_districts=[o.district_name for o in ev_obs_list],
                    )
                )
                # Exclude from interval expansion to prevent date fabrication
                continue

            events_expanded_count += 1
            duration_days = (ev_end_d - ev_start_d).days + 1

            for day_offset in range(duration_days):
                curr_date = ev_start_d + timedelta(days=day_offset)
                date_iso = curr_date.isoformat()

                for obs in ev_obs_list:
                    total_unconsolidated += 1
                    occurrences_by_key[(obs.kgis_district_code, date_iso)].append((event, obs))

        # 3. Consolidate overlapping events on (kgis_district_code, date)
        positive_labels: dict[tuple[str, str], DistrictDayFloodLabel] = {}

        for (kgis_code, date_iso), occ_list in occurrences_by_key.items():
            first_obs = occ_list[0][1]
            ueis = sorted(list({ev.uei for ev, _ in occ_list}))
            causes = sorted(list({ev.main_cause for ev, _ in occ_list if ev.main_cause}))
            severities = sorted(list({ev.severity for ev, _ in occ_list if ev.severity}))

            # Casualties / displaced summation
            known_fatalities = [
                ev.human_fatality for ev, _ in occ_list if ev.human_fatality is not None
            ]
            total_fatalities: int | None = (
                sum(known_fatalities) if known_fatalities else None
            )

            known_displaced = [
                ev.human_displaced for ev, _ in occ_list if ev.human_displaced is not None
            ]
            total_displaced: int | None = sum(known_displaced) if known_displaced else None

            dist_id = self._district_id_map.get(kgis_code)

            positive_labels[(kgis_code, date_iso)] = DistrictDayFloodLabel(
                kgis_district_code=kgis_code,
                lgd_district_code=first_obs.lgd_district_code,
                district_name=first_obs.district_name,
                district_id=dist_id,
                date=date_iso,
                flood_occurrence=1,
                label_state=SampleLabelState.POSITIVE,
                event_count=len(ueis),
                source_event_ids=ueis,
                main_causes=causes,
                severities=severities,
                fatalities=total_fatalities,
                displaced=total_displaced,
                source_dataset=SOURCE_NAME,
                data_category=DATA_CATEGORY,
                quality_status=QUALITY_STATUS,
                processing_version=PROCESSING_VERSION,
            )

        # 4. Generate observation window background grid (negatives / unlabelled)
        final_labels: list[DistrictDayFloodLabel] = []
        negative_count = 0
        unlabelled_count = 0

        if start_d is not None and end_d is not None and (generate_negatives or include_unlabelled):
            # Deterministically iterate through all 31 KSR-SAC districts across all days in window
            total_window_days = (end_d - start_d).days + 1

            for day_offset in range(total_window_days):
                curr_date = start_d + timedelta(days=day_offset)
                date_iso = curr_date.isoformat()

                for dist in self._districts:
                    kgis_code = dist.kgis_district_code.strip().zfill(2)
                    key = (kgis_code, date_iso)

                    if key in positive_labels:
                        final_labels.append(positive_labels[key])
                    else:
                        dist_id = self._district_id_map.get(kgis_code)
                        if generate_negatives:
                            negative_count += 1
                            final_labels.append(
                                DistrictDayFloodLabel(
                                    kgis_district_code=kgis_code,
                                    lgd_district_code=dist.lgd_district_code,
                                    district_name=dist.district_name,
                                    district_id=dist_id,
                                    date=date_iso,
                                    flood_occurrence=0,
                                    label_state=SampleLabelState.NEGATIVE,
                                    event_count=0,
                                    source_event_ids=[],
                                    main_causes=[],
                                    severities=[],
                                    fatalities=0,
                                    displaced=0,
                                    source_dataset=SOURCE_NAME,
                                    data_category=DATA_CATEGORY,
                                    quality_status=QUALITY_STATUS,
                                    processing_version=PROCESSING_VERSION,
                                )
                            )
                        elif include_unlabelled:
                            unlabelled_count += 1
                            final_labels.append(
                                DistrictDayFloodLabel(
                                    kgis_district_code=kgis_code,
                                    lgd_district_code=dist.lgd_district_code,
                                    district_name=dist.district_name,
                                    district_id=dist_id,
                                    date=date_iso,
                                    flood_occurrence=None,
                                    label_state=SampleLabelState.UNLABELLED,
                                    event_count=0,
                                    source_event_ids=[],
                                    main_causes=[],
                                    severities=[],
                                    fatalities=None,
                                    displaced=None,
                                    source_dataset=SOURCE_NAME,
                                    data_category=DATA_CATEGORY,
                                    quality_status=QUALITY_STATUS,
                                    processing_version=PROCESSING_VERSION,
                                )
                            )
        else:
            # Default: Positive evidenced labels only (no silent negative labels)
            final_labels = list(positive_labels.values())

        # Sort deterministically by date, then KGIS district code
        final_labels.sort(key=lambda x: (x.date, x.kgis_district_code))

        # Compute summary metrics
        positive_dates = [r.date for r in final_labels if r.label_state == SampleLabelState.POSITIVE]
        earliest_date = min(positive_dates) if positive_dates else None
        latest_date = max(positive_dates) if positive_dates else None
        districts_covered = len({r.kgis_district_code for r in final_labels if r.label_state == SampleLabelState.POSITIVE})

        unresolved_events_count = len(
            [e for e in norm_result.events if e.uei not in obs_by_uei]
        )

        return DistrictDayLabelResult(
            labels=final_labels,
            date_anomalies=date_anomalies,
            total_raw_records_received=norm_result.raw_records_received,
            karnataka_records_filtered=norm_result.karnataka_records_filtered,
            valid_events_processed=norm_result.total_resolved_events,
            invalid_records_rejected=norm_result.invalid_records_rejected,
            anomalous_events_count=len(date_anomalies),
            unresolved_events_count=unresolved_events_count,
            events_expanded_count=events_expanded_count,
            total_unconsolidated_district_days=total_unconsolidated,
            unique_positive_district_days=len(positive_labels),
            unique_negative_district_days=negative_count,
            unique_unlabelled_district_days=unlabelled_count,
            earliest_date=earliest_date,
            latest_date=latest_date,
            districts_represented=districts_covered,
        )

    def save_parquet(
        self,
        result: DistrictDayLabelResult,
        target_path: Path | str,
        compression: str = "snappy",
    ) -> Path:
        """
        Serialize District x Day labels to Parquet using PyArrow.

        Args:
            result: DistrictDayLabelResult containing labels.
            target_path: Target .parquet file path.
            compression: Compression codec (default: 'snappy').

        Returns:
            Path to written parquet file.
        """
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        labels = result.labels
        arrays = [
            pa.array([r.kgis_district_code for r in labels], type=pa.string()),
            pa.array([r.lgd_district_code for r in labels], type=pa.string()),
            pa.array([r.district_name for r in labels], type=pa.string()),
            pa.array([r.district_id for r in labels], type=pa.string()),
            pa.array([r.date for r in labels], type=pa.string()),
            pa.array([r.flood_occurrence for r in labels], type=pa.int8()),
            pa.array(
                [
                    r.label_state.value if hasattr(r.label_state, "value") else str(r.label_state)
                    for r in labels
                ],
                type=pa.string(),
            ),
            pa.array([r.event_count for r in labels], type=pa.int32()),
            pa.array([r.source_event_ids for r in labels], type=pa.list_(pa.string())),
            pa.array([r.main_causes for r in labels], type=pa.list_(pa.string())),
            pa.array([r.severities for r in labels], type=pa.list_(pa.string())),
            pa.array([r.fatalities for r in labels], type=pa.int32()),
            pa.array([r.displaced for r in labels], type=pa.int32()),
            pa.array([r.source_dataset for r in labels], type=pa.string()),
            pa.array([r.data_category for r in labels], type=pa.string()),
            pa.array([r.quality_status for r in labels], type=pa.string()),
            pa.array([r.processing_version for r in labels], type=pa.string()),
        ]

        table = pa.Table.from_arrays(arrays, schema=ARROW_DISTRICT_DAY_LABEL_SCHEMA)

        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, delete=False, suffix=".parquet"
        ) as tf:
            pq.write_table(table, tf, compression=compression)
            temp_name = tf.name

        Path(temp_name).replace(path)
        logger.info(f"Wrote {len(labels)} district-day labels to {path}")
        return path

    @staticmethod
    def load_parquet(path: Path | str) -> pa.Table:
        """Read and validate a District x Day label Parquet file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Parquet file not found: {p}")
        table = pq.read_table(p)
        return table

    def ingest_to_db(
        self,
        session: Any,
        result: DistrictDayLabelResult,
        batch_size: int = 1000,
    ) -> int:
        """
        Persist District x Day labels into PostGIS database table district_day_flood_labels.

        Idempotent upsert matching on (district_id, event_date).
        Resolves district_id from the database if not already populated.

        Args:
            session: SQLAlchemy session.
            result: DistrictDayLabelResult containing labels to ingest.
            batch_size: Batch size for chunked execution.

        Returns:
            Number of records upserted.
        """
        import uuid as uuid_pkg
        from sqlalchemy import func
        from sqlalchemy.dialects.postgresql import insert
        from app.db.models.geography import District
        from app.db.models.flood import DistrictDayFloodLabel as DbDistrictDayFloodLabel

        # Build district UUID map
        districts = session.query(District).all()
        lgd_to_uuid = {d.code: d.id for d in districts if d.code}
        kgis_to_uuid = {
            dist.kgis_district_code.strip().zfill(2): lgd_to_uuid.get(dist.lgd_district_code)
            for dist in self._districts
            if dist.lgd_district_code in lgd_to_uuid
        }

        records_to_insert = []
        for l in result.labels:
            dist_uuid = None
            if l.district_id:
                try:
                    dist_uuid = uuid_pkg.UUID(l.district_id)
                except ValueError:
                    pass
            if dist_uuid is None:
                dist_uuid = lgd_to_uuid.get(l.lgd_district_code) or kgis_to_uuid.get(l.kgis_district_code)

            if dist_uuid is None:
                logger.warning(
                    f"Skipping label for {l.district_name} ({l.kgis_district_code}): "
                    f"could not resolve database district_id"
                )
                continue

            event_d = dt_date.fromisoformat(l.date)
            records_to_insert.append({
                "district_id": dist_uuid,
                "event_date": event_d,
                "label": l.label,
                "flood_occurrence": l.flood_occurrence,
                "event_count": l.event_count,
                "source_event_ids": l.source_event_ids,
                "main_causes": l.main_causes,
                "severities": l.severities,
                "fatalities": l.fatalities,
                "displaced": l.displaced,
                "source_id": None,
                "data_category": l.data_category,
                "quality_status": l.quality_status,
                "mapping_status": "MAPPED",
                "processing_version": l.processing_version,
            })

        if not records_to_insert:
            return 0

        total_upserted = 0
        for i in range(0, len(records_to_insert), batch_size):
            chunk = records_to_insert[i : i + batch_size]
            stmt = insert(DbDistrictDayFloodLabel).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_district_day_flood_labels",
                set_={
                    "label": stmt.excluded.label,
                    "flood_occurrence": stmt.excluded.flood_occurrence,
                    "event_count": stmt.excluded.event_count,
                    "source_event_ids": stmt.excluded.source_event_ids,
                    "main_causes": stmt.excluded.main_causes,
                    "severities": stmt.excluded.severities,
                    "fatalities": stmt.excluded.fatalities,
                    "displaced": stmt.excluded.displaced,
                    "source_id": stmt.excluded.source_id,
                    "data_category": stmt.excluded.data_category,
                    "quality_status": stmt.excluded.quality_status,
                    "mapping_status": stmt.excluded.mapping_status,
                    "processing_version": stmt.excluded.processing_version,
                    "updated_at": func.now(),
                },
            )
            session.execute(stmt)
            total_upserted += len(chunk)

        session.commit()
        logger.info(f"Successfully upserted {total_upserted} district-day flood labels into database")
        return total_upserted
