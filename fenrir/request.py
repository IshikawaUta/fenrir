import urllib.parse
import json
from typing import Dict, Any, List, Optional

class Request:
    def __init__(self, scope: Dict[str, Any]):
        self.scope = scope
        self.method = scope.get("method", "GET").upper()
        self.path = scope.get("path", "/")
        self.query_string = scope.get("query_string", b"")
        
        # Parse query params
        self.args: Dict[str, str] = {}
        self.args_list: Dict[str, List[str]] = {}
        if self.query_string:
            qs = self.query_string.decode("latin1")
            parsed_qs = urllib.parse.parse_qs(qs)
            self.args_list = parsed_qs
            self.args = {k: v[0] for k, v in parsed_qs.items()}

        # Parse headers (case-insensitive)
        self.headers: Dict[str, str] = {}
        for k, v in scope.get("headers", []):
            self.headers[k.decode("latin1").lower()] = v.decode("latin1")

        # Cookies
        self.cookies: Dict[str, str] = {}
        cookie_header = self.headers.get("cookie", "")
        if cookie_header:
            for item in cookie_header.split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    self.cookies[k] = v

        self._body = b""
        self._json = None
        self._form = None
        self._parsed = False
        self.session = None

    @property
    def host(self) -> str:
        h = self.headers.get("host", "")
        from fenrir.context import current_app
        try:
            trusted = current_app.config.get("TRUSTED_HOSTS")
        except RuntimeError:
            trusted = None
        
        if trusted:
            def match_host(host_val: str, pattern: str) -> bool:
                if pattern.startswith("*."):
                    return host_val.endswith(pattern[1:]) or host_val == pattern[2:]
                return host_val == pattern
            
            host_only = h.split(":")[0] if ":" in h else h
            if not any(match_host(host_only, p) for p in trusted):
                from fenrir.exceptions import HTTPBadRequest
                raise HTTPBadRequest(detail="Invalid Host header")
        return h

    async def _read_body(self, receive):
        """Read full request body from ASGI receive channel."""
        if self._parsed:
            return
        
        body_chunks = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)
            elif message["type"] == "http.disconnect":
                break

        self._body = b"".join(body_chunks)
        self._parsed = True

    @property
    def body(self) -> bytes:
        return self._body

    @property
    def json(self) -> Any:
        if self._json is None and self._body:
            try:
                self._json = json.loads(self._body.decode("utf-8"))
            except ValueError:
                self._json = {}
        return self._json

    async def form(self) -> Dict[str, Any]:
        if self._form is not None:
            return self._form
            
        self._form = {}
        if not self._body:
            return self._form
            
        content_type = self.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            import io
            import python_multipart as multipart
            from fenrir.upload import UploadFile
            
            body_stream = io.BytesIO(self._body)
            headers = {"Content-Type": content_type.encode("latin-1")}
            
            def decode_bytes(val) -> str:
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="replace")
                return str(val) if val is not None else ""

            def on_field(field):
                name = decode_bytes(field.field_name)
                value = decode_bytes(field.value)
                if name in self._form:
                    existing = self._form[name]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        self._form[name] = [existing, value]
                else:
                    self._form[name] = value

            def on_file(file):
                name = decode_bytes(file.field_name)
                filename = decode_bytes(file.file_name)
                content_type_val = decode_bytes(file.content_type)
                file.file_object.seek(0)
                upload_file = UploadFile(filename, file.file_object, content_type_val)
                if name in self._form:
                    existing = self._form[name]
                    if isinstance(existing, list):
                        existing.append(upload_file)
                    else:
                        self._form[name] = [existing, upload_file]
                else:
                    self._form[name] = upload_file

            multipart.parse_form(headers, body_stream, on_field, on_file)
            
        elif "application/x-www-form-urlencoded" in content_type:
            parsed = urllib.parse.parse_qs(self._body.decode("utf-8", errors="replace"))
            for k, v in parsed.items():
                if len(v) == 1:
                    self._form[k] = v[0]
                else:
                    self._form[k] = v
                    
        return self._form

    # FastAPI-style async support
    async def body_async(self) -> bytes:
        return self.body

    async def json_async(self) -> Any:
        return self.json

    # Falcon compatibility layer
    @property
    def context(self) -> Dict[str, Any]:
        if not hasattr(self, "_context"):
            self._context = {}
        return self._context

    def get_header(self, name: str, default: Any = None) -> Optional[str]:
        return self.headers.get(name.lower(), default)

    def get_param(self, name: str, required: bool = False, default: Any = None) -> Optional[str]:
        val = self.args.get(name)
        if val is None:
            if required:
                from fenrir.exceptions import HTTPBadRequest
                raise HTTPBadRequest(detail=f"Missing query parameter: {name}")
            return default
        return val

    def get_param_as_int(self, name: str, required: bool = False, default: Any = None) -> Optional[int]:
        val = self.get_param(name, required, default)
        if val is None or val is default:
            return default
        try:
            return int(val)
        except ValueError:
            from fenrir.exceptions import HTTPBadRequest
            raise HTTPBadRequest(detail=f"Query parameter '{name}' must be an integer")

