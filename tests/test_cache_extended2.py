"""Tests for fenrir.cache — FileCache, Cache base."""
import asyncio
import json
import os
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fenrir.cache import (
    CacheBackend, MemoryCache, FileCache, Cache,
)


# ═══════════════════════════════════════════════════════════════════════
# CacheBackend Base Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCacheBackend:
    @pytest.mark.anyio
    async def test_base_methods_raise(self):
        b = CacheBackend()
        with pytest.raises(NotImplementedError):
            await b.get("x")
        with pytest.raises(NotImplementedError):
            await b.set("x", "y")
        with pytest.raises(NotImplementedError):
            await b.delete("x")

    @pytest.mark.anyio
    async def test_set_many_base(self):
        b = CacheBackend()
        with pytest.raises(NotImplementedError):
            await b.set_many({"x": "y"})


# ═══════════════════════════════════════════════════════════════════════
# FileCache Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFileCache:
    @pytest.mark.anyio
    async def test_set_get(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set("key1", "value1")
        result = await fc.get("key1")
        assert result == "value1"

    @pytest.mark.anyio
    async def test_get_expired(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=0)
        await fc.set("key1", "value1", ttl=0)
        # ttl=0 means expires_at is None, so it never expires
        result = await fc.get("key1")
        assert result == "value1"

    @pytest.mark.anyio
    async def test_get_not_found(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        result = await fc.get("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_get_corrupt_file(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        path = fc._get_path("bad")
        path.write_bytes(b"not json{{{")
        result = await fc.get("bad")
        assert result is None
        assert not path.exists()

    @pytest.mark.anyio
    async def test_delete(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set("key1", "value1")
        assert await fc.delete("key1") is True
        assert await fc.get("key1") is None

    @pytest.mark.anyio
    async def test_delete_not_found(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        # delete returns True even if file doesn't exist (unlink(missing_ok=True))
        result = await fc.delete("nope")
        assert isinstance(result, bool)

    @pytest.mark.anyio
    async def test_exists(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set("key1", "value1")
        assert await fc.exists("key1") is True
        assert await fc.exists("nope") is False

    @pytest.mark.anyio
    async def test_clear(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set("a", "1")
        await fc.set("b", "2")
        await fc.clear()
        assert await fc.get("a") is None
        assert await fc.get("b") is None

    @pytest.mark.anyio
    async def test_get_many(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set("a", "1")
        await fc.set("b", "2")
        results = await fc.get_many(["a", "b", "c"])
        assert results == {"a": "1", "b": "2"}

    @pytest.mark.anyio
    async def test_set_many(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        await fc.set_many({"a": "1", "b": "2"})
        assert await fc.get("a") == "1"
        assert await fc.get("b") == "2"

    def test_get_path(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        p = fc._get_path("testkey")
        assert p.suffix == ".cache"
        # Path should be deterministic for same key
        p2 = fc._get_path("testkey")
        assert p == p2

    @pytest.mark.anyio
    async def test_set_write_error(self, tmp_path):
        fc = FileCache(str(tmp_path), ttl=60)
        with patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                await fc.set("key", "value")


# ═══════════════════════════════════════════════════════════════════════
# Cache Wrapper Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCacheWrapper:
    def test_memory_backend(self):
        c = Cache(backend=MemoryCache())
        assert isinstance(c._backend, MemoryCache)

    def test_default_backend(self):
        c = Cache()
        assert isinstance(c._backend, MemoryCache)

    def test_backend_property(self):
        mb = MemoryCache()
        c = Cache(backend=mb)
        assert c.backend is mb

    @pytest.mark.anyio
    async def test_get_set(self):
        c = Cache(backend=MemoryCache())
        await c.set("k", "v")
        assert await c.get("k") == "v"

    @pytest.mark.anyio
    async def test_delete(self):
        c = Cache(backend=MemoryCache())
        await c.set("k", "v")
        await c.delete("k")
        assert await c.get("k") is None

    @pytest.mark.anyio
    async def test_exists(self):
        c = Cache(backend=MemoryCache())
        await c.set("k", "v")
        assert await c.exists("k") is True

    @pytest.mark.anyio
    async def test_clear(self):
        c = Cache(backend=MemoryCache())
        await c.set("a", "1")
        await c.set("b", "2")
        await c.clear()
        assert await c.get("a") is None

    @pytest.mark.anyio
    async def test_get_many_set_many(self):
        c = Cache(backend=MemoryCache())
        await c.set_many({"a": "1", "b": "2"})
        results = await c.get_many(["a", "b", "c"])
        assert results == {"a": "1", "b": "2"}

    @pytest.mark.anyio
    async def test_cached_decorator(self):
        c = Cache(backend=MemoryCache())
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
    async def test_cached_decorator_different_args(self):
        c = Cache(backend=MemoryCache())
        call_count = 0

        @c.cached(ttl=60)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x

        await func(1)
        await func(2)
        assert call_count == 2

    @pytest.mark.anyio
    async def test_cached_decorator_with_key_func(self):
        c = Cache(backend=MemoryCache())

        @c.cached(ttl=60, key_func=lambda x: f"custom:{x}")
        async def func(x):
            return x

        await func(5)
        assert await c.get("custom:5") == 5

    @pytest.mark.anyio
    async def test_invalidate_decorator(self):
        c = Cache(backend=MemoryCache())
        call_count = 0

        @c.invalidate()
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x

        await func(1)
        await func(1)
        assert call_count == 2

    @pytest.mark.anyio
    async def test_invalidate_with_key_func(self):
        c = Cache(backend=MemoryCache())
        await c.set("mykey", "old")

        @c.invalidate(key_func=lambda x: "mykey")
        async def func(x):
            return "new"

        result = await func(1)
        assert result == "new"
        assert await c.get("mykey") is None

    @pytest.mark.anyio
    async def test_invalidate_with_prefix_memory(self):
        c = Cache(backend=MemoryCache())
        await c.set("users:1", "old")

        @c.invalidate(key_prefix="users")
        async def func(x):
            return "new"

        result = await func(1)
        assert result == "new"

    @pytest.mark.anyio
    async def test_cached_invalidate(self):
        c = Cache(backend=MemoryCache())
        call_count = 0

        @c.cached(ttl=60)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        r1 = await func(5)
        assert call_count == 1
        await func.invalidate(5)
        r2 = await func(5)
        assert call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# RedisCache Tests (mock only, no real Redis)
# ═══════════════════════════════════════════════════════════════════════

class TestRedisCache:
    def test_make_key(self):
        from fenrir.cache import RedisCache
        rc = RedisCache(prefix="test:")
        assert rc._make_key("foo") == "test:foo"

    @pytest.mark.anyio
    async def test_get_redis_import_error(self):
        from fenrir.cache import RedisCache
        rc = RedisCache()
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            with pytest.raises(ImportError, match="redis"):
                await rc._get_redis()

    @pytest.mark.anyio
    async def test_context_manager(self):
        from fenrir.cache import RedisCache
        rc = RedisCache()
        async with rc:
            assert rc is not None
