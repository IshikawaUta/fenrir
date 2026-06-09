from fenrir.app import Fenrir, Blueprint
from fenrir.context import request, g, current_app, session
from fenrir.dependencies import Depends, Query, Header, Cookie, Body, Path, Form, File
from fenrir.upload import UploadFile
from fenrir.websocket import WebSocket, WebSocketDisconnect, WebSocketTimeout
from fenrir.exceptions import (
    HTTPException,
    HTTPBadRequest,
    HTTPUnauthorized,
    HTTPForbidden,
    HTTPNotFound,
    HTTPMethodNotAllowed,
    HTTPConflict,
    HTTPUnprocessableEntity,
    HTTPInternalServerError,
)
from fenrir.response import (
    Response,
    JSONResponse,
    HTMLResponse,
    TextResponse,
    RedirectResponse,
    StreamingResponse,
    FileResponse,
    PlainTextResponse,
)
from fenrir.templating import render_template, BaseTemplateRenderer, Jinja2Renderer
from fenrir.views import View, MethodView
from fenrir.helpers import url_for, send_file, send_from_directory, redirect
from fenrir.routing import Router, Route, APIRouter
from fenrir.sse import EventSourceResponse
from fenrir.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPBasic,
    HTTPBearer,
    HTTPDigest,
    OAuth2PasswordBearer,
    OAuth2AuthorizationCodeBearer,
    OpenIDConnect,
)
from fenrir.background import BackgroundTasks, BackgroundTask
from fenrir.compat import WsgiToAsgi, install_bottle_compat, install_falcon_compat, install_sanic_compat
from fenrir.bottle import Bottle
import fenrir.bottle as bottle
import fenrir.falcon as falcon
import fenrir.sanic as sanic
from fenrir.testing import TestClient, FenrirTestClient
from fenrir.middleware import (
    CORSMiddleware,
    GZipMiddleware,
    RequestIDMiddleware,
    RateLimitMiddleware,
)
from fenrir.pagination import PaginationParams, paginate, paginate_dict
from fenrir.sessions import (
    RedisSessionInterface,
    InMemorySessionInterface,
    InMemorySessionBackend,
    ServerSideSession,
)


# Re-export Annotated for convenient use with param markers
from fenrir.compat import Annotated

__version__ = "2.2.2"
__all__ = [
    # Core app
    "Fenrir",
    "Blueprint",
    # Context
    "request",
    "g",
    "current_app",
    "session",
    # Dependency injection
    "Depends",
    "Query",
    "Header",
    "Cookie",
    "Body",
    "Path",
    "Form",
    "File",
    "Annotated",
    # File upload
    "UploadFile",
    # WebSocket
    "WebSocket",
    "WebSocketDisconnect",
    "WebSocketTimeout",
    # Exceptions
    "HTTPException",
    "HTTPBadRequest",
    "HTTPUnauthorized",
    "HTTPForbidden",
    "HTTPNotFound",
    "HTTPMethodNotAllowed",
    "HTTPConflict",
    "HTTPUnprocessableEntity",
    "HTTPInternalServerError",
    # Responses
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "TextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
    "PlainTextResponse",
    # Templating
    "render_template",
    "BaseTemplateRenderer",
    "Jinja2Renderer",
    # Views
    "View",
    "MethodView",
    # Helpers
    "url_for",
    "send_file",
    "send_from_directory",
    "redirect",
    # Routing
    "Router",
    "Route",
    "APIRouter",
    # SSE
    "EventSourceResponse",
    # Security
    "APIKeyCookie",
    "APIKeyHeader",
    "APIKeyQuery",
    "HTTPBasic",
    "HTTPBearer",
    "HTTPDigest",
    "OAuth2PasswordBearer",
    "OAuth2AuthorizationCodeBearer",
    "OpenIDConnect",
    # Background tasks
    "BackgroundTasks",
    "BackgroundTask",
    # WSGI/Falcon/Sanic compat
    "WsgiToAsgi",
    "install_bottle_compat",
    "install_falcon_compat",
    "install_sanic_compat",
    # Bottle built-in
    "Bottle",
    "bottle",
    # Falcon built-in
    "falcon",
    # Sanic built-in
    "sanic",
    # Testing
    "TestClient",
    "FenrirTestClient",
    # Middleware
    "CORSMiddleware",
    "GZipMiddleware",
    "RequestIDMiddleware",
    "RateLimitMiddleware",
    # Pagination
    "PaginationParams",
    "paginate",
    "paginate_dict",
    # Server-side sessions
    "RedisSessionInterface",
    "InMemorySessionInterface",
    "InMemorySessionBackend",
    "ServerSideSession",
]

