"""
Tests for IFI Historical Flood Evidence Audit (Phase 2.7B).

Verifies the deterministic, in-memory audit of normalized IFI historical flood evidence
against the verified KSR-SAC administrative GIS foundation:
1. Complete 31-district coverage table (sorted by KGIS code)
2. Districts with zero evidence (Vijayanagara explicitly 0)
3. Yearly aggregation (unique events, observations, affected districts)
4. Earliest and latest event dates
5. Unique event counting
6. Unique district-event pair counting
7. Unresolved-token aggregation (token, reason, count, affected events)
8. Direct-vs-alias-vs-Bijapur recovery breakdown
9. Deterministic repeated audit
10. Raw source preservation (no mutation)
11. No fabricated geometry, depth, or confidence
12. Empty and minimal input behavior
13. Real IFI archive integration audit
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
from app.gis.ifi_audit import (
    AuditQualityMetrics,
    DistrictCoverageRecord,
    IfiEvidenceAuditReport,
    IfiEvidenceAuditor,
    UnresolvedTokenSummary,
    YearlyCoverageRecord,
)
from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict


# Sample minimal CSV for unit testing audit engine
SAMPLE_AUDIT_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
1,UEI-TEST-001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,,,Class 2,500.0,12,5,1000,20,,Damage 1,IMD,ID1,541,29
2,UEI-TEST-002,01-07-2019 06:00,05-07-2019 18:00,4,Monsoon Flood,,"Belagavi, Bagalkote, Vijayapura",Karnataka,,,Class 3,1200.0,3,0,500,10,,Damage 2,IMD,ID2,"527, 524, 530",29
3,UEI-TEST-003,10-09-2020 00:00,12-09-2020 00:00,2,Heavy Rain,,"Beedar, Bagalkotee, Chamarajanagaraa, Bijapur",Karnataka,,,Class 1,300.0,0,0,50,0,,Damage 3,IMD,ID3,"None, None, None, 636",29
4,UEI-TEST-004,20-08-2009 00:00,22-08-2009 00:00,2,Heavy Rain,,"Mudigere, Rugi",Karnataka,,,Class 1,100.0,0,0,0,0,,Damage 4,IMD,ID4,"None, None",29
"""


@pytest.fixture(scope="module")
def ksrsac_districts() -> list[NormalizedDistrict]:
    """Load authoritative KSR-SAC districts."""
    normalizer = KsrsacAdminNormalizer()
    return normalizer.normalize().districts


@pytest.fixture(scope="module")
def auditor(ksrsac_districts: list[NormalizedDistrict]) -> IfiEvidenceAuditor:
    """Initialize audit engine with KSR-SAC districts."""
    return IfiEvidenceAuditor(ksrsac_districts)


class TestIfiEvidenceAuditor:
    """Test suite for IfiEvidenceAuditor."""

    def test_complete_31_district_coverage_table(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 1: Verify all 31 KSR-SAC districts appear in the coverage table, sorted by KGIS code."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        assert len(report.district_coverage) == 31

        # Must be strictly sorted by KGIS code 01 to 31
        kgis_codes = [r.kgis_district_code for r in report.district_coverage]
        expected_codes = [str(i).zfill(2) for i in range(1, 32)]
        assert kgis_codes == expected_codes

        # Every record must match authoritative KSR-SAC attributes
        ksrsac_by_kgis = {d.kgis_district_code.strip().zfill(2): d for d in ksrsac_districts}
        for r in report.district_coverage:
            expected_d = ksrsac_by_kgis[r.kgis_district_code]
            assert r.district_name == expected_d.district_name
            assert r.lgd_district_code == expected_d.lgd_district_code

    def test_districts_with_zero_evidence(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 2: Districts without evidence must explicitly remain zero without manufactured coverage."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        # In SAMPLE_AUDIT_CSV, Vijayanagara (KGIS 31) has no events
        vijayanagara_rec = next(r for r in report.district_coverage if r.kgis_district_code == "31")
        assert vijayanagara_rec.district_name == "Vijayanagara"
        assert vijayanagara_rec.unique_events == 0
        assert vijayanagara_rec.district_observations == 0
        assert vijayanagara_rec.first_event_date is None
        assert vijayanagara_rec.last_event_date is None
        assert vijayanagara_rec.has_evidence is False

        assert report.metrics.districts_without_evidence > 0
        assert report.metrics.districts_with_evidence + report.metrics.districts_without_evidence == 31

    def test_yearly_aggregation(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 3: Verify yearly coverage aggregation from actual event dates."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        yearly_dict = {y.year: y for y in report.yearly_coverage}

        # SAMPLE_AUDIT_CSV contains events in 2009, 2018, 2019, 2020
        assert 2018 in yearly_dict
        assert yearly_dict[2018].unique_events == 1
        assert yearly_dict[2018].district_observations == 1
        assert yearly_dict[2018].districts_affected == 1

        assert 2019 in yearly_dict
        assert yearly_dict[2019].unique_events == 1
        assert yearly_dict[2019].district_observations == 3
        assert yearly_dict[2019].districts_affected == 3

        # Years between 2009 and 2018 with zero events must appear in years_with_zero_records
        for y in range(2010, 2018):
            assert y in report.years_with_zero_records

    def test_earliest_and_latest_dates(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 4: Earliest and latest event dates calculated directly from source records."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        assert report.earliest_event_date == "2009-08-19" or report.earliest_event_date == "2009-08-20"
        assert report.latest_event_date == "2020-09-09" or report.latest_event_date == "2020-09-10"

    def test_unique_event_counting(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 5: Unique event counting derives strictly from valid normalized events."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        assert report.metrics.total_unique_events == 4
        assert report.metrics.valid_events == 4
        assert report.metrics.raw_records == 4

    def test_unique_district_event_counting(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 6: Unique district-event pairs match normalized observations."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        # Event 1: Kodagu (1)
        # Event 2: Belagavi, Bagalkote, Vijayapura (3)
        # Event 3: Beedar (alias), Bagalkotee (alias), Chamarajanagaraa (alias), Bijapur (correction) -> 4
        # Event 4: Mudigere (taluk), Rugi (locality) -> 0 observations
        # Total observations = 1 + 3 + 4 = 8
        assert report.metrics.normalized_observations == 8
        assert report.metrics.total_unique_district_event_pairs == 8

    def test_unresolved_token_aggregation(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 7: Unresolved tokens aggregated with reason and occurrence/event counts."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        unresolved_map = {u.raw_token: u for u in report.unresolved_tokens}

        assert "Mudigere" in unresolved_map
        assert unresolved_map["Mudigere"].reason == "TALUK_LEVEL_TOKEN"
        assert unresolved_map["Mudigere"].occurrence_count == 1
        assert unresolved_map["Mudigere"].affected_event_count == 1

        assert "Rugi" in unresolved_map
        assert unresolved_map["Rugi"].reason == "LOCALITY_LEVEL_TOKEN"
        assert unresolved_map["Rugi"].occurrence_count == 1
        assert unresolved_map["Rugi"].affected_event_count == 1

        # Invariant 1: unresolved occurrence counts equal sum of unresolved token records
        total_occurrences = sum(u.occurrence_count for u in report.unresolved_tokens)
        assert total_occurrences == len(norm_result.unresolved_tokens)
        assert total_occurrences == report.metrics.unresolved_tokens

        # Invariant 2: distinct unresolved strings equal number of aggregation records
        assert len(report.unresolved_tokens) == report.metrics.distinct_unresolved_strings
        assert len(report.unresolved_tokens) == len({u.raw_token for u in norm_result.unresolved_tokens})

    def test_recovery_breakdown_metrics(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 8: Report direct LGD vs verified alias vs Bijapur recovery counts."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        # Event 1: Kodagu (541) -> Direct LGD (1)
        # Event 2: Belagavi (527), Bagalkote (524), Vijayapura (530) -> Direct LGD (3)
        # Event 3: Beedar (alias), Bagalkotee (alias), Chamarajanagaraa (alias) -> Verified Alias (3)
        # Event 3: Bijapur (636) -> Bijapur Correction (1)
        assert report.metrics.resolved_by_direct_lgd == 4
        assert report.metrics.resolved_by_verified_alias == 3
        assert report.metrics.resolved_by_bijapur_correction == 1
        # Invariant 3: resolution-method counts sum to normalized observations
        assert (
            report.metrics.resolved_by_direct_lgd
            + report.metrics.resolved_by_verified_alias
            + report.metrics.resolved_by_bijapur_correction
            == report.metrics.normalized_observations
        )

    def test_deterministic_repeated_audit(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 9: Repeated audit execution produces bit-identical reports."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)

        report1 = auditor.audit(norm_result)
        report2 = auditor.audit(norm_result)

        assert report1.metrics == report2.metrics
        assert report1.district_coverage == report2.district_coverage
        assert report1.yearly_coverage == report2.yearly_coverage
        assert report1.unresolved_tokens == report2.unresolved_tokens
        assert report1.earliest_event_date == report2.earliest_event_date
        assert report1.latest_event_date == report2.latest_event_date
        assert report1.years_with_zero_records == report2.years_with_zero_records

    def test_raw_source_preservation(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 10: Auditor never mutates raw source data or normalized objects."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)

        events_before = list(norm_result.events)
        obs_before = list(norm_result.observations)
        unresolved_before = list(norm_result.unresolved_tokens)

        _ = auditor.audit(norm_result)

        assert norm_result.events == events_before
        assert norm_result.observations == obs_before
        assert norm_result.unresolved_tokens == unresolved_before

    def test_no_fabricated_geometry_depth_confidence(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 11: Audit explicitly confirms geometry, depth, and confidence are unavailable."""
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(SAMPLE_AUDIT_CSV)
        report = auditor.audit(norm_result)

        # Check source semantics declaration
        semantics = report.source_semantics
        assert semantics["geometry_status"] == "EXPLICITLY_UNAVAILABLE (NULL)"
        assert semantics["flood_depth_status"] == "EXPLICITLY_UNAVAILABLE (NULL)"
        assert semantics["source_confidence_status"] == "EXPLICITLY_UNAVAILABLE (NULL)"
        assert semantics["mapping_status"] == "DETERMINISTIC (Separated from source confidence)"
        assert "NOT satellite inundation ground truth" in semantics["scientific_ground_truth"]

        # Check all normalized observations have strictly None for geometry, depth, confidence
        for obs in norm_result.observations:
            assert obs.geometry is None
            assert obs.flood_depth is None
            assert obs.confidence is None

    def test_empty_input_behavior(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Requirement 12: Empty normalization result produces clean, zeroed audit report."""
        empty_result = IfiNormalizationResult(
            events=[],
            observations=[],
            unresolved_tokens=[],
            out_of_state_tokens_skipped=0,
            raw_records_received=0,
            karnataka_records_filtered=0,
            invalid_records_rejected=0,
            duplicate_events_skipped=0,
            duplicate_observations_skipped=0,
        )

        report = auditor.audit(empty_result)

        assert report.metrics.raw_records == 0
        assert report.metrics.total_unique_events == 0
        assert report.metrics.normalized_observations == 0
        assert report.metrics.districts_with_evidence == 0
        assert report.metrics.districts_without_evidence == 31
        assert len(report.district_coverage) == 31
        assert report.yearly_coverage == []
        assert report.years_with_zero_records == []
        assert report.earliest_event_date is None
        assert report.latest_event_date is None


class TestIfiRealArchiveAuditIntegration:
    """Integration test auditing the real, authoritative IFI historical archive."""

    REAL_IFI_CSV = Path("data/raw/ifi/ifi_v3_karnataka_20260917_164914.csv")

    @pytest.mark.skipif(not REAL_IFI_CSV.exists(), reason="Real IFI archive not present")
    def test_real_ifi_archive_audit_metrics(
        self, auditor: IfiEvidenceAuditor, ksrsac_districts: list[NormalizedDistrict]
    ) -> None:
        """Audit the real IFI archive and verify all exact metrics."""
        report = auditor.audit_source(self.REAL_IFI_CSV)

        m = report.metrics
        assert m.raw_records == 6876
        assert m.karnataka_records == 494
        assert m.valid_events == 493
        assert m.rejected_events == 1
        assert m.normalized_observations == 1271
        assert m.duplicate_events == 0
        assert m.duplicate_observations == 7
        assert m.out_of_state_tokens == 35
        assert m.unresolved_tokens == 31
        assert m.distinct_unresolved_strings == 18
        assert m.districts_with_evidence == 30
        assert m.districts_without_evidence == 1
        assert m.total_unique_events == 493
        assert m.total_unique_district_event_pairs == 1271

        # Resolution breakdown
        assert m.resolved_by_direct_lgd == 1099
        assert m.resolved_by_verified_alias == 140
        assert m.resolved_by_bijapur_correction == 32
        assert m.resolved_by_direct_lgd + m.resolved_by_verified_alias + m.resolved_by_bijapur_correction == 1271

        # Temporal coverage
        assert report.earliest_event_date == "1969-07-14"
        assert report.latest_event_date == "2023-07-24"
        assert report.years_with_zero_records == [1970, 1971, 1973, 1976, 1977]

        # Spatial coverage & Invariant 5: zero-evidence districts remain explicitly zero
        assert len(report.district_coverage) == 31
        for r in report.district_coverage:
            if not r.has_evidence:
                assert r.unique_events == 0
                assert r.district_observations == 0
                assert r.first_event_date is None
                assert r.last_event_date is None

        # Vijayanagara (KGIS 31, LGD 738) has zero matching IFI observations
        vj_rec = next(r for r in report.district_coverage if r.kgis_district_code == "31")
        assert vj_rec.district_name == "Vijayanagara"
        assert vj_rec.lgd_district_code == "738"
        assert vj_rec.unique_events == 0
        assert vj_rec.district_observations == 0
        assert vj_rec.has_evidence is False

        # Invariant 1: unresolved occurrence counts equal sum of unresolved token records
        total_unresolved_occurrences = sum(u.occurrence_count for u in report.unresolved_tokens)
        assert total_unresolved_occurrences == 31
        assert total_unresolved_occurrences == report.metrics.unresolved_tokens

        # Invariant 2: distinct unresolved strings equal number of aggregation records
        assert len(report.unresolved_tokens) == 18
        assert len(report.unresolved_tokens) == report.metrics.distinct_unresolved_strings

        # Invariant 3: resolution-method counts sum to normalized observations
        assert (
            m.resolved_by_direct_lgd + m.resolved_by_verified_alias + m.resolved_by_bijapur_correction
            == m.normalized_observations
            == 1271
        )

        # Invariant 4: audit output is deterministic
        normalizer = IfiEventNormalizer(ksrsac_districts)
        norm_result = normalizer.normalize(self.REAL_IFI_CSV)
        report2 = auditor.audit(norm_result)
        assert report == report2

        # Invariant 6: no synthetic geometry/depth/confidence
        assert all(obs.geometry is None for obs in norm_result.observations)
        assert all(obs.flood_depth is None for obs in norm_result.observations)
        assert all(obs.confidence is None for obs in norm_result.observations)
        assert all(ev.geometry is None for ev in norm_result.events)
        assert all(ev.confidence is None for ev in norm_result.events)
