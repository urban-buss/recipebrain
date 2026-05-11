# Local Development Setup

Set up Recipebrain for local development with VS Code.

## Clone the Repository

```bash
cd ~/repos  # or your preferred projects directory
git clone https://github.com/urban-buss/recipebrain.git
cd recipebrain
```

## Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
```

Verify the Python path points to the venv:

```bash
which python3
# /Users/<you>/repos/recipebrain/.venv/bin/python3
```

## Install Dependencies

```bash
# Everything (recommended for development)
pip install -e ".[dev,ocr,llm]"
```

See [Installation](../getting-started/installation.md) for individual extras.

## VS Code Workspace

```bash
code recipebrain.code-workspace
```

Or: **File → Open Workspace from File…** → select `recipebrain.code-workspace`.

### Select Python Interpreter

1. Press `Ctrl+Shift+P` (Windows) / `Cmd+Shift+P` (macOS) → "Python: Select Interpreter"
2. Choose `.venv/bin/python` (should appear at the top)

### Workspace Settings

The repository includes pre-configured settings in `.vscode/settings.json`:

```json
{
    "python.testing.pytestArgs": ["tests"],
    "python.testing.unittestEnabled": false,
    "python.testing.pytestEnabled": true
}
```

This enables the VS Code test explorer with pytest automatically.

## Verify Setup

```bash
# 1. Check CLI is available
recipebrain --help

# 2. Run unit tests
pytest tests/ -v

# 3. Run ETL (scrape some recipes)
recipebrain etl --source fooby --limit 5

# 4. Validate output
recipebrain validate

# 5. Check info
recipebrain info

# 6. Run doctor
recipebrain doctor
```

## Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `python3: command not found` | Python not in PATH | Windows: reinstall with "Add to PATH"; macOS: `eval "$(/opt/homebrew/bin/brew shellenv)"` |
| `ModuleNotFoundError: recipebrain` | Package not installed | Run `pip install -e .` with venv active |
| `No module named 'extruct'` | Core deps missing | `pip install -e .` (ensure no install errors) |
| VS Code can't find tests | Wrong interpreter | Select `.venv/bin/python` as interpreter |
| `httpx.TimeoutException` | Scraping timeout | Check network; increase `[scraping] timeout_seconds` |
| `recipebrain etl` returns "No sources processed" | No sources enabled | Check `recipebrain.toml` `[sources.*]` sections |

## Next Steps

- [Project Structure](project-structure.md) — Source tree overview
- [Testing](testing.md) — Run and write tests
- [Configuration](../configuration/overview.md) — TOML settings
