# DATA_SOURCES.md

**Project:** FloodPulse
**Status:** Updated following Phase 1 research. Source verification is complete.
- Authoritative Selection Matrix: See [FINAL_SOURCE_SELECTION.md](file:///home/pioneer/Projects/FloodPrediction/docs/FINAL_SOURCE_SELECTION.md).
- Detailed Adapter Ingestion Contracts: See [DATA_ACQUISITION_SPEC.md](file:///home/pioneer/Projects/FloodPrediction/docs/DATA_ACQUISITION_SPEC.md).
- Comprehensive 44-Source Inventory: See [DATA_SOURCE_INVENTORY.md](file:///home/pioneer/Projects/FloodPrediction/docs/DATA_SOURCE_INVENTORY.md).
- Empirical Test Evidence: See [DATA_SOURCE_VERIFICATION.md](file:///home/pioneer/Projects/FloodPrediction/docs/DATA_SOURCE_VERIFICATION.md).

---

## Source registration requirements

Every data source used by FloodPulse must record:

| Field | Description |
|---|---|
| Source name | Short identifier |
| Publisher / authority | Organization responsible for the data |
| URL | Official access URL or endpoint |
| Dataset / API | Specific dataset or API identifier |
| Coverage | What the data covers (rainfall, flood events, boundaries, etc.) |
| Geographic scope | Spatial extent (e.g., all-India, Karnataka, district-level) |
| Temporal coverage | Date range of available data |
| Update frequency | How often the source publishes new data |
| Access method | Open download, API, login-gated, etc. |
| License / terms | Usage license or terms of service |
| Retrieval timestamp | When the data was last retrieved |
| Data format | CSV, JSON, GeoJSON, NetCDF, Shapefile, GeoTIFF, etc. |
| Variables | Key fields / columns / bands |
| Units | Measurement units for each variable |
| Identifier fields | How records are uniquely identified |
| Quality limitations | Known gaps, biases, or coverage issues |
| Provenance | Chain of custody from source to FloodPulse |

---

## Source verification status values

```
CONFIRMED          — Accessed, format verified, Karnataka coverage confirmed, ready for adapter
ACCESS_PENDING     — Source identified but not yet tested
VALIDATION_PENDING — Accessible but fields/coverage not yet verified
CREDENTIAL_BLOCKED — Verified service requiring unobtained credentials
UNAVAILABLE        — Source does not provide what was expected or restricted to internal government logins
REJECTED           — Source evaluated and not suitable
```

No adapter is written against a source that is not `CONFIRMED`.

---

## Known source categories

### Flood event records

**India Flood Inventory (IFI)**
- Publisher: IIT Delhi HydroSense Lab
- Distribution: GitHub (`hydrosenselab/India-Flood-Inventory`), Zenodo
- Coverage: Historical flood events across India, 1967–2023
- Geographic scope: District-level, all-India (filterable to Karnataka)
- Format: CSV / GeoJSON
- Purpose: ML training target (positive labels for flood events)
- Status: **ACCESS_PENDING** — requires re-verification before integration

### Rainfall / weather

**IMD (India Meteorological Department)**
- Publisher: IMD, Pune
- Coverage: Daily gridded rainfall (historical), weather observations
- Geographic scope: All-India, 0.25° grid resolution
- Format: Binary / NetCDF (historical), various for current observations
- Purpose: Primary rainfall data for feature engineering
- Status: **ACCESS_PENDING** — requires verification of current access, format, and Karnataka extraction

**NASA POWER**
- Publisher: NASA Langley Research Center
- Coverage: Meteorological parameters derived from satellite/reanalysis
- Geographic scope: Global, point-level queries
- Format: JSON / CSV via API
- Purpose: Research/validation — supplementary weather data, not primary
- Status: **ACCESS_PENDING**

### Hydrology

**CWC — Central Water Commission**
- Publisher: CWC / NWIC (National Water Informatics Centre)
- Portal: National Water Data Portal (nwdp.nwic.gov.in)
- Coverage: River water levels, reservoir telemetry
- Geographic scope: Major rivers and reservoirs across India
- Format: CSV (portal exports)
- Purpose: River level and reservoir data for feature engineering
- Status: **ACCESS_PENDING** — portal access and Karnataka station coverage must be verified

**GloFAS (Global Flood Awareness System)**
- Publisher: Copernicus / ECMWF
- Coverage: River discharge forecasts
- Geographic scope: Global
- Format: NetCDF / GRIB via CDS API
- Purpose: Supplementary river discharge forecasts for validation
- Status: **ACCESS_PENDING**

### Administrative boundaries

**KGIS (Karnataka Geographic Information System)**
- Publisher: KSRSAC (Karnataka State Remote Sensing Applications Centre)
- Coverage: District, taluk, village boundaries
- Format: Shapefile / KML
- Purpose: Authoritative Karnataka administrative boundaries
- Status: **ACCESS_PENDING** — requires verification of current download availability

**LGD (Local Government Directory)**
- Publisher: Ministry of Panchayati Raj, Government of India
- Coverage: Administrative codes and names for all states/districts/subdistricts
- Format: API / CSV
- Purpose: Standardized district/taluk code normalization
- Status: **ACCESS_PENDING**

### Geospatial / terrain

**Survey of India / NRSC / Bhuvan**
- Publisher: Survey of India / NRSC
- Coverage: Terrain, administrative boundaries, satellite imagery
- Status: **ACCESS_PENDING** — some datasets are login-gated (e.g., NDEM). Must verify open vs restricted access per dataset.

**OpenTopography / SRTM**
- Publisher: NASA (via OpenTopography or direct USGS access)
- Coverage: SRTM 30m elevation data
- Geographic scope: Global (Karnataka extractable)
- Format: GeoTIFF
- Purpose: DEM for slope and elevation feature derivation
- Status: **ACCESS_PENDING**

### Karnataka state sources

**KSNDMC (Karnataka State Natural Disaster Monitoring Centre)**
- Access path: Via OpenCity (data.opencity.in) CKAN portal
- Coverage: District/taluk/hobli rainfall, telemetric stations
- Format: CSV / JSON / KML via CKAN API
- Purpose: Karnataka-specific rainfall and station data
- Status: **ACCESS_PENDING** — KSNDMC has no direct public API; access is through OpenCity

**Karnataka SDMA / DDMA**
- Coverage: Disaster management plans, shelter lists
- Status: **ACCESS_PENDING** — no confirmed public dataset or API

### Operational mapping

**OpenStreetMap**
- Publisher: OpenStreetMap community
- Coverage: Road networks, building footprints, POIs
- Purpose: Routing, shelter proximity calculations, facility locations
- Status: **ACCESS_PENDING** — open data, but routing service (OSRM/GraphHopper) must be evaluated

---

## Rules

1. No adapter is written against a row that is not `CONFIRMED`.
2. If access status changes, update this table in the same commit as the adapter.
3. Every retrieval must log timestamp, source URL, and response status.
4. No URLs should be invented or assumed — each must be verified against the actual source.
