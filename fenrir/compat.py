"""
fenrir.compat — Compatibility utilities.

Provides:
- WsgiToAsgi: Wrap a WSGI application to run inside an ASGI server.
- install_bottle_compat: Expose fenrir.bottle under the top-level `bottle` name
  without clobbering sys.modules globally (call explicitly if needed).
"""
from __future__ import annotations

import asyncio
import io
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

# get_origin / get_args: use typing_extensions so that Annotated from
# typing_extensions is properly introspected on Python 3.8, where
# typing.get_origin(typing_extensions.Annotated[...]) returns None.
try:
    from typing_extensions import get_origin, get_args
except ImportError:
    from typing import get_origin, get_args  # type: ignore[assignment]

# asyncio.to_thread compatibility for Python 3.8.
# IMPORTANT: use contextvars.copy_context() so that ContextVar values
# (request context, session, etc.) are visible inside the thread.
if sys.version_info >= (3, 9):
    to_thread = asyncio.to_thread
else:
    import contextvars
    import functools

    async def to_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, ctx.run, func_call)



class WsgiToAsgi:
    """Wrap a WSGI application to run inside an ASGI server.

    Usage::

        app = Fenrir()
        legacy = bottle.Bottle()
        app.mount_wsgi("/legacy", WsgiToAsgi(legacy))
    """

    def __init__(self, wsgi_app: Callable) -> None:
        self.wsgi_app = wsgi_app

    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        # Build WSGI environ
        environ = self._build_environ(scope)

        # Read body
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        environ["wsgi.input"] = io.BytesIO(body)
        environ["CONTENT_LENGTH"] = str(len(body))

        # Collect WSGI response via start_response callback
        status_code = [200]
        response_headers: List = []

        def start_response(status: str, headers: List, exc_info=None):
            status_code[0] = int(status.split(" ", 1)[0])
            response_headers[:] = [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in headers
            ]

        # Run WSGI app in thread so sync WSGI doesn't block event loop
        loop = asyncio.get_event_loop()
        response_iter: Iterable[bytes] = await loop.run_in_executor(
            None, lambda: self.wsgi_app(environ, start_response)
        )

        # Collect response body
        response_body = b""
        try:
            for chunk in response_iter:
                response_body += chunk
        finally:
            if hasattr(response_iter, "close"):
                response_iter.close()  # type: ignore[union-attr]

        # Send ASGI response
        await send(
            {
                "type": "http.response.start",
                "status": status_code[0],
                "headers": response_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": response_body,
            }
        )

    @staticmethod
    def _build_environ(scope: Dict) -> Dict[str, Any]:
        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"")
        server = scope.get("server") or ("localhost", 80)

        environ: Dict[str, Any] = {
            "REQUEST_METHOD": scope.get("method", "GET").upper(),
            "SCRIPT_NAME": scope.get("root_path", ""),
            "PATH_INFO": path,
            "QUERY_STRING": query_string.decode("latin-1") if isinstance(query_string, bytes) else query_string,
            "SERVER_NAME": server[0],
            "SERVER_PORT": str(server[1]),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": scope.get("scheme", "http"),
            "wsgi.input": io.BytesIO(),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }

        # Process headers
        for header_name, header_value in scope.get("headers", []):
            name = header_name.decode("latin-1").upper().replace("-", "_")
            value = header_value.decode("latin-1")
            if name == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = value
            elif name == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = value
            else:
                environ[f"HTTP_{name}"] = value

        return environ


def install_bottle_compat() -> None:
    """Register fenrir.bottle under the ``bottle`` name in sys.modules.

    This allows code that does ``import bottle`` to transparently use
    fenrir's bundled Bottle implementation. Call this once at startup if
    you want full transparent compatibility.
    """
    import fenrir.bottle as _bottle  # noqa: PLC0415

    if "bottle" not in sys.modules:
        sys.modules["bottle"] = _bottle
        _bottle.__path__ = []  # type: ignore[attr-defined]

        # Patch __module__ so repr() shows 'bottle.*' not 'fenrir.bottle.*'
        for _name, _obj in list(_bottle.__dict__.items()):
            if isinstance(_obj, type) and _obj.__module__ == "fenrir.bottle":
                _obj.__module__ = "bottle"


def install_falcon_compat() -> None:
    """Register fenrir.falcon under the ``falcon`` name in sys.modules.

    This allows code that does ``import falcon`` to transparently use
    fenrir's built-in Falcon compatibility layer.
    """
    import fenrir.falcon as _falcon

    if "falcon" not in sys.modules:
        sys.modules["falcon"] = _falcon
        _falcon.__path__ = []

        # Patch __module__
        for _name, _obj in list(_falcon.__dict__.items()):
            if isinstance(_obj, type) and _obj.__module__ == "fenrir.falcon":
                _obj.__module__ = "falcon"


def install_sanic_compat() -> None:
    """Register fenrir.sanic under the ``sanic`` name in sys.modules.

    This allows code that does ``import sanic`` to transparently use
    fenrir's built-in Sanic compatibility layer.
    """
    import fenrir.sanic as _sanic

    if "sanic" not in sys.modules:
        sys.modules["sanic"] = _sanic
        _sanic.__path__ = []

        # Patch __module__
        for _name, _obj in list(_sanic.__dict__.items()):
            if isinstance(_obj, type) and _obj.__module__ == "fenrir.sanic":
                _obj.__module__ = "sanic"


