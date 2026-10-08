# Stage 5A: target definition and issuance archives

Status: **target_and_archive_validation_ready_limited**. Methodology review is complete; **ML training remains prohibited**. No primary prediction target, forecast-day boundary, issue-clock schedule or risk-class mapping is adopted. No training matrix, negative label or hydrological comparison is created.

## Product intent and observable outcomes

The original Q&A specifies Karnataka district/locality Low/Medium/High risk, seven forecast days and a six-hour refresh. It also mixes occurrence, severity, general scores, probabilities, hotspots and alerts. The current README describes the verified rebuild. Referenced master/change files are absent. Historical synthetic-label, proxy-score, numeric cutoff and completion claims in the Q&A are not evidence or accepted class definitions.

The local version inventories **271** matching requirement paragraphs/tables from QandA, README and the current prediction method, with exact original text, document role, sections and line ranges. Original Q&A excerpts remain local. Geography, temporal aggregation, probability calibration and class definitions remain unspecified where the source is ambiguous.

Four concepts remain separate:

| Concept | Current defensible definition |
| --- | --- |
| Observation target | Observation-qualified non-permanent mapped water in an original GFD cell at least once during its recorded event window |
| Model target | Not adopted; occurrence versus impact/severity and operational spatial/time unit need independent definitions |
| User-facing risk | Low/Medium/High is a requirement; no validated mapping from an observation or model output |
| Alert decision | Separate operational policy, not automatically the class label or probability |

The strongest supported measurement is spatial/event-window positive evidence. It does not establish daily onset, six-hour occurrence, whole-district/locality states, severity, depth, impact or calibrated risk. GFD start/end dates identify the recorded event window, not exact water onset/cessation at each pixel. The four positive scopes remain 2728 Udupi (33), 3551 Udupi (23), 3652 Chitradurga (2) and 2758 Kolar (329). Pixel counts are not independent event samples or severity scores.

Observed-zero maps 2698 Bijapur and 3107 Raichur are comparison evidence only. Missing, unobserved or unreported does not mean non-flood. IFI reports support documentary occurrence with retained uncertainty. Existing Sentinel-1 diagnostics are not validated positive labels. NRSC contextual maps require time, georeferencing and categorical-reference validation before machine-readable labels.

CWC's April 2025 [SOP](https://cwc.gov.in/sites/default/files/sopapril2025.pdf), Annex 3.2, PDF page 82, distinguishes above-normal/severe/extreme station water levels relative to warning/danger/HFL. KSDMA's [2021 action plan](https://ksdma.karnataka.gov.in/storage/pdf-files/ActionplanforFloodriskmanagement2021.pdf), Tables 5/6, PDF pages 75/78, lists village hazard categories. Neither supplies FloodPulse's seven-day Low/Medium/High mapping. Datum restrictions still prohibit project water-level threshold features. No generic probability cutoffs are adopted.

## Issuance contract

`exact_issuance_schedule_unspecified`: six-hour refresh does not imply 00/06/12/18 UTC, nor a local clock schedule. Seven forecast days do not specify rolling 24-hour windows, next IST calendar days or provider forecast days.

A future record must retain separate timezone-aware prediction issue, model initialization, documented first availability, retrieval and valid-interval clocks, plus product/model version, member, spatial-unit vintage and units. Only an actual operational forecast available by prediction time T may supply future values. Forecast initialization is not public availability. Observations after T, event-window rainfall, outcome reports, flood extent and future peaks remain prohibited predictors. CHIRPS Final's delayed publication is separate from calendar antecedent calculation.

## Weather archives and parity

Official sources were inspected on 8 October 2026. Originals, HTTP receipts and hashes stay local; automated tests use controlled temporary fixtures only.

| Product | What is preserved | Result and limitation |
| --- | --- | --- |
| [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api) | Requested model and initialization | IFS begins 14 March 2024; earlier series are explicitly Cycle 49R1 hindcasts. Cycle 50R1 applies from 12 May 2026 06 UTC. Earlier IFS is not an as-issued operational archive. Recent pinned runs have delivery/version caveats. |
| [Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) | Fixed lead series | Mostly since 2024; earlier GFS temperature does not establish earlier precipitation. Not a complete issued run. |
| [Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api) / historical weather | Stitched series / later analysis | Not issuance-preserving; reanalysis is not a forecast originally known at T. |
| [ECMWF TIGGE](https://www.ecmwf.int/en/research/projects/tigge), [ECDS catalogue](https://ecds.ecmwf.int/datasets/tigge-forecasts?tab=overview) | Archived operational ensemble forecasts, since October 2006 | Potential 2009/2010 overlap. Public 48-hour access delay, centre/version/gaps and terms must be validated. Selected historical runs have not been retrieved. |
| [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) | Current operational subset | Latest 12 runs, about 2–3 days, not an old-event archive through this route. Prospective capture needs actual delivery clocks. |

TIGGE's current ECMWF table describes 00/12 UTC ensemble initializations, six-hour output steps and typically 10–15-day lead spans. These are provider properties, not the application clock. Centre-dependent native/interpolated grids and historical model upgrades preclude automatic exact parity with current ECMWF/Open-Meteo products. Total precipitation is accumulated from step zero in kg/m² (parameter 228228). A future interval extraction must difference the same run/member's accumulated steps while preserving missingness and original units. No rainfall transformations are calculated here. Official [FAQ](https://confluence.ecmwf.int/spaces/TIGGE/pages/40797492/FAQ) and [migration guide](https://confluence.ecmwf.int/display/DAC/User+guide+for+migration+of+S2S+and+TIGGE+to+ECDS) describe the 48-hour delay and 27 May 2026 ECDS migration. The full TIGGE licence URL timed out during the bounded attempt; catalogue licence identity is known, detailed reuse remains a future gate.

[Open-Meteo availability metadata](https://open-meteo.com/en/docs/model-updates) separates initialization, modification and availability. Last-run metadata is not a historic delivery-clock archive. A small public Bengaluru request pinned to 1 October 2026 00 UTC returned 24 hourly times: **23 finite precipitation values, one null, 24 finite temperatures**. The null remains unchanged. The original response is 1,000 bytes, SHA-256 `d005edd589969bffda47c243b4e2c30c202857db93b77c8760f53cca133e46f0`. It verifies API readability and interval/units, not original public delivery or model-version identity: the response does not echo the requested run/model/version. The generated documentation's Berlin temperature example was also inspected via its advertised link; its original bytes were not retained. No historical event forecasts or large archives were downloaded.

## Hydrology archives

| Product | Evidence class | Implication |
| --- | --- | --- |
| [cems-glofas-forecast](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview) | Operational forecast archive | Catalogue starts 5 November 2019; none of four GFD positives overlap. Daily 00 UTC, 51 members, catalogue v4, 0.05°. Historical versions vary. EWDS 30-day archive and current 15-day/46-day products must not be conflated. |
| [cems-glofas-reforecast](https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast?tab=overview) | Later hindcasts | Nominal 2003–2022 years overlap all four, but simulations were not issued before those events. Current catalogue v4, 11 members, twice-weekly 00 UTC, 24-hour steps, 46 days. Specific dates and version parity unverified. |
| [cems-glofas-historical](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview) | Consolidated retrospective modelled discharge | Stage 4D timestamps remain end-of-preceding-24h context. Neither measured discharge nor operational issued forecasts. |

GloFAS historical v5 grid matching for Sadalga/Huvinhedgi does not establish their mapping to earlier forecast-system networks. Gokak remains excluded. NWDP temporal semantics, datum compatibility and quantitative measured/modelled comparisons remain unresolved/prohibited. No EWDS request was made in Stage 5A. Historical/reforecast/operational version and forcing differences require separate parity evaluation.

## Archive/label overlap

| Positive scope | Recorded GFD window | TIGGE catalogue overlap | Open-Meteo precipitation / GloFAS operational overlap |
| --- | --- | --- | --- |
| 2728 Udupi, 33 cells | 14–30 September 2005 | No | No |
| 2758 Kolar, 329 cells | 23 October–9 December 2005 | No | No |
| 3551 Udupi, 23 cells | 25 September–12 October 2009 | Yes; actual runs and delivery not verified | No |
| 3652 Chitradurga, 2 cells | 18–24 May 2010 | Yes; actual runs and delivery not verified | No |

All four overlap nominal GloFAS hindcast years, which does not establish as-issued availability. Existing SOI2025 geometry is locally restricted and not independently current-LGD reconciled; WorldCover2021 and later DSM/static products cannot be assumed available for 2005–2010. Existing Belagavi SRTM terrain has February 2000 acquisition context, but publication vintage, footprint and derived processing still require as-of checks. Static acquisition and release clocks are separate.

## Future negative protocol and readiness

A proposed observed non-inundation requires an explicit spatial unit/time interval, valid sensor coverage throughout the interval, independently assessed detection sensitivity and false-negative limitations, permanent-water handling, independent reference/monitoring, and a predeclared comparison selection protocol. A spatial coverage percentage alone does not prove temporal absence. All protocol results remain review candidates: **zero negative labels are created**.

Readiness: target definition **UNRESOLVED**; positive evidence **LIMITED**; negative labels **NOT_READY**; forecast archive **LIMITED**; weather/hydrology parity **UNRESOLVED**; temporal alignment/sample size **NOT_READY**; risk mapping **UNRESOLVED**. No primary target or horizon is adopted. A lack of deployable target does not invalidate the observation evidence.

## Exact next stage

**Stage 5B — Time-Resolved Label Development & Issuance Dataset Pilot (gated)**: existing Belagavi review tile, official Hulagabali/Halyal/Sankaratti context, 24–30 July 2021. First establish legitimate, categorical, time-resolved NRSC reference evidence and reuse; the retained 26/28 July maps are context, their viewport registration is not flood geometry and acquisition hours are not documented. Obtain source-supported acquisition intervals before defining outcomes.

If that gate succeeds, validate a small ECMWF `tigge-forecasts` request for the existing scope. Candidate initializations are 23 July 2021 00/12 UTC, with required steps between 48–168 hours only. These are proposed runs, not verified available records. Keep members/versions and reconstruct prediction T from documented public delivery after the 48-hour delay; initializations are not T. Terms/account and exact run availability are additional gates. Do not begin a training matrix or choose production issue clocks in that pilot.

Use independent mapped non-permanent water as a possible precise observation target, and only protocol-validated monitored non-inundation as a possible comparison. Omit hydrology until forecast-network/version/time parity is established; Gokak remains excluded. If the label/terms/archive gate fails, retain findings rather than making labels; consider bounded prospective pinned-run capture and monitored outcomes in the existing Udupi window. Include relevant upstream catchments in any later hydrology design, even beyond Karnataka.

## Reproduction and publication

`python scripts/review_target_archives.py build` creates a new local version and refuses an existing one. `validate` reproduces all decisions, verifies original input/code/output hashes, and performs no writes. `publish-metadata` creates the permitted public manifest once. No credentials are read; no live network call occurs in these commands or tests. Local original documents, Q&A excerpts, technical raw response and detailed evidence stay outside Git. Public artifacts contain own methodology, source IDs/URLs, checksums and technical counts only.
