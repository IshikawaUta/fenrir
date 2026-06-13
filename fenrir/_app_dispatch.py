"""Fenrir ASGI dispatch — request handling, response coercion, exception handling."""
import asyncio
import inspect
import logging
from typing import Any, Callable, Dict

from fenrir.compat import to_thread
from fenrir.request import Request
from fenrir.response import Response, JSONResponse
from fenrir.context import _request_ctx_var, _g_ctx_var, _app_ctx_var, G
from fenrir.dependencies import resolve_parameters, _get_cached_signature
from fenrir.exceptions import HTTPException

logger = logging.getLogger("fenrir")


class FenrirDispatchMixin:
    """Mixin providing ASGI __call__, _dispatch, _run_handler, and response methods."""

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import fenrir.app as _app_mod
        _app_mod._active_app = self
        from fenrir.context import _app_ctx_var
        _app_ctx_var.set(self)

        if self._asgi_middlewares and not self._asgi_app:
            app = self._dispatch
            for mw_class, mw_options in reversed(self._asgi_middlewares):
                app = mw_class(app, **mw_options)
            self._asgi_app = app

        if self._asgi_app:
            await self._asgi_app(scope, receive, send)
            return

        await self._dispatch(scope, receive, send)

    async def _dispatch(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import fenrir.app as _app_mod
        _app_mod._active_app = self
        from fenrir.context import _app_ctx_var
        _app_ctx_var.set(self)

        scope_type = scope.get("type")

        # ── Lifespan ───────────────────────────────────────────────────
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
                        return
                elif message["type"] == "lifespan.shutdown":
                    try:
                        await self._trigger_listeners("before_server_stop")
                        await self._trigger_listeners("after_server_stop")
                        await send({"type": "lifespan.shutdown.complete"})
                    except Exception as e:
                        await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                    return
            return

        # ── WebSocket ──────────────────────────────────────────────────
        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
            return

        if scope_type != "http":
            return

        # ── WSGI mounts ────────────────────────────────────────────────
        req_path = scope.get("path", "/")
        for prefix, wsgi_adapter in self._wsgi_mounts:
            if req_path == prefix or req_path.startswith(prefix + "/"):
                stripped = req_path[len(prefix):] or "/"
                patched_scope = dict(scope)
                patched_scope["path"] = stripped
                patched_scope["root_path"] = scope.get("root_path", "") + prefix
                await wsgi_adapter(patched_scope, receive, send)
                return

        # ── HTTP request pipeline ──────────────────────────────────────
        req = Request(scope)
        await req._read_body(receive)
        resp = Response(status=200)

        if self.session_interface:
            req.session = self.session_interface.open_session(self, req)

        from fenrir.signals import request_started, request_finished, got_request_exception
        request_started.send(self)

        from fenrir.context import RequestContext
        ctx = RequestContext(self, req)
        response_obj = None

        with ctx:
            try:
                _ = req.host
                route, path_params, handler_func = self.router.match(req.path, req.method)
                req.path_params = path_params

                active_bp = self._route_blueprints.get(route)
                if active_bp:
                    req.blueprint = active_bp.name

                # Request middlewares
                for mw in self.middlewares["request"]:
                    res = await self._run_handler(mw, req)
                    if res is not None:
                        response_obj = res
                        break

                if response_obj is None and active_bp:
                    for mw in active_bp.middlewares["request"]:
                        res = await self._run_handler(mw, req)
                        if res is not None:
                            response_obj = res
                            break

                # Route handler
                if response_obj is None:
                    resolved_params = await resolve_parameters(handler_func, path_params, req, resp)

                    if route.is_falcon_resource():
                        if hasattr(handler_func, "_falcon_before_hooks"):
                            for hook in handler_func._falcon_before_hooks:
                                res_hook = hook(req, resp, route.handler, path_params)
                                if inspect.isawaitable(res_hook):
                                    await res_hook
                        res = await self._run_handler(handler_func, **resolved_params)
                        if hasattr(handler_func, "_falcon_after_hooks"):
                            for hook in handler_func._falcon_after_hooks:
                                res_hook = hook(req, resp, route.handler, path_params)
                                if inspect.isawaitable(res_hook):
                                    await res_hook
                    else:
                        res = await self._run_handler(handler_func, **resolved_params)

                    response_obj = resp if res is None else res

                # Response model
                if not isinstance(response_obj, Response):
                    response_obj = self._apply_response_model(route, response_obj)
                elif hasattr(route, "response_model") and route.response_model is not None:
                    response_obj = self._apply_response_model(route, response_obj)
                elif hasattr(route, "response_models") and route.response_models:
                    response_obj = self._apply_response_model(route, response_obj)

                if not isinstance(response_obj, Response):
                    response_obj = self._coerce_response(response_obj)

                # Response middlewares
                if active_bp:
                    for mw in reversed(active_bp.middlewares["response"]):
                        res = await self._run_handler(mw, req, response_obj)
                        if res is not None:
                            response_obj = self._coerce_response(res)

                for mw in reversed(self.middlewares["response"]):
                    res = await self._run_handler(mw, req, response_obj)
                    if res is not None:
                        response_obj = self._coerce_response(res)

                if self.session_interface and req.session is not None:
                    self.session_interface.save_session(self, req.session, response_obj)

                request_finished.send(self, response=response_obj)

            except Exception as exc:
                got_request_exception.send(self, exception=exc)
                response_obj = await self._handle_exception(req, exc)
                if self.session_interface and req.session is not None:
                    try:
                        self.session_interface.save_session(self, req.session, response_obj)
                    except Exception:
                        pass

        # Cleanup yield dependencies
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

        # Send HTTP response
        await self._send_http_response(scope, response_obj, receive, send)

        # Background tasks
        if hasattr(req, "_background_tasks") and req._background_tasks.tasks:
            await req._background_tasks()

    async def _handle_websocket(self, scope, receive, send):
        from fenrir.websocket import WebSocket, WebSocketDisconnect
        req = Request(scope)
        try:
            route, path_params, handler_func = self.router.match_websocket(req.path)
        except Exception:
            await send({"type": "websocket.close", "code": 1008})
            return

        ws_timeout = getattr(route, "ws_timeout", None)
        ws = WebSocket(scope, receive, send, timeout=ws_timeout)
        resp = Response(status=200)
        token_req = _request_ctx_var.set(req)
        token_g = _g_ctx_var.set(G())
        token_app = _app_ctx_var.set(self)

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
            _app_ctx_var.reset(token_app)

    async def _send_http_response(self, scope, response_obj, receive, send):
        is_head = scope.get("method", "").upper() == "HEAD"

        if getattr(response_obj, "streaming", False) and hasattr(response_obj, "stream_body"):
            await send({
                "type": "http.response.start",
                "status": response_obj.status,
                "headers": response_obj.get_asgi_headers(),
            })
            if not is_head:
                try:
                    async for chunk in response_obj.stream_body():
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
                except Exception as e:
                    logger.error("Error in streaming response", exc_info=e)
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        elif hasattr(response_obj, "__call__"):
            await response_obj(scope, receive, send)
        else:
            await send({
                "type": "http.response.start",
                "status": response_obj.status,
                "headers": response_obj.get_asgi_headers(),
            })
            await send({
                "type": "http.response.body",
                "body": b"" if is_head else response_obj.body,
            })

    async def _run_handler(self, func: Callable, *args, **kwargs) -> Any:
        if args:
            try:
                sig = _get_cached_signature(func)
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

    def _apply_response_model(self, route, content: Any) -> Response:
        actual_status = getattr(route, "status_code", 200)
        actual_content = content
        if isinstance(content, tuple):
            if len(content) == 2:
                actual_content, actual_status = content
            elif len(content) == 3:
                actual_content, actual_status, _ = content

        response_models = getattr(route, "response_models", {})
        if response_models and actual_status in response_models:
            return self._serialize_with_model(response_models[actual_status], actual_content, actual_status, route)

        rm = getattr(route, "response_model", None)
        if rm is None:
            return self._coerce_response(content)
        return self._serialize_with_model(rm, actual_content, actual_status, route)

    def _serialize_with_model(self, rm, content: Any, status: int, route) -> Response:
        try:
            from pydantic import BaseModel, TypeAdapter

            exclude_unset = getattr(route, "response_model_exclude_unset", False)
            exclude_defaults = getattr(route, "response_model_exclude_defaults", False)
            include = getattr(route, "response_model_include", None)
            exclude = getattr(route, "response_model_exclude", None)

            if isinstance(rm, type) and issubclass(rm, BaseModel):
                if isinstance(content, BaseModel):
                    validated = rm.model_validate(content.model_dump())
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
                    ta.dump_python(raw, exclude_unset=exclude_unset, exclude_defaults=exclude_defaults, include=include, exclude=exclude),
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
                return JSONResponse(list(content))
            resp = self._coerce_response(body)
            resp.status = status
            if headers:
                resp.headers.update(headers)
            return resp

        if isinstance(content, Response):
            return content
        if isinstance(content, str):
            from fenrir.response import HTMLResponse
            return HTMLResponse(content)
        if isinstance(content, bytes):
            return Response(content, content_type="application/octet-stream")
        if isinstance(content, (dict, list, int, float, bool)) or content is None:
            return JSONResponse(content)
        return Response(str(content))

    async def _handle_exception(self, req: Request, exc: Exception) -> Response:
        status_code = getattr(exc, "status_code", None)
        if status_code in self.exception_handlers:
            handler = self.exception_handlers[status_code]
            try:
                res = await self._run_handler(handler, req, exc)
                return self._coerce_response(res)
            except Exception as inner_exc:
                exc = inner_exc

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

        logger.error("Unhandled server exception", exc_info=exc)
        return JSONResponse({"detail": "Internal Server Error"}, status=500)

    async def _trigger_listeners(self, event: str):
        for listener in self.listeners.get(event, []):
            if inspect.iscoroutinefunction(listener):
                await listener(self)
            else:
                await to_thread(listener, self)
