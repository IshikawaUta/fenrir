"""CodSpeed micro-benchmarks for Fenrir core hot paths.

Run with: ``pytest tests/benchmarks --codspeed``
"""

import pytest

from fenrir.performance import fast_json_dumps, fast_json_loads
from fenrir.routing import Router

pytestmark = pytest.mark.benchmark


def _handler():
    return {"ok": True}


@pytest.mark.benchmark
def test_fast_json_dumps(benchmark):
    data = {
        "id": 1,
        "name": "fenrir" * 20,
        "tags": ["async", "web", "framework"],
        "nested": {"ok": True, "items": list(range(10))},
    }
    benchmark(fast_json_dumps, data)


@pytest.mark.benchmark
def test_fast_json_loads(benchmark):
    raw = (
        b'{"id": 1, "name": "fenrir", "tags": ["async", "web", "framework"], '
        b'"nested": {"ok": true, "items": [0, 1, 2, 3, 4]}}'
    )
    benchmark(fast_json_loads, raw)


@pytest.mark.benchmark
def test_router_static_match(benchmark):
    router = Router()
    router.add_route("/users", _handler)
    router.add_route("/users/<id:int>", _handler)
    router.add_route("/posts/<year:int>/<slug>", _handler)

    def _match():
        router.match("/users", "GET")

    benchmark(_match)


@pytest.mark.benchmark
def test_router_parametric_match(benchmark):
    router = Router()
    router.add_route("/users", _handler)
    router.add_route("/users/<id:int>", _handler)
    router.add_route("/posts/<year:int>/<slug>", _handler)

    def _match():
        router.match("/users/42", "GET")

    benchmark(_match)


@pytest.mark.benchmark
def test_router_miss(benchmark):
    router = Router()
    router.add_route("/users", _handler)
    router.add_route("/users/<id:int>", _handler)

    def _match():
        try:
            router.match("/not/found", "GET")
        except Exception:
            pass

    benchmark(_match)
