import pytest
from fenrir import Fenrir

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def app():
    app = Fenrir(title="TestApp")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["SESSION_COOKIE_SECURE"] = False
    return app

@pytest.fixture
async def client(app):
    async with app.test_client() as c:
        yield c

import asyncio
import gc
import sys

@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    # Cancel any lingering tasks and close event loops
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if pending:
            for t in pending:
                t.cancel()
            # Wait for cancellation
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
    # Force GC to close generators etc.
    gc.collect()
    # Ensure asyncio default loop is cleared
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass
