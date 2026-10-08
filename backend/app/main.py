from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .weather import OpenMeteoAdapter, WeatherUnavailable, unavailable
from .location_weather import fetch_point_weather, selected_location
from .historical import router as historical_router
from .drainage import router as drainage_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bounded upstream requests, with no retries, persistence or background jobs.
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
        app.state.weather = OpenMeteoAdapter(client)
        yield


app = FastAPI(title="FloodPulse", version="0.1.0", lifespan=lifespan)
app.include_router(historical_router)
app.include_router(drainage_router)


def get_weather(request: Request) -> OpenMeteoAdapter:
    return request.app.state.weather


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "floodpulse", "version": "0.1.0"}


@app.get("/api/weather")
async def weather(
    latitude: float | None = Query(None, ge=-90, le=90, allow_inf_nan=False),
    longitude: float | None = Query(None, ge=-180, le=180, allow_inf_nan=False),
    adapter: OpenMeteoAdapter = Depends(get_weather),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Supply both latitude and longitude.")
    try:
        if latitude is None:
            return await adapter.fetch()
        return await fetch_point_weather(adapter.client, latitude, longitude)
    except WeatherUnavailable as exc:
        body = unavailable(str(exc))
        if latitude is not None:
            body.update(location=selected_location(latitude, longitude), prediction_status="not_available")
        return JSONResponse(status_code=503, content=body)
