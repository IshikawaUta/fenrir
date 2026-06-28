import mimetypes
import os
from typing import AsyncGenerator, AsyncIterable, Callable, Dict, Any, Generator, Iterable, Optional, Union, List, Tuple
from http.cookies import SimpleCookie

# Import orjson via fenrir.json
from fenrir.json import _orjson, _HAS_ORJSON
from fenrir.compat import _thread_pool

class Response:
    def __init__(
        self,
        body: Union[str, bytes] = b"",
        status: Union[int, str] = 200,
        headers: Dict[str, str] = None,
        content_type: str = "text/html; charset=utf-8",
    ):
        self._status = 200
        self.status = status
        self.headers = headers or {}
        # Fast check: only scan headers if we need to set content-type
        # Case-insensitive check (Content-Type vs content-type)
        if content_type and not any(k.lower() == "content-type" for k in self.headers):
            self.headers["content-type"] = content_type
        
        if isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = body
            
        self.cookies = SimpleCookie()

    @property
    def status(self) -> int:
        return self._status

    @status.setter
    def status(self, value: Union[int, str]):
        if isinstance(value, str):
            parts = value.split(" ", 1)
            if parts[0].isdigit():
                self._status = int(parts[0])
            else:
                raise ValueError(f"Invalid status code: {value!r}")
        else:
            self._status = value

    @property
    def body(self) -> bytes:
        return self._body

    @body.setter
    def body(self, value: Union[str, bytes]):
        if isinstance(value, str):
            self._body = value.encode("utf-8")
        else:
            self._body = value

    @property
    def text(self) -> Optional[str]:
        if self._body is None:
            return None
        try:
            return self._body.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return None

    @text.setter
    def text(self, value: Optional[str]):
        if value is None:
            self._body = b""
        else:
            self._body = value.encode("utf-8")

    def set_header(self, name: str, value: str) -> None:
        self.headers[name.lower()] = value

    def unset_header(self, name: str) -> None:
        self.headers.pop(name.lower(), None)


    @property
    def media(self) -> Any:
        try:
            from fenrir.context import current_app
            try:
                app = current_app._get_current_object()
            except RuntimeError:
                app = None
            
            if app is not None and hasattr(app, "json"):
                return app.json.loads(self._body.decode("utf-8"))
            if _HAS_ORJSON:
                return _orjson.loads(self._body)
            import json
            return json.loads(self._body.decode("utf-8"))
        except ValueError:
            return None

    @media.setter
    def media(self, value: Any):
        from fenrir.context import current_app
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            app = None
            
        if app is not None and hasattr(app, "json"):
            dumped = app.json.dumps(value)
        elif _HAS_ORJSON:
            dumped = _orjson.dumps(value)
            if isinstance(dumped, bytes):
                dumped = dumped.decode("utf-8")
        else:
            import json
            dumped = json.dumps(value)
            
        self._body = dumped.encode("utf-8") if isinstance(dumped, str) else dumped
        self.headers["content-type"] = "application/json"

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: int = None,
        expires: Union[str, int] = None,
        path: str = "/",
        domain: str = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str = None,
    ):
        self.cookies[key] = value
        cookie = self.cookies[key]
        if max_age is not None:
            cookie["max-age"] = max_age
        if expires is not None:
            if isinstance(expires, int):
                import datetime
                expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires)).strftime("%a, %d %b %Y %H:%M:%S GMT")
            cookie["expires"] = expires
        if path:
            cookie["path"] = path
        if domain:
            cookie["domain"] = domain
        if secure:
            cookie["secure"] = True
        if httponly:
            cookie["httponly"] = True
        if samesite:
            cookie["samesite"] = samesite

    def delete_cookie(self, key: str, path: str = "/", domain: str = None):
        # Use a past date to ensure browsers delete the cookie
        self.set_cookie(key, value="", max_age=0, expires="Thu, 01 Jan 1970 00:00:00 GMT", path=path, domain=domain)

    def get_asgi_headers(self) -> List[Tuple[bytes, bytes]]:
        headers_list = []
        for k, v in self.headers.items():
            headers_list.append((k.encode("latin1"), v.encode("latin1")))
        
        # Add set-cookie headers
        cookie_output = self.cookies.output()
        if cookie_output:
            for line in cookie_output.split("\r\n"):
                if line.startswith("Set-Cookie: "):
                    cookie_val = line[len("Set-Cookie: "):]
                    headers_list.append((b"set-cookie", cookie_val.encode("latin1")))
        
        return headers_list


class JSONResponse(Response):
    def __init__(self, content: Any, status: int = 200, headers: Dict[str, str] = None):
        # Try custom JSON provider first (supports custom serializers)
        from fenrir.context import current_app
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            app = None
            
        if app is not None and hasattr(app, "json"):
            body = app.json.dumps(content)
            if isinstance(body, str):
                body = body.encode("utf-8")
        elif _HAS_ORJSON:
            # Fast path: use orjson directly to bytes (avoids double encode/decode)
            body = _orjson.dumps(content)
            if not isinstance(body, bytes):
                body = body.encode("utf-8")
        else:
            from fenrir.json import DefaultJSONProvider
            body = DefaultJSONProvider(None).dumps(content)
            if isinstance(body, str):
                body = body.encode("utf-8")
            
        super().__init__(
            body=body,
            status=status,
            headers=headers,
            content_type="application/json",
        )


class HTMLResponse(Response):
    def __init__(self, content: str, status: int = 200, headers: Dict[str, str] = None):
        super().__init__(
            body=content,
            status=status,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )


class TextResponse(Response):
    def __init__(self, content: str, status: int = 200, headers: Dict[str, str] = None):
        super().__init__(
            body=content,
            status=status,
            headers=headers,
            content_type="text/plain; charset=utf-8",
        )


class RedirectResponse(Response):
    def __init__(self, url: str, status: int = 307, headers: Dict[str, str] = None):
        headers = headers or {}
        headers["location"] = url
        super().__init__(
            body=b"",
            status=status,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )


# Alias matching Flask/FastAPI naming
PlainTextResponse = TextResponse


class StreamingResponse(Response):
    """Send a response whose body is produced by an async/sync generator.

    Usage::

        @app.get("/stream")
        async def stream():
            async def gen():
                for i in range(5):
                    yield f"chunk {i}\\n"
            return StreamingResponse(gen(), media_type="text/plain")
    """

    def __init__(
        self,
        content: Union[AsyncGenerator, Generator, AsyncIterable, Iterable, Callable],
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "text/plain; charset=utf-8",
        content_type: Optional[str] = None,
    ) -> None:
        # Don't call super().__init__ with body; we keep content as iterator
        self._status = status
        self.headers = headers or {}
        # content_type is an alias for media_type (Sanic/Bottle compat)
        resolved_ct = content_type or media_type
        if "content-type" not in {k.lower() for k in self.headers}:
            self.headers["content-type"] = resolved_ct
        self._content = content
        self._body = b""  # unused but expected by some code paths
        self.cookies = __import__("http.cookies", fromlist=["SimpleCookie"]).SimpleCookie()


    # Mark this as a streaming response so the ASGI dispatcher handles it
    streaming = True

    async def stream_body(self) -> AsyncGenerator[bytes, None]:
        """Yield body chunks for ASGI transport."""
        import inspect as _inspect

        content = self._content
        if callable(content) and not _inspect.isasyncgen(content) and not _inspect.isgenerator(content):
            content = content()

        if _inspect.isasyncgen(content):
            async for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                yield chunk
        elif _inspect.isgenerator(content):
            for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                yield chunk
        elif hasattr(content, "__aiter__"):
            async for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                yield chunk
        elif hasattr(content, "__iter__"):
            for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                yield chunk


class FileResponse(Response):
    """Serve a file from the filesystem with automatic MIME detection.

    Usage::

        @app.get("/download")
        async def download():
            return FileResponse("/path/to/file.pdf")
    """

    def __init__(
        self,
        path: str,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: Optional[str] = None,
        filename: Optional[str] = None,
        content_disposition_type: str = "attachment",
    ) -> None:
        self._file_path = path
        self.status = status
        self.headers = headers or {}
        self.cookies = __import__("http.cookies", fromlist=["SimpleCookie"]).SimpleCookie()
        self.streaming = True

        # Guess content type
        if media_type is None:
            guessed, _ = mimetypes.guess_type(path)
            media_type = guessed or "application/octet-stream"

        if "content-type" not in {k.lower() for k in self.headers}:
            self.headers["content-type"] = media_type

        # Content-Disposition
        if filename is None:
            filename = os.path.basename(path)
        if filename:
            safe_filename = filename.replace('"', '').replace('\r', '').replace('\n', '').replace('\x00', '')
            self.headers.setdefault(
                "content-disposition",
                f'{content_disposition_type}; filename="{safe_filename}"'
            )

        # Content-Length
        try:
            self.headers.setdefault("content-length", str(os.path.getsize(path)))
        except OSError:
            pass

        self._body = b""

    async def stream_body(self) -> AsyncGenerator[bytes, None]:
        """Yield file contents in chunks without blocking the event loop."""
        import asyncio
        chunk_size = 64 * 1024  # 64 KB
        loop = asyncio.get_running_loop()

        def _read_chunk(f):
            return f.read(chunk_size)

        with open(self._file_path, "rb") as f:
            while True:
                chunk = await loop.run_in_executor(_thread_pool, _read_chunk, f)
                if not chunk:
                    break
                yield chunk
