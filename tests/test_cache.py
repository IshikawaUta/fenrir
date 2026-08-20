"""Tests for fenrir.cache — Multi-backend caching system."""
import time

import pytest

from fenrir.cache import Cache, FileCache, MemoryCache

# ═══════════════════════════════════════════════════════════════════════
# MemoryCache Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryCache:
    @pytest.mark.anyio
    async def test_set_get(self):
        cache = MemoryCache()
        await cache.set("key", "value")
        result = await cache.get("key")
        assert result == "value"

    @pytest.mark.anyio
    async def test_get_nonexistent(self):
        cache = MemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_delete(self):
        cache = MemoryCache()
        await cache.set("key", "value")
        result = await cache.delete("key")
        assert result is True
        assert await cache.get("key") is None

    @pytest.mark.anyio
    async def test_exists(self):
        cache = MemoryCache()
        await cache.set("key", "value")
        assert await cache.exists("key") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.anyio
    async def test_clear(self):
        cache = MemoryCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.anyio
    async def test_ttl_expiry(self):
        cache = MemoryCache()
        await cache.set("key", "value", ttl=1)
        assert await cache.get("key") == "value"
        time.sleep(1.1)
        assert await cache.get("key") is None

    @pytest.mark.anyio
    async def test_max_size(self):
        cache = MemoryCache(max_size=2)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"

    @pytest.mark.anyio
    async def test_lru_order(self):
        cache = MemoryCache(max_size=2)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.get("key1")
        await cache.set("key3", "value3")
        assert await cache.get("key1") == "value1"
        assert await cache.get("key2") is None
        assert await cache.get("key3") == "value3"

    @pytest.mark.anyio
    async def test_get_many(self):
        cache = MemoryCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        result = await cache.get_many(["key1", "key2", "key3"])
        assert result == {"key1": "value1", "key2": "value2"}

    @pytest.mark.anyio
    async def test_set_many(self):
        cache = MemoryCache()
        await cache.set_many({"key1": "value1", "key2": "value2"})
        assert await cache.get("key1") == "value1"
        assert await cache.get("key2") == "value2"

    def test_stats(self):
        cache = MemoryCache(max_size=100)
        stats = cache.stats()
        assert stats["max_size"] == 100
        assert stats["size"] == 0


# ═══════════════════════════════════════════════════════════════════════
# FileCache Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFileCache:
    @pytest.mark.anyio
    async def test_set_get(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set("key", "value")
            result = await cache.get("key")
            assert result == "value"

    @pytest.mark.anyio
    async def test_ttl_expiry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir, ttl=1)
            await cache.set("key", "value", ttl=1)
            assert await cache.get("key") == "value"
            time.sleep(1.1)
            assert await cache.get("key") is None

    @pytest.mark.anyio
    async def test_delete(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set("key", "value")
            result = await cache.delete("key")
            assert result is True
            assert await cache.get("key") is None

    @pytest.mark.anyio
    async def test_clear(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.clear()
            assert await cache.get("key1") is None
            assert await cache.get("key2") is None


# ═══════════════════════════════════════════════════════════════════════
# Cache Wrapper Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCacheWrapper:
    @pytest.mark.anyio
    async def test_set_get(self):
        cache = Cache(MemoryCache())
        await cache.set("key", "value")
        result = await cache.get("key")
        assert result == "value"

    @pytest.mark.anyio
    async def test_cached_decorator(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60)
        async def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_func(5)
        result2 = await expensive_func(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.anyio
    async def test_cached_decorator_different_args(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60)
        async def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        await expensive_func(5)
        await expensive_func(10)

        assert call_count == 2

    @pytest.mark.anyio
    async def test_invalidate_decorator(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60, key_prefix="test")
        async def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - computes
        result1 = await expensive_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - cached
        result2 = await expensive_func(5)
        assert result2 == 10
        assert call_count == 1

        # Manually delete the cache entry
        await cache.delete("test:5")

        # Third call - recomputes
        result3 = await expensive_func(5)
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.anyio
    async def test_delete(self):
        cache = Cache(MemoryCache())
        await cache.set("key", "value")
        result = await cache.delete("key")
        assert result is True
        assert await cache.get("key") is None


# ═══════════════════════════════════════════════════════════════════════
# Extended MemoryCache Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryCacheExtended:
    @pytest.mark.anyio
    async def test_set_none_value(self):
        cache = MemoryCache()
        await cache.set("key", None)
        assert await cache.exists("key") is True

    @pytest.mark.anyio
    async def test_update_key(self):
        cache = MemoryCache()
        await cache.set("key", "value1")
        await cache.set("key", "value2")
        assert await cache.get("key") == "value2"

    @pytest.mark.anyio
    async def test_get_many_empty(self):
        cache = MemoryCache()
        result = await cache.get_many([])
        assert result == {}

    @pytest.mark.anyio
    async def test_set_many_empty(self):
        cache = MemoryCache()
        await cache.set_many({})
        assert cache.stats()["size"] == 0

    @pytest.mark.anyio
    async def test_delete_nonexistent(self):
        cache = MemoryCache()
        result = await cache.delete("missing")
        assert result is False

    @pytest.mark.anyio
    async def test_exists_after_expiry(self):
        cache = MemoryCache()
        await cache.set("key", "value", ttl=1)
        assert await cache.exists("key") is True
        time.sleep(1.1)
        assert await cache.exists("key") is False

    @pytest.mark.anyio
    async def test_get_many_with_expiry(self):
        cache = MemoryCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2", ttl=1)
        time.sleep(1.1)
        result = await cache.get_many(["key1", "key2"])
        assert result == {"key1": "value1"}

    def test_stats_after_operations(self):
        cache = MemoryCache(max_size=10)
        import asyncio
        asyncio.run(cache.set("key", "value"))
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["max_size"] == 10


# ═══════════════════════════════════════════════════════════════════════
# Cache Backend Base Class Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCacheBackendBase:
    @pytest.mark.anyio
    async def test_base_methods_not_implemented(self):
        from fenrir.cache import CacheBackend
        backend = CacheBackend()
        with pytest.raises(NotImplementedError):
            await backend.get("key")
        with pytest.raises(NotImplementedError):
            await backend.set("key", "value")
        with pytest.raises(NotImplementedError):
            await backend.delete("key")
        with pytest.raises(NotImplementedError):
            await backend.exists("key")
        with pytest.raises(NotImplementedError):
            await backend.clear()
        with pytest.raises(NotImplementedError):
            await backend.get_many(["key"])


# ═══════════════════════════════════════════════════════════════════════
# FileCache Extended Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFileCacheExtended:
    @pytest.mark.anyio
    async def test_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set("key", "value")
            assert await cache.exists("key") is True
            assert await cache.exists("missing") is False

    @pytest.mark.anyio
    async def test_get_many(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            result = await cache.get_many(["key1", "key2", "missing"])
            assert result == {"key1": "value1", "key2": "value2"}

    @pytest.mark.anyio
    async def test_set_many(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            await cache.set_many({"key1": "value1", "key2": "value2"})
            assert await cache.get("key1") == "value1"
            assert await cache.get("key2") == "value2"

    @pytest.mark.anyio
    async def test_delete_nonexistent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=tmpdir)
            result = await cache.delete("missing")
            assert result is False


# ═══════════════════════════════════════════════════════════════════════
# Cache Decorator Extended Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCacheDecoratorExtended:
    @pytest.mark.anyio
    async def test_cached_with_key_func(self):
        cache = Cache(MemoryCache())
        call_count = 0

        def my_key_func(x, y):
            return f"custom:{x}:{y}"

        @cache.cached(ttl=60, key_func=my_key_func)
        async def add(x, y):
            nonlocal call_count
            call_count += 1
            return x + y

        r1 = await add(1, 2)
        r2 = await add(1, 2)
        assert r1 == 3
        assert r2 == 3
        assert call_count == 1

    @pytest.mark.anyio
    async def test_cached_sync_func(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60)
        def sync_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # cached decorator wraps sync functions in async wrapper
        r1 = await sync_func(5)
        r2 = await sync_func(5)
        assert r1 == 10
        assert r2 == 10
        assert call_count == 1

    @pytest.mark.anyio
    async def test_invalidate_decorator(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60, key_prefix="inv")
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x

        await func(1)
        assert call_count == 1
        await cache.backend.delete("inv:1")
        await func(1)
        assert call_count == 2

    @pytest.mark.anyio
    async def test_clear_decorator(self):
        cache = Cache(MemoryCache())
        call_count = 0

        @cache.cached(ttl=60, key_prefix="clr")
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x

        await func(1)
        await func(2)
        assert call_count == 2
        await cache.clear()
        await func(1)
        assert call_count == 3
