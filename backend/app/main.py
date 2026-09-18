"""
FloodPulse API — FastAPI application entry point.

This module creates the application instance and registers routers.
No domain-specific routes are included in this foundation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.source_health import router as source_health_router
from app.core.config import get_settings
from app.scheduler.manager import get_scheduler_manager

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI application lifespan managing scheduler startup and shutdown."""
    scheduler = get_scheduler_manager()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="FloodPulse API",
    description="Karnataka AI Flood Intelligence & Emergency Response System",
    version="0.0.1",
    lifespan=lifespan,
)

# CORS — restrict in production via environment configuration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Routers ----
# Unversioned operational process health checks
app.include_router(health_router)

# API v1 domain & source health routes
app.include_router(source_health_router, prefix="/api/v1")
