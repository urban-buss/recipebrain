"""System information report for recipebrain.

Gathers version info, Python environment, data summary, and MCP surface
counts for the ``recipebrain info`` CLI command.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from recipebrain import __version__
from recipebrain.writer import SCHEMAS


@dataclass
class InfoReport:
    """Structured system information."""

    version: str = ""
    python_version: str = ""
    platform: str = ""
    output_dir: str = ""
    parquet_entities: int = 0
    parquet_files_present: int = 0
    total_data_mb: float = 0.0
    schema_count: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def gather_info(output_dir: Path) -> InfoReport:
    """Collect system and data information.

    Args:
        output_dir: Path to the Parquet data directory.
    """
    present = 0
    total_bytes = 0
    if output_dir.exists():
        for entity in SCHEMAS:
            path = output_dir / f"{entity}.parquet"
            if path.exists():
                present += 1
                total_bytes += path.stat().st_size

    return InfoReport(
        version=__version__,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.platform(),
        output_dir=str(output_dir),
        parquet_entities=len(SCHEMAS),
        parquet_files_present=present,
        total_data_mb=round(total_bytes / (1024 * 1024), 2),
        schema_count=len(SCHEMAS),
    )


def format_info(report: InfoReport) -> str:
    """Format an InfoReport as human-readable text."""
    lines = [
        f"recipebrain {report.version}",
        f"Python {report.python_version} on {report.platform}",
        f"Data dir: {report.output_dir}",
        f"Schemas: {report.schema_count} entities",
        f"Parquet files: {report.parquet_files_present}/{report.parquet_entities} present"
        f" ({report.total_data_mb} MB)",
    ]
    for k, v in report.extra.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)
