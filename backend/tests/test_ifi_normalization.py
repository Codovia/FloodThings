"""
Tests for IFI Historical Flood Event Normalization Foundation (Phase 2.7A).

Verifies:
- Valid IFI event normalization
- Provenance preservation (data_category = HISTORICAL_EVENT, quality_status = VALID)
- Deterministic district mapping against KSR-SAC verified districts
- Duplicate handling (events and observations)
- Invalid/missing dates handling
- Missing geometry explicitly remains None
- Unresolved district mapping without guessing
- Deterministic repeated normalization
- Real raw IFI archive normalization
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path

import pytest

from app.gis.ifi import (
    IfiEventNormalizer,
    IfiNormalizationResult,
    NormalizedIfiEvent,
    NormalizedIfiObservation,
    UnresolvedDistrictTokenRecord,
)
from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict

# Sample CSV with single event and multiple districts
SAMPLE_VALID_IFI_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-KA-0001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,12,5,1000,20,Casualties reported,Substantial damage to infrastructure,IMD,SRC-001,541,29
"""

SAMPLE_MULTI_DISTRICT_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-KA-0002,01-07-2019 06:00,05-07-2019 18:00,4,Monsoon Flood,,"Belagavi, Bagalkote, Vijayapura",Karnataka,,,Class 3,1200.0,3,0,500,10,Minor,Crop and road damage,IMD,SRC-002,"527, 524, 530",29
"""

SAMPLE_SPELLING_ALIASES_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-KA-0003,10-09-2020 00:00,12-09-2020 00:00,2,Heavy Rain,,"Beedar, Bagalkotee, Uttar Kashia Kannada, Chamarajanagaraa, Bijapur, Mangalore, Ramanagara",Karnataka,,,Class 1,300.0,0,0,50,0,None,Minor waterlogging,IMD,SRC-003,"None, None, None, None, 636, None, 631",29
"""

SAMPLE_OUT_OF_STATE_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-KA-0004,15-07-1969 00:00,22-07-1969 00:00,8,Floods,,"Belagavi, Kasaragod, Wayanad, Kozhikode","Karnataka, Kerala",,,Class 2,800.0,5,2,200,5,None,Houses damaged,IMD,SRC-004,"527, 558, 567, 561","29,32"
"""

SAMPLE_UNRESOLVED_TOKENS_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-KA-0005,20-08-2009 00:00,22-08-2009 00:00,2,Heavy Rain,,"Chamarajanagaraa Chikkaballapura, Mudigere, Rugi, Parts of Karnataka, Uttar Kashia",Karnataka,,,Class 1,100.0,0,0,0,0,None,Minor damage,IMD,SRC-005,"None, None, None, None, None",29
"""

SAMPLE_DUPLICATE_EVENTS_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-DUP-001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,12,5,1000,20,,Damage 1,IMD,ID1,541,29
2,UEI-DUP-001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,12,5,1000,20,,Damage 1,IMD,ID1,541,29
"""

SAMPLE_DUPLICATE_OBSERVATIONS_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-OBS-DUP-001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,"Bengaluru Urban, Bangalore Urban, Bengaluru (Urban)",Karnataka,,,Class 2,500.0,0,0,0,0,,None,IMD,ID1,"525, 525, 525",29
"""

SAMPLE_INVALID_DATES_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-BAD-DATE-1,,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,0,0,0,0,,None,IMD,ID1,541,29
2,UEI-BAD-DATE-2,NOT_A_DATE,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,0,0,0,0,,None,IMD,ID2,541,29
3,UEI-GOOD-DATE-3,15-08-2018 00:00,,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,0,0,0,0,,None,IMD,ID3,541,29
"""


class TestIfiNormalization:
    """Test suite for IfiEventNormalizer."""

    @pytest.fixture(scope="class")
    def normalizer(self) -> IfiEventNormalizer:
        """Create normalizer backed by authoritative KSR-SAC boundaries."""
        return IfiEventNormalizer()

    def test_valid_ifi_event_normalization(self, normalizer: IfiEventNormalizer):
        """Test normalization of a single valid historical flood event."""
        res = normalizer.normalize(SAMPLE_VALID_IFI_CSV)

        assert res.total_resolved_events == 1
        assert res.total_resolved_observations == 1
        assert res.invalid_records_rejected == 0
        assert res.duplicate_events_skipped == 0

        event = res.events[0]
        assert event.uei == "UEI-TEST-KA-0001"
        assert "UEI-TEST-KA-0001" in event.name
        # 15-08-2018 00:00 IST -> 14-08-2018 18:30 UTC
        assert event.start_time == datetime(2018, 8, 14, 18, 30, tzinfo=timezone.utc)
        assert event.end_time == datetime(2018, 8, 19, 18, 30, tzinfo=timezone.utc)
        assert event.duration_days == 5
        assert event.main_cause == "Heavy Rain"
        assert event.severity == "Class 2"
        assert event.affected_area_sq_km == 500.0
        assert event.human_fatality == 12
        assert event.human_displaced == 1000
        assert "Substantial damage" in event.extent_damage

        obs = res.observations[0]
        assert obs.uei == "UEI-TEST-KA-0001"
        assert obs.observation_time == event.start_time
        assert obs.kgis_district_code == "25"
        assert obs.lgd_district_code == "541"
        assert obs.district_name == "Kodagu"
        assert obs.source_record_id == "ifi_UEI-TEST-KA-0001_541"
        assert obs.flooded is True

    def test_provenance_preservation(self, normalizer: IfiEventNormalizer):
        """Verify strict provenance preservation across event and observation models."""
        res = normalizer.normalize(SAMPLE_VALID_IFI_CSV)
        event = res.events[0]
        obs = res.observations[0]

        # Event provenance
        assert event.source_name == "India Flood Inventory (IFI v3.0)"
        assert event.confidence is None  # Source publishes no confidence score; remains None per CONSTRAINTS.md
        assert event.start_date_raw == "15-08-2018 00:00"  # Original source string preserved
        assert event.raw_districts == "Kodagu"
        assert event.raw_state == "Karnataka"

        # Observation provenance
        assert obs.data_category == "HISTORICAL_EVENT"
        assert obs.quality_status == "VALID"
        assert obs.confidence is None  # Source publishes no observation confidence; remains None
        assert obs.mapping_status == "DETERMINISTIC"  # Explicitly documents deterministic KSR-SAC mapping
        assert obs.source_record_id == "ifi_UEI-TEST-KA-0001_541"

    def test_deterministic_district_mapping(self, normalizer: IfiEventNormalizer):
        """Test deterministic resolution of LGD codes, canonical names, and historical spelling variants."""
        # 1. Multi-district event with clean LGD codes
        res_multi = normalizer.normalize(SAMPLE_MULTI_DISTRICT_CSV)
        assert res_multi.total_resolved_events == 1
        assert res_multi.total_resolved_observations == 3

        resolved_lgds = {obs.lgd_district_code for obs in res_multi.observations}
        assert resolved_lgds == {"527", "524", "530"}

        # 2. Historical spelling variants and geocoding repairs
        res_aliases = normalizer.normalize(SAMPLE_SPELLING_ALIASES_CSV)
        assert res_aliases.total_resolved_events == 1
        assert res_aliases.total_resolved_observations == 7

        alias_map = {obs.district_name: (obs.kgis_district_code, obs.lgd_district_code) for obs in res_aliases.observations}
        # Beedar -> Bidar (KGIS 05, LGD 529)
        assert alias_map["Bidar"] == ("05", "529")
        # Bagalkotee -> Bagalkote (KGIS 02, LGD 524)
        assert alias_map["Bagalkote"] == ("02", "524")
        # Uttar Kashia Kannada -> Uttara Kannada (KGIS 10, LGD 550)
        assert alias_map["Uttara Kannada"] == ("10", "550")
        # Chamarajanagaraa -> Chamarajanagara (KGIS 27, LGD 531)
        assert alias_map["Chamarajanagara"] == ("27", "531")
        # Bijapur (assigned 636 in IFI) -> Vijayapura (KGIS 03, LGD 530)
        assert alias_map["Vijayapura"] == ("03", "530")
        # Mangalore -> Dakshina Kannada (KGIS 24, LGD 534)
        assert alias_map["Dakshina Kannada"] == ("24", "534")
        # Ramanagara -> Bengaluru South (KGIS 29, LGD 631)
        assert alias_map["Bengaluru South"] == ("29", "631")

    def test_out_of_state_filtering(self, normalizer: IfiEventNormalizer):
        """Verify non-Karnataka districts in multi-state events are cleanly filtered without error."""
        res = normalizer.normalize(SAMPLE_OUT_OF_STATE_CSV)
        assert res.total_resolved_events == 1
        # Only Belagavi is in Karnataka
        assert res.total_resolved_observations == 1
        assert res.observations[0].district_name == "Belagavi"
        assert res.observations[0].lgd_district_code == "527"
        # Kasaragod (558), Wayanad (567), Kozhikode (561) in Kerala are skipped
        assert res.out_of_state_tokens_skipped == 3
        assert len(res.unresolved_tokens) == 0

    def test_unresolved_district_mapping(self, normalizer: IfiEventNormalizer):
        """Verify ambiguous, concatenated, and sub-district tokens are NOT guessed and logged cleanly."""
        res = normalizer.normalize(SAMPLE_UNRESOLVED_TOKENS_CSV)
        assert res.total_resolved_events == 1
        # None should be falsely resolved
        assert res.total_resolved_observations == 0
        assert len(res.unresolved_tokens) == 5

        reasons = {u.raw_token: u.reason for u in res.unresolved_tokens}
        assert reasons["Chamarajanagaraa Chikkaballapura"] == "CONCATENATED_TOKENS"
        assert reasons["Mudigere"] == "TALUK_LEVEL_TOKEN"
        assert reasons["Rugi"] == "LOCALITY_LEVEL_TOKEN"
        assert reasons["Parts of Karnataka"] == "NON_DISTRICT_DESCRIPTOR"
        assert reasons["Uttar Kashia"] == "AMBIGUOUS_TOKEN"

    def test_duplicate_handling(self, normalizer: IfiEventNormalizer):
        """Verify idempotent deduplication of events by UEI and observations by (UEI, district)."""
        # 1. Duplicate events
        res_ev = normalizer.normalize(SAMPLE_DUPLICATE_EVENTS_CSV)
        assert res_ev.total_resolved_events == 1
        assert res_ev.duplicate_events_skipped == 1

        # 2. Duplicate district tokens in same event
        res_obs = normalizer.normalize(SAMPLE_DUPLICATE_OBSERVATIONS_CSV)
        assert res_obs.total_resolved_events == 1
        # Three tokens for Bengaluru Urban in same event -> only 1 observation
        assert res_obs.total_resolved_observations == 1
        assert res_obs.duplicate_observations_skipped == 2

    def test_invalid_and_missing_dates(self, normalizer: IfiEventNormalizer):
        """Verify unparseable or missing start dates are rejected while end dates are optional."""
        res = normalizer.normalize(SAMPLE_INVALID_DATES_CSV)
        # First 2 have invalid/missing start dates, 3rd is valid with missing end date
        assert res.total_resolved_events == 1
        assert res.invalid_records_rejected == 2

        event = res.events[0]
        assert event.uei == "UEI-GOOD-DATE-3"
        assert event.start_time is not None
        assert event.end_time is None

    def test_missing_geometry_remains_strictly_null(self, normalizer: IfiEventNormalizer):
        """Verify strict adherence to zero-fabrication constraint: geometry is None and depth is None."""
        res = normalizer.normalize(SAMPLE_VALID_IFI_CSV)
        event = res.events[0]
        obs = res.observations[0]

        assert event.geometry is None
        assert obs.geometry is None
        assert obs.flood_depth is None

    def test_deterministic_repeated_normalization(self, normalizer: IfiEventNormalizer):
        """Verify normalization is 100% deterministic across repeated runs on identical input."""
        res1 = normalizer.normalize(SAMPLE_SPELLING_ALIASES_CSV)
        res2 = normalizer.normalize(SAMPLE_SPELLING_ALIASES_CSV)

        assert res1.total_resolved_events == res2.total_resolved_events
        assert res1.total_resolved_observations == res2.total_resolved_observations
        assert len(res1.unresolved_tokens) == len(res2.unresolved_tokens)

        for obs1, obs2 in zip(res1.observations, res2.observations):
            assert obs1.source_record_id == obs2.source_record_id
            assert obs1.kgis_district_code == obs2.kgis_district_code
            assert obs1.lgd_district_code == obs2.lgd_district_code
            assert obs1.observation_time == obs2.observation_time

    def test_real_raw_ifi_archive_normalization(self, normalizer: IfiEventNormalizer):
        """Verify end-to-end normalization against the preserved real raw IFI v3 archive."""
        repo_root = Path(__file__).resolve().parents[2]
        raw_csv_path = repo_root / "data" / "raw" / "ifi" / "ifi_v3_karnataka_20260917_164914.csv"
        if not raw_csv_path.exists():
            pytest.skip("Real raw IFI v3 CSV file not available")

        res = normalizer.normalize(raw_csv_path)

        # Verified ground truth counts for Karnataka in IFI v3
        assert res.raw_records_received == 6876
        assert res.karnataka_records_filtered == 494
        assert res.total_resolved_events == 493  # 1 record has empty start date
        assert res.invalid_records_rejected == 1
        assert res.total_resolved_observations == 1271
        assert len(res.unresolved_tokens) == 31
        assert res.out_of_state_tokens_skipped == 35
        assert res.duplicate_events_skipped == 0
        assert res.duplicate_observations_skipped == 7

        # Ensure all observations carry valid KSR-SAC codes, explicit None geometry, and clean confidence
        for obs in res.observations:
            assert obs.geometry is None
            assert obs.flood_depth is None
            assert obs.confidence is None  # Source confidence is unprovided by IFI
            assert obs.mapping_status == "DETERMINISTIC"
            assert obs.data_category == "HISTORICAL_EVENT"
            assert obs.quality_status == "VALID"
            assert 1 <= int(obs.kgis_district_code) <= 31
            assert obs.lgd_district_code is not None
            assert obs.source_record_id.startswith("ifi_UEI-")
