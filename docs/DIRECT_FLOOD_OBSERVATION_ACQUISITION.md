# Phase 12E: direct flood observation acquisition

**NO-GO for a genuine future-flood prediction experiment.** Actual acquisitions
and source checks improve the observation foundation, but yield **zero eligible
positives, zero defensible negatives, zero independent eligible flood events and
zero complete issue-time feature joins**. No model was fitted, replaced or
deployed. Groundsource was not enlarged or re-extracted. Rainfall inference and
all application workflows remain separate.

Baseline: `8e702b944a5d207cb1d56b0c30fe6c73930eec68`, branch
`feature/karnataka-data-foundation`. Research and acquisition date: 12 October
2026. Machine-readable outputs: [report](phase12e/report.json),
[native product register](phase12e/native_product_register.json),
[acquisition plan](phase12e/acquisition_plan.json),
[proposed target protocol](phase12e/candidate_target_protocol.json) and
[riverine readiness](phase12e/riverine_readiness.json), with
[source/acquisition receipts](phase12e/source_receipts.json).

## Acquisition scope and provenance

The initial local acquisition plan was written **before** metadata transfer in
`data/recovery/phase12e_v1/acquisition_plan_initial.json`. A second pinned plan
preceded the two raster previews. Free disk before acquisition was
359,662,538,752 bytes. All new originals, original response bytes, receipt hashes,
previews and detailed observation contexts are protected and ignored in
`data/raw/direct_flood_observations_phase12e_v1/`; derived outputs are in
`data/working/direct_flood_observations_phase12e_v1/`. The existing 667 MB archive,
government geometry and historical datasets were unchanged.

There were **26 bounded metadata/document requests**, each capped at 2 MiB:
19 retrieved, six HTTP failures/redirects and one unavailable request. Their
accepted bodies total **2,443,538 bytes**, including the official 1,436,479-byte
JPL specification. No original PDF is published. Separate existing-access Earth
Engine metadata and **two 100×100, four-band previews** were retrieved. The
previews total **13,227 bytes**, below the recorded 4 MiB aggregate ceiling.

Metadata requests refuse unapproved hosts, embedded credentials, authentication
query parameters, native archive paths, native raster/archive signatures,
redirect following, oversized/truncated bodies and receipt overwrites. Only
safe HTTP/content/date headers are retained. Earth Engine used existing access;
no authentication flow or credential update occurred. No external message,
government geometry upload, full tile, SAFE, HDF or reforecast download occurred.

Two initial CMR `granule_ur` requests returned HTTP400; corrected temporal and
concept-ID queries recovered both original records. Those failures are not
evidence that the products are unavailable. The PO.DAAC specification link
redirected303; the same specification was recovered through the official
[JPL DSWx product suite](https://www.jpl.nasa.gov/go/opera/products/dswx-product-suite/).
Initial EWDS307 responses were resolved by explicitly requesting its public
overview URLs. Bhuvan WMS GetCapabilities returned400; no usable native mask or
preview was obtained from that endpoint. The NASA August2026 Udupi query returned
zero matches in the queried collection/window/month, which does **not** establish
statewide absence, product discontinuation or adequate observation.

## Native OPERA candidates and actual bounded observations

The originals matched by NASA CMR are:

1. `OPERA_L3_DSWx-S1_T43PDQ_20241204T004900Z_20241204T183634Z_S1A_30_v1.0`
   — concept `G3315956458-POCLOUD`.
2. `OPERA_L3_DSWx-S1_T43PDQ_20241209T005659Z_20241212T220859Z_S1A_30_v1.0`
   — concept `G3327211919-POCLOUD`.

These are a predetermined, date-sorted observation-quality batch, **not two
independently confirmed December flood events**. They avoid the documented 2025
processing-anomaly period. Publisher product/RTC version is1.0; UMM software
version is1.1, distinct from product version. UMM input RTC filenames and per-file
MD5/bytes are retained. Original packages total **6,702,352 bytes**; original
four-class files total5,838,457 bytes. Their originals were not downloaded or
publisher-checksum verified. Platform subset SHA-256 verification establishes
the exact subset bytes only.

| Observation | Publisher sensing interval, UTC | Platform nominal time | Source classes in 10,000 pixel contexts | Preview bytes |
|---|---|---|---|---:|
| 4 December2024 | 00:48:40–00:49:03 | 00:49:00 | WTR0:9,993; WTR3:7 | 12,308 |
| 9 December2024 | 00:56:47–00:57:01 | 00:56:59 | All four bands255:10,000 | 919 |

NASA's UMM range is retained as the **publisher granule sensing interval**.
Earth Engine repeats a single nominal instant for start/end; it is not the
actual stop time. Per-pixel burst assignment has not been reconstructed. Product
processing on4December or12December is not its sensing time.

The subsets use the pre-existing public Udupi 3 km research window, EPSG:32643,
30 m spacing, transform `[30,0,471150,0,-30,1476450]`, without resampling within
the Earth Engine asset. **They are platform-derived asset-grid subsets, not
untouched original PO.DAAC products.** The full platform footprint bounds are
approximately `[74.075228,12.574119,75.090351,13.568567]`; NASA UMM instead gives
`[74.030272,12.618131,75.045299,13.612754]`. This disagreement affects both
products. Both descriptions cover the research window, but do not certify
pixel placement. Original GeoTIFF tags, checksum-bound georeferencing and
independent registration validation are required. Neither coordinates nor
rasters were shifted to conceal this disagreement.

The [JPL specification](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DSWx-S1_Product_Spec_v1.0.0_D-108761_RevA_2024-08-16_.pdf)
was inspected as text and rendered PDF pages16–18. Together with the
[Earth Engine catalogue](https://developers.google.com/earth-engine/datasets/catalog/OPERA_DSWX_L3_V1_S1)
it establishes source classes and limitations:

- WTR0 means source not-water; ancillary land-cover masking can produce0. WTR1
  means open water; WTR3 is algorithmic inundated vegetation. BWTR combines1/3
  into binary water and does not distinguish temporary from permanent water.
- WTR/BWTR/CONF250 and251 are HAND and layover/shadow exclusions. Fill is255.
  DIAG uses252/253 for those exclusions; the linked specification also lists120
  as DIAG fill. Both120 and exported255 fail the observation-quality screen.
- CONF1/31 denote high-confidence open water,2/32 moderate water,5 potential
  inundated vegetation,35 inundated vegetation in mapped wetland,6/36 low
  backscatter excluded by bimodality and7/37 ancillary-mask exclusions. Generic
  prose in the specification misnumbers some classes, while the detailed class
  definitions and catalogue agree. The code follows the explicit definitions;
  unfamiliar/contradictory values fail closed.
- Source mapping is 30 m, not a guarantee of detecting a 30 m flood. The catalogue
  describes open-water features larger than3ha and at least200m wide, normally
  at a6–12day revisit. Clouds are not the principal radar obstruction; terrain
  layover/shadow, vegetation, buildings, low backscatter and ancillary exclusion
  remain relevant. A contemporary independently validated permanence baseline
  and local omission/commission assessment are still absent.

The returned GeoTIFFs tag nodata0 although zero is a documented valid source
class. The validator explicitly reads raw classes, retains original bytes and
uses documented fill/mask codes; a default masked read would incorrectly discard
valid not-water/diagnostic zeros. It never turns retained zeros into negatives.

For4December, CONF counts are0:5,998;5:3,881;6:4;30:110;35:7. The strict screen
retains **6,108 source not-water candidates** and **seven unverified vegetation
water classifications**;3,885 contexts are insufficient. The9December pass is
entirely insufficient despite the full-tile footprint and its positive catalogue
spatial-coverage percentage. Zero high-confidence open-water pixels were obtained.
The seven vegetation pixels are not independently verified temporary flooding.

| Outcome evidence across both passes | Pixel-acquisition contexts |
|---|---:|
| Independently observed temporary inundation | 0 |
| Adequately observed absence of temporary inundation | 0 |
| Independently verified permanent water | 0 |
| Insufficient observation | 13,885 |
| Unknown pending permanence, geography and independent interpretation | 6,115 |

Thus **one acquisition contains interpretable non-fill source classes, zero
have independently verified geographic accuracy, and zero are eligible flood
observation/training labels**. These repeated pixel contexts are not20,000
independent examples. Both acquisition-level scientific contracts remain UNKNOWN.

Five retained August2025 products were independently rechecked by NASA metadata
only; all exact IDs/timestamps are in the product register. The earlier retained
PO.DAAC alert describes mixing S1A/S1C dates during20May–7November2025, a9December
fix and planned replacement. Current queries for the first two still return
revision1 records dated August2025. Product-specific replacement was not proved;
all five stay quarantined. A planned fix or vanished webpage banner is not a
checksum-bound correction receipt. OPERA cannot supply native2005/2009 or2021
observations for the historical reference events.

## Belagavi2021 Sentinel-1 and official NRSC evidence

The exact retained native scenes were recovered from the official Copernicus
OData catalogue with original footprints, dates, IDs, byte counts and published
MD5/BLAKE3 checksums:

| Native product identifier | Sensing interval UTC | Catalogue ContentLength bytes |
|---|---|---:|
| `S1A_IW_GRDH_1SDV_20210705T004732_20210705T004757_038635_048F13_BF03.SAFE` | 5July00:47:32.006–00:47:57.004 | 1,706,457,291 |
| `S1A_IW_GRDH_1SDV_20210717T004732_20210717T004757_038810_049451_0405.SAFE` | 17July00:47:32.777–00:47:57.775 | 1,706,401,930 |
| `S1A_IW_GRDH_1SDV_20210729T004733_20210729T004758_038985_049989_7AE1.SAFE` | 29July00:47:33.337–00:47:58.335 | 1,706,385,435 |

All are descending IW VV/VH, relative orbit63. Their native footprints are
retained separately from restricted government boundaries. The
[official Sentinel-1 specification](https://sentiwiki.copernicus.eu/web/s1-products)
distinguishes **20×22m nominal IW-GRD resolution** from **10m pixel spacing**.
They are continuous radar measurements, not flood classes or permanent-water
labels. Calibration, thermal/border noise, incidence, orbit/terrain correction,
layover/shadow, registration, seasonal backscatter and independent flood truth
must be checked. Exact IPF/native processing-version evidence needs SAFE
annotations; catalogue modification/checksum dates do not establish reprocessing.

The retained NRSC PDFs were re-inspected as text and rendered pages. Map
`09-FL-2021-KA/2021/01` uses WorldView3 on26July2021, received under International
Charter830. Map `08-FL-2021-MH/2021/06` uses Resourcesat2A LISSIII on28July2021.
Both were issued29July, show clouds and indicate regional flood inundation.
Their **native scene/granule IDs and sensing clocks remain UNKNOWN**. The PDF
viewport, labelled arrow or map issue date is not a target-grid flood mask or a
29July observation. Existing unusual projection metadata remains unrepaired.
The29July SAR scene cannot inherit26/28July water truth without independent
temporal verification.

[NRSC's general satellite service](https://www.nrsc.gov.in/nrscnew/Services_Bhuvan_SatelliteDataServices.php)
advertises23.5m LISSIII and56m AWiFS archives with a two-year lag. This does not
identify the exact disaster scene or grant rights over WorldView/Charter material.
The for-official-use notices, original imagery rights, exact payload size and
native quality/permanence masks remain unresolved. No official map was digitized
or restricted administrative geometry exported. New Belagavi native raster
acquisitions and eligible labels: **zero**.

## Udupi historical GFD references

The immutable research material retains event2728,14–30September2005,33 positive
composite cells; and3551,25September–12October2009,23 positive composite cells.
These56 positive event-window cells remain historical research evidence. The
[GFD catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)
documents MODIS250m detection, three-day composites, maximum event extent,
clear-view counts and JRC permanent-water masking, under CC BY-NC4.0. A30m export
does not improve native resolution. Event duration/date and clear-view totals
do not recover exact individual acquisition times or complete interval absence.

Bounded NASA metadata recovered:

- `MOD09GQ.A2005257.h25v07.061.2020245185739`, catalogue size40.3153MB;
- `MOD09GQ.A2009268.h25v07.061.2021142075429`, catalogue size39.7163MB.

These are daily Terra surface-reflectance **v061**, not confirmed original GFD
V006 inputs. Catalogue00:00–23:59:59 intervals represent daily products, not an
actual sensing clock. Original Terra/Aqua input lineage, MOD09GA/GQ bands and QA,
cloud/shadow/clear observation, original acquisition/pixel time, registration,
permanence and independent event timing must be recovered before daily labels.
No MODIS raster or new GFD negative was generated.

## Prediction-target review

The frozen Phase12D **250m/next24h/2,500m²** proposal remains unapproved. It is
not justified by these products:0.25ha is below OPERA's documented open-water
domain; native pixel spacing does not validate patch sensitivity; composites
and sparse passes do not establish full-day absence. Even an independently
verified timed positive would not create matching daily negatives automatically.

| Target | What validates it | Current decision |
|---|---|---|
| Temporary floodwater at acquisition | Actual sensing interval, native georeferencing, validated permanence/detection/quality, independent observed outcome | Source-class screening only; no verified flood outcomes |
| Temporary inundation anywhere in following24h | Independently timed target patch for positive; capable reviewed observation over complete unit and interval for negative; inputs available before issue | NO-GO; no defensible interval negatives or complete feature joins |
| Measured discharge exceeds justified flood threshold within horizon | Verified station/reach and measurements, compatible threshold/units, within-window cadence/QC, historical issued/reforecast input lineage | NO-GO; measurement semantics/threshold/identity/history unresolved |

**Recommended first satellite forecast proposal:** whole fixed1km cells in the
existing public Udupi window, origin(0,0), issued exactly24h before an acquisition
scheduled and archived before issue. Target a temporary unobstructed open-water
patch **exceeding3ha and at least200m wide inside the unit at that future
acquisition**. These are proposed domain limits requiring local validation,
not independently approved scientific thresholds. The complete sensing interval
must fit a predeclared, proposed±5minute schedule tolerance. Adequately observed
absence applies only to that acquisition and complete unit, never the intervening
day. Unknown/obstructed/incomplete/permanence-unresolved observations are censored.

This preserves a genuine future target while reducing unsupported temporal
claims. It is an observable open-water pilot towards the Karnataka objective,
with separate regional validation needed before geographic expansion. It cannot
claim all flooded vegetation, urban drainage, under-building or small-patch floods.
No acquisition classifier was trained or advertised as a forecast.

Independent review must approve the target, contemporary seasonal/permanent-water
baseline, local omission/commission and registration limits, positive and
adequately observed dry cohorts, rights, physical-event independence and sample
adequacy. Hold out complete events, later time blocks and distinct Karnataka
geographies, with an embargo for overlapping feature/outcome windows. Evaluate
precision/recall, false alarms, misses, calibration/Brier score and uncertainty
against persistence/climatology and relevant physical baselines. Archive issue,
run, publication/availability, valid interval and version for every predictor.
Later reanalysis or target-window observations cannot masquerade as historically
available predictors. Suitable reforecast studies require a separate approved
retrospective protocol and must distinguish later-generated reforecasts from
historically issued forecasts and live deployment skill.

## Riverine readiness and precise missing measurements

Current bounded CWC/NWDP pages were compared with7October originals. Their visible
metadata text is unchanged. JavaScript's IST adjustment describes the webpage
update display, not measurement timezone; occurrences of “UTC” inside “Kutch”
are not timestamp evidence. Metre units and separate `RL_of_zeroGauge`/
`MeanSeaLevel` fields still do not define the measured-level datum. Current CWC
metadata index does not supply record-specific correction/relocation/time/QC
clarification. No old hydro data or eligibility was rewritten.

| Station | CWC ID | Retained level rows | Discharge rows | Caveated daily-discharge subset |
|---|---|---:|---:|---:|
| Sadalga | CW1KRU000083 | 552 | 27 | 2 |
| Gokak Falls | CW1KRU000212 | 573 | 2 | 0 |
| Huvinahedgi | CW1KRU000339 | 517 | 26 | 12 |

Coverage is25July–20August2019:1,697 source observations,14 caveated eligible
daily rows,81 comparisons and33 retained disagreements. Apparent24-count days
do not establish scheduled hourly completeness. Station coordinates/relocations,
Gokak's river/model reach, timezone, timestamp meaning, instantaneous versus
aggregation semantics, measured/computed/discarded QC and datum history remain
unresolved. Published warning/danger/HFL stage levels are not currently compatible
with the exact NWDP field. No flood-justified **discharge** threshold is verified.
An arbitrary percentile or GloFAS return-period percentile is not measured flooding.

The retained GloFAS pilot has **806 modelled cell-day rows**,13 candidate cell
series,62 time steps and zero measured/model comparisons. Sadalga and Huvinhedgi
have limited model-grid screening support; Gokak remains ambiguous. Modelled
LISFLOOD discharge is not measured CWC discharge. The current
[historical overview](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview)
now states v5.0 operational, released15July2026; the frozen earlier download
schema's pre-operational designation is not silently overwritten. The current
[reforecast overview](https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast?tab=overview)
still describes v4.0,00UTC Monday/Thursday initialization,24h means,46day lead and
2003–2022 reference years. Verify the actual native schema/version before a
request. v4 reforecasts and retained v5 historical output are not interchangeable;
a daily mean cannot validate an instantaneous within-window maximum.

Required additional evidence is specific:

1. Authoritative dated station/reach coordinates and relocation history, including
   Sadalga's changed metadata and Gokak's unresolved model inflow/reach position.
2. Continuous hourly or finer **measured** level/discharge across multiple wet/dry
   seasons and independent floods, with explicit sampling schedule, timezone,
   acquisition/aggregation intervals, original QC, observed/computed/discarded
   markers, revisions and record lineage. Sampling must resolve the proposed
   threshold crossings; missing periods remain UNKNOWN.
3. Gauge-zero/benchmark datum and change history; approved warning/danger levels
   in the same datum. For a discharge target, an independently flood-justified
   m³/s threshold and valid dated rating curves with high-flow extrapolation/
   uncertainty if converting measured stage. Stage danger crossing is a distinct
   river-risk target and cannot certify district flood extent without inundation
   linkage.
4. Independently documented threshold/flood episodes and adequately monitored
   below-threshold intervals; resolve the33 source disagreements without choosing
   a preferred source by convenience.
5. Historically issued forecast runs/publication and valid intervals, or explicitly
   qualified suitable reforecasts with initialization/forcing cutoff, ensemble
   lead, matching model version, calibration participation and temporal meaning.
   The supplied historical NetCDF has no original request/job/availability receipt.
6. Resource-specific usage permission and clarification of NWDP/CWC policy
   conflicts. Detailed observations, coordinates and comparisons remain local;
   no unsent clarification package was transmitted.

**Possible pilots:** Udupi supports source-class and georeferencing/permanence
investigation; Belagavi/Athani supports official-event/native-SAR linkage research;
Sadalga/Huvinhedgi support conditional riverine feasibility work. None currently
supports an independently evaluated flood forecast. Gokak additionally needs
reach resolution. Other Karnataka districts have zero new eligible labels here;
no district-wide observation coverage is inferred from these windows or footprints.

## Deferred downloads, validation and delivery

The concrete acquisition plan records exact IDs, available checksums, rights,
purpose and disk budget. Two original OPERA packages would require6,702,352 source
bytes,107,164,800 uncompressed four-band bytes and an initial512MiB working reserve.
The three Sentinel-1 catalogue sizes total **5,119,244,656 bytes**; an initial
conservative20GiB working reservation covers source/extraction/intermediates,
subject to actual transfer/unpacked-size verification. **Neither transfer is
authorized.** NRSC exact native IDs/volume and a scientifically valid GloFAS
reforecast request remain unknown. Substantial transfers require a separate,
concrete user authorization and would not themselves clear independent label
gates. No unnecessary large transfer was requested or performed.

Reproduce the completed audit offline:

```bash
scripts/.venv/bin/python -B scripts/acquire_direct_observation_metadata.py validate
scripts/.venv/bin/python -B scripts/audit_direct_flood_observations.py validate --public docs/phase12e
PYTHONPATH=data/working/groundsource_runtime_v1 backend/.venv/bin/python -B -m pytest -q tests
backend/.venv/bin/python -B -m pytest -q backend/tests -k 'not real_training_reproduction' -o faulthandler_timeout=120
```

`build` refuses an existing version. Validation checks input/code/receipt/output
hashes and reproduces all observation/product/count outputs read-only. Metadata
and preview `fetch` commands refuse retained versions; they are not necessary
for validation and must not be rerun to overwrite sources. A fresh clone lacks
ignored source products; acquire only within a separately recorded approved scope
or provide retained originals. Public metadata do not substitute for those bytes.

Tests cover source-code masks, potential/moderate water, contradictory bands,
explicit valid zeros, missing pixels, temporal semantics, geographic disagreement,
native-grid/volume constraints, source checksums, redirects/authentication,
truncation and immutable retention. Application regression excludes the existing
rainfall-fitting reproduction test deliberately; saved-model validation remains
read-only. Source checks include IFI, GFDv2/v3/v4, hydrology reconciliation/semantics/
closures, GloFAS, SAR incidence/calibration/pilot, Udupi history, saved rainfall,
outcome foundation, feasibility, SOI and frozen Phase12C/12D. Exact final results
and protected-file verification are recorded chronologically in root `update.md`.

Git contains only new audit/acquisition code, isolated tests, documentation and
small permitted native metadata/aggregate receipts. Original rasters, government
polygons, PDFs, detailed hydrology, credentials, unrelated environment changes and
`QandA.md` are excluded. Independent scientific approval and genuine positive/
negative outcome evidence remain prerequisites; passing software tests is not GO.
