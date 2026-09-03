"""Tests for fenrir.pool — ConnectionPool and DatabasePool."""
import asyncio

import pytest

from fenrir.pool import ConnectionPool, DatabasePool, _PoolItem


def _counter():
    """Factory that returns incrementing integers as 'connections'."""
    n = 0
    def create():
        nonlocal n
        n += 1
        return n
    return create


class TestPoolItem:
    def test_conn_attribute(self):
        item = _PoolItem("conn1")
        assert item.conn == "conn1"

    def test_timestamps_set(self):
        item = _PoolItem("c")
        assert item.created_at > 0
        assert item.last_used > 0


class TestConnectionPoolInit:
    def test_default_values(self):
        pool = ConnectionPool(create_func=lambda: 1)
        assert pool._min_size == 1
        assert pool._max_size == 10
        assert pool._closed is False
        assert pool._initialized is False

    def test_custom_values(self):
        pool = ConnectionPool(create_func=lambda: 1, min_size=3, max_size=20)
        assert pool._min_size == 3
        assert pool._max_size == 20

    def test_stats_before_init(self):
        pool = ConnectionPool(create_func=lambda: 1)
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["idle"] == 0
        assert stats["max_size"] == 10

class TestConnectionPoolInitialize:
    @pytest.mark.anyio
    async def test_initialize_pre_fills(self):
        pool = ConnectionPool(create_func=_counter(), min_size=3, max_size=5)
        await pool.initialize()
        assert pool._initialized is True
        assert len(pool._pool) == 3

    @pytest.mark.anyio
    async def test_initialize_idempotent(self):
        pool = ConnectionPool(create_func=_counter(), min_size=2, max_size=5)
        await pool.initialize()
        await pool.initialize()  # should not error or double-fill
        assert len(pool._pool) == 2

    @pytest.mark.anyio
    async def test_initialize_with_validate_func(self):
        validate = lambda conn: conn > 0
        pool = ConnectionPool(create_func=_counter(), min_size=2, max_size=5, validate_func=validate)
        await pool.initialize()
        assert pool._initialized is True


class TestConnectionPoolAcquire:
    @pytest.mark.anyio
    async def test_acquire_returns_connection(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        async with pool.acquire() as conn:
            assert conn is not None

    @pytest.mark.anyio
    async def test_acquire_reuses_idle(self):
        counter = _counter()
        pool = ConnectionPool(create_func=counter, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            first = conn
        # Pool should have 1 idle now
        assert len(pool._pool) == 1
        async with pool.acquire() as conn2:
            # Should reuse from pool, not create new
            assert conn2 == first

    @pytest.mark.anyio
    async def test_acquire_when_closed_raises(self):
        pool = ConnectionPool(create_func=_counter(), min_size=0, max_size=3)
        await pool.close()
        with pytest.raises(RuntimeError, match="closed"):
            async with pool.acquire():
                pass

    @pytest.mark.anyio
    async def test_acquire_discards_on_exception(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        with pytest.raises(ValueError):
            async with pool.acquire() as conn:
                raise ValueError("fail")
        # Connection should be discarded, not returned to pool
        assert pool.stats["active"] == 0

    @pytest.mark.anyio
    async def test_connection_property(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        pc = pool.acquire()
        conn = await pc.__aenter__()
        assert pc.connection is conn
        await pc.__aexit__(None, None, None)

    @pytest.mark.anyio
    async def test_aexit_no_item(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        pc = pool.acquire()
        assert await pc.__aexit__(None, None, None) is False

    @pytest.mark.anyio
    async def test_acquire_destroys_invalid_idle(self):
        closed = []
        pool = ConnectionPool(
            create_func=_counter(),
            close_func=lambda c: closed.append(c),
            validate_func=lambda c: False,
            min_size=1,
            max_size=3,
        )
        await pool.initialize()
        async with pool.acquire() as conn:
            assert conn is not None
        assert len(closed) == 1

    @pytest.mark.anyio
    async def test_acquire_create_failure(self):
        def fail():
            raise RuntimeError("create failed")

        pool = ConnectionPool(create_func=fail, min_size=0, max_size=3)
        with pytest.raises(RuntimeError, match="create failed"):
            async with pool.acquire() as conn:
                pass
        assert pool.stats["active"] == 0


class TestConnectionPoolClose:
    @pytest.mark.anyio
    async def test_close_empty_pool(self):
        pool = ConnectionPool(create_func=_counter(), min_size=0, max_size=3)
        await pool.close()
        assert pool._closed is True

    @pytest.mark.anyio
    async def test_close_async_close_func(self):
        closed = []

        async def _async_close(c):
            closed.append(c)

        pool = ConnectionPool(create_func=_counter(), close_func=_async_close, min_size=2, max_size=5)
        await pool.initialize()
        await pool.close()
        assert len(closed) == 2

    @pytest.mark.anyio
    async def test_close_func_raises_warns(self, caplog):
        def bad_close(c):
            raise RuntimeError("close failed")

        pool = ConnectionPool(create_func=_counter(), close_func=bad_close, min_size=1, max_size=3)
        await pool.initialize()
        await pool.close()
        assert "Error closing connection" in caplog.text

    @pytest.mark.anyio
    async def test_release_when_not_initialized(self):
        pool = ConnectionPool(create_func=_counter(), min_size=0, max_size=3)
        await pool._release(_PoolItem("x"))

    @pytest.mark.anyio
    async def test_release_when_closed(self):
        closed = []
        pool = ConnectionPool(create_func=_counter(), close_func=lambda c: closed.append(c), min_size=1, max_size=3)
        await pool.initialize()
        pool._closed = True
        await pool._release(_PoolItem("c"))
        assert closed == ["c"]

    @pytest.mark.anyio
    async def test_discard_when_not_initialized(self):
        closed = []
        pool = ConnectionPool(create_func=_counter(), close_func=lambda c: closed.append(c), min_size=0, max_size=3)
        await pool._discard(_PoolItem("x"))
        assert closed == ["x"]

    @pytest.mark.anyio
    async def test_close_with_connections(self):
        pool = ConnectionPool(create_func=_counter(), min_size=2, max_size=5)
        await pool.initialize()
        await pool.close()
        assert pool._closed is True
        assert len(pool._pool) == 0

    @pytest.mark.anyio
    async def test_close_calls_close_func(self):
        closed = []
        pool = ConnectionPool(
            create_func=_counter(),
            close_func=lambda c: closed.append(c),
            min_size=2,
            max_size=5,
        )
        await pool.initialize()
        await pool.close()
        assert len(closed) == 2


class TestConnectionPoolValidation:
    @pytest.mark.anyio
    async def test_validate_connection_expired_lifetime(self):
        pool = ConnectionPool(create_func=_counter(), max_lifetime_seconds=0)
        await pool.initialize()
        item = pool._pool[0]
        # Force old timestamp
        item.created_at = -999
        valid = await pool._validate_connection(item)
        assert valid is False

    @pytest.mark.anyio
    async def test_validate_connection_expired_idle(self):
        pool = ConnectionPool(create_func=_counter(), max_idle_seconds=0)
        await pool.initialize()
        item = pool._pool[0]
        item.last_used = -999
        valid = await pool._validate_connection(item)
        assert valid is False

    @pytest.mark.anyio
    async def test_validate_with_custom_func(self):
        pool = ConnectionPool(create_func=_counter(), validate_func=lambda c: False)
        await pool.initialize()
        item = pool._pool[0]
        valid = await pool._validate_connection(item)
        assert valid is False

    @pytest.mark.anyio
    async def test_validate_with_async_func(self):
        async def validate(conn):
            return True
        pool = ConnectionPool(create_func=_counter(), validate_func=validate)
        await pool.initialize()
        item = pool._pool[0]
        valid = await pool._validate_connection(item)
        assert valid is True

    @pytest.mark.anyio
    async def test_validate_exception_returns_false(self):
        def bad_validate(conn):
            raise RuntimeError("broken")
        pool = ConnectionPool(create_func=_counter(), validate_func=bad_validate)
        await pool.initialize()
        item = pool._pool[0]
        valid = await pool._validate_connection(item)
        assert valid is False


class TestConnectionPoolStats:
    @pytest.mark.anyio
    async def test_stats_after_acquire(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        async with pool.acquire():
            stats = pool.stats
            assert stats["active"] == 1
            assert stats["idle"] == 0

    @pytest.mark.anyio
    async def test_stats_after_release(self):
        pool = ConnectionPool(create_func=_counter(), min_size=1, max_size=3)
        async with pool.acquire():
            pass
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["idle"] >= 1


class TestDatabasePool:
    @pytest.mark.anyio
    async def test_execute_with_retry_success(self):
        pool = DatabasePool(create_func=_counter(), min_size=1, max_size=3)

        def query(conn):
            return conn * 10

        result = await pool.execute_with_retry(query)
        assert result == 10

    @pytest.mark.anyio
    async def test_execute_with_retry_failure(self):
        pool = DatabasePool(create_func=_counter(), min_size=1, max_size=3, retry_attempts=2, retry_backoff=0.01)

        def failing_query(conn):
            raise RuntimeError("db error")

        with pytest.raises(RuntimeError, match="db error"):
            await pool.execute_with_retry(failing_query)

    @pytest.mark.anyio
    async def test_execute_with_retry_async_func(self):
        pool = DatabasePool(create_func=_counter(), min_size=1, max_size=3)

        async def async_query(conn):
            return conn + 100

        result = await pool.execute_with_retry(async_query)
        assert result == 101

    @pytest.mark.anyio
    async def test_execute_with_custom_retries(self):
        pool = DatabasePool(create_func=_counter(), min_size=1, max_size=3, retry_attempts=5)
        count = 0

        def flaky(conn):
            nonlocal count
            count += 1
            if count < 3:
                raise RuntimeError("not yet")
            return "ok"

        result = await pool.execute_with_retry(flaky, retries=5)
        assert result == "ok"


class TestPoolConcurrency:
    @pytest.mark.anyio
    async def test_concurrent_acquires(self):
        pool = ConnectionPool(create_func=_counter(), min_size=0, max_size=3)
        results = []

        async def worker(i):
            async with pool.acquire() as conn:
                results.append(conn)

        await asyncio.gather(*(worker(i) for i in range(3)))
        assert len(results) == 3
