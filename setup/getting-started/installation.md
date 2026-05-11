# Installation

Two ways to install Recipebrain: PyPI (users) or source (developers).

## Option A: Install from PyPI

```bash
python3 --version  # ensure 3.11+
pip install recipebrain
```

> **Note:** The PyPI package does not include the test suite. For development, use Option B.

## Option B: Install from Source (developers)

```bash
git clone https://github.com/urban-buss/recipebrain.git
cd recipebrain
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
pip install -e ".[dev]"
```

See [Local Setup](../development/local-setup.md) for the full development guide.

## Optional Extras

Install individual extras or all at once:

```bash
pip install "recipebrain[dev,ocr,llm]"
```

| Extra | What it adds | Dependencies |
|-------|-------------|--------------|
| `dev` | Testing and linting | `pytest`, `pytest-cov`, `ruff`, `mypy` |
| `ocr` | OCR-based recipe extraction from images | `pytesseract`, `Pillow` |
| `llm` | LLM-powered recipe parsing and enrichment | `openai` |

## Verify

```bash
recipebrain --help
```

Expected output:

```
usage: recipebrain [-h] [--version] [--config CONFIG]
                   {etl,promotions,ingest,validate,mcp,reindex,doctor,info,
                    snapshot,install-skills,log,dashboard} ...

Personal Swiss recipe knowledge base with promotion-aware meal planning.
```

## Next Steps

- [Quick Start](quick-start.md) — Run ETL and verify
- [Configuration](../configuration/overview.md) — TOML settings
- [ETL](../modules/etl.md) — Scrape recipes from Swiss sources
