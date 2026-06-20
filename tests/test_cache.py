"""Tests for fenrir.cache — Multi-backend caching system."""
import pytest
import time
from fenrir.cache import Cache, MemoryCache, FileCache


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
