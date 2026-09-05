"""
fenrir.static — Static file serving ASGI application.

Provides a ``StaticFiles`` ASGI app that serves files from a directory
with ETag, If-Modified-Since, and directory traversal protection.
"""
from __future__ import annotations

import mimetypes
import os
import stat
from email.utils import formatdate, parsedate_to_datetime
from functools import lru_cache
from typing import Any, Callable, Dict, Optional

from fenrir.compat import to_thread


# Cache for mimetypes.guess_type results
@lru_cache(maxsize=1024)
def _cached_guess_type(filepath: str):
    return mimetypes.guess_type(filepath)


class StaticFiles:
    """ASGI application that serves static files from a directory.

    Supports ETag-based caching, If-Modified-Since, and prevents
    directory traversal attacks.

    Usage::

        from fenrir import Fenrir
        from fenrir.static import StaticFiles

        app = Fenrir()
        app.mount("/static", StaticFiles(directory="static"))
        # Production with long cache:
        app.mount("/static", StaticFiles(directory="static", cache_control="public, max-age=31536000, immutable"))
    """

    def __init__(
        self,
        directory: str,
        html: bool = False,
        check_dir: bool = True,
        cache_control: str = "public, max-age=0",
    ) -> None:
        self.directory = os.path.abspath(directory)
        self.html = html
        self.cache_control = cache_control
        if check_dir and not os.path.isdir(self.directory):
            raise RuntimeError(f"Directory '{self.directory}' does not exist.")

    def _resolve_path(self, path: str) -> Optional[str]:
        """Resolve a URL path to a filesystem path, preventing traversal."""
        # Strip leading slash
        rel = path.lstrip("/")
        # Normalize and resolve (use realpath to follow symlinks)
        resolved = os.path.realpath(os.path.join(self.directory, rel))
        # Security: must stay within directory
        real_directory = os.path.realpath(self.directory)
        if not (resolved == real_directory or resolved.startswith(real_directory + os.sep)):
            return None
        if not os.path.isfile(resolved):
            return None
        return resolved

    def _get_etag(self, st: os.stat_result) -> str:
        """Generate ETag from file stat result."""
        return f'"{int(st.st_mtime)}-{st.st_size}"'

    def _get_mtime(self, st: os.stat_result) -> str:
        """Get HTTP-date of file modification time from stat result."""
        return formatdate(timeval=st.st_mtime, usegmt=True)

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "/")

        # Try to serve index.html for directory paths when html=True
        if self.html and (path == "/" or path.endswith("/")):
            index_path = self._resolve_path(path + "index.html")
            if index_path:
                path = path + "index.html"

        filepath = self._resolve_path(path)
        if filepath is None:
            # Try index.html for directory
            if self.html:
                index_candidate = os.path.join(path.rstrip("/"), "index.html")
                filepath = self._resolve_path(index_candidate)
                if filepath:
                    path = index_candidate
            if filepath is None:
                await send({
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"Not Found",
                })
                return

        # Get file metadata (use cached stat for repeated requests)
        try:
            st = await to_thread(os.stat, filepath)
        except OSError:
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": b"Not Found"})
            return

        # Check if directory (should not happen with file check, but safe guard)
        if stat.S_ISDIR(st.st_mode):
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": b"Forbidden"})
            return

        # Generate headers
        etag = self._get_etag(st)
        mtime_header = self._get_mtime(st)
        content_type, _ = _cached_guess_type(filepath)
        if content_type is None:
            content_type = "application/octet-stream"

        # Build headers list
        headers: list = [
            (b"content-type", content_type.encode("latin-1")),
            (b"content-length", str(st.st_size).encode("latin-1")),
            (b"etag", etag.encode("latin-1")),
            (b"cache-control", self.cache_control.encode("latin-1")),
        ]
        if mtime_header:
            headers.append((b"last-modified", mtime_header.encode("latin-1")))

        # Check If-None-Match (ETag)
        request_headers = dict(scope.get("headers", []))
        if_none_match = request_headers.get(b"if-none-match", b"").decode("latin-1")
        if if_none_match and if_none_match.strip('"') == etag.strip('"'):
            await send({
                "type": "http.response.start",
                "status": 304,
                "headers": [(b"etag", etag.encode("latin-1"))],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        # Check If-Modified-Since
        if_modified_since = request_headers.get(b"if-modified-since", b"").decode("latin-1")
        if if_modified_since and mtime_header:
            try:
                client_time = parsedate_to_datetime(if_modified_since)
                server_time = parsedate_to_datetime(mtime_header)
                if client_time >= server_time:
                    await send({
                        "type": "http.response.start",
                        "status": 304,
                        "headers": [
                            (b"etag", etag.encode("latin-1")),
                            (b"last-modified", mtime_header.encode("latin-1")),
                        ],
                    })
                    await send({"type": "http.response.body", "body": b""})
                    return
            except (ValueError, TypeError):
                pass

        # Send file
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })

        # HEAD requests: headers only, no body
        if scope.get("method", "").upper() == "HEAD":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        # Stream file in chunks using thread pool for non-blocking I/O
        chunk_size = 64 * 1024  # 64 KB
        try:
            def _read_chunks():
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            for chunk in await to_thread(lambda: list(_read_chunks())):
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                })
        except OSError:
            # File was deleted between stat and open (TOCTOU race)
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        await send({"type": "http.response.body", "body": b"", "more_body": False})
