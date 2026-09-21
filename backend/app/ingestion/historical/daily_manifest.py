"""
Persistent checkpoint and manifest manager for daily historical meteorological processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
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
        cell_ids: list[str] | None = None,
        spatial_fingerprint: str | None = None,
    ) -> None:
        """Register a chunk in the processing manifest if not already tracked."""
        now = datetime.now(timezone.utc).isoformat()
        if chunk_id not in self._data["chunks"]:
            self._data["chunks"][chunk_id] = {
                "chunk_id": chunk_id,
                "year": year,
                "batch_id": batch_id,
                "spatial_fingerprint": spatial_fingerprint,
                "cell_ids": cell_ids or [],
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
        cell_ids: list[str] | None = None,
        spatial_fingerprint: str | None = None,
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
        if cell_ids is not None:
            chunk["cell_ids"] = cell_ids
        if spatial_fingerprint is not None:
            chunk["spatial_fingerprint"] = spatial_fingerprint
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

    def recover_stale_running_chunks(
        self,
        processed_base_dir: Path | None = None,
        raw_base_dir: Path | None = None,
    ) -> dict[str, list[str]]:
        """
        Safely recover stale RUNNING chunks at startup after an interrupted run.

        For each chunk in RUNNING state:
        - Verify candidate output Parquet exists and is non-empty.
        - Verify Parquet is readable by pyarrow.
        - Verify row count matches recorded output_record_count if present.
        - Verify output checksum matches recorded output checksum (output_sha256 or output_checksum)
          when the manifest record has one.
          (Note: Existing/legacy records do not track output checksums; in that case, all other
          available validations are strictly performed, and no checksum is fabricated.)
        - Verify cell_ids and spatial_fingerprint derived from Parquet coordinates match
          the chunk's recorded metadata.
        - Verify source raw payload SHA-256 matches recorded input_sha256 if the source raw
          artifact is available on disk, and verify Parquet raw_payload_sha256 metadata/column.
        - Only reconcile RUNNING -> SUCCEEDED if all validations pass.
        - Otherwise reset RUNNING -> PENDING so processing can safely resume.

        Returns:
            {"reconciled_succeeded": [...], "reset_to_pending": [...]}
        """
        reconciled_succeeded: list[str] = []
        reset_to_pending: list[str] = []
        modified = False

        base_dir = Path(processed_base_dir) if processed_base_dir else self.manifest_path.parent

        for chunk_id, record in self._data["chunks"].items():
            if record.get("status") != DailyProcessingStatus.RUNNING.value:
                continue

            out_path_str = record.get("output_path")
            if out_path_str:
                candidate_path = Path(out_path_str)
            else:
                year = record.get("year")
                batch_id = record.get("batch_id")
                if year is not None and batch_id is not None:
                    candidate_path = base_dir / f"year={year}" / f"batch_{batch_id:03d}.parquet"
                else:
                    candidate_path = None

            is_valid = True
            failure_reason = ""
            row_count = 0
            actual_cell_ids: list[str] = []
            actual_fingerprint: str | None = None

            # 1. Output Parquet file exists and non-empty
            if not candidate_path or not candidate_path.exists() or candidate_path.stat().st_size == 0:
                is_valid = False
                failure_reason = "Parquet output file does not exist or is empty"
            else:
                # 2. Output checksum check if manifest record tracks one
                rec_out_checksum = record.get("output_sha256") or record.get("output_checksum")
                if rec_out_checksum is not None:
                    try:
                        computed_out_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                        if computed_out_sha256 != rec_out_checksum:
                            is_valid = False
                            failure_reason = (
                                f"Output checksum mismatch: expected {rec_out_checksum}, "
                                f"got {computed_out_sha256}"
                            )
                    except Exception as e:
                        is_valid = False
                        failure_reason = f"Failed to compute output checksum: {e}"
                # (Note: For legacy records without an output checksum, we do not fabricate or synthesize one.)

            # 3. Parquet readability & table content inspection
            table = None
            if is_valid:
                try:
                    import pyarrow.parquet as pq

                    table = pq.read_table(candidate_path)
                    row_count = table.num_rows
                    if row_count <= 0:
                        is_valid = False
                        failure_reason = "Parquet table contains 0 rows"
                except Exception as e:
                    is_valid = False
                    failure_reason = f"Parquet file unreadable or corrupted: {e}"

            # 4. Row count matches recorded output_record_count if present
            if is_valid and table is not None:
                rec_count = record.get("output_record_count")
                if rec_count is not None and rec_count != row_count:
                    is_valid = False
                    failure_reason = (
                        f"Row count mismatch: manifest recorded {rec_count}, "
                        f"file contains {row_count}"
                    )

            # 5. Cell IDs & spatial fingerprint consistency
            if is_valid and table is not None:
                if "latitude" not in table.column_names or "longitude" not in table.column_names:
                    is_valid = False
                    failure_reason = "Parquet table missing latitude or longitude columns"
                else:
                    try:
                        lats = table["latitude"].to_pylist()
                        lons = table["longitude"].to_pylist()
                        coords = sorted(set(zip(lats, lons)))
                        if not coords:
                            is_valid = False
                            failure_reason = "No coordinates found in Parquet table"
                        else:
                            actual_cell_ids = sorted([
                                f"ERA5_{int(round(lat * 100)):04d}_{int(round(lon * 100)):05d}"
                                for lat, lon in coords
                            ])
                            actual_fingerprint = hashlib.sha256(
                                ",".join(actual_cell_ids).encode("utf-8")
                            ).hexdigest()[:8]

                            # 5a. Verify against canonical batch definition if batch_id is present
                            batch_id = record.get("batch_id")
                            if batch_id is not None:
                                from app.ingestion.historical.grid import get_spatial_batches

                                batches = get_spatial_batches(batch_size=10, eligible_only=True)
                                if 1 <= batch_id <= len(batches):
                                    expected_cells = batches[batch_id - 1]
                                    expected_ids = sorted([c.cell_id for c in expected_cells])
                                    expected_fp = hashlib.sha256(
                                        ",".join(expected_ids).encode("utf-8")
                                    ).hexdigest()[:8]
                                    if actual_cell_ids != expected_ids or actual_fingerprint != expected_fp:
                                        is_valid = False
                                        failure_reason = (
                                            f"Spatial/batch mismatch with canonical batch {batch_id}: "
                                            f"expected fingerprint {expected_fp}, got {actual_fingerprint}"
                                        )

                            # 5b. Verify against recorded cell_ids
                            rec_cell_ids = record.get("cell_ids")
                            if is_valid and rec_cell_ids:
                                if sorted(rec_cell_ids) != actual_cell_ids:
                                    is_valid = False
                                    failure_reason = (
                                        f"Cell IDs mismatch: manifest has {sorted(rec_cell_ids)}, "
                                        f"Parquet has {actual_cell_ids}"
                                    )

                            # 5c. Verify against recorded spatial_fingerprint
                            rec_fp = record.get("spatial_fingerprint")
                            if is_valid and rec_fp:
                                if rec_fp != actual_fingerprint:
                                    is_valid = False
                                    failure_reason = (
                                        f"Spatial fingerprint mismatch: manifest has {rec_fp}, "
                                        f"Parquet has {actual_fingerprint}"
                                    )
                    except Exception as e:
                        is_valid = False
                        failure_reason = f"Failed to validate coordinates/fingerprint: {e}"

            # 6. Source raw artifact validation when available
            if is_valid and table is not None:
                candidate_raw_path = None
                raw_path_str = record.get("source_raw_path")
                if raw_path_str:
                    candidate_raw = Path(raw_path_str)
                    if candidate_raw.exists() and candidate_raw.stat().st_size > 0:
                        candidate_raw_path = candidate_raw

                if candidate_raw_path is None and raw_base_dir:
                    year = record.get("year")
                    batch_id = record.get("batch_id")
                    if year is not None and batch_id is not None:
                        alt_raw = Path(raw_base_dir) / f"year={year}" / f"batch_{batch_id:03d}.json.gz"
                        if alt_raw.exists() and alt_raw.stat().st_size > 0:
                            candidate_raw_path = alt_raw

                if candidate_raw_path is not None:
                    try:
                        import gzip

                        raw_bytes = candidate_raw_path.read_bytes()
                        if candidate_raw_path.name.endswith(".gz"):
                            uncomp_bytes = gzip.decompress(raw_bytes)
                        else:
                            uncomp_bytes = raw_bytes
                        computed_raw_sha256 = hashlib.sha256(uncomp_bytes).hexdigest()

                        rec_input_sha256 = record.get("input_sha256")
                        if rec_input_sha256 is not None and computed_raw_sha256 != rec_input_sha256:
                            is_valid = False
                            failure_reason = (
                                f"Source raw payload SHA-256 mismatch: recorded {rec_input_sha256}, "
                                f"actual file {computed_raw_sha256}"
                            )

                        if is_valid and "raw_payload_sha256" in table.column_names:
                            pq_hashes = set(table["raw_payload_sha256"].to_pylist())
                            if len(pq_hashes) != 1 or next(iter(pq_hashes)) != computed_raw_sha256:
                                is_valid = False
                                failure_reason = (
                                    "Parquet raw_payload_sha256 column does not match "
                                    "source raw artifact SHA-256"
                                )

                        if is_valid and table.schema.metadata:
                            meta_sha = table.schema.metadata.get(b"raw_payload_sha256")
                            if meta_sha and meta_sha.decode("utf-8") != computed_raw_sha256:
                                is_valid = False
                                failure_reason = (
                                    "Parquet metadata raw_payload_sha256 does not match "
                                    "source raw artifact SHA-256"
                                )
                    except Exception as e:
                        is_valid = False
                        failure_reason = f"Failed to validate source raw artifact {candidate_raw_path}: {e}"
                else:
                    # When source raw file is not present on disk, check Parquet table/metadata against recorded input_sha256
                    rec_input_sha256 = record.get("input_sha256")
                    if rec_input_sha256 is not None:
                        if "raw_payload_sha256" in table.column_names:
                            pq_hashes = set(table["raw_payload_sha256"].to_pylist())
                            if len(pq_hashes) != 1 or next(iter(pq_hashes)) != rec_input_sha256:
                                is_valid = False
                                failure_reason = (
                                    "Parquet raw_payload_sha256 column does not match "
                                    f"recorded input_sha256 {rec_input_sha256}"
                                )
                        if is_valid and table.schema.metadata:
                            meta_sha = table.schema.metadata.get(b"raw_payload_sha256")
                            if meta_sha and meta_sha.decode("utf-8") != rec_input_sha256:
                                is_valid = False
                                failure_reason = (
                                    "Parquet metadata raw_payload_sha256 does not match "
                                    f"recorded input_sha256 {rec_input_sha256}"
                                )

            # 7. Final State Transition
            if is_valid:
                now = datetime.now(timezone.utc).isoformat()
                record["status"] = DailyProcessingStatus.SUCCEEDED.value
                record["completed_at"] = now
                record["last_error"] = None
                record["output_path"] = str(candidate_path)
                record["output_record_count"] = row_count
                if actual_cell_ids and not record.get("cell_ids"):
                    record["cell_ids"] = actual_cell_ids
                if actual_fingerprint and not record.get("spatial_fingerprint"):
                    record["spatial_fingerprint"] = actual_fingerprint
                reconciled_succeeded.append(chunk_id)
                modified = True
            else:
                record["status"] = DailyProcessingStatus.PENDING.value
                record["started_at"] = None
                record["last_error"] = (
                    f"Interrupted while RUNNING; safely reset to PENDING at startup ({failure_reason})"
                )
                reset_to_pending.append(chunk_id)
                modified = True

        if modified:
            self.save()

        return {
            "reconciled_succeeded": reconciled_succeeded,
            "reset_to_pending": reset_to_pending,
        }

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
