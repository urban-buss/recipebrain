# Building Distribution Packages

How to build sdist and wheel packages for Recipebrain.

## Prerequisites

```bash
pip install build
```

## Build

```bash
python -m build
```

Creates:

```
dist/
├── recipebrain-X.Y.Z.tar.gz              # Source distribution
└── recipebrain-X.Y.Z-py3-none-any.whl    # Wheel (binary)
```

## Verify

```bash
# Check wheel contents
# Windows:
python -m zipfile -l dist\recipebrain-*.whl | Select-Object -First 30

# macOS/Linux:
unzip -l dist/recipebrain-*.whl | head -30

# Test install in a fresh venv
python3 -m venv /tmp/test-install
source /tmp/test-install/bin/activate
pip install dist/recipebrain-*.whl
recipebrain --help
deactivate
rm -rf /tmp/test-install
```

## Build Metadata

Configured in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools >= 68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
recipebrain = "recipebrain.cli:main"
```

The `recipebrain` CLI command calls `src/recipebrain/cli.py:main()`.

## Next Steps

- [Release Process](../publishing/release-process.md) — Version, tag, publish
- [PyPI](../publishing/pypi.md) — Publish to PyPI
