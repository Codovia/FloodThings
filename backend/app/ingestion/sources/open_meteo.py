"""
Open-Meteo weather and precipitation source adapter.

Ingests:
1. Operational weather & forecast from https://api.open-meteo.com/v1/forecast
2. Historical reanalysis precipitation from https://archive-api.open-meteo.com/v1/archive

Strict rules:
- Forecasts and observations are NEVER mixed.
- Past timestamps -> WeatherObservation & RainfallObservation.
- Future timestamps -> WeatherForecast.
- Units: °C (temperature), % (humidity), hPa (pressure), m/s (wind_speed), mm (rainfall).
- Raw API JSON is always preserved under data/raw/open_meteo/ before processing.
- Idempotent: checks existing source_id and source_record_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.geography import District
from app.db.models.weather import (
    RainfallObservation,
    WeatherForecast,
    WeatherObservation,
)
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)
from app.ingestion.validation import (
    DataCategory,
    QualityStatus,
    make_point_wkt,
    parse_utc_timestamp,
    validate_coordinates,
    validate_float,
)

RAW_OPEN_METEO_DIR = Path("data/raw/open_meteo")

# Default Karnataka monitoring points (lat, lon, name, district_code)
DEFAULT_LOCATIONS: list[dict[str, Any]] = [
    {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946, "district_code": "526"},
    {"name": "Belagavi", "lat": 15.8500, "lon": 74.5000, "district_code": "527"},
    {"name": "Mangaluru", "lat": 12.8700, "lon": 75.2500, "district_code": "535"},
    {"name": "Kalaburagi", "lat": 17.3300, "lon": 76.8300, "district_code": "539"},
    {"name": "Mandya", "lat": 12.5200, "lon": 76.9000, "district_code": "545"},
]


class OpenMeteoAdapter(BaseAdapter):
    """Adapter for Open-Meteo operational and historical weather data."""

    source_name = "Open-Meteo Weather API"
    organization = "Open-Meteo GmbH"
    source_url = "https://open-meteo.com"
    access_method = "REST_API"
    data_type = "METEOROLOGICAL"
    update_frequency = "HOURLY"

    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self, session: Session, raw_dir: Path = RAW_OPEN_METEO_DIR):
        super().__init__(session)
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        mode: str = "operational",
        locations: list[dict[str, Any]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        client: httpx.Client | None = None,
    ) -> IngestionResult:
        """Execute Open-Meteo ingestion.

        Args:
            mode: 'operational' (past 2 days + 3 days forecast) or 'historical' (archive reanalysis).
            locations: list of locations with 'lat', 'lon', 'name', optional 'district_code'.
            start_date: ISO date (YYYY-MM-DD) for historical mode.
            end_date: ISO date (YYYY-MM-DD) for historical mode.
            client: optional custom httpx.Client (useful for testing).
        """
        metrics = IngestionMetrics()
        started_at = datetime.now(timezone.utc)
        target_locations = locations or DEFAULT_LOCATIONS

        data_source = get_or_create_data_source(
            self.session,
            name=self.source_name,
            organization=self.organization,
            description="Operational weather, forecast, and historical reanalysis from Open-Meteo",
            source_url=self.source_url,
            access_method=self.access_method,
            data_type=self.data_type,
            geographic_coverage="Karnataka State",
            update_frequency=self.update_frequency,
            license_type="CC BY 4.0",
        )

        run = start_ingestion_run(self.session, data_source.id)

        # Pre-cache districts by code
        dist_stmt = select(District)
        districts = {d.code: d.id for d in self.session.execute(dist_stmt).scalars() if d.code}

        should_close_client = False
        if client is None:
            client = httpx.Client(timeout=30.0, verify=False)
            should_close_client = True

        try:
            for loc in target_locations:
                lat = loc["lat"]
                lon = loc["lon"]
                name = loc.get("name", f"{lat:.2f},{lon:.2f}")
                dist_code = loc.get("district_code")
                dist_id = districts.get(dist_code)

                coords = validate_coordinates(lat, lon, karnataka_only=False)
                if coords is None:
                    metrics.records_rejected += 1
                    metrics.errors.append(f"Invalid coordinates for {name}: lat={lat}, lon={lon}")
                    continue

                if mode == "historical":
                    self._ingest_historical_location(
                        client=client,
                        data_source_id=data_source.id,
                        lat=coords[0],
                        lon=coords[1],
                        location_name=name,
                        district_id=dist_id,
                        start_date=start_date or "2024-07-01",
                        end_date=end_date or "2024-07-03",
                        metrics=metrics,
                    )
                else:
                    self._ingest_operational_location(
                        client=client,
                        data_source_id=data_source.id,
                        lat=coords[0],
                        lon=coords[1],
                        location_name=name,
                        district_id=dist_id,
                        metrics=metrics,
                    )

            self.session.commit()
            status = "SUCCESS" if not metrics.errors else "PARTIAL"
            complete_ingestion_run(self.session, run, status=status, metrics=metrics)
            self.session.commit()

            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status=status,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
            )

        except Exception as exc:
            self.session.rollback()
            err_msg = str(exc)
            metrics.errors.append(err_msg)
            complete_ingestion_run(
                self.session, run, status="FAILED", metrics=metrics, error_message=err_msg
            )
            self.session.commit()
            return IngestionResult(
                source_name=self.source_name,
                run_id=run.id,
                status="FAILED",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
                error_message=err_msg,
            )
        finally:
            if should_close_client:
                client.close()

    def _ingest_operational_location(
        self,
        client: httpx.Client,
        data_source_id: uuid.UUID,
        lat: float,
        lon: float,
        location_name: str,
        district_id: uuid.UUID | None,
        metrics: IngestionMetrics,
    ) -> None:
        """Fetch and ingest operational forecast and recent observations."""
        retrieved_at = datetime.now(timezone.utc)
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation,weather_code",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
            "timezone": "UTC",
            "past_days": 2,
            "forecast_days": 3,
        }

        resp = client.get(self.FORECAST_URL, params=params)
        resp.raise_for_status()
        raw_json = resp.json()

        # 1. Raw Data Preservation
        ts_slug = retrieved_at.strftime("%Y%m%d_%H%M%S")
        raw_file = self.raw_dir / f"operational_{lat:.4f}_{lon:.4f}_{ts_slug}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, indent=2)

        hourly = raw_json.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])
        pressures = hourly.get("surface_pressure", [])
        wind_speeds = hourly.get("wind_speed_10m", [])
        wind_dirs = hourly.get("wind_direction_10m", [])
        precips = hourly.get("precipitation", [])

        geom = make_point_wkt(lat, lon)

        for i, time_str in enumerate(times):
            metrics.records_received += 1
            record_dt = parse_utc_timestamp(time_str, default_tz=timezone.utc)
            if record_dt is None:
                metrics.records_rejected += 1
                continue

            temp_c = validate_float(temps[i] if i < len(temps) else None, min_val=-50.0, max_val=60.0)
            hum = validate_float(humidities[i] if i < len(humidities) else None, min_val=0.0, max_val=100.0)
            press = validate_float(pressures[i] if i < len(pressures) else None, min_val=700.0, max_val=1100.0)
            ws = validate_float(wind_speeds[i] if i < len(wind_speeds) else None, min_val=0.0, max_val=150.0)
            wd = validate_float(wind_dirs[i] if i < len(wind_dirs) else None, min_val=0.0, max_val=360.0)
            precip_mm = validate_float(precips[i] if i < len(precips) else None, min_val=0.0, max_val=1000.0)

            # Strict rule: Past is OBSERVATION, Future is FORECAST
            if record_dt < retrieved_at:
                # 1. WeatherObservation
                w_rec_id = f"openmeteo_obs_{lat:.4f}_{lon:.4f}_{record_dt.isoformat()}"
                w_stmt = select(WeatherObservation).where(
                    WeatherObservation.source_id == data_source_id,
                    WeatherObservation.source_record_id == w_rec_id,
                )
                existing_w = self.session.execute(w_stmt).scalar_one_or_none()
                if existing_w is None:
                    w_obs = WeatherObservation(
                        id=uuid.uuid4(),
                        location_type="STATION_COORDINATES",
                        location_reference=location_name,
                        district_id=district_id,
                        observed_at=record_dt,
                        latitude=lat,
                        longitude=lon,
                        geometry=geom,
                        temperature=temp_c,
                        humidity=hum,
                        pressure=press,
                        wind_speed=ws,
                        wind_direction=wd,
                        weather_condition=None,
                        source_id=data_source_id,
                        source_record_id=w_rec_id,
                        retrieved_at=retrieved_at,
                        quality_status=QualityStatus.VALID,
                        data_category=DataCategory.MODEL_OUTPUT,
                    )
                    self.session.add(w_obs)
                    metrics.records_inserted += 1
                metrics.records_valid += 1

                # 2. RainfallObservation
                r_rec_id = f"openmeteo_rain_{lat:.4f}_{lon:.4f}_{record_dt.isoformat()}"
                r_stmt = select(RainfallObservation).where(
                    RainfallObservation.source_id == data_source_id,
                    RainfallObservation.source_record_id == r_rec_id,
                )
                existing_r = self.session.execute(r_stmt).scalar_one_or_none()
                if existing_r is None:
                    r_obs = RainfallObservation(
                        id=uuid.uuid4(),
                        station_id=location_name,
                        district_id=district_id,
                        observed_at=record_dt,
                        rainfall_mm=precip_mm,
                        duration_minutes=60,
                        latitude=lat,
                        longitude=lon,
                        geometry=geom,
                        source_id=data_source_id,
                        source_record_id=r_rec_id,
                        retrieved_at=retrieved_at,
                        quality_status=QualityStatus.VALID,
                        data_category=DataCategory.MODEL_OUTPUT,
                    )
                    self.session.add(r_obs)
                    metrics.records_inserted += 1

            else:
                # WeatherForecast
                f_rec_id = f"openmeteo_fcst_{lat:.4f}_{lon:.4f}_{record_dt.isoformat()}"
                f_stmt = select(WeatherForecast).where(
                    WeatherForecast.source_id == data_source_id,
                    WeatherForecast.source_record_id == f_rec_id,
                )
                existing_f = self.session.execute(f_stmt).scalar_one_or_none()
                if existing_f is None:
                    fcst = WeatherForecast(
                        id=uuid.uuid4(),
                        location_type="STATION_COORDINATES",
                        location_reference=location_name,
                        district_id=district_id,
                        issued_at=retrieved_at,
                        forecast_for=record_dt,
                        temperature=temp_c,
                        rainfall_probability=None,
                        forecast_rainfall_mm=precip_mm,
                        humidity=hum,
                        wind_speed=ws,
                        weather_condition=None,
                        source_id=data_source_id,
                        source_record_id=f_rec_id,
                        quality_status=QualityStatus.VALID,
                    )
                    self.session.add(fcst)
                    metrics.records_inserted += 1
                metrics.records_valid += 1

            self.session.flush()

    def _ingest_historical_location(
        self,
        client: httpx.Client,
        data_source_id: uuid.UUID,
        lat: float,
        lon: float,
        location_name: str,
        district_id: uuid.UUID | None,
        start_date: str,
        end_date: str,
        metrics: IngestionMetrics,
    ) -> None:
        """Fetch and ingest historical reanalysis records (Observations only)."""
        retrieved_at = datetime.now(timezone.utc)
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
            "timezone": "UTC",
        }

        resp = client.get(self.ARCHIVE_URL, params=params)
        resp.raise_for_status()
        raw_json = resp.json()

        # Raw Data Preservation
        ts_slug = retrieved_at.strftime("%Y%m%d_%H%M%S")
        raw_file = self.raw_dir / f"historical_{lat:.4f}_{lon:.4f}_{start_date}_{end_date}_{ts_slug}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, indent=2)

        hourly = raw_json.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])
        pressures = hourly.get("surface_pressure", [])
        wind_speeds = hourly.get("wind_speed_10m", [])
        wind_dirs = hourly.get("wind_direction_10m", [])
        precips = hourly.get("precipitation", [])

        geom = make_point_wkt(lat, lon)

        for i, time_str in enumerate(times):
            metrics.records_received += 1
            record_dt = parse_utc_timestamp(time_str, default_tz=timezone.utc)
            if record_dt is None:
                metrics.records_rejected += 1
                continue

            temp_c = validate_float(temps[i] if i < len(temps) else None, min_val=-50.0, max_val=60.0)
            hum = validate_float(humidities[i] if i < len(humidities) else None, min_val=0.0, max_val=100.0)
            press = validate_float(pressures[i] if i < len(pressures) else None, min_val=700.0, max_val=1100.0)
            ws = validate_float(wind_speeds[i] if i < len(wind_speeds) else None, min_val=0.0, max_val=150.0)
            wd = validate_float(wind_dirs[i] if i < len(wind_dirs) else None, min_val=0.0, max_val=360.0)
            precip_mm = validate_float(precips[i] if i < len(precips) else None, min_val=0.0, max_val=1000.0)

            # Historical is always an observation
            w_rec_id = f"openmeteo_hist_obs_{lat:.4f}_{lon:.4f}_{record_dt.isoformat()}"
            w_stmt = select(WeatherObservation).where(
                WeatherObservation.source_id == data_source_id,
                WeatherObservation.source_record_id == w_rec_id,
            )
            existing_w = self.session.execute(w_stmt).scalar_one_or_none()
            if existing_w is None:
                w_obs = WeatherObservation(
                    id=uuid.uuid4(),
                    location_type="STATION_COORDINATES",
                    location_reference=location_name,
                    district_id=district_id,
                    observed_at=record_dt,
                    latitude=lat,
                    longitude=lon,
                    geometry=geom,
                    temperature=temp_c,
                    humidity=hum,
                    pressure=press,
                    wind_speed=ws,
                    wind_direction=wd,
                    weather_condition=None,
                    source_id=data_source_id,
                    source_record_id=w_rec_id,
                    retrieved_at=retrieved_at,
                    quality_status=QualityStatus.VALID,
                    data_category=DataCategory.REANALYSIS,
                )
                self.session.add(w_obs)
                metrics.records_inserted += 1
            metrics.records_valid += 1

            r_rec_id = f"openmeteo_hist_rain_{lat:.4f}_{lon:.4f}_{record_dt.isoformat()}"
            r_stmt = select(RainfallObservation).where(
                RainfallObservation.source_id == data_source_id,
                RainfallObservation.source_record_id == r_rec_id,
            )
            existing_r = self.session.execute(r_stmt).scalar_one_or_none()
            if existing_r is None:
                r_obs = RainfallObservation(
                    id=uuid.uuid4(),
                    station_id=location_name,
                    district_id=district_id,
                    observed_at=record_dt,
                    rainfall_mm=precip_mm,
                    duration_minutes=60,
                    latitude=lat,
                    longitude=lon,
                    geometry=geom,
                    source_id=data_source_id,
                    source_record_id=r_rec_id,
                    retrieved_at=retrieved_at,
                    quality_status=QualityStatus.VALID,
                    data_category=DataCategory.REANALYSIS,
                )
                self.session.add(r_obs)
                metrics.records_inserted += 1

            self.session.flush()
