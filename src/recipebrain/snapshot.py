"""Data snapshot management for backup and versioning.

Creates timestamped copies of the Parquet output directory before destructive
operations (ETL, migrations). Supports listing and restoring snapshots.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path


def create_snapshot(
    output_dir: Path,
    snapshot_dir: Path,
    *,
    label: str | None = None,
) -> Path | None:
    """Create a timestamped snapshot of the output directory.

    Copies all ``.parquet`` files from ``output_dir`` into a new subdirectory
    under ``snapshot_dir`` named with the current timestamp and optional label.

    Args:
        output_dir: Path to the Parquet data directory.
        snapshot_dir: Base directory for snapshots.
        label: Optional human-readable label appended to the snapshot name.

    Returns:
        Path to the created snapshot directory, or None if nothing to snapshot.

    Examples:
        >>> path = create_snapshot(Path("output"), Path("snapshots"), label="pre-etl")
    """
    parquet_files = list(output_dir.glob("*.parquet"))
    if not parquet_files:
        return None

    ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{label}" if label else ts
    dest = snapshot_dir / name
    dest.mkdir(parents=True, exist_ok=True)

    for f in parquet_files:
        shutil.copy2(f, dest / f.name)

    return dest


def list_snapshots(snapshot_dir: Path) -> list[dict]:
    """List available snapshots, most recent first.

    Returns:
        List of dicts with keys: name, path, file_count, created_at.
    """
    if not snapshot_dir.exists():
        return []

    snapshots: list[dict] = []
    for d in sorted(snapshot_dir.iterdir(), reverse=True):
        if d.is_dir():
            files = list(d.glob("*.parquet"))
            snapshots.append(
                {
                    "name": d.name,
                    "path": d,
                    "file_count": len(files),
                    "created_at": _parse_timestamp(d.name),
                }
            )
    return snapshots


def restore_snapshot(
    snapshot_path: Path,
    output_dir: Path,
) -> int:
    """Restore a snapshot by copying its Parquet files to the output directory.

    Overwrites existing files in ``output_dir`` with the snapshot contents.

    Args:
        snapshot_path: Path to the snapshot directory to restore.
        output_dir: Target output directory.

    Returns:
        Number of files restored.

    Raises:
        FileNotFoundError: If the snapshot directory doesn't exist.
    """
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    parquet_files = list(snapshot_path.glob("*.parquet"))
    if not parquet_files:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for f in parquet_files:
        shutil.copy2(f, output_dir / f.name)

    return len(parquet_files)


def _parse_timestamp(name: str) -> str | None:
    """Extract ISO timestamp from a snapshot directory name.

    Examples:
        >>> _parse_timestamp("20240601_120000_pre-etl")
        '2024-06-01T12:00:00'
    """
    # Format: YYYYMMDD_HHMMSS[_label]
    parts = name.split("_", 2)
    if len(parts) < 2:
        return None
    try:
        dt = datetime.datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S")
        return dt.isoformat()
    except ValueError:
        return None
