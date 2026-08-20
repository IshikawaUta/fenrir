# Contributing to Fenrir

Thanks for considering contributing to Fenrir! This document explains how to set
up a development environment, run the checks that CI runs, and follow the
project's conventions.

## Development Setup

Fenrir supports Python 3.8 – 3.13. Install the package in editable mode with
the full optional dependency set:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pip install pytest pytest-codspeed httpx anyio typeguard Mako falcon sanic fakeredis coverage
```

## Running the Test Suite

Always run the **full suite**, not individual files:

```bash
PYTHONPATH=. pytest -q --no-header -p no:cacheprovider
```

> **Known local flakiness.** A few tests (e.g.
> `tests/test_bugfixes.py::TestPaginationFix`) can fail with
> `ImportError: cannot import name 'import_string' from partially initialized
> module 'pydantic._internal._validators'` when a test file that imports
> `pydantic` is executed **in isolation** or in a narrow selection. This is
> caused by a pydantic version-migration shim (`pydantic/_migration.py`)
> interacting with `shibokensupport`; it does **not** reproduce when the full
> suite runs and is not a code bug. Run the whole suite if you hit it.

## Linting (ruff)

The project uses `ruff` with rules `E, F, W, I, B` and a line length of 120
(see `pyproject.toml`). Run:

```bash
ruff check fenrir tests
```

Most findings can be auto-fixed with `ruff check fenrir tests --fix`. Note:

- The vendored `fenrir/bottle.py` and `bottle_tests/` are excluded.
- Tests have targeted per-file ignores (`B008`, `B017`, `B023`, `B007`,
  `E402`, `E731`, `E712`, `F841`) — keep new tests consistent with these.

## Type Checking (mypy)

Fenrir is a mostly-untyped legacy codebase, so mypy is configured to stay
strict on annotated code while tolerating legacy patterns. CI runs exactly:

```bash
mypy fenrir tests
```

Configuration (`pyproject.toml`):
- `no_implicit_optional = false` — the codebase uses implicit `Optional`
  defaults (`detail: str = None`) throughout.
- `follow_imports = "skip"` — avoids cross-module `attr-defined` noise from
  the mixin/dynamic-attribute architecture.
- `disable_error_code = ["var-annotated", "annotation-unchecked"]`.
- The vendored `fenrir/bottle.py` is excluded from type checking.

If you touch annotated code, keep it mypy-clean. Dynamic attributes that
cannot be declared (e.g. hooks attached to callables, `Request._dependency_cache`)
are silenced with targeted `# type: ignore[attr-defined]` comments.

## Coverage

Coverage is configured in `pyproject.toml` (`source = ["fenrir"]`, branch
coverage, bottle excluded). Run the suite with coverage:

```bash
PYTHONPATH=. coverage run -m pytest -q --no-header -p no:cacheprovider
coverage report -m
coverage xml -o coverage.xml   # CI uploads this to Codecov
```

The project targets **100% coverage per module** (overall ~99%). If you add
behavior to `fenrir`, extend the matching `tests/test_*_coverage.py` suite so
the new lines stay covered.

## Benchmarks

- **`benchmark.py`** — multi-framework comparison (Fenrir vs FastAPI vs Flask
  vs Falcon vs Sanic). Requires `pip install fastapi flask falcon sanic
  sanic-testing httpx`. Run with `python benchmark.py`.
- **CodSpeed micro-benchmarks** — `tests/benchmarks/` use the `benchmark`
  fixture from `pytest-codspeed` and are **skipped** in the regular test run.
  To run them locally:
  ```bash
  pip install pytest-codspeed
  pytest tests/benchmarks --codspeed
  ```

## Continuous Integration

`.github/workflows/`:

1. **test.yml** — `lint` job (ruff + mypy on Python 3.13) and `test` job (full
   suite with coverage across Python 3.8 – 3.13, uploading `coverage.xml` to
   Codecov).
2. **codspeed.yml** — CodSpeed performance regression tracking on PRs.
3. **benchmark.yml** — runs `benchmark.py`; results posted to the job summary.
4. **zizmor.yml** — security audit of the workflow files themselves.
5. **release.yml** — creates a GitHub Release from the matching CHANGELOG
   section when a `v*` tag is pushed.
6. **docker.yml** — builds multi-arch GHCR images.
7. **publish.yml** — publishes to PyPI via trusted publishing on release.

All actions are pinned to immutable SHAs and updated weekly by Dependabot.
Make sure both test.yml jobs (and ideally zizmor) pass before opening a pull
request.

## Conventions

- **Compatibility:** Fenrir must keep running on Python 3.8. Avoid syntax and
  typing constructs that break on 3.8 (no `X | None`, no built-in generics in
  annotations without `from __future__ import annotations`).
- **Style:** follow the existing code style and keep ruff clean.
- **Tests:** add tests for any new behavior; verify with the full suite.
- **Commits:** use short imperative subjects (e.g. `fix: ...`, `release: ...`),
  matching the existing history.

## Pull Requests

1. Run the full test suite locally.
2. Run `ruff check fenrir tests` and the scoped `mypy` command above.
3. Open the PR against `main` (or `master`).