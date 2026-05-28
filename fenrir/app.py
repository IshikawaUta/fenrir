import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union
from fenrir.compat import to_thread
from fenrir.request import Request
from fenrir.response import Response, JSONResponse, HTMLResponse, StreamingResponse
from fenrir.routing import Router, Route
from fenrir.context import _request_ctx_var, _g_ctx_var, G
from fenrir.dependencies import resolve_parameters
from fenrir.openapi import get_openapi, get_swagger_html, get_redoc_html
from fenrir.exceptions import HTTPException, HTTPInternalServerError, HTTPNotFound, HTTPMethodNotAllowed

import sys

logger = logging.getLogger("fenrir")

# Global active app reference for Asteri loader (persisted via sys namespace to survive reloads)
_active_app: Optional["Fenrir"] = getattr(sys, "_fenrir_active_app", None)


class _WsgiMount(Exception):
    """Internal sentinel: WSGI app should handle this request."""
    def __init__(self, adapter: Any, scope: Any) -> None:
        self.adapter = adapter
        self.scope = scope


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


import os

class Fenrir:
    def __init__(
        self,
        import_name: str = None,
        title: str = "Fenrir API",
        version: str = "1.2.1",
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
            "SESSION_COOKIE_SECURE": False,
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
        self._asgi_middlewares: List = []   # ASGI-style middleware stack
        self._wsgi_mounts: List = []        # (prefix, WsgiToAsgi) pairs
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

        # Add built-in docs endpoints
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

    # Decorators for routing
    def route(self, path: str, methods: List[str] = None, **route_kwargs):
        def decorator(handler):
            self.add_route(path, handler, methods, **route_kwargs)
            return handler
        return decorator

    def websocket(self, path: str):
        def decorator(handler):
            self.add_websocket_route(path, handler)
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

    def add_websocket_route(self, path: str, handler: Any):
        self.router.add_websocket_route(path, handler)

    def include_router(self, router: Router, prefix: str = ""):
        self.router.include_router(router, prefix=prefix)

    def add_middleware(self, middleware_class: Any, **options: Any) -> None:
        """Wrap the entire app with an ASGI middleware class.

        The middleware class must accept ``(app, **options)`` and be callable
        as ``await mw(scope, receive, send)``.
        """
        self._asgi_middlewares.append((middleware_class, options))

    def mount_wsgi(self, path: str, wsgi_app: Any) -> None:
        """Mount a WSGI application (e.g. a Bottle app) under *path*.

        Requests whose path starts with *path* are forwarded to *wsgi_app*
        via the built-in :class:`fenrir.compat.WsgiToAsgi` adapter.
        """
        from fenrir.compat import WsgiToAsgi
        adapter = WsgiToAsgi(wsgi_app)
        prefix = path.rstrip("/")

        async def _wsgi_handler(req, **_kw):
            # Delegate directly to adapter — we short-circuit by raising a
            # special sentinel that the __call__ dispatcher catches.
            raise _WsgiMount(adapter, req)

        # Store mount separately so __call__ can intercept before routing
        self._wsgi_mounts.append((prefix, adapter))

    # Blueprint registration
    def register_blueprint(self, blueprint: Blueprint):
        self.blueprints.append(blueprint)
        self.teardown_request_funcs[blueprint.name] = blueprint.teardown_request_funcs
        for path, handler, methods in blueprint.routes:
            # Prefix url_prefix
            full_path = blueprint.url_prefix + path
            self.router.add_route(full_path, handler, methods)
            # Associate route with its blueprint for middleware lookups
            new_route = self.router.routes[-1]
            self._route_blueprints[new_route] = blueprint

        for path, handler in blueprint.websocket_routes:
            full_path = blueprint.url_prefix + path
            self.router.add_websocket_route(full_path, handler)

    # Middleware decorator
    def middleware(self, middleware_type: str = "request"):
        def decorator(func):
            if middleware_type in ("request", "response"):
                self.middlewares[middleware_type].append(func)
            return func
        return decorator

    # Listener decorator
    def listener(self, event_name: str):
        def decorator(func):
            if event_name in self.listeners:
                self.listeners[event_name].append(func)
            return func
        return decorator

    def add_task(self, coro: Any) -> asyncio.Task:
        """Schedule a background task to run on the active event loop (Sanic compatibility)."""
        if inspect.iscoroutinefunction(coro):
            coro_obj = coro()
        else:
            coro_obj = coro
        return asyncio.create_task(coro_obj)


    def register_error_handler(self, exc_class_or_code: Union[Type[Exception], int], handler: Callable):
        if isinstance(exc_class_or_code, int):
            self.exception_handlers[exc_class_or_code] = handler
        elif isinstance(exc_class_or_code, type) and issubclass(exc_class_or_code, Exception):
            self.exception_handlers[exc_class_or_code] = handler
        else:
            raise ValueError("Error handler key must be an exception class or HTTP status code.")

    # Exception handler decorator
    def exception(self, *exceptions: Union[Type[Exception], int]):
        def decorator(func):
            for exc in exceptions:
                self.register_error_handler(exc, func)
            return func
        return decorator

    def teardown_request(self, f: Callable) -> Callable:
        self.teardown_request_funcs[None].append(f)
        return f

    def teardown_appcontext(self, f: Callable) -> Callable:
        self.teardown_appcontext_funcs.append(f)
        return f

    def before_request(self, f: Callable) -> Callable:
        self.middlewares["request"].append(f)
        return f

    def after_request(self, f: Callable) -> Callable:
        self.middlewares["response"].append(f)
        return f

    def do_teardown_request(self, exc: Optional[BaseException] = None):
        from fenrir.context import request
        bp_name = None
        try:
            bp_name = getattr(request, "blueprint", None)
        except Exception:
            pass
        funcs = []
        if bp_name in self.teardown_request_funcs:
            funcs.extend(self.teardown_request_funcs[bp_name])
        funcs.extend(self.teardown_request_funcs.get(None, []))
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

    # OpenAPI schema helper
    def openapi(self) -> Dict[str, Any]:
        return get_openapi(self.title, self.version, self.router.routes)

    # Life-cycle execution helpers
    async def _trigger_listeners(self, event: str):
        for listener in self.listeners.get(event, []):
            if inspect.iscoroutinefunction(listener):
                await listener(self)
            else:
                await asyncio.to_thread(listener, self)

    # ASGI Entrypoint
    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import sys
        sys._fenrir_active_app = self
        global _active_app
        _active_app = self

        # Apply ASGI middleware stack (outermost first, added last)
        if self._asgi_middlewares:
            app = self._dispatch
            for mw_class, mw_options in reversed(self._asgi_middlewares):
                app = mw_class(app, **mw_options)
            await app(scope, receive, send)
            return

        await self._dispatch(scope, receive, send)

    async def _dispatch(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import sys
        sys._fenrir_active_app = self
        global _active_app
        _active_app = self

        scope_type = scope.get("type")

        if scope_type == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    try:
                        await self._trigger_listeners("before_server_start")
                        await self._trigger_listeners("after_server_start")
                        await send({"type": "lifespan.startup.complete"})
                    except Exception as e:
                        await send({"type": "lifespan.startup.failed", "message": str(e)})
                elif message["type"] == "lifespan.shutdown":
                    try:
                        await self._trigger_listeners("before_server_stop")
                        await self._trigger_listeners("after_server_stop")
                        await send({"type": "lifespan.shutdown.complete"})
                    except Exception as e:
                        await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                    break
            return

        if scope_type == "websocket":
            try:
                from fenrir.websocket import WebSocket, WebSocketDisconnect
            except ImportError:
                await send({"type": "websocket.close", "code": 1011})
                return

            req = Request(scope)
            try:
                route, path_params, handler_func = self.router.match_websocket(req.path)
            except Exception:
                await send({"type": "websocket.close", "code": 1008})
                return

            ws = WebSocket(scope, receive, send)
            resp = Response(status=200)
            token_req = _request_ctx_var.set(req)
            token_g = _g_ctx_var.set(G())

            try:
                resolved_params = await resolve_parameters(handler_func, path_params, req, resp, ws=ws)
                await self._run_handler(handler_func, **resolved_params)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error("Unhandled exception in websocket handler", exc_info=e)
                if ws.client_state != "DISCONNECTED":
                    await ws.close(code=1011)
            finally:
                _request_ctx_var.reset(token_req)
                _g_ctx_var.reset(token_g)
            return

        if scope_type != "http":
            return

        # Check WSGI mounts before normal routing
        req_path = scope.get("path", "/")
        for prefix, wsgi_adapter in self._wsgi_mounts:
            if req_path == prefix or req_path.startswith(prefix + "/"):
                # Strip prefix from PATH_INFO
                stripped = req_path[len(prefix):] or "/"
                patched_scope = dict(scope)
                patched_scope["path"] = stripped
                patched_scope["root_path"] = scope.get("root_path", "") + prefix
                await wsgi_adapter(patched_scope, receive, send)
                return

        # 1. Initialize request and response context
        req = Request(scope)
        await req._read_body(receive)
        
        resp = Response(status=200)

        # Open session
        if self.session_interface:
            req.session = self.session_interface.open_session(self, req)

        # Trigger request_started signal
        from fenrir.signals import request_started, request_finished, got_request_exception
        request_started.send(self)

        from fenrir.context import RequestContext
        ctx = RequestContext(self, req)
        
        response_obj = None
        
        with ctx:
            try:
                _ = req.host
                # 2. Match Route
                route, path_params, handler_func = self.router.match(req.path, req.method)
                
                # set blueprint name on request
                active_bp = self._route_blueprints.get(route)
                if active_bp:
                    req.blueprint = active_bp.name
                
                # 4. Process request middlewares
                # Global request middlewares
                for mw in self.middlewares["request"]:
                    res = await self._run_handler(mw, req)
                    if res is not None:
                        response_obj = res
                        break
                        
                # Blueprint request middlewares
                if response_obj is None and active_bp:
                    for mw in active_bp.middlewares["request"]:
                        res = await self._run_handler(mw, req)
                        if res is not None:
                            response_obj = res
                            break
                
                # 5. Run route handler (if not short-circuited by request middleware)
                if response_obj is None:
                    # Resolve parameters (dependencies, path, query, header, cookie, body)
                    resolved_params = await resolve_parameters(handler_func, path_params, req, resp)

                    # Execute route handler with Falcon hooks if applicable
                    if route.is_falcon_resource():
                        # Execute before hooks
                        if hasattr(handler_func, "_falcon_before_hooks"):
                            for hook in handler_func._falcon_before_hooks:
                                res_hook = hook(req, resp, route.handler, path_params)
                                if inspect.isawaitable(res_hook):
                                    await res_hook

                        res = await self._run_handler(handler_func, **resolved_params)

                        # Execute after hooks
                        if hasattr(handler_func, "_falcon_after_hooks"):
                            for hook in handler_func._falcon_after_hooks:
                                res_hook = hook(req, resp, route.handler, path_params)
                                if inspect.isawaitable(res_hook):
                                    await res_hook
                    else:
                        res = await self._run_handler(handler_func, **resolved_params)

                    # Falcon style Resource handlers do not return anything but mutate resp in-place
                    if res is None:
                        response_obj = resp
                    else:
                        response_obj = res


                # Apply response_model serialization (if route declares one)
                if not isinstance(response_obj, Response):
                    response_obj = self._apply_response_model(route, response_obj)
                elif hasattr(route, "response_model") and route.response_model is not None:
                    coerced = self._apply_response_model(route, response_obj)
                    response_obj = coerced

                # Convert handler result to Response object (only if not already a Response)
                if not isinstance(response_obj, Response):
                    response_obj = self._coerce_response(response_obj)

                # 6. Process response middlewares (reverse order)
                # Blueprint response middlewares
                if active_bp:
                    for mw in reversed(active_bp.middlewares["response"]):
                        res = await self._run_handler(mw, req, response_obj)
                        if res is not None:
                            response_obj = self._coerce_response(res)
                
                # Global response middlewares
                for mw in reversed(self.middlewares["response"]):
                    res = await self._run_handler(mw, req, response_obj)
                    if res is not None:
                        response_obj = self._coerce_response(res)

                # Save session
                if self.session_interface and req.session is not None:
                    self.session_interface.save_session(self, req.session, response_obj)

                # Trigger request_finished signal
                request_finished.send(self, response=response_obj)

            except Exception as exc:
                # Trigger got_request_exception signal
                got_request_exception.send(self, exception=exc)
                response_obj = await self._handle_exception(req, exc)
                # Save session on error response too if modified
                if self.session_interface and req.session is not None:
                    try:
                        self.session_interface.save_session(self, req.session, response_obj)
                    except Exception:
                        pass

        # Clean up yield dependencies
        if hasattr(req, "_yield_cleanups"):
            for cleanup in reversed(req._yield_cleanups):
                try:
                    if inspect.iscoroutinefunction(cleanup):
                        await cleanup()
                    elif asyncio.iscoroutine(cleanup):
                        await cleanup
                    elif callable(cleanup):
                        res = cleanup()
                        if inspect.isawaitable(res):
                            await res
                except Exception as cleanup_err:
                    logger.error("Error in dependency cleanup", exc_info=cleanup_err)

        # 7. Send HTTP Response
        is_head = scope.get("method", "").upper() == "HEAD"

        # Streaming responses (StreamingResponse / FileResponse)
        if getattr(response_obj, "streaming", False) and hasattr(response_obj, "stream_body"):
            await send({
                "type": "http.response.start",
                "status": response_obj.status,
                "headers": response_obj.get_asgi_headers(),
            })
            if not is_head:
                async for chunk in response_obj.stream_body():
                    await send({
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    })
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        elif hasattr(response_obj, "__call__"):
            await response_obj(scope, receive, send)
        else:
            await send({
                "type": "http.response.start",
                "status": response_obj.status,
                "headers": response_obj.get_asgi_headers()
            })
            # RFC 7231: HEAD response must NOT include a body
            await send({
                "type": "http.response.body",
                "body": b"" if is_head else response_obj.body
            })

        # 8. Run background tasks after response is sent
        if hasattr(req, "_background_tasks") and req._background_tasks.tasks:
            await req._background_tasks()

    async def _run_handler(self, func: Callable, *args, **kwargs) -> Any:
        if args:
            try:
                sig = inspect.signature(func)
                num_params = 0
                for param in sig.parameters.values():
                    if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                        num_params += 1
                    elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                        num_params = len(args)
                        break
                args = args[:num_params]
            except (ValueError, TypeError):
                pass

        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return await to_thread(func, *args, **kwargs)

    def _apply_response_model(self, route: Route, content: Any) -> Response:
        """Serialise *content* through the route's response_model if defined."""
        rm = getattr(route, "response_model", None)
        if rm is None:
            return self._coerce_response(content)

        try:
            from pydantic import BaseModel, TypeAdapter

            exclude_unset = getattr(route, "response_model_exclude_unset", False)
            exclude_defaults = getattr(route, "response_model_exclude_defaults", False)
            include = getattr(route, "response_model_include", None)
            exclude = getattr(route, "response_model_exclude", None)
            status = getattr(route, "status_code", 200)

            if isinstance(rm, type) and issubclass(rm, BaseModel):
                # Always go through response_model.model_validate so extra fields
                # from a different Pydantic model are properly stripped.
                if isinstance(content, BaseModel):
                    # Convert via dict to let response_model pick only its fields
                    raw_dict = content.model_dump()
                    validated = rm.model_validate(raw_dict)
                elif isinstance(content, dict):
                    validated = rm.model_validate(content)
                else:
                    validated = rm.model_validate(content)

                serialised = validated.model_dump(
                    exclude_unset=exclude_unset,
                    exclude_defaults=exclude_defaults,
                    include=include,
                    exclude=exclude,
                )
                return JSONResponse(serialised, status=status)
            else:
                ta = TypeAdapter(rm)
                raw = ta.validate_python(content)
                return JSONResponse(
                    ta.dump_python(
                        raw,
                        exclude_unset=exclude_unset,
                        exclude_defaults=exclude_defaults,
                        include=include,
                        exclude=exclude,
                    ),
                    status=status,
                )
        except Exception:
            return self._coerce_response(content)

    def _coerce_response(self, content: Any) -> Response:
        if isinstance(content, tuple):
            status = 200
            headers = {}
            if len(content) == 2:
                body, status = content
            elif len(content) == 3:
                body, status, headers = content
            else:
                body = content
            
            resp = self._coerce_response(body)
            resp.status = status
            if headers:
                resp.headers.update(headers)
            return resp

        if isinstance(content, Response):
            return content
        if isinstance(content, str):
            return HTMLResponse(content)
        if isinstance(content, bytes):
            return Response(content, content_type="application/octet-stream")
        if isinstance(content, (dict, list, int, float, bool)) or content is None:
            return JSONResponse(content)
        return Response(str(content))

    async def _handle_exception(self, req: Request, exc: Exception) -> Response:
        # Check by status code if applicable
        status_code = getattr(exc, "status_code", None)
        if status_code in self.exception_handlers:
            handler = self.exception_handlers[status_code]
            try:
                res = await self._run_handler(handler, req, exc)
                return self._coerce_response(res)
            except Exception as inner_exc:
                exc = inner_exc

        # Check for registered custom exception class handlers
        for exc_class, handler in self.exception_handlers.items():
            if isinstance(exc_class, type) and issubclass(exc_class, Exception):
                if isinstance(exc, exc_class):
                    try:
                        res = await self._run_handler(handler, req, exc)
                        return self._coerce_response(res)
                    except Exception as inner_exc:
                        exc = inner_exc
                        break

        if isinstance(exc, HTTPException):
            return JSONResponse({"detail": exc.detail}, status=exc.status_code, headers=exc.headers)

        # Unhandled system errors
        logger.error("Unhandled server exception", exc_info=exc)
        return JSONResponse({"detail": "Internal Server Error"}, status=500)

    # Server runner using Asteri
    def run(self, host: str = "127.0.0.1", port: int = 8000, workers: int = 1, **kwargs):
        """Run the Fenrir app locally using Asteri v2.2.2 ASGI worker."""
        from asteri.arbiter import Arbiter
        from asteri.workers.asgi import ASGIWorker
        import sys
        
        # Store our application instance globally so Asteri's worker process can import it
        sys._fenrir_active_app = self
        global _active_app
        _active_app = self
        
        # Tell Asteri to load 'fenrir.app:_active_app'
        arbiter = Arbiter(
            app_path="fenrir.app:_active_app",
            worker_class=ASGIWorker,
            num_workers=workers,
            binds=[f"{host}:{port}"],
            **kwargs
        )
        try:
            arbiter.start()
        except KeyboardInterrupt:
            pass
