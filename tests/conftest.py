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
    """Cancel lingering async tasks and close event loops to prevent hangs."""
    # Get the event loop (if any)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    
    if loop and not loop.is_closed():
        # Cancel all pending tasks
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if pending:
            for task in pending:
                task.cancel()
            # Wait for tasks to finish cancellation
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        
        # Close the loop
        if loop.is_running():
            loop.stop()
        loop.close()
    
    # Force garbage collection to clean up any remaining resources
    gc.collect()
    
    # Clear the event loop reference
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatically cleanup after each test."""
    yield
    # Force GC after each test
    gc.collect()
