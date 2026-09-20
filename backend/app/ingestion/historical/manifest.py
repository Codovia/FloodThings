"""
Persistent checkpoint and manifest manager for historical meteorological extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    ValidationResult,
)


class HistoricalExtractionManifest:
    """
    Manages persistent state and checkpointing for historical extraction chunks.

    Guarantees:
    - Atomicity: Manifest writes use tempfile + rename.
    - Idempotency: A SUCCEEDED chunk with an existing, hash-verified raw file is never re-extracted.
    - Integrity: Missing or corrupted raw files are flagged and never treated as completed.
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
                # If corrupted, preserve existing or start fresh
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

    def register_chunks(self, chunks: list[ExtractionChunk]) -> None:
        """Register chunks in manifest with PENDING status if not already tracked."""
        now = datetime.now(timezone.utc).isoformat()
        modified = False
        for chunk in chunks:
            if chunk.chunk_id not in self._data["chunks"]:
                self._data["chunks"][chunk.chunk_id] = {
                    "chunk_id": chunk.chunk_id,
                    "year": chunk.year,
                    "batch_id": chunk.batch_id,
                    "locations_count": len(chunk.cells),
                    "coordinates": chunk.coordinates,
                    "status": ChunkStatus.PENDING.value,
                    "attempt_count": 0,
                    "created_at": now,
                    "started_at": None,
                    "completed_at": None,
                    "last_error": None,
                    "raw_path": None,
                    "payload_sha256": None,
                    "compressed_sha256": None,
                    "uncompressed_bytes": None,
                    "compressed_bytes": None,
                    "validation_status": None,
                }
                modified = True
        if modified:
            self.save()

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Retrieve chunk record by ID."""
        return self._data["chunks"].get(chunk_id)

    def mark_running(self, chunk_id: str) -> None:
        """Transition chunk to RUNNING state."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = ChunkStatus.RUNNING.value
        chunk["started_at"] = now
        chunk["attempt_count"] = chunk.get("attempt_count", 0) + 1
        self.save()

    def mark_succeeded(
        self,
        chunk_id: str,
        raw_path: str,
        payload_sha256: str,
        compressed_sha256: str,
        uncompressed_bytes: int,
        compressed_bytes: int,
        validation: ValidationResult,
    ) -> None:
        """Transition chunk to SUCCEEDED state with complete provenance metadata."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = ChunkStatus.SUCCEEDED.value
        chunk["completed_at"] = now
        chunk["last_error"] = None
        chunk["raw_path"] = raw_path
        chunk["payload_sha256"] = payload_sha256
        chunk["compressed_sha256"] = compressed_sha256
        chunk["uncompressed_bytes"] = uncompressed_bytes
        chunk["compressed_bytes"] = compressed_bytes
        chunk["validation_status"] = validation.to_dict()
        self.save()

    def mark_failed(
        self,
        chunk_id: str,
        error: str,
        status: ChunkStatus = ChunkStatus.RETRYABLE,
    ) -> None:
        """Transition chunk to failure state (RETRYABLE, PERMANENTLY_FAILED, or VALIDATION_FAILED)."""
        now = datetime.now(timezone.utc).isoformat()
        chunk = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        chunk["status"] = status.value
        chunk["last_error"] = error
        chunk["completed_at"] = now
        self.save()

    def is_chunk_completed(self, chunk_id: str) -> bool:
        """
        Verify whether a chunk is completely and reliably downloaded.

        Must satisfy:
        1. status == SUCCEEDED
        2. raw file exists on disk
        3. disk file SHA-256 matches manifest compressed_sha256
        """
        chunk = self.get_chunk(chunk_id)
        if not chunk or chunk.get("status") != ChunkStatus.SUCCEEDED.value:
            return False

        raw_path_str = chunk.get("raw_path")
        if not raw_path_str:
            return False

        raw_path = Path(raw_path_str)
        if not raw_path.exists() or raw_path.stat().st_size == 0:
            return False

        expected_hash = chunk.get("compressed_sha256")
        if not expected_hash:
            return False

        # Verify disk checksum against recorded checksum
        try:
            with open(raw_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            return actual_hash == expected_hash
        except Exception:
            return False

    def get_pending_or_retryable_chunks(
        self, chunks: list[ExtractionChunk]
    ) -> list[ExtractionChunk]:
        """Return list of chunks that need extraction (PENDING, RETRYABLE, or invalid on disk)."""
        runnable: list[ExtractionChunk] = []
        for c in chunks:
            if not self.is_chunk_completed(c.chunk_id):
                runnable.append(c)
        return runnable

    def summary(self) -> dict[str, int]:
        """Return count summary of chunk statuses."""
        counts = {s.value: 0 for s in ChunkStatus}
        for chunk in self._data["chunks"].values():
            st = chunk.get("status", ChunkStatus.PENDING.value)
            if st in counts:
                counts[st] += 1
            else:
                counts[st] = 1
        return counts
