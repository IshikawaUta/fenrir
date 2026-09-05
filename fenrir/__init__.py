"""
Fenrir Framework — A hybrid Python web framework.

Optimized for performance with lazy imports and fast startup.
"""
from __future__ import annotations

# Core imports only (fast startup)
from fenrir.app import Blueprint, Fenrir
from fenrir.context import current_app, g, request, session
from fenrir.exceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPException,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPUnauthorized,
    HTTPUnprocessableEntity,
)
from fenrir.response import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
    TextResponse,
)

# Lazy-loaded modules (deferred until needed)
_LAZY_IMPORTS = {
    # Dependency injection
    "Depends": ("fenrir.dependencies", "Depends"),
    "Query": ("fenrir.dependencies", "Query"),
    "Header": ("fenrir.dependencies", "Header"),
    "Cookie": ("fenrir.dependencies", "Cookie"),
    "Body": ("fenrir.dependencies", "Body"),
    "Path": ("fenrir.dependencies", "Path"),
    "Form": ("fenrir.dependencies", "Form"),
    "File": ("fenrir.dependencies", "File"),
    "Annotated": ("fenrir.compat", "Annotated"),
    # File upload
    "UploadFile": ("fenrir.upload", "UploadFile"),
    # WebSocket
    "WebSocket": ("fenrir.websocket", "WebSocket"),
    "WebSocketDisconnect": ("fenrir.websocket", "WebSocketDisconnect"),
    "WebSocketTimeout": ("fenrir.websocket", "WebSocketTimeout"),
    # Templating
    "render_template": ("fenrir.templating", "render_template"),
    "BaseTemplateRenderer": ("fenrir.templating", "BaseTemplateRenderer"),
    "Jinja2Renderer": ("fenrir.templating", "Jinja2Renderer"),
    # Views
    "View": ("fenrir.views", "View"),
    "MethodView": ("fenrir.views", "MethodView"),
    # Helpers
    "url_for": ("fenrir.helpers", "url_for"),
    "send_file": ("fenrir.helpers", "send_file"),
    "send_from_directory": ("fenrir.helpers", "send_from_directory"),
    "redirect": ("fenrir.helpers", "redirect"),
    # Routing
    "Router": ("fenrir.routing", "Router"),
    "Route": ("fenrir.routing", "Route"),
    "APIRouter": ("fenrir.routing", "APIRouter"),
    "RouteTrie": ("fenrir.routing", "RouteTrie"),
    # SSE
    "EventSourceResponse": ("fenrir.sse", "EventSourceResponse"),
    # Security
    "APIKeyCookie": ("fenrir.security", "APIKeyCookie"),
    "APIKeyHeader": ("fenrir.security", "APIKeyHeader"),
    "APIKeyQuery": ("fenrir.security", "APIKeyQuery"),
    "HTTPBasic": ("fenrir.security", "HTTPBasic"),
    "HTTPBearer": ("fenrir.security", "HTTPBearer"),
    "HTTPDigest": ("fenrir.security", "HTTPDigest"),
    "OAuth2PasswordBearer": ("fenrir.security", "OAuth2PasswordBearer"),
    "OAuth2AuthorizationCodeBearer": ("fenrir.security", "OAuth2AuthorizationCodeBearer"),
    "OpenIDConnect": ("fenrir.security", "OpenIDConnect"),
    "WebSocketTokenAuth": ("fenrir.security", "WebSocketTokenAuth"),
    # Background tasks
    "BackgroundTasks": ("fenrir.background", "BackgroundTasks"),
    "BackgroundTask": ("fenrir.background", "BackgroundTask"),
    # WSGI/Falcon/Sanic compat
    "WsgiToAsgi": ("fenrir.compat", "WsgiToAsgi"),
    "install_bottle_compat": ("fenrir.compat", "install_bottle_compat"),
    "install_falcon_compat": ("fenrir.compat", "install_falcon_compat"),
    "install_sanic_compat": ("fenrir.compat", "install_sanic_compat"),
    # Bottle
    "Bottle": ("fenrir.bottle", "Bottle"),
    # Testing
    "TestClient": ("fenrir.testing", "TestClient"),
    "FenrirTestClient": ("fenrir.testing", "FenrirTestClient"),
    # Middleware
    "CORSMiddleware": ("fenrir.middleware", "CORSMiddleware"),
    "GZipMiddleware": ("fenrir.middleware", "GZipMiddleware"),
    "RequestIDMiddleware": ("fenrir.middleware", "RequestIDMiddleware"),
    "RateLimitMiddleware": ("fenrir.middleware", "RateLimitMiddleware"),
    "BodyLimitMiddleware": ("fenrir.middleware", "BodyLimitMiddleware"),
    "CSRFMiddleware": ("fenrir.middleware", "CSRFMiddleware"),
    "SecurityHeadersMiddleware": ("fenrir.middleware", "SecurityHeadersMiddleware"),
    # Static files
    "StaticFiles": ("fenrir.static", "StaticFiles"),
    # Connection Pooling
    "ConnectionPool": ("fenrir.pool", "ConnectionPool"),
    "DatabasePool": ("fenrir.pool", "DatabasePool"),
    # HTTP/2 Push
    "HTTP2Push": ("fenrir.http2", "HTTP2Push"),
    # Pagination
    "PaginationParams": ("fenrir.pagination", "PaginationParams"),
    "paginate": ("fenrir.pagination", "paginate"),
    "paginate_dict": ("fenrir.pagination", "paginate_dict"),
    # Sessions
    "RedisSessionInterface": ("fenrir.sessions", "RedisSessionInterface"),
    "InMemorySessionInterface": ("fenrir.sessions", "InMemorySessionInterface"),
    "InMemorySessionBackend": ("fenrir.sessions", "InMemorySessionBackend"),
    "ServerSideSession": ("fenrir.sessions", "ServerSideSession"),
    # Monitoring
    "init_monitoring": ("fenrir.monitoring.core", "init_monitoring"),
    "record_request": ("fenrir.monitoring.core", "record_request"),
    "check_site_health": ("fenrir.monitoring.core", "check_site_health"),
    "check_site_health_async": ("fenrir.monitoring.core", "check_site_health_async"),
    "get_traffic_stats": ("fenrir.monitoring.core", "get_traffic_stats"),
    "init_fenrir_monitoring": ("fenrir.features", "init_fenrir_monitoring"),
    # Plugin system
    "Plugin": ("fenrir.plugins", "Plugin"),
    "PluginRegistry": ("fenrir.plugins", "PluginRegistry"),
    "plugin_hook": ("fenrir.plugins", "plugin_hook"),
    "setup_plugins": ("fenrir.plugins", "setup_plugins"),
    "PluginError": ("fenrir.plugins", "PluginError"),
    "PluginDependencyError": ("fenrir.plugins", "PluginDependencyError"),
    "PluginConfigError": ("fenrir.plugins", "PluginConfigError"),
    "PluginVersionError": ("fenrir.plugins", "PluginVersionError"),
    "PluginHealth": ("fenrir.plugins", "PluginHealth"),
    # Hook/extension points
    "HookRegistry": ("fenrir.hooks", "HookRegistry"),
    "get_hooks": ("fenrir.hooks", "get_hooks"),
    # ORM
    "Database": ("fenrir.orm", "Database"),
    "Model": ("fenrir.orm", "Model"),
    # Caching
    "Cache": ("fenrir.cache", "Cache"),
    "MemoryCache": ("fenrir.cache", "MemoryCache"),
    "RedisCache": ("fenrir.cache", "RedisCache"),
    "FileCache": ("fenrir.cache", "FileCache"),
    # Queue/Job system
    "Queue": ("fenrir.queue", "Queue"),
    "Job": ("fenrir.queue", "Job"),
    "Worker": ("fenrir.queue", "Worker"),
    "MemoryQueue": ("fenrir.queue", "MemoryQueue"),
    "RedisQueue": ("fenrir.queue", "RedisQueue"),
    # Performance
    "optimize_app": ("fenrir.performance", "optimize_app"),
    "ResponseCache": ("fenrir.performance", "ResponseCache"),
    "ObjectPool": ("fenrir.performance", "ObjectPool"),
}

# Sub-module imports (lazy)
_SUBMODULE_IMPORTS = {
    "bottle": "fenrir.bottle",
    "falcon": "fenrir.falcon",
    "sanic": "fenrir.sanic",
    "orm": "fenrir.orm",
    "graphql": "fenrir.graphql",
    "grpc": "fenrir.grpc",
    "performance": "fenrir.performance",
}

__version__ = "4.3.1"


def __getattr__(name: str):
    """Lazy import for performance."""
    # Check lazy imports
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        # Cache for subsequent access
        globals()[name] = value
        return value

    # Check sub-module imports
    if name in _SUBMODULE_IMPORTS:
        import importlib
        module = importlib.import_module(_SUBMODULE_IMPORTS[name])
        globals()[name] = module
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "RouteTrie",
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
    "WebSocketTokenAuth",
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
    "BodyLimitMiddleware",
    "CSRFMiddleware",
    "SecurityHeadersMiddleware",
    # Static files
    "StaticFiles",
    # Pagination
    "PaginationParams",
    "paginate",
    "paginate_dict",
    # Connection Pooling
    "ConnectionPool",
    "DatabasePool",
    # HTTP/2 Push
    "HTTP2Push",
    # Server-side sessions
    "RedisSessionInterface",
    "InMemorySessionInterface",
    "InMemorySessionBackend",
    "ServerSideSession",
    # Monitoring
    "init_monitoring",
    "record_request",
    "check_site_health",
    "check_site_health_async",
    "get_traffic_stats",
    # Features
    "init_fenrir_monitoring",
    # Plugin system
    "Plugin",
    "PluginRegistry",
    "plugin_hook",
    "setup_plugins",
    "PluginError",
    "PluginDependencyError",
    "PluginConfigError",
    "PluginVersionError",
    "PluginHealth",
    # Hook/extension points
    "HookRegistry",
    "get_hooks",
    # ORM
    "Database",
    "Model",
    "orm",
    # Caching
    "Cache",
    "MemoryCache",
    "RedisCache",
    "FileCache",
    # Queue/Job system
    "Queue",
    "Job",
    "Worker",
    "MemoryQueue",
    "RedisQueue",
    # GraphQL/gRPC (lazy-loaded)
    "graphql",
    "grpc",
    # Performance module
    "performance",
    "optimize_app",
    "ResponseCache",
    "ObjectPool",
]
