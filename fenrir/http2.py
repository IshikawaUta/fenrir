"""
fenrir.http2 — HTTP/2 Server Push support for Fenrir.

Provides utilities for HTTP/2 push promises, allowing the server to proactively
send resources to clients before they request them.

Note: HTTP/2 push requires the ASGI server to support HTTP/2 (e.g., Uvicorn with
h2, Daphne, or Hypercorn). If the server does not support HTTP/2, push promises
are silently ignored.
"""
from __future__ import annotations

from typing import Any, List

from fenrir.response import Response


class HTTP2Push:
    """HTTP/2 Server Push helper.

    Attaches ``Link`` headers for HTTP/2 push promises to responses.

    Usage::

        from fenrir import Fenrir
        from fenrir.http2 import HTTP2Push

        app = Fenrir()
        push = HTTP2Push()

        @app.get("/")
        async def index():
            return push.push(
                "<html>...</html>",
                push_paths=["/static/style.css", "/static/app.js"],
            )

        # Or as a decorator that auto-pushes static assets
        @push.auto_push(static_url="/static")
        async def index():
            return "<html>...</html>"
    """

    def __init__(self, as_header: bool = True):
        self._as_header = as_header
        self._push_paths: List[str] = []

    def push(self, content: Any, push_paths: List[str] = None) -> Response:
        """Add HTTP/2 push promises to a response.

        Args:
            content: The response content (string, dict, Response, etc.)
            push_paths: List of paths to push to the client.

        Returns:
            Response with Link headers for HTTP/2 push.
        """
        if not push_paths:
            push_paths = self._push_paths

        if not push_paths:
            return self._wrap_response(content)

        resp = self._wrap_response(content)

        # Build Link headers for HTTP/2 push
        link_parts = []
        for path in push_paths:
            link_parts.append(f'<{path}>; rel=preload; as={self._guess_as(path)}')

        existing_link = resp.headers.get("link", "")
        if existing_link:
            link_parts.insert(0, existing_link.rstrip(";").rstrip(","))

        resp.headers["link"] = ", ".join(link_parts)
        resp.headers["x-http2-push"] = "true"

        return resp

    def add_push_path(self, path: str) -> HTTP2Push:
        """Add a path to the push list (chainable)."""
        self._push_paths.append(path)
        return self

    def clear_push_paths(self) -> HTTP2Push:
        """Clear the push list."""
        self._push_paths.clear()
        return self

    def auto_push(self, static_url: str = "/static", paths: List[str] = None):
        """Decorator that automatically pushes static assets.

        Args:
            static_url: Base URL for static files.
            paths: List of static file paths to push.
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                result = await func(*args, **kwargs)
                if paths:
                    push_paths = [f"{static_url}/{p.lstrip('/')}" for p in paths]
                else:
                    push_paths = []
                return self.push(result, push_paths=push_paths)
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator

    def _wrap_response(self, content: Any) -> Response:
        """Wrap content in a Response object."""
        if isinstance(content, Response):
            return content
        if isinstance(content, str):
            from fenrir.response import HTMLResponse
            return HTMLResponse(content)
        if isinstance(content, (dict, list)):
            from fenrir.response import JSONResponse
            return JSONResponse(content)
        return Response(body=str(content).encode("utf-8"))

    @staticmethod
    def _guess_as(path: str) -> str:
        """Guess the resource type for the ``as`` attribute."""
        if path.endswith(".css"):
            return "style"
        if path.endswith(".js"):
            return "script"
        if path.endswith((".woff", ".woff2", ".ttf", ".otf")):
            return "font"
        if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            return "image"
        if path.endswith(".html"):
            return "document"
        if path.endswith(".json"):
            return "fetch"
        return "fetch"
