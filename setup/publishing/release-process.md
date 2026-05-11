# Release Process

How to version, tag, and publish a new Recipebrain release.

## Versioning

Recipebrain follows [Semantic Versioning](https://semver.org/):

| Bump | When | Example |
|------|------|---------|
| **MAJOR** | Breaking changes to CLI, MCP tools, or config format | `1.0.0` → `2.0.0` |
| **MINOR** | New features, new MCP tools, new source adapters | `0.1.0` → `0.2.0` |
| **PATCH** | Bug fixes, parser corrections, documentation | `0.1.0` → `0.1.1` |

Version is defined in two places:
- `pyproject.toml` → `version = "0.0.1"`
- `src/recipebrain/__init__.py` → `__version__ = "0.0.1"`

## Release Checklist

### 1. Update Version

Edit both `pyproject.toml` and `src/recipebrain/__init__.py`.

### 2. Update Changelog

Move items from `[Unreleased]` to a new version heading in `CHANGELOG.md`:

```markdown
## [0.1.0] — 2026-05-15

### Added
- New source adapter: schweizerfleisch.ch
- MCP tool: suggest_easy for weeknight meals

### Fixed
- ...
```

### 3. Commit

```bash
git add pyproject.toml src/recipebrain/__init__.py CHANGELOG.md
git commit -m "release: v0.1.0"
```

### 4. Tag and Push

```bash
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

### 5. Verify on PyPI

After CI completes: `https://pypi.org/project/recipebrain/0.1.0/`

## Pre-Release Testing

```bash
# 1. Full test suite
pytest

# 2. Build and verify
python -m build
twine check dist/*

# 3. Test install in clean venv
python3 -m venv /tmp/release-test
source /tmp/release-test/bin/activate
pip install dist/recipebrain-*.whl
recipebrain --help
recipebrain etl --source fooby --limit 3
recipebrain validate
deactivate
rm -rf /tmp/release-test
```

## Next Steps

- [PyPI](pypi.md) — Publishing details
- [Building](../development/building.md) — Build packages
