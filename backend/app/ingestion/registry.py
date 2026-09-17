"""
Registry and lifecycle management for DataSource and DataIngestionRun.

Ensures strict referential integrity and provenance tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.system import DataIngestionRun, DataSource
from app.ingestion.base import IngestionMetrics


def get_or_create_data_source(
    session: Session,
    name: str,
    organization: str | None = None,
    description: str | None = None,
    source_url: str | None = None,
    access_method: str | None = None,
    data_type: str | None = None,
    geographic_coverage: str = "Karnataka",
    update_frequency: str | None = None,
    license_type: str | None = None,
) -> DataSource:
    """Find existing DataSource by name or create a new one."""
    stmt = select(DataSource).where(DataSource.name == name)
    ds = session.execute(stmt).scalar_one_or_none()

    if ds is None:
        ds = DataSource(
            id=uuid.uuid4(),
            name=name,
            organization=organization,
            description=description,
            source_url=source_url,
            access_method=access_method,
            data_type=data_type,
            geographic_coverage=geographic_coverage,
            update_frequency=update_frequency,
            license=license_type,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(ds)
        session.flush()

    return ds


def start_ingestion_run(session: Session, source_id: uuid.UUID) -> DataIngestionRun:
    """Initialize and persist a new DataIngestionRun in RUNNING state."""
    run = DataIngestionRun(
        id=uuid.uuid4(),
        source_id=source_id,
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
        records_received=0,
        records_inserted=0,
        records_updated=0,
        records_rejected=0,
    )
    session.add(run)
    session.flush()
    return run


def complete_ingestion_run(
    session: Session,
    run: DataIngestionRun,
    status: str,
    metrics: IngestionMetrics,
    error_message: str | None = None,
) -> None:
    """Mark a DataIngestionRun as completed and record metrics."""
    run.completed_at = datetime.now(timezone.utc)
    run.status = status
    run.records_received = metrics.records_received
    run.records_inserted = metrics.records_inserted
    run.records_updated = metrics.records_updated
    run.records_rejected = metrics.records_rejected
    if error_message:
        run.error_message = error_message
    elif metrics.errors:
        run.error_message = "\n".join(metrics.errors[:10])
    session.flush()
