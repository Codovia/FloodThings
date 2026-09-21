"""
Explicit manifest migration script for Phase 3.12D.

Upgrades extraction_manifest.json and processing_manifest.json to Schema Version 1.1:
- Backs up existing manifests to *.bak_v1_0
- Populates deterministic 'spatial_fingerprint' and 'cell_ids' for all existing chunks
- Adds top-level manifest_metadata with schema and grid specifications
- Preserves all existing checksums, statuses, timestamps, and payload paths without modification
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

from app.ingestion.historical.grid import (
    KARNATAKA_ERA5_CELLS,
    get_spatial_batches,
    compute_spatial_fingerprint,
)


def coords_to_cell_ids(coordinates: list[list[float]]) -> list[str]:
    """Convert list of [lat, lon] to canonical ERA5 cell IDs."""
    cell_ids = []
    for pt in coordinates:
        lat, lon = pt[0], pt[1]
        lat_str = f"{int(round(lat * 100)):04d}"
        lon_str = f"{int(round(lon * 100)):05d}"
        cell_ids.append(f"ERA5_{lat_str}_{lon_str}")
    return cell_ids


def migrate_extraction_manifest(manifest_path: Path, dry_run: bool = True) -> int:
    """Migrate extraction manifest in-place to v1.1."""
    if not manifest_path.exists():
        print(f"Extraction manifest not found at {manifest_path}, skipping.")
        return 0

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", {})
    migrated_count = 0

    for chunk_id, record in chunks.items():
        coords = record.get("coordinates", [])
        if coords:
            cell_ids = coords_to_cell_ids(coords)
            fp = hashlib.sha256(",".join(sorted(cell_ids)).encode("utf-8")).hexdigest()[:8]
            record["cell_ids"] = cell_ids
            record["spatial_fingerprint"] = fp
            migrated_count += 1

    metadata = {
        "schema_version": "1.1",
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "grid_version": "authoritative_324",
        "source_id": "openmeteo_era5",
        "spatial_batches_count": 33,
        "eligible_cells_count": 318,
        "excluded_cells_count": 6,
    }
    data["manifest_metadata"] = metadata
    data["version"] = "1.1"

    if dry_run:
        print(f"[DRY-RUN] Would migrate {migrated_count} extraction chunks in {manifest_path}")
        return migrated_count

    # Backup
    bak_path = manifest_path.with_suffix(".json.bak_v1_0")
    if not bak_path.exists():
        shutil.copy2(manifest_path, bak_path)
        print(f"Created backup at {bak_path}")

    # Atomic write
    temp_dir = manifest_path.parent
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2, sort_keys=True)
        temp_name = tf.name
    Path(temp_name).replace(manifest_path)
    print(f"Successfully migrated {migrated_count} extraction chunks in {manifest_path}")
    return migrated_count


def migrate_processing_manifest(
    proc_path: Path, ext_path: Path, dry_run: bool = True
) -> int:
    """Migrate processing manifest in-place to v1.1 using extraction manifest as source of truth."""
    if not proc_path.exists():
        print(f"Processing manifest not found at {proc_path}, skipping.")
        return 0

    with open(proc_path, "r", encoding="utf-8") as f:
        proc_data = json.load(f)

    # Load extraction manifest to correlate cell coordinates
    ext_data = {}
    if ext_path.exists():
        with open(ext_path, "r", encoding="utf-8") as f:
            ext_data = json.load(f).get("chunks", {})

    # Also resolve from static authoritative batches as fallback
    batches = get_spatial_batches(batch_size=10, eligible_only=True)
    batch_map = {idx: b for idx, b in enumerate(batches, start=1)}

    proc_chunks = proc_data.get("chunks", {})
    migrated_count = 0

    for chunk_id, record in proc_chunks.items():
        batch_id = record.get("batch_id")
        ext_record = ext_data.get(chunk_id, {})
        coords = ext_record.get("coordinates", [])

        if coords:
            cell_ids = coords_to_cell_ids(coords)
            fp = hashlib.sha256(",".join(sorted(cell_ids)).encode("utf-8")).hexdigest()[:8]
        elif batch_id in batch_map:
            cells = batch_map[batch_id]
            cell_ids = [c.cell_id for c in cells]
            fp = compute_spatial_fingerprint(cells)
        else:
            cell_ids = []
            fp = None

        if fp:
            record["cell_ids"] = cell_ids
            record["spatial_fingerprint"] = fp
            migrated_count += 1

    proc_data["manifest_metadata"] = {
        "schema_version": "1.1",
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "processing_version": "1.0",
        "spatial_batches_count": 33,
        "eligible_cells_count": 318,
    }
    proc_data["version"] = "1.1"

    if dry_run:
        print(f"[DRY-RUN] Would migrate {migrated_count} processing chunks in {proc_path}")
        return migrated_count

    # Backup
    bak_path = proc_path.with_suffix(".json.bak_v1_0")
    if not bak_path.exists():
        shutil.copy2(proc_path, bak_path)
        print(f"Created backup at {bak_path}")

    # Atomic write
    temp_dir = proc_path.parent
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        json.dump(proc_data, tf, indent=2, sort_keys=True)
        temp_name = tf.name
    Path(temp_name).replace(proc_path)
    print(f"Successfully migrated {migrated_count} processing chunks in {proc_path}")
    return migrated_count


def main():
    parser = argparse.ArgumentParser(description="Migrate historical ERA5 manifests to schema v1.1.")
    parser.add_argument(
        "--raw-manifest",
        type=Path,
        default=Path("data/raw/era5_historical/extraction_manifest.json"),
        help="Path to raw extraction manifest",
    )
    parser.add_argument(
        "--processed-manifest",
        type=Path,
        default=Path("data/processed/era5_daily/processing_manifest.json"),
        help="Path to daily processing manifest",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform actual migration and backup (defaults to dry-run)",
    )
    args = parser.parse_args()

    dry_run = not args.live
    print(f"Running manifest migration (dry_run={dry_run})...")

    ext_migrated = migrate_extraction_manifest(args.raw_manifest, dry_run=dry_run)
    proc_migrated = migrate_processing_manifest(
        args.processed_manifest, args.raw_manifest, dry_run=dry_run
    )

    print(f"Migration complete: {ext_migrated} extraction chunks, {proc_migrated} processing chunks.")
    if dry_run:
        print("To apply changes, re-run with --live.")


if __name__ == "__main__":
    main()
