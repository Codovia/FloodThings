"""Read-only point weather using the existing validated seven-day weather contract.

User coordinates are not district identities. No persistence, geocoding, risk
classification or scientific dataset writes occur here.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from .weather import API_URL, PARAMS, WeatherUnavailable, number, parse_weather


def selected_location(latitude: float, longitude: float) -> dict:
    return {
        "name": "Selected coordinates",
        "latitude": latitude, "longitude": longitude,
        "source_url": None, "source": "user_selected_wgs84_coordinates",
        "administrative_identity_status": "not_verified",
    }


async def fetch_point_weather(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict:
    """Use one bounded provider call; preserve requested and provider-grid positions."""
    try:
        latitude = number(latitude, minimum=-90, maximum=90)
        longitude = number(longitude, minimum=-180, maximum=180)
        if latitude is None or longitude is None:
            raise ValueError("Both coordinates required")
        params = {**PARAMS, "latitude": latitude, "longitude": longitude}
        async with asyncio.timeout(10):
            response = await client.get(API_URL, params=params)
        response.raise_for_status()
        body = parse_weather(response.json(), datetime.now(timezone.utc))
        if any(value is None for value in body["grid_location"].values()):
            raise ValueError("Provider grid coordinates unavailable")
        return {**body, "location": selected_location(latitude, longitude),
                "prediction_status": "not_available",
                "prediction_message": "Flood prediction target and label methodology are not yet validated."}
    except (httpx.HTTPError, TimeoutError) as exc:
        raise WeatherUnavailable("Weather provider could not be reached. Try again later.") from exc
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise WeatherUnavailable("Weather provider returned incomplete or invalid data.") from exc
