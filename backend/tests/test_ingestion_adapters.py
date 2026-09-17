"""
Unit tests for FloodPulse data ingestion adapters.

Verifies:
- Schema field mapping and parsing.
- Unit conversions (feet -> m, TMC -> MCM, cusecs -> m³/s).
- Separation of observations vs forecasts.
- Missing values preserved as NULL (missing != 0).
"""

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock
import pytest
from sqlalchemy import text

from app.db.models.flood import FloodEvent, FloodObservation
from app.db.models.geography import District, State
from app.db.models.hydrology import (
    Reservoir,
    ReservoirObservation,
    River,
    RiverBasin,
    RiverObservation,
    RiverStation,
)
from app.db.models.weather import (
    RainfallObservation,
    WeatherForecast,
    WeatherObservation,
)
from app.db.session import _get_session_factory
from app.ingestion.sources.geography import KarnatakaGeographyAdapter
from app.ingestion.sources.ifi_flood import IfiFloodAdapter
from app.ingestion.sources.nwic_reservoir import (
    CUSECS_TO_CUMECS,
    FEET_TO_METRES,
    TMC_TO_MCM,
    NwicReservoirAdapter,
)
from app.ingestion.sources.nwic_river import NwicRiverLevelAdapter
from app.ingestion.sources.open_meteo import OpenMeteoAdapter
from app.ingestion.validation import DataCategory


class TestNwicRiverAdapter:
    """Test CWC river stage parsing and normalization."""

    SAMPLE_CWC_CSV = """SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,Tehsil,Block,Village,River,Basin,Tributary,Subtributary,SubSubtributary,Local River,Latitude,Longitude,Is_DischargeDataAvailable,RL_of_zeroGauge,MeanSeaLevel,Data Acquisition Time,River Water Level Manual Hourly (meter)
1,AKKIHEBBAL,CWC,29,Karnataka,544,Mandya,KRISHNARAJPET,-,-,Cauvery,Cauvery,Hemavathi,-,-,Hemavathi,12.5986,76.4005,Yes,745.00,745.00,02-01-2026 08:00,747.53
2,AKKIHEBBAL,CWC,29,Karnataka,544,Mandya,KRISHNARAJPET,-,-,Cauvery,Cauvery,Hemavathi,-,-,Hemavathi,12.5986,76.4005,Yes,745.00,745.00,02-01-2026 09:00,747.60
"""

    def test_cwc_river_ingestion_and_units(self):
        factory = _get_session_factory()
        with factory() as session:
            adapter = NwicRiverLevelAdapter(session)
            res = adapter.ingest(csv_content=self.SAMPLE_CWC_CSV)

            assert res.status in ("SUCCESS", "PARTIAL")
            assert res.metrics.records_valid >= 2

            # Query inserted observation
            obs = (
                session.query(RiverObservation)
                .join(RiverStation)
                .filter(RiverStation.station_code == "AKKIHEBBAL")
                .order_by(RiverObservation.observed_at)
                .first()
            )
            assert obs is not None
            assert obs.water_level == 747.53
            assert obs.water_level_unit == "m"
            assert obs.discharge is None  # Zero fabrication: missing discharge remains NULL
            assert obs.quality_status == "VALID"
            assert obs.data_category == DataCategory.OBSERVATION
            assert obs.source_id is not None


class TestNwicReservoirAdapter:
    """Test NWIC reservoir telemetry unit conversions."""

    SAMPLE_RESERVOIR_CSV = """Reservoir Name,Basin,"Sub 
Basin",River,Monitoring Date,Percentage Full,Reservoir Level (ft),Design Gross Capacity (TMC),Gross Capacity (TMC),"Live Capacity 
(TMC)",Live Above Cill (TMC),Inflow (Cusecs),Outflow to River (Cusecs),Canal Withdrawal (Cusecs),Evaporation (Cusecs),Cumulative Inflow (TMC),Cumulative Outflow (TMC),Cumulative Withdrawal (TMC),"Cumulative Evaporation 
(TMC)"
Almatti Dam,Krishna,Middle Krishna,Krishna,08-06-2006 12:06:00,50.0,1676.755,123.081,35.364,17.744,31.544,17312,4700,0,,17.149,1.149,1.149,
"""

    def test_reservoir_unit_conversions(self):
        factory = _get_session_factory()
        with factory() as session:
            adapter = NwicReservoirAdapter(session)
            res = adapter.ingest(csv_content=self.SAMPLE_RESERVOIR_CSV)

            assert res.status in ("SUCCESS", "PARTIAL")
            assert res.metrics.records_valid >= 1

            obs = (
                session.query(ReservoirObservation)
                .join(Reservoir)
                .filter(Reservoir.code == "ALMATTI_DAM")
                .first()
            )
            assert obs is not None

            # 1. Level: feet -> metres
            expected_level_m = round(1676.755 * FEET_TO_METRES, 3)
            assert round(obs.water_level, 3) == expected_level_m

            # 2. Storage: TMC -> MCM
            expected_storage_mcm = round(35.364 * TMC_TO_MCM, 3)
            assert round(obs.storage, 3) == expected_storage_mcm

            # 3. Inflow: cusecs -> m³/s
            expected_inflow_m3s = round(17312 * CUSECS_TO_CUMECS, 3)
            assert round(obs.inflow, 3) == expected_inflow_m3s

            # 4. Outflow: cusecs -> m³/s
            expected_outflow_m3s = round(4700 * CUSECS_TO_CUMECS, 3)
            assert round(obs.outflow, 3) == expected_outflow_m3s

            assert obs.quality_status == "VALID"
            assert obs.data_category == DataCategory.OBSERVATION


class TestOpenMeteoAdapterSeparation:
    """Test strict separation of weather observations vs weather forecasts and reanalysis."""

    def test_operational_payload_separation(self):
        factory = _get_session_factory()
        with factory() as session:
            try:
                # Mock HTTP response with past and future timestamps
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.status_code = 200

                # 1 timestamp in the past (2020-01-01), 1 in the future (2035-01-01)
                mock_json = {
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "hourly": {
                        "time": ["2020-01-01T10:00", "2035-01-01T10:00"],
                        "temperature_2m": [26.5, 27.2],
                        "relative_humidity_2m": [65.0, 60.0],
                        "surface_pressure": [1012.0, 1011.5],
                        "wind_speed_10m": [3.5, 4.0],
                        "wind_direction_10m": [180.0, 190.0],
                        "precipitation": [5.2, 0.0],
                    },
                }
                mock_response.json.return_value = mock_json
                mock_client.get.return_value = mock_response

                adapter = OpenMeteoAdapter(session)
                res = adapter.ingest(
                    mode="operational",
                    locations=[{"name": "Test Op Loc", "lat": 12.9716, "lon": 77.5946, "district_code": "526"}],
                    client=mock_client,
                )

                assert res.status in ("SUCCESS", "PARTIAL")

                # Verify past record went to WeatherObservation & RainfallObservation with MODEL_OUTPUT
                past_dt = datetime(2020, 1, 1, 10, 0, tzinfo=timezone.utc)
                w_obs = session.query(WeatherObservation).filter_by(location_reference="Test Op Loc", observed_at=past_dt).first()
                assert w_obs is not None
                assert w_obs.temperature == 26.5
                assert w_obs.wind_speed == 3.5
                assert w_obs.data_category == DataCategory.MODEL_OUTPUT

                r_obs = session.query(RainfallObservation).filter_by(station_id="Test Op Loc", observed_at=past_dt).first()
                assert r_obs is not None
                assert r_obs.rainfall_mm == 5.2
                assert r_obs.data_category == DataCategory.MODEL_OUTPUT

                # Verify future record went to WeatherForecast
                future_dt = datetime(2035, 1, 1, 10, 0, tzinfo=timezone.utc)
                fcst = session.query(WeatherForecast).filter_by(location_reference="Test Op Loc", forecast_for=future_dt).first()
                assert fcst is not None
                assert fcst.temperature == 27.2
                assert fcst.forecast_rainfall_mm == 0.0
            finally:
                session.execute(text("DELETE FROM weather_observations WHERE location_reference = 'Test Op Loc'"))
                session.execute(text("DELETE FROM rainfall_observations WHERE station_id = 'Test Op Loc'"))
                session.execute(text("DELETE FROM weather_forecasts WHERE location_reference = 'Test Op Loc'"))
                session.commit()

    def test_historical_payload_separation(self):
        factory = _get_session_factory()
        with factory() as session:
            try:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.status_code = 200

                mock_json = {
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "hourly": {
                        "time": ["2019-07-01T00:00"],
                        "temperature_2m": [24.0],
                        "relative_humidity_2m": [80.0],
                        "surface_pressure": [1010.0],
                        "wind_speed_10m": [2.0],
                        "wind_direction_10m": [150.0],
                        "precipitation": [12.5],
                    },
                }
                mock_response.json.return_value = mock_json
                mock_client.get.return_value = mock_response

                adapter = OpenMeteoAdapter(session)
                res = adapter.ingest(
                    mode="historical",
                    locations=[{"name": "Test Hist Loc", "lat": 12.9716, "lon": 77.5946, "district_code": "526"}],
                    start_date="2019-07-01",
                    end_date="2019-07-01",
                    client=mock_client,
                )

                assert res.status in ("SUCCESS", "PARTIAL")

                hist_dt = datetime(2019, 7, 1, 0, 0, tzinfo=timezone.utc)
                w_obs = session.query(WeatherObservation).filter_by(location_reference="Test Hist Loc", observed_at=hist_dt).first()
                assert w_obs is not None
                assert w_obs.temperature == 24.0
                assert w_obs.data_category == DataCategory.REANALYSIS

                r_obs = session.query(RainfallObservation).filter_by(station_id="Test Hist Loc", observed_at=hist_dt).first()
                assert r_obs is not None
                assert r_obs.rainfall_mm == 12.5
                assert r_obs.data_category == DataCategory.REANALYSIS
            finally:
                session.execute(text("DELETE FROM weather_observations WHERE location_reference = 'Test Hist Loc'"))
                session.execute(text("DELETE FROM rainfall_observations WHERE station_id = 'Test Hist Loc'"))
                session.commit()


class TestIfiFloodAdapter:
    """Test India Flood Inventory historical ground truth parsing."""

    SAMPLE_IFI_CSV = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
101,UEI-TEST-KA-001,15-08-2018 00:00,20-08-2018 00:00,5,Heavy Rain,,Kodagu,Karnataka,12.42,75.74,Class 2,500.0,12,5,1000,20,Casualties,Severe landslides and inundation,IMD,ID_01,"542",29
"""

    def test_ifi_event_and_observation_creation(self):
        factory = _get_session_factory()
        with factory() as session:
            try:
                adapter = IfiFloodAdapter(session)
                res = adapter.ingest(csv_content=self.SAMPLE_IFI_CSV)

                assert res.status in ("SUCCESS", "PARTIAL")
                assert res.metrics.records_valid >= 1

                # Verify FloodEvent
                ev = session.query(FloodEvent).filter(FloodEvent.name.like("%UEI-TEST-KA-001%")).first()
                assert ev is not None
                assert ev.severity == "Class 2"
                assert ev.affected_area == 500.0
                assert ev.confidence == 1.0

                # Verify FloodObservation
                obs = (
                    session.query(FloodObservation)
                    .filter_by(source_record_id="ifi_UEI-TEST-KA-001_542")
                    .first()
                )
                assert obs is not None
                assert obs.flooded is True
                assert obs.flood_depth is None  # NEVER 0.0 — missing depth remains NULL!
                assert obs.confidence == 1.0
                assert obs.quality_status == "VALID"
                assert obs.data_category == DataCategory.HISTORICAL_EVENT
            finally:
                session.execute(text("DELETE FROM flood_observations WHERE source_record_id LIKE '%UEI-TEST-KA-001%'"))
                session.execute(text("DELETE FROM flood_events WHERE name LIKE '%UEI-TEST-KA-001%'"))
                session.commit()
