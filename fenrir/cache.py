"""
fenrir.cache — Multi-backend caching system for Fenrir.

Provides a unified caching API with pluggable backends:
- MemoryCache: In-process LRU cache (fastest, no external deps)
- RedisCache: Redis-backed distributed cache
- FileCache: Disk-based cache for persistence

Usage::

    from fenrir.cache import Cache, MemoryCache, RedisCache

    # Simple in-memory cache
    cache = Cache(MemoryCache(max_size=1000, ttl=300))
    await cache.set("key", "value", ttl=60)
    value = await cache.get("key")

    # Redis cache
    cache = Cache(RedisCache(redis_url="redis://localhost"))

    # Decorator
    @cache.cached(ttl=300)
    async def expensive_query(user_id):
        return await db.fetch_user(user_id)

    # Cache invalidation
    await cache.delete("key")
    await cache.clear()
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

from fenrir.compat import to_thread
from fenrir.json import _HAS_ORJSON, _orjson

logger = logging.getLogger("fenrir.cache")


# Sentinel for cache miss
class _CacheMiss:
    """Sentinel class for cache miss — distinct from None."""
    pass


CACHE_MISS = _CacheMiss()


class CacheBackend:
    """Base cache backend interface."""

    async def get(self, key: str) -> Any:
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> bool:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError

    async def get_many(self, keys: list) -> dict:
        result = {}
        for key in keys:
            if await self.exists(key):
                result[key] = await self.get(key)
        return result

    async def set_many(self, mapping: dict, ttl: Optional[int] = None) -> None:
        for key, value in mapping.items():
            await self.set(key, value, ttl=ttl)


class MemoryCache(CacheBackend):
    """In-process LRU cache with TTL support.

    Fastest option for single-process applications.

    Usage::

        cache = MemoryCache(max_size=1000, ttl=300)
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300) -> None:
        self._max_size = max_size
        self._default_ttl = ttl
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any:
        if key in self._cache:
            value, expires_at = self._cache[key]
            if expires_at is None or time.time() < expires_at:
                self._cache.move_to_end(key)
                self._hits += 1
                return value
            else:
                del self._cache[key]
        self._misses += 1
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl if ttl > 0 else None

        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expires_at)

        # Evict LRU when over capacity — O(1) instead of O(n) expired scan
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        if key in self._cache:
            _, expires_at = self._cache[key]
            if expires_at is None or time.time() < expires_at:
                return True
            del self._cache[key]
        return False

    async def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 2) if total > 0 else 0,
        }


class RedisCache(CacheBackend):
    """Redis-backed distributed cache.

    Requires the ``redis`` package (``pip install redis``).

    Usage::

        cache = RedisCache(redis_url="redis://localhost:6379/0")
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "fenrir:",
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
    ) -> None:
        self._redis_url = redis_url
        self._prefix = prefix
        self._serializer = serializer or self._default_serialize
        self._deserializer = deserializer or self._default_deserialize
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
            except ImportError:
                raise ImportError(
                    "redis is required for RedisCache. "
                    "Install with: pip install fenrir-framework[redis]"
                ) from None
        return self._redis

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    @staticmethod
    def _default_serialize(value: Any) -> bytes:
        """Safe serialization using orjson (or json fallback)."""
        if _HAS_ORJSON:
            try:
                return _orjson.dumps(value)
            except Exception:
                return _orjson.dumps({"_repr": repr(value), "_type": type(value).__name__})
        try:
            return json.dumps(value, default=str).encode("utf-8")
        except (TypeError, ValueError):
            return json.dumps({"_repr": repr(value), "_type": type(value).__name__}).encode("utf-8")

    @staticmethod
    def _default_deserialize(data: bytes) -> Any:
        """Safe deserialization using orjson (or json fallback)."""
        if _HAS_ORJSON:
            try:
                return _orjson.loads(data)
            except Exception:
                return None
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    async def get(self, key: str) -> Any:
        redis = await self._get_redis()
        data = await redis.get(self._make_key(key))
        if data is not None:
            return self._deserializer(data)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        redis = await self._get_redis()
        data = self._serializer(value)
        if ttl is not None and ttl > 0:
            await redis.set(self._make_key(key), data, ex=ttl)
        else:
            await redis.set(self._make_key(key), data)

    async def delete(self, key: str) -> bool:
        redis = await self._get_redis()
        result = await redis.delete(self._make_key(key))
        return result > 0

    async def exists(self, key: str) -> bool:
        redis = await self._get_redis()
        return await redis.exists(self._make_key(key)) > 0

    async def clear(self) -> None:
        redis = await self._get_redis()
        # Use SCAN instead of KEYS to avoid blocking Redis
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"{self._prefix}*", count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break

    async def get_many(self, keys: list) -> dict:
        if not keys:
            return {}
        redis = await self._get_redis()
        prefixed_keys = [self._make_key(k) for k in keys]
        values = await redis.mget(prefixed_keys)
        result = {}
        # Collect keys that returned None to check existence
        none_keys = []
        none_indices = []
        for i, (key, value) in enumerate(zip(keys, values)):
            if value is not None:
                result[key] = self._deserializer(value)
            else:
                none_keys.append(prefixed_keys[i])
                none_indices.append(i)
        # Batch-check existence for None values
        if none_keys:
            try:
                pipe = redis.pipeline()
                for pk in none_keys:
                    pipe.exists(pk)
                exists_results = await pipe.execute()
            except AttributeError:
                # Fallback for test stubs without pipeline support
                exists_results = [await redis.exists(pk) for pk in none_keys]
            for idx, exists_val in zip(none_indices, exists_results):
                if exists_val:
                    result[keys[idx]] = None
        return result

    async def set_many(self, mapping: dict, ttl: Optional[int] = None) -> None:
        if not mapping:
            return
        redis = await self._get_redis()
        pipe = redis.pipeline()
        for key, value in mapping.items():
            data = self._serializer(value)
            if ttl is not None and ttl > 0:
                pipe.set(self._make_key(key), data, ex=ttl)
            else:
                pipe.set(self._make_key(key), data)
        await pipe.execute()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def __aenter__(self) -> RedisCache:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


class FileCache(CacheBackend):
    """Disk-based cache for persistence across restarts.

    Usage::

        cache = FileCache(cache_dir="/tmp/fenrir_cache", ttl=3600)
    """

    def __init__(self, cache_dir: str = ".fenrir_cache", ttl: int = 3600) -> None:
        self._cache_dir = Path(cache_dir)
        self._ttl = ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        safe_key = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self._cache_dir / f"{safe_key}.cache"

    async def get(self, key: str) -> Any:
        path = self._get_path(key)
        if not await to_thread(path.exists):
            return None
        try:
            data = await to_thread(path.read_bytes)
            if _HAS_ORJSON:
                entry = _orjson.loads(data)
            else:
                entry = json.loads(data.decode("utf-8"))
            if entry["expires_at"] is None or time.time() < entry["expires_at"]:
                return entry["value"]
            else:
                await to_thread(path.unlink, True)
        except Exception:
            await to_thread(path.unlink, True)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._ttl
        expires_at = time.time() + ttl if ttl > 0 else None
        entry = {"value": value, "expires_at": expires_at, "created_at": time.time()}
        path = self._get_path(key)
        if _HAS_ORJSON:
            data = _orjson.dumps(entry)
        else:
            data = json.dumps(entry, default=str).encode("utf-8")
        # Atomic write: write to temp file, then rename
        temp_path = path.with_suffix(".tmp")
        try:
            await to_thread(temp_path.write_bytes, data)
            await to_thread(temp_path.rename, path)
        except Exception:
            await to_thread(temp_path.unlink, True)
            raise

    async def delete(self, key: str) -> bool:
        path = self._get_path(key)
        if await to_thread(path.exists):
            await to_thread(path.unlink)
            return True
        return False

    async def exists(self, key: str) -> bool:
        path = self._get_path(key)
        if not await to_thread(path.exists):
            return False
        try:
            data = await to_thread(path.read_bytes)
            if _HAS_ORJSON:
                entry = _orjson.loads(data)
            else:
                entry = json.loads(data.decode("utf-8"))
            if entry["expires_at"] is None or time.time() < entry["expires_at"]:
                return True
            await to_thread(path.unlink, True)
        except Exception:
            pass
        return False

    async def clear(self) -> None:
        def _clear():
            for path in self._cache_dir.glob("*.cache"):
                path.unlink(missing_ok=True)
        await to_thread(_clear)


_UNSET = object()  # Sentinel for cache miss


class Cache:
    """Unified cache interface with decorator support.

    Usage::

        cache = Cache(MemoryCache())

        # Direct operations
        await cache.set("key", "value", ttl=60)
        value = await cache.get("key")

        # Decorator
        @cache.cached(ttl=300, key_prefix="user")
        async def get_user(user_id: int):
            return await db.get_user(user_id)

        # Cache invalidation
        @cache.invalidate(key_prefix="user")
        async def update_user(user_id: int, data: dict):
            ...
    """

    def __init__(self, backend: Optional[CacheBackend] = None) -> None:
        self._backend = backend or MemoryCache()

    @property
    def backend(self) -> CacheBackend:
        return self._backend

    async def get(self, key: str) -> Any:
        result = await self._backend.get(key)
        return result

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        await self._backend.set(key, value, ttl=ttl)

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(key)

    async def clear(self) -> None:
        await self._backend.clear()

    async def get_many(self, keys: list) -> dict:
        return await self._backend.get_many(keys)

    async def set_many(self, mapping: dict, ttl: Optional[int] = None) -> None:
        await self._backend.set_many(mapping, ttl=ttl)

    def cached(
        self,
        ttl: int = 300,
        key_prefix: str = "",
        key_func: Optional[Callable] = None,
    ) -> Callable:
        """Decorator to cache function results.

        Usage::

            @cache.cached(ttl=60, key_prefix="users")
            async def get_user(user_id: int):
                return await db.get_user(user_id)
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    func_name = f"{func.__module__}.{func.__qualname__}"
                    key_parts = [key_prefix or func_name] + [repr(a) for a in args]
                    key_parts += [f"{k}={repr(v)}" for k, v in sorted(kwargs.items())]
                    cache_key = ":".join(key_parts)

                # Try get first; if backend returns a distinct miss sentinel, compute.
                # MemoryCache.get returns None for miss, so we use exists+get
                # as a practical approach (small TOCTOU window is acceptable).
                if await self.exists(cache_key):
                    return await self.get(cache_key)

                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                await self.set(cache_key, result, ttl=ttl)
                return result

            async def invalidate(*args: Any, **kwargs: Any) -> None:
                """Invalidate cache for this function."""
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    func_name = f"{func.__module__}.{func.__qualname__}"
                    key_parts = [key_prefix or func_name] + [repr(a) for a in args]
                    key_parts += [f"{k}={repr(v)}" for k, v in sorted(kwargs.items())]
                    cache_key = ":".join(key_parts)
                await self.delete(cache_key)

            wrapper.invalidate = invalidate  # type: ignore[attr-defined]
            return wrapper
        return decorator

    def invalidate(self, key_prefix: str = "", key_func: Optional[Callable] = None) -> Callable:
        """Decorator to invalidate cache entries after function execution."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

                if key_func:
                    cache_key = key_func(*args, **kwargs)
                    await self.delete(cache_key)
                elif key_prefix:
                    # Invalidate all keys with prefix using SCAN
                    backend: Any = self._backend
                    if hasattr(backend, '_redis'):
                        # Redis: scan for keys with prefix
                        try:
                            redis = await backend._get_redis()
                            cursor = 0
                            while True:
                                cursor, keys = await redis.scan(
                                    cursor, match=f"{backend._prefix}{key_prefix}*", count=100
                                )
                                if keys:
                                    await redis.delete(*keys)
                                if cursor == 0:
                                    break
                        except Exception as e:
                            logger.warning("Failed to invalidate cache prefix '%s': %s", key_prefix, e)
                    elif hasattr(backend, '_cache'):
                        # MemoryCache: iterate and delete matching keys
                        keys_to_delete = [
                            k for k in backend._cache.keys()
                            if k.startswith(key_prefix)
                        ]
                        for k in keys_to_delete:
                            await self.delete(k)

                return result
            return wrapper
        return decorator

    async def __aenter__(self) -> Cache:
        return self

    async def __aexit__(self, *args: Any) -> None:
        if hasattr(self._backend, 'close'):
            await self._backend.close()
