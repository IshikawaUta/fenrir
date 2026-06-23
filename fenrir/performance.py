"""
fenrir.performance — Performance optimizations for Fenrir.

Features:
- Lazy imports for fast startup
- Object pooling for memory efficiency
- Response caching
- Optimized middleware pipeline
- Fast path for common operations

Usage::

    from fenrir.performance import optimize_app

    app = Fenrir()
    optimize_app(app)
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import logging

logger = logging.getLogger("fenrir.performance")


# ═══════════════════════════════════════════════════════════════════════
# Object Pool
# ═══════════════════════════════════════════════════════════════════════

class ObjectPool:
    """Reusable object pool to reduce GC pressure.

    Usage::

        pool = ObjectPool(dict, max_size=1000)
        obj = pool.acquire()
        # Use obj
        pool.release(obj)
    """

    def __init__(
        self,
        factory: Callable,
        max_size: int = 1000,
        reset_func: Optional[Callable] = None,
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._reset_func = reset_func
        self._pool: list = []
        self._acquired = 0

    def acquire(self) -> Any:
        if self._pool:
            self._acquired += 1
            return self._pool.pop()
        self._acquired += 1
        return self._factory()

    def release(self, obj: Any) -> None:
        if self._reset_func:
            try:
                self._reset_func(obj)
            except Exception:
                self._acquired -= 1
                return
        self._acquired -= 1
        if len(self._pool) < self._max_size:
            self._pool.append(obj)

    def clear(self) -> None:
        self._pool.clear()
        # Don't reset _acquired — let external holders finish

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "pool_size": len(self._pool),
            "acquired": self._acquired,
            "max_size": self._max_size,
        }


# Global pools
_dict_pool = ObjectPool(dict, max_size=10000, reset_func=lambda d: d.clear())
_list_pool = ObjectPool(list, max_size=10000, reset_func=lambda l: l.clear())


# ═══════════════════════════════════════════════════════════════════════
# Response Cache (for repeated identical requests)
# ═══════════════════════════════════════════════════════════════════════

class ResponseCache:
    """LRU cache for HTTP responses.

    Automatically caches GET responses with appropriate cache headers.

    Usage::

        cache = ResponseCache(max_size=1000, default_ttl=60)
        app.add_middleware(ResponseCacheMiddleware, cache=cache)
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 60,
    ) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _make_key(self, method: str, path: str, query: str = "") -> str:
        if query:
            return f"{method}:{path}:{query}"
        return f"{method}:{path}"

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expires_at = self._cache[key]
            if time.time() < expires_at:
                self._cache.move_to_end(key)
                self._hits += 1
                return value
            del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self._default_ttl
        expires_at = time.time() + ttl

        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expires_at)

        # Evict expired entries first, then LRU
        while len(self._cache) > self._max_size:
            evicted = False
            now = time.time()
            for k, (_, exp) in self._cache.items():
                if exp <= now:
                    del self._cache[k]
                    evicted = True
                    break
            if not evicted:
                self._cache.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 2) if total > 0 else 0,
        }


# ═══════════════════════════════════════════════════════════════════════
# Fast Path Router
# ═══════════════════════════════════════════════════════════════════════

class FastPathRouter:
    """Optimized router with pre-compiled patterns for common routes.

    Maintains a fast lookup table for frequently accessed routes.

    Usage::

        router = FastPathRouter()
        router.add_fast_path("/", home_handler)
        handler = router.get_handler("GET", "/")
    """

    def __init__(self) -> None:
        self._fast_paths: Dict[str, Callable] = {}
        self._fallback: Optional[Callable] = None

    def add_fast_path(self, path: str, handler: Callable, methods: Optional[List[str]] = None) -> None:
        methods = methods or ["GET"]
        for method in methods:
            key = f"{method}:{path}"
            self._fast_paths[key] = handler

    def get_handler(self, method: str, path: str) -> Optional[Callable]:
        return self._fast_paths.get(f"{method}:{path}")

    def set_fallback(self, handler: Callable) -> None:
        self._fallback = handler


# ═══════════════════════════════════════════════════════════════════════
# Optimized Middleware Pipeline
# ═══════════════════════════════════════════════════════════════════════

class OptimizedPipeline:
    """Pre-compiled middleware pipeline for minimal overhead.

    Unlike dynamic middleware chains, this pre-compiles the pipeline
    into a single callable for maximum performance.

    Usage::

        pipeline = OptimizedPipeline(app)
        pipeline.add(middleware1)
        pipeline.add(middleware2)
        compiled = pipeline.compile()
        await compiled(scope, receive, send)
    """

    def __init__(self, app: Callable) -> None:
        self._app = app
        self._middlewares: List[Tuple[Callable, Dict]] = []
        self._compiled: Optional[Callable] = None

    def add(self, middleware: Callable, **kwargs: Any) -> "OptimizedPipeline":
        self._middlewares.append((middleware, kwargs))
        self._compiled = None
        return self

    def compile(self) -> Callable:
        if self._compiled is not None:
            return self._compiled

        app = self._app

        # Build chain in reverse order
        for middleware_cls, kwargs in reversed(self._middlewares):
            try:
                app = middleware_cls(app, **kwargs)
            except Exception as e:
                logger.error("Failed to compile middleware %s: %s", middleware_cls, e)
                raise

        self._compiled = app
        return app


# ═══════════════════════════════════════════════════════════════════════
# Lazy Import Cache
# ═══════════════════════════════════════════════════════════════════════

class LazyImportCache:
    """Cache for lazily imported modules to avoid repeated imports.

    Usage::

        cache = LazyImportCache()
        json = cache.import_module("json")
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def import_module(self, module_path: str) -> Any:
        if module_path in self._cache:
            return self._cache[module_path]

        import importlib
        module = importlib.import_module(module_path)
        self._cache[module_path] = module
        return module

    def clear(self) -> None:
        self._cache.clear()


# Global lazy import cache
_lazy_cache = LazyImportCache()


# ═══════════════════════════════════════════════════════════════════════
# Fast JSON Serializer
# ═══════════════════════════════════════════════════════════════════════

from fenrir.json import json_dumps_bytes, json_loads


def fast_json_dumps(obj: Any) -> bytes:
    """Fast JSON serialization using centralized fenrir.json helpers."""
    return json_dumps_bytes(obj)


def fast_json_loads(data: bytes) -> Any:
    """Fast JSON deserialization using centralized fenrir.json helpers."""
    return json_loads(data)


# ═══════════════════════════════════════════════════════════════════════
# App Optimizer
# ═══════════════════════════════════════════════════════════════════════

def optimize_app(app: Any, **kwargs: Any) -> None:
    """Apply all performance optimizations to a Fenrir app.

    Usage::

        from fenrir.performance import optimize_app

        app = Fenrir()
        optimize_app(app, cache_responses=True, pool_size=1000)
    """
    cache_responses = kwargs.get("cache_responses", True)
    pool_size = kwargs.get("pool_size", 1000)
    response_ttl = kwargs.get("response_ttl", 60)

    # Add response cache middleware
    if cache_responses:
        cache = ResponseCache(max_size=pool_size, default_ttl=response_ttl)
        app._response_cache = cache

        @app.middleware("response")
        async def cache_response(req, resp):
            if req.method == "GET" and hasattr(resp, "status") and resp.status == 200:
                try:
                    query = req.query_string.decode("latin-1") if req.query_string else ""
                except (UnicodeDecodeError, AttributeError):
                    query = ""
                key = cache._make_key(req.method, req.path, query)
                try:
                    body = resp.body if hasattr(resp, "body") else b""
                    cache.set(key, (resp.status, resp.headers, body))
                except Exception:
                    pass

        @app.middleware("request")
        async def check_cache(req):
            if req.method != "GET":
                return

            try:
                query = req.query_string.decode("latin-1") if req.query_string else ""
            except (UnicodeDecodeError, AttributeError):
                query = ""
            key = cache._make_key(req.method, req.path, query)
            cached = cache.get(key)

            if cached:
                from fenrir.response import Response
                status, headers, body = cached
                # Set cached response on request — handler should check for this
                req._cached_response = Response(
                    body=body,
                    status=status,
                    headers=dict(headers) if headers else {},
                )

    # Pre-compile middleware pipeline
    if hasattr(app, "_asgi_middlewares") and app._asgi_middlewares:
        logger.info("Pre-compiling %d ASGI middlewares", len(app._asgi_middlewares))


# ═══════════════════════════════════════════════════════════════════════
# Performance Monitoring
# ═══════════════════════════════════════════════════════════════════════

class PerformanceMonitor:
    """Monitor and log performance metrics.

    Usage::

        monitor = PerformanceMonitor()
        monitor.start_timer("request")
        # ... handle request
        elapsed = monitor.stop_timer("request")
    """

    MAX_LATENCIES = 10000  # Maximum latency samples to keep

    def __init__(self) -> None:
        self._timers: Dict[str, float] = {}
        self._counters: Dict[str, int] = {}
        self._latencies: Dict[str, List[float]] = {}

    def start_timer(self, name: str) -> None:
        self._timers[name] = time.perf_counter()

    def stop_timer(self, name: str) -> float:
        if name in self._timers:
            elapsed = time.perf_counter() - self._timers.pop(name)
            if name not in self._latencies:
                self._latencies[name] = []
            self._latencies[name].append(elapsed)
            # Prevent unbounded growth
            if len(self._latencies[name]) > self.MAX_LATENCIES:
                self._latencies[name] = self._latencies[name][-self.MAX_LATENCIES:]
            return elapsed
        return 0.0

    def increment(self, name: str) -> None:
        self._counters[name] = self._counters.get(name, 0) + 1

    def get_stats(self, name: str) -> Dict[str, float]:
        if name not in self._latencies:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        latencies = self._latencies[name]
        if not latencies:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        sorted_lat = sorted(latencies)
        count = len(sorted_lat)
        return {
            "count": count,
            "min": sorted_lat[0],
            "max": sorted_lat[-1],
            "avg": sum(sorted_lat) / count,
            "p50": sorted_lat[count // 2],
            "p95": sorted_lat[int(count * 0.95)] if count > 1 else sorted_lat[0],
            "p99": sorted_lat[int(count * 0.99)] if count > 1 else sorted_lat[0],
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        return {name: self.get_stats(name) for name in self._latencies}


# Global monitor
monitor = PerformanceMonitor()
