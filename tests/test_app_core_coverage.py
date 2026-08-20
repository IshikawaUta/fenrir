"""Targeted coverage tests for fenrir._app_core internals."""
import pytest

from fenrir import Fenrir
from fenrir.routing import APIRouter


class TestBlueprint:
    def test_methods(self):
        from fenrir._app_core import Blueprint

        bp = Blueprint("t", "/bp")
        calls = []

        def handler():
            return "ok"

        bp.put("/put")(handler)
        bp.delete("/del")(handler)
        bp.patch("/patch")(handler)
        bp.post("/post")(handler)
        bp.get("/get")(handler)
        assert len(bp.routes) == 5

        bp.websocket("/ws")(handler)
        assert len(bp.websocket_routes) == 1

    @pytest.mark.anyio
    async def test_route_without_leading_slash(self):
        from fenrir._app_core import Blueprint
        from fenrir.testing import TestClient

        app = Fenrir()
        bp = Blueprint("noslash", url_prefix="/pre")

        @bp.route("no-slash", ["GET"])
        async def h():
            return {"ok": True}

        @bp.websocket("ws-no-slash")
        async def ws(ws):
            pass

        @bp.websocket("/ws-slash")
        async def ws2(ws):
            pass

        app.register_blueprint(bp)
        client = TestClient(app)
        resp = await client.get("/pre/no-slash")
        assert resp.status_code == 200

    def test_teardown_request_registration(self):
        from fenrir._app_core import Blueprint

        bp = Blueprint("t2")
        log = []

        @bp.teardown_request
        def td(exc):
            log.append(exc)

        assert bp.teardown_request_funcs == [td]


class TestRootPath:
    def test_import_fail_fallback(self, tmp_path):
        from fenrir import Fenrir

        app = Fenrir()
        ns = {"__name__": "nonexistent.module.xyz", "app": app}
        exec("app._init_core()", ns)
        assert app.root_path

    def test_no_caller_module(self):
        from fenrir import Fenrir

        app = Fenrir()
        ns = {"__name__": None, "app": app}
        exec("app._init_core()", ns)
        assert app.root_path

    def test_root_path_provided(self, tmp_path):
        from fenrir import Fenrir

        app = Fenrir(root_path="/tmp/x", instance_path="/abs/y")
        assert app.root_path == "/tmp/x"
        assert app.instance_path == "/abs/y"

    def test_renderer_provided(self):
        from fenrir import Fenrir

        renderer = object()
        app = Fenrir(renderer=renderer)
        assert app.renderer is renderer


class TestDocs:
    def test_docs_env_enabled(self, monkeypatch):
        monkeypatch.setenv("FENRIR_DOCS_ENABLED", "on")
        app = Fenrir()
        assert app.openapi_url == "/openapi.json"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"

    @pytest.mark.anyio
    async def test_docs_endpoints(self, monkeypatch):
        from fenrir.testing import TestClient

        monkeypatch.setenv("FENRIR_DOCS_ENABLED", "1")
        app = Fenrir()
        client = TestClient(app)
        resp = await client.get("/docs")
        assert resp.status_code == 200
        resp = await client.get("/redoc")
        assert resp.status_code == 200
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200

    def test_docs_enabled_param(self):
        app = Fenrir(docs_enabled=True)
        assert app.openapi_url == "/openapi.json"
        app2 = Fenrir(docs_enabled=False)
        assert app2.openapi_url is None
        assert app2.docs_url is None
        assert app2.redoc_url is None


class TestMisc:
    @pytest.mark.anyio
    async def test_include_router(self):
        from fenrir.testing import TestClient

        app = Fenrir()
        router = APIRouter()

        @router.get("/ping")
        async def ping():
            return {"pong": True}

        app.include_router(router, prefix="/api")
        client = TestClient(app)
        resp = await client.get("/api/ping")
        assert resp.status_code == 200
        assert resp.json()["pong"] is True

    def test_config_security_middleware_idempotent(self):
        app = Fenrir()
        app.config["MAX_CONTENT_LENGTH"] = 1024
        app.config["RATE_LIMIT_MAX_REQUESTS"] = 100
        assert app._apply_config_security_middleware() is True
        assert app._apply_config_security_middleware() is False
        assert any(
            cls.__name__ in ("BodyLimitMiddleware", "RateLimitMiddleware")
            for cls, _ in app._asgi_middlewares
        )

    def test_mount_validation(self):
        app = Fenrir()
        with pytest.raises(ValueError):
            app.mount("static", lambda: None)
        with pytest.raises(ValueError):
            app.mount("/static", "not-callable")

    def test_middleware_invalid_type(self):
        app = Fenrir()
        with pytest.raises(ValueError):
            app.middleware("invalid")(lambda req: None)

    def test_listener_unknown_event(self):
        app = Fenrir()

        def handler():
            pass

        assert app.listener("nonexistent")(handler) is handler

    def test_websocket_decorator(self):
        app = Fenrir()

        @app.websocket("/ws")
        async def ws(ws):
            pass

        @app.websocket("/ws2", timeout=5)
        async def ws2(ws):
            pass

        assert len(app.router.websocket_routes) == 2

    def test_mount_ok(self):
        app = Fenrir()

        async def sub(scope, receive, send):
            pass

        app.mount("/static", sub)
        assert app._asgi_mounts[0][0] == "/static"

    def test_before_after_request(self):
        app = Fenrir()

        @app.before_request
        async def before(req):
            pass

        @app.after_request
        async def after(req, resp):
            pass

        assert app.middlewares["request"][-1] is before
        assert app.middlewares["response"][-1] is after

    def test_register_error_handler_invalid(self):
        app = Fenrir()
        with pytest.raises(ValueError):
            app.register_error_handler("invalid", lambda e: None)

    @pytest.mark.anyio
    async def test_add_task_coroutine_object(self):
        app = Fenrir()

        async def af():
            return 1

        coro = af()
        task = app.add_task(coro)
        assert await task == 1

    @pytest.mark.anyio
    async def test_add_task_is_async_attr(self):
        app = Fenrir()

        async def af():
            return 2

        class FakeCoro:
            _is_async = True

            def __call__(self):
                return af()

        task = app.add_task(FakeCoro())
        assert await task == 2


class TestTeardown:
    def test_teardown_outside_request(self):
        app = Fenrir()
        log = []

        @app.teardown_request
        def td(exc):
            log.append(exc)

        app.do_teardown_request()
        assert log == [None]

    @pytest.mark.anyio
    async def test_teardown_dedup(self):
        from fenrir._app_core import Blueprint
        from fenrir.testing import TestClient

        app = Fenrir()
        log = []
        bp = Blueprint("bp", "/bp")

        @bp.route("/h", ["GET"])
        async def h():
            return {"ok": True}

        def td(exc):
            log.append(exc)

        bp.teardown_request(td)
        bp.teardown_request(td)
        app.teardown_request(td)
        app.register_blueprint(bp)

        client = TestClient(app)
        resp = await client.get("/bp/h")
        assert resp.status_code == 200
        assert len(log) == 1

    def test_do_teardown_appcontext(self):
        app = Fenrir()
        log = []

        @app.teardown_appcontext
        def td(exc):
            log.append(exc)

        app.do_teardown_appcontext()
        assert log == [None]


class TestContextHelpers:
    def test_test_request_context_no_session(self):
        app = Fenrir()
        app.session_interface = None
        with app.test_request_context():
            pass

    def test_app_context(self):
        from fenrir.context import AppContext

        app = Fenrir()
        with app.app_context() as ctx:
            assert isinstance(ctx, AppContext)
