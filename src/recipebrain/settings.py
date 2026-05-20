"""Configuration management for recipebrain.

Loads settings from TOML files with sensible defaults.
All config dataclasses are frozen to prevent accidental mutation after load.

Precedence (highest → lowest):
    1. CLI arguments (``--config``)
    2. Environment variable (``RECIPEBRAIN_CONFIG``)
    3. ``recipebrain.local.toml`` (gitignored, personal overrides)
    4. ``recipebrain.toml`` (committed defaults)
    5. User config pointer (``~/.config/recipebrain/config-path``)
    6. Built-in defaults (in this module)

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
    discovery_timeout_seconds: int = 120
    max_discovery_retries: int = 3


@dataclass(frozen=True)
class SourceConfig:
    enabled: bool = True
    languages: list[str] = field(default_factory=lambda: ["de"])

    @property
    def language(self) -> str:
        """Primary language (first in the list). Backward-compat accessor."""
        return self.languages[0] if self.languages else "de"


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
class ImagesConfig:
    enabled: bool = True
    max_width: int = 1200
    quality: int = 80
    format: str = "jpeg"
    min_dimension: int = 10


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
    images: ImagesConfig = field(default_factory=ImagesConfig)
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
            kwargs["sources"] = {
                name: _parse_source_config(cfg) for name, cfg in data["sources"].items()
            }

        if "promotions" in data:
            kwargs["promotions"] = PromotionsConfig(**data["promotions"])

        if "pantry" in data:
            kwargs["pantry"] = PantryConfig(**data["pantry"])

        if "cellarbrain" in data:
            kwargs["cellarbrain"] = CellarbrainConfig(**data["cellarbrain"])

        if "images" in data:
            kwargs["images"] = ImagesConfig(**data["images"])

        if "mcp" in data:
            kwargs["mcp"] = McpConfig(**data["mcp"])

        return cls(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Source config parsing
# ---------------------------------------------------------------------------


def _parse_source_config(raw: dict) -> SourceConfig:
    """Parse a source config dict, handling both legacy and new formats.

    Supports:
        - ``languages = ["de", "fr"]`` (new list format)
        - ``language = "de"`` (legacy single-string format, converted to list)

    If both keys are present, ``languages`` takes precedence.
    """
    enabled = raw.get("enabled", True)

    if "languages" in raw:
        languages = raw["languages"]
    elif "language" in raw:
        languages = [raw["language"]]
    else:
        languages = ["de"]

    return SourceConfig(enabled=enabled, languages=languages)


# ---------------------------------------------------------------------------
# Config file resolution
# ---------------------------------------------------------------------------


# Well-known user config directory for storing the config-path pointer.
_USER_CONFIG_DIR = Path.home() / ".config" / "recipebrain"
_CONFIG_PATH_FILE = _USER_CONFIG_DIR / "config-path"


def _resolve_config_path(
    config_path: Path | str | None,
) -> Path | None:
    """Find the config file using the precedence chain.

    Resolution order:
        1. Explicit *config_path* argument (CLI ``--config``)
        2. ``RECIPEBRAIN_CONFIG`` environment variable
        3. ``recipebrain.local.toml`` in CWD (gitignored overrides)
        4. ``recipebrain.toml`` in CWD (committed defaults)
        5. User config pointer at ``~/.config/recipebrain/config-path``
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

    # Fall back to user-level pointer written by ``recipebrain init``
    return _read_config_path_pointer()


def _read_config_path_pointer() -> Path | None:
    """Read the config-path pointer file written by ``recipebrain init``.

    Returns the resolved path if the pointer file exists and the target
    config file is present, otherwise ``None``.
    """
    if not _CONFIG_PATH_FILE.is_file():
        return None
    try:
        stored = _CONFIG_PATH_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not stored:
        return None
    p = Path(stored)
    if not p.is_file():
        logger.debug("Config pointer %s references missing file: %s", _CONFIG_PATH_FILE, p)
        return None
    return p.resolve()


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
