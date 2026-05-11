"""Configuration management for recipebrain.

Loads settings from TOML files with sensible defaults.
All config dataclasses are frozen to prevent accidental mutation after load.

Precedence (highest → lowest):
    1. CLI arguments (``--config``)
    2. Environment variable (``RECIPEBRAIN_CONFIG``)
    3. ``recipebrain.local.toml`` (gitignored, personal overrides)
    4. ``recipebrain.toml`` (committed defaults)
    5. Built-in defaults (in this module)

Relative paths in the TOML are anchored to the config file's parent directory
at load time — never resolved against the process CWD.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PathsConfig:
    output_dir: str = "output"
    dossier_dir: str = "dossiers/recipes"
    inbox_dir: str = "inbox"
    snapshot_dir: str = "snapshots"


@dataclass(frozen=True)
class ScrapingConfig:
    rate_limit_seconds: float = 2.0
    user_agent: str = "recipebrain/0.0.1 (personal use)"
    respect_robots_txt: bool = True
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SourceConfig:
    enabled: bool = True
    language: str = "de"


@dataclass(frozen=True)
class PromotionsConfig:
    enabled: bool = True
    adapter: str = "profital"
    refresh_interval_hours: int = 168


@dataclass(frozen=True)
class PantryConfig:
    expiry_warning_days: int = 3


@dataclass(frozen=True)
class CellarbrainConfig:
    enabled: bool = False
    mcp_endpoint: str = "stdio"


@dataclass(frozen=True)
class McpConfig:
    transport: str = "stdio"
    host: str = "localhost"
    port: int = 8002


@dataclass(frozen=True)
class Settings:
    paths: PathsConfig = field(default_factory=PathsConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    promotions: PromotionsConfig = field(default_factory=PromotionsConfig)
    pantry: PantryConfig = field(default_factory=PantryConfig)
    cellarbrain: CellarbrainConfig = field(default_factory=CellarbrainConfig)
    mcp: McpConfig = field(default_factory=McpConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Settings:
        """Load settings from a TOML file, returning defaults if file is absent.

        Resolution order: explicit *path* → ``RECIPEBRAIN_CONFIG`` env var →
        ``recipebrain.local.toml`` → ``recipebrain.toml`` → built-in defaults.

        Relative paths in ``[paths]`` are resolved against the config file's
        parent directory (not the process CWD). When no config file is found,
        paths are anchored to the current working directory and a warning is
        emitted.
        """
        resolved = _resolve_config_path(path)

        if resolved is None:
            logger.warning(
                "No config file found — using built-in defaults. "
                "Set -c/--config or RECIPEBRAIN_CONFIG to specify a config file.",
            )
            config_root = Path.cwd().resolve()
            return cls(paths=_resolve_paths(PathsConfig(), config_root))

        config_root = resolved.parent

        with open(resolved, "rb") as f:
            data = tomllib.load(f)

        kwargs: dict[str, object] = {}

        if "paths" in data:
            kwargs["paths"] = _resolve_paths(PathsConfig(**data["paths"]), config_root)
        else:
            kwargs["paths"] = _resolve_paths(PathsConfig(), config_root)

        if "scraping" in data:
            kwargs["scraping"] = ScrapingConfig(**data["scraping"])

        if "sources" in data:
            kwargs["sources"] = {name: SourceConfig(**cfg) for name, cfg in data["sources"].items()}

        if "promotions" in data:
            kwargs["promotions"] = PromotionsConfig(**data["promotions"])

        if "pantry" in data:
            kwargs["pantry"] = PantryConfig(**data["pantry"])

        if "cellarbrain" in data:
            kwargs["cellarbrain"] = CellarbrainConfig(**data["cellarbrain"])

        if "mcp" in data:
            kwargs["mcp"] = McpConfig(**data["mcp"])

        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Config file resolution
# ---------------------------------------------------------------------------


def _resolve_config_path(
    config_path: Path | str | None,
) -> Path | None:
    """Find the config file using the precedence chain.

    Resolution order:
        1. Explicit *config_path* argument (CLI ``--config``)
        2. ``RECIPEBRAIN_CONFIG`` environment variable
        3. ``recipebrain.local.toml`` in CWD (gitignored overrides)
        4. ``recipebrain.toml`` in CWD (committed defaults)
    """
    if config_path is not None:
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p.resolve()

    env = os.environ.get("RECIPEBRAIN_CONFIG")
    if env:
        p = Path(env)
        if not p.exists():
            raise FileNotFoundError(
                f"RECIPEBRAIN_CONFIG points to missing file: {p}",
            )
        return p.resolve()

    # Prefer local (gitignored) override over the committed defaults
    local = Path("recipebrain.local.toml")
    if local.exists():
        return local.resolve()

    default = Path("recipebrain.toml")
    if default.exists():
        return default.resolve()

    return None


# ---------------------------------------------------------------------------
# Path anchoring helpers
# ---------------------------------------------------------------------------


def _anchor(path_str: str, root: Path) -> str:
    """Resolve *path_str* against *root* if relative; absolute paths are normalised."""
    p = Path(path_str)
    if p.is_absolute():
        return str(p.resolve())
    return str((root / p).resolve())


def _resolve_paths(paths: PathsConfig, config_root: Path) -> PathsConfig:
    """Return a new PathsConfig with all relative paths anchored to *config_root*."""
    return PathsConfig(
        output_dir=_anchor(paths.output_dir, config_root),
        dossier_dir=_anchor(paths.dossier_dir, config_root),
        inbox_dir=_anchor(paths.inbox_dir, config_root),
        snapshot_dir=_anchor(paths.snapshot_dir, config_root),
    )
