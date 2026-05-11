# Setup Wiki

Recipebrain setup, development, deployment, and operations documentation.

## Quick Start

```bash
git clone https://github.com/urban-buss/recipebrain.git && cd recipebrain
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
recipebrain etl --source fooby --limit 10
recipebrain validate && recipebrain info
```

See [Quick Start](getting-started/quick-start.md) for the full walkthrough.

---

## Getting Started

| Page | Description |
|------|-------------|
| [Quick Start](getting-started/quick-start.md) | Zero to working recipe collection in 5 commands |
| [Prerequisites](getting-started/prerequisites.md) | Platform requirements and tool installation |
| [Installation](getting-started/installation.md) | Install from PyPI or source |

## Development

| Page | Description |
|------|-------------|
| [Local Setup](development/local-setup.md) | Clone, venv, VS Code workspace |
| [Project Structure](development/project-structure.md) | Annotated source tree |
| [Testing](development/testing.md) | Run tests, write tests, smoke testing |
| [Building](development/building.md) | Build sdist and wheel packages |

## Configuration

| Page | Description |
|------|-------------|
| [Overview](configuration/overview.md) | TOML config, precedence, all sections |

## Modules

| Page | Description |
|------|-------------|
| [ETL Pipeline](modules/etl.md) | Scrape → parse → transform → write |
| [MCP Server](modules/mcp-server.md) | Transports, client configs, tools reference |
| [CLI](modules/cli.md) | ETL, validate, info, snapshot commands |
| [Dashboard](modules/dashboard.md) | Observability web UI |
| [Agent Skills](modules/agent-skills.md) | Skill architecture and available skills |

## Operations

| Page | Description |
|------|-------------|
| [Logging](operations/logging.md) | Structured logging configuration |
| [Observability](operations/observability.md) | EventCollector, in-memory tool metrics |
| [Health Monitoring](operations/health-monitoring.md) | Doctor checks and data freshness |
| [VS Code Debugging](operations/vscode-debugging.md) | Debug configurations and tips |
| [MCP Testing](operations/mcp-testing.md) | Verify and test the MCP server |

## Publishing

| Page | Description |
|------|-------------|
| [Release Process](publishing/release-process.md) | Version, tag, publish workflow |
| [PyPI](publishing/pypi.md) | Automated and manual PyPI publishing |

## Reference

| Page | Description |
|------|-------------|
| [Fresh Install Validation](reference/fresh-install-validation.md) | Agent prompt for post-install QA |

---
