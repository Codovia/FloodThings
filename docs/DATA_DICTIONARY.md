# DATA_DICTIONARY.md

**Project:** FloodPulse
**Status:** Conceptual planning document. No database schema or application models have been implemented.

This document defines the planned data concepts for FloodPulse. Final SQL schemas, column types, and constraints will be designed during database implementation phases.

---

## Administrative geography

### State
The Indian state. FloodPulse focuses on Karnataka.
- Key info: name, state code, geometry (MultiPolygon).

### District
An administrative district within Karnataka.
- Key info: name, district code (LGD), state reference, geometry (MultiPolygon), centroid.

### Taluk
A subdivision of a district.
- Key info: name, taluk code, district reference, geometry (MultiPolygon).

### Locality
A named locality, village, or ward within a taluk. Used for finer-grained reporting where data supports it.
- Key info: name, locality code, taluk reference, approximate geometry or centroid.

---

## Hydrology

### RiverBasin
A major river basin (e.g., Krishna, Cauvery, Godavari).
- Key info: name, basin code, geometry.

### SubBasin
A sub-basin within a major river basin.
- Key info: name, sub-basin code, parent basin reference, geometry.

### River
A named river or stream.
- Key info: name, basin/sub-basin reference, geometry (LineString/MultiLineString).

### RiverStation
A monitoring station on a river, operated by CWC or state agencies.
- Key info: station code, name, river reference, location (Point), operating agency, data source reference.

### RiverObservation
A timestamped water level or discharge measurement from a river station.
- Key info: station reference, observed_at (UTC), water_level_m, discharge_m3s, source, retrieved_at, quality/status.

### RiverForecast
A forecast of future river water level or discharge.
- Key info: station reference, forecast_for (UTC), issued_at (UTC), water_level_m, discharge_m3s, source, model/method.

### Reservoir
A reservoir or major dam.
- Key info: name, reservoir code, location (Point), full reservoir level, capacity, river reference, operating agency.

### ReservoirObservation
A timestamped storage/level reading from a reservoir.
- Key info: reservoir reference, observed_at (UTC), storage_mcm, level_m, inflow_m3s, outflow_m3s, source, retrieved_at.

---

## Weather

### WeatherObservation
A timestamped weather observation from a station or gridded source.
- Key info: location reference (station or grid cell), observed_at (UTC), temperature_c, humidity_pct, wind_speed_mps, wind_direction_deg, pressure_hpa, source, retrieved_at.

### RainfallObservation
A timestamped rainfall measurement for a location.
- Key info: location reference, observation_date, rainfall_mm, measurement_period, source, retrieved_at, quality/status.

### WeatherForecast
A forecast of future weather conditions.
- Key info: location reference, forecast_for (UTC), issued_at (UTC), forecast variables, source, model/method.

---

## Flood events and hazard

### FloodObservation
A recorded historical flood event from a legitimate inventory (e.g., IFI).
- Key info: event ID (source), start_date, end_date, duration_days, cause, affected districts, severity, area affected, casualties, damage description, source, source_record_id.

### FloodEvent
An aggregated or normalized flood event derived from one or more flood observations.
- Key info: event reference, spatial unit(s) affected, temporal extent, severity classification, provenance.

### FloodHazardZone
A spatially defined zone of cumulative flood hazard.
- Key info: zone geometry, hazard level, source (e.g., NRSC Flood Hazard Atlas), methodology, reference period.

---

## Terrain and land cover

### LandCover
Land use / land cover classification for a spatial unit.
- Key info: location reference, classification, source, reference date.

### WaterBody
A lake, tank, or other water body.
- Key info: name, type, geometry, district reference, source.

### TerrainDataset
A registered DEM or terrain derivative dataset.
- Key info: dataset name, source, resolution, CRS, spatial extent, acquisition date, processing method.

---

## Prediction

### PredictionGridCell
A spatial unit used for prediction (likely district or sub-district polygon).
- Key info: cell ID, geometry, district/taluk reference.

### FeatureSnapshot
A set of engineered features for a prediction unit at a point in time.
- Key info: grid cell reference, feature_date, feature values (rainfall metrics, terrain, hydrology, etc.), dataset_version.

### MLDatasetVersion
A versioned ML dataset constructed from feature snapshots and labels.
- Key info: version ID, creation date, feature schema, label definition, temporal range, spatial coverage, row count, class balance, provenance.

### MLModel
A registered trained model.
- Key info: model ID, version, algorithm, training dataset version, hyperparameters, training date, evaluation metrics, artifact path.

### FloodPrediction
An ML-generated flood risk prediction for a spatial unit.
- Key info: grid cell reference, prediction_for (date/period), risk_level, probability, model version, generated_at, confidence indicators.

---

## Emergency response

### EmergencyFacility
A shelter, hospital, fire station, police station, or other emergency facility.
- Key info: name, type, location (Point), address, district/taluk reference, capacity, contact info, source, verification status.

### CommunityReport
A citizen-submitted report of flooding, damage, or need.
- Key info: reporter reference, location (Point or approximate), report_type, description, timestamp, photos, verification_status (always starts UNVERIFIED), moderator notes.

---

## Alerts and notifications

### Alert
A generated alert based on prediction or official warning.
- Key info: alert_type (AI_PREDICTION vs OFFICIAL_WARNING), severity, spatial scope, temporal scope, message, issued_at, source, deduplication_key.

### TelegramSubscription
A Telegram chat/user registered for flood alerts.
- Key info: chat_id, subscription scope (district, taluk, etc.), created_at, active status.

---

## System

### User
A system user (citizen, admin, data manager).
- Key info: user ID, role, authentication details, created_at.

### AuditLog
A log of important administrative actions.
- Key info: actor reference, action, target, timestamp, details.
