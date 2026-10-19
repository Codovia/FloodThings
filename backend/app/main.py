import logging
import os
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

from .weather import OpenMeteoAdapter, WeatherUnavailable, unavailable
from .location_weather import fetch_point_weather, selected_location
from .historical import router as historical_router
from .drainage import router as drainage_router
from .flood_map import router as flood_map_router
from .locations import router as locations_router
from .shelters import router as shelters_router, dispose_shelter_engine
from .notifications import router as notifications_router
from .reports import router as reports_router
from .telegram_subscriptions import router as subscriptions_router
from .home_geocoding import router as geocoding_router, ReverseGeocoder
from .river_outlook import router as river_outlook_router, RiverOutlook
from .risk import router as risk_router, RiskService
from .official import router as official_router, OfficialService, official_tls_context
from .admin_place import router as admin_place_router, PlaceLookup
from .routing import router as routing_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bounded upstream requests, with no retries, persistence or background jobs.
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
        app.state.weather = OpenMeteoAdapter(client)
        app.state.reverse_geocoder = ReverseGeocoder(client)
        app.state.river_outlook = RiverOutlook(client)
        app.state.risk = RiskService(client)
        # IMD and NDMA SACHET get their own client with the extra pinned root (see official.py).
        official_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False, verify=official_tls_context())
        app.state.official = OfficialService(official_client)
        app.state.place_lookup = PlaceLookup(client)
        app.state.http = client
        try:
            yield
        finally:
            await official_client.aclose()
            from .location_database import dispose_engine
            dispose_engine()
            dispose_shelter_engine()


app = FastAPI(title="FloodPulse", version="0.1.0", lifespan=lifespan)
from .rate_limit import install as install_rate_limits
app.state.rate_limiter = install_rate_limits(app)
app.include_router(historical_router)
app.include_router(drainage_router)
app.include_router(flood_map_router)
app.include_router(locations_router)
app.include_router(shelters_router)
app.include_router(notifications_router)
app.include_router(reports_router)
app.include_router(subscriptions_router)
app.include_router(geocoding_router)
app.include_router(river_outlook_router)
app.include_router(risk_router)
app.include_router(official_router)
app.include_router(admin_place_router)
app.include_router(routing_router)


log = logging.getLogger("floodpulse")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Full details stay in the server log under an error ID; the visitor sees a generic message.
    # Only method and path are logged: query strings can contain citizen coordinates.
    error_id = uuid.uuid4().hex[:12]
    log.error("unhandled error %s on %s %s", error_id, request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"status": "error", "error_id": error_id,
        "message": "Something went wrong on our side. Please try again; if it keeps happening, quote this error ID."})


@app.exception_handler(RequestValidationError)
async def validation_without_admin_secrets(request: Request, exc):
    if request.url.path.startswith(('/api/admin/', '/api/reports')):
        return JSONResponse(status_code=422, content={'detail': 'Invalid administrator request; check fields and verification requirements' if request.url.path.startswith('/api/admin/') else 'Invalid citizen report; check consent, timestamps, GPS and photo fields'})
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def shelter_response_security(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/admin/') or request.url.path == '/api/shelters' or request.url.path.startswith('/api/reports'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
    return response


def get_weather(request: Request) -> OpenMeteoAdapter:
    return request.app.state.weather


@app.get('/api/environment')
def environment_mode():
    from .shelters import mode
    return JSONResponse({'mode':mode()},headers={'Cache-Control':'no-store'})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "floodpulse", "version": "0.1.0"}


@app.get("/api/health/ready")
def ready():
    """For uptime monitors: also checks the database (no credentials or error details are returned)."""
    from sqlalchemy import text
    from .shelters import shelter_engine
    try:
        with shelter_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        log.warning("readiness check: database unavailable")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"}, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "ok", "database": "ok"}, headers={"Cache-Control": "no-store"})


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
        body = unavailable(str(exc), exc)
        if latitude is not None:
            body.update(location=selected_location(latitude, longitude), prediction_status="not_available")
        headers = {"Retry-After": str(int(exc.retry_after_seconds + 1))} if exc.retry_after_seconds is not None else None
        return JSONResponse(status_code=503, content=body, headers=headers)


@app.get("/api/ai/rainfall-outlook")
async def ai_rainfall_outlook(
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    adapter: OpenMeteoAdapter = Depends(get_weather),
):
    from .rainfall_outlook import rainfall_outlook
    from .rainfall_features import RainfallUnavailable
    try:
        return await rainfall_outlook(adapter.client, latitude, longitude)
    except RainfallUnavailable as exc:
        return JSONResponse(status_code=503, content={"status": "unavailable", "experimental": True,
            "message": str(exc), "location": {"latitude": latitude, "longitude": longitude},
            "prediction": None, "probability": None, "model_version": "rainfall_logistic_v1",
            "flood_prediction_status": "not_available"})


# Production: serve the built frontend from the same origin. Registered last so API routes win.
if os.environ.get("FLOODPULSE_STATIC_DIR"):
    from .static_site import mount_frontend
    mount_frontend(app, os.environ["FLOODPULSE_STATIC_DIR"])
