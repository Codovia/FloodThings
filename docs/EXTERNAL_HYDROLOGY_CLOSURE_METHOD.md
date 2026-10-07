# Stage 4F — External hydrology evidence closure

This stage completes a bounded public-source investigation, not hydrological feature engineering. The result is `external_hydrology_closure_complete_with_unresolved_items`. Neither a canonical Gokak model cell nor an exact NWDP daily temporal dictionary was established. No quantitative measured/modelled pairs, performance metrics, features or labels were created. Stage 4A–4E remains immutable.

## Scope and reproducibility

Research on 7 October 2026 used 24 declared searches covering exact station/code/site/history/map/basin terms and exact discharge/acquisition/dictionary/API/manual terms. Eight public source artifacts were retrieved once, with 30-second HTML or 60-second PDF deadlines and 2 MiB/32 MiB ceilings. No authenticated source access, new observations, model downloads or messages occurred. Search queries, retrieval receipts, original bytes, hashes and reviewed page findings remain in `data/raw/reference/stage4f_v1/`. Closure describes the limit of this accessible public scope; it does not establish that unpublished documentation is absent.

The previously failed Stage 4A basin-report download was already recorded as truncated at its 8 MiB ceiling. Its bytes were preserved. A separate complete official report was retrieved for this stage. The initial web-tool timeout/401 for two PDFs was distinguished from the successful bounded ordinary public downloads of those same URLs. No restricted access was bypassed.

The offline script `scripts/close_external_hydrology.py` builds `data/working/karnataka_external_hydrology_closure_v1/`, rejects an existing output version, and validates hashes and deterministic source-to-product reproduction without rewriting inputs or outputs. It checks the Stage 4E validator, retained source receipts, inspected PDF pages, exact Preview fields and published catalogue metadata. Interpretations remain explicit human-reviewed evidence, not automatic inference from field labels. The public manifest publishes references, hashes, aggregate classifications and a usage matrix only. Source PDFs, detailed coordinates and evidence remain local under existing conservative reuse policy.

## Gokak gauge/reach evidence

The [CWC station inventory as of 1 June 2012](https://cwc.gov.in/sites/default/files/hydrological-network-details-of-cwc.pdf), PDF 88/printed 54, and [CWC September 2020 HO station book](https://cwc.gov.in/sites/default/files/ho-book-2020compressed-edited-latest.pdf), PDF 196/printed 186, both associate Gokak with Ghataprabha and a 2,770 km² catchment. Their coordinates differ. The older code is retained as historical context, without inventing a code crosswalk, relocation or canonical coordinate. The 2020 office-use-only document stays local.

The [India-WRIS/CWC/NRSC Krishna Basin report, Version 2.0](https://indiawris.gov.in/downloads/Krishna%20Basin.pdf), PDF 20, 66, 68 and 162, provides river, station inventory and basin-map context. Its publication date is not established by the inspected cover; file modification dates are not substituted. Map 20 (PDF 68/printed 60) has basin-wide extent and a 100 km scale bar. The previously retained [CWC Krishna basin map](https://cwc.gov.in/sites/default/files/admin/Krishna-kgbo-map.pdf), PDF 1, is also an overview and warns that not all sites can be shown at its scale. Neither map was georeferenced to pretend it distinguishes adjacent 0.05° model cells or an exact gauge cross-section.

Stage 4E v5 static evidence remains unchanged: the western candidate drains into the eastern candidate, where three model-channel branches converge. Both are explicit in the local package. Upstream area, distance and connected topology support investigation but do not locate the physical gauge on a particular side of that model junction. No river name was invented for a model branch. No discharge magnitude or timing was used for selection.

Final class: `gokak_reach_externally_unresolved`; selected cell: null; model match: `station_grid_match_ambiguous`. The separate `coordinate_conflict_unresolved` remains unchanged.

## NWDP temporal evidence

The [exact Karnataka CWC resource](https://nwdp.nwic.gov.in/dataset/river-discharge-manual-dailly-central-water-commission-cwc/resource/f95150ea-c8fc-4740-8815-d9c34c9d53a3), its published Preview, and advertised catalogue API were retrieved successfully. Dataset ID: `08fa3fd0-7861-471d-a295-27c1b239d1fa`; resource ID: `f95150ea-c8fc-4740-8815-d9c34c9d53a3`. Data update: `2026-01-24T23:36:31.332749`; metadata update: `2026-01-25T03:26:18.320179`. These are portal/resource updates, not measurement timezone or historical publication times. The exact discharge/acquisition columns are exposed as text, without statistic, timezone, timestamp-role or interval definitions. No resource data dictionary or schema definition was supplied by the inspected catalogue. Generic [NWDP API help](https://nwdp.nwic.gov.in/en/dataset_api/home_api_page) adds no exact field definitions. An IST clock in portal JavaScript belongs to display-update handling; it is not an observation dictionary.

The [CWC Handbook for Hydrometeorological Observations, January 2017](https://cwc.gov.in/sites/default/files/final-hm-handbook-jan-2017.pdf), section 4.6, PDF 45/printed 43, describes RD-1 observations at 08:00 and subsequent e-SWIS entry and Year Book processing. This is relevant pre-2019 procedural context. It does not prove what statistic the exact NWDP export stores, whether its timestamp is a session, reporting time or interval boundary, its timezone, or equivalence to the retained 2019–20 Year Book revision. Stage 4E's Year Book and 2020 handbook findings remain intact.

| Exact NWDP attribute | Classification | Missing evidence |
| --- | --- | --- |
| Value semantics | unresolved | Exact field statistic/method, rather than a general measurement procedure |
| Timezone | unresolved | Observation timezone, rather than a portal clock |
| Timestamp meaning | unresolved | Definition of Data Acquisition Time |
| Aggregation window | unresolved | Whether aggregated and, if so, exact bounds |
| Year Book equivalence | unresolved | Exact field/time/record lineage correspondence |

Overall: `nwdp_temporal_semantics_externally_unresolved`. This narrower exact-export classification does not erase Stage 4E's partially resolved general procedural context. Original GloFAS preceding-24-hour mean/end-of-period UTC semantics remain separate and unchanged. Quantitative aligned pairs remain zero. Neither daily frequency nor an 08:00 schedule defines a 24-hour mean, IST or a period-end timestamp.

## Stage 5 usage decision

The public manifest and local `stage5_hydrology_usage_matrix.json` contain the machine-readable decision matrix. Stage 5 may design independently identified GloFAS modelled context for supported Sadalga and Huvinhedgi cells, with coordinate/version/calibration caveats; leakage-controlled rainfall antecedents; and independently validated static context. Source availability at prediction time must still be established. These permissions allow planning around the two unresolved questions; they do not authorize automatic feature extraction in Stage 4F or ML training.

Stage 5 must exclude canonical Gokak discharge, quantitative CWC/GloFAS comparisons and calibration claims, unresolved-datum water-level thresholds, automatic within-station water-level features without method review, assumed instantaneous historical availability, substitution of model values for measured gaps, and missing-to-negative labels. Measured CWC/NWDP, published Year Book and modelled GloFAS remain distinct source classes. Preserve 1,697 source observations, 81 reconciliation cases, 14 quality-caveated eligible rows and 33 disagreements.

## Unsent clarification template

Prepared for manual delivery only; no message was sent. The local package references the prior Stage 4C2 request and contains the exact resource/station IDs and source URLs.

1. CWC: For Gokak Falls `CW1KRU000212`, provide canonical dated gauge/cross-section coordinates, coordinate-correction or relocation history, and a site map identifying whether the 2019 gauge is upstream/downstream of the relevant Ghataprabha tributary junction. A model-cell match must not be confused with coordinate-history resolution.
2. CWC/NWIC: For resource `f95150ea-c8fc-4740-8815-d9c34c9d53a3`, define the exact manual-daily discharge statistic/method and any observed/computed flags; establish whether and how it corresponds to Year Book values.
3. CWC/NWIC: Define Data Acquisition Time's role and timezone; if the value is an aggregate, provide exact daily interval bounds. Distinguish observation fields from portal upload/update timestamps.

Next stage: a bounded Stage 5 research-feature methodology and prediction-time availability review for supported modelled cells and antecedent rainfall/static context, with these exclusions carried forward. Further closure of these two questions requires a specific new authoritative dictionary or gauge-site record, not repeated public searches.
