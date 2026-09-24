"""
Tests for IFI Historical Flood District x Day Label Pipeline (Phase 3.13).

Verifies:
1. District normalization (canonical KSR-SAC 31 districts, alias resolution)
2. Duplicate event handling (idempotent event deduplication)
3. Overlapping flood events (consolidation to single row, list of UEIs, casualty sum)
4. Date expansion (inclusive daily expansion, duration alignment)
5. District x Day uniqueness (strictly unique (kgis_district_code, date) keys)
6. Missing district handling (unresolved/unmapped tokens not guessed)
7. Missing date handling and anomaly isolation (start > end isolated)
8. Provenance preservation (UEIs, LGD codes, data_category, quality_status)
9. No synthetic events (every positive label traces to real IFI UEI)
10. No silent negative-label generation (unrecorded days not silently zero-filled)
11. Deterministic output (identical output across repeated runs)
12. Real raw IFI archive integration test (exact ground truth reconciliation)
13. Parquet serialization and schema integrity roundtrip
"""

from __future__ import annotations

from datetime import date as dt_date, datetime, timezone
import io
from pathlib import Path
import tempfile

import pyarrow as pa
import pytest

from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict
from app.ml.contracts import SampleLabelState
from app.ml.flood_labels import (
    ARROW_DISTRICT_DAY_LABEL_SCHEMA,
    DateAnomalyRecord,
    DistrictDayFloodLabel,
    DistrictDayLabelResult,
    IFI_EARLIEST_VALID_DATE,
    IFI_LATEST_VALID_DATE,
    IfiDistrictDayLabelPipeline,
)

# -----------------------------------------------------------------------------
# Test Fixtures & Samples
# -----------------------------------------------------------------------------

SAMPLE_MULTI_DAY_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-EXP-001,10-08-2018 00:00,12-08-2018 00:00,3,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,5,2,100,10,Casualties,Damage,IMD,SRC-01,541,29
"""

SAMPLE_OVERLAPPING_EVENTS_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-OVL-001,10-08-2019 00:00,11-08-2019 00:00,2,Monsoon Flood,,Belagavi,Karnataka,,,Class 2,300.0,3,0,50,0,,Damage 1,IMD,ID-1,527,29
2,UEI-OVL-002,11-08-2019 00:00,12-08-2019 00:00,2,Dam Breach,,Belagavi,Karnataka,,,Class 3,700.0,4,1,200,5,,Damage 2,IMD,ID-2,527,29
"""

SAMPLE_DUPLICATE_EVENTS_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-DUP-001,15-08-2018 00:00,17-08-2018 00:00,3,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,2,0,50,0,,Damage,IMD,ID-1,541,29
2,UEI-DUP-001,15-08-2018 00:00,17-08-2018 00:00,3,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,2,0,50,0,,Damage,IMD,ID-1,541,29
"""

SAMPLE_DATE_ANOMALY_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-ANOM-001,20-12-2018 00:00,10-06-2018 00:00,3,Heavy Rain,,Chikkamagaluru,Karnataka,,,Class 1,,0,0,0,0,,Damage,IMD,ID-1,532,29
2,UEI-VALID-002,15-08-2018 00:00,15-08-2018 00:00,1,Heavy Rain,,Kodagu,Karnataka,,,Class 2,,1,0,10,0,,Damage,IMD,ID-2,541,29
"""

SAMPLE_MISSING_DATES_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-NO-START,,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,,,,,,,Damage,IMD,ID-1,541,29
2,UEI-BAD-START,INVALID_DATE,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,,,,,,,Damage,IMD,ID-2,541,29
3,UEI-NO-END,15-08-2018 00:00,,1,Heavy Rain,,Kodagu,Karnataka,,,Class 2,,0,0,0,0,,Damage,IMD,ID-3,541,29
"""

SAMPLE_ALIASES_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-ALIAS-001,01-08-2020 00:00,01-08-2020 00:00,1,Floods,,"Beedar, Bagalkotee, Uttar Kashia Kannada, Bijapur, Mangalore",Karnataka,,,Class 1,,0,0,0,0,,Damage,IMD,ID-1,"None, None, None, 636, None",29
"""


@pytest.fixture(scope="module")
def ksrsac_districts() -> list[NormalizedDistrict]:
    """Load canonical KSR-SAC districts."""
    return KsrsacAdminNormalizer().normalize().districts


@pytest.fixture(scope="module")
def pipeline(ksrsac_districts: list[NormalizedDistrict]) -> IfiDistrictDayLabelPipeline:
    """Initialize pipeline instance with KSR-SAC districts."""
    return IfiDistrictDayLabelPipeline(ksrsac_districts)


# -----------------------------------------------------------------------------
# Test Suite
# -----------------------------------------------------------------------------


class TestIfiDistrictDayLabelPipeline:
    """Test suite for IfiDistrictDayLabelPipeline."""

    def test_district_normalization(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 1: Verify correct normalization against canonical 31 districts and aliases."""
        res = pipeline.generate_labels(SAMPLE_ALIASES_CSV)
        assert res.unique_positive_district_days == 5

        dist_codes = {r.kgis_district_code for r in res.labels}
        # Beedar -> Bidar (05), Bagalkotee -> Bagalkote (02), Uttar Kashia Kannada -> Uttara Kannada (10)
        # Bijapur (LGD 636) -> Vijayapura (03), Mangalore -> Dakshina Kannada (24)
        expected_codes = {"05", "02", "10", "03", "24"}
        assert dist_codes == expected_codes

        # Vijayanagara (31) must never be manufactured
        assert "31" not in dist_codes

    def test_duplicate_event_handling(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 2: Verify duplicate event rows are deduplicated and do not inflate label counts."""
        res = pipeline.generate_labels(SAMPLE_DUPLICATE_EVENTS_CSV)
        assert res.valid_events_processed == 1
        assert res.events_expanded_count == 1
        assert res.unique_positive_district_days == 3  # 15th, 16th, 17th August

    def test_overlapping_flood_events(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """
        Requirement 3: Verify multiple events on the same (district, date) consolidate into
        a single target row with flood_occurrence=1, preserving all UEIs and summing casualties.
        """
        res = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)

        # Event 1: 10-08-2019 to 11-08-2019 IST -> UTC: 2019-08-09 to 2019-08-10
        # Event 2: 11-08-2019 to 12-08-2019 IST -> UTC: 2019-08-10 to 2019-08-11
        # Days generated (in UTC):
        # - 2019-08-09: 1 event (UEI-OVL-001)
        # - 2019-08-10: 2 overlapping events (UEI-OVL-001, UEI-OVL-002) -> CONSOLIDATED
        # - 2019-08-11: 1 event (UEI-OVL-002)
        assert res.unique_positive_district_days == 3
        assert len(res.labels) == 3

        labels_by_date = {r.date: r for r in res.labels}

        # Check overlapping date: 2019-08-10 (UTC)
        overlap_label = labels_by_date["2019-08-10"]
        assert overlap_label.kgis_district_code == "01"
        assert overlap_label.flood_occurrence == 1
        assert overlap_label.label_state == SampleLabelState.POSITIVE
        assert overlap_label.event_count == 2
        assert overlap_label.source_event_ids == ["UEI-OVL-001", "UEI-OVL-002"]
        assert overlap_label.fatalities == 7  # 3 + 4
        assert overlap_label.displaced == 250  # 50 + 200
        assert set(overlap_label.main_causes) == {"Monsoon Flood", "Dam Breach"}
        assert set(overlap_label.severities) == {"Class 2", "Class 3"}

    def test_date_expansion(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 4: Verify start and end dates expand to inclusive discrete calendar days."""
        res = pipeline.generate_labels(SAMPLE_MULTI_DAY_CSV)

        # 10-08-2018 00:00 to 12-08-2018 00:00 IST -> UTC dates 2018-08-09 to 2018-08-11 (3 days)
        assert res.unique_positive_district_days == 3
        dates = [r.date for r in res.labels]
        assert dates == ["2018-08-09", "2018-08-10", "2018-08-11"]
        for r in res.labels:
            assert r.flood_occurrence == 1
            assert r.kgis_district_code == "25"  # Kodagu
            assert r.source_event_ids == ["UEI-EXP-001"]

    def test_district_day_uniqueness(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 5: Verify strictly unique (district, date) pairs in output."""
        res = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)
        keys = [(r.kgis_district_code, r.date) for r in res.labels]
        assert len(keys) == len(set(keys))

    def test_missing_district_handling(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 6: Verify unmapped/unresolved district tokens are never guessed or manufactured."""
        sample_unresolved = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-UNRES-001,01-08-2020 00:00,02-08-2020 00:00,2,Floods,,Parts of Karnataka,Karnataka,,,Class 1,,0,0,0,0,,Damage,IMD,ID-1,None,29
"""
        res = pipeline.generate_labels(sample_unresolved)
        # Event has no resolvable district -> cannot be expanded
        assert res.unique_positive_district_days == 0
        assert res.unresolved_events_count == 1
        assert res.events_expanded_count == 0

    def test_missing_date_handling_and_anomaly_isolation(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """Requirement 7: Verify missing dates are rejected and date anomalies (start > end) are isolated."""
        # 1. Missing / invalid start date
        res_missing = pipeline.generate_labels(SAMPLE_MISSING_DATES_CSV)
        assert res_missing.invalid_records_rejected == 2
        assert res_missing.valid_events_processed == 1  # The one with missing end date
        assert res_missing.unique_positive_district_days == 1

        # 2. Date anomaly (start date after end date: 20-12-2018 > 10-06-2018)
        res_anom = pipeline.generate_labels(SAMPLE_DATE_ANOMALY_CSV)
        assert res_anom.anomalous_events_count == 1
        assert res_anom.events_expanded_count == 1  # Only the valid event
        assert len(res_anom.date_anomalies) == 1
        anom = res_anom.date_anomalies[0]
        assert anom.uei == "UEI-ANOM-001"
        assert anom.reason == "START_DATE_AFTER_END_DATE"
        assert "Chikkamagaluru" in anom.affected_districts

    def test_provenance_preservation(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 8: Verify complete semantic provenance across all label fields."""
        res = pipeline.generate_labels(SAMPLE_MULTI_DAY_CSV)
        label = res.labels[0]

        assert label.source_dataset == "India Flood Inventory (IFI v3.0)"
        assert label.data_category == "HISTORICAL_EVENT"
        assert label.quality_status == "VALID"
        assert label.processing_version == "3.13.0"
        assert label.source_event_ids == ["UEI-EXP-001"]
        assert label.kgis_district_code == "25"
        assert label.lgd_district_code == "541"
        assert label.district_name == "Kodagu"

    def test_no_synthetic_events(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 9: Verify every positive label traces back to real IFI source event UEIs."""
        res = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)
        for label in res.labels:
            if label.label_state == SampleLabelState.POSITIVE:
                assert label.flood_occurrence == 1
                assert len(label.source_event_ids) >= 1
                for uei in label.source_event_ids:
                    assert uei.startswith("UEI-")

    def test_no_silent_negative_label_generation(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """
        Requirement 10: Verify absence of an IFI event does NOT silently generate negative labels.
        Negative labels must only be generated when explicitly requested with a valid observation window.
        """
        # Default run: Positive only
        res = pipeline.generate_labels(SAMPLE_MULTI_DAY_CSV)
        assert res.unique_negative_district_days == 0
        assert res.unique_unlabelled_district_days == 0
        for r in res.labels:
            assert r.flood_occurrence == 1
            assert r.label_state == SampleLabelState.POSITIVE

        # Missing window when negatives requested must raise ValueError
        with pytest.raises(ValueError, match="requires both observation_start and observation_end"):
            pipeline.generate_labels(SAMPLE_MULTI_DAY_CSV, generate_negatives=True)

        # Window outside verified historical observation bounds must raise ValueError
        with pytest.raises(ValueError, match="extends outside the validated IFI historical observation bounds"):
            pipeline.generate_labels(
                SAMPLE_MULTI_DAY_CSV,
                observation_start="1960-01-01",
                observation_end="1960-12-31",
                generate_negatives=True,
            )

    def test_deterministic_output(self, pipeline: IfiDistrictDayLabelPipeline) -> None:
        """Requirement 11: Repeated execution on identical input produces identical output."""
        res1 = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)
        res2 = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)

        assert len(res1.labels) == len(res2.labels)
        for l1, l2 in zip(res1.labels, res2.labels):
            assert l1 == l2

    def test_observation_window_three_state_generation(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """Verify three-state labelling contract within an explicit observation window."""
        # Multi-day sample in Kodagu: 2018-08-09 to 2018-08-11 UTC (3 days)
        # Window: 2018-08-09 to 2018-08-13 (5 days across 31 districts = 155 district-days)
        window_start = "2018-08-09"
        window_end = "2018-08-13"

        # 1. Unlabelled mode (default three-state)
        res_unlab = pipeline.generate_labels(
            SAMPLE_MULTI_DAY_CSV,
            observation_start=window_start,
            observation_end=window_end,
            include_unlabelled=True,
        )
        assert len(res_unlab.labels) == 155
        pos_labels = [r for r in res_unlab.labels if r.label_state == SampleLabelState.POSITIVE]
        unlab_labels = [r for r in res_unlab.labels if r.label_state == SampleLabelState.UNLABELLED]
        assert len(pos_labels) == 3
        assert len(unlab_labels) == 152
        for r in unlab_labels:
            assert r.flood_occurrence is None
            assert r.event_count == 0

        # 2. Explicit negative mode
        res_neg = pipeline.generate_labels(
            SAMPLE_MULTI_DAY_CSV,
            observation_start=window_start,
            observation_end=window_end,
            generate_negatives=True,
        )
        assert len(res_neg.labels) == 155
        neg_labels = [r for r in res_neg.labels if r.label_state == SampleLabelState.NEGATIVE]
        assert len(neg_labels) == 152
        for r in neg_labels:
            assert r.flood_occurrence == 0
            assert r.event_count == 0

    def test_parquet_serialization_roundtrip(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """Requirement 13: Verify PyArrow Parquet serialization and exact roundtrip integrity."""
        res = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)

        with tempfile.TemporaryDirectory() as td:
            target_path = Path(td) / "test_labels.parquet"
            out_file = pipeline.save_parquet(res, target_path)

            assert out_file.exists()
            assert out_file.stat().st_size > 0

            table = pipeline.load_parquet(out_file)
            assert len(table) == len(res.labels)
            assert table.schema == ARROW_DISTRICT_DAY_LABEL_SCHEMA

            # Verify list column contents
            sources = table.column("source_event_ids").to_pylist()
            causes = table.column("main_causes").to_pylist()
            severities = table.column("severities").to_pylist()

            # Date 2019-08-11 has 2 overlapping events
            assert ["UEI-OVL-001", "UEI-OVL-002"] in sources
            assert ["Dam Breach", "Monsoon Flood"] in causes


# -----------------------------------------------------------------------------
# Real Archive Integration Tests
# -----------------------------------------------------------------------------


    def test_three_state_label_property(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """Verify .label property strictly maps to 'FLOOD', 'NO_FLOOD', 'UNKNOWN'."""
        res = pipeline.generate_labels(
            SAMPLE_MULTI_DAY_CSV,
            observation_start="2018-08-09",
            observation_end="2018-08-11",
            include_unlabelled=True,
        )
        pos = [l for l in res.labels if l.flood_occurrence == 1]
        unlab = [l for l in res.labels if l.flood_occurrence is None]
        assert len(pos) == 3
        for l in pos:
            assert l.label == "FLOOD"
        for l in unlab:
            assert l.label == "UNKNOWN"

        res_neg = pipeline.generate_labels(
            SAMPLE_MULTI_DAY_CSV,
            observation_start="2018-08-09",
            observation_end="2018-08-11",
            generate_negatives=True,
        )
        neg = [l for l in res_neg.labels if l.flood_occurrence == 0]
        for l in neg:
            assert l.label == "NO_FLOOD"


# -----------------------------------------------------------------------------
# Real Archive Integration Tests
# -----------------------------------------------------------------------------


class TestIfiRealArchiveIntegration:
    """Integration test suite executing against preserved raw IFI v3 archive."""

    REPO_ROOT = Path(__file__).resolve().parents[2]
    REAL_ARCHIVE_PATH = REPO_ROOT / "data" / "raw" / "ifi" / "ifi_v3_karnataka_20260917_164914.csv"

    def test_real_raw_ifi_archive_label_generation(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """
        Requirement 12: End-to-end integration test verifying ground truth numbers from
        the authoritative India Flood Inventory v3.0 archive for Karnataka.
        """
        if not self.REAL_ARCHIVE_PATH.exists():
            pytest.skip("Real raw IFI v3 CSV file not available")

        res = pipeline.generate_labels(self.REAL_ARCHIVE_PATH)

        # Ground truth counts from real IFI archive
        assert res.total_raw_records_received == 6876
        assert res.karnataka_records_filtered == 494
        assert res.valid_events_processed == 493
        assert res.invalid_records_rejected == 1  # UEI-IMD-FL-2001-0043 (empty start date)
        assert res.anomalous_events_count == 1  # UEI-IMD-FL-2018-0027 (start > end)
        assert res.unresolved_events_count == 10  # 10 events with unmapped/empty/out-of-state tokens
        assert res.events_expanded_count == 482  # 493 - 10 - 1 = 482
        assert res.total_unconsolidated_district_days == 43022
        assert res.unique_positive_district_days == 17501
        assert res.unique_negative_district_days == 0
        assert res.unique_unlabelled_district_days == 0

        # Exact temporal boundaries
        assert res.earliest_date == "1969-07-14"
        assert res.latest_date == "2023-07-24"

        # Spatial boundaries: exactly 30 districts have positive flood evidence
        # Vijayanagara (31) has zero records in IFI v3.0
        assert res.districts_represented == 30
        distinct_kgis = {r.kgis_district_code for r in res.labels}
        assert len(distinct_kgis) == 30
        assert "31" not in distinct_kgis

        # Verify all positive records adhere to invariants
        for label in res.labels:
            assert label.flood_occurrence == 1
            assert label.label == "FLOOD"
            assert label.label_state == SampleLabelState.POSITIVE
            assert label.event_count >= 1
            assert len(label.source_event_ids) == label.event_count
            assert label.source_dataset == "India Flood Inventory (IFI v3.0)"
            assert label.data_category == "HISTORICAL_EVENT"
            assert label.quality_status == "VALID"
            assert label.processing_version == "3.13.0"
            assert 1 <= int(label.kgis_district_code) <= 30
            assert IFI_EARLIEST_VALID_DATE <= dt_date.fromisoformat(label.date) <= IFI_LATEST_VALID_DATE


# -----------------------------------------------------------------------------
# Database Integration Tests
# -----------------------------------------------------------------------------


class TestIfiDbIntegration:
    """Integration test suite verifying database ingestion and constraints."""

    def test_db_ingestion_and_idempotency(
        self, pipeline: IfiDistrictDayLabelPipeline
    ) -> None:
        """Verify labels are ingested into district_day_flood_labels and re-running is idempotent."""
        from app.db.session import _get_session_factory
        from app.db.models.flood import DistrictDayFloodLabel as DbDistrictDayFloodLabel
        from app.db.models.geography import District

        session_factory = _get_session_factory()
        with session_factory() as session:
            # Check if districts exist
            dist_count = session.query(District).count()
            if dist_count == 0:
                pytest.skip("Districts table not populated in DB")

            # Generate labels from sample
            res = pipeline.generate_labels(SAMPLE_OVERLAPPING_EVENTS_CSV)
            assert len(res.labels) == 3

            # Ingest to DB
            upserted_first = pipeline.ingest_to_db(session, res)
            assert upserted_first == 3

            # Query DB
            db_records = (
                session.query(DbDistrictDayFloodLabel)
                .filter(DbDistrictDayFloodLabel.processing_version == "3.13.0")
                .all()
            )
            assert len(db_records) >= 3

            # Verify idempotency on second run
            upserted_second = pipeline.ingest_to_db(session, res)
            assert upserted_second == 3

            # Clean up test rows
            for uei in ["UEI-OVL-001", "UEI-OVL-002"]:
                session.query(DbDistrictDayFloodLabel).filter(
                    DbDistrictDayFloodLabel.source_event_ids.contains([uei])
                ).delete(synchronize_session=False)
            session.commit()
