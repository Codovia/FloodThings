from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .weather import OpenMeteoAdapter, WeatherUnavailable, unavailable
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
async def weather(adapter: OpenMeteoAdapter = Depends(get_weather)):
    try:
        return await adapter.fetch()
    except WeatherUnavailable as exc:
        return JSONResponse(status_code=503, content=unavailable(str(exc)))
