<p align="center">
  <img src="https://raw.githubusercontent.com/IshikawaUta/fenrir/refs/heads/main/logo.jpg" alt="Fenrir Logo" width="500px"/>
</p>

# Fenrir Web Framework

[![PyPI version](https://img.shields.io/pypi/v/fenrir-framework.svg?color=blueviolet)](https://pypi.org/project/fenrir-framework/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-1331%20Passed-brightgreen.svg)](https://github.com/IshikawaUta/fenrir/actions)
[![CI](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml/badge.svg)](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml)
[![Performance](https://img.shields.io/badge/Performance-High--Speed%20ASGI-orange.svg)]()

**Fenrir** is a state-of-the-art, high-performance, hybrid Python web framework built on top of modern ASGI specifications. It elegantly merges the best programming paradigms from Python's most popular web frameworks (**Flask**, **FastAPI**, **Sanic**, **Falcon**, and **Bottle**) into a single unified workspace, powered locally by the premium **Asteri** application server.

Whether you prefer the automatic Pydantic validation of FastAPI, the seamless context-locals of Flask, the raw class-based speed of Falcon, or the robust background task model of Sanic, **Fenrir** allows you to leverage them all simultaneously in the same codebase.

---

## 📦 Installation

Install directly from **PyPI**:

```bash
pip install fenrir-framework
```

Or install with Redis support for distributed sessions and rate limiting:

```bash
pip install fenrir-framework[redis]
```

Or install in development mode by cloning the repository:

```bash
git clone https://github.com/IshikawaUta/fenrir.git
cd fenrir
pip install -e .
```

---

## 🌟 Key Features

*   **⚡ High-Speed ASGI Core**: Extremely low-overhead routing and handler pipeline, achieving massive request throughput.
*   **🔺 Trie-Based Routing**: O(k) route matching where k = path depth, instead of O(n) linear scan. Handles 1000+ routes efficiently.
*   **🧩 Framework Hybridization**:
    *   **FastAPI Paradigm**: Native Pydantic v2 data validation, `Annotated` type decorators, automated parameter resolution (`Query`, `Path`, `Header`, `Cookie`, `Body`), dynamic dependency injection (`Depends`), and automated `response_model` serialization.
    *   **Flask Paradigm**: Thread/Task-safe context locals (`request`, `g`, `session`), Jinja2 template rendering (`render_template`), and request teardown hooks.
    *   **Falcon Paradigm**: Class-based resource controllers (`on_get`, `on_post`), before/after hooks, and in-place response mutation.
    *   **Sanic Paradigm**: Global `sys.modules` patching (`install_sanic_compat()`), standard response helpers (`json`, `text`, `html`, `raw`, `redirect`), lifecycle listeners (`before_server_start`, etc.), and a background event scheduler (`app.add_task`).
    *   **Bottle Paradigm**: Built-in WSGI-to-ASGI wrapper and legacy mount adapter (`app.mount_wsgi()`) to run old WSGI applications at ASGI speeds.
*   **📖 Auto-Generated OpenAPI Docs**: Interactive **Swagger UI** (`/docs`) and **ReDoc** (`/redoc`) instantly generated from your Pydantic schemas and route metadata.
*   **🔌 Modern Communications**: Out-of-the-box support for **WebSockets** (with authentication) and **Server-Sent Events (SSE)**.
*   **🔐 WebSocket Authentication**: `WebSocketTokenAuth` dependency for token-based WebSocket authentication via headers or query parameters.
*   **🗄️ Connection Pooling**: Built-in generic `ConnectionPool` and `DatabasePool` with health checks, retry logic, and automatic connection recycling.
*   **🌐 HTTP/2 Push**: `HTTP2Push` utility for server push with Link headers and auto-push decorators.
*   **⏱️ Advanced Rate Limiting**: Per-IP or per-user rate limiting with optional Redis backend for distributed deployments.
*   **🛡️ Body Size Limits**: `BodyLimitMiddleware` to reject oversized request bodies and prevent DoS attacks.
*   **🔒 CSRF Protection**: `CSRFMiddleware` for cross-site request forgery token validation on state-changing methods, with automatic token generation and cookie injection.
*   **📦 Streaming Request Body**: `stream_body()` method for memory-efficient processing of large uploads without buffering.
*   **🗜️ Streaming GZip Compression**: `GZipMiddleware` compresses each chunk on-the-fly for `StreamingResponse`, with default compression level 6 (optimal CPU/ratio trade-off).
*   **⚡ Signature & Schema Caching**: `inspect.signature()` and OpenAPI schema are cached for faster repeated requests.
*   **🛠️ Premium CLI Tooling**: Visual route tables, interactive app shell, in-memory benchmarking suite, project scaffolding, and environment system inspection.
*   **📊 Built-in Monitoring Dashboard**: Health checks, traffic analysis, error rates, alerts, uptime stats, response time history, and hourly traffic with secure bcrypt authentication.
*   **🔌 Plugin System**: Version compatibility, dependency resolution, config validation, hot-reload, auto-discovery, health monitoring.
*   **🪝 Hook/Extension Points**: Priority ordering, one-time hooks, wildcard hooks, async/sync support, middleware integration.
*   **🗄️ Lightweight ORM**: SQLite/PostgreSQL support, Model with metaclass, QuerySet with filters/ordering, SQL injection prevention.
*   **💾 Caching System**: MemoryCache (LRU + TTL), RedisCache (SCAN not KEYS), FileCache (atomic writes).
*   **📋 Queue/Job System**: Job with retry/backoff/priority/timeout, Worker with concurrency, MemoryQueue and RedisQueue backends.
*   **🔗 GraphQL Support**: strawberry-graphql integration with GraphiQL playground.
*   **📡 gRPC Support**: GRPCServer, GRPCService, GRPCClient, interceptors.
*   **📊 Performance Module**: ObjectPool, ResponseCache, PerformanceMonitor, optimize_app().
*   **⚡ orjson Integration**: All JSON serialization uses orjson (7x faster than stdlib json).
*   **🐍 Python 3.8–3.13 Compatible**: Full backward compatibility ensured via `typing_extensions` polyfills for `Annotated`, `get_origin`, `get_args`; and a `contextvars`-aware `asyncio.to_thread` shim.

---

## 🚀 Quick Start (The Hybrid Power)

Here is a simple example (`demo_app.py`) showcasing how Flask, FastAPI, Falcon, and Sanic styles coexist harmoniously in a single application with built-in monitoring:

```python
import os
import logging
from pydantic import BaseModel
from fenrir import (
    Fenrir, Blueprint, request, g, Depends, Query, Header,
    render_template, Response, Form, File, UploadFile,
    WebSocket, WebSocketDisconnect
)
from fenrir.features import init_fenrir_monitoring

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo")

# Initialize App
app = Fenrir(title="Fenrir Hybrid Framework Demo", version="4.1.1")

# --- Enable Built-in Features ---
# Monitoring Dashboard: /monitoring (login: admin/changeme)
# Configure via .env or CLI: fenrir monitoring enable
init_fenrir_monitoring(app)

# --- 1. FastAPI-style Pydantic Validation & Dependency Injection ---
class UserRegister(BaseModel):
    username: str
    email: str
    age: int

async def verify_api_key(x_api_key: str = Header(default=None)):
    expected_key = os.getenv("API_KEY", "changeme-set-API_KEY-env")
    if x_api_key != expected_key:
        logger.warning("Invalid API key provided!")
    return x_api_key

# --- 2. Flask-style Decorators, Context-Locals, and Templating ---
@app.get("/")
async def home():
    name = request.args.get("name", "Fenrir User")
    return render_template("index.html", name=name)

# Form & File Upload Endpoint
@app.post("/upload")
async def handle_upload(
    title: str = Form(),
    file: UploadFile = File()
):
    content = await file.read()
    return {
        "title": title,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content)
    }

# WebSocket Echo Endpoint
@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(f"Fenrir Chat Echo: {msg}")
    except WebSocketDisconnect:
        logger.info("Chat WebSocket disconnected")

# --- 3. Falcon-style Class-based Resources ---
class ItemResource:
    async def on_get(self, req, resp, item_id: int):
        resp.status = 200
        resp.media = {
            "item_id": item_id,
            "status": "active",
            "msg": f"Fetched item {item_id} (Falcon Resource style)"
        }

    async def on_post(self, req, resp, item_id: int):
        data = req.json
        resp.status = 201
        resp.media = {
            "item_id": item_id,
            "received_body": data,
            "msg": f"Created sub-item for item {item_id} (Falcon Resource style)"
        }

app.add_route("/items/<item_id:int>", ItemResource())

# --- 4. Sanic-style Listeners and Middlewares ---
@app.listener("before_server_start")
async def setup_db(app_instance):
    logger.info("[Listener] Initializing mock database connection pool...")
    app_instance.db_pool = "Connected"

@app.listener("after_server_stop")
async def teardown_db(app_instance):
    logger.info("[Listener] Closing database connection pool...")

@app.middleware("request")
async def log_request_path(req):
    logger.info(f"[Middleware] Request received: {req.method} {req.path}")
    g.user_type = "guest"

@app.middleware("response")
async def add_custom_powered_by(req, resp):
    logger.info(f"[Middleware] Response sent: {resp.status}")
    resp.headers["X-Powered-By"] = "Fenrir Framework"

# --- 5. Flask/Sanic-style Blueprint modular routing ---
api_bp = Blueprint("api", url_prefix="/api")

@api_bp.post("/register")
async def register_user(
    body: UserRegister,
    api_key: str = Depends(verify_api_key),
    role: str = Query(default="member")
):
    return {
        "status": "success",
        "user_type": g.user_type,
        "role": role,
        "api_key_used": api_key,
        "registered_user": body.model_dump()
    }

app.register_blueprint(api_bp)

# --- 6. Custom Exception Handler ---
@app.exception(ValueError)
async def handle_value_error(req, exc):
    return Response(f"Custom Value Error: {exc}", status=400)

@app.get("/trigger-error")
async def trigger_error():
    raise ValueError("Something went wrong!")

# --- 7. Run with Asteri ASGI Server ---
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=2, app_path="demo_app:app")
```

---

## 🔺 Trie-Based Routing

Fenrir v4.1.1 uses a trie-based routing index for O(k) route matching, where k is the path depth. This is significantly faster than linear O(n) matching when you have many routes.

```python
from fenrir import Fenrir

app = Fenrir()

# These routes are indexed in a trie for fast lookup
@app.get("/api/v1/users")
async def list_users(): ...

@app.get("/api/v1/users/<int:user_id>")
async def get_user(user_id: int): ...

@app.get("/api/v1/posts/<int:post_id>/comments")
async def get_comments(post_id: int): ...

# Route matching is O(k) where k = number of path segments
# /api/v1/users/42 → checks: api → v1 → users → 42 (parametric)
```

---

## 🔐 WebSocket Authentication

Authenticate WebSocket connections using tokens from headers or query parameters:

```python
from fenrir import Fenrir, WebSocket, Depends
from fenrir.security import WebSocketTokenAuth

app = Fenrir()
auth = WebSocketTokenAuth()

@app.websocket("/ws")
async def websocket_handler(websocket: WebSocket, token: str = Depends(auth)):
    await websocket.accept()
    await websocket.send_text(f"Authenticated with token: {token}")
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Echo: {data}")
```

---

## 🗄️ Connection Pooling

Built-in connection pooling for databases and external services:

```python
from fenrir import Fenrir
from fenrir.pool import ConnectionPool

app = Fenrir()

# Create a connection pool
pool = ConnectionPool(
    create_func=lambda: create_engine("sqlite:///db.sqlite3"),
    close_func=lambda engine: engine.dispose(),
    min_size=2,
    max_size=10,
)

@app.get("/users")
async def list_users():
    async with pool.acquire() as conn:
        result = conn.execute("SELECT * FROM users")
        return {"users": [dict(row) for row in result]}
```

---

## 🌐 HTTP/2 Push

Proactively push resources to clients before they request them:

```python
from fenrir import Fenrir
from fenrir.http2 import HTTP2Push

app = Fenrir()
push = HTTP2Push()

@app.get("/")
async def index():
    return push.push(
        "<html><link rel='stylesheet' href='/static/style.css'></html>",
        push_paths=["/static/style.css", "/static/app.js"],
    )
```

---

## ⏱️ Advanced Rate Limiting

Per-IP or per-user rate limiting with optional Redis backend:

```python
from fenrir import Fenrir
from fenrir.middleware import RateLimitMiddleware

app = Fenrir()

# Per-IP rate limiting
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# Per-user rate limiting
def user_key(scope):
    for k, v in scope.get("headers", []):
        if k == b"x-user-id":
            return v.decode("latin-1")
    client = scope.get("client")
    return client[0] if client else "unknown"

app.add_middleware(RateLimitMiddleware, key_func=user_key)

# Distributed rate limiting with Redis
import redis.asyncio as aioredis
redis_client = aioredis.Redis()
app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
```

---

## 📦 Streaming Request Body

Process large uploads efficiently without buffering the entire body:

```python
from fenrir import Fenrir, Request

app = Fenrir()

@app.post("/upload")
async def upload(request: Request):
    total_bytes = 0
    async for chunk in request.stream_body(chunk_size=65536):
        total_bytes += len(chunk)
        # Process each chunk without loading entire body into memory
    return {"bytes_received": total_bytes}
```

---

## 💻 CLI Command Reference

Fenrir comes packed with a high-fidelity, visually rich command-line tool. Start the CLI by executing `fenrir` or `python -m fenrir.cli`.

### 1. `fenrir run`
Serve your application locally. Powered by **Asteri**, supporting dynamic multiprocessing, worker management, and live hot-reloading.
```bash
fenrir run demo_app:app --port 8000 --dev
```
*   **Flags**:
    *   `-H`, `--host`: Host bind address (default: `127.0.0.1`).
    *   `-p`, `--port`: Port number (default: `8000`).
    *   `-w`, `--workers`: Number of concurrent workers (default: `1`).
    *   `-d`, `--dev` / `--reload`: Active development mode with auto-reload.
    *   `--disable-dashboard`: Disable Asteri built-in dashboard (`/asteri-status`).

### 2. `fenrir routes`
Print a beautiful, colorized structural table of all registered HTTP endpoints, methods, matching handlers, and associated blueprints.
```bash
fenrir routes demo_app:app
```

### 3. `fenrir shell`
Instantly spawn an interactive python shell pre-configured with all key framework classes and context loaded (`app`, `request`, `g`, `Response`, `Blueprint`, etc.).
```bash
fenrir shell demo_app:app
```

### 4. `fenrir bench`
Perform in-memory framework benchmarking directly over ASGI using `HTTPX`. Eliminates network noise and tests raw pipeline speed under loaded constraints.
```bash
fenrir bench demo_app:app -i 1000 -t 5 -p / -m GET
```

### 5. `fenrir new`
Scaffold a complete, cleanly structured new Fenrir project directory in seconds with a premium responsive UI out of the box.
```bash
fenrir new my_new_project
cd my_new_project
fenrir run app.py --dev
```

### 6. `fenrir info`
Inspect the environment including Python details, OS details, Pydantic/Asteri versions, active compatibility layers, and route statistics.
```bash
fenrir info demo_app:app
```

### 7. `fenrir monitoring`
Manage the built-in monitoring dashboard for health checks and traffic analysis.
```bash
fenrir monitoring enable     # Enable monitoring dashboard
fenrir monitoring disable    # Disable monitoring dashboard
fenrir monitoring status     # Show monitoring configuration
fenrir monitoring set-password  # Set new dashboard password
```

**Default credentials:**
- Username: `admin`
- Password: `changeme`

> **Note:** Change the default password in production using `fenrir monitoring set-password` or set `MONITORING_PASSWORD` in `.env` file.

---

## 📊 Monitoring API Endpoints

All endpoints require authentication via monitoring token cookie.

### `GET /monitoring/api/stats`
Returns traffic stats, site counts, and uptime start time.

### `GET /monitoring/api/traffic`
Returns today/yesterday traffic comparison.

### `GET /monitoring/api/alerts?limit=50`
Returns recent alerts (limit: 1-500, default 50).

### `GET /monitoring/api/health`
Triggers health check on all monitored sites.

### `GET /monitoring/api/uptime`
Returns uptime percentage for each monitored site.

### `GET /monitoring/api/response-times?url=...&hours=24`
Returns response time history for a specific site (max 168 hours).

### `GET /monitoring/api/hourly?hours=24`
Returns hourly traffic breakdown (max 720 hours).

### `GET /monitoring/api/summary`
Returns comprehensive summary with overview, sites, alerts, and hourly traffic.

### `POST /monitoring/api/check`
Check health of a specific site: `{"url": "http://example.com"}`

---

## 🧪 Comprehensive Test Suite

Fenrir is thoroughly covered by an automated test suite comprising **1536 tests** validating every single component, including the new trie-based routing, streaming body, connection pooling, HTTP/2 push, WebSocket authentication, rate limiting, HTTP digest/OAuth2/OpenID security schemes, PATCH/PUT/DELETE routing, lifespan handling, CSRF auto-token generation, streaming GZip compression, monitoring dashboard (including uptime, response time history, hourly traffic, and summary endpoints), dev mode debug page, ASGI middleware error handling, plugin system, hook system, lightweight ORM, caching system, queue/job system, GraphQL support, gRPC support, performance optimization module, and all v4.1.1 improvements. The suite runs automatically via **GitHub Actions** on every push across Python **3.8 – 3.13**.

Run the test suite locally:

```bash
PYTHONPATH=. pytest -v
```

### Output:
```text
================================ 1331 passed, 1 skipped in 39.86s ================================
```

---

## 🔄 Changelog

### Fenrir v4.1.1 — Bug Fixes, Performance & Test Coverage

**1536 tests validated**: the largest test suite in the framework’s history.

**Bug Fixes (53+):**
- Fixed CSRF token HMAC predictable randomness (now uses `secrets.token_hex(32)`)
- Fixed CORS duplicate branches and incorrect headers handling
- Fixed RateLimit TOCTOU race condition with `asyncio.Lock` → `deque`
- Fixed BodyLimit body drain and double response issue
- Fixed MemoryQueue unbounded cleanup with periodic cleanup task
- Fixed ORM ORDER BY column_name validation and PostgreSQL INSERT RETURNING
- Fixed config.py `exec()` path traversal with strict validation
- Fixed monitoring/core.py default password rejection and SSRF validation
- Fixed graphql.py JSONResponse `status_code` → `status` parameter
- Fixed graphql.py missing `import inspect` for signature inspection
- Fixed graphql.py sync context_factory always awaited (even for plain dict)
- Fixed cache.py `cached` decorator `exists()` check before staleness
- Fixed plugins.py lazy import validation
- Fixed sessions.py event loop crash with `_run_sync_or_async()`
- Fixed monitoring/routes.py logout `GET` → `POST` for CSRF protection
- Fixed `_app_dispatch.py` duplicate `response_model` processing
- Fixed `_app_dispatch.py` SessionMiddleware error handling
- Fixed ORM `update()` column_name validation
- Fixed `_app_core.py` mount validation
- Fixed features.py monitoring middlewares when disabled
- Fixed queue.py `json_loads`/`json_dumps` AttributeError
- Fixed json.py redundant list comprehension
- Fixed ORM `transaction()` context manager for batched commits
- Fixed ORM `_from_row` with `field_index_map` O(1) lookup
- Fixed ORM `_insert` and `_update` with proper column_name validation
- Fixed ORM `_create_table` with proper column_name handling
- Fixed openapi.py HEAD filter for duplicate routes
- Fixed context.py `RequestContext.__enter__` rollback on exception
- Fixed testing.py `follow_redirects` parameter
- Fixed helpers.py `url_for` WebSocket class-based view fallback
- Fixed sse.py sync generator blocking with `run_in_executor`
- Fixed pool.py `close()`/`_release()`/`_discard()` lock None guard
- Fixed performance.py `FileResponse.stream_body` with `run_in_executor`
- Fixed static.py TOCTOU race condition in `StaticFiles`
- Fixed middleware.py async import for `CSRFMiddleware`
- Fixed monitoring/core.py `check_site_health` SSRF validation
- And 15+ more bug fixes

**Performance Optimizations (12):**
- FileResponse `stream_body` with `run_in_executor` for non-blocking I/O
- `is_falcon_resource()` cached at route init for faster detection
- TypeAdapter cache per annotation in dependencies for faster validation
- URLSafeTimedSerializer cache in sessions for faster serialization
- ORM `field_index_map` O(1) lookup instead of O(n) `list.index()`
- `deque` for RateLimit instead of `list` filter for O(1) popleft
- Redis `aclose()` and `set(ex=ttl)` deprecation fixes
- `LruCache.popitem()` O(1) for cache eviction
- `transaction()` context manager for ORM batched commits
- Import hot path dedup in `_app_dispatch.py`
- Lazy imports cached for `BackgroundTasks`, `UploadFile`, `current_app`
- `linecache` for debug source inspection

**Deprecation Fixes (3):**
- RedisQueue `close()` → `aclose()` (aioredis deprecation)
- RedisCache `close()` → `aclose()` (aioredis deprecation)
- RedisCache `setex()` → `set(ex=ttl)` (redis-py deprecation)

**Test Coverage: 76% → 83% (1331 tests)**
- graphql.py: 32% → 92% (19 new tests)
- grpc.py: 49% → 70% (24 new tests)
- upload.py: 54% → 100% (15 new tests)
- templating.py: 65% → 100% (12 new tests)
- orm.py: 64% → 71% (32 new tests)
- signals.py: 71% → 96% (19 new tests)
- cache.py: 52% → 91% (50 new tests)
- plugins.py: 63% → 86% (77 new tests)
- performance.py: 0% → 85% (51 new tests)
- queue.py: 47% → 94% (47 new tests)
- cli.py: 44% → 68% (17 new tests)

**Benchmark:**
- Added 5-framework comparison (Fenrir, FastAPI, Flask, Falcon, Sanic)
- Fenrir wins Import Time (108ms vs FastAPI 1013ms) and Route Registration (59ms vs FastAPI 299ms)
- Falcon wins Throughput (3419 req/s) and Import Time in some runs
- FastAPI wins App Init (0.64ms)

**Security Fixes:**
- Hardcoded API key in demo_app.py → environment variable `API_KEY`
- Default password "changeme" → rejection with warning
- SSRF validation for monitoring health checks
- CSRF token now uses cryptographically secure random

### v4.0.0 — Production-Ready Major Release

**New Features:**
- **Plugin System** (`fenrir/plugins.py`): PluginRegistry with version compatibility, dependency resolution (circular detection), config validation, hot-reload, auto-discovery via entry points, health monitoring, namespace isolation, thread-safety
- **Hook/Extension Points** (`fenrir/hooks.py`): HookRegistry with priority ordering, one-time hooks, wildcard hooks, async/sync support, middleware integration, hook cancellation
- **Lightweight ORM** (`fenrir/orm.py`): Database (SQLite/PostgreSQL), Model with metaclass, Field types, QuerySet with filters/ordering/limit/offset, parameterized queries, SQL injection prevention
- **Caching System** (`fenrir/cache.py`): MemoryCache (LRU + TTL), RedisCache (SCAN not KEYS), FileCache (atomic writes), prefix invalidation
- **Queue/Job System** (`fenrir/queue.py`): Queue with handler registration, Job with retry/backoff/priority/timeout, Worker with concurrency, MemoryQueue and RedisQueue backends
- **GraphQL Support** (`fenrir/graphql.py`): GraphQLRouter with strawberry-graphql integration, GraphiQL playground
- **gRPC Support** (`fenrir/grpc.py`): GRPCServer, GRPCService, GRPCClient, GRPCContext, interceptors
- **Performance Module** (`fenrir/performance.py`): ObjectPool, ResponseCache, PerformanceMonitor, optimize_app()
- **orjson Integration**: All JSON serialization uses orjson (7x faster than stdlib json), with stdlib json fallback

**Performance Optimizations:**
- **Lazy imports**: Reduced import time from 681ms to 53ms (92% faster)
- **orjson JSON serialization**: 7x faster than stdlib json (233ms vs 1652ms for 10000 ops)
- **Centralized JSON helpers**: `json_dumps()`, `json_loads()`, `json_dumps_bytes()` in `fenrir/json.py`
- **Benchmark results**: Fenrir wins 3/4 vs FastAPI (Import, Route Reg, Throughput)

**Bug Fixes (29 total):**
- **CRITICAL (2)**: Race condition `Database.connect()` with proper asyncio.Lock, SQL injection `QuerySet.update()` with field validation
- **HIGH (4)**: Swallowed errors in `_app_dispatch.py` with logging, pool overflow in `pool.py` with semaphore inside lock, gRPC service registration, memory leak in queue cleanup
- **MEDIUM (3)**: Session deadlock with separate thread event loop, one-time wildcard hook removal, redundant import json consolidation
- **LOW (6)**: Dead code removal, SSE silent exception logging, delete_cookie expires fix, context.py do_teardown_request guard, send_file streaming, Model._meta mutable default

**Architecture Improvements:**
- **Python 3.8-3.13 Compatibility**: No match/case, no type|None syntax, no list[int] runtime hints
- **Import Circular Free**: DAG import graph with lazy loading
- **Thread Safety**: Proper locks for plugins (RLock), hooks (Lock), Redis queue (asyncio.Lock)

**Tests:**
- Added 126 new tests covering plugin system, hook system, ORM, cache, queue, GraphQL, gRPC, performance
- Total test count: 874 (up from 748)

### v3.1.3 — Dev Mode Debug Page & Error Handling

**New Features:**
- Laravel-style dev mode debug page (`--dev` flag or `FENRIR_DEV_MODE=1` env var)
- Debug page with sidebar, tabs (Stack Trace / Request / Raw Trace), and collapsible frames
- ASGI middleware errors now caught and displayed on debug page
- Dev mode overrides custom exception handlers for full debug info
- Client info detection: scope → X-Forwarded-For → X-Real-IP → Host header
- XSS protection via `html.escape()` on all user-controlled values
- Responsive design for mobile (768px and 480px breakpoints)
- Vendor frame toggle with frame count

**Bug Fixes:**
- Fixed `dev_mode=False` overriding env var (changed default to `None`)
- Fixed `os.environ` leak between tests in CLI
- Fixed `html.escape()` crash on non-string detail (pydantic validation)

**Tests:**
- Added 42 new tests covering dev mode, ASGI middleware errors, responsive CSS, XSS, and client info
- Total test count: 748 (up from 706)

### v3.1.2 — Security & Bug Fix Release

**Security Fixes:**
- Fixed monitoring dashboard authentication bypass (token validation)
- Added authentication to all monitoring API endpoints
- Fixed XSS vulnerabilities in monitoring dashboard HTML output
- Added CSRF protection on monitoring login form
- Fixed OpenAPI Swagger/ReDoc XSS via `openapi_url` parameter
- Fixed Content-Disposition header injection via unescaped filename
- Added token expiration (24 hours) for monitoring sessions

**Bug Fixes:**
- Fixed `.env` file not loaded when running via `fenrir` CLI (vs `python -m fenrir.cli`)
- Fixed `response-times` API endpoint passing wrong argument to function
- Fixed `int()` conversion without error handling causing 500 errors
- Fixed config environment vars ignored when `enabled=True` passed
- Fixed `body.decode()` crash on non-UTF-8 request bodies
- Fixed default secret key hardcoded (now generates random if not set)
- Fixed JSONResponse import error when used outside request context
- Fixed `session.pop()` always marking session as modified
- Fixed Redis session async deadlock with proper timeout error
- Fixed `_load_data()` overwriting sites configuration
- Fixed CSRF cookie not being sent back (changed path to `/`)
- Fixed CSRF token not refreshed on failed login attempts

**Improvements:**
- Added `html.escape()` for all monitoring dashboard HTML output
- Added `try/except` for query parameter int conversions
- Added Secure cookie flag support via `MONITORING_SECURE_COOKIES` env var
- Added health check URL validation (only configured sites allowed)
- Added error handling for disk write failures in monitoring data
- Added warning when default password is used
- Added parallel health checks using `asyncio.gather()`
- Added JavaScript `escapeHtml()` for client-side DOM injection
- Added `MONITORING_ALLOW_DEFAULT_PASSWORD` env var override
- Added OSError handling for monitoring data directory creation
- Added `send_file()` streaming for large files via `FileResponse`
- Added `DefaultJSONProvider` fallback for `JSONResponse` outside request context

**Tests:**
- Added 37 new tests covering security fixes and edge cases
- Fixed all test warnings (deprecated per-request cookies in httpx)
- Total test count: 706 (up from 669)

### v3.1.1 — Bug Fix Release

**Bug Fixes:**
- Fixed `fenrir.monitoring` subpackage not included in package distribution (`pyproject.toml` packages list)

### v3.1.0 — Monitoring Features

Added built-in monitoring dashboard:

**New Features:**
- Monitoring dashboard with health checks, traffic analysis, and alerts
- CLI commands for enable/disable monitoring
- bcrypt password hashing for secure authentication
- Async health checks using thread pool
- Uptime statistics endpoint (`/monitoring/api/uptime`)
- Response time history endpoint (`/monitoring/api/response-times`)
- Hourly traffic breakdown endpoint (`/monitoring/api/hourly`)
- Comprehensive summary endpoint (`/monitoring/api/summary`)
- Enhanced dashboard with uptime percentage display
- `--disable-dashboard` flag for Asteri built-in dashboard

**Bug Fixes:**
- Fixed unused import in monitoring routes
- Fixed invalid integer parsing in alerts API
- Fixed blocking call in health check (now async)
- Fixed Response constructor parameter mismatch

---

### v3.0.0 — Major Bug Fix & Architecture Release

Fixed 21 bugs, added 46 new tests, and introduced architecture improvements:

**HIGH SEVERITY Fixes (7)**
- Fixed `routing.py`: Converter keyword as param name producing `param_name=""`.
- Fixed `routing.py`: `<path>` converter now recurses into child nodes at all possible depths, enabling routes like `/api/<path:resource>/details` to match correctly.
- Fixed `app.py`: Global teardown functions no longer run twice — deduplication via `seen` set.
- Fixed `app.py`: WebSocket handlers now properly set `_app_ctx_var` so `current_app` works inside websocket handlers.
- Fixed `dependencies.py`: Plain default params (e.g. `page: int = 1`) now return the actual default value instead of `None`.
- Fixed `dependencies.py`: `Annotated[T, Query()]` with function default now preserves the default value.
- Fixed `compat.py`: WSGI response body iteration now runs in a thread executor via `run_in_executor`, preventing event loop blocking.

**MEDIUM SEVERITY Fixes (8)**
- Fixed `app.py`: `_coerce_response` no longer infinitely recurses on 4+ element tuples — serializes as JSON array.
- Fixed `app.py`: Streaming error now always sends `more_body=False` frame, ensuring complete ASGI responses.
- Fixed `response.py`: `text` property returns `""` instead of `None` for empty bodies.
- Fixed `security.py`: `HTTPDigest` now returns a parsed dict instead of raw header string.
- Fixed `openapi.py`: Path parameter detection now checks both `param_name` and `alias`.
- Fixed `pagination.py`: URL building now deduplicates query params using `urllib.parse` instead of blind appending.
- Fixed `helpers.py`: `Content-Disposition` filename is now properly quoted.
- Fixed `signals.py`: Async signal results are now collected as task objects.

**LOW SEVERITY Fixes (6)**
- Removed dead code `_WsgiMount` exception and `_wsgi_handler` from `app.py`.
- Fixed unused `resp` variable in websocket path — now passed to `resolve_parameters`.
- Removed dead code `regex_segments` from `routing.py` `RouteTrie.insert()`.
- Fixed `templating.py`: Removed destructive `os.makedirs` side effect from `Jinja2Renderer.__init__`.
- Fixed `context.py`: Added `hasattr` guard for `do_teardown_appcontext` in `AppContext.__exit__`.
- Fixed `views.py`: `req.method` can no longer cause `AttributeError` — defaults to `"GET"` when `None`.

**Architecture Improvements**
- Added `BodyLimitMiddleware`: Rejects requests exceeding configurable max body size (default 10 MB), now enforces actual body size via chunk monitoring (not just Content-Length header).
- Added `CSRFMiddleware`: CSRF token validation for state-changing HTTP methods, with automatic token generation and cookie injection (`auto_generate=True` by default).
- Fixed `GZipMiddleware`: Streaming compression for `StreamingResponse` (on-the-fly chunk compression); fixed `_is_compressible()` to only compress explicit text-based types (was incorrectly compressing all `application/*` and `image/*`).
- Added `inspect.signature()` caching via `_get_cached_signature()` in `dependencies.py`, now used by `resolve_parameters()` for optimal parameter resolution.
- Added OpenAPI schema caching in `app.openapi()` — cached after first call, invalidated on route changes.
- Fixed `CORSMiddleware`: Wildcard origin with credentials now echoes the specific origin per CORS spec.
- Fixed `RateLimitMiddleware`: Redis backend now checks limit before adding request (matching in-memory behavior).
- Fixed `app.py`: Lifespan handler now returns after startup failure instead of looping forever.

**New Tests (46 tests)**
- PATCH/PUT/DELETE method routing + 405 on wrong method (7 tests)
- HTTPDigest auth parsing: success, missing header, wrong scheme, auto_error=False, field parsing (5 tests)
- OAuth2AuthorizationCodeBearer: success, missing, auto_error=False (3 tests)
- OpenIDConnect: success, missing, wrong scheme, auto_error=False, model (5 tests)
- Rate limiting via Redis backend: under limit, over limit, different keys (3 tests)
- GZip + streaming response (2 tests)
- 4+ element tuple response coercion (4 tests)
- Malformed JSON body + wrong content-type with strict mode (3 tests)
- Lifespan scope handling: startup/shutdown, startup failure (2 tests)
- CORS wildcard + credentials edge case (2 tests)
- Signature caching verification (3 tests)
- OpenAPI schema caching (2 tests)
- CSRF middleware auto-token generation: GET sets cookie, POST without token rejected, POST with valid token accepted, auto_generate=False (4 tests)
- GZip streaming compression: chunks compressed on-the-fly (1 test)

### v2.3.5 — Bug Fix & Changelog Update
- Updated changelog to accurately reflect version history
- All version references synchronized across codebase

### v2.3.4 — Bug Fix Release
- Fix server crash: `fenrir run` was passing wrong `app_path` (`fenrir.app:_active_app`) to Asteri worker, causing `'NoneType' object is not callable`
- Fix Python 3.8 support: replaced `asyncio.to_thread` with `fenrir.compat.to_thread` shim
- Updated all version strings across codebase

### v2.3.3 — 🚫 Retracted
- Published with incomplete version updates, superseded by v2.3.4

### v2.3.2 — Architecture & Performance Upgrade

Major architecture improvements, new features, and performance optimizations:

**Architecture Improvements**
- **Trie-Based Routing**: Replaced O(n) linear route matching with O(k) trie-based routing. Route lookup now scales with path depth, not total route count.
- **Context Vars Migration**: Removed `sys._fenrir_active_app` hack, replaced with proper `contextvars.ContextVar` for thread/async-task-safe app context.

**New Components**
- **Connection Pooling (`fenrir.pool`)**: Generic `ConnectionPool` and `DatabasePool` with health checks, retry logic, automatic connection recycling, and configurable pool sizes.
- **HTTP/2 Push (`fenrir.http2`)**: `HTTP2Push` utility for server push with Link headers, auto-push decorators, and resource type guessing.
- **WebSocket Authentication (`fenrir.security`)**: `WebSocketTokenAuth` dependency for token-based WebSocket authentication via headers or query parameters.

**New Features**
- **Streaming Request Body**: `request.stream_body()` method for memory-efficient processing of large uploads without buffering.
- **Per-User Rate Limiting**: `key_func` parameter in `RateLimitMiddleware` for custom rate limiting keys (user ID, API key, etc.).
- **Distributed Rate Limiting**: Redis backend support for `RateLimitMiddleware` using sliding window algorithm.

**Performance Optimizations**
- **GZip Compression Level**: Default `compresslevel` changed from 9 to 6 for optimal CPU/ratio trade-off.
- **Redis Rate Limiter**: Uses `time.monotonic()` instead of `time.time()` for clock-safe operation, with unique IDs to prevent collisions.
- **Deprecated API Fix**: Replaced deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()` in WSGI adapter.

**Bug Fixes**
- Fixed missing `import sys` in `app.py` that silently broke root_path detection.
- Fixed stale `sys._fenrir_active_app` references in `views.py` and `templating.py`.
- Fixed inconsistent version strings across `pyproject.toml`, `__init__.py`, and `app.py`.
- Fixed unused `import asyncio` in `falcon.py`.
- Removed private `Semaphore._value` access from `Pool.stats`.

**New Exports**
- `RouteTrie`, `WebSocketTokenAuth`, `ConnectionPool`, `DatabasePool`, `HTTP2Push`

### v2.2.2 — Major Feature Update

New middleware, session backends, pagination, and more:

**New Middleware (`fenrir.middleware`)**
- **CORSMiddleware**: Full CORS support for HTTP and WebSocket with configurable origins, methods, headers, credentials, and max-age.
- **GZipMiddleware**: Automatic gzip compression for responses above a configurable size threshold.
- **RequestIDMiddleware**: Auto-generates unique request IDs or forwards client-provided IDs via configurable header.
- **RateLimitMiddleware**: Sliding-window rate limiter per client IP with configurable limits and block status code.

**New Session Backends (`fenrir.sessions`)**
- **InMemorySessionInterface**: In-memory session storage with TTL expiration, suitable for single-process apps and testing.
- **RedisSessionInterface**: Redis-backed session storage with support for both sync (`fakeredis`) and async (`redis.asyncio`) clients. Install with `pip install fenrir-framework[redis]`.

**New Pagination Utilities (`fenrir.pagination`)**
- **PaginationParams**: Pydantic model for query parameters (`page`, `page_size`, `sort_by`, `sort_order`).
- **paginate()**: Utility to paginate SQLAlchemy-style query results with metadata.
- **paginate_dict()**: Utility to paginate lists of dictionaries.

**New Features**
- **WebSocket per-route timeout**: `@app.websocket("/ws", timeout=5.0)` raises `WebSocketTimeout` if no message received within the timeout.
- **Multiple response models per status**: `response_models={200: SuccessModel, 404: ErrorModel}` applies different models based on the actual response status code.

**Improvements**
- ASGI middleware stack is now built once and cached, with automatic invalidation when new middleware is added.
- Zero deprecation warnings across the entire test suite (528 tests).

### v1.2.2 — Logo & Favicon Patch

High-quality logo assets and resolved CLI template favicon issues:

- **High-Resolution Logo**: Updated `logo.png` asset to a high-fidelity image for sharper rendering in documentation and templates.
- **Favicon Resolution**: Ensured favicon is correctly rendered and copied during project scaffolding (`fenrir new`) from the package assets.

### v1.2.1 — Packaging & Asset Integration Patch

Logo and favicon assets are now properly included in the package distribution:

**Logo Asset Packaging**
- **Issue**: `fenrir new` command failed to copy logo and favicon files when creating new projects outside the main repository.
- **Root cause**: Logo files (`logo.png`, `logo.jpg`) were stored in the repository root, not within the `fenrir/` package directory, so they were not included when the package was installed via PyPI.
- **Fix**: 
  - Moved `logo.png` and `logo.jpg` from repository root to `fenrir/` package directory.
  - Added `[tool.setuptools.package-data]` configuration in `pyproject.toml` to include image files: `fenrir = ["logo.png", "logo.jpg"]`.
  - Updated `fenrir/cli.py` `cmd_new()` function to look for logos in the fenrir package directory first, with fallbacks for development mode.
- **Result**: All tests pass (528 unit tests). `fenrir new` now works correctly in all environments.

### v1.1.1 — Python 3.8–3.10 Full Compatibility Patch

Five test failures on Python 3.8 CI were identified and patched:

**1. `RuntimeError: Working outside of request context` (session, redirect in sync handlers)**
- **Root cause**: `loop.run_in_executor()` does **not** propagate `contextvars` by default. Sync route handlers using `session[...]` or `redirect()` lost the request context when moved into the executor thread.
- **Fix**: `fenrir/compat.py` — polyfill now calls `contextvars.copy_context().run(func)` instead of passing `func` directly to the executor.

**2. `AssertionError: {'user': None} != {'user': 'Alice'}` (Annotated[str, Header()])**
- **Root cause**: `typing.get_origin(typing_extensions.Annotated[...])` returns `None` on Python 3.8, so `Annotated` parameters were silently ignored during dependency resolution.
- **Fix**: `fenrir/compat.py` — export `get_origin`/`get_args` from `typing_extensions` (which correctly handles its own `Annotated`). `fenrir/dependencies.py` and `fenrir/openapi.py` now import these from `fenrir.compat`.

**3. `AssertionError: {'content_type': ''} != {'content_type': 'text/plain'}` (file upload)**
- **Root cause**: `python-multipart < 0.0.21` (installed on Python 3.8–3.10 CI runners) did not pass `content_type` into `File.__init__`, so `file.content_type` did not exist.
- **Fix**: `fenrir/request.py` — intercepts the parser's `on_header_field`/`on_header_value`/`on_headers_finished` callbacks to capture the `Content-Type` of each multipart part before the `File` object is constructed, and injects it as a fallback.

**4. `AssertionError: 'target' == '/nested/target'` (relative redirect)**
- Resolved as a side-effect of fix #1 (contextvars propagation restores `request.path` inside the executor thread).

**5. CI timeout on Python 3.9 (gevent build)**
- The Python 3.9 job was cancelled mid-build because compiling `gevent` took too long. This is an infrastructure concern, not a code issue; no code change required.

### v1.1.0 — CI/CD & Centering Fix
- Added **GitHub Actions** workflow for automated testing across Python 3.8–3.13.
- Fixed centering of `PROJECT CREATED SUCCESSFULLY` badge and logo in scaffolded template.
- Added **RFC 7231 HEAD** method compliance.
- Added `itsdangerous` and `python-multipart` as explicit core dependencies.

### v0.1.0 — Initial Release
- Core ASGI framework with Flask, FastAPI, Sanic, Falcon, and Bottle hybridization.
- 528 automated unit tests.
- Premium CLI tooling (`run`, `routes`, `shell`, `bench`, `new`, `info`).
- Auto-generated OpenAPI/Swagger documentation.
- WebSocket and Server-Sent Events support.

---

## 📜 License

Fenrir is open-sourced software licensed under the [MIT License](LICENSE).
