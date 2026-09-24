"""
Source health and ingestion run history API endpoints.

Routes:
    GET /api/v1/health/sources
    GET /api/v1/health/sources/{source_id}/runs
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.system import DataSource
from app.db.session import get_db
from app.schemas.source_health import (
    DataIngestionRunItem,
    SourceHealthItem,
    SourceHealthResponse,
    SourceRunsResponse,
)
from app.services.source_health import SourceHealthService

router = APIRouter(prefix="/health", tags=["source-health"])


@router.get(
    "/sources",
    response_model=SourceHealthResponse,
    summary="Get dynamic health evaluation for all external data sources",
)
def get_all_sources_health(
    db: Session = Depends(get_db),
) -> SourceHealthResponse:
    """Evaluate and return runtime source health across all registered data providers.

    Health is dynamically computed from DataSource configuration, DataIngestionRun history,
    and actual observation table timestamps. No persistent health_status column is used.
    """
    service = SourceHealthService()
    health_items = service.get_all_sources_health(db)

    return SourceHealthResponse(
        sources=[
            SourceHealthItem(
                source_id=item.source_id,
                name=item.name,
                organization=item.organization,
                data_type=item.data_type,
                update_frequency=item.update_frequency,
                authority_level=item.authority_level,
                is_active=item.is_active,
                health_status=item.health_status,
                health_reason=item.health_reason,
                last_attempted_at=item.last_attempted_at,
                last_successful_at=item.last_successful_at,
                latest_data_timestamp=item.latest_data_timestamp,
                latest_run_status=item.latest_run_status,
                consecutive_failures=item.consecutive_failures,
                recent_error_message=item.recent_error_message,
                last_http_status_code=item.last_http_status_code,
            )
            for item in health_items
        ],
        total_sources=len(health_items),
        evaluated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/sources/{source_id}/runs",
    response_model=SourceRunsResponse,
    summary="Get paginated ingestion run history for a specific data source",
)
def get_source_ingestion_runs(
    source_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> SourceRunsResponse:
    """Retrieve audit history of data ingestion runs for a specific data source."""
    # Verify data source exists
    data_source = db.get(DataSource, source_id)
    if data_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DataSource with id '{source_id}' not found",
        )

    service = SourceHealthService()
    runs, total = service.get_source_runs(db, source_id=source_id, limit=limit, offset=offset)

    return SourceRunsResponse(
        source_id=source_id,
        runs=[
            DataIngestionRunItem(
                run_id=r.id,
                started_at=r.started_at,
                completed_at=r.completed_at,
                status=r.status,
                records_received=r.records_received,
                records_inserted=r.records_inserted,
                records_updated=r.records_updated,
                records_rejected=r.records_rejected,
                error_message=r.error_message,
                http_status_code=r.http_status_code,
            )
            for r in runs
        ],
        total_runs=total,
        limit=limit,
        offset=offset,
    )
