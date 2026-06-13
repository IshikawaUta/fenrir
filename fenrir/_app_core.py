"""Fenrir application core — init, routing decorators, middleware, blueprints."""
import asyncio
import inspect
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Type, Union

from fenrir.request import Request
from fenrir.response import HTMLResponse
from fenrir.routing import Router, Route
from fenrir.openapi import get_swagger_html, get_redoc_html

logger = logging.getLogger("fenrir")


class Blueprint:
    def __init__(self, name: str, url_prefix: str = ""):
        self.name = name
        self.url_prefix = url_prefix.rstrip("/")
        self.routes: List[tuple] = []
        self.websocket_routes: List[tuple] = []
        self.middlewares: Dict[str, List[Callable]] = {"request": [], "response": []}
        self.teardown_request_funcs: List[Callable] = []

    def before_request(self, f: Callable) -> Callable:
        self.middlewares["request"].append(f)
        return f

    def after_request(self, f: Callable) -> Callable:
        self.middlewares["response"].append(f)
        return f

    def teardown_request(self, f: Callable) -> Callable:
        self.teardown_request_funcs.append(f)
        return f

    def route(self, path: str, methods: List[str] = None):
        def decorator(handler):
            self.add_route(path, handler, methods)
            return handler
        return decorator

    def websocket(self, path: str):
        def decorator(handler):
            self.websocket_routes.append((path, handler))
            return handler
        return decorator

    def get(self, path: str):
        return self.route(path, ["GET"])

    def post(self, path: str):
        return self.route(path, ["POST"])

    def put(self, path: str):
        return self.route(path, ["PUT"])

    def delete(self, path: str):
        return self.route(path, ["DELETE"])

    def patch(self, path: str):
        return self.route(path, ["PATCH"])

    def add_route(self, path: str, handler: Any, methods: List[str] = None):
        self.routes.append((path, handler, methods))

    def middleware(self, middleware_type: str = "request"):
        def decorator(func):
            if middleware_type in ("request", "response"):
                self.middlewares[middleware_type].append(func)
            return func
        return decorator


class FenrirCoreMixin:
    """Mixin providing __init__, routing decorators, middleware, and blueprint registration."""

    def _init_core(
        self,
        import_name: str = None,
        title: str = "Fenrir API",
        version: str = "3.0.0",
        template_folder: str = "templates",
        renderer: Any = None,
        docs_url: str = "/docs",
        redoc_url: str = "/redoc",
        openapi_url: str = "/openapi.json",
        instance_path: str = None,
        instance_relative_config: bool = False,
        root_path: str = None,
        strict_content_type: bool = False,
        route_class: Optional[Type[Route]] = None,
    ):
        self.title = title
        self.version = version
        self.template_folder = template_folder

        if root_path is None:
            try:
                caller_frame = sys._getframe(1)
                caller_module = caller_frame.f_globals.get("__name__")
                if caller_module:
                    import importlib
                    try:
                        mod = importlib.import_module(caller_module)
                        root_path = os.path.dirname(os.path.abspath(mod.__file__))
                    except Exception:
                        root_path = os.getcwd()
                else:
                    root_path = os.getcwd()
            except Exception:
                root_path = os.getcwd()

        self.root_path = root_path

        if instance_path is None:
            self.instance_path = os.path.join(self.root_path, "instance")
        else:
            self.instance_path = os.path.abspath(instance_path)

        config_root = self.instance_path if instance_relative_config else self.root_path
        from fenrir.config import Config
        self.config = Config(config_root, defaults={
            "ENV": "production",
            "DEBUG": False,
            "TESTING": False,
            "SECRET_KEY": None,
            "SESSION_COOKIE_NAME": "session",
            "SESSION_COOKIE_DOMAIN": None,
            "SESSION_COOKIE_PATH": "/",
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SECURE": True,
            "SESSION_COOKIE_SAMESITE": None,
        })

        from fenrir.sessions import SecureCookieSessionInterface
        self.session_interface = SecureCookieSessionInterface()

        from fenrir.json import DefaultJSONProvider
        self.json = DefaultJSONProvider(self)

        self.teardown_request_funcs: Dict[Optional[str], List[Callable]] = {None: []}
        self.teardown_appcontext_funcs: List[Callable] = []

        if renderer is None:
            from fenrir.templating import Jinja2Renderer
            self.renderer = Jinja2Renderer(template_folder)
        else:
            self.renderer = renderer

        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url

        self.router = Router(route_class=route_class)
        self.middlewares: Dict[str, List[Callable]] = {"request": [], "response": []}
        self._asgi_middlewares: List = []
        self._asgi_app: Any = None
        self._wsgi_mounts: List = []
        self.listeners: Dict[str, List[Callable]] = {
            "before_server_start": [],
            "after_server_start": [],
            "before_server_stop": [],
            "after_server_stop": [],
        }
        self.exception_handlers: Dict[Union[Type[Exception], int], Callable] = {}
        self.blueprints: List[Blueprint] = []
        self._route_blueprints: Dict[Route, Blueprint] = {}
        self.dependency_overrides = {}
        self.strict_content_type = strict_content_type
        self._openapi_schema_cache: Optional[Dict[str, Any]] = None

        # Built-in docs endpoints
        if self.openapi_url:
            @self.get(self.openapi_url)
            async def openapi_endpoint():
                return self.openapi()

        if self.docs_url and self.openapi_url:
            @self.get(self.docs_url)
            async def swagger_ui():
                return HTMLResponse(get_swagger_html(self.openapi_url, f"{self.title} - Swagger UI"))

        if self.redoc_url and self.openapi_url:
            @self.get(self.redoc_url)
            async def redoc_ui():
                return HTMLResponse(get_redoc_html(self.openapi_url, f"{self.title} - ReDoc"))

    # ── Routing decorators ──────────────────────────────────────────────

    def route(self, path: str, methods: List[str] = None, **route_kwargs):
        def decorator(handler):
            self.add_route(path, handler, methods, **route_kwargs)
            return handler
        return decorator

    def websocket(self, path: str, timeout: float = None):
        def decorator(handler):
            self.add_websocket_route(path, handler, ws_timeout=timeout)
            return handler
        return decorator

    def get(self, path: str, **kwargs):
        return self.route(path, ["GET"], **kwargs)

    def post(self, path: str, **kwargs):
        return self.route(path, ["POST"], **kwargs)

    def put(self, path: str, **kwargs):
        return self.route(path, ["PUT"], **kwargs)

    def delete(self, path: str, **kwargs):
        return self.route(path, ["DELETE"], **kwargs)

    def patch(self, path: str, **kwargs):
        return self.route(path, ["PATCH"], **kwargs)

    def add_route(self, path: str, handler: Any, methods: List[str] = None, **route_kwargs):
        self.router.add_route(path, handler, methods, **route_kwargs)
        self._invalidate_openapi_cache()

    def add_websocket_route(self, path: str, handler: Any, ws_timeout: float = None):
        self.router.add_websocket_route(path, handler, ws_timeout=ws_timeout)
        self._invalidate_openapi_cache()

    def include_router(self, router: Router, prefix: str = ""):
        self.router.include_router(router, prefix=prefix)

    # ── Middleware ──────────────────────────────────────────────────────

    def add_middleware(self, middleware_class: Any, **options: Any) -> None:
        self._asgi_middlewares.append((middleware_class, options))
        self._asgi_app = None

    def mount_wsgi(self, path: str, wsgi_app: Any) -> None:
        from fenrir.compat import WsgiToAsgi
        adapter = WsgiToAsgi(wsgi_app)
        prefix = path.rstrip("/")
        self._wsgi_mounts.append((prefix, adapter))

    def middleware(self, middleware_type: str = "request"):
        def decorator(func):
            if middleware_type in ("request", "response"):
                self.middlewares[middleware_type].append(func)
            return func
        return decorator

    def before_request(self, f: Callable) -> Callable:
        self.middlewares["request"].append(f)
        return f

    def after_request(self, f: Callable) -> Callable:
        self.middlewares["response"].append(f)
        return f

    # ── Blueprints ─────────────────────────────────────────────────────

    def register_blueprint(self, blueprint: Blueprint):
        self.blueprints.append(blueprint)
        self.teardown_request_funcs[blueprint.name] = blueprint.teardown_request_funcs
        for path, handler, methods in blueprint.routes:
            full_path = blueprint.url_prefix + path
            self.router.add_route(full_path, handler, methods)
            new_route = self.router.routes[-1]
            self._route_blueprints[new_route] = blueprint
        for path, handler in blueprint.websocket_routes:
            full_path = blueprint.url_prefix + path
            self.router.add_websocket_route(full_path, handler)

    # ── Listeners ──────────────────────────────────────────────────────

    def listener(self, event_name: str):
        def decorator(func):
            if event_name in self.listeners:
                self.listeners[event_name].append(func)
            return func
        return decorator

    def add_task(self, coro: Any) -> asyncio.Task:
        if inspect.iscoroutinefunction(coro):
            coro_obj = coro()
        else:
            coro_obj = coro
        return asyncio.create_task(coro_obj)

    # ── Error handlers ─────────────────────────────────────────────────

    def register_error_handler(self, exc_class_or_code: Union[Type[Exception], int], handler: Callable):
        if isinstance(exc_class_or_code, int):
            self.exception_handlers[exc_class_or_code] = handler
        elif isinstance(exc_class_or_code, type) and issubclass(exc_class_or_code, Exception):
            self.exception_handlers[exc_class_or_code] = handler
        else:
            raise ValueError("Error handler key must be an exception class or HTTP status code.")

    def exception(self, *exceptions: Union[Type[Exception], int]):
        def decorator(func):
            for exc in exceptions:
                self.register_error_handler(exc, func)
            return func
        return decorator

    # ── Teardown ───────────────────────────────────────────────────────

    def teardown_request(self, f: Callable) -> Callable:
        self.teardown_request_funcs[None].append(f)
        return f

    def teardown_appcontext(self, f: Callable) -> Callable:
        self.teardown_appcontext_funcs.append(f)
        return f

    def do_teardown_request(self, exc: Optional[BaseException] = None):
        from fenrir.context import request
        bp_name = None
        try:
            bp_name = getattr(request, "blueprint", None)
        except Exception:
            pass
        seen = set()
        funcs = []
        if bp_name and bp_name in self.teardown_request_funcs:
            for f in self.teardown_request_funcs[bp_name]:
                if id(f) not in seen:
                    seen.add(id(f))
                    funcs.append(f)
        for f in self.teardown_request_funcs.get(None, []):
            if id(f) not in seen:
                seen.add(id(f))
                funcs.append(f)
        for func in reversed(funcs):
            try:
                func(exc)
            except Exception:
                pass

    def do_teardown_appcontext(self, exc: Optional[BaseException] = None):
        for func in reversed(self.teardown_appcontext_funcs):
            try:
                func(exc)
            except Exception:
                pass

    # ── Context helpers ────────────────────────────────────────────────

    def app_context(self) -> Any:
        from fenrir.context import AppContext
        return AppContext(self)

    def test_request_context(self, *args: Any, **kwargs: Any) -> Any:
        from fenrir.context import RequestContext
        scope = {
            "type": "http",
            "method": kwargs.get("method", "GET").upper(),
            "path": args[0] if args else "/",
            "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in kwargs.get("headers", {}).items()],
            "query_string": kwargs.get("query_string", b""),
        }
        req = Request(scope)
        if self.session_interface:
            req.session = self.session_interface.open_session(self, req)
        return RequestContext(self, req)

    def test_client(self) -> Any:
        from fenrir.testing import FenrirTestClient
        return FenrirTestClient(self)

    # ── OpenAPI ────────────────────────────────────────────────────────

    def openapi(self) -> Dict[str, Any]:
        if self._openapi_schema_cache is not None:
            return self._openapi_schema_cache
        from fenrir.openapi import get_openapi
        schema = get_openapi(self.title, self.version, self.router.routes)
        self._openapi_schema_cache = schema
        return schema

    def _invalidate_openapi_cache(self):
        self._openapi_schema_cache = None
