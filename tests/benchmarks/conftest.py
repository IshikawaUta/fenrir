"""Pytest configuration for CodSpeed micro-benchmarks.

Benchmarks in this directory use the ``benchmark`` fixture provided by
``pytest-codspeed``. When that plugin is not installed (e.g. in the regular
CI test run) the benchmarks are skipped instead of failing.
"""

from pathlib import Path

import pytest

_BENCHMARKS_DIR = Path(__file__).parent


def pytest_configure(config):
    config.addinivalue_line("markers", "benchmark: CodSpeed micro-benchmark")


def pytest_collection_modifyitems(config, items):
    try:
        import pytest_codspeed  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(reason="pytest-codspeed is not installed")
        for item in items:
            if _BENCHMARKS_DIR in Path(item.path).parents:
                item.add_marker(skip)
