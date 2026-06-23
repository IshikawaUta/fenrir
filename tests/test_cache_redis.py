"""Tests for fenrir.cache — RedisCache with fakeredis."""
import asyncio
import pytest
from unittest.mock import patch
from fenrir.cache import RedisCache, Cache


@pytest.fixture
def fake_redis():
    """Create a fakeredis instance with proper event loop for Python 3.9."""
    import fakeredis.aioredis
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = fakeredis.FakeServer()
    r = fakeredis.aioredis.FakeRedis(server=server)
    yield r
    loop.close()


@pytest.fixture
def redis_cache(fake_redis):
    """Create a RedisCache with fakeredis backend."""
    rc = RedisCache(prefix="test:")
    rc._redis = fake_redis
    return rc


# ═══════════════════════════════════════════════════════════════════════
# RedisCache Tests
# ═══════════════════════════════════════════════════════════════════════

class TestRedisCache:
    @pytest.mark.anyio
    async def test_set_get(self, redis_cache):
        await redis_cache.set("key1", "value1")
        result = await redis_cache.get("key1")
        assert result == "value1"

    @pytest.mark.anyio
    async def test_get_not_found(self, redis_cache):
        result = await redis_cache.get("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_delete(self, redis_cache):
        await redis_cache.set("key1", "value1")
        assert await redis_cache.delete("key1") is True
        assert await redis_cache.get("key1") is None

    @pytest.mark.anyio
    async def test_exists(self, redis_cache):
        await redis_cache.set("key1", "value1")
        assert await redis_cache.exists("key1") is True
        assert await redis_cache.exists("nope") is False

    @pytest.mark.anyio
    async def test_clear(self, redis_cache):
        await redis_cache.set("a", "1")
        await redis_cache.set("b", "2")
        await redis_cache.clear()
        assert await redis_cache.get("a") is None
        assert await redis_cache.get("b") is None

    @pytest.mark.anyio
    async def test_get_many(self, redis_cache):
        await redis_cache.set("a", "1")
        await redis_cache.set("b", "2")
        results = await redis_cache.get_many(["a", "b", "c"])
        assert results == {"a": "1", "b": "2"}

    @pytest.mark.anyio
    async def test_set_many(self, redis_cache):
        await redis_cache.set_many({"a": "1", "b": "2"})
        assert await redis_cache.get("a") == "1"
        assert await redis_cache.get("b") == "2"

    @pytest.mark.anyio
    async def test_set_with_ttl(self, redis_cache):
        await redis_cache.set("key1", "value1", ttl=60)
        result = await redis_cache.get("key1")
        assert result == "value1"

    @pytest.mark.anyio
    async def test_close(self, redis_cache):
        await redis_cache.close()
        # Should not raise

    @pytest.mark.anyio
    async def test_context_manager(self, redis_cache):
        async with redis_cache:
            assert redis_cache._redis is not None


# ═══════════════════════════════════════════════════════════════════════
# RedisCache with Cache wrapper
# ═══════════════════════════════════════════════════════════════════════

class TestRedisCacheWithCache:
    @pytest.mark.anyio
    async def test_cache_wrapper(self, fake_redis):
        rc = RedisCache(prefix="test:")
        rc._redis = fake_redis
        c = Cache(backend=rc)

        await c.set("k", "v")
        assert await c.get("k") == "v"

    @pytest.mark.anyio
    async def test_cached_decorator(self, fake_redis):
        rc = RedisCache(prefix="test:")
        rc._redis = fake_redis
        c = Cache(backend=rc)
        call_count = 0

        @c.cached(ttl=60)
        async def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        r1 = await expensive(5)
        r2 = await expensive(5)
        assert r1 == 10
        assert r2 == 10
        assert call_count == 1

    @pytest.mark.anyio
    async def test_invalidate_with_prefix(self, fake_redis):
        rc = RedisCache(prefix="test:")
        rc._redis = fake_redis
        c = Cache(backend=rc)
        await c.set("users:1", "Alice")

        @c.invalidate(key_prefix="users")
        async def update():
            return "done"

        await update()
        # Prefix-based invalidation on Redis uses SCAN
