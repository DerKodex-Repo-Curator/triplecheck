# Contributing to triplecheck

Thanks for your interest! Here's how to get started.

## Dev Setup

```bash
git clone https://github.com/raullenchai/triplecheck.git
cd triplecheck
python -m venv .venv && source .venv/bin/activate
pip install -e '.[graph]'
pip install pytest ruff
```

## Running Tests

```bash
pytest tests/ -v
```

## Linting

```bash
ruff check triplecheck/
ruff format --check triplecheck/
```

## Making Changes

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes
3. Add tests if applicable
4. Run `pytest` and `ruff check` to make sure everything passes
5. Commit with a descriptive message: `feat: add X` / `fix: resolve Y`
6. Open a PR against `main`

## Adding a New Provider

1. Create `triplecheck/providers/my_provider.py`
2. Subclass `BaseProvider` — implement `review()`, `fix()`, `judge()`
3. Register in `triplecheck/roles.py` → `PROVIDER_MAP`
4. Add example model config to `config.example.yml`
5. Add a test in `tests/`

## Commit Style

```
feat: add new feature
fix: resolve bug
docs: update README
test: add tests for X
chore: update deps
refactor: restructure Y
```

## Questions?

Open an issue — happy to help.
