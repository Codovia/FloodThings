"""
Persistent checkpoint and manifest manager for daily historical meteorological processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from app.ingestion.historical.daily_models import (
    DailyProcessingStatus,
    DailyValidationResult,
)


class DailyProcessingManifest:
    """
    Manages persistent state and checkpointing for daily processed chunks.

    Guarantees:
    - Atomicity: Manifest writes use tempfile + rename.
    - Idempotency: A SUCCEEDED chunk with an existing output Parquet file and matching
      input raw SHA-256 is skipped without reprocessing.
    - Cache invalidation: If the raw input checksum changes, the chunk is flagged for reprocessing.
    """

    def __init__(self, manifest_path: Path):
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"version": "1.0", "chunks": {}}
        self.load()

    def load(self) -> None:
        """Load manifest from disk if it exists."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                if "chunks" not in self._data:
                    self._data["chunks"] = {}
            except Exception:
                self._data = {"version": "1.0", "chunks": {}}
        else:
            self._data = {"version": "1.0", "chunks": {}}

    def save(self) -> None:
        """Atomically persist manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = self.manifest_path.parent
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            json.dump(self._data, tf, indent=2, sort_keys=True)
            temp_name = tf.name
        Path(temp_name).replace(self.manifest_path)

    def register_chunk(
        self,
        chunk_id: str,
        year: int,
        batch_id: int,
        source_raw_path: str,
        input_sha256: str,
        processing_version: str = "1.0",
    ) -> None:
        """Register a chunk in the processing manifest if not already tracked."""
        now = datetime.now(timezone.utc).isoformat()
        if chunk_id not in self._data["chunks"]:
            self._data["chunks"][chunk_id] = {
                "chunk_id": chunk_id,
                "year": year,
                "batch_id": batch_id,
                "source_raw_path": source_raw_path,
                "input_sha256": input_sha256,
                "output_path": None,
                "output_record_count": None,
                "quality_summary": None,
                "processing_version": processing_version,
                "status": DailyProcessingStatus.PENDING.value,
                "created_at": now,
                "started_at": None,
                "completed_at": None,
                "last_error": None,
            }
            self.save()

    def mark_running(self, chunk_id: str) -> None:
        """Transition chunk to RUNNING state."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = DailyProcessingStatus.RUNNING.value
        chunk["started_at"] = now
        self.save()

    def mark_succeeded(
        self,
        chunk_id: str,
        output_path: str,
        output_record_count: int,
        validation: DailyValidationResult,
        input_sha256: str,
        processing_version: str = "1.0",
    ) -> None:
        """Transition chunk to SUCCEEDED state with provenance and quality metrics."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = DailyProcessingStatus.SUCCEEDED.value
        chunk["output_path"] = output_path
        chunk["output_record_count"] = output_record_count
        chunk["input_sha256"] = input_sha256
        chunk["processing_version"] = processing_version
        chunk["completed_at"] = now
        chunk["last_error"] = None
        chunk["quality_summary"] = {
            "records_validated": validation.records_validated,
            "cells_validated": validation.cells_validated,
            "complete_days": validation.complete_days,
            "incomplete_days": validation.incomplete_days,
        }
        self.save()

    def mark_failed(
        self,
        chunk_id: str,
        error: str,
        status: DailyProcessingStatus = DailyProcessingStatus.FAILED,
    ) -> None:
        """Transition chunk to failure state."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = status.value
        chunk["last_error"] = error
        chunk["completed_at"] = now
        self.save()

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Retrieve chunk record by ID."""
        return self._data["chunks"].get(chunk_id)

    def is_chunk_processed(
        self,
        chunk_id: str,
        current_raw_sha256: str,
        processing_version: str = "1.0",
    ) -> bool:
        """
        Check if a chunk has already been successfully processed.

        Must satisfy:
        1. status == SUCCEEDED
        2. recorded input_sha256 == current_raw_sha256 (cache invalidation on raw changes)
        3. recorded processing_version == processing_version
        4. output Parquet file exists and is non-empty
        """
        chunk = self.get_chunk(chunk_id)
        if not chunk or chunk.get("status") != DailyProcessingStatus.SUCCEEDED.value:
            return False

        if chunk.get("input_sha256") != current_raw_sha256:
            return False

        if chunk.get("processing_version") != processing_version:
            return False

        output_path_str = chunk.get("output_path")
        if not output_path_str:
            return False

        output_path = Path(output_path_str)
        if not output_path.exists() or output_path.stat().st_size == 0:
            return False

        return True

    def summary(self) -> dict[str, int]:
        """Return count summary of processing statuses."""
        counts = {s.value: 0 for s in DailyProcessingStatus}
        for chunk in self._data["chunks"].values():
            st = chunk.get("status", DailyProcessingStatus.PENDING.value)
            if st in counts:
                counts[st] += 1
            else:
                counts[st] = 1
        return counts
