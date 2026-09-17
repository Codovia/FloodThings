"""
Tests verifying strict idempotency across all FloodPulse data ingestion adapters.

Rule: running ingest() multiple times with identical source data must never
create duplicate observations or database entities.
"""

from unittest.mock import MagicMock
import pytest

from app.db.session import _get_session_factory
from app.ingestion.sources.geography import KarnatakaGeographyAdapter
from app.ingestion.sources.ifi_flood import IfiFloodAdapter
from app.ingestion.sources.nwic_reservoir import NwicReservoirAdapter
from app.ingestion.sources.nwic_river import NwicRiverLevelAdapter
from app.ingestion.sources.open_meteo import OpenMeteoAdapter


class TestIngestionIdempotency:
    """Test idempotent execution across all adapters."""

    def test_geography_idempotency(self):
        factory = _get_session_factory()
        with factory() as session:
            adapter = KarnatakaGeographyAdapter(session)
            res1 = adapter.ingest()
            assert res1.status == "SUCCESS"

            # Second execution must insert 0 records
            res2 = adapter.ingest()
            assert res2.status == "SUCCESS"
            assert res2.metrics.records_inserted == 0
            assert res2.metrics.records_updated == 0

    def test_cwc_river_idempotency(self):
        csv_data = """SlNo,Station,Agency,State LGD Code,State,District LGD Code,District,Tehsil,Block,Village,River,Basin,Tributary,Subtributary,SubSubtributary,Local River,Latitude,Longitude,Is_DischargeDataAvailable,RL_of_zeroGauge,MeanSeaLevel,Data Acquisition Time,River Water Level Manual Hourly (meter)
1,IDEMP_STN,CWC,29,Karnataka,544,Mandya,KRISHNARAJPET,-,-,Cauvery,Cauvery,Hemavathi,-,-,Hemavathi,12.50,76.40,Yes,745.00,745.00,01-01-2026 08:00,746.00
"""
        factory = _get_session_factory()
        with factory() as session:
            try:
                adapter = NwicRiverLevelAdapter(session)
                res1 = adapter.ingest(csv_content=csv_data)
                assert res1.status in ("SUCCESS", "PARTIAL")

                res2 = adapter.ingest(csv_content=csv_data)
                assert res2.status in ("SUCCESS", "PARTIAL")
                assert res2.metrics.records_inserted == 0
            finally:
                from sqlalchemy import text
                session.execute(text("DELETE FROM river_observations WHERE source_record_id LIKE '%IDEMP%'"))
                session.execute(text("DELETE FROM river_stations WHERE station_code = 'IDEMP_STN'"))
                session.commit()

    def test_nwic_reservoir_idempotency(self):
        csv_data = """Reservoir Name,Basin,"Sub 
Basin",River,Monitoring Date,Percentage Full,Reservoir Level (ft),Design Gross Capacity (TMC),Gross Capacity (TMC),"Live Capacity 
(TMC)",Live Above Cill (TMC),Inflow (Cusecs),Outflow to River (Cusecs),Canal Withdrawal (Cusecs),Evaporation (Cusecs),Cumulative Inflow (TMC),Cumulative Outflow (TMC),Cumulative Withdrawal (TMC),"Cumulative Evaporation 
(TMC)"
IDEMP_RES,Cauvery,Cauvery,Cauvery,01-01-2026 08:00:00,75.0,1500.0,50.0,40.0,30.0,20.0,1000,500,0,,10.0,1.0,1.0,
"""
        factory = _get_session_factory()
        with factory() as session:
            try:
                adapter = NwicReservoirAdapter(session)
                res1 = adapter.ingest(csv_content=csv_data)
                assert res1.status in ("SUCCESS", "PARTIAL")

                res2 = adapter.ingest(csv_content=csv_data)
                assert res2.status in ("SUCCESS", "PARTIAL")
                assert res2.metrics.records_inserted == 0
            finally:
                from sqlalchemy import text
                session.execute(text("DELETE FROM reservoir_observations WHERE source_record_id LIKE '%IDEMP%'"))
                session.execute(text("DELETE FROM reservoirs WHERE code = 'IDEMP_RES' OR name = 'IDEMP_RES'"))
                session.commit()

    def test_ifi_flood_idempotency(self):
        csv_data = """Unnamed: 0,UEI,Start Date,End Date,Duration(Days),Main Cause,Location,Districts,State,Latitude,Longitude,Severity,Area Affected,Human fatality,Human injured,Human Displaced,Animal Fatality,Description of Casualties/injured,Extent of damage ,Event Source,Event Souce ID,District_LGD_Codes,State_Codes
999,UEI-IDEMP-KA-001,01-07-2020 00:00,05-07-2020 00:00,4,Heavy Rain,,Mandya,Karnataka,12.52,76.90,Class 1,200.0,0,0,100,0,None,Minor inundation,IMD,ID_999,"545",29
"""
        factory = _get_session_factory()
        with factory() as session:
            try:
                adapter = IfiFloodAdapter(session)
                res1 = adapter.ingest(csv_content=csv_data)
                assert res1.status in ("SUCCESS", "PARTIAL")

                res2 = adapter.ingest(csv_content=csv_data)
                assert res2.status in ("SUCCESS", "PARTIAL")
                assert res2.metrics.records_inserted == 0
            finally:
                from sqlalchemy import text
                session.execute(text("DELETE FROM flood_observations WHERE source_record_id LIKE '%UEI-IDEMP-KA-001%'"))
                session.execute(text("DELETE FROM flood_events WHERE name LIKE '%UEI-IDEMP-KA-001%'"))
                session.commit()

    def test_open_meteo_idempotency(self):
        factory = _get_session_factory()
        with factory() as session:
            try:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "hourly": {
                        "time": ["2021-01-01T00:00"],
                        "temperature_2m": [22.0],
                        "relative_humidity_2m": [70.0],
                        "surface_pressure": [1013.0],
                        "wind_speed_10m": [2.5],
                        "wind_direction_10m": [90.0],
                        "precipitation": [0.0],
                    },
                }
                mock_client.get.return_value = mock_response

                adapter = OpenMeteoAdapter(session)
                loc = [{"name": "Idemp Loc", "lat": 12.9716, "lon": 77.5946, "district_code": "526"}]

                res1 = adapter.ingest(mode="operational", locations=loc, client=mock_client)
                assert res1.status in ("SUCCESS", "PARTIAL")

                res2 = adapter.ingest(mode="operational", locations=loc, client=mock_client)
                assert res2.status in ("SUCCESS", "PARTIAL")
                assert res2.metrics.records_inserted == 0
            finally:
                from sqlalchemy import text
                session.execute(text("DELETE FROM weather_observations WHERE location_reference = 'Idemp Loc'"))
                session.execute(text("DELETE FROM rainfall_observations WHERE station_id = 'Idemp Loc'"))
                session.execute(text("DELETE FROM weather_forecasts WHERE location_reference = 'Idemp Loc'"))
                session.commit()
