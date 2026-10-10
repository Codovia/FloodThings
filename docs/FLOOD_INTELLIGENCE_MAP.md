# Karnataka Flood Intelligence Map — Sprint 11

`/flood-map` is an evidence viewer, not a current-flood or susceptibility prediction. All 31 district names are selectable using the existing versioned NIC directory (file or explicitly configured PostgreSQL backend). Current-LGD reconciliation remains unresolved. District filtering never fuzzy-matches names, creates centroids or substitutes another district. Only Udupi and Dakshina Kannada have reviewed public navigation bounds; the other 29 districts retain the previous map view when selected. Bounds support navigation, not district-wide weather or certified current boundaries.

## Eligible display inventory

| Evidence | Public geometry | Interpretation and handling |
| --- | --- | --- |
| Udupi GFD 2728, 14–30 September 2005 | 33 original retained cell polygons | Observation-qualified event-window maximum mapped non-permanent water |
| Udupi GFD 3551, 25 September–12 October 2009 | 23 original retained cell polygons | Same semantics; separate event identity, no invented settlement points |
| Other GFD positive scopes, observed-zero comparisons and insufficient-observation scopes | No additional reviewed public spatial product enabled | Preserve all research statuses; observed-zero is not a general negative label and insufficient observation remains unknown |
| IFI recovered catalogue | Not enabled as map geometry | All 494 Karnataka records retain unresolved current geographic mappings; approximate/documentary locations are not converted into verified locality coordinates |
| Potential flood-prone zones | Zero registered verified polygons | Explicit unavailable layer; neither historical cell geometry, elevation, rivers nor rainfall is promoted into a hazard zone |
| Drainage context | Existing 3 km × 3 km Udupi study window, terrain/land-cover previews | OSM snapshot returned **zero** drain/ditch ways; this does not establish absence of drainage. No statewide waterways collection is enabled |
| Shelter entrances | Only current, verified Open assignments with spare capacity, queried on user toggle | Existing verification expiry, live/demonstration separation and empty/error states apply; no operational records are seeded |

The map defaults to both public historical events: **56 cells / two events / one district**. Cells are not independent flood events and cannot define daily occurrence. The event selector can show either reviewed event. The original vertices and geometry types are unchanged; stable IDs use event + original grid row/column. Detail responses include the original geometry-file SHA-256. Clicking a polygon selects evidence, not a weather location; background clicks select an independently labelled weather point. A keyboard cell selector provides equivalent detail access. No cell automatically becomes a supported AI locality.

## Provenance and display permissions

- [Global Flood Database V1 catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1), Cloud to Street / Dartmouth Flood Observatory; Tellman et al. (2021), DOI 10.1038/s41586-021-03695-w. **CC BY-NC 4.0**, attribution and non-commercial use required. Catalogue reviewed 10 October 2026. Description documents 250 m MODIS classification; the current catalogue band table labels 30 m. This application retains the established **250 m processing grid**, original exports and verified grid recovery; it does not reinterpret the grid from that inconsistent table. Event-window maximum is not a precise flood boundary or a village position.
- Udupi boundary: [geoBoundaries ADM2 v6 catalogue](https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2), William & Mary geoLab, **CC BY 4.0**, reviewed 10 October 2026. Modern district context is not independently verified as a historical administrative boundary. No SOI geometry or derivative is served.
- District names and navigation metadata retain the existing directory v2 provenance. Dakshina Kannada bounds have their separate gbOpen **ODbL 1.0** provenance; they are not relabelled as CGAZ/CC BY data.
- Drainage source references, download timestamps, licences, attribution and liability notice are retained in the existing `udupi_drainage_gis_v1` manifest/API: Copernicus WorldDEM-30, ESA WorldCover 2021 (CC BY 4.0), and OpenStreetMap (ODbL 1.0). A mapped drainage feature would remain geometry-only, with overflow risk not established. Capacity, condition, blockage, hydraulic direction and network completeness are unknown.

The two immutable source products retain their existing manifests/checksums; Sprint 11 adds a versioned API view (`karnataka_flood_intelligence_v1`), not a replacement source dataset. Source loaders verify checksums, identities, observation quality and licences before serving. Source rows, rasters, manifests and trained-model artifacts are unchanged. Original research and restricted geometry stay local. Commercial reuse is not authorized by the GFD non-commercial licence.

## API contracts

| GET endpoint | Behavior |
| --- | --- |
| `/api/flood-map/districts` | 31 stable NIC identities and explicit public geometry/drainage/hazard coverage; unavailable geometry counts are null, not a claimed zero observation |
| `/api/flood-map/historical?district_id=…&event_id=…&limit=200&offset=0` | Original CRS84 cell polygons enriched with evidence metadata; separate category, source, event dates, unknown mechanism, checksum and coverage |
| `/api/flood-map/hazards?district_id=…` | Independent empty GeoJSON with `status=unavailable`, no source and the explicit no-verified-dataset message |
| `/api/flood-map/drainage?district_id=…` | Existing bounded Udupi context, or explicit unavailable; never hazard geometry or overflow prediction |
| `/api/flood-map/features/{feature_id}` | Exact historical feature and its limitations; no inferred nearest locality or automatic model inference |

Unknown IDs return 404; malformed/beyond-bound parameters 422; source corruption/unavailability 503. Historical results have a maximum page size of 200 (current full collection 56), deterministic ordering and stable IDs. Missing/corrupt database configuration has no silent file fallback. These endpoints are public read-only and make no external source request or database write. Existing geographic, weather, admin and shelter contracts remain available.

## Mechanisms and scientific safeguards

The detail UI supports riverine, pluvial/urban waterlogging, flash, coastal and unknown vocabularies. **Every currently displayed cell is Unknown/unverified**, with no supporting mechanism source. A future verified mechanism requires reviewed event-specific provenance; proximity to rivers/drains, rain amounts or terrain is insufficient. No risk severity or calibrated probability is assigned.

Historical observation masks and clear-view support remain visible. Missing evidence is unknown, not non-flood. No flood-negative labels, new hydrology extraction, training or automatic warnings are created. The experimental rainfall model remains separate, with unchanged precision 14.50%/recall 91.67%, and is not a flood classifier. Historical GloFAS is not live discharge. Water-level datum, temporal alignment, SOI restrictions and Gokak ambiguity remain unchanged.

## Demonstration

1. Open `/flood-map`; choose **Udupi**, or retain statewide view. Use **Zoom to mapped water** and select an observed polygon or the keyboard cell selector.
2. Inspect exact event dates, original geometry meaning, observation quality, mechanism Unknown, licence, checksum and limitations. Close details and select another cell/event.
3. Enable **Potential Flood-Prone Zones** independently. Its explicit unavailable state does not remove historical polygons.
4. Select **Kolar** or another district without eligible public geometry. Confirm the empty public-evidence state, unknown flood absence and disabled district zoom when bounds are unavailable. Return statewide; layer choices remain.
5. Enable **Drainage / waterways**. Udupi displays the bounded study outline and zero mapped drain-way notice; expand the existing research controls for actual retained raster previews. Other districts show unavailable context.
6. Enable **Verified shelters**. Only current public-approved entries could be shown, with district filtering and verification expiry. The operational directory currently remains empty; directions and public management remain on the dedicated Shelters page.
7. Navigate to Weather & AI for the selected independent point; existing weather/AI/freshness functionality is preserved. No flood-safety claim follows from map selection.

Next priority: presentation rehearsal and actual authorized shelter provisioning/verification where appropriate. Broader hazard or historical geographic coverage requires a separately reviewed, reusable source; it is not fabricated to fill the map.
