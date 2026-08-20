"""Unit tests for fenrir.cache edge paths."""

import pytest

from fenrir.cache import Cache, FileCache, MemoryCache, RedisCache


class StubRedis:
    def __init__(self, scan_results=None):
        self.scan_results = list(scan_results or [])
        self.deleted = []
        self.exists_answers = {}

    async def scan(self, cursor, match=None, count=100):
        if self.scan_results:
            return self.scan_results.pop(0)
        return (0, [])

    async def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)

    async def exists(self, key):
        return self.exists_answers.get(key, 0)

    async def mget(self, keys):
        return [None for _ in keys]

    async def get(self, key):
        return None

    async def set(self, *a, **k):
        return True

    async def aclose(self):
        pass


class StubRedisRaise:
    async def scan(self, *a, **k):
        raise RuntimeError("scan failed")

    async def delete(self, *keys):
        return 0

    async def get(self, key):
        return None

    async def set(self, *a, **k):
        return True

    async def aclose(self):
        pass


class TestSerializeFallbacks:
    def test_orjson_serialize_unserializable(self, monkeypatch):
        import fenrir.cache as cmod

        class _StubOrjson:
            def dumps(self, value):
                if isinstance(value, set):
                    raise TypeError("cannot serialize set")
                return b'{"_repr": "serialized", "_type": "dict"}'

        monkeypatch.setattr(cmod, "_HAS_ORJSON", True)
        monkeypatch.setattr(cmod, "_orjson", _StubOrjson())
        data = RedisCache._default_serialize({1, 2})
        assert b"_repr" in data

    def test_orjson_deserialize_bad(self):
        assert RedisCache._default_deserialize(b"not-json") is None

    def test_json_serialize(self, monkeypatch):
        import fenrir.cache as cmod
        monkeypatch.setattr(cmod, "_HAS_ORJSON", False)
        data = RedisCache._default_serialize({"a": 1})
        assert b'"a"' in data

    def test_json_serialize_fallback(self, monkeypatch):
        import json as json_mod

        import fenrir.cache as cmod

        real_dumps = json_mod.dumps
        state = {"n": 0}

        def _fail_once(*a, **k):
            state["n"] += 1
            if state["n"] == 1:
                raise TypeError("cannot serialize")
            return real_dumps(*a, **k)

        monkeypatch.setattr(cmod, "_HAS_ORJSON", False)
        monkeypatch.setattr(json_mod, "dumps", _fail_once)
        data = RedisCache._default_serialize(object())
        assert b"_repr" in data

    def test_json_deserialize_ok(self, monkeypatch):
        import fenrir.cache as cmod
        monkeypatch.setattr(cmod, "_HAS_ORJSON", False)
        assert RedisCache._default_deserialize(b'{"a": 1}') == {"a": 1}

    def test_json_deserialize_bad(self, monkeypatch):
        import fenrir.cache as cmod
        monkeypatch.setattr(cmod, "_HAS_ORJSON", False)
        assert RedisCache._default_deserialize(b"bad-json") is None


class TestRedisGetConnection:
    @pytest.mark.anyio
    async def test_get_redis_creates(self):
        rc = RedisCache(redis_url="redis://localhost:6379/0")
        redis = await rc._get_redis()
        assert redis is rc._redis
        await rc.close()


class TestRedisClear:
    @pytest.mark.anyio
    async def test_clear_multiple_pages(self):
        rc = RedisCache(prefix="test:")
        rc._redis = StubRedis(scan_results=[(5, ["test:k1", "test:k2"]), (0, [])])
        await rc.clear()
        assert rc._redis.deleted == ["test:k1", "test:k2"]

    @pytest.mark.anyio
    async def test_get_many_empty(self):
        rc = RedisCache(prefix="test:")
        rc._redis = StubRedis()
        assert await rc.get_many([]) == {}

    @pytest.mark.anyio
    async def test_get_many_none_but_exists(self):
        rc = RedisCache(prefix="test:")
        stub = StubRedis()
        stub.exists_answers["test:k"] = 1
        rc._redis = stub
        assert await rc.get_many(["k"]) == {"k": None}

    @pytest.mark.anyio
    async def test_set_many_empty(self):
        rc = RedisCache(prefix="test:")
        rc._redis = StubRedis()
        await rc.set_many({})


class TestInvalidate:
    @pytest.mark.anyio
    async def test_cached_invalidate_with_key_func(self):
        cache = Cache(MemoryCache())
        calls = []

        @cache.cached(key_func=lambda *a, **k: f"custom:{a[0]}")
        async def work(x):
            calls.append(x)
            return x * 2

        assert await work(5) == 10
        assert await work(5) == 10
        assert len(calls) == 1
        await work.invalidate(5)
        assert await work(5) == 10
        assert len(calls) == 2

    @pytest.mark.anyio
    async def test_invalidate_memory_prefix(self):
        cache = Cache(MemoryCache())
        await cache.set("users:1", "alice")
        await cache.set("other:1", "bob")

        @cache.invalidate(key_prefix="users")
        async def update():
            return "done"

        await update()
        assert await cache.get("users:1") is None
        assert await cache.get("other:1") == "bob"

    @pytest.mark.anyio
    async def test_invalidate_redis_prefix(self):
        rc = RedisCache(prefix="test:")
        rc._redis = StubRedis(scan_results=[(3, ["test:users:1", "test:users:2"]), (0, [])])
        cache = Cache(backend=rc)

        @cache.invalidate(key_prefix="users")
        async def update():
            return "done"

        await update()
        assert rc._redis.deleted == ["test:users:1", "test:users:2"]

    @pytest.mark.anyio
    async def test_invalidate_redis_scan_error(self, caplog):
        rc = RedisCache(prefix="test:")
        rc._redis = StubRedisRaise()
        cache = Cache(backend=rc)

        @cache.invalidate(key_prefix="users")
        async def update():
            return "done"

        await update()
        assert "Failed to invalidate cache prefix" in caplog.text


class TestCacheContext:
    @pytest.mark.anyio
    async def test_context_manager(self):
        async with Cache() as cache:
            assert isinstance(cache.backend, MemoryCache)

    @pytest.mark.anyio
    async def test_aexit_calls_close(self):
        rc = RedisCache(prefix="test:")
        async with Cache(backend=rc) as cache:
            assert cache.backend is rc

    @pytest.mark.anyio
    async def test_invalidate_bare_backend(self):
        from fenrir.cache import CacheBackend

        class BareBackend(CacheBackend):
            async def get(self, key):
                return None

            async def set(self, key, value, ttl=None):
                pass

            async def delete(self, key):
                return True

            async def exists(self, key):
                return False

            async def clear(self):
                pass

        cache = Cache(backend=BareBackend())

        @cache.invalidate(key_prefix="x")
        async def update():
            return "done"

        assert await update() == "done"


class TestFileCacheFallbacks:
    @pytest.mark.anyio
    async def test_roundtrip_json_fallback(self, monkeypatch, tmp_path):
        import fenrir.cache as cmod
        monkeypatch.setattr(cmod, "_HAS_ORJSON", False)
        fc = FileCache(cache_dir=str(tmp_path))
        await fc.set("k", {"v": 1})
        assert await fc.get("k") == {"v": 1}
        assert await fc.exists("k") is True

    @pytest.mark.anyio
    async def test_exists_corrupt(self, tmp_path):
        fc = FileCache(cache_dir=str(tmp_path))
        path = fc._get_path("broken")
        path.write_bytes(b"corrupt-data")
        assert await fc.exists("broken") is False

    @pytest.mark.anyio
    async def test_exists_expired(self, tmp_path):
        import json

        fc = FileCache(cache_dir=str(tmp_path))
        path = fc._get_path("exp")
        path.write_bytes(json.dumps({"value": 1, "expires_at": -999, "created_at": 0}).encode())
        assert await fc.exists("exp") is False
        assert path.exists() is False
