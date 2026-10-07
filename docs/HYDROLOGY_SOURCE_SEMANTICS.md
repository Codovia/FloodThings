# Hydrology source semantics and clarification template

Stage 4C2, 7 October 2026. This records bounded official-source research, not
permission to construct features or replace observations. Detailed resolution
products and the concrete unsent clarification package are local in
`data/working/karnataka_hydrology_semantics_v1/`. Public provenance is in
`data/reference/karnataka_hydrology_semantics_v1/manifest.json`.

## Measurement reference and quality

The [CWC June 2020 handbook](https://cwc.gov.in/sites/default/files/hand-book-hydro-meteorological-observations._1.pdf)
distinguishes gauge reading from water-level elevation. Section 2.1.3, PDF page18,
connects gauge zero to a GTS benchmark and determines its R.L. relative to MSL.
The reporting example on PDF186, step4, explicitly adds gauge-zero R.L. to the
reading. This supports `reported water level = gauge reading + gauge-zero R.L.`
for that procedure. RD-2 (PDF139) separates mean gauge, MSL water level,
discharge and observed/computed status. RD-3/4 (PDF141/142) keep gauge zero and
level fields distinct. Section4.4 (PDF50) explains discharge computation from
observed stage-discharge curves, including high-flood extrapolation.

These instructions do **not** establish the exact NWDP field's reference.
The [Krishna resource](https://nwdp.nwic.gov.in/en/dataset/river-water-level-manual-hourly-cwc-subernarekha/resource/7778f459-0e82-4681-9638-5e494c36fd42)
and its advertised Preview/catalogue identify metre units and separate
RL_of_zeroGauge/MeanSeaLevel columns, without defining their relationship to
the measured field. Numeric magnitudes cannot resolve datum. All three pilot
stations remain `nwdp_datum_unresolved`; warning/danger/HFL compatibility stays
`datum_unresolved`. No conversions/exceedances have been calculated.

The [Krishna Year Book 2019–20](https://cwc.gov.in/sites/default/files/stage-dischargecompressed.pdf),
PDF22 section1.4.2/1.4.3, describes division validation, regional finalisation,
seasonal rating-curve checks and computation for non-observed/discarded values.
It mentions e-SWIS entry since June2016. This establishes a processing/revision
possibility, not a particular NWDP revision or precedence. Book `*` computed,
`#` discarded/rating-curve-changed, and unmarked observed/estimated distinctions
remain unchanged. No record-specific lineage/approval/QC field was found in the
retained CSV schemas or current resource metadata. Portal file/metadata update
times are not record revision times. All 33 disagreements retain their prior
categories and receive a separate
`revision_possible_record_lineage_unverified` finding. Neither source is preferred.

## Coordinates and reuse

The [March2026 HO book](https://cwc.gov.in/sites/default/files/Final%20signed%20HO%20Book_2026.pdf)
references 1January2026 and contains all three current CWC codes. It changes
Sadalga's published coordinates relative to the April2025 book, while the other
two pairs remain the same. No station-specific correction/relocation explanation
was found in these books or the linked closed-station book. All coordinate source
values are retained separately, with no averaging, replacement or canonical
point selection. NWDP/Year Book agreement at Huvinhedgi does not resolve its
different 2025/2026 metadata location.

The [2018 dissemination policy](https://www.cwc.gov.in/sites/default/files/hddp2018_0.pdf)
supports validated unclassified India-WRIS downloads and attributed use in
publications. Classified-data restrictions must not be applied indiscriminately
to Krishna data. The HO webpage still links the older2013 policy.
The portal-linked [National Water Data Policy2026](https://nwdp.nwic.gov.in/pdf/national-water-data-policy.pdf)
states supersession of2018 and supports free unclassified downloads with producer
acknowledgement (section4.4). However, its PDF metadata title says **Final Draft**;
adoption/commencement was not independently established. Its creation date is
not an enactment date.

[NWDP copyright](https://www.nwdp.nwic.gov.in/footer/copyrightPolicy) supports
accurate, nonmisleading attributed reproduction except explicitly third-party
material. [CWC copyright](https://cwc.gov.in/en/copyright-policy) requires
permission to reproduce its website contents. Neither producer identity alone
nor Other(Open) establishes third-party copyright or a standard licence.
No resource-specific licence definition/URL was found in the inspected metadata.
The interaction remains `policy_conflict_unresolved` for detailed NWDP resources.
Keep source documents, raw observations, detailed comparisons and coordinates
local. Public code, templates, references and aggregate provenance contain no
withheld observations. Local retention is project handling, not a legal grant.

## Stage4D guard

The existing14 quality-caveated daily-discharge rows remain the entire eligible
subset (Sadalga2, Huvinhedgi12, Gokak0). Absolute and threshold-relative hourly
level use remains blocked. Within-station differences mathematically remove a
constant additive datum, so future change/rise research is conditionally
defensible only after reference stability, QC, acquisition intervals and time
semantics checks. Strong identity, unique timestamps and consistent units alone
do not prove those conditions. No changes/rates were calculated or eligibility
statuses rewritten. Precise coordinate joins remain unresolved; documentary
station association is usable with caveats. Historical availability stays
unverified.

## Unsent clarification template

Purpose: FloodPulse academic exploratory historical flood research. No model or
hydrological features have been produced in this stage. This is a template only;
the local package contains bounded examples and provenance, without large files.

Resource: **River Water Level Manual Hourly CWC Krishna (1991-2020)**;
dataset `d951a09c-6cf8-470e-be77-e80116f13d34`, resource
`7778f459-0e82-4681-9638-5e494c36fd42`. Daily-discharge resource
`f95150ea-c8fc-4740-8815-d9c34c9d53a3`.
Stations: Sadalga `CW1KRU000083`, Gokak Falls `CW1KRU000212`,
Huvinahedgi `CW1KRU000339`.

1. Is the exact Water Level field stage above local zero, R.L. above MSL, or
   station-specific? Please supply the dictionary and applicable datum history.
2. Are NWDP manual-daily values field, validated archival, revised or direct
   Year Book records? Can later revisions differ? Please identify record versions
   for the local discrepancy examples; neither publication has been preferred.
3. Which fields distinguish observed, computed, revised and rejected/discarded
   discharge? How do absent flags and the book's `*`/`#` markers relate?
4. Which coordinates are canonical? Please provide dated relocation, gauge-site
   shifting or coordinate-correction evidence, including Sadalga and Gokak.
5. May downloaded observations and detailed comparisons be redistributed in an
   academic open-source project with attribution? Please clarify Other(Open),
   portal/producer copyright applicability and the2026 document's adoption status.
   Does CWC require written permission?

Nothing has been sent. Obtain authoritative responses before lifting these gates.
