"""Targeted coverage tests for fenrir._app_dispatch."""
import sys

import pytest

from fenrir import Fenrir
from fenrir.response import Response


class FakeReq:
    def __init__(self, headers=None, scope=None):
        self.method = "GET"
        self.path = "/x"
        self.query_string = "a=1"
        self.headers = headers or {}
        self.scope = scope or {}


class TestDispatchMounts:
    @pytest.mark.anyio
    async def test_wsgi_mount(self):
        app = Fenrir()

        def wsgi_app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"wsgi-ok"]

        app.mount_wsgi("/legacy", wsgi_app)
        async with app.test_client() as client:
            resp = await client.get("/legacy/path")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_asgi_mount(self):
        app = Fenrir()

        async def sub_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"sub-ok"})

        app.mount("/sub", sub_app)
        async with app.test_client() as client:
            resp = await client.get("/sub/x")
            assert resp.status_code == 200
            assert resp.content == b"sub-ok"

    @pytest.mark.anyio
    async def test_mount_exact_path(self):
        app = Fenrir()

        async def sub_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        app.mount("/sub", sub_app)
        async with app.test_client() as client:
            resp = await client.get("/sub")
            assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_mount_no_match(self):
        app = Fenrir()

        async def sub_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        app.mount("/sub", sub_app)

        @app.get("/other")
        async def other():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/other")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_wsgi_mount_no_match(self):
        app = Fenrir()

        def wsgi_app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"legacy"]

        app.mount_wsgi("/old", wsgi_app)

        @app.get("/modern")
        async def modern():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/modern")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_no_session_interface(self):
        app = Fenrir()
        app.session_interface = None

        @app.get("/nosess")
        async def nosess():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/nosess")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_non_http_scope(self):
        app = Fenrir()
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request"}

        await app._dispatch({"type": "weird"}, receive, send)
        assert sent == []

    @pytest.mark.anyio
    async def test_dispatch_without_ctx(self):
        app = Fenrir()

        @app.get("/hello")
        async def hello():
            return {"ok": True}

        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request"}

        scope = {"type": "http", "method": "GET", "path": "/hello",
                 "headers": [], "query_string": b""}
        await app._dispatch(scope, receive, send)
        assert any(m["type"] == "http.response.start" and m["status"] == 200 for m in sent)


class TestDispatchResponseModel:
    @pytest.mark.anyio
    async def test_response_model_pydantic(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            count: int

        app = Fenrir()

        @app.get("/pmodel", response_model=Item)
        async def pmodel():
            return {"name": "x", "count": 1}

        async with app.test_client() as client:
            resp = await client.get("/pmodel")
            assert resp.json()["name"] == "x"

    @pytest.mark.anyio
    async def test_response_model_pydantic_instance(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            count: int = 0

        app = Fenrir()

        @app.get("/pinst", response_model=Item)
        async def pinst():
            return Item(name="y", count=2)

        async with app.test_client() as client:
            resp = await client.get("/pinst")
            assert resp.json()["count"] == 2

    @pytest.mark.anyio
    async def test_response_model_exclude(self):
        app = Fenrir()

        @app.get("/excl", response_model=dict, response_model_exclude={"secret"})
        async def excl():
            return {"name": "z", "secret": "hide"}

        async with app.test_client() as client:
            resp = await client.get("/excl")
            assert "secret" not in resp.json()

    @pytest.mark.anyio
    async def test_response_model_include_defaults(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            count: int = 7

        app = Fenrir()

        @app.get("/inc", response_model=Item,
                 response_model_include={"name"},
                 response_model_exclude_defaults=True)
        async def inc():
            return Item(name="q", count=7)

        async with app.test_client() as client:
            resp = await client.get("/inc")
            assert "count" not in resp.json()

    @pytest.mark.anyio
    async def test_response_model_plain_content(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            count: int = 0

        app = Fenrir()

        @app.get("/plain", response_model=Item)
        async def plain():
            return "not-a-dict"

        async with app.test_client() as client:
            resp = await client.get("/plain")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_response_model_dict(self):
        app = Fenrir()

        @app.get("/model")
        async def model():
            return {"name": "fenrir", "count": 3}

        async with app.test_client() as client:
            resp = await client.get("/model")
            assert resp.status_code == 200
            assert resp.json()["name"] == "fenrir"

    @pytest.mark.anyio
    async def test_response_models_by_status(self):
        app = Fenrir()

        @app.get("/multi", response_models={200: dict})
        async def multi():
            return {"x": 1}

        async with app.test_client() as client:
            resp = await client.get("/multi")
            assert resp.json() == {"x": 1}

    @pytest.mark.anyio
    async def test_response_model_apply_to_response(self):
        from fenrir.response import JSONResponse

        app = Fenrir()

        @app.get("/respmodel", response_model=dict)
        async def respmodel():
            return JSONResponse({"y": 2}, status=201)

        async with app.test_client() as client:
            resp = await client.get("/respmodel")
            assert resp.status_code == 201
            assert resp.json()["y"] == 2

    @pytest.mark.anyio
    async def test_response_model_tuple_content(self):
        app = Fenrir()

        @app.get("/tuple", response_model=dict)
        async def tuple_content():
            return ({"z": 3}, 202)

        async with app.test_client() as client:
            resp = await client.get("/tuple")
            assert resp.status_code == 202
            assert resp.json()["z"] == 3


class TestDispatchCoerce:
    @pytest.mark.anyio
    async def test_coerce_bytes(self):
        app = Fenrir()

        @app.get("/bytes")
        async def bytes_content():
            return b"raw-bytes"

        async with app.test_client() as client:
            resp = await client.get("/bytes")
            assert resp.content == b"raw-bytes"

    @pytest.mark.anyio
    async def test_coerce_other(self):
        app = Fenrir()

        class Custom:
            def __str__(self):
                return "custom-str"

        @app.get("/custom")
        async def custom():
            return Custom()

        async with app.test_client() as client:
            resp = await client.get("/custom")
            assert "custom-str" in resp.text

    @pytest.mark.anyio
    async def test_coerce_tuple_3(self):
        app = Fenrir()
        app._coerce_response(("body", 201, {"X-Custom": "1"}))
        app._coerce_response(("body", 200))
        app._coerce_response((1, 2, 3, 4))


class TestDispatchFalcon:
    @pytest.mark.anyio
    async def test_falcon_sync_before_hook(self):
        from fenrir import falcon

        order = []

        def before_hook(req, resp, resource, params):
            order.append("before")

        class Resource:
            @falcon.before(before_hook)
            async def on_get(self, req, resp):
                resp.media = {"ok": True}

        app = Fenrir()
        app.add_route("/fsync", Resource())
        async with app.test_client() as client:
            resp = await client.get("/fsync")
            assert resp.status_code == 200
        assert order == ["before"]

    @pytest.mark.anyio
    async def test_falcon_resource_hooks(self):
        from fenrir import falcon

        order = []

        async def before_hook(req, resp, resource, params):
            order.append("before")

        async def after_hook(req, resp, resource, params):
            order.append("after")

        class Resource:
            @falcon.before(before_hook)
            @falcon.after(after_hook)
            async def on_get(self, req, resp):
                order.append("handler")
                resp.media = {"ok": True}

        app = Fenrir()
        app.add_route("/falcon", Resource())
        async with app.test_client() as client:
            resp = await client.get("/falcon")
            assert resp.status_code == 200
        assert order == ["before", "handler", "after"]


class TestDispatchExceptionHandling:
    @pytest.mark.anyio
    async def test_status_exception_handler_error(self):
        from fenrir.exceptions import HTTPInternalServerError

        app = Fenrir()

        @app.exception(500)
        async def handler(req, exc):
            raise RuntimeError("inner failure")

        @app.get("/boom")
        async def boom():
            raise HTTPInternalServerError("boom")

        async with app.test_client() as client:
            resp = await client.get("/boom")
            assert resp.status_code == 500

    @pytest.mark.anyio
    async def test_class_exception_handler(self):
        app = Fenrir()

        class CustomError(Exception):
            pass

        @app.exception(CustomError)
        async def handler(req, exc):
            return {"handled": True}

        @app.get("/customerr")
        async def customerr():
            raise CustomError("custom")

        async with app.test_client() as client:
            resp = await client.get("/customerr")
            assert resp.status_code == 200
            assert resp.json()["handled"] is True

    @pytest.mark.anyio
    async def test_class_handler_failure_falls_back(self):
        app = Fenrir()

        class E2(Exception):
            pass

        @app.exception(E2)
        async def handler(req, exc):
            raise ValueError("broken")

        @app.get("/e2")
        async def e2():
            raise E2("x")

        async with app.test_client() as client:
            resp = await client.get("/e2")
            assert resp.status_code == 500

    @pytest.mark.anyio
    async def test_class_handler_no_match(self):
        app = Fenrir()

        class Never(Exception):
            pass

        @app.exception(Never)
        async def handler(req, exc):
            return "no"

        @app.get("/nm")
        async def nm():
            raise RuntimeError("x")

        async with app.test_client() as client:
            resp = await client.get("/nm")
            assert resp.status_code == 500

    @pytest.mark.anyio
    async def test_http_exception_default(self):
        from fenrir.exceptions import HTTPNotFound

        app = Fenrir()

        @app.get("/nf")
        async def nf():
            raise HTTPNotFound("nope")

        async with app.test_client() as client:
            resp = await client.get("/nf")
            assert resp.status_code == 404


class TestDispatchStreaming:
    @pytest.mark.anyio
    async def test_streaming_response(self):
        from fenrir.response import StreamingResponse

        app = Fenrir()

        async def gen():
            yield b"chunk1"
            yield b"chunk2"

        @app.get("/stream")
        async def stream():
            return StreamingResponse(gen())

        async with app.test_client() as client:
            resp = await client.get("/stream")
            assert resp.status_code == 200
            assert resp.content == b"chunk1chunk2"

    @pytest.mark.anyio
    async def test_streaming_error(self):
        from fenrir.response import StreamingResponse

        app = Fenrir()

        async def bad_gen():
            yield b"x"
            raise RuntimeError("stream broke")

        @app.get("/streambad")
        async def streambad():
            return StreamingResponse(bad_gen())

        async with app.test_client() as client:
            resp = await client.get("/streambad")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_head_no_body(self):
        app = Fenrir()

        @app.get("/head")
        async def head_route():
            return "hello"

        async with app.test_client() as client:
            resp = await client.head("/head")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_head_streaming(self):
        from fenrir.response import StreamingResponse

        app = Fenrir()

        async def gen():
            yield b"data"

        @app.get("/hstream")
        async def hstream():
            return StreamingResponse(gen())

        async with app.test_client() as client:
            resp = await client.head("/hstream")
            assert resp.status_code == 200


class TestDispatchRunHandler:
    @pytest.mark.anyio
    async def test_run_handler_truncates_args(self):
        app = Fenrir()
        seen = []

        def positional_only(a, b, /):
            seen.append((a, b))

        await app._run_handler(positional_only, 1, 2, 3)
        assert seen == [(1, 2)]

        def varargs(*args):
            seen.append(("var", len(args)))

        await app._run_handler(varargs, 1, 2, 3)
        assert seen[-1] == ("var", 3)

    @pytest.mark.anyio
    async def test_run_handler_sig_failure(self, monkeypatch):
        app = Fenrir()
        calls = []

        def target(*a, **k):
            calls.append(1)

        def broken_sig(func):
            raise ValueError("no sig")

        import fenrir._app_dispatch as d
        monkeypatch.setattr(d, "_get_cached_signature", broken_sig)
        await app._run_handler(target, 1, 2)
        assert calls == [1]

    @pytest.mark.anyio
    async def test_run_handler_no_args(self):
        app = Fenrir()
        seen = []

        async def target():
            seen.append(1)

        await app._run_handler(target)
        assert seen == [1]

    @pytest.mark.anyio
    async def test_run_handler_keyword_only(self):
        app = Fenrir()
        seen = []

        def target(a, **kw):
            seen.append((a, kw))

        await app._run_handler(target, 1, 2, 3)
        assert seen == [(1, {})]

    @pytest.mark.anyio
    async def test_run_handler_sync_is_async_false(self):
        app = Fenrir()
        seen = []

        def target():
            seen.append(1)

        target._is_async = False
        await app._run_handler(target)
        assert seen == [1]


class TestDispatchBackgroundAndCleanup:
    @pytest.mark.anyio
    async def test_background_tasks(self):
        from fenrir.background import BackgroundTasks

        app = Fenrir()
        ran = []

        @app.get("/bg")
        async def bg(tasks: BackgroundTasks):
            tasks.add_task(ran.append, "done")
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/bg")
            assert resp.status_code == 200
        assert ran == ["done"]

    @pytest.mark.anyio
    async def test_yield_cleanup(self):
        app = Fenrir()
        cleaned = []

        @app.get("/yield")
        async def yield_route():
            return {"dep": "value"}

        async with app.test_client() as client:
            resp = await client.get("/yield")
            assert resp.status_code == 200

        from fenrir.dependencies import Depends
        calls = []

        async def dep():
            yield "v"
            calls.append("cleanup")

        app2 = Fenrir()

        @app2.get("/yd")
        async def yd(x=Depends(dep)):
            return {"x": x}

        async with app2.test_client() as client:
            resp = await client.get("/yd")
            assert resp.json() == {"x": "v"}
        assert calls == ["cleanup"]

    @pytest.mark.anyio
    async def test_yield_cleanup_sync_gen(self):
        from fenrir.dependencies import Depends

        app = Fenrir()
        calls = []

        def dep():
            yield "v"
            calls.append("sync-cleanup")

        @app.get("/ysync")
        async def ysync(x=Depends(dep)):
            return {"x": x}

        async with app.test_client() as client:
            resp = await client.get("/ysync")
            assert resp.json() == {"x": "v"}
        assert calls == ["sync-cleanup"]

    @pytest.mark.anyio
    async def test_cleanup_error(self):
        app = Fenrir()

        async def dep():
            yield "v"
            raise RuntimeError("cleanup boom")

        from fenrir.dependencies import Depends

        @app.get("/yerr")
        async def yerr(x=Depends(dep)):
            return {"x": x}

        async with app.test_client() as client:
            resp = await client.get("/yerr")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_cleanup_manual_variants(self):
        app = Fenrir()
        cleaned = []

        def cleanup_returning_coro():
            async def inner():
                cleaned.append("coro")
            return inner()

        @app.middleware("request")
        async def mw(req):
            req._yield_cleanups = [object(), cleanup_returning_coro]

        @app.get("/mcv")
        async def mcv():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/mcv")
            assert resp.status_code == 200
        assert cleaned == ["coro"]


class TestDispatchSession:
    @pytest.mark.anyio
    async def test_session_open_failure(self):
        app = Fenrir()

        class BadSession:
            def open_session(self, app, req):
                raise RuntimeError("session broken")

        app.session_interface = BadSession()
        async with app.test_client() as client:
            resp = await client.get("/")
            assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_session_save_failure(self):
        app = Fenrir()
        app.config["SECRET_KEY"] = "k"

        class SaveFailSession:
            def open_session(self, app, req):
                return {}

            def save_session(self, app, session, response):
                raise RuntimeError("save broken")

        app.session_interface = SaveFailSession()

        @app.get("/ss")
        async def ss():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/ss")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_session_save_failure_exception_path(self):
        app = Fenrir()

        class SaveFailSession:
            def open_session(self, app, req):
                return {}

            def save_session(self, app, session, response):
                raise RuntimeError("save broken")

        app.session_interface = SaveFailSession()

        @app.get("/sse")
        async def sse():
            raise RuntimeError("boom")

        async with app.test_client() as client:
            resp = await client.get("/sse")
            assert resp.status_code == 500


class TestDispatchListeners:
    @pytest.mark.anyio
    async def test_trigger_listeners_eviction(self, monkeypatch):
        import fenrir._app_dispatch as d

        d._listener_is_async_cache.clear()
        app = Fenrir()
        called = []

        async def listener(a):
            called.append("async")

        def sync_listener(a):
            called.append("sync")

        # pre-fill cache to force eviction
        for i in range(d._LISTENER_CACHE_MAX):
            d._listener_is_async_cache[10_000_000 + i] = False
        app.listeners["x"] = [listener, sync_listener]
        await app._trigger_listeners("x")
        assert called == ["async", "sync"]

    @pytest.mark.anyio
    async def test_trigger_listeners_cached(self):
        import fenrir._app_dispatch as d

        app = Fenrir()
        called = []

        def sync_listener(a):
            called.append(1)

        app.listeners["cached"] = [sync_listener]
        cache_key = d._make_listener_cache_key(sync_listener)
        d._listener_is_async_cache[cache_key] = False
        await app._trigger_listeners("cached")
        assert called == [1]

    @pytest.mark.anyio
    async def test_trigger_listeners_cache_not_full(self):
        import fenrir._app_dispatch as d

        d._listener_is_async_cache.clear()
        app = Fenrir()
        called = []

        def sync_listener(a):
            called.append(1)

        app.listeners["fresh"] = [sync_listener]
        await app._trigger_listeners("fresh")
        assert called == [1]

    @pytest.mark.anyio
    async def test_lifespan(self):
        app = Fenrir()
        events = []

        @app.listener("before_server_start")
        def on_start(app):
            events.append("start")

        @app.listener("before_server_stop")
        def on_stop(app):
            events.append("stop")

        sent = []

        async def send(msg):
            sent.append(msg)

        messages = iter([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        async def receive():
            return next(messages)

        await app({"type": "lifespan", "headers": [], "path": "/"}, receive, send)
        assert events == ["start", "stop"]
        assert sent[-1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.anyio
    async def test_lifespan_startup_failure(self):
        app = Fenrir()

        @app.listener("before_server_start")
        def on_start(app):
            raise RuntimeError("startup failed")

        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "lifespan.startup"}

        await app({"type": "lifespan", "headers": [], "path": "/"}, receive, send)
        assert sent[0]["type"] == "lifespan.startup.failed"

    @pytest.mark.anyio
    async def test_lifespan_unknown_message(self):
        app = Fenrir()
        sent = []

        async def send(msg):
            sent.append(msg)

        messages = iter([
            {"type": "lifespan.startup"},
            {"type": "mystery"},
            {"type": "lifespan.shutdown"},
        ])

        async def receive():
            return next(messages)

        await app({"type": "lifespan", "headers": [], "path": "/"}, receive, send)
        assert sent[0]["type"] == "lifespan.startup.complete"
        assert sent[-1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.anyio
    async def test_lifespan_shutdown_failure(self):
        app = Fenrir()

        @app.listener("after_server_stop")
        def on_stop(app):
            raise RuntimeError("shutdown failed")

        sent = []

        async def send(msg):
            sent.append(msg)

        messages = iter([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        async def receive():
            return next(messages)

        await app({"type": "lifespan", "headers": [], "path": "/"}, receive, send)
        assert sent[-1]["type"] == "lifespan.shutdown.failed"


class TestDispatchWebsocket:
    @pytest.mark.anyio
    async def test_websocket_no_match(self):
        app = Fenrir()
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "websocket.connect"}

        await app._handle_websocket({"type": "websocket", "path": "/nows"}, receive, send)
        assert sent[0]["code"] == 1008

    @pytest.mark.anyio
    async def test_websocket_disconnect(self):
        app = Fenrir()

        @app.websocket("/ws")
        async def ws(ws):
            await ws.accept()
            raise RuntimeError("boom")

        sent = []

        async def send(msg):
            sent.append(msg)

        from fenrir.websocket import WebSocketDisconnect

        async def receive():
            raise WebSocketDisconnect()

        await app._handle_websocket({"type": "websocket", "path": "/ws"}, receive, send)

    @pytest.mark.anyio
    async def test_websocket_error(self):
        app = Fenrir()

        @app.websocket("/wserr")
        async def ws(ws):
            await ws.accept()
            raise RuntimeError("boom")

        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "websocket.receive", "text": ""}

        await app._handle_websocket({"type": "websocket", "path": "/wserr"}, receive, send)
        assert any(m.get("code") == 1011 for m in sent)

    @pytest.mark.anyio
    async def test_websocket_disconnected_on_error(self):
        app = Fenrir()

        @app.websocket("/wsdisp")
        async def ws(ws):
            await ws.accept()
            ws.client_state = "DISCONNECTED"
            raise RuntimeError("gone")

        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "websocket.connect"}

        await app._handle_websocket({"type": "websocket", "path": "/wsdisp"}, receive, send)
        assert not any(m.get("code") == 1011 for m in sent)


class TestDispatchCall:
    @pytest.mark.anyio
    async def test_call_exception_http(self):
        app = Fenrir()

        async def broken(scope, receive, send):
            raise RuntimeError("outer boom")

        app._asgi_app = broken
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request"}

        await app({"type": "http", "method": "GET", "path": "/x",
                   "headers": [], "query_string": b""}, receive, send)
        assert any(m["type"] == "http.response.start" and m["status"] == 500 for m in sent)

    @pytest.mark.anyio
    async def test_call_security_rebuild(self):
        app = Fenrir()
        app.config["MAX_CONTENT_LENGTH"] = 1000

        @app.get("/s")
        async def s():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/s")
            assert resp.status_code == 200
            app._config_security_applied = False
            resp = await client.get("/s")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_call_non_http_exception(self):
        app = Fenrir()

        async def broken(scope, receive, send):
            raise RuntimeError("non-http boom")

        app._asgi_app = broken
        with pytest.raises(RuntimeError):
            await app({"type": "weird"}, None, None)

    @pytest.mark.anyio
    async def test_middleware_stack_built_once(self):
        app = Fenrir()
        app._asgi_middlewares = [(lambda a: a, {})]
        app._asgi_app = None

        @app.get("/m")
        async def m():
            return "ok"

        async with app.test_client() as client:
            resp = await client.get("/m")
            assert resp.status_code == 200


class TestDispatchMiddlewarePaths:
    @pytest.mark.anyio
    async def test_bp_request_middleware_stops(self):
        from fenrir.app import Blueprint

        bp = Blueprint("bp")

        @bp.middleware("request")
        async def mw(req):
            return Response("stopped", status=299)

        @bp.get("/bpstop")
        async def route():
            return "never"

        app = Fenrir()
        app.register_blueprint(bp)
        async with app.test_client() as client:
            resp = await client.get("/bpstop")
            assert resp.status_code == 299

    @pytest.mark.anyio
    async def test_response_middleware_changes(self):
        app = Fenrir()

        @app.middleware("response")
        async def mw(req, resp):
            return Response("wrapped", status=222)

        @app.get("/rmw")
        async def route():
            return "plain"

        async with app.test_client() as client:
            resp = await client.get("/rmw")
            assert resp.status_code == 222

    @pytest.mark.anyio
    async def test_request_middleware_returns_response(self):
        app = Fenrir()

        @app.middleware("request")
        async def mw(req):
            return Response("early", status=201)

        @app.get("/rm")
        async def route():
            return "never"

        async with app.test_client() as client:
            resp = await client.get("/rm")
            assert resp.status_code == 201


class TestDebugPage:
    def test_detail_non_str_no_traceback(self):
        app = Fenrir()

        class D(Exception):
            detail = {"a": 1}

        exc = D("x")
        resp = app._render_debug_page(FakeReq(), exc, D, None)
        assert resp._status == 500

    def test_header_fallbacks(self):
        app = Fenrir()
        exc = ValueError("boom")
        resp = app._render_debug_page(
            FakeReq(headers={"x-forwarded-for": "10.0.0.1, 10.0.0.2"}), exc, ValueError, None)
        assert resp._status == 500
        resp = app._render_debug_page(
            FakeReq(headers={"x-real-ip": "10.1.1.1"}), exc, ValueError, None)
        assert resp._status == 500
        resp = app._render_debug_page(
            FakeReq(headers={"host": "example.com:8080"}), exc, ValueError, None)
        assert resp._status == 500

    def test_frame_no_source(self):
        app = Fenrir()
        long_path = "/tmp/opencode/" + "a" * 120 + ".py"
        code = compile(
            "def inner():\n    raise ValueError('boom')\ninner()",
            long_path,
            "exec",
        )
        try:
            exec(code, {})
        except ValueError as e:
            _, _, tb = sys.exc_info()
            resp = app._render_debug_page(FakeReq(), e, ValueError, tb)
        assert resp._status == 500
