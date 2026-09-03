"""Targeted coverage tests for fenrir.middleware edge branches."""
import time
from collections import deque
from unittest.mock import MagicMock

import pytest

from fenrir.middleware import (
    BodyLimitMiddleware,
    CORSMiddleware,
    CSRFMiddleware,
    GZipMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)


def _scope(scope_type="http", method="GET", headers=None):
    return {"type": scope_type, "method": method, "headers": headers or []}


# ═══════════════════════════════════════════════════════════════════════
# CORSMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestCORS:
    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = CORSMiddleware(inner)
        await mw(_scope("lifespan"), None, None)
        assert called

    @pytest.mark.anyio
    async def test_ws_no_origin_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = CORSMiddleware(inner, allow_origins=["*"])
        await mw(_scope("websocket", headers=[(b"x", b"y")]), None, None)
        assert called

    @pytest.mark.anyio
    async def test_ws_http_response_headers(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "websocket.http.response.start", "status": 200, "headers": [(b"x", b"y")]})
            await send({"type": "websocket.http.response.body", "body": b"hi"})

        mw = CORSMiddleware(inner, allow_origins=["https://allowed.com"])
        await mw(_scope("websocket", headers=[(b"origin", b"https://allowed.com")]), receive, send)
        start = sent[0]
        assert (b"access-control-allow-origin", b"https://allowed.com") in start["headers"]


# ═══════════════════════════════════════════════════════════════════════
# GZipMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestGZip:
    def test_is_compressible(self):
        mw = GZipMiddleware(lambda: None)
        assert mw._is_compressible("text/html; charset=utf-8") is True
        assert mw._is_compressible("text/vnd.custom") is True
        assert mw._is_compressible("application/octet-stream") is False

    @pytest.mark.anyio
    async def test_no_accept_encoding_with_headers(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = GZipMiddleware(inner, minimum_size=0)
        await mw(_scope(headers=[(b"x-custom", b"1")]), receive, send)
        assert sent[0]["status"] == 200

    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = GZipMiddleware(inner)
        await mw(_scope("websocket"), None, None)
        assert called

    @pytest.mark.anyio
    async def test_no_content_type_header(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"x", b"1")]})
            await send({"type": "http.response.body", "body": b"a" * 1000})

        mw = GZipMiddleware(inner, minimum_size=0)
        await mw(_scope(headers=[(b"accept-encoding", b"gzip")]), receive, send)
        start = sent[0]
        assert (b"content-encoding", b"gzip") not in start["headers"]

    @pytest.mark.anyio
    async def test_streaming_non_compressible(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/octet-stream")],
            })
            await send({"type": "http.response.body", "body": b"part1", "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": True})
            await send({"type": "http.response.body", "body": b"part2", "more_body": False})

        mw = GZipMiddleware(inner, minimum_size=0)
        await mw(_scope(headers=[(b"accept-encoding", b"gzip")]), receive, send)
        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert (b"content-encoding", b"gzip") not in starts[0]["headers"]

    @pytest.mark.anyio
    async def test_body_before_headers_streaming(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.body", "body": b"chunk", "more_body": True})
            await send({"type": "http.response.body", "body": b"end", "more_body": False})

        mw = GZipMiddleware(inner, minimum_size=0)
        await mw(_scope(headers=[(b"accept-encoding", b"gzip")]), receive, send)
        assert sent[0]["type"] == "http.response.body"
        assert sent[0]["body"] == b"chunk"

    @pytest.mark.anyio
    async def test_unknown_message_type(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.trailers", "trailers": []})

        mw = GZipMiddleware(inner, minimum_size=0)
        await mw(_scope(headers=[(b"accept-encoding", b"gzip")]), receive, send)
        assert sent[-1]["type"] == "http.response.trailers"


# ═══════════════════════════════════════════════════════════════════════
# RequestIDMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestRequestID:
    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = RequestIDMiddleware(inner)
        await mw(_scope("lifespan"), None, None)
        assert called


# ═══════════════════════════════════════════════════════════════════════
# RateLimitMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimit:
    def test_default_key(self):
        mw = RateLimitMiddleware(lambda: None)
        assert mw._default_key({"headers": []}) == "unknown"
        assert mw._default_key({"headers": [], "client": ["1.2.3.4", 80]}) == "1.2.3.4"
        assert mw._default_key({"headers": [(b"x-forwarded-for", b"9.9.9.9, 8.8.8.8")]}) == "9.9.9.9"

    @pytest.mark.anyio
    async def test_cleanup(self):
        mw = RateLimitMiddleware(lambda: None, max_requests=1, window_seconds=60)
        mw._last_cleanup = time.monotonic() - 120
        now = time.monotonic()
        mw._requests["old"] = deque([now - 100, now - 90])
        mw._requests["new"] = deque([now])
        await mw._cleanup()
        assert "old" not in mw._requests
        assert "new" in mw._requests

    @pytest.mark.anyio
    async def test_expired_front_removed(self):
        mw = RateLimitMiddleware(lambda: None, max_requests=5, window_seconds=60)
        now = time.monotonic()
        mw._requests["k"] = deque([now - 100, now])
        limited, _ = await mw._is_rate_limited("k")
        assert limited is False

    @pytest.mark.anyio
    async def test_redis_limited_no_oldest(self):
        from unittest.mock import AsyncMock

        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, 5, 1, True])
        pipe.zadd = MagicMock()
        pipe.expire = MagicMock()
        redis = MagicMock()
        redis.pipeline = MagicMock(return_value=pipe)
        redis.zrange = AsyncMock(return_value=[])
        redis.zrem = AsyncMock()
        mw = RateLimitMiddleware(lambda: None, max_requests=2, window_seconds=60, redis_client=object())
        mw._redis = redis
        limited, retry = await mw._is_rate_limited_redis("key")
        assert limited is True
        assert retry == 60.0

    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = RateLimitMiddleware(inner)
        await mw(_scope("websocket"), None, None)
        assert called


# ═══════════════════════════════════════════════════════════════════════
# BodyLimitMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestBodyLimit:
    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = BodyLimitMiddleware(inner)
        await mw(_scope("lifespan"), None, None)
        assert called

    @pytest.mark.anyio
    async def test_invalid_content_length(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = BodyLimitMiddleware(inner, max_content_length=100)
        await mw(_scope("http", "POST", headers=[(b"content-length", b"abc")]), receive, send)
        assert sent[0]["status"] == 200

    @pytest.mark.anyio
    async def test_chunked_exceeded(self):
        sent = []
        chunks = [
            {"type": "http.request", "body": b"a" * 60, "more_body": True},
            {"type": "http.request", "body": b"b" * 60, "more_body": True},
            {"type": "http.request", "body": b"c" * 60, "more_body": False},
        ]

        async def send(msg):
            sent.append(msg)

        async def receive():
            return chunks.pop(0)

        async def inner(scope, receive, send):
            while True:
                msg = await receive()
                if not msg.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = BodyLimitMiddleware(inner, max_content_length=100)
        await mw(_scope("http", "POST"), receive, send)
        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert starts[0]["status"] == 413

    @pytest.mark.anyio
    async def test_non_request_message(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.disconnect"}

        async def inner(scope, receive, send):
            msg = await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = BodyLimitMiddleware(inner, max_content_length=100)
        await mw(_scope("http", "POST"), receive, send)
        assert sent[0]["status"] == 200


# ═══════════════════════════════════════════════════════════════════════
# CSRFMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestCSRF:
    def test_verify_token_no_secret(self):
        mw = CSRFMiddleware(lambda: None, secret_key="")
        # With empty secret_key, tokens are rejected (F1 fix: silent disable)
        assert mw._verify_token("anything") is False

    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = CSRFMiddleware(inner, secret_key="s")
        await mw(_scope("websocket"), None, None)
        assert called

    @pytest.mark.anyio
    async def test_safe_method_existing_token_append(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"set-cookie", b"session=abc")]})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = CSRFMiddleware(inner, secret_key="", auto_generate=True)
        scope = _scope(
            "http", "GET",
            headers=[(b"cookie", b"foo=1; _csrf_token=exist"), (b"x-extra", b"1")],
        )
        await mw(scope, receive, send)
        start = [m for m in sent if m["type"] == "http.response.start"][0]
        # Keep as list of tuples to verify BOTH set-cookie headers are preserved
        cookie_headers = [v for n, v in start["headers"] if n == b"set-cookie"]
        assert len(cookie_headers) == 2, f"Expected 2 set-cookie headers, got {len(cookie_headers)}: {cookie_headers}"
        assert b"session=abc" in cookie_headers[0]
        assert b"_csrf_token=exist" in cookie_headers[1]

    @pytest.mark.anyio
    async def test_safe_method_no_existing_token(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = CSRFMiddleware(inner, secret_key="", auto_generate=True)
        scope = _scope("http", "GET", headers=[(b"cookie", b"foo=1; bar=2"), (b"x-extra", b"1")])
        await mw(scope, receive, send)
        start = [m for m in sent if m["type"] == "http.response.start"][0]
        cookie_headers = [v for n, v in start["headers"] if n == b"set-cookie"]
        assert len(cookie_headers) == 1
        assert b"_csrf_token=" in cookie_headers[0]

    @pytest.mark.anyio
    async def test_unsafe_missing_token(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {}

        async def inner(scope, receive, send):
            pass

        mw = CSRFMiddleware(inner, secret_key="s")
        scope = _scope("http", "POST", headers=[(b"cookie", b"foo=1; bar=2")])
        await mw(scope, receive, send)
        assert sent[0]["status"] == 403


# ═══════════════════════════════════════════════════════════════════════
# SecurityHeadersMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    def test_options(self):
        mw = SecurityHeadersMiddleware(
            lambda: None,
            hsts_max_age=None,
            frame_options=None,
            content_type_options=None,
            referrer_policy=None,
            permissions_policy=None,
            cross_origin_opener_policy=None,
            csp="default-src 'self'",
            xss_protection="1",
        )
        names = [n for n, _ in mw._headers]
        assert b"content-security-policy" in names
        assert b"x-xss-protection" in names
        assert b"strict-transport-security" not in names

        mw2 = SecurityHeadersMiddleware(lambda: None, hsts_max_age=100, hsts_include_subdomains=False)
        hsts = [v for n, v in mw2._headers if n == b"strict-transport-security"][0]
        assert b"includeSubDomains" not in hsts

    @pytest.mark.anyio
    async def test_non_http_passthrough(self):
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        mw = SecurityHeadersMiddleware(inner)
        await mw(_scope("websocket"), None, None)
        assert called
