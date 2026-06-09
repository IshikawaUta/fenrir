<p align="center">
  <img src="https://raw.githubusercontent.com/IshikawaUta/fenrir/refs/heads/main/logo.jpg" alt="Fenrir Logo" width="500px"/>
</p>

# Fenrir Web Framework

[![PyPI version](https://img.shields.io/pypi/v/fenrir-framework.svg?color=blueviolet)](https://pypi.org/project/fenrir-framework/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-528%20Passed-brightgreen.svg)](https://github.com/IshikawaUta/fenrir/actions)
[![CI](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml/badge.svg)](https://github.com/IshikawaUta/fenrir/actions/workflows/test.yml)
[![Performance](https://img.shields.io/badge/Performance-High--Speed%20ASGI-orange.svg)]()

**Fenrir** is a state-of-the-art, high-performance, hybrid Python web framework built on top of modern ASGI specifications. It elegantly merges the best programming paradigms from Python's most popular web frameworks (**Flask**, **FastAPI**, **Sanic**, **Falcon**, and **Bottle**) into a single unified workspace, powered locally by the premium **Asteri v2.2.2** application server.

Whether you prefer the automatic Pydantic validation of FastAPI, the seamless context-locals of Flask, the raw class-based speed of Falcon, or the robust background task model of Sanic, **Fenrir** allows you to leverage them all simultaneously in the same codebase.

---

## 📦 Installation

Install directly from **PyPI**:

```bash
pip install fenrir-framework
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
*   **🧩 Framework Hybridization**:
    *   **FastAPI Paradigm**: Native Pydantic v2 data validation, `Annotated` type decorators, automated parameter resolution (`Query`, `Path`, `Header`, `Cookie`, `Body`), dynamic dependency injection (`Depends`), and automated `response_model` serialization.
    *   **Flask Paradigm**: Thread/Task-safe context locals (`request`, `g`, `session`), Jinja2 template rendering (`render_template`), and request teardown hooks.
    *   **Falcon Paradigm**: Class-based resource controllers (`on_get`, `on_post`), before/after hooks, and in-place response mutation.
    *   **Sanic Paradigm**: Global `sys.modules` patching (`install_sanic_compat()`), standard response helpers (`json`, `text`, `html`, `raw`, `redirect`), lifecycle listeners (`before_server_start`, etc.), and a background event scheduler (`app.add_task`).
    *   **Bottle Paradigm**: Built-in WSGI-to-ASGI wrapper and legacy mount adapter (`app.mount_wsgi()`) to run old WSGI applications at ASGI speeds.
*   **📖 Auto-Generated OpenAPI Docs**: Interactive **Swagger UI** (`/docs`) and **ReDoc** (`/redoc`) instantly generated from your Pydantic schemas and route metadata.
*   **🔌 Modern Communications**: Out-of-the-box support for **WebSockets** and **Server-Sent Events (SSE)**.
*   **🛠️ Premium CLI Tooling**: Visual route tables, interactive app shell, in-memory benchmarking suite, project scaffolding, and environment system inspection.
*   **🐍 Python 3.8–3.13 Compatible**: Full backward compatibility ensured via `typing_extensions` polyfills for `Annotated`, `get_origin`, `get_args`; and a `contextvars`-aware `asyncio.to_thread` shim.

---

## 🚀 Quick Start (The Hybrid Power)

Here is a simple example (`demo_app.py`) showcasing how Flask, FastAPI, Falcon, and Sanic styles coexist harmoniously in a single application:

```python
import logging
from pydantic import BaseModel
from fenrir import (
    Fenrir, Blueprint, request, g, Depends, Query, Header,
    render_template, Response, Form, File, UploadFile,
    WebSocket, WebSocketDisconnect
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo")

# Initialize the Hybrid App
app = Fenrir(title="Fenrir Hybrid Demo", version="2.2.2")

# --- 1. FastAPI-Style Validation & DI ---
class UserRegister(BaseModel):
    username: str
    email: str
    age: int

async def verify_api_key(x_api_key: str = Header(default=None)):
    if x_api_key != "super-secret-key":
        logger.warning("Invalid API key attempt")
    return x_api_key

# --- 2. Flask-Style Routing & Context-Locals ---
@app.get("/")
async def home():
    name = request.args.get("name", "Fenrir Developer")
    return render_template("index.html", name=name)

# --- 3. Falcon-Style Class-Based Resources ---
class ItemResource:
    async def on_get(self, req, resp, item_id: int):
        resp.status = 200
        resp.media = {"item_id": item_id, "style": "Falcon Resource"}

app.add_route("/items/<item_id:int>", ItemResource())

# --- 4. Sanic-Style Listeners & Background Tasks ---
@app.listener("before_server_start")
async def setup_db(app_instance):
    logger.info("Initializing mock database...")

@app.middleware("request")
async def log_request(req):
    logger.info(f"Incoming: {req.method} {req.path}")
    g.user_role = "guest"  # Share state using Flask-style 'g'

# Run with Asteri ASGI server
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=2)
```

---

## 💻 CLI Command Reference

Fenrir comes packed with a high-fidelity, visually rich command-line tool. Start the CLI by executing `fenrir` or `python -m fenrir.cli`.

### 1. `fenrir run`
Serve your application locally. Powered by **Asteri v2.2.2**, supporting dynamic multiprocessing, worker management, and live hot-reloading.
```bash
fenrir run demo_app:app --port 8000 --dev
```
*   **Flags**:
    *   `-H`, `--host`: Host bind address (default: `127.0.0.1`).
    *   `-p`, `--port`: Port number (default: `8000`).
    *   `-w`, `--workers`: Number of concurrent workers (default: `1`).
    *   `-d`, `--dev` / `--reload`: Active development mode with auto-reload.

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

---

## 🧪 Comprehensive Test Suite

Fenrir is thoroughly covered by an automated test suite comprising **528 tests** validating every single component, compat namespace, file upload, routing detail, and CLI functionality. The suite runs automatically via **GitHub Actions** on every push across Python **3.8 – 3.13**.

Run the test suite locally:

```bash
PYTHONPATH=. pytest -v
```

### Output:
```text
======================= 528 passed, 1 skipped in 3.4s ========================
```

---

## 🔄 Changelog

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
