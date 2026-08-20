"""
Tests for all new middleware, pagination, session, and routing features.

Covers:
  - CORSMiddleware (HTTP + WebSocket)
  - GZipMiddleware
  - RequestIDMiddleware
  - RateLimitMiddleware
  - RedisSessionInterface / InMemorySessionInterface
  - WebSocket per-route timeout
  - Pagination utility
  - Multiple response models per status (runtime)
"""
import asyncio
import json
import time

import httpx
import pytest
from pydantic import BaseModel

from fenrir import (
    Fenrir,
    Response,
    WebSocket,
)
from fenrir.middleware import (
    CORSMiddleware,
    GZipMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
)
from fenrir.pagination import PaginationParams, paginate, paginate_dict
from fenrir.sessions import (
    InMemorySessionBackend,
    InMemorySessionInterface,
    RedisSessionInterface,
    ServerSideSession,
)

# ---------------------------------------------------------------------------
# CORSMiddleware — HTTP
# ---------------------------------------------------------------------------

class TestCORSMiddleware:
    @pytest.mark.anyio
    async def test_cors_preflight(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.options(
                "/data",
                headers={
                    "origin": "https://example.com",
                    "access-control-request-method": "GET",
                },
            )
            assert res.status_code == 204
            assert res.headers.get("access-control-allow-origin") == "https://example.com"
            # Default allow_methods is ["*"]
            assert res.headers.get("access-control-allow-methods") == "*"
            assert res.headers.get("access-control-allow-headers") == "*"
            assert res.headers.get("access-control-max-age") == "600"

    @pytest.mark.anyio
    async def test_cors_preflight_specific_methods(self):
        app = Fenrir()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://example.com"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.options(
                "/data",
                headers={
                    "origin": "https://example.com",
                    "access-control-request-method": "GET",
                },
            )
            assert res.status_code == 204
            assert "GET" in res.headers.get("access-control-allow-methods", "")
            assert "POST" in res.headers.get("access-control-allow-methods", "")
            assert "Content-Type" in res.headers.get("access-control-allow-headers", "")

    @pytest.mark.anyio
    async def test_cors_origin_allowed(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"origin": "https://example.com"})
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "https://example.com"

    @pytest.mark.anyio
    async def test_cors_origin_not_allowed(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://allowed.com"])

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"origin": "https://evil.com"})
            assert res.status_code == 200
            assert "access-control-allow-origin" not in res.headers

    @pytest.mark.anyio
    async def test_cors_wildcard(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Request without origin — should get "*"
            res = await client.get("/data")
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "*"

    @pytest.mark.anyio
    async def test_cors_wildcard_with_origin(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Request with origin — echoes origin back (CORS spec behavior)
            res = await client.get("/data", headers={"origin": "https://any.com"})
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "https://any.com"

    @pytest.mark.anyio
    async def test_cors_credentials(self):
        app = Fenrir()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://example.com"],
            allow_credentials=True,
            expose_headers=["X-Custom"],
        )

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"origin": "https://example.com"})
            assert res.headers.get("access-control-allow-credentials") == "true"
            assert "X-Custom" in res.headers.get("access-control-expose-headers", "")

    @pytest.mark.anyio
    async def test_cors_preflight_max_age(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["*"], max_age=3600)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.options(
                "/data",
                headers={"origin": "https://example.com", "access-control-request-method": "GET"},
            )
            assert res.headers.get("access-control-max-age") == "3600"


# ---------------------------------------------------------------------------
# CORSMiddleware — WebSocket
# ---------------------------------------------------------------------------

class TestCORSWebSocket:
    @pytest.mark.anyio
    async def test_cors_websocket_origin_allowed(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])

        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket):
            await ws.accept()
            msg = await ws.receive_text()
            await ws.send_text(f"echo: {msg}")
            await ws.close()

        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [(b"origin", b"https://example.com")],
        }
        receive_queue = asyncio.Queue()
        send_queue = asyncio.Queue()

        async def receive():
            return await receive_queue.get()

        async def send(msg):
            await send_queue.put(msg)

        await receive_queue.put({"type": "websocket.connect"})
        task = asyncio.create_task(app(scope, receive, send))

        accept_msg = await send_queue.get()
        assert accept_msg["type"] == "websocket.accept"

        await receive_queue.put({"type": "websocket.receive", "text": "hello"})
        echo_msg = await send_queue.get()
        assert echo_msg["text"] == "echo: hello"

        await receive_queue.put({"type": "websocket.disconnect", "code": 1000})
        await task

    @pytest.mark.anyio
    async def test_cors_websocket_origin_not_allowed(self):
        app = Fenrir()
        app.add_middleware(CORSMiddleware, allow_origins=["https://allowed.com"])

        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket):
            await ws.accept()

        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [(b"origin", b"https://evil.com")],
        }
        receive_queue = asyncio.Queue()
        send_queue = asyncio.Queue()

        async def receive():
            return await receive_queue.get()

        async def send(msg):
            await send_queue.put(msg)

        await receive_queue.put({"type": "websocket.connect"})
        task = asyncio.create_task(app(scope, receive, send))

        # When origin not allowed, middleware passes through — handler accepts
        msg = await send_queue.get()
        assert msg["type"] in ("websocket.accept", "websocket.close")
        await task


# ---------------------------------------------------------------------------
# GZipMiddleware
# ---------------------------------------------------------------------------

class TestGZipMiddleware:
    @pytest.mark.anyio
    async def test_gzip_compresses_large_response(self):
        app = Fenrir()
        app.add_middleware(GZipMiddleware, minimum_size=100)

        @app.get("/data")
        async def data():
            return "x" * 1000

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            http1=False, http2=False,
        ) as client:
            res = await client.get("/data", headers={"accept-encoding": "gzip"})
            assert res.status_code == 200
            assert res.headers.get("content-encoding") == "gzip"
            # httpx auto-decompresses; verify original content integrity
            assert res.text == "x" * 1000

    @pytest.mark.anyio
    async def test_gzip_no_compress_small_response(self):
        app = Fenrir()
        app.add_middleware(GZipMiddleware, minimum_size=1000)

        @app.get("/data")
        async def data():
            return "small"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"accept-encoding": "gzip"})
            assert res.status_code == 200
            assert "content-encoding" not in res.headers
            assert res.text == "small"

    @pytest.mark.anyio
    async def test_gzip_no_compress_without_accept_encoding(self):
        app = Fenrir()
        app.add_middleware(GZipMiddleware, minimum_size=100)

        @app.get("/data")
        async def data():
            return "x" * 1000

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Explicitly set accept-encoding to something other than gzip
            res = await client.get("/data", headers={"accept-encoding": "identity"})
            assert res.status_code == 200
            assert "content-encoding" not in res.headers
            assert res.text == "x" * 1000

    @pytest.mark.anyio
    async def test_gzip_json_response(self):
        app = Fenrir()
        app.add_middleware(GZipMiddleware, minimum_size=50)

        @app.get("/data")
        async def data():
            return {"key": "x" * 200}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"accept-encoding": "gzip"})
            assert res.status_code == 200
            # httpx auto-decompresses gzip; verify content integrity
            parsed = res.json()
            assert parsed["key"] == "x" * 200

    @pytest.mark.anyio
    async def test_gzip_204_not_compressed(self):
        app = Fenrir()
        app.add_middleware(GZipMiddleware, minimum_size=0)

        @app.get("/no-content")
        async def no_content():
            return Response(status=204)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/no-content", headers={"accept-encoding": "gzip"})
            assert res.status_code == 204
            assert "content-encoding" not in res.headers


# ---------------------------------------------------------------------------
# RequestIDMiddleware
# ---------------------------------------------------------------------------

class TestRequestIDMiddleware:
    @pytest.mark.anyio
    async def test_request_id_generated(self):
        app = Fenrir()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data")
            assert res.status_code == 200
            rid = res.headers.get("x-request-id")
            assert rid is not None
            assert len(rid) > 0

    @pytest.mark.anyio
    async def test_request_id_from_client(self):
        app = Fenrir()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data", headers={"X-Request-ID": "my-custom-id"})
            assert res.headers.get("x-request-id") == "my-custom-id"

    @pytest.mark.anyio
    async def test_request_id_custom_header(self):
        app = Fenrir()
        app.add_middleware(RequestIDMiddleware, header_name="X-Correlation-ID")

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data")
            assert "x-correlation-id" in res.headers
            assert "x-request-id" not in res.headers

    @pytest.mark.anyio
    async def test_request_id_custom_generator(self):
        app = Fenrir()
        app.add_middleware(RequestIDMiddleware, generator=lambda: "fixed-id-123")

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/data")
            assert res.headers.get("x-request-id") == "fixed-id-123"


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:
    @pytest.mark.anyio
    async def test_rate_limit_allows_under_limit(self):
        app = Fenrir()
        app.add_middleware(RateLimitMiddleware, max_requests=5, window_seconds=60)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(5):
                res = await client.get("/data")
                assert res.status_code == 200

    @pytest.mark.anyio
    async def test_rate_limit_blocks_over_limit(self):
        app = Fenrir()
        app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                res = await client.get("/data")
                assert res.status_code == 200

            res = await client.get("/data")
            assert res.status_code == 429
            body = res.json()
            assert "Rate limit exceeded" in body["detail"]
            assert "retry-after" in res.headers

    @pytest.mark.anyio
    async def test_rate_limit_different_clients(self):
        app = Fenrir()
        app.add_middleware(RateLimitMiddleware, max_requests=2, window_seconds=60)

        @app.get("/data")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Client 1 — exhaust limit
            res = await client.get("/data", headers={"X-Forwarded-For": "1.1.1.1"})
            assert res.status_code == 200
            res = await client.get("/data", headers={"X-Forwarded-For": "1.1.1.1"})
            assert res.status_code == 200
            res = await client.get("/data", headers={"X-Forwarded-For": "1.1.1.1"})
            assert res.status_code == 429

            # Client 2 — separate bucket
            res = await client.get("/data", headers={"X-Forwarded-For": "2.2.2.2"})
            assert res.status_code == 200
            res = await client.get("/data", headers={"X-Forwarded-For": "2.2.2.2"})
            assert res.status_code == 200
            res = await client.get("/data", headers={"X-Forwarded-For": "2.2.2.2"})
            assert res.status_code == 429


# ---------------------------------------------------------------------------
# InMemorySessionInterface
# ---------------------------------------------------------------------------

class TestInMemorySession:
    def test_backend_basic_ops(self):
        backend = InMemorySessionBackend()
        backend.set("sid1", {"user": "alice"}, ttl=60)
        data = backend.get("sid1")
        assert data == {"user": "alice"}

        backend.delete("sid1")
        assert backend.get("sid1") is None

    def test_backend_expiration(self):
        backend = InMemorySessionBackend()
        backend.set("sid1", {"user": "alice"}, ttl=0)
        time.sleep(0.01)
        backend._cleanup()
        assert backend.get("sid1") is None

    @pytest.mark.anyio
    async def test_in_memory_session_interface(self):
        app = Fenrir()
        interface = InMemorySessionInterface()
        app.session_interface = interface
        app.config["SECRET_KEY"] = "test-secret"

        @app.get("/set")
        async def set_session():
            from fenrir.context import session
            session["user"] = "alice"
            return {"ok": True}

        @app.get("/get")
        async def get_session():
            from fenrir.context import session
            return {"user": session.get("user")}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/set")
            assert res.status_code == 200
            cookie = res.cookies.get("session")
            assert cookie is not None

            client.cookies.set("session", cookie)
            res2 = await client.get("/get")
            assert res2.status_code == 200
            assert res2.json()["user"] == "alice"


# ---------------------------------------------------------------------------
# WebSocket per-route timeout
# ---------------------------------------------------------------------------

class TestWebSocketTimeout:
    @pytest.mark.anyio
    async def test_websocket_timeout_fires(self):
        from fenrir.websocket import WebSocketTimeout

        app = Fenrir()

        @app.websocket("/ws/timeout", timeout=0.1)
        async def timeout_handler(ws: WebSocket):
            await ws.accept()
            try:
                msg = await ws.receive_text()
                await ws.send_text(msg)
            except WebSocketTimeout:
                await ws.close(code=1000, reason="timeout")

        scope = {
            "type": "websocket",
            "path": "/ws/timeout",
            "headers": [],
        }
        receive_queue = asyncio.Queue()
        send_queue = asyncio.Queue()

        async def receive():
            return await receive_queue.get()

        async def send(msg):
            await send_queue.put(msg)

        await receive_queue.put({"type": "websocket.connect"})
        task = asyncio.create_task(app(scope, receive, send))

        accept_msg = await send_queue.get()
        assert accept_msg["type"] == "websocket.accept"

        # Don't send anything — let timeout fire
        close_msg = await asyncio.wait_for(send_queue.get(), timeout=2.0)
        assert close_msg["type"] == "websocket.close"
        assert close_msg["reason"] == "timeout"

        await task

    @pytest.mark.anyio
    async def test_websocket_no_timeout(self):
        app = Fenrir()

        @app.websocket("/ws/notimeout")
        async def no_timeout_handler(ws: WebSocket):
            await ws.accept()
            msg = await ws.receive_text()
            await ws.send_text(f"got: {msg}")
            await ws.close()

        scope = {
            "type": "websocket",
            "path": "/ws/notimeout",
            "headers": [],
        }
        receive_queue = asyncio.Queue()
        send_queue = asyncio.Queue()

        async def receive():
            return await receive_queue.get()

        async def send(msg):
            await send_queue.put(msg)

        await receive_queue.put({"type": "websocket.connect"})
        task = asyncio.create_task(app(scope, receive, send))

        accept_msg = await send_queue.get()
        assert accept_msg["type"] == "websocket.accept"

        await receive_queue.put({"type": "websocket.receive", "text": "hello"})
        echo_msg = await send_queue.get()
        assert echo_msg["text"] == "got: hello"

        close_msg = await send_queue.get()
        assert close_msg["type"] == "websocket.close"

        await task


# ---------------------------------------------------------------------------
# Pagination utility
# ---------------------------------------------------------------------------

class TestPagination:
    def test_paginate_basic(self):
        items = list(range(50))
        result = paginate(items, page=1, size=10)
        assert result["items"] == list(range(10))
        assert result["total"] == 50
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["pages"] == 5
        assert result["has_next"] is True
        assert result["has_prev"] is False

    def test_paginate_last_page(self):
        items = list(range(50))
        result = paginate(items, page=5, size=10)
        assert result["items"] == list(range(40, 50))
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_paginate_page_clamped(self):
        items = list(range(10))
        result = paginate(items, page=999, size=10)
        assert result["page"] == 1
        assert result["has_next"] is False

    def test_paginate_empty(self):
        result = paginate([], page=1, size=10)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["pages"] == 1
        assert result["has_next"] is False
        assert result["has_prev"] is False

    def test_paginate_with_base_url(self):
        items = list(range(25))
        result = paginate(items, page=2, size=10, base_url="/items?foo=bar")
        links = result["links"]
        assert "page=2" in links["self_url"]
        assert "page=3" in links["next_url"]
        assert "page=1" in links["prev_url"]
        assert "page=3" in links["last_url"]

    def test_paginate_dict(self):
        items = [{"id": i} for i in range(15)]
        result = paginate_dict(items, page=1, size=5)
        assert len(result["items"]) == 5
        assert result["items"][0]["id"] == 0
        assert result["total"] == 15

    def test_pagination_params(self):
        p = PaginationParams(page=3, size=20)
        assert p.offset == 40
        assert p.limit == 20

    def test_paginate_first_page(self):
        items = list(range(25))
        result = paginate(items, page=1, size=10)
        assert result["has_prev"] is False
        assert result["has_next"] is True

    def test_paginate_middle_page(self):
        items = list(range(50))
        result = paginate(items, page=3, size=10)
        assert result["items"] == list(range(20, 30))
        assert result["has_prev"] is True
        assert result["has_next"] is True


# ---------------------------------------------------------------------------
# Multiple response models per status (runtime)
# ---------------------------------------------------------------------------

class ItemOut(BaseModel):
    id: int
    name: str

class ErrorOut(BaseModel):
    detail: str
    code: int

class TestMultipleResponseModels:
    @pytest.mark.anyio
    async def test_multiple_response_models_200(self):
        app = Fenrir()

        @app.get(
            "/items/<item_id:int>",
            response_models={
                200: ItemOut,
                404: ErrorOut,
            },
        )
        async def get_item(item_id: int):
            if item_id == 1:
                return {"id": 1, "name": "Widget"}
            return Response(
                body=json.dumps({"detail": "Not found", "code": 404}).encode(),
                status=404,
                content_type="application/json",
            )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/items/1")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == 1
            assert data["name"] == "Widget"
            assert "extra" not in data

    @pytest.mark.anyio
    async def test_multiple_response_models_404(self):
        app = Fenrir()

        @app.get(
            "/items/<item_id:int>",
            response_models={
                200: ItemOut,
                404: ErrorOut,
            },
        )
        async def get_item(item_id: int):
            if item_id == 1:
                return {"id": 1, "name": "Widget"}
            return Response(
                body=json.dumps({"detail": "Not found", "code": 404}).encode(),
                status=404,
                content_type="application/json",
            )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/items/999")
            assert res.status_code == 404
            data = res.json()
            assert data["detail"] == "Not found"
            assert data["code"] == 404

    @pytest.mark.anyio
    async def test_multiple_response_models_tuple_return(self):
        app = Fenrir()

        @app.get(
            "/items/<item_id:int>",
            response_models={
                200: ItemOut,
                404: ErrorOut,
            },
        )
        async def get_item(item_id: int):
            if item_id == 1:
                return {"id": 1, "name": "Widget"}, 200
            return {"detail": "Not found", "code": 404}, 404

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/items/1")
            assert res.status_code == 200
            assert res.json()["name"] == "Widget"

            res = await client.get("/items/999")
            assert res.status_code == 404
            assert res.json()["detail"] == "Not found"

    @pytest.mark.anyio
    async def test_response_model_backward_compat(self):
        """Ensure the existing single response_model still works."""
        app = Fenrir()

        @app.get("/item", response_model=ItemOut)
        async def get_item():
            return {"id": 1, "name": "Widget", "extra": "ignored"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/item")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == 1
            assert data["name"] == "Widget"
            assert "extra" not in data

    @pytest.mark.anyio
    async def test_multiple_response_models_only_matching_status(self):
        """Only the model matching the actual status code is applied."""
        app = Fenrir()

        @app.get(
            "/items/<item_id:int>",
            response_models={
                200: ItemOut,
                404: ErrorOut,
            },
        )
        async def get_item(item_id: int):
            return {"id": 1, "name": "Widget"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/items/1")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == 1
            assert data["name"] == "Widget"


# ---------------------------------------------------------------------------
# Redis session backend (fakeredis)
# ---------------------------------------------------------------------------

class TestRedisSession:
    def _make_redis(self):
        import fakeredis
        return fakeredis.FakeRedis()

    def test_redis_session_basic(self):
        redis = self._make_redis()
        interface = RedisSessionInterface(redis_client=redis, ttl=60)
        app = Fenrir()
        app.config["SESSION_COOKIE_NAME"] = "session"
        app.session_interface = interface

        # Simulate a request without cookie → new session
        from fenrir.request import Request
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        req = Request(scope)
        session = interface.open_session(app, req)
        assert isinstance(session, ServerSideSession)
        assert session.sid
        assert len(session) == 0

        # Modify session and save
        session["user"] = "alice"
        session["role"] = "admin"

        from fenrir.response import Response
        resp = Response()
        interface.save_session(app, session, resp)

        # Verify cookie was set
        cookie_sid = resp.cookies.get("session")
        assert cookie_sid is not None

        # Verify data was stored in Redis
        stored = redis.get(f"session:{session.sid}")
        assert stored is not None
        import json
        data = json.loads(stored)
        assert data["user"] == "alice"
        assert data["role"] == "admin"

    def test_redis_session_load_existing(self):
        redis = self._make_redis()
        interface = RedisSessionInterface(redis_client=redis, ttl=60)
        app = Fenrir()
        app.config["SESSION_COOKIE_NAME"] = "session"
        app.session_interface = interface

        # Manually store session data in Redis
        import json
        sid = "test-existing-sid"
        redis.set(f"session:{sid}", json.dumps({"user": "bob", "lang": "en"}))

        # Request with the cookie → should load existing session
        from fenrir.request import Request
        scope = {
            "type": "http", "method": "GET", "path": "/",
            "headers": [(b"cookie", f"session={sid}".encode())],
            "query_string": b"",
        }
        req = Request(scope)
        session = interface.open_session(app, req)
        assert session.sid == sid
        assert session["user"] == "bob"
        assert session["lang"] == "en"

    def test_redis_session_delete_on_empty(self):
        redis = self._make_redis()
        interface = RedisSessionInterface(redis_client=redis, ttl=60)
        app = Fenrir()
        app.config["SESSION_COOKIE_NAME"] = "session"
        app.session_interface = interface

        # Store a session
        import json
        sid = "to-delete-sid"
        redis.set(f"session:{sid}", json.dumps({"user": "charlie"}))

        # Create session object and clear it
        session = ServerSideSession()
        session.sid = sid
        session["user"] = "charlie"
        session.clear()  # makes it empty but modified

        from fenrir.response import Response
        resp = Response()
        interface.save_session(app, session, resp)

        # Data should be deleted from Redis
        assert redis.get(f"session:{sid}") is None

    @pytest.mark.anyio
    async def test_redis_session_end_to_end(self):
        """Full integration: set session in one request, read in next."""
        redis = self._make_redis()
        interface = RedisSessionInterface(redis_client=redis, ttl=60)

        app = Fenrir()
        app.config["SESSION_COOKIE_NAME"] = "sid"
        app.session_interface = interface

        @app.get("/login")
        async def login():
            from fenrir.context import session
            session["user"] = "dave"
            return {"ok": True}

        @app.get("/whoami")
        async def whoami():
            from fenrir.context import session
            return {"user": session.get("user")}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Login — sets session
            res = await client.get("/login")
            assert res.status_code == 200
            cookie = res.cookies.get("sid")
            assert cookie is not None

            # Whoami — reads session
            client.cookies.set("sid", cookie)
            res2 = await client.get("/whoami")
            assert res2.status_code == 200
            assert res2.json()["user"] == "dave"

    def test_redis_session_custom_prefix(self):
        redis = self._make_redis()
        interface = RedisSessionInterface(redis_client=redis, prefix="myapp:sess:", ttl=120)
        app = Fenrir()
        app.config["SESSION_COOKIE_NAME"] = "session"
        app.session_interface = interface

        from fenrir.request import Request
        from fenrir.response import Response
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        req = Request(scope)
        session = interface.open_session(app, req)
        session["x"] = 1
        resp = Response()
        interface.save_session(app, session, resp)

        # Data stored with custom prefix
        assert redis.get(f"myapp:sess:{session.sid}") is not None
        # Default prefix should not exist
        assert redis.get(f"session:{session.sid}") is None
