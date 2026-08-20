import base64
from typing import Any, Dict, Optional, Tuple

from fenrir.exceptions import HTTPException
from fenrir.request import Request


class SecurityBase:
    def __init__(
        self,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.scheme_name = scheme_name or self.__class__.__name__
        self.description = description


class APIKeyBase(SecurityBase):
    pass


class APIKeyCookie(APIKeyBase):
    def __init__(
        self,
        name: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.name = name
        self.auto_error = auto_error
        self.model = {
            "type": "apiKey",
            "in": "cookie",
            "name": name,
            "description": description,
        }

    async def __call__(self, request: Request) -> Optional[str]:
        api_key = request.cookies.get(self.name)
        if not api_key:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        return api_key


class APIKeyHeader(APIKeyBase):
    def __init__(
        self,
        name: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.name = name
        self.auto_error = auto_error
        self.model = {
            "type": "apiKey",
            "in": "header",
            "name": name,
            "description": description,
        }

    async def __call__(self, request: Request) -> Optional[str]:
        api_key = request.headers.get(self.name.lower())
        if not api_key:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        return api_key


class APIKeyQuery(APIKeyBase):
    def __init__(
        self,
        name: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.name = name
        self.auto_error = auto_error
        self.model = {
            "type": "apiKey",
            "in": "query",
            "name": name,
            "description": description,
        }

    async def __call__(self, request: Request) -> Optional[str]:
        api_key = request.args.get(self.name)
        if not api_key:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        return api_key


class WebSocketTokenAuth(SecurityBase):
    """WebSocket authentication dependency that validates a token from the
    initial WebSocket connection headers or query parameters.

    Usage::

        from fenrir import WebSocket, Depends
        from fenrir.security import WebSocketTokenAuth

        auth = WebSocketTokenAuth()

        @app.websocket("/ws")
        async def ws_handler(websocket: WebSocket, token: str = Depends(auth)):
            await websocket.accept()
            ...
    """

    def __init__(
        self,
        header_name: str = "authorization",
        query_param: str = "token",
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.header_name = header_name
        self.query_param = query_param
        self.auto_error = auto_error
        self.model = {
            "type": "http",
            "scheme": "bearer",
            "description": description or "WebSocket token authentication",
        }

    async def __call__(self, websocket: Any = None) -> Optional[str]:
        if websocket is None:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None

        scope = websocket.scope
        headers = dict(scope.get("headers", []))

        # Try header first
        token = None
        header_val = headers.get(self.header_name.encode("latin-1"))
        if header_val:
            auth = header_val.decode("latin-1")
            parts = auth.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            else:
                token = auth

        # Fall back to query parameter
        if token is None:
            query_string = scope.get("query_string", b"").decode("latin-1")
            import urllib.parse
            params = urllib.parse.parse_qs(query_string)
            token_vals = params.get(self.query_param, [])
            if token_vals:
                token = token_vals[0]

        if not token:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        return token


class HTTPBase(SecurityBase):
    def __init__(
        self,
        scheme: str,
        realm: Optional[str] = None,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.scheme = scheme
        self.realm = realm
        self.auto_error = auto_error
        self.model = {
            "type": "http",
            "scheme": scheme,
            "description": description,
        }
        if realm:
            self.model["realm"] = realm


class HTTPBasic(HTTPBase):
    def __init__(
        self,
        realm: Optional[str] = None,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(
            scheme="basic",
            realm=realm,
            scheme_name=scheme_name,
            description=description,
            auto_error=auto_error,
        )

    async def __call__(self, request: Request) -> Optional[Tuple[str, str]]:
        auth = request.headers.get("authorization")
        if not auth:
            if self.auto_error:
                headers = {}
                if self.realm:
                    headers["WWW-Authenticate"] = f'Basic realm="{self.realm}"'
                else:
                    headers["WWW-Authenticate"] = "Basic"
                raise HTTPException(
                    status_code=401, detail="Not authenticated", headers=headers
                )
            return None
        try:
            parts = auth.split()
            if len(parts) != 2 or parts[0].lower() != "basic":
                raise ValueError()
            decoded = base64.b64decode(parts[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
            return username, password
        except Exception:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid credentials") from None
            return None


class HTTPBearer(HTTPBase):
    def __init__(
        self,
        bearerFormat: Optional[str] = None,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(
            scheme="bearer",
            scheme_name=scheme_name,
            description=description,
            auto_error=auto_error,
        )
        self.bearerFormat = bearerFormat
        if bearerFormat:
            self.model["bearerFormat"] = bearerFormat

    async def __call__(self, request: Request) -> Optional[str]:
        auth = request.headers.get("authorization")
        if not auth:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return None
        return parts[1]


class HTTPDigest(HTTPBase):
    def __init__(
        self,
        realm: Optional[str] = None,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(
            scheme="digest",
            realm=realm,
            scheme_name=scheme_name,
            description=description,
            auto_error=auto_error,
        )

    async def __call__(self, request: Request) -> Optional[Dict[str, str]]:
        auth = request.headers.get("authorization")
        if not auth:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        if not auth.lower().startswith("digest "):
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return None
        # Parse digest header into a dict of key=value pairs
        import re
        digest_part = auth[7:]  # strip "Digest "
        parts = re.findall(r'(\w+)=(?:"([^"]+)"|([^\s,]+))', digest_part)
        return {k: v or v2 for k, v, v2 in parts}


class OAuth2(SecurityBase):
    def __init__(
        self,
        flows: Dict[str, Any],
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.flows = flows
        self.auto_error = auto_error
        self.model = {
            "type": "oauth2",
            "flows": flows,
            "description": description,
        }

    async def __call__(self, request: Request) -> Optional[str]:
        auth = request.headers.get("authorization")
        if not auth:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return None
        return parts[1]


class OAuth2PasswordBearer(OAuth2):
    def __init__(
        self,
        tokenUrl: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        flows = {"password": {"tokenUrl": tokenUrl, "scopes": {}}}
        super().__init__(
            flows=flows,
            scheme_name=scheme_name,
            description=description,
            auto_error=auto_error,
        )


class OAuth2AuthorizationCodeBearer(OAuth2):
    def __init__(
        self,
        authorizationUrl: str,
        tokenUrl: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        flows = {
            "authorizationCode": {
                "authorizationUrl": authorizationUrl,
                "tokenUrl": tokenUrl,
                "scopes": {},
            }
        }
        super().__init__(
            flows=flows,
            scheme_name=scheme_name,
            description=description,
            auto_error=auto_error,
        )


class OpenIDConnect(SecurityBase):
    def __init__(
        self,
        openIdConnectUrl: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(scheme_name=scheme_name, description=description)
        self.openIdConnectUrl = openIdConnectUrl
        self.auto_error = auto_error
        self.model = {
            "type": "openIdConnect",
            "openIdConnectUrl": openIdConnectUrl,
            "description": description,
        }

    async def __call__(self, request: Request) -> Optional[str]:
        auth = request.headers.get("authorization")
        if not auth:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return None
        return parts[1]
