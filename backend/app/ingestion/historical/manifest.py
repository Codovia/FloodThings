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
        """Register chunks in manifest with PENDING status if not already tracked, or update pending/failed records."""
        now = datetime.now(timezone.utc).isoformat()
        modified = False
        for chunk in chunks:
            existing = self._data["chunks"].get(chunk.chunk_id)
            if existing is None:
                self._data["chunks"][chunk.chunk_id] = {
                    "chunk_id": chunk.chunk_id,
                    "year": chunk.year,
                    "batch_id": chunk.batch_id,
                    "spatial_fingerprint": chunk.spatial_fingerprint,
                    "cell_ids": chunk.cell_ids,
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
            elif existing.get("status") != ChunkStatus.SUCCEEDED.value:
                # Update spatial definition if previously pending or failed under different/older grid settings
                if (
                    existing.get("spatial_fingerprint") != chunk.spatial_fingerprint
                    or existing.get("locations_count") != len(chunk.cells)
                ):
                    existing["spatial_fingerprint"] = chunk.spatial_fingerprint
                    existing["cell_ids"] = chunk.cell_ids
                    existing["locations_count"] = len(chunk.cells)
                    existing["coordinates"] = chunk.coordinates
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
        chunk: ExtractionChunk | None = None,
    ) -> None:
        """Transition chunk to SUCCEEDED state with complete provenance metadata."""
        now = datetime.now(timezone.utc).isoformat()
        rec = self._data["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id})
        rec["status"] = ChunkStatus.SUCCEEDED.value
        rec["completed_at"] = now
        rec["last_error"] = None
        rec["raw_path"] = raw_path
        rec["payload_sha256"] = payload_sha256
        rec["compressed_sha256"] = compressed_sha256
        rec["uncompressed_bytes"] = uncompressed_bytes
        rec["compressed_bytes"] = compressed_bytes
        rec["validation_status"] = validation.to_dict()
        if chunk is not None:
            rec["spatial_fingerprint"] = chunk.spatial_fingerprint
            rec["cell_ids"] = chunk.cell_ids
            rec["locations_count"] = len(chunk.cells)
            rec["coordinates"] = chunk.coordinates
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

    def recover_stale_running_chunks(
        self, raw_base_dir: Path | None = None
    ) -> dict[str, list[str]]:
        """
        Safely recover stale RUNNING chunks at startup after an interrupted run.

        For each chunk in RUNNING state:
        - Inspect recorded artifact path, checksum, and spatial fingerprint.
        - If a valid completed artifact exists on disk with matching checksum,
          valid decompression, valid JSON structure, and matching spatial fingerprint,
          reconcile the chunk to SUCCEEDED.
        - Otherwise, transition the stale chunk to PENDING so production can resume.
        Never blindly mark RUNNING chunks as SUCCEEDED without full validation.

        Returns:
            {"reconciled_succeeded": [...], "reset_to_pending": [...]}
        """
        reconciled_succeeded: list[str] = []
        reset_to_pending: list[str] = []
        modified = False

        base_dir = Path(raw_base_dir) if raw_base_dir else self.manifest_path.parent

        for chunk_id, record in self._data["chunks"].items():
            if record.get("status") != ChunkStatus.RUNNING.value:
                continue

            raw_path_str = record.get("raw_path")
            if raw_path_str:
                candidate_path = Path(raw_path_str)
            else:
                year = record.get("year")
                batch_id = record.get("batch_id")
                if year is not None and batch_id is not None:
                    candidate_path = base_dir / f"year={year}" / f"batch_{batch_id:03d}.json.gz"
                else:
                    candidate_path = None

            is_valid_artifact = False
            uncompressed_bytes_len = 0
            compressed_bytes_len = 0
            computed_payload_sha256 = None
            computed_comp_sha256 = None
            val_dict = None

            if candidate_path and candidate_path.exists() and candidate_path.stat().st_size > 0:
                try:
                    import gzip
                    from app.ingestion.historical.models import GridCell
                    from app.ingestion.historical.validator import HistoricalChunkValidator

                    compressed_bytes = candidate_path.read_bytes()
                    compressed_bytes_len = len(compressed_bytes)
                    computed_comp_sha256 = hashlib.sha256(compressed_bytes).hexdigest()

                    # Check recorded compressed_sha256 if present
                    rec_comp_hash = record.get("compressed_sha256")
                    if rec_comp_hash and rec_comp_hash != computed_comp_sha256:
                        is_valid_artifact = False
                    else:
                        uncompressed_bytes = gzip.decompress(compressed_bytes)
                        uncompressed_bytes_len = len(uncompressed_bytes)
                        computed_payload_sha256 = hashlib.sha256(uncompressed_bytes).hexdigest()

                        rec_payload_hash = record.get("payload_sha256")
                        if rec_payload_hash and rec_payload_hash != computed_payload_sha256:
                            is_valid_artifact = False
                        else:
                            parsed_json = json.loads(uncompressed_bytes.decode("utf-8"))

                            # Validate coordinates and fingerprint
                            coords = record.get("coordinates", [])
                            cells = [GridCell(lat=c[0], lon=c[1]) for c in coords]
                            chunk_obj = ExtractionChunk(
                                chunk_id=chunk_id,
                                year=record.get("year", 1969),
                                batch_id=record.get("batch_id", 1),
                                cells=cells,
                            )
                            rec_fp = record.get("spatial_fingerprint")
                            if rec_fp and chunk_obj.spatial_fingerprint != rec_fp:
                                is_valid_artifact = False
                            else:
                                validator = HistoricalChunkValidator()
                                val_result = validator.validate_chunk_response(
                                    chunk_obj, parsed_json, http_status=200
                                )
                                if val_result.is_valid:
                                    is_valid_artifact = True
                                    val_dict = val_result.to_dict()
                except Exception:
                    is_valid_artifact = False

            if is_valid_artifact:
                now = datetime.now(timezone.utc).isoformat()
                record["status"] = ChunkStatus.SUCCEEDED.value
                record["completed_at"] = now
                record["last_error"] = None
                record["raw_path"] = str(candidate_path)
                record["payload_sha256"] = computed_payload_sha256
                record["compressed_sha256"] = computed_comp_sha256
                record["uncompressed_bytes"] = uncompressed_bytes_len
                record["compressed_bytes"] = compressed_bytes_len
                record["validation_status"] = val_dict
                reconciled_succeeded.append(chunk_id)
                modified = True
            else:
                record["status"] = ChunkStatus.PENDING.value
                record["started_at"] = None
                record["last_error"] = "Interrupted while RUNNING; safely reset to PENDING at startup"
                reset_to_pending.append(chunk_id)
                modified = True

        if modified:
            self.save()

        return {
            "reconciled_succeeded": reconciled_succeeded,
            "reset_to_pending": reset_to_pending,
        }

    def is_chunk_completed(
        self, chunk_id: str, expected_fingerprint: str | None = None
    ) -> bool:
        """
        Verify whether a chunk is completely and reliably downloaded.

        Must satisfy:
        1. status == SUCCEEDED
        2. spatial_fingerprint matches expected_fingerprint (if specified)
        3. raw file exists on disk and is non-empty
        4. disk file SHA-256 matches manifest compressed_sha256
        """
        chunk = self.get_chunk(chunk_id)
        if not chunk or chunk.get("status") != ChunkStatus.SUCCEEDED.value:
            return False

        if expected_fingerprint is not None:
            actual_fp = chunk.get("spatial_fingerprint")
            if not actual_fp:
                # Fallback: compute from coordinates for un-migrated legacy v1.0 records
                coords = chunk.get("coordinates", [])
                cell_ids = [
                    f"ERA5_{int(round(lat * 100)):04d}_{int(round(lon * 100)):05d}"
                    for lat, lon in coords
                ]
                actual_fp = hashlib.sha256(",".join(sorted(cell_ids)).encode("utf-8")).hexdigest()[:8]
            if actual_fp != expected_fingerprint:
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
            if not self.is_chunk_completed(c.chunk_id, expected_fingerprint=c.spatial_fingerprint):
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
