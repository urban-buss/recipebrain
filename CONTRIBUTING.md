# Contributing to recipebrain

## Setup

```bash
git clone https://github.com/<owner>/recipebrain.git
cd recipebrain
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
pytest
```

## Test Discipline

Every code change must include corresponding tests. Never submit production code without tests.

- Add unit tests in `tests/test_<module>.py`.
- Cover the happy path, edge cases, and error cases.
- Use `tmp_path` for file I/O — never write to real `output/` or `dossiers/`.
- Run `pytest` before considering any task complete.

## Code Style

- **Formatter/linter:** ruff (configured in `pyproject.toml`).
- **Type checker:** mypy (strict mode disabled initially, but `warn_unused_ignores = true`).
- Both must pass before merge:
  ```bash
  ruff check .
  ruff format --check .
  mypy src/recipebrain
  ```

## Commit Messages

- Imperative mood, lowercase subject: `add fooby source adapter`
- No prefix convention required (no `fix:`, `feat:` mandated).
- Keep subject ≤ 72 characters; body explains *why* if non-obvious.

## Branching

- `main` is protected — PRs only.
- Branch from `main`, rebase before merge.
- Delete branches after merge.

## Adding a Recipe Source Adapter

1. Create `src/recipebrain/sources/<name>.py` implementing `SourceAdapter`.
2. Add tests in `tests/test_sources_<name>.py`.
3. Register in source config (when registry is implemented).
4. Run full test suite.

## Adding a Promotion Adapter

1. Create `src/recipebrain/promotions/<name>.py` implementing `PromotionAdapter`.
2. Add tests in `tests/test_promotions_<name>.py`.
3. Run full test suite.
