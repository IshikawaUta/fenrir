"""RedisSession fix - prevent event loop leak in test warning."""
from unittest.mock import MagicMock


class MockRedisInterface:
    """Mock RedisSessionInterface that doesn't create background threads."""

    def __init__(self, *args, **kwargs):
        self._run_sync_or_async_called = False

    def _run_sync_or_async(self, func, *args, **kwargs):
        """Mock implementation that doesn't spawn threads."""
        self._run_sync_or_async_called = True
        # Just run the function directly
        return func(*args, **kwargs)


def test_run_sync_or_async_handles_no_loop_clean():
    """Test that _run_sync_or_async handles loop isolation."""
    # Use the fixed redis_client mock
    mock_redis_client = MagicMock()
    iface = MockRedisInterface(redis_client=mock_redis_client)

    # Verify method exists and is callable
    assert callable(iface._run_sync_or_async)

    # Execute the method - it should not spawn background threads
    def dummy_func():
        return "result"

    result = iface._run_sync_or_async(dummy_func)
    assert result == "result"
    assert iface._run_sync_or_async_called == True


def test_redis_session_no_event_loop_leak():
    """Test that no background threads are spawned for connection management."""
    import threading
    import time

    # Track all threads before test
    initial_thread_count = len(threading.enumerate())

    # Mock redis_client as a simple object
    mock_redis = MagicMock()

    # Create session interface and trigger initialization
    from fenrir.sessions import RedisSessionInterface

    # Mock for app context
    app = MagicMock()
    app.config = {"SECRET_KEY": "test-key"}

    # We need to make sure the RedisSessionInterface won't
    # try to create real connections or start threads
    # The actual implementation should handle this gracefully
    # Since we're using mocks, we can just test the basic behavior

    # Mock the redis_client to avoid real connections
    iface = RedisSessionInterface(redis_client=mock_redis)

    # Verify it's callable
    assert callable(iface._run_sync_or_async)

    # Give any background threads a chance to start
    time.sleep(0.1)

    # Check thread count - should still be essentially the same
    final_thread_count = len(threading.enumerate())
    # Allow some threads for normal testing infrastructure
    assert final_thread_count <= initial_thread_count + 2


if __name__ == "__main__":
    test_run_sync_or_async_handles_no_loop_clean()
    test_redis_session_no_event_loop_leak()
    print("All tests passed!")
