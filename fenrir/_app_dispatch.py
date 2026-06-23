"""Fenrir ASGI dispatch — request handling, response coercion, exception handling."""
import asyncio
import inspect
import logging
import html
import traceback
import sys
from typing import Any, Callable, Dict

from fenrir.compat import to_thread
from fenrir.request import Request
from fenrir.response import Response, JSONResponse, HTMLResponse
from fenrir.context import _request_ctx_var, _g_ctx_var, _app_ctx_var, G
from fenrir.dependencies import resolve_parameters, _get_cached_signature
from fenrir.exceptions import HTTPException

logger = logging.getLogger("fenrir")

_STATUS_TEXTS = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
    422: "Unprocessable Entity", 500: "Internal Server Error",
}

def _status_text(code: int) -> str:
    return _STATUS_TEXTS.get(code, "Error")


class FenrirDispatchMixin:
    """Mixin providing ASGI __call__, _dispatch, _run_handler, and response methods."""

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import fenrir.app as _app_mod
        _app_mod._active_app = self
        _app_ctx_var.set(self)

        if self._asgi_middlewares and not self._asgi_app:
            app = self._dispatch
            for mw_class, mw_options in reversed(self._asgi_middlewares):
                app = mw_class(app, **mw_options)
            self._asgi_app = app

        try:
            if self._asgi_app:
                await self._asgi_app(scope, receive, send)
                return
            await self._dispatch(scope, receive, send)
        except Exception as exc:
            if scope.get("type") == "http":
                req = Request(scope)
                resp = await self._handle_exception(req, exc)
                await self._send_http_response(scope, resp, receive, send)
            else:
                raise

    async def _dispatch(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        import fenrir.app as _app_mod
        _app_mod._active_app = self
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

        # ── ASGI sub-app mounts ────────────────────────────────────────
        for prefix, asgi_app in self._asgi_mounts:
            if req_path == prefix or req_path.startswith(prefix + "/"):
                stripped = req_path[len(prefix):] or "/"
                patched_scope = dict(scope)
                patched_scope["path"] = stripped
                patched_scope["root_path"] = scope.get("root_path", "") + prefix
                await asgi_app(patched_scope, receive, send)
                return

        # ── HTTP request pipeline ──────────────────────────────────────
        req = Request(scope)
        await req._read_body(receive)
        resp = Response(status=200)

        if self.session_interface:
            try:
                req.session = self.session_interface.open_session(self, req)
            except Exception as e:
                logger.warning("Failed to open session: %s", e)
                req.session = None

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
                elif (hasattr(route, "response_model") and route.response_model is not None) or \
                     (hasattr(route, "response_models") and route.response_models):
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
                    try:
                        self.session_interface.save_session(self, req.session, response_obj)
                    except Exception as e:
                        logger.warning("Failed to save session: %s", e)

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
        except Exception as e:
            logger.debug("Response model serialization failed, falling back to coerce: %s", e)
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
        if getattr(self, "dev_mode", False):
            exc_type, _, exc_tb = sys.exc_info()
            if exc_tb is None:
                exc_type = type(exc)
            return self._render_debug_page(req, exc, exc_type, exc_tb)

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

    def _render_debug_page(self, req: Request, exc: Exception, exc_type: type, exc_tb: Any) -> HTMLResponse:
        status_code = getattr(exc, "status_code", 500)
        detail = getattr(exc, "detail", str(exc))
        if not isinstance(detail, str):
            detail = str(detail)

        exc_class_name = type(exc).__name__

        # Build traceback entries
        tb_lines = traceback.format_exception(exc_type, exc, exc_tb)
        tb_text = "".join(tb_lines)

        # Extract source context from traceback
        source_frames = []
        if exc_tb is not None:
            tb = exc_tb
            while tb is not None:
                frame = tb.tb_frame
                filename = frame.f_code.co_filename
                lineno = tb.tb_lineno
                func_name = frame.f_code.co_name

                # Try to read source context using linecache (cached)
                code_context = []
                try:
                    import linecache
                    all_lines = linecache.getlines(filename)
                    if all_lines:
                        start = max(0, lineno - 5)
                        end = min(len(all_lines), lineno + 4)
                        for i in range(start, end):
                            code_context.append((i + 1, all_lines[i].rstrip("\n")))
                except (OSError, IOError):
                    pass

                source_frames.append({
                    "filename": filename,
                    "lineno": lineno,
                    "func_name": func_name,
                    "code_context": code_context,
                })
                tb = tb.tb_next

        # Request info
        method = str(getattr(req, "method", "N/A"))
        path = str(getattr(req, "path", "N/A"))
        query_string = ""
        if hasattr(req, "query_string") and req.query_string:
            query_string = req.query_string.decode("utf-8", errors="replace") if isinstance(req.query_string, bytes) else str(req.query_string)

        # Client info: try scope["client"] -> x-forwarded-for -> x-real-ip -> host header
        client_host, client_port = "unknown", "unknown"
        scope_client = req.scope.get("client") if hasattr(req, "scope") else None
        if scope_client and isinstance(scope_client, (list, tuple)) and len(scope_client) >= 2:
            client_host = str(scope_client[0])
            client_port = str(scope_client[1])
        else:
            headers = getattr(req, "headers", {})
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                client_host = forwarded.split(",")[0].strip()
            else:
                real_ip = headers.get("x-real-ip")
                if real_ip:
                    client_host = real_ip
                else:
                    host_header = headers.get("host", "")
                    if host_header:
                        client_host = host_header.split(":")[0]

        # Build stack trace frames HTML
        frames_html = ""
        vendor_count = 0

        for idx, frame_info in enumerate(source_frames):
            fname = html.escape(frame_info["filename"])
            ffunc = html.escape(frame_info["func_name"])
            flineno = frame_info["lineno"]

            # Determine if this is a vendor/framework file
            fn = frame_info["filename"]
            is_vendor = (
                "/site-packages/" in fn
                or "/lib/python" in fn
                or fn.endswith("/fenrir/_app_dispatch.py")
                or fn.endswith("/fenrir/_app_core.py")
                or fn.endswith("/fenrir/app.py")
                or fn.endswith("/fenrir/routing.py")
                or fn.endswith("/fenrir/request.py")
                or fn.endswith("/fenrir/response.py")
                or fn.endswith("/fenrir/dependencies.py")
                or fn.endswith("/fenrir/exceptions.py")
                or fn.endswith("/fenrir/context.py")
                or fn.endswith("/fenrir/middleware.py")
                or fn.endswith("/fenrir/templating.py")
                or fn.endswith("/fenrir/security.py")
                or fn.endswith("/fenrir/sessions.py")
                or fn.endswith("/fenrir/json.py")
                or fn.endswith("/fenrir/helpers.py")
                or fn.endswith("/fenrir/views.py")
                or fn.endswith("/fenrir/openapi.py")
                or fn.endswith("/fenrir/bottle.py")
                or fn.endswith("/fenrir/falcon.py")
                or fn.endswith("/fenrir/sanic.py")
                or fn.endswith("/fenrir/testing.py")
                or fn.endswith("/fenrir/upload.py")
                or fn.endswith("/fenrir/websocket.py")
                or fn.endswith("/fenrir/sse.py")
                or fn.endswith("/fenrir/pool.py")
                or fn.endswith("/fenrir/http2.py")
                or fn.endswith("/fenrir/pagination.py")
                or fn.endswith("/fenrir/background.py")
                or fn.endswith("/fenrir/compat.py")
                or fn.endswith("/fenrir/config.py")
                or fn.endswith("/fenrir/signals.py")
                or fn.endswith("/fenrir/features.py")
                or "/fenrir/monitoring/" in fn
            )
            if is_vendor:
                vendor_count += 1

            # Shorten filename for display
            display_fname = fname
            if len(display_fname) > 80:
                display_fname = "..." + display_fname[-77:]

            code_html = ""
            if frame_info["code_context"]:
                code_lines = []
                for line_no, line_text in frame_info["code_context"]:
                    is_error_line = line_no == flineno
                    cls = ' class="code-line error-line"' if is_error_line else ' class="code-line"'
                    gutter = f'<span class="gutter">{line_no}</span>'
                    code_lines.append(f'<div{cls}>{gutter}<span class="line-content">{html.escape(line_text)}</span></div>')
                code_html = "\n".join(code_lines)

            frames_html += f'''
            <div class="frame-card" data-vendor="{'true' if is_vendor else 'false'}">
              <div class="frame-header" onclick="toggleFrame(this)">
                <span class="frame-file">{display_fname}</span>
                <span class="frame-line">line {flineno}</span>
                <span class="frame-func">{ffunc}()</span>
                <span class="frame-arrow">&#9662;</span>
              </div>
              <div class="frame-code">
                {code_html}
              </div>
            </div>'''

        from fenrir import __version__ as fenrir_version

        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fenrir Exception — {html.escape(exc_class_name)}</title>
<style>
  :root {{
    --bg: #f8f9fa;
    --sidebar-bg: #1b1e2b;
    --card-bg: #ffffff;
    --border: #e5e7eb;
    --text: #374151;
    --text-muted: #6b7280;
    --accent: #ef4444;
    --accent-light: #fef2f2;
    --code-bg: #1e2030;
    --code-text: #c0caf5;
    --gutter: #4a5068;
    --highlight-bg: #ef444418;
    --highlight-border: #ef4444;
    --link: #6366f1;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif; background: var(--bg); color: var(--text); display: flex; min-height: 100vh; }}

  /* Sidebar */
  .sidebar {{
    width: 260px; min-height: 100vh; background: var(--sidebar-bg); color: #fff;
    display: flex; flex-direction: column; position: fixed; left: 0; top: 0; bottom: 0; z-index: 10;
  }}
  .sidebar-brand {{
    padding: 28px 24px 20px; border-bottom: 1px solid #2d3148;
  }}
  .sidebar-brand .framework {{ font-size: 13px; color: #8b8fa8; text-transform: uppercase; letter-spacing: 2px; font-weight: 600; }}
  .sidebar-brand .version {{ font-size: 12px; color: #555a78; margin-top: 4px; }}
  .sidebar-error {{
    padding: 32px 24px; text-align: center; flex: 1;
  }}
  .sidebar-error .code {{
    font-size: 72px; font-weight: 800; color: var(--accent); line-height: 1; margin-bottom: 8px;
  }}
  .sidebar-error .name {{
    font-size: 14px; color: #a0a4c0; word-break: break-all; font-family: 'SF Mono', 'Fira Code', monospace;
  }}
  .sidebar-info {{
    padding: 20px 24px; border-top: 1px solid #2d3148;
  }}
  .sidebar-info .info-row {{
    display: flex; justify-content: space-between; padding: 8px 0; font-size: 12px; color: #8b8fa8;
  }}
  .sidebar-info .info-row .label {{ text-transform: uppercase; letter-spacing: 1px; }}
  .sidebar-info .info-row .value {{ color: #c0caf5; font-family: 'SF Mono', monospace; }}

  /* Main Content */
  .main {{ margin-left: 260px; flex: 1; padding: 32px 40px; max-width: 900px; }}

  .message-card {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 24px 28px; margin-bottom: 24px; border-left: 4px solid var(--accent);
  }}
  .message-card h2 {{ font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px; }}
  .message-card p {{ font-size: 14px; color: var(--text-muted); line-height: 1.6; }}

  .tabs {{
    display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 24px;
  }}
  .tab {{
    padding: 10px 20px; font-size: 13px; font-weight: 600; color: var(--text-muted);
    cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.15s;
    background: none; border-top: none; border-left: none; border-right: none;
  }}
  .tab:hover {{ color: var(--text); }}
  .tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* Stack Trace */
  .frame-card {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    margin-bottom: 8px; overflow: hidden;
  }}
  .frame-header {{
    display: flex; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer;
    font-size: 13px; transition: background 0.1s;
  }}
  .frame-header:hover {{ background: #f9fafb; }}
  .frame-file {{ color: var(--link); font-family: 'SF Mono', monospace; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .frame-line {{ color: var(--accent); font-weight: 600; white-space: nowrap; }}
  .frame-func {{ color: var(--text-muted); font-family: 'SF Mono', monospace; white-space: nowrap; }}
  .frame-arrow {{ color: var(--text-muted); font-size: 10px; transition: transform 0.2s; }}
  .frame-card.open .frame-arrow {{ transform: rotate(180deg); }}
  .frame-code {{ display: none; background: var(--code-bg); border-top: 1px solid #2d3148; padding: 0; max-height: 400px; overflow-y: auto; }}
  .frame-card.open .frame-code {{ display: block; }}
  .code-line {{ display: flex; font-size: 13px; line-height: 1.7; font-family: 'SF Mono', 'Fira Code', monospace; padding: 0 16px; }}
  .code-line.error-line {{ background: var(--highlight-bg); border-left: 3px solid var(--highlight-border); }}
  .gutter {{ color: var(--gutter); width: 40px; text-align: right; padding-right: 16px; user-select: none; flex-shrink: 0; }}
  .line-content {{ color: var(--code-text); white-space: pre; }}
  .code-line.error-line .gutter {{ color: var(--accent); font-weight: 600; }}

  /* Request Table */
  .request-table {{
    width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 8px;
    overflow: hidden; border: 1px solid var(--border);
  }}
  .request-table td {{ padding: 12px 16px; font-size: 13px; border-bottom: 1px solid var(--border); }}
  .request-table tr:last-child td {{ border-bottom: none; }}
  .request-table td:first-child {{ font-weight: 600; color: var(--text-muted); width: 140px; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
  .request-table td:last-child {{ font-family: 'SF Mono', monospace; color: var(--text); }}

  /* Traceback */
  .traceback-box {{
    background: var(--code-bg); border-radius: 8px; padding: 20px; font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace; color: var(--code-text);
    white-space: pre-wrap; word-break: break-all; line-height: 1.7; overflow-x: auto;
  }}

  /* Controls */
  .controls {{ margin-bottom: 20px; display: flex; gap: 8px; }}
  .btn-toggle {{
    padding: 6px 14px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--card-bg); color: var(--text-muted); cursor: pointer; font-weight: 500;
  }}
  .btn-toggle:hover {{ background: #f3f4f6; color: var(--text); }}

  @media (max-width: 768px) {{
    body {{ flex-direction: column; }}
    .sidebar {{
      width: 100%; position: relative; min-height: auto;
      flex-direction: column;
      padding: 0;
    }}
    .sidebar-brand {{
      padding: 12px 16px; border-bottom: 1px solid #2d3148;
      display: flex; align-items: center; gap: 8px;
    }}
    .sidebar-brand .framework {{ font-size: 11px; }}
    .sidebar-brand .version {{ margin-top: 0; font-size: 11px; }}
    .sidebar-error {{
      padding: 16px; text-align: center;
    }}
    .sidebar-error .code {{ font-size: 48px; margin-bottom: 4px; }}
    .sidebar-error .name {{ font-size: 12px; }}
    .sidebar-info {{
      width: 100%; padding: 10px 16px; border-top: 1px solid #2d3148;
      display: flex; flex-wrap: wrap; gap: 6px 16px;
    }}
    .sidebar-info .info-row {{
      padding: 4px 0; font-size: 11px; flex: 0 0 auto;
    }}
    .sidebar-info .info-row .label {{ font-size: 9px; }}
    .sidebar-info .info-row .value {{ max-width: 160px; overflow: hidden; text-overflow: ellipsis; }}

    .main {{ margin-left: 0; padding: 16px; max-width: 100%; }}

    .message-card {{ padding: 16px 18px; margin-bottom: 16px; }}
    .message-card h2 {{ font-size: 14px; }}
    .message-card p {{ font-size: 13px; word-break: break-word; }}

    .tabs {{ overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 16px; flex-wrap: nowrap; }}
    .tab {{ padding: 8px 14px; font-size: 12px; white-space: nowrap; flex-shrink: 0; }}

    .controls {{ flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
    .btn-toggle {{ padding: 5px 10px; font-size: 11px; }}

    .frame-header {{
      flex-wrap: wrap; gap: 6px; padding: 10px 12px; font-size: 12px;
    }}
    .frame-file {{ flex-basis: 100%; order: -1; font-size: 11px; word-break: break-all; }}
    .frame-func {{ display: none; }}
    .frame-line {{ font-size: 11px; }}

    .frame-code {{ max-height: 300px; overflow-x: auto; }}
    .code-line {{ font-size: 11px; padding: 0 8px; }}
    .gutter {{ width: 28px; padding-right: 8px; font-size: 10px; }}

    .request-table {{ display: block; overflow-x: auto; }}
    .request-table td {{ padding: 8px 12px; font-size: 12px; }}
    .request-table td:first-child {{ width: 80px; font-size: 10px; }}

    .traceback-box {{ padding: 12px; font-size: 11px; max-height: 400px; overflow-y: auto; }}
  }}

  @media (max-width: 480px) {{
    .sidebar-error .code {{ font-size: 36px; }}
    .sidebar-error .name {{ font-size: 11px; }}
    .main {{ padding: 12px; }}
    .tabs {{ gap: 0; }}
    .tab {{ padding: 8px 10px; font-size: 11px; }}
    .message-card {{ padding: 12px 14px; }}
    .controls {{ gap: 4px; }}
    .btn-toggle {{ padding: 4px 8px; font-size: 10px; }}
    .frame-header {{ padding: 8px 10px; }}
    .frame-file {{ font-size: 10px; }}
    .code-line {{ font-size: 10px; }}
    .request-table td {{ padding: 6px 8px; font-size: 11px; }}
  }}
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-brand">
    <div class="framework">Fenrir</div>
    <div class="version">v{html.escape(fenrir_version)}</div>
  </div>
  <div class="sidebar-error">
    <div class="code">{status_code}</div>
    <div class="name">{html.escape(exc_class_name)}</div>
  </div>
  <div class="sidebar-info">
    <div class="info-row"><span class="label">Method</span><span class="value">{html.escape(method)}</span></div>
    <div class="info-row"><span class="label">URI</span><span class="value" style="overflow:hidden;text-overflow:ellipsis;">{html.escape(path)}</span></div>
    <div class="info-row"><span class="label">Client</span><span class="value">{html.escape(client_host)}:{client_port}</span></div>
    {"<div class='info-row'><span class='label'>Query</span><span class='value'>" + html.escape(query_string) + "</span></div>" if query_string else ""}
  </div>
</div>

<div class="main">
  <div class="message-card">
    <h2>{html.escape(_status_text(status_code))}</h2>
    <p>{html.escape(detail)}</p>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('stacktrace', this)">Stack Trace</button>
    <button class="tab" onclick="switchTab('request', this)">Request</button>
    <button class="tab" onclick="switchTab('rawtrace', this)">Raw Trace</button>
  </div>

  <div id="tab-stacktrace" class="tab-content active">
    <div class="controls">
      <button class="btn-toggle" onclick="toggleVendor()" {'disabled style="opacity:0.4;cursor:not-allowed"' if vendor_count == 0 else ''}>Toggle vendor frames ({vendor_count})</button>
      <button class="btn-toggle" onclick="collapseAll()">Collapse all</button>
      <button class="btn-toggle" onclick="expandAll()">Expand all</button>
    </div>
    {frames_html}
  </div>

  <div id="tab-request" class="tab-content">
    <table class="request-table">
      <tr><td>Method</td><td>{html.escape(method)}</td></tr>
      <tr><td>URI</td><td>{html.escape(path)}</td></tr>
      {"<tr><td>Query</td><td>" + html.escape(query_string) + "</td></tr>" if query_string else ""}
      <tr><td>Client</td><td>{html.escape(client_host)}:{client_port}</td></tr>
    </table>
  </div>

  <div id="tab-rawtrace" class="tab-content">
    <div class="traceback-box">{html.escape(tb_text)}</div>
  </div>
</div>

<script>
function switchTab(name, btn) {{
  document.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});
  document.querySelectorAll('.tab-content').forEach(function(t) {{ t.classList.remove('active'); }});
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}}
function toggleFrame(el) {{
  el.closest('.frame-card').classList.toggle('open');
}}
function toggleVendor() {{
  var frames = document.querySelectorAll('.frame-card');
  for (var i = 0; i < frames.length; i++) {{
    if (frames[i].getAttribute('data-vendor') === 'true') {{
      frames[i].classList.toggle('open');
    }}
  }}
}}
function collapseAll() {{
  var frames = document.querySelectorAll('.frame-card');
  for (var i = 0; i < frames.length; i++) {{
    frames[i].classList.remove('open');
  }}
}}
function expandAll() {{
  var frames = document.querySelectorAll('.frame-card');
  for (var i = 0; i < frames.length; i++) {{
    frames[i].classList.add('open');
  }}
}}
</script>

</body>
</html>"""
        return HTMLResponse(page, status=status_code)

    async def _trigger_listeners(self, event: str):
        for listener in self.listeners.get(event, []):
            if inspect.iscoroutinefunction(listener):
                await listener(self)
            else:
                await to_thread(listener, self)
