"""
fenrir.middleware — Built-in ASGI middleware classes.

Provides CORS, GZip compression, Request ID, and Rate Limiter middleware
that integrate seamlessly with Fenrir's ASGI pipeline.
"""
from __future__ import annotations

import gzip
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from fenrir.json import json_dumps

logger = logging.getLogger("fenrir.middleware")


class CORSMiddleware:
    """ASGI middleware that adds CORS headers to responses.

    Supports both HTTP and WebSocket upgrades (CORS for WebSocket).

    Usage::

        from fenrir import Fenrir
        from fenrir.middleware import CORSMiddleware

        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
    """

    def __init__(
        self,
        app: Callable,
        allow_origins: Union[List[str], str] = "*",
        allow_methods: Union[List[str], str] = "*",
        allow_headers: Union[List[str], str] = "*",
        allow_credentials: bool = False,
        expose_headers: Union[List[str], str] = "",
        max_age: int = 600,
    ) -> None:
        self.app = app
        self.allow_origins = allow_origins if isinstance(allow_origins, list) else [allow_origins]
        self.allow_methods = allow_methods if isinstance(allow_methods, list) else [allow_methods]
        self.allow_headers = allow_headers if isinstance(allow_headers, list) else [allow_headers]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers if isinstance(expose_headers, list) else [expose_headers] if expose_headers else []
        self.max_age = max_age
        self._all_origins = "*" in self.allow_origins

    def _is_origin_allowed(self, origin: str) -> bool:
        if self._all_origins:
            return True
        return origin in self.allow_origins

    def _get_cors_headers(self, origin: Optional[str], is_preflight: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if origin and self._is_origin_allowed(origin):
            # When credentials are allowed with wildcard origins, echo the
            # specific origin per CORS spec (browsers reject "*" with credentialed requests).
            if self._all_origins and self.allow_credentials:
                headers["access-control-allow-origin"] = origin
            else:
                headers["access-control-allow-origin"] = origin
            headers["vary"] = "Origin"
        elif self._all_origins and not self.allow_credentials:
            headers["access-control-allow-origin"] = "*"

        if self.allow_credentials:
            headers["access-control-allow-credentials"] = "true"

        if self.expose_headers:
            headers["access-control-expose-headers"] = ", ".join(self.expose_headers)

        if is_preflight:
            headers["access-control-allow-methods"] = ", ".join(self.allow_methods)
            headers["access-control-allow-headers"] = ", ".join(self.allow_headers)
            headers["access-control-max-age"] = str(self.max_age)

        return headers

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = None
        for k, v in scope.get("headers", []):
            if k == b"origin":
                origin = v.decode("latin-1")
                break

        method = scope.get("method", "").upper()

        if method == "OPTIONS":
            cors_headers = self._get_cors_headers(origin, is_preflight=True)
            if cors_headers:
                await send({
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [
                        (k.encode("latin-1"), v.encode("latin-1"))
                        for k, v in cors_headers.items()
                    ],
                })
                await send({"type": "http.response.body", "body": b""})
                return

        async def send_wrapper(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                cors_headers = self._get_cors_headers(origin)
                existing = dict(message.get("headers", []))
                for k, v in cors_headers.items():
                    existing[k.encode("latin-1")] = v.encode("latin-1")
                message["headers"] = list(existing.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _handle_websocket(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        origin = None
        for k, v in scope.get("headers", []):
            if k == b"origin":
                origin = v.decode("latin-1")
                break

        if origin and self._is_origin_allowed(origin):
            async def send_wrapper(message: Dict[str, Any]) -> None:
                if message["type"] == "websocket.http.response.start":
                    cors_headers = self._get_cors_headers(origin)
                    existing = dict(message.get("headers", []))
                    for hk, hv in cors_headers.items():
                        existing[hk.encode("latin-1")] = hv.encode("latin-1")
                    message["headers"] = list(existing.items())
                await send(message)
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)


class GZipMiddleware:
    """ASGI middleware that compresses response bodies with gzip.

    Only compresses responses with compressible content types and bodies
    exceeding the minimum size threshold.  Uses streaming compression for
    memory efficiency on large responses.

    Usage::

        app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)
    """

    COMPRESSIBLE_TYPES = {
        "text/plain",
        "text/html",
        "text/css",
        "text/xml",
        "text/javascript",
        "application/json",
        "application/javascript",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
        "application/vnd.ms-fontobject",
        "font/opentype",
        "image/svg+xml",
        "application/xhtml+xml",
        "application/wasm",
    }

    def __init__(
        self,
        app: Callable,
        minimum_size: int = 500,
        compresslevel: int = 6,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    def _is_compressible(self, content_type: str) -> bool:
        ct = content_type.split(";")[0].strip().lower()
        if ct in self.COMPRESSIBLE_TYPES:
            return True
        # Allow text/* and application/json-adjacent types
        if ct.startswith("text/"):
            return True
        return False

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        accept_encoding = ""
        for k, v in scope.get("headers", []):
            if k == b"accept-encoding":
                accept_encoding = v.decode("latin-1")
                break

        if "gzip" not in accept_encoding.lower():
            await self.app(scope, receive, send)
            return

        body_chunks: List[bytes] = []
        initial_message: Optional[Dict[str, Any]] = None
        content_type_value = ""
        bypass = False
        is_streaming = False
        headers_sent = False

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal initial_message, content_type_value, bypass, is_streaming, headers_sent

            if message["type"] == "http.response.start":
                status = message.get("status", 200)
                if status < 200 or status in (204, 304):
                    bypass = True
                    await send(message)
                    return
                initial_message = message
                headers_list = message.get("headers", [])
                for k, v in headers_list:
                    if k == b"content-type":
                        content_type_value = v.decode("latin-1")
                        break
                return

            if bypass:
                await send(message)
                return

            if message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                more_body = message.get("more_body", False)

                if more_body:
                    if not is_streaming and len(body_chunks) == 0:
                        is_streaming = True

                    if is_streaming and chunk:
                        if not headers_sent:
                            hdrs = dict(initial_message.get("headers", []))
                            if self._is_compressible(content_type_value):
                                hdrs[b"content-encoding"] = b"gzip"
                            hdrs.pop(b"content-length", None)
                            hdrs.pop(b"transfer-encoding", None)
                            await send({
                                "type": "http.response.start",
                                "status": initial_message.get("status", 200),
                                "headers": list(hdrs.items()),
                            })
                            headers_sent = True
                        if self._is_compressible(content_type_value) and len(chunk) >= self.minimum_size:
                            chunk = gzip.compress(chunk, compresslevel=self.compresslevel)
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
                    else:
                        body_chunks.append(chunk)
                    return

                # Final chunk
                body_chunks.append(chunk)
                full_body = b"".join(body_chunks)

                # Streaming already sent headers — just send the final body
                if headers_sent:
                    await send({"type": "http.response.body", "body": full_body, "more_body": False})
                    return

                if (
                    len(full_body) >= self.minimum_size
                    and self._is_compressible(content_type_value)
                ):
                    compressed = gzip.compress(full_body, compresslevel=self.compresslevel)
                    hdrs = dict(initial_message.get("headers", []))
                    hdrs[b"content-length"] = str(len(compressed)).encode("latin-1")
                    hdrs[b"content-encoding"] = b"gzip"
                    hdrs.pop(b"transfer-encoding", None)
                    await send({
                        "type": "http.response.start",
                        "status": initial_message.get("status", 200),
                        "headers": list(hdrs.items()),
                    })
                    await send({
                        "type": "http.response.body",
                        "body": compressed,
                        "more_body": False,
                    })
                else:
                    await send(initial_message)
                    await send({
                        "type": "http.response.body",
                        "body": full_body,
                        "more_body": False,
                    })
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestIDMiddleware:
    """ASGI middleware that attaches a unique request ID to every request.

    The request ID is generated as a UUID4 by default, or extracted from
    a configurable incoming header. It is added to the response via the
    ``X-Request-ID`` header (configurable).

    Usage::

        app.add_middleware(RequestIDMiddleware)
        # or with a custom header name:
        app.add_middleware(RequestIDMiddleware, header_name="X-Correlation-ID")
    """

    def __init__(
        self,
        app: Callable,
        header_name: str = "X-Request-ID",
        generator: Optional[Callable[[], str]] = None,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.generator = generator or (lambda: str(uuid.uuid4()))

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = None
        for k, v in scope.get("headers", []):
            if k.decode("latin-1").lower() == self.header_name.lower():
                request_id = v.decode("latin-1")
                break

        if not request_id:
            request_id = self.generator()

        async def send_wrapper(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                hdrs = dict(message.get("headers", []))
                hdrs[self.header_name.lower().encode("latin-1")] = request_id.encode("latin-1")
                message["headers"] = list(hdrs.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """ASGI middleware that rate-limits requests per client IP or per-user.

    Uses a sliding-window counter algorithm with automatic cleanup.
    Supports an optional Redis backend for distributed rate limiting.

    Usage::

        # Per-IP rate limiting (default)
        app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

        # Per-user rate limiting with custom key function
        def user_key(scope):
            for k, v in scope.get("headers", []):
                if k == b"x-user-id":
                    return v.decode("latin-1")
            # fallback to IP
            client = scope.get("client")
            return client[0] if client else "unknown"

        app.add_middleware(RateLimitMiddleware, key_func=user_key)

        # Distributed rate limiting with Redis
        import redis.asyncio as aioredis
        redis_client = aioredis.Redis()
        app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
    """

    def __init__(
        self,
        app: Callable,
        max_requests: int = 100,
        window_seconds: int = 60,
        key_func: Optional[Callable[[Dict[str, Any]], str]] = None,
        retry_after_header: bool = True,
        redis_client: Any = None,
    ) -> None:
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or self._default_key
        self.retry_after_header = retry_after_header
        self._redis = redis_client
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    @staticmethod
    def _default_key(scope: Dict[str, Any]) -> str:
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-for":
                return v.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    def _cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self.window_seconds:
            return
        self._last_cleanup = now
        cutoff = now - self.window_seconds
        expired_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if not self._requests[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del self._requests[key]

    def _is_rate_limited(self, key: str) -> Tuple[bool, float]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            oldest = self._requests[key][0]
            retry_after = self.window_seconds - (now - oldest)
            return True, max(retry_after, 0.0)
        self._requests[key].append(now)
        return False, 0.0

    async def _is_rate_limited_redis(self, key: str) -> Tuple[bool, float]:
        """Distributed rate limiting using Redis sliding window."""
        import time as _time
        now = _time.monotonic()
        window_start = now - self.window_seconds
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = await pipe.execute()
        current_count = results[1]
        if current_count >= self.max_requests:
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = self.window_seconds - (now - oldest[0][1])
                return True, max(retry_after, 0.0)
            return True, float(self.window_seconds)
        # Only add the request AFTER confirming it's allowed
        unique_id = f"{now}:{uuid.uuid4().hex[:8]}"
        add_pipe = self._redis.pipeline()
        add_pipe.zadd(key, {unique_id: now})
        add_pipe.expire(key, self.window_seconds)
        await add_pipe.execute()
        return False, 0.0

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self.key_func(scope)

        if self._redis is not None:
            limited, retry_after = await self._is_rate_limited_redis(key)
        else:
            self._cleanup()
            limited, retry_after = self._is_rate_limited(key)

        if limited:
            headers = [
                (b"retry-after", str(int(retry_after) + 1).encode("latin-1")),
                (b"content-type", b"application/json"),
            ]
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": headers,
            })
            body = f'{{"detail":"Rate limit exceeded. Try again in {int(retry_after)+1} seconds."}}'
            await send({"type": "http.response.body", "body": body.encode("utf-8")})
            return

        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """ASGI middleware that rejects requests exceeding a maximum body size.

    Prevents denial-of-service attacks via large request bodies.

    Usage::

        app.add_middleware(BodyLimitMiddleware, max_content_length=1_048_576)  # 1 MB
    """

    def __init__(
        self,
        app: Callable,
        max_content_length: int = 10_485_760,  # 10 MB default
        status_code: int = 413,
    ) -> None:
        self.app = app
        self.max_content_length = max_content_length
        self.status_code = status_code

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check Content-Length header first (fast path)
        content_length = 0
        has_content_length = False
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    content_length = int(v.decode("latin-1"))
                    has_content_length = True
                except (ValueError, TypeError):
                    content_length = 0
                break

        if has_content_length and content_length > self.max_content_length:
            body = json_dumps({"detail": f"Request body too large. Maximum size is {self.max_content_length} bytes."})
            await send({
                "type": "http.response.start",
                "status": self.status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            })
            await send({"type": "http.response.body", "body": body.encode("utf-8")})
            return

        # For chunked or unknown-length bodies, monitor actual size
        total_received = 0
        exceeded = False

        async def monitored_receive():
            nonlocal total_received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_received += len(chunk)
                if total_received > self.max_content_length and not exceeded:
                    exceeded = True
            return message

        # Wrap send to reject if body exceeded
        async def guarded_send(message):
            if exceeded and message["type"] == "http.response.start":
                body = json_dumps({"detail": f"Request body too large. Maximum size is {self.max_content_length} bytes."})
                await send({
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("latin-1")),
                    ],
                })
                await send({"type": "http.response.body", "body": body.encode("utf-8")})
                return
            await send(message)

        await self.app(scope, monitored_receive, guarded_send)


class CSRFMiddleware:
    """ASGI middleware that enforces CSRF token validation for state-changing methods.

    Reads the CSRF token from the ``X-CSRF-Token`` header and validates it
    against the ``_csrf_token`` cookie.  Safe methods (GET, HEAD, OPTIONS)
    are always allowed through.

    When ``auto_generate=True`` (default), a CSRF token cookie is injected
    into every safe-method response so clients can read it and send it back
    in subsequent state-changing requests.

    Usage::

        app.add_middleware(CSRFMiddleware, secret_key="my-secret")
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(
        self,
        app: Callable,
        secret_key: str = "",
        cookie_name: str = "_csrf_token",
        header_name: str = "X-CSRF-Token",
        safe_methods: Optional[frozenset] = None,
        auto_generate: bool = True,
    ) -> None:
        self.app = app
        self.secret_key = secret_key
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.safe_methods = safe_methods or self.SAFE_METHODS
        self.auto_generate = auto_generate

    def _generate_token(self) -> str:
        import hmac
        import hashlib
        import time
        import secrets
        if self.secret_key:
            ts = str(int(time.time()))
            return hmac.new(self.secret_key.encode(), ts.encode(), hashlib.sha256).hexdigest()
        return secrets.token_hex(32)

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        if method in self.safe_methods:
            if self.auto_generate:
                token = self._generate_token()
                async def send_with_csrf(message: Dict[str, Any]) -> None:
                    if message["type"] == "http.response.start":
                        headers = dict(message.get("headers", []))
                        cookie_val = f"{self.cookie_name}={token}; Path=/; SameSite=Lax"
                        headers[b"set-cookie"] = cookie_val.encode("latin-1")
                        message["headers"] = list(headers.items())
                    await send(message)
                await self.app(scope, receive, send_with_csrf)
            else:
                await self.app(scope, receive, send)
            return

        # Extract CSRF token from header
        header_token = None
        cookie_token = None
        for k, v in scope.get("headers", []):
            if k == self.header_name.lower().encode():
                header_token = v.decode("latin-1")
            if k == b"cookie":
                cookie_str = v.decode("latin-1")
                for part in cookie_str.split(";"):
                    part = part.strip()
                    if part.startswith(f"{self.cookie_name}="):
                        cookie_token = part.split("=", 1)[1]

        if not header_token or not cookie_token or header_token != cookie_token:
            body = json_dumps({"detail": "CSRF token missing or invalid."})
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            })
            await send({"type": "http.response.body", "body": body.encode("utf-8")})
            return

        await self.app(scope, receive, send)
