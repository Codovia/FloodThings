"""
Core extraction engine for historical Open-Meteo ERA5 reanalysis data.
"""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from app.ingestion.historical.client import (
    HistoricalExtractionError,
    HistoricalOpenMeteoClient,
    MalformedResponseError,
    RateLimitExceededError,
    ServerError,
)
from app.ingestion.historical.manifest import HistoricalExtractionManifest
from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    ExtractionConfig,
    ExtractionMetadata,
    ValidationResult,
)
from app.ingestion.historical.validator import HistoricalChunkValidator


class HistoricalExtractor:
    """
    Orchestrates historical meteorological extraction across Karnataka grid chunks.

    Guarantees:
    - Conservative sequential execution with rate-limit pacing.
    - Idempotency: Completed chunks with valid disk hashes are never re-downloaded.
    - Raw preservation: Exact raw API response bytes compressed with gzip.
    - Strict validation: Discrepancies marked as VALIDATION_FAILED; zero synthetic filling.
    """

    def __init__(
        self,
        config: ExtractionConfig | None = None,
        manifest: HistoricalExtractionManifest | None = None,
        client: HistoricalOpenMeteoClient | None = None,
        validator: HistoricalChunkValidator | None = None,
    ):
        self.config = config or ExtractionConfig()
        self.manifest = manifest or HistoricalExtractionManifest(self.config.manifest_path)
        self.client = client or HistoricalOpenMeteoClient(self.config)
        self.validator = validator or HistoricalChunkValidator(self.config)

    def extract_chunk(self, chunk: ExtractionChunk) -> ValidationResult:
        """
        Execute extraction for a single deterministic chunk.

        Steps:
        1. Check idempotency (skip if already completed and hash-verified).
        2. Mark RUNNING in manifest.
        3. Fetch raw payload from client.
        4. Calculate raw payload SHA-256.
        5. Validate payload against integrity rules.
        6. If valid, gzip-compress and persist to disk (with metadata).
        7. Update manifest to SUCCEEDED or appropriate failure state.
        """
        chunk_id = chunk.chunk_id

        # 1. Idempotency Check
        if self.manifest.is_chunk_completed(chunk_id, expected_fingerprint=chunk.spatial_fingerprint):
            return ValidationResult(
                is_valid=True,
                status=ChunkStatus.SUCCEEDED,
                warnings=[f"Chunk {chunk_id} already completed on disk with verified hash; skipped."],
            )

        # 2. Register & Mark RUNNING
        self.manifest.register_chunks([chunk])
        self.manifest.mark_running(chunk_id)

        # 3. Fetch from API
        try:
            raw_bytes, parsed_json, http_status, latency = self.client.fetch_chunk_payload(chunk)
        except RateLimitExceededError as rle:
            self.manifest.mark_failed(chunk_id, str(rle), ChunkStatus.RETRYABLE)
            return ValidationResult(is_valid=False, status=ChunkStatus.RETRYABLE, errors=[str(rle)])
        except ServerError as se:
            self.manifest.mark_failed(chunk_id, str(se), ChunkStatus.RETRYABLE)
            return ValidationResult(is_valid=False, status=ChunkStatus.RETRYABLE, errors=[str(se)])
        except MalformedResponseError as mre:
            self.manifest.mark_failed(chunk_id, str(mre), ChunkStatus.VALIDATION_FAILED)
            return ValidationResult(is_valid=False, status=ChunkStatus.VALIDATION_FAILED, errors=[str(mre)])
        except HistoricalExtractionError as hee:
            status = ChunkStatus.RETRYABLE if hee.retryable else ChunkStatus.PERMANENTLY_FAILED
            self.manifest.mark_failed(chunk_id, str(hee), status)
            return ValidationResult(is_valid=False, status=status, errors=[str(hee)])
        except Exception as unk:
            err_msg = f"Unexpected extraction error: {unk}"
            self.manifest.mark_failed(chunk_id, err_msg, ChunkStatus.PERMANENTLY_FAILED)
            return ValidationResult(is_valid=False, status=ChunkStatus.PERMANENTLY_FAILED, errors=[err_msg])

        # 4. Calculate Raw Payload SHA-256
        payload_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        uncompressed_size = len(raw_bytes)

        # 5. Validate Payload
        val_result = self.validator.validate_chunk_response(chunk, parsed_json, http_status)
        if not val_result.is_valid:
            self.manifest.mark_failed(
                chunk_id,
                "; ".join(val_result.errors[:5]),
                ChunkStatus.VALIDATION_FAILED,
            )
            return val_result

        # 6. Gzip Compression and Storage
        compressed_bytes = gzip.compress(raw_bytes)
        compressed_sha256 = hashlib.sha256(compressed_bytes).hexdigest()
        compressed_size = len(compressed_bytes)

        target_dir = self.config.raw_base_dir / f"year={chunk.year}"
        raw_file_path = target_dir / f"batch_{chunk.batch_id:03d}.json.gz"
        meta_file_path = target_dir / f"batch_{chunk.batch_id:03d}.meta.json"

        if not self.config.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(raw_file_path, "wb") as f:
                f.write(compressed_bytes)

            metadata = ExtractionMetadata(
                chunk_id=chunk_id,
                year=chunk.year,
                batch_id=chunk.batch_id,
                requested_url=self.client.build_request_url(chunk),
                requested_model=self.config.model,
                requested_coordinates=[[c.lat, c.lon] for c in chunk.cells],
                requested_start_date=f"{chunk.year}-01-01",
                requested_end_date=f"{chunk.year}-12-31",
                requested_timezone=self.config.timezone,
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                http_status=http_status,
                response_latency_seconds=latency,
                uncompressed_bytes=uncompressed_size,
                compressed_bytes=compressed_size,
                payload_sha256=payload_sha256,
                compressed_sha256=compressed_sha256,
            )
            with open(meta_file_path, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, indent=2)

        # 7. Update Manifest to SUCCEEDED
        self.manifest.mark_succeeded(
            chunk_id=chunk_id,
            raw_path=str(raw_file_path),
            payload_sha256=payload_sha256,
            compressed_sha256=compressed_sha256,
            uncompressed_bytes=uncompressed_size,
            compressed_bytes=compressed_size,
            validation=val_result,
            chunk=chunk,
        )
        return val_result

    def extract_chunks(
        self,
        chunks: list[ExtractionChunk],
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Execute extraction across a list of chunks with conservative pacing and limits.

        Returns summary of execution results.
        """
        target_chunks = chunks[:limit] if limit is not None else chunks
        total = len(target_chunks)
        succeeded = 0
        failed = 0
        skipped = 0

        for idx, chunk in enumerate(target_chunks, start=1):
            res = self.extract_chunk(chunk)
            if res.is_valid:
                if res.warnings and "already completed" in res.warnings[0]:
                    skipped += 1
                else:
                    succeeded += 1
            else:
                failed += 1

        return {
            "total_processed": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "manifest_summary": self.manifest.summary(),
        }
