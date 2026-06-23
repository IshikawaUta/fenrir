"""Tests for fenrir.performance module."""
import asyncio
import time
import pytest
from fenrir.performance import (
    ObjectPool,
    ResponseCache,
    FastPathRouter,
    OptimizedPipeline,
    LazyImportCache,
    PerformanceMonitor,
    fast_json_dumps,
    fast_json_loads,
    optimize_app,
    _dict_pool,
    _list_pool,
    _lazy_cache,
    monitor,
)


# ═══════════════════════════════════════════════════════════════════════
# ObjectPool
# ═══════════════════════════════════════════════════════════════════════

class TestObjectPool:
    def test_acquire_creates_new(self):
        pool = ObjectPool(dict)
        obj = pool.acquire()
        assert isinstance(obj, dict)
        assert pool.stats["acquired"] == 1

    def test_release_and_reacquire(self):
        pool = ObjectPool(dict)
        obj = pool.acquire()
        pool.release(obj)
        assert pool.stats["pool_size"] == 1
        assert pool.stats["acquired"] == 0

        obj2 = pool.acquire()
        assert obj2 is obj  # Same object reused
        assert pool.stats["pool_size"] == 0

    def test_max_size_limit(self):
        pool = ObjectPool(dict, max_size=2)
        o1 = pool.acquire()
        o2 = pool.acquire()
        o3 = pool.acquire()
        pool.release(o1)
        pool.release(o2)
        pool.release(o3)  # Should be discarded (pool full)
        assert pool.stats["pool_size"] == 2

    def test_reset_func(self):
        pool = ObjectPool(dict, reset_func=lambda d: d.clear())
        obj = pool.acquire()
        obj["key"] = "value"
        pool.release(obj)
        obj2 = pool.acquire()
        assert "key" not in obj2  # Reset was called

    def test_reset_func_error_handled(self):
        def bad_reset(d):
            raise ValueError("reset failed")

        pool = ObjectPool(dict, reset_func=bad_reset)
        obj = pool.acquire()
        pool.release(obj)  # Should not crash
        assert pool.stats["acquired"] == 0  # Decremented before reset

    def test_clear(self):
        pool = ObjectPool(dict)
        o1 = pool.acquire()
        o2 = pool.acquire()
        pool.release(o1)
        pool.release(o2)
        pool.clear()
        assert pool.stats["pool_size"] == 0
        assert pool.stats["acquired"] == 0

    def test_stats(self):
        pool = ObjectPool(dict, max_size=100)
        obj = pool.acquire()
        stats = pool.stats
        assert stats == {"pool_size": 0, "acquired": 1, "max_size": 100}
        pool.release(obj)

    def test_global_pools(self):
        assert _dict_pool is not None
        assert _list_pool is not None
        obj = _dict_pool.acquire()
        assert isinstance(obj, dict)
        _dict_pool.release(obj)


# ═══════════════════════════════════════════════════════════════════════
# ResponseCache
# ═══════════════════════════════════════════════════════════════════════

class TestResponseCache:
    def test_set_and_get(self):
        cache = ResponseCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_miss(self):
        cache = ResponseCache()
        assert cache.get("nonexistent") is None

    def test_expiration(self):
        cache = ResponseCache()
        cache.set("key1", "value1", ttl=0)
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = ResponseCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_access_refreshes(self):
        cache = ResponseCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # Access "a" to refresh
        cache.set("c", 3)  # Should evict "b" (least recently used)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_invalidate(self):
        cache = ResponseCache()
        cache.set("key1", "value1")
        assert cache.invalidate("key1") is True
        assert cache.get("key1") is None
        assert cache.invalidate("key1") is False

    def test_clear(self):
        cache = ResponseCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # hit
        cache.get("c")  # miss
        # Before clear: hits=1, misses=1
        cache.clear()
        # After clear: hits=0, misses=0
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    def test_make_key(self):
        cache = ResponseCache()
        assert cache._make_key("GET", "/path") == "GET:/path"
        assert cache._make_key("GET", "/path", "q=1") == "GET:/path:q=1"

    def test_stats(self):
        cache = ResponseCache()
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        stats = cache.stats
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0

    def test_stats_empty(self):
        cache = ResponseCache()
        stats = cache.stats
        assert stats["hit_rate"] == 0

    def test_custom_ttl(self):
        cache = ResponseCache(default_ttl=1)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_update_existing_key(self):
        cache = ResponseCache(max_size=2)
        cache.set("a", 1)
        cache.set("a", 2)  # Update
        assert cache.get("a") == 2


# ═══════════════════════════════════════════════════════════════════════
# FastPathRouter
# ═══════════════════════════════════════════════════════════════════════

class TestFastPathRouter:
    def test_add_and_get(self):
        router = FastPathRouter()
        handler = lambda: "ok"
        router.add_fast_path("/", handler)
        assert router.get_handler("GET", "/") is handler

    def test_multiple_methods(self):
        router = FastPathRouter()
        handler = lambda: "ok"
        router.add_fast_path("/", handler, methods=["GET", "POST"])
        assert router.get_handler("GET", "/") is handler
        assert router.get_handler("POST", "/") is handler
        assert router.get_handler("DELETE", "/") is None

    def test_fallback(self):
        router = FastPathRouter()
        fallback = lambda: "fallback"
        router.set_fallback(fallback)
        assert router.get_handler("GET", "/missing") is None  # No fallback in get_handler
        assert router._fallback is fallback

    def test_default_methods(self):
        router = FastPathRouter()
        handler = lambda: "ok"
        router.add_fast_path("/test", handler)
        assert router.get_handler("GET", "/test") is handler


# ═══════════════════════════════════════════════════════════════════════
# OptimizedPipeline
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizedPipeline:
    def test_compile_empty(self):
        async def app(scope, receive, send):
            pass

        pipeline = OptimizedPipeline(app)
        compiled = pipeline.compile()
        assert compiled is app

    def test_compile_with_middleware(self):
        async def app(scope, receive, send):
            pass

        class DummyMiddleware:
            def __init__(self, app, **kwargs):
                self.app = app
                self.kwargs = kwargs

        pipeline = OptimizedPipeline(app)
        pipeline.add(DummyMiddleware, key="value")
        compiled = pipeline.compile()
        assert compiled is not app

    def test_compile_caching(self):
        async def app(scope, receive, send):
            pass

        pipeline = OptimizedPipeline(app)
        c1 = pipeline.compile()
        c2 = pipeline.compile()
        assert c1 is c2

    def test_compile_invalidates_on_add(self):
        async def app(scope, receive, send):
            pass

        class DummyMiddleware:
            def __init__(self, app, **kwargs):
                self.app = app

        pipeline = OptimizedPipeline(app)
        c1 = pipeline.compile()
        pipeline.add(DummyMiddleware)
        c2 = pipeline.compile()
        assert c1 is not c2


# ═══════════════════════════════════════════════════════════════════════
# LazyImportCache
# ═══════════════════════════════════════════════════════════════════════

class TestLazyImportCache:
    def test_import_module(self):
        cache = LazyImportCache()
        import json
        result = cache.import_module("json")
        assert result is json

    def test_import_cached(self):
        cache = LazyImportCache()
        m1 = cache.import_module("os")
        m2 = cache.import_module("os")
        assert m1 is m2

    def test_clear(self):
        cache = LazyImportCache()
        cache.import_module("os")
        cache.clear()
        assert "os" not in cache._cache

    def test_global_cache(self):
        assert _lazy_cache is not None


# ═══════════════════════════════════════════════════════════════════════
# Fast JSON
# ═══════════════════════════════════════════════════════════════════════

class TestFastJSON:
    def test_dumps_loads(self):
        data = {"key": "value", "num": 42}
        encoded = fast_json_dumps(data)
        assert isinstance(encoded, bytes)
        decoded = fast_json_loads(encoded)
        assert decoded == data

    def test_dumps_list(self):
        data = [1, 2, 3]
        encoded = fast_json_dumps(data)
        decoded = fast_json_loads(encoded)
        assert decoded == data


# ═══════════════════════════════════════════════════════════════════════
# PerformanceMonitor
# ═══════════════════════════════════════════════════════════════════════

class TestPerformanceMonitor:
    def test_timer(self):
        mon = PerformanceMonitor()
        mon.start_timer("test")
        time.sleep(0.001)
        elapsed = mon.stop_timer("test")
        assert elapsed > 0

    def test_timer_nonexistent(self):
        mon = PerformanceMonitor()
        assert mon.stop_timer("missing") == 0.0

    def test_increment(self):
        mon = PerformanceMonitor()
        mon.increment("requests")
        mon.increment("requests")
        assert mon._counters["requests"] == 2

    def test_get_stats(self):
        mon = PerformanceMonitor()
        mon.start_timer("test")
        time.sleep(0.001)
        mon.stop_timer("test")
        stats = mon.get_stats("test")
        assert stats["count"] == 1
        assert stats["min"] > 0
        assert stats["max"] > 0
        assert stats["avg"] > 0
        assert stats["p50"] > 0

    def test_get_stats_empty(self):
        mon = PerformanceMonitor()
        stats = mon.get_stats("missing")
        assert stats["count"] == 0

    def test_get_all_stats(self):
        mon = PerformanceMonitor()
        mon.start_timer("a")
        mon.stop_timer("a")
        mon.start_timer("b")
        mon.stop_timer("b")
        all_stats = mon.get_all_stats()
        assert "a" in all_stats
        assert "b" in all_stats

    def test_max_latencies_limit(self):
        mon = PerformanceMonitor()
        for i in range(10005):
            mon.start_timer("test")
            mon.stop_timer("test")
        assert len(mon._latencies["test"]) <= PerformanceMonitor.MAX_LATENCIES

    def test_percentiles_single(self):
        mon = PerformanceMonitor()
        mon.start_timer("test")
        mon.stop_timer("test")
        stats = mon.get_stats("test")
        assert stats["p95"] == stats["p99"] == stats["min"]

    def test_global_monitor(self):
        assert monitor is not None


# ═══════════════════════════════════════════════════════════════════════
# optimize_app
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizeApp:
    def test_optimize_app(self):
        from fenrir import Fenrir
        app = Fenrir()
        optimize_app(app)
        assert hasattr(app, "_response_cache")

    def test_optimize_app_no_cache(self):
        from fenrir import Fenrir
        app = Fenrir()
        optimize_app(app, cache_responses=False)
        assert not hasattr(app, "_response_cache")

    def test_optimize_app_custom_ttl(self):
        from fenrir import Fenrir
        app = Fenrir()
        optimize_app(app, response_ttl=120)
        assert app._response_cache._default_ttl == 120
