# PyPI Publishing

Automated and manual publishing to PyPI.

## Automated Publishing (Recommended)

When a GitHub Actions workflow is configured:

1. Push a tag matching `v*` (e.g., `v0.1.0`)
2. GitHub Actions builds sdist + wheel
3. Uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) to upload

### One-Time Setup

#### GitHub Environment

1. Repository → **Settings → Environments** → **New environment**
2. Name it exactly: **`pypi`**
3. Optional: add protection rules

#### PyPI Trusted Publisher

1. [pypi.org](https://pypi.org/manage/account/) → **Publishing**
2. Under "Add a new pending publisher":

   | Field | Value |
   |-------|-------|
   | PyPI project name | `recipebrain` |
   | Owner | your GitHub username or org |
   | Repository name | `recipebrain` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. Click **Add**

## Manual Publishing

For emergency releases:

```bash
pip install build twine
python -m build
twine check dist/*

# Test PyPI first (optional)
twine upload --repository testpypi dist/*

# Production
twine upload dist/*
```

## Verify Installation

```bash
python3 -m venv /tmp/pypi-test
source /tmp/pypi-test/bin/activate
pip install recipebrain
recipebrain --help
deactivate
rm -rf /tmp/pypi-test
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Environment 'pypi' not found` | Environment doesn't exist | Create in GitHub Settings |
| `403 … not allowed to upload` | Publisher not configured | Add trusted publisher on PyPI |
| Package is empty after publish | Build not finding source | Check `[tool.setuptools.packages.find]` |
| `The name 'recipebrain' is already taken` | Name conflict | Use pending publisher before first upload |

## Next Steps

- [Release Process](release-process.md) — Version, tag, publish workflow
- [Building](../development/building.md) — Build packages locally
