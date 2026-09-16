"""
FloodPulse API — FastAPI application entry point.

This module creates the application instance and registers routers.
No domain-specific routes are included in this foundation.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="FloodPulse API",
    description="Karnataka AI Flood Intelligence & Emergency Response System",
    version="0.0.1",
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
app.include_router(health_router)
