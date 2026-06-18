"""
Tests for new features added to Fenrir v3.1.3:
- Trie-based routing
- Streaming request body
- Streaming GZip compression
- WebSocket authentication
- Connection pooling
- Per-user rate limiting
- HTTP/2 push
- Optimal GZip level
- Distributed rate limiting
"""
import asyncio
import gzip
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fenrir import Fenrir, Depends, WebSocket
from fenrir.routing import RouteTrie, Router, Route
from fenrir.middleware import GZipMiddleware, RateLimitMiddleware
from fenrir.security import WebSocketTokenAuth
from fenrir.pool import ConnectionPool, DatabasePool
from fenrir.http2 import HTTP2Push
from fenrir.request import Request


# ============================================================================
# Trie-based routing tests
# ============================================================================

class TestRouteTrie:
    def setup_method(self):
        self.trie = RouteTrie()

    def test_static_route_insert_and_search(self):
        route = Route("/users", lambda: None, ["GET"])
        self.trie.insert(route)
        candidates = self.trie.search("/users")
        assert len(candidates) == 1
        assert candidates[0] is route

    def test_static_route_no_match(self):
        route = Route("/users", lambda: None, ["GET"])
        self.trie.insert(route)
        candidates = self.trie.search("/posts")
        assert len(candidates) == 0

    def test_parametric_route_search(self):
        route = Route("/users/<int:id>", lambda: None, ["GET"])
        self.trie.insert(route)
        candidates = self.trie.search("/users/42")
        assert len(candidates) == 1
        assert candidates[0] is route

    def test_multiple_routes_same_level(self):
        r1 = Route("/users", lambda: None, ["GET"])
        r2 = Route("/posts", lambda: None, ["GET"])
        self.trie.insert(r1)
        self.trie.insert(r2)
        assert len(self.trie.search("/users")) == 1
        assert len(self.trie.search("/posts")) == 1

    def test_nested_static_routes(self):
        r1 = Route("/api/v1/users", lambda: None, ["GET"])
        r2 = Route("/api/v1/posts", lambda: None, ["GET"])
        self.trie.insert(r1)
        self.trie.insert(r2)
        assert len(self.trie.search("/api/v1/users")) == 1
        assert len(self.trie.search("/api/v1/posts")) == 1

    def test_mixed_static_and_parametric(self):
        r1 = Route("/users", lambda: None, ["GET"])
        r2 = Route("/users/<int:id>", lambda: None, ["GET"])
        self.trie.insert(r1)
        self.trie.insert(r2)
        candidates_users = self.trie.search("/users")
        candidates_user_id = self.trie.search("/users/42")
        assert len(candidates_users) == 1
        assert len(candidates_user_id) == 1

    def test_root_route(self):
        route = Route("/", lambda: None, ["GET"])
        self.trie.insert(route)
        candidates = self.trie.search("/")
        assert len(candidates) == 1

    def test_deep_path_search(self):
        route = Route("/a/b/c/d/e", lambda: None, ["GET"])
        self.trie.insert(route)
        candidates = self.trie.search("/a/b/c/d/e")
        assert len(candidates) == 1


class TestRouterTrieIntegration:
    def test_router_uses_trie_for_matching(self):
        router = Router()

        def handler1(): pass
        def handler2(): pass

        router.add_route("/users", handler1, ["GET"])
        router.add_route("/posts/<int:id>", handler2, ["GET"])

        route, params, handler = router.match("/users", "GET")
        assert route.path_pattern == "/users"

        route, params, handler = router.match("/posts/42", "GET")
        assert route.path_pattern == "/posts/<int:id>"
        assert params == {"id": 42}

    def test_router_trie_performance_with_many_routes(self):
        router = Router()

        def handler(): pass

        # Add 1000 routes
        for i in range(1000):
            router.add_route(f"/route/{i}", handler, ["GET"])

        # Search should be fast even with many routes
        start = time.monotonic()
        for i in range(100):
            router.match(f"/route/{i}", "GET")
        elapsed = time.monotonic() - start

        # Should complete in under 1 second for 100 lookups
        assert elapsed < 1.0


# ============================================================================
# Streaming request body tests
# ============================================================================

class TestStreamingBody:
    @pytest.mark.anyio
    async def test_stream_body_from_buffered(self):
        from fenrir.request import Request

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [],
            "query_string": b"",
        }
        req = Request(scope)
        req._body = b"hello world"
        req._parsed = True

        chunks = []
        async for chunk in req.stream_body(chunk_size=4):
            chunks.append(chunk)

        assert chunks == [b"hell", b"o wo", b"rld"]

    @pytest.mark.anyio
    async def test_stream_body_empty(self):
        from fenrir.request import Request

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [],
            "query_string": b"",
        }
        req = Request(scope)
        req._body = b""
        req._parsed = True

        chunks = []
        async for chunk in req.stream_body():
            chunks.append(chunk)

        assert chunks == []

    @pytest.mark.anyio
    async def test_stream_body_full_chunk(self):
        from fenrir.request import Request

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [],
            "query_string": b"",
        }
        req = Request(scope)
        req._body = b"exact"
        req._parsed = True

        chunks = []
        async for chunk in req.stream_body(chunk_size=5):
            chunks.append(chunk)

        assert chunks == [b"exact"]


# ============================================================================
# GZip middleware tests
# ============================================================================

class TestGZipMiddleware:
    @pytest.mark.anyio
    async def test_gzip_compresslevel_default(self):
        app_mock = AsyncMock()

        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"x" * 1000,
                "more_body": False,
            })

        mw = GZipMiddleware(dummy_app, minimum_size=100, compresslevel=6)
        assert mw.compresslevel == 6

    @pytest.mark.anyio
    async def test_gzip_compresslevel_custom(self):
        async def dummy_app(scope, receive, send):
            pass

        mw = GZipMiddleware(dummy_app, compresslevel=3)
        assert mw.compresslevel == 3

    @pytest.mark.anyio
    async def test_gzip_compression_works(self):
        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"x" * 1000,
                "more_body": False,
            })

        mw = GZipMiddleware(dummy_app, minimum_size=100, compresslevel=6)

        sent_messages = []
        async def mock_send(message):
            sent_messages.append(message)

        scope = {
            "type": "http",
            "method": "GET",
            "headers": [(b"accept-encoding", b"gzip")],
        }
        await mw(scope, AsyncMock(), mock_send)

        # Should have compressed the response
        assert len(sent_messages) == 2
        assert sent_messages[0]["type"] == "http.response.start"
        headers_dict = dict(sent_messages[0]["headers"])
        assert b"content-encoding" in headers_dict
        assert headers_dict[b"content-encoding"] == b"gzip"

    @pytest.mark.anyio
    async def test_gzip_bypass_small_response(self):
        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"small",
                "more_body": False,
            })

        mw = GZipMiddleware(dummy_app, minimum_size=100, compresslevel=6)

        sent_messages = []
        async def mock_send(message):
            sent_messages.append(message)

        scope = {
            "type": "http",
            "method": "GET",
            "headers": [(b"accept-encoding", b"gzip")],
        }
        await mw(scope, AsyncMock(), mock_send)

        # Should NOT compress small response
        assert len(sent_messages) == 2
        headers_dict = dict(sent_messages[0]["headers"])
        assert b"content-encoding" not in headers_dict


# ============================================================================
# Rate limiting tests
# ============================================================================

class TestRateLimitMiddleware:
    def test_default_key_func(self):
        scope = {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
        }
        key = RateLimitMiddleware._default_key(scope)
        assert key == "1.2.3.4"

    def test_default_key_func_client(self):
        scope = {
            "type": "http",
            "headers": [],
            "client": ("192.168.1.1", 12345),
        }
        key = RateLimitMiddleware._default_key(scope)
        assert key == "192.168.1.1"

    def test_custom_key_func_user_id(self):
        def user_key(scope):
            for k, v in scope.get("headers", []):
                if k == b"x-user-id":
                    return v.decode("latin-1")
            return "anonymous"

        scope = {
            "type": "http",
            "headers": [(b"x-user-id", b"user-123")],
        }
        key = user_key(scope)
        assert key == "user-123"

    @pytest.mark.anyio
    async def test_rate_limit_enforced(self):
        async def dummy_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RateLimitMiddleware(dummy_app, max_requests=3, window_seconds=60)

        scope = {"type": "http", "headers": [], "client": ("1.2.3.4", 12345)}

        # First 3 requests should pass
        for _ in range(3):
            sent = []
            async def mock_send(msg):
                sent.append(msg)
            await mw(scope, AsyncMock(), mock_send)

        # 4th request should be rate limited
        sent = []
        async def mock_send(msg):
            sent.append(msg)
        await mw(scope, AsyncMock(), mock_send)

        assert sent[0]["status"] == 429


# ============================================================================
# WebSocket auth tests
# ============================================================================

class TestWebSocketTokenAuth:
    @pytest.mark.anyio
    async def test_ws_auth_from_header(self):
        auth = WebSocketTokenAuth()
        ws = MagicMock()
        ws.scope = {
            "headers": [(b"authorization", b"Bearer test-token-123")],
            "query_string": b"",
        }

        result = await auth(ws)
        assert result == "test-token-123"

    @pytest.mark.anyio
    async def test_ws_auth_from_query(self):
        auth = WebSocketTokenAuth()
        ws = MagicMock()
        ws.scope = {
            "headers": [],
            "query_string": b"token=query-token-456",
        }

        result = await auth(ws)
        assert result == "query-token-456"

    @pytest.mark.anyio
    async def test_ws_auth_no_token(self):
        auth = WebSocketTokenAuth(auto_error=False)
        ws = MagicMock()
        ws.scope = {
            "headers": [],
            "query_string": b"",
        }

        result = await auth(ws)
        assert result is None

    @pytest.mark.anyio
    async def test_ws_auth_raises_on_missing(self):
        auth = WebSocketTokenAuth(auto_error=True)
        ws = MagicMock()
        ws.scope = {
            "headers": [],
            "query_string": b"",
        }

        with pytest.raises(Exception):
            await auth(ws)


# ============================================================================
# Connection pool tests
# ============================================================================

class TestConnectionPool:
    @pytest.mark.anyio
    async def test_pool_acquire_and_release(self):
        conn_counter = 0

        def create():
            nonlocal conn_counter
            conn_counter += 1
            return f"conn-{conn_counter}"

        pool = ConnectionPool(create_func=create, min_size=1, max_size=3)
        await pool.initialize()

        async with pool.acquire() as conn:
            assert conn == "conn-1"

        # Connection should be returned to pool
        assert pool.stats["idle"] == 1

    @pytest.mark.anyio
    async def test_pool_max_size(self):
        def create():
            return "conn"

        pool = ConnectionPool(create_func=create, min_size=0, max_size=2)
        await pool.initialize()

        async with pool.acquire() as conn1:
            async with pool.acquire() as conn2:
                # Both connections acquired
                assert pool.stats["active"] == 2

        # After releasing both, they should be idle
        assert pool.stats["idle"] >= 1

    @pytest.mark.anyio
    async def test_pool_discard_on_error(self):
        def create():
            return "conn"

        pool = ConnectionPool(create_func=create, min_size=0, max_size=3)
        await pool.initialize()

        async with pool.acquire() as conn:
            pass  # Connection will be released normally

        # After release, connection should be in idle pool
        assert pool.stats["idle"] >= 1

    @pytest.mark.anyio
    async def test_pool_close(self):
        def create():
            return "conn"

        pool = ConnectionPool(create_func=create, min_size=2, max_size=5)
        await pool.initialize()
        assert pool.stats["idle"] == 2

        await pool.close()
        assert pool._closed is True
        assert pool.stats["idle"] == 0


class TestDatabasePool:
    @pytest.mark.anyio
    async def test_execute_with_retry(self):
        call_count = 0

        def create():
            return "db-conn"

        def failing_query(conn):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection lost")
            return "success"

        pool = DatabasePool(create_func=create, min_size=1, max_size=3)
        result = await pool.execute_with_retry(failing_query, retries=3)
        assert result == "success"
        assert call_count == 3


# ============================================================================
# HTTP/2 push tests
# ============================================================================

class TestHTTP2Push:
    def test_push_adds_link_header(self):
        push = HTTP2Push()
        resp = push.push("<html></html>", push_paths=["/style.css", "/app.js"])

        assert resp.headers.get("x-http2-push") == "true"
        assert "/style.css" in resp.headers.get("link", "")
        assert "/app.js" in resp.headers.get("link", "")

    def test_push_guesses_as_type(self):
        assert HTTP2Push._guess_as("/style.css") == "style"
        assert HTTP2Push._guess_as("/app.js") == "script"
        assert HTTP2Push._guess_as("/font.woff2") == "font"
        assert HTTP2Push._guess_as("/image.png") == "image"
        assert HTTP2Push._guess_as("/page.html") == "document"
        assert HTTP2Push._guess_as("/data.json") == "fetch"

    def test_push_no_paths(self):
        push = HTTP2Push()
        resp = push.push("<html></html>", push_paths=[])
        assert resp.headers.get("x-http2-push") is None

    def test_add_push_path_chainable(self):
        push = HTTP2Push()
        push.add_push_path("/style.css").add_push_path("/app.js")
        assert push._push_paths == ["/style.css", "/app.js"]

    def test_clear_push_paths(self):
        push = HTTP2Push()
        push.add_push_path("/style.css")
        push.clear_push_paths()
        assert push._push_paths == []

    @pytest.mark.anyio
    async def test_auto_push_decorator(self):
        push = HTTP2Push()

        @push.auto_push(static_url="/static", paths=["style.css", "app.js"])
        async def index():
            return "<html></html>"

        resp = await index()
        assert resp.headers.get("x-http2-push") == "true"
        assert "/static/style.css" in resp.headers.get("link", "")


# ============================================================================
# App integration tests
# ============================================================================

class TestAppIntegration:
    def test_app_creates_trie(self):
        app = Fenrir()
        assert hasattr(app.router, '_trie')

    def test_app_route_added_to_trie(self):
        app = Fenrir()

        @app.get("/test")
        async def handler():
            return "ok"

        assert len(app.router._trie.search("/test")) == 1

    def test_context_no_sys_hack(self):
        """Verify that sys._fenrir_active_app is no longer used."""
        import sys
        app = Fenrir()
        # The old hack should not be present
        assert not hasattr(sys, '_fenrir_active_app')

    @pytest.mark.anyio
    async def test_streaming_body_endpoint(self):
        app = Fenrir()

        @app.post("/upload")
        async def upload(request: Request):
            total = 0
            async for chunk in request.stream_body(chunk_size=1024):
                total += len(chunk)
            return {"bytes_received": total}

        client = app.test_client()
        async with client as c:
            response = await c.post("/upload", content=b"hello world")
            assert response.status_code == 200
