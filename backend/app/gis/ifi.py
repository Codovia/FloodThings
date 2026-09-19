"""
India Flood Inventory (IFI v3.0) Historical Flood Event Normalization.

Connects and deterministically normalizes historical flood disaster events from the
India Flood Inventory (IFI v3.0, HydroSenseLab / IMD) to the verified KSR-SAC
administrative GIS foundation:
- State boundary: Karnataka (State Code 29)
- District boundaries: 31 authoritative KSR-SAC districts (KGIS codes 01-31)

Design Principles:
1. Pure read-only operation: Raw source files under data/raw/ifi/ are NEVER modified.
2. Grounded administrative mapping: Every deterministic district match links directly
   to a verified KSR-SAC NormalizedDistrict (preserving KGIS code, LGD code, and canonical name).
3. Strict zero-fabrication geometry rule:
   - Missing geometry remains strictly NULL (None).
   - Flood geometry must NEVER be inferred from district centroids or synthetic coordinates.
   - IFI events are historical disaster evidence, NOT satellite inundation ground truth.
4. Preserves semantic provenance:
   - data_category = 'HISTORICAL_EVENT'
   - quality_status = 'VALID'
   - flood_depth = None (missing depth is never filled with 0.0 or estimates)
   - source_record_id = f"ifi_{uei}_{lgd_district_code}"
5. Deterministic alias resolution: Resolves documented historical and spelling variants
   (e.g., Beedar -> Bidar, Bagalkotee -> Bagalkote, Uttar Kashia Kannada -> Uttara Kannada,
   Bijapur [LGD 636 misattribution] -> Vijayapura).
6. Unresolved token containment: If a district token cannot be deterministically mapped
   (e.g., OCR concatenation artifacts like "Bagalkotee Belagavi" or taluk tokens like "Mudigere"):
   - Do NOT guess.
   - Mark as unresolved and record in UnresolvedDistrictTokenRecord audit trail.
7. Out-of-state filtering: Non-Karnataka districts in multi-state events are deterministically
   identified and excluded without treating them as errors.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any
import zoneinfo

from app.gis.ksrsac import KsrsacAdminNormalizer, NormalizedDistrict

IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
UTC_TZ = timezone.utc

SOURCE_NAME: str = "India Flood Inventory (IFI v3.0)"
SOURCE_ORGANIZATION: str = "HydroSenseLab / India Meteorological Department"
KARNATAKA_STATE_CODE: str = "29"

# -----------------------------------------------------------------------------
# Verified Deterministic Spelling & Historical District Aliases for Karnataka
# Maps lowercased name variant -> KGIS District Code ('01' to '31')
# -----------------------------------------------------------------------------
DISTRICT_NAME_ALIASES: dict[str, str] = {
    # 01 - Belagavi
    "belagavi": "01",
    "belgaum": "01",
    # 02 - Bagalkote
    "bagalkote": "02",
    "bagalkotee": "02",
    "bagalkot": "02",
    # 03 - Vijayapura
    "vijayapura": "03",
    "bijapur": "03",
    # 04 - Kalaburagi
    "kalaburagi": "04",
    "kalaburgi": "04",
    "gulbarga": "04",
    # 05 - Bidar
    "bidar": "05",
    "beedar": "05",
    # 06 - Raichur
    "raichur": "06",
    # 07 - Koppal
    "koppal": "07",
    # 08 - Gadag
    "gadag": "08",
    # 09 - Dharwad
    "dharwad": "09",
    # 10 - Uttara Kannada
    "uttara kannada": "10",
    "uttar kashia kannada": "10",  # Upstream IFI OCR / geocoding corruption
    "uttar kannada": "10",
    "north canara": "10",
    # 11 - Haveri
    "haveri": "11",
    # 12 - Ballari
    "ballari": "12",
    "bellary": "12",
    # 13 - Chitradurga
    "chitradurga": "13",
    # 14 - Davanagere
    "davanagere": "14",
    "davangere": "14",
    # 15 - Shivamogga
    "shivamogga": "15",
    "shimoga": "15",
    # 16 - Udupi
    "udupi": "16",
    # 17 - Chikkamagaluru
    "chikkamagaluru": "17",
    "chikmagalur": "17",
    # 18 - Tumakuru
    "tumakuru": "18",
    "tumkur": "18",
    # 19 - Kolara
    "kolara": "19",
    "kolar": "19",
    # 20 - Bengaluru (Urban)
    "bengaluru (urban)": "20",
    "bengaluru urban": "20",
    "bangalore urban": "20",
    "bangalore": "20",
    # 21 - Bengaluru (Rural)
    "bengaluru (rural)": "21",
    "bengaluru rural": "21",
    "bangalore rural": "21",
    # 22 - Mandya
    "mandya": "22",
    # 23 - Hassan
    "hassan": "23",
    # 24 - Dakshina Kannada
    "dakshina kannada": "24",
    "mangalore": "24",
    "south canara": "24",
    # 25 - Kodagu
    "kodagu": "25",
    "coorg": "25",
    # 26 - Mysuru
    "mysuru": "26",
    "mysore": "26",
    # 27 - Chamarajanagara
    "chamarajanagara": "27",
    "chamarajanagaraa": "27",
    "chamarajanagar": "27",
    # 28 - Chikkaballapura
    "chikkaballapura": "28",
    "chikkaballapur": "28",
    # 29 - Bengaluru South / Ramanagara
    "bengaluru south": "29",
    "ramanagara": "29",
    "ramanagar": "29",
    # 30 - Yadgir
    "yadgir": "30",
    # 31 - Vijayanagara
    "vijayanagara": "31",
    "vijayanagar": "31",
}

# Known out-of-state LGD codes present in multi-state events
KNOWN_OUT_OF_STATE_LGD_CODES: frozenset[str] = frozenset(
    {
        # Kerala (State 32)
        "554", "555", "556", "557", "558", "559", "560", "561", "562", "563",
        "564", "565", "566", "567",
        # Gujarat (State 24)
        "460",  # Surendranagar
        # Andhra Pradesh / Telangana (State 28 / 36)
        "507",  # Hyderabad
        "510",  # Krishna
        "519",  # Srikakulam
        # Uttarakhand (State 05)
        "57",   # Uttar Kashi
        # Madhya Pradesh (State 23)
        "603",  # Trailing artifact / MP
    }
)


# -----------------------------------------------------------------------------
# Data Containers
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedIfiEvent:
    """Normalized disaster catalog event record from IFI v3.0."""

    uei: str
    name: str
    start_time: datetime  # UTC (derived under IST assumption)
    end_time: datetime | None  # UTC (derived under IST assumption)
    start_date_raw: str  # Original unparsed source string (e.g., '15-08-2018 00:00')
    end_date_raw: str | None  # Original unparsed source string
    duration_days: int | None
    main_cause: str
    severity: str
    affected_area_sq_km: float | None
    human_fatality: int | None
    human_displaced: int | None
    extent_damage: str
    raw_districts: str
    raw_state: str
    source_name: str = SOURCE_NAME
    confidence: float | None = None  # Source does not publish confidence; remains None per CONSTRAINTS.md
    geometry: None = None  # Explicitly unavailable


@dataclass(frozen=True)
class NormalizedIfiObservation:
    """Normalized district-level historical flood evidence record."""

    uei: str
    observation_time: datetime  # UTC (start of event)
    kgis_district_code: str
    lgd_district_code: str
    district_name: str
    source_record_id: str
    flooded: bool = True
    flood_depth: float | None = None  # Never filled with 0.0 or estimate
    confidence: float | None = None  # Source does not publish confidence; remains None per CONSTRAINTS.md
    mapping_status: str = "DETERMINISTIC"  # Administrative resolution status against KSR-SAC
    resolution_method: str = "DIRECT_LGD"  # 'DIRECT_LGD', 'VERIFIED_ALIAS', 'BIJAPUR_CORRECTION'
    quality_status: str = "VALID"
    data_category: str = "HISTORICAL_EVENT"
    geometry: None = None  # Explicitly unavailable


@dataclass(frozen=True)
class UnresolvedDistrictTokenRecord:
    """Audit record for a district token that could not be deterministically mapped."""

    uei: str
    raw_token: str
    raw_code: str
    reason: str  # 'CONCATENATED_TOKENS', 'TALUK_LEVEL_TOKEN', 'LOCALITY_LEVEL_TOKEN', 'AMBIGUOUS_TOKEN', 'UNMAPPED_TOKEN'


@dataclass(frozen=True)
class IfiNormalizationResult:
    """Complete result of IFI historical flood event normalization."""

    events: list[NormalizedIfiEvent]
    observations: list[NormalizedIfiObservation]
    unresolved_tokens: list[UnresolvedDistrictTokenRecord]
    out_of_state_tokens_skipped: int
    raw_records_received: int
    karnataka_records_filtered: int
    invalid_records_rejected: int
    duplicate_events_skipped: int
    duplicate_observations_skipped: int

    @property
    def total_resolved_observations(self) -> int:
        return len(self.observations)

    @property
    def total_resolved_events(self) -> int:
        return len(self.events)


# -----------------------------------------------------------------------------
# Normalizer Engine
# -----------------------------------------------------------------------------


class IfiEventNormalizer:
    """
    Deterministic normalizer for India Flood Inventory (IFI v3.0) historical events.

    Parses raw IFI CSV data, filters for Karnataka (State Code 29), normalizes timestamps
    from IST to UTC, resolves affected district tokens deterministically against KSR-SAC
    verified administrative districts, records unresolved tokens in an audit log, and preserves
    explicit NULL geometries.
    """

    def __init__(self, ksrsac_districts: list[NormalizedDistrict] | None = None):
        if ksrsac_districts is not None:
            self._districts = ksrsac_districts
        else:
            admin_result = KsrsacAdminNormalizer().normalize()
            self._districts = admin_result.districts

        # Index KSR-SAC districts by KGIS code, LGD code, and canonical lowercased name
        self._by_kgis: dict[str, NormalizedDistrict] = {
            d.kgis_district_code.strip().zfill(2): d for d in self._districts
        }
        self._by_lgd: dict[str, NormalizedDistrict] = {
            d.lgd_district_code.strip(): d for d in self._districts if d.lgd_district_code
        }
        self._by_canonical_name: dict[str, NormalizedDistrict] = {
            d.district_name.strip().lower(): d for d in self._districts
        }

    def _parse_timestamp(self, ts_str: str | None) -> datetime | None:
        """Parse raw IST timestamp string (e.g., '15-08-2018 00:00' or '2018-08-15') to UTC datetime."""
        if not ts_str:
            return None
        ts_clean = ts_str.strip()
        if not ts_clean or ts_clean.lower() in ("none", "null", "nan"):
            return None

        # Try common date/time formats
        formats = [
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                dt_naive = datetime.strptime(ts_clean, fmt)
                dt_ist = dt_naive.replace(tzinfo=IST_TZ)
                return dt_ist.astimezone(UTC_TZ)
            except ValueError:
                continue

        # Try ISO format
        try:
            dt = datetime.fromisoformat(ts_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return dt.astimezone(UTC_TZ)
        except ValueError:
            return None

    def _resolve_district(
        self, raw_name: str, raw_code: str
    ) -> tuple[NormalizedDistrict | None, str | None, str | None]:
        """
        Deterministically map a district token to a KSR-SAC NormalizedDistrict.

        Returns:
            (NormalizedDistrict, None, resolution_method) if resolved deterministically.
            (None, 'OUT_OF_STATE', None) if token belongs to another state.
            (None, reason_code, None) if unmapped/ambiguous/taluk/concatenated.
        """
        code_clean = raw_code.strip()
        name_clean = raw_name.strip()
        name_lower = name_clean.lower()

        # 1. Out of state detection
        if code_clean in KNOWN_OUT_OF_STATE_LGD_CODES:
            return None, "OUT_OF_STATE", None

        # 2. Known geocoding error in IFI: 'Bijapur' assigned 636 (Chhattisgarh) instead of 530 (Karnataka)
        if name_lower == "bijapur" and (code_clean in ("636", "none", "", "530")):
            dist = self._by_kgis.get("03")
            if dist:
                return dist, None, "BIJAPUR_CORRECTION"

        # 3. Direct match by LGD code against KSR-SAC
        if code_clean.isdigit() and code_clean in self._by_lgd:
            return self._by_lgd[code_clean], None, "DIRECT_LGD"

        # 4. Match by canonical name or verified alias
        if name_lower in DISTRICT_NAME_ALIASES:
            kgis_code = DISTRICT_NAME_ALIASES[name_lower]
            dist = self._by_kgis.get(kgis_code)
            if dist:
                return dist, None, "VERIFIED_ALIAS"

        # 5. Direct match by canonical KSR-SAC name
        if name_lower in self._by_canonical_name:
            return self._by_canonical_name[name_lower], None, "VERIFIED_ALIAS"

        # 6. Categorize unresolved reasons without guessing
        # Check if composite / concatenated tokens
        common_words = [
            "belagavi", "bagalkotee", "bagalkote", "chamarajanagaraa", "chamarajanagara",
            "chikkaballapura", "hassan", "bengaluru", "davangere", "davanagere", "gadag",
            "ballari", "kalaburagi", "udupi", "chitradurga", "bijapur", "surendranagar"
        ]
        matches = [w for w in common_words if w in name_lower]
        if len(matches) >= 2 or " " in name_clean and any(w in name_lower for w in common_words):
            if any(name_lower.startswith(w) for w in ["chamarajanagaraa", "bagalkotee"]):
                return None, "CONCATENATED_TOKENS", None

        if name_lower in ("mudigere", "chikodi"):
            return None, "TALUK_LEVEL_TOKEN", None

        if name_lower == "rugi":
            return None, "LOCALITY_LEVEL_TOKEN", None

        if "parts of karnataka" in name_lower:
            return None, "NON_DISTRICT_DESCRIPTOR", None

        if name_lower == "uttar kashia":
            return None, "AMBIGUOUS_TOKEN", None

        return None, "UNMAPPED_TOKEN", None

    def normalize(
        self,
        csv_source: str | Path | io.StringIO,
        max_records: int | None = None,
    ) -> IfiNormalizationResult:
        """
        Normalize historical flood events from CSV source.

        Args:
            csv_source: File path, raw CSV text string, or StringIO.
            max_records: Optional maximum records to process.

        Returns:
            IfiNormalizationResult containing normalized events, observations, and audit log.
        """
        if isinstance(csv_source, Path):
            with open(csv_source, "r", encoding="utf-8") as f:
                content = f.read()
        elif isinstance(csv_source, str) and (Path(csv_source).exists() if len(csv_source) < 1000 else False):
            with open(csv_source, "r", encoding="utf-8") as f:
                content = f.read()
        elif isinstance(csv_source, str):
            content = csv_source
        elif isinstance(csv_source, io.StringIO):
            content = csv_source.getvalue()
        else:
            raise ValueError(f"Unsupported csv_source type: {type(csv_source)}")

        # Configure CSV reader
        reader = csv.DictReader(io.StringIO(content, newline=""))

        events: list[NormalizedIfiEvent] = []
        observations: list[NormalizedIfiObservation] = []
        unresolved_tokens: list[UnresolvedDistrictTokenRecord] = []

        seen_ueis: set[str] = set()
        seen_obs_keys: set[tuple[str, str]] = set()  # (uei, kgis_district_code)

        raw_records_received = 0
        karnataka_records_filtered = 0
        invalid_records_rejected = 0
        duplicate_events_skipped = 0
        duplicate_observations_skipped = 0
        out_of_state_tokens_skipped = 0

        for raw_row in reader:
            raw_records_received += 1

            # Strip leading BOM and clean keys/values
            row = {k.strip("\ufeff ").strip(): v.strip() for k, v in raw_row.items() if k}

            state_codes_str = row.get("State_Codes", "")
            state_codes = [c.strip() for c in state_codes_str.split(",") if c.strip()]

            # Filter for Karnataka events
            if KARNATAKA_STATE_CODE not in state_codes:
                continue

            karnataka_records_filtered += 1

            uei = row.get("UEI", "").strip()
            start_date_raw = row.get("Start Date")
            end_date_raw = row.get("End Date")

            start_dt = self._parse_timestamp(start_date_raw)
            if start_dt is None:
                invalid_records_rejected += 1
                continue

            end_dt = self._parse_timestamp(end_date_raw)

            # Deduplicate events by UEI
            if uei in seen_ueis:
                duplicate_events_skipped += 1
                continue
            seen_ueis.add(uei)

            # Parse event metadata
            duration_str = row.get("Duration(Days)", "").strip()
            duration_days: int | None = int(duration_str) if duration_str.isdigit() else None

            main_cause = row.get("Main Cause", "").strip() or "Unspecified"
            severity = row.get("Severity", "").strip() or "MODERATE"

            area_raw = row.get("Area Affected", "").strip()
            try:
                affected_area = float(area_raw) if area_raw else None
            except ValueError:
                affected_area = None

            fatality_raw = row.get("Human fatality", "").strip()
            fatality: int | None = int(fatality_raw) if fatality_raw.isdigit() else None

            displaced_raw = row.get("Human Displaced", "").strip()
            displaced: int | None = int(displaced_raw) if displaced_raw.isdigit() else None

            extent_damage = row.get("Extent of damage ", "").strip() or row.get("Extent of damage", "").strip()
            districts_str = row.get("Districts", "").strip()
            state_str = row.get("State", "").strip()

            event_name = (
                f"Flood Event {uei} ({districts_str[:50]})"
                if uei
                else f"Flood Event {start_dt.strftime('%Y-%m-%d')}"
            )

            event = NormalizedIfiEvent(
                uei=uei,
                name=event_name,
                start_time=start_dt,
                end_time=end_dt,
                start_date_raw=start_date_raw or "",
                end_date_raw=end_date_raw if end_date_raw else None,
                duration_days=duration_days,
                main_cause=main_cause,
                severity=severity,
                affected_area_sq_km=affected_area,
                human_fatality=fatality,
                human_displaced=displaced,
                extent_damage=extent_damage,
                raw_districts=districts_str,
                raw_state=state_str,
                source_name=SOURCE_NAME,
                confidence=None,  # Source does not publish confidence
                geometry=None,  # Explicitly unavailable
            )
            events.append(event)

            # Parse district tokens and pair with LGD codes
            d_names = [d.strip() for d in districts_str.split(",") if d.strip()]
            district_lgds_str = row.get("District_LGD_Codes", "").strip()
            d_codes = [c.strip() for c in district_lgds_str.split(",") if c.strip()]

            # Build name/code pairs
            pairs: list[tuple[str, str]] = []
            if len(d_names) == len(d_codes):
                pairs = list(zip(d_names, d_codes))
            else:
                min_l = min(len(d_names), len(d_codes))
                pairs = list(zip(d_names[:min_l], d_codes[:min_l]))
                for extra_name in d_names[min_l:]:
                    pairs.append((extra_name, "None"))

            for raw_name, raw_code in pairs:
                norm_dist, unmapped_reason, res_method = self._resolve_district(raw_name, raw_code)

                if unmapped_reason == "OUT_OF_STATE":
                    out_of_state_tokens_skipped += 1
                    continue

                if norm_dist is None:
                    unresolved_tokens.append(
                        UnresolvedDistrictTokenRecord(
                            uei=uei,
                            raw_token=raw_name,
                            raw_code=raw_code,
                            reason=unmapped_reason or "UNMAPPED_TOKEN",
                        )
                    )
                    continue

                # Deduplicate observations by (uei, kgis_district_code)
                obs_key = (uei, norm_dist.kgis_district_code)
                if obs_key in seen_obs_keys:
                    duplicate_observations_skipped += 1
                    continue
                seen_obs_keys.add(obs_key)

                source_rec_id = f"ifi_{uei}_{norm_dist.lgd_district_code}"
                observation = NormalizedIfiObservation(
                    uei=uei,
                    observation_time=start_dt,
                    kgis_district_code=norm_dist.kgis_district_code,
                    lgd_district_code=norm_dist.lgd_district_code,
                    district_name=norm_dist.district_name,
                    source_record_id=source_rec_id,
                    flooded=True,
                    flood_depth=None,  # Never filled with 0.0 or estimate
                    confidence=None,  # Source does not publish confidence
                    mapping_status="DETERMINISTIC",
                    resolution_method=res_method or "DIRECT_LGD",
                    quality_status="VALID",
                    data_category="HISTORICAL_EVENT",
                    geometry=None,  # Explicitly unavailable
                )
                observations.append(observation)

            if max_records and len(events) >= max_records:
                break

        return IfiNormalizationResult(
            events=events,
            observations=observations,
            unresolved_tokens=unresolved_tokens,
            out_of_state_tokens_skipped=out_of_state_tokens_skipped,
            raw_records_received=raw_records_received,
            karnataka_records_filtered=karnataka_records_filtered,
            invalid_records_rejected=invalid_records_rejected,
            duplicate_events_skipped=duplicate_events_skipped,
            duplicate_observations_skipped=duplicate_observations_skipped,
        )
