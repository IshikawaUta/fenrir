"""Tests for fenrir.compat — WsgiToAsgi, to_thread, install_*_compat."""
import sys

import pytest

from fenrir.compat import WsgiToAsgi, install_bottle_compat, install_falcon_compat, install_sanic_compat, to_thread


class TestToThread:
    @pytest.mark.anyio
    async def test_to_thread_sync_func(self):
        def add(a, b):
            return a + b
        result = await to_thread(add, 2, 3)
        assert result == 5

    @pytest.mark.anyio
    async def test_to_thread_with_kwargs(self):
        def greet(name="world"):
            return f"hello {name}"
        result = await to_thread(greet, name="fenrir")
        assert result == "hello fenrir"

    @pytest.mark.anyio
    async def test_to_thread_exception_propagates(self):
        def fail():
            raise ValueError("oops")
        with pytest.raises(ValueError, match="oops"):
            await to_thread(fail)


class TestWsgiToAsgi:
    def _make_wsgi_app(self):
        def app(environ, start_response):
            path = environ.get("PATH_INFO", "/")
            method = environ.get("REQUEST_METHOD", "GET")
            body = environ.get("wsgi.input", b"")
            if hasattr(body, "read"):
                body = body.read()
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [f"{method} {path} {len(body)}".encode()]
        return app

    def test_init(self):
        wsgi_app = self._make_wsgi_app()
        asgi = WsgiToAsgi(wsgi_app)
        assert asgi.wsgi_app is wsgi_app

    @pytest.mark.anyio
    async def test_wsgi_generator_with_close(self):
        def gen_app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])

            def gen():
                yield b"chunk1"
                yield b"chunk2"

            return gen()

        asgi = WsgiToAsgi(gen_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/gen",
            "query_string": b"",
            "headers": [(b"host", b"localhost"), (b"content-type", b"text/plain")],
        }
        responses = []

        async def send(msg):
            responses.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        await asgi(scope, receive, send)
        body_msg = [r for r in responses if r["type"] == "http.response.body"][0]
        assert body_msg["body"] == b"chunk1chunk2"
        start_msg = [r for r in responses if r["type"] == "http.response.start"][0]
        assert start_msg["status"] == 200

    @pytest.mark.anyio
    async def test_basic_http_request(self):
        wsgi_app = self._make_wsgi_app()
        asgi = WsgiToAsgi(wsgi_app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"host", b"localhost")],
        }

        responses = []

        async def send(msg):
            responses.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        await asgi(scope, receive, send)

        # Should have sent response headers and body
        types = [r["type"] for r in responses]
        assert "http.response.start" in types
        assert "http.response.body" in types

    @pytest.mark.anyio
    async def test_request_with_body(self):
        wsgi_app = self._make_wsgi_app()
        asgi = WsgiToAsgi(wsgi_app)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/data",
            "query_string": b"",
            "headers": [(b"host", b"localhost"), (b"content-length", b"5")],
        }

        responses = []

        async def send(msg):
            responses.append(msg)

        async def receive():
            return {"type": "http.request", "body": b"hello", "more_body": False}

        await asgi(scope, receive, send)
        assert len(responses) >= 2

    @pytest.mark.anyio
    async def test_request_with_query_string(self):
        wsgi_app = self._make_wsgi_app()
        asgi = WsgiToAsgi(wsgi_app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "query_string": b"q=test",
            "headers": [(b"host", b"localhost")],
        }

        responses = []

        async def send(msg):
            responses.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        await asgi(scope, receive, send)
        assert len(responses) >= 2

    @pytest.mark.anyio
    async def test_websocket_scope_returns_403(self):
        wsgi_app = self._make_wsgi_app()
        asgi = WsgiToAsgi(wsgi_app)

        scope = {"type": "websocket"}
        responses = []

        async def send(msg):
            responses.append(msg)

        async def receive():
            return {"type": "websocket.connect"}

        await asgi(scope, receive, send)
        # Should NOT send anything for websocket scope (just return None)
        assert responses == []


class TestInstallBottleCompat:
    def test_install_bottle(self):
        install_bottle_compat()
        assert "bottle" in sys.modules

    def test_install_bottle_after_removal(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "bottle", raising=False)
        install_bottle_compat()
        import bottle
        assert hasattr(bottle, "Bottle")

    def test_bottle_is_fenrir_bottle(self):
        install_bottle_compat()
        import bottle
        assert hasattr(bottle, "Bottle")


class TestInstallFalconCompat:
    def test_install_falcon(self):
        install_falcon_compat()
        assert "falcon" in sys.modules

    def test_install_falcon_after_removal(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "falcon", raising=False)
        install_falcon_compat()
        import falcon
        assert hasattr(falcon, "HTTPError")


class TestInstallSanicCompat:
    def test_install_sanic(self):
        install_sanic_compat()
        assert "sanic" in sys.modules

    def test_install_sanic_after_removal(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "sanic", raising=False)
        install_sanic_compat()
        import sanic
        assert hasattr(sanic, "response")


def test_shutdown_thread_pool(monkeypatch):
    import fenrir.compat as compat

    class FakePool:
        def __init__(self):
            self.shutdown_called = False

        def shutdown(self, wait=False):
            self.shutdown_called = True

    fake = FakePool()
    monkeypatch.setattr(compat, "_thread_pool", fake)
    compat._shutdown_thread_pool()
    assert fake.shutdown_called
