<p align="center">
  <img src="https://raw.githubusercontent.com/IshikawaUta/fenrir/refs/heads/main/logo.jpg" alt="Fenrir Logo" width="500px"/>
</p>

# Fenrir Web Framework

[![PyPI - Version](https://img.shields.io/pypi/v/fenrir-framework.svg)](https://pypi.org/project/fenrir-framework/)
[![Python Versions](https://img.shields.io/pypi/pyversions/fenrir-framework.svg)](https://pypi.org/project/fenrir-framework/)
[![License: MIT](https://img.shields.io/pypi/l/fenrir-framework.svg)](LICENSE)
[![Tests](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml/badge.svg)](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/IshikawaUta/fenrir/branch/main/graph/badge.svg)](https://codecov.io/gh/IshikawaUta/fenrir)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://app.codspeed.io/IshikawaUta/fenrir?utm_source=badge)
[![Security](https://img.shields.io/badge/%F0%9F%8C%88-zizmor-white?labelColor=white)](https://zizmor.sh/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/typing-mypy-2A6DB2.svg)](https://github.com/python/mypy)
[![Docker](https://img.shields.io/badge/Docker-GHCR-2496ED.svg)](https://github.com/IshikawaUta/fenrir/pkgs/container/fenrir)

**Fenrir** is a state-of-the-art, high-performance, hybrid Python web framework built on top of modern ASGI specifications. It elegantly merges the best programming paradigms from Python's most popular web frameworks (**Flask**, **FastAPI**, **Sanic**, **Falcon**, and **Bottle**) into a single unified workspace, powered locally by the premium **Asteri** application server.

Whether you prefer the automatic Pydantic validation of FastAPI, the seamless context-locals of Flask, the raw class-based speed of Falcon, or the robust background task model of Sanic, **Fenrir** allows you to leverage them all simultaneously in the same codebase.

---

## 📦 Installation

Install directly from **PyPI**:

```bash
pip install fenrir-framework
```

Optional extras:

```bash
pip install fenrir-framework[redis]      # Redis sessions & rate limiting
pip install fenrir-framework[orm]        # SQLite + PostgreSQL ORM (aiosqlite, asyncpg)
pip install fenrir-framework[graphql]    # Strawberry GraphQL support
pip install fenrir-framework[grpc]       # gRPC server/client support
pip install fenrir-framework[testing]    # HTTPX-based TestClient / fenrir bench
pip install fenrir-framework[all]        # everything above
```

Or install in development mode by cloning the repository:

```bash
git clone https://github.com/IshikawaUta/fenrir.git
cd fenrir
pip install -e ".[all]"
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
app = Fenrir(title="Fenrir Hybrid Framework Demo", version="4.3.1")

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

Fenrir v4.3.1 uses a trie-based routing index for O(k) route matching, where k is the path depth. This is significantly faster than linear O(n) matching when you have many routes.

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

## 🗄️ ORM

A lightweight async ORM for SQLite/PostgreSQL (aiosqlite/asyncpg) with
metaclass-based models, chained query filtering, ordering, and
SQL-injection-safe queries.

```python
from fenrir import Fenrir
from fenrir.orm import Database, Integer, Model, String

app = Fenrir()

class User(Model):
    __tablename__ = "users"
    id = Integer(primary_key=True)
    name = String(max_length=100)
    email = String(max_length=255, unique=True)

db = Database("sqlite:///app.db")   # or "postgresql://user:pass@host/db"
User.bind(db)
await db.create_all()

@app.get("/users/<int:user_id>")
async def get_user(user_id: int):
    user = await User.get(id=user_id)
    return {"user": user.to_dict() if user else None}

@app.get("/users")
async def list_users():
    return {"users": [u.to_dict() for u in await User.all()]}
```

Classmethods on models: `create`, `get`, `get_or_create`, `all`, `filter`,
`count`, `bulk_create`; `filter()`/`exclude()`/`order_by()`/`limit()`/`offset()`
chain into async terminators `all()`, `first()`, `count()`, `delete()`,
`update(**kwargs)`. Models support `auto_now`/`auto_now_add` datetime fields,
JSON fields, `save()`/`delete()`/`to_dict()` on instances, and transactions
via `async with db.transaction():`.

---

## 💾 Caching

Built-in caching with pluggable backends — `MemoryCache` (LRU + TTL),
`RedisCache` (uses SCAN, not KEYS), and `FileCache` (atomic writes).

```python
from fenrir import Fenrir
from fenrir.cache import Cache, MemoryCache

app = Fenrir()
cache = Cache(backend=MemoryCache(max_size=1000))

@app.get("/cached")
async def cached():
    value = await cache.get("key")
    if value is None:
        value = await compute_expensive_thing()
        await cache.set("key", value, ttl=60)
    return {"value": value}
```

---

## 📋 Queues & Jobs

Background job queue with retry/backoff/priority/timeout and a worker pool,
backed by `MemoryQueue` or `RedisQueue`.

```python
from fenrir import Fenrir
from fenrir.queue import Queue, Worker

app = Fenrir()
queue = Queue()

@queue.handler("send_email")
async def send_email(email: str):
    # send the email ...
    return {"sent_to": email}

@app.get("/enqueue")
async def enqueue():
    job = await queue.enqueue("send_email", email="a@b.com", max_retries=3)
    return {"job_id": job.id}

Worker(queue).start()   # processes jobs concurrently
```

Register job functions with the `@queue.handler("name")` decorator. Jobs
support retry with exponential backoff, priority ordering, timeouts, delays,
and cancellation.

---

## 🔐 Sessions

Flask-style `session` context-local backed by `InMemorySessionInterface`
(default) or `RedisSessionInterface` for distributed deployments.

```python
import redis.asyncio as aioredis
from fenrir import Fenrir, session
from fenrir.sessions import RedisSessionInterface

app = Fenrir()
app.config["SECRET_KEY"] = "change-me"                 # strong random value in prod
app.session_interface = RedisSessionInterface(
    redis_client=aioredis.from_url("redis://localhost:6379"),
    prefix="fenrir:",
)

@app.get("/login")
async def login():
    session["user"] = {"id": 1}
    return {"ok": True}
```

`SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`,
and `SESSION_COOKIE_NAME` are configured via `app.config[...]` (secure cookies
are enabled by default).

---

## 📢 Signals

A Flask-like signal system with named signals, sender filtering, and
sync/async receivers.

```python
from fenrir import Fenrir
from fenrir.signals import Namespace

app = Fenrir()
ns = Namespace()
user_created = ns.signal("user-created")

@user_created.connect
async def on_user_created(sender, **kwargs):
    print("New user:", kwargs["user"])

user_created.send(sender=app, user={"id": 1})   # sync; receivers may be async
```

---

## 📑 Pagination

`paginate()` wraps any sequence into a standardized paginated envelope with
`total`, `page`, `size`, `pages`, `has_next`/`has_prev`, and link URLs.

```python
from fenrir import Depends
from fenrir.pagination import PaginationParams, paginate

@app.get("/items")
async def items(page: PaginationParams = Depends(PaginationParams)):
    rows = await fetch_all_rows()          # your query
    return paginate(rows, page=page.page, size=page.size, base_url="/items")
```

---

## 🧰 Helpers

URL generation and file responses:

```python
from fenrir import Fenrir, redirect, send_file, send_from_directory, url_for

app = Fenrir()

@app.get("/users/<int:uid>")
async def profile(uid: int):
    return {"profile": uid}

@app.get("/go")
async def go():
    return redirect(url_for("profile", uid=42))       # → /users/42

@app.get("/download")
async def download():
    return send_file("reports.pdf", as_attachment=True, download_name="report.pdf")

@app.get("/static/<path:path>")
async def static_files(path: str):
    return send_from_directory("public", path)
```

---

## 🚦 HTTP Exceptions

Rich HTTP exception hierarchy that can be raised or returned; each carries an
HTTP status code and description.

```python
from fenrir import Fenrir, HTTPBadRequest, HTTPForbidden, HTTPNotFound

@app.get("/secure/<int:uid>")
async def secure(uid: int):
    if uid != 1:
        raise HTTPForbidden("You cannot access this resource.")
    return {"uid": uid}

@app.get("/missing")
async def missing():
    raise HTTPNotFound("This page does not exist.")
```

Catch exceptions with `@app.exception(...)` to return custom responses.

---

## 🗂️ Class-Based Views

`View` and `MethodView` base classes for organizing handlers by HTTP method.

```python
from fenrir import Fenrir, request
from fenrir.views import MethodView

app = Fenrir()

class UserView(MethodView):
    async def get(self, user_id: int):
        return {"method": "GET", "user_id": user_id}
    async def post(self):
        return {"method": "POST", "body": request.json}

app.add_route("/users/<int:user_id>", UserView())
```

---

## 📦 Response Classes

Explicit response types for streaming, files, redirects, and raw bodies:

```python
from fenrir import (
    Fenrir, FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
    RedirectResponse, StreamingResponse,
)

app = Fenrir()

@app.get("/json")
async def json_route():
    return JSONResponse({"ok": True})

@app.get("/html")
async def html_route():
    return HTMLResponse("<h1>Hello</h1>")

@app.get("/text")
async def text_route():
    return PlainTextResponse("plain text")

@app.get("/stream")
async def stream_route():
    return StreamingResponse(iter(b"chunk"))

@app.get("/old")
async def old_route():
    return RedirectResponse("/new", status_code=301)
```

---

## 🧪 Testing

Use the built-in `TestClient` (HTTPX-based) for in-process ASGI testing:

```python
import pytest
from myapp import app   # your Fenrir app

@pytest.mark.anyio
async def test_home():
    async with app.test_client() as client:
        r = await client.get("/")
        assert r.status_code == 200
```

`TestClient`/`FenrirTestClient` are available as `fenrir.TestClient` and
`from fenrir.testing import FenrirTestClient`. Requires the `testing` extra
(`pip install fenrir-framework[testing]`).

---

## 🔧 Environment Variables

Fenrir reads a `.env` file via `python-dotenv`. Core variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Secret key used to sign sessions/CSRF tokens. **Set a strong random value in production.** |
| `MONITORING_ENABLED` | Enable (`true`/`false`) the built-in monitoring dashboard. |
| `MONITORING_USER` | Monitoring dashboard username (default `admin`). |
| `MONITORING_PASSWORD` | Monitoring dashboard password (default `changeme`). |
| `MONITORING_SECRET_KEY` | Secret key for monitoring dashboard auth. |
| `MONITORING_SITES` | Comma-separated URLs for the monitoring health checks. |

See `.env.example` for the full template.

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

Fenrir is thoroughly covered by an automated test suite comprising **2,358 tests** (plus 6 intentional skips) validating every single component: trie-based routing, streaming body, connection pooling, HTTP/2 push, WebSocket authentication, rate limiting, HTTP digest/OAuth2/OpenID security schemes, PATCH/PUT/DELETE routing, lifespan handling, CSRF auto-token generation, streaming GZip compression, monitoring dashboard, dev mode debug page, ASGI middleware error handling, plugin system, hook system, lightweight ORM, caching system, queue/job system, GraphQL support, gRPC support, performance optimization module, CLI tooling, and the built-in monitoring dashboard.

**Coverage**: **99%** overall (8,208 statements, 2,792 branches) — every `fenrir` module at 100%. The suite runs automatically via **GitHub Actions** on every push across Python **3.8 – 3.13**, with ruff linting, mypy type-checking, and the coverage report uploaded to **Codecov**.

Run the test suite locally:

```bash
PYTHONPATH=. pytest -q
```

### Output:
```text
=============================== 2358 passed, 6 skipped in 466.34s (0:07:46) ================================
```

### Performance & Benchmarking

- **`benchmark.py`** — in-process comparison of Fenrir vs FastAPI vs Flask vs Falcon vs Sanic (import time, routing, JSON serialization, and ASGI request throughput). Run it in CI via the **Benchmark** workflow (results posted to the job summary) or locally with `python benchmark.py`.
- **CodSpeed** — micro-benchmarks in `tests/benchmarks/` (JSON serialization, router static/parametric/miss matching) track performance regressions on every PR via the **CodSpeed** workflow. Run them locally with:
  ```bash
  pip install pytest-codspeed
  pytest tests/benchmarks --codspeed
  ```
- **`fenrir bench`** — quick in-memory benchmark of your own app over ASGI (requires the `testing` extra):
  ```bash
  fenrir bench demo_app:app -i 1000 -t 5 -p / -m GET
  ```

### CI / CD

| Workflow | Purpose |
| --- | --- |
| `test.yml` | ruff + mypy lint; full suite with coverage on Python 3.8–3.13; Codecov upload |
| `codspeed.yml` | CodSpeed performance regression tracking |
| `benchmark.yml` | runs `benchmark.py` and posts results to the job summary |
| `zizmor.yml` | security audit of the GitHub Actions workflows themselves |
| `release.yml` | auto-creates a GitHub Release from the matching `CHANGELOG.md` section on `v*` tag push |
| `docker.yml` | builds and pushes multi-arch (amd64/arm64) images to GHCR |
| `publish.yml` | publishes wheels/sdist to PyPI on release (trusted publishing) |

All workflow actions are pinned to immutable commit SHAs and kept up to date by Dependabot.

---

## 🐳 Docker

An official runtime image is published to **GitHub Container Registry**:
`ghcr.io/ishikawauta/fenrir`.

```bash
docker pull ghcr.io/ishikawauta/fenrir

# Run the bundled demo app
docker run -p 8000:8000 ghcr.io/ishikawauta/fenrir

# Run your own app (mount it at /app and point APP_MODULE at it)
docker run -p 8000:8000 \
  -e APP_MODULE=myapp:app \
  -v "$PWD:/app" \
  ghcr.io/ishikawauta/fenrir
```

Configuration via environment variables: `APP_MODULE` (default `demo_app:app`),
`HOST` (default `0.0.0.0`), `PORT` (default `8000`), `WORKERS` (default `1`).
You can also pass an arbitrary command directly to the container. Build locally
with `docker build -t fenrir .`.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, test, lint
(`ruff`), type-check (`mypy`), and coverage instructions.

## 🔒 Security

Found a vulnerability? Please see [SECURITY.md](SECURITY.md) for our disclosure
policy and how to report issues.

## 📜 Code of Conduct

Please note that this project is released with a
[Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree
to abide by its terms.

## 📜 License

Fenrir is open-sourced software licensed under the [MIT License](LICENSE).
