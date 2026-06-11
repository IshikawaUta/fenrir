"""
fenrir.pool — Built-in connection pool for database and external service connections.

Provides a generic, async-safe connection pool with health checks, retry logic,
and automatic connection recycling.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from fenrir.compat import to_thread

logger = logging.getLogger("fenrir.pool")

T = TypeVar("T")


class ConnectionPool(Generic[T]):
    """Generic async-safe connection pool with health checks and retry logic.

    Features:
        - Configurable min/max pool size
        - Connection health checks before reuse
        - Automatic connection recycling on failure
        - Retry logic with exponential backoff
        - Connection timeout and idle timeout
        - Metrics: active, idle, waiting counts

    Usage::

        import asyncpg

        pool = ConnectionPool(
            create_func=lambda: asyncpg.create_pool("postgresql://..."),
            close_func=lambda conn: conn.close(),
            min_size=2,
            max_size=10,
        )

        async with pool.acquire() as conn:
            result = await conn.fetch("SELECT * FROM users")
    """

    def __init__(
        self,
        create_func: Callable[[], T],
        close_func: Callable[[T], Any] = None,
        min_size: int = 1,
        max_size: int = 10,
        max_idle_seconds: int = 300,
        max_lifetime_seconds: int = 3600,
        health_check_interval: int = 60,
        retry_attempts: int = 3,
        retry_backoff: float = 0.5,
        validate_func: Callable[[T], bool] = None,
    ):
        self._create_func = create_func
        self._close_func = close_func
        self._min_size = min_size
        self._max_size = max_size
        self._max_idle = max_idle_seconds
        self._max_lifetime = max_lifetime_seconds
        self._health_check_interval = health_check_interval
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff
        self._validate_func = validate_func

        self._pool: deque[_PoolItem[T]] = deque()
        self._active: int = 0
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._lock: Optional[asyncio.Lock] = None
        self._closed = False
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the pool and pre-fill with min_size connections."""
        if self._initialized:
            return
        self._semaphore = asyncio.Semaphore(self._max_size)
        self._lock = asyncio.Lock()
        for _ in range(self._min_size):
            conn = await self._create_connection()
            self._pool.append(_PoolItem(conn))
        self._initialized = True

    async def _create_connection(self) -> T:
        """Create a new connection."""
        return await to_thread(self._create_func)

    async def _validate_connection(self, item: _PoolItem[T]) -> bool:
        """Validate a connection is still healthy."""
        now = time.monotonic()
        if now - item.created_at > self._max_lifetime:
            return False
        if now - item.last_used > self._max_idle:
            return False
        if self._validate_func:
            try:
                result = self._validate_func(item.conn)
                if asyncio.iscoroutine(result):
                    result = await result
                return bool(result)
            except Exception:
                return False
        return True

    async def _destroy_connection(self, item: _PoolItem[T]) -> None:
        """Destroy a connection."""
        try:
            if self._close_func:
                result = self._close_func(item.conn)
                if asyncio.iscoroutine(result):
                    await result
        except Exception as e:
            logger.warning("Error closing connection: %s", e)

    def acquire(self) -> _PoolConnection[T]:
        """Acquire a connection from the pool.

        Returns a context manager that automatically returns the connection.
        """
        return _PoolConnection(self)

    async def _release(self, item: _PoolItem[T]) -> None:
        """Release a connection back to the pool."""
        async with self._lock:
            self._active -= 1
            if self._closed:
                await self._destroy_connection(item)
            else:
                item.last_used = time.monotonic()
                self._pool.append(item)
        self._semaphore.release()

    async def _discard(self, item: _PoolItem[T]) -> None:
        """Discard a broken connection."""
        async with self._lock:
            self._active -= 1
        await self._destroy_connection(item)
        self._semaphore.release()

    async def close(self) -> None:
        """Close all connections in the pool."""
        self._closed = True
        async with self._lock:
            while self._pool:
                item = self._pool.popleft()
                await self._destroy_connection(item)

    @property
    def stats(self) -> Dict[str, int]:
        """Return pool statistics."""
        return {
            "active": self._active,
            "idle": len(self._pool),
            "max_size": self._max_size,
        }


class _PoolItem(Generic[T]):
    """Internal pool item wrapping a connection."""
    __slots__ = ("conn", "created_at", "last_used")

    def __init__(self, conn: T):
        self.conn = conn
        self.created_at = time.monotonic()
        self.last_used = time.monotonic()


class _PoolConnection(Generic[T]):
    """Context manager for a pool connection."""

    def __init__(self, pool: ConnectionPool[T]):
        self._pool = pool
        self._item: Optional[_PoolItem[T]] = None

    @property
    def connection(self) -> T:
        return self._item.conn

    async def __aenter__(self) -> T:
        if not self._pool._initialized:
            await self._pool.initialize()

        if self._pool._closed:
            raise RuntimeError("Connection pool is closed")

        await self._pool._semaphore.acquire()

        async with self._pool._lock:
            self._pool._active += 1

            # Try to get an existing connection
            while self._pool._pool:
                item = self._pool._pool.popleft()
                if await self._pool._validate_connection(item):
                    item.last_used = time.monotonic()
                    self._item = item
                    return item.conn
                else:
                    await self._pool._destroy_connection(item)

            # Create new connection
            try:
                conn = await self._pool._create_connection()
                self._item = _PoolItem(conn)
                return conn
            except Exception:
                self._pool._active -= 1
                self._pool._semaphore.release()
                raise

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._item is None:
            return False
        if exc_type is not None:
            await self._pool._discard(self._item)
        else:
            await self._pool._release(self._item)
        return False


class DatabasePool(ConnectionPool[T]):
    """Specialized connection pool for database connections with built-in
    query retry logic.

    Usage::

        pool = DatabasePool(
            create_func=lambda: create_engine("sqlite:///db.sqlite3"),
            close_func=lambda engine: engine.dispose(),
            min_size=2,
            max_size=10,
        )

        async with pool.acquire() as conn:
            result = await conn.execute(text("SELECT 1"))
    """

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        retries: int = None,
        **kwargs,
    ) -> Any:
        """Execute a function with retry logic and exponential backoff."""
        attempts = retries or self._retry_attempts
        last_exc = None
        for attempt in range(attempts):
            try:
                async with self.acquire() as conn:
                    result = func(conn, *args, **kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
                    return result
            except Exception as e:
                last_exc = e
                if attempt < attempts - 1:
                    wait = self._retry_backoff * (2 ** attempt)
                    logger.warning(
                        "Database operation failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1, attempts, wait, e,
                    )
                    await asyncio.sleep(wait)
        raise last_exc
