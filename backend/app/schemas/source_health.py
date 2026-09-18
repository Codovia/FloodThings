"""
Pydantic response schemas for Source Health and Ingestion Run History API endpoints.
"""

from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class SourceHealthItem(BaseModel):
    """Health summary for a single external data source."""

    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID
    name: str
    organization: str | None = None
    data_type: str | None = None
    update_frequency: str | None = None
    is_active: bool
    health_status: str = Field(..., description="HEALTHY, DEGRADED, or DOWN")
    health_reason: str = Field(..., description="Deterministic explanation of assigned health state")
    last_attempted_at: datetime | None = None
    last_successful_at: datetime | None = None
    latest_data_timestamp: datetime | None = Field(
        None, description="Actual physical or model observation timestamp stored in database"
    )
    latest_run_status: str | None = Field(
        None, description="RUNNING, SUCCESS, PARTIAL, or FAILED"
    )
    consecutive_failures: int = 0
    recent_error_message: str | None = None


class SourceHealthResponse(BaseModel):
    """Response payload for GET /api/v1/health/sources."""

    sources: list[SourceHealthItem]
    total_sources: int
    evaluated_at: datetime


class DataIngestionRunItem(BaseModel):
    """Detailed summary of a single data ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    records_received: int | None = 0
    records_inserted: int | None = 0
    records_updated: int | None = 0
    records_rejected: int | None = 0
    error_message: str | None = None


class SourceRunsResponse(BaseModel):
    """Response payload for GET /api/v1/health/sources/{source_id}/runs."""

    source_id: uuid.UUID
    runs: list[DataIngestionRunItem]
    total_runs: int
    limit: int
    offset: int
