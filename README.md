# recipebrain

Personal Swiss recipe knowledge base with promotion-aware meal planning, exposed via MCP.

**Companion to [cellarbrain](https://github.com/<owner>/cellarbrain).** Standalone — no Python coupling. Interop via MCP at runtime, orchestrated by the chat host.

## Status

**Pre-alpha.** Skeleton only. No scraping, no real MCP tools, no queries yet.

## Quickstart

```bash
git clone https://github.com/<owner>/recipebrain.git
cd recipebrain
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
cp recipebrain.toml.example recipebrain.toml
pytest
recipebrain --help
```

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/01-vision-and-usecases.md](docs/01-vision-and-usecases.md) | Vision, user persona, 10 use cases |
| [docs/02-requirements.md](docs/02-requirements.md) | Functional & non-functional requirements |
| [docs/03-data-sources.md](docs/03-data-sources.md) | Swiss recipe & promotion sources |
| [docs/04-entity-model.md](docs/04-entity-model.md) | Parquet table schemas, views |
| [docs/05-mcp-tools.md](docs/05-mcp-tools.md) | 15 MCP tools + resources |
| [docs/06-architecture.md](docs/06-architecture.md) | Pipeline, modules, build phasing |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records |

## Relationship to cellarbrain

recipebrain and cellarbrain are independent Python packages that interoperate via MCP:

- **cellarbrain** answers "which wine pairs with this dish?"
- **recipebrain** answers "which dish pairs with this wine I want to open?"
- Together (both MCP servers configured in the same host) = end-to-end meal planning with wine pairing.

No shared library. No Python imports between them. The chat host orchestrates cross-server tool calls. See [docs/06-architecture.md](docs/06-architecture.md) for details.

## Privacy

All data stays local. No cloud sync, no telemetry, no accounts. Recipe data is scraped from public websites and stored as local Parquet files. Your cook log, pantry, and preferences never leave your machine.

## Releasing

PyPI publishing uses trusted publishers (OIDC). Configure the `pypi` environment in GitHub repo settings with PyPI's trusted publisher binding. Then push a version tag:

```bash
git tag v0.0.1
git push origin v0.0.1
```

The `publish.yml` workflow handles the rest.

## License

MIT — see [LICENSE](LICENSE).
