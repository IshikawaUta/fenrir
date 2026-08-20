
import pytest

from fenrir import Depends, Fenrir
from fenrir.testing import TestClient

cleanup_logs = []

@pytest.fixture(autouse=True)
def run_around():
    cleanup_logs.clear()
    yield

def get_sync_db():
    cleanup_logs.append("db_init")
    try:
        yield "db_session"
    finally:
        cleanup_logs.append("db_cleanup")


async def get_async_db():
    cleanup_logs.append("async_db_init")
    try:
        yield "async_db_session"
    finally:
        cleanup_logs.append("async_db_cleanup")


@pytest.mark.anyio
async def test_yield_dependencies():
    app = Fenrir()

    @app.get("/sync-dep")
    async def sync_endpoint(db: str = Depends(get_sync_db)):
        cleanup_logs.append(f"endpoint_use:{db}")
        return {"db": db}

    client = TestClient(app)
    resp = await client.get("/sync-dep")

    assert resp.status_code == 200
    assert resp.json() == {"db": "db_session"}

    # Check the sequence of events
    assert cleanup_logs == ["db_init", "endpoint_use:db_session", "db_cleanup"]


@pytest.mark.anyio
async def test_async_yield_dependencies():
    app = Fenrir()

    @app.get("/async-dep")
    async def async_endpoint(db: str = Depends(get_async_db)):
        cleanup_logs.append(f"async_endpoint_use:{db}")
        return {"db": db}

    client = TestClient(app)
    resp = await client.get("/async-dep")

    assert resp.status_code == 200
    assert resp.json() == {"db": "async_db_session"}

    # Check the sequence of events
    assert cleanup_logs == ["async_db_init", "async_endpoint_use:async_db_session", "async_db_cleanup"]


# Cache testing variables
resolve_count = 0

def counting_dep():
    global resolve_count
    resolve_count += 1
    return resolve_count

@pytest.mark.anyio
async def test_dependency_caching():
    global resolve_count
    resolve_count = 0
    app = Fenrir()

    @app.get("/caching")
    async def caching_endpoint(
        a: int = Depends(counting_dep, use_cache=True),
        b: int = Depends(counting_dep, use_cache=True),
        c: int = Depends(counting_dep, use_cache=False)
    ):
        return {"a": a, "b": b, "c": c}

    client = TestClient(app)
    resp = await client.get("/caching")

    assert resp.status_code == 200
    # a and b are cached, so they return the same number (1).
    # c has use_cache=False, so it increments resolve_count again (2).
    assert resp.json() == {"a": 1, "b": 1, "c": 2}
    assert resolve_count == 2
