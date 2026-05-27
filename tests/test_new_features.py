"""Tests for new built-in features:
- StreamingResponse / FileResponse / PlainTextResponse
- BackgroundTasks
- response_model serialization
- Annotated param style
- add_middleware (ASGI-style)
- mount_wsgi (Bottle / WSGI apps)
- Route metadata (tags, summary, deprecated, responses)
"""
import os
import tempfile
import pytest
import httpx
from pydantic import BaseModel
from fenrir import (
    Fenrir,
    Annotated,
    Query,
    Header,
    Body,
    Depends,
    BackgroundTasks,
    StreamingResponse,
    FileResponse,
    PlainTextResponse,
    WsgiToAsgi,
    install_bottle_compat,
    Bottle,
    bottle,
    APIRouter,
)


# ─────────────────────────────────────────────
# StreamingResponse
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_streaming_response_async_gen():
    app = Fenrir()

    @app.get("/stream")
    async def stream():
        async def gen():
            for i in range(3):
                yield f"chunk{i}"
        return StreamingResponse(gen(), media_type="text/plain")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/stream")
    assert r.status_code == 200
    assert r.text == "chunk0chunk1chunk2"


@pytest.mark.anyio
async def test_streaming_response_sync_gen():
    app = Fenrir()

    @app.get("/stream")
    async def stream():
        def gen():
            yield b"hello "
            yield b"world"
        return StreamingResponse(gen(), media_type="text/plain")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/stream")
    assert r.status_code == 200
    assert r.text == "hello world"


# ─────────────────────────────────────────────
# FileResponse
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_file_response():
    app = Fenrir()

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("hello file")
        fname = f.name

    try:
        @app.get("/file")
        async def serve():
            return FileResponse(fname, content_disposition_type="inline")

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/file")
        assert r.status_code == 200
        assert r.text == "hello file"
        assert "text/plain" in r.headers["content-type"]
    finally:
        os.unlink(fname)


# ─────────────────────────────────────────────
# PlainTextResponse
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_plain_text_response():
    app = Fenrir()

    @app.get("/txt")
    async def txt():
        return PlainTextResponse("hello plain")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/txt")
    assert r.status_code == 200
    assert r.text == "hello plain"
    assert "text/plain" in r.headers["content-type"]


# ─────────────────────────────────────────────
# BackgroundTasks
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_background_tasks_run_after_response():
    executed = []
    app = Fenrir()

    def record(msg: str):
        executed.append(msg)

    @app.post("/notify")
    async def notify(tasks: BackgroundTasks):
        tasks.add_task(record, "bg-ran")
        return {"status": "queued"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/notify")
    assert r.status_code == 200
    assert r.json() == {"status": "queued"}
    # Background task should have run by now (same event loop, awaited after send)
    assert "bg-ran" in executed


@pytest.mark.anyio
async def test_background_tasks_async():
    executed = []
    app = Fenrir()

    async def async_record(msg: str):
        executed.append(msg)

    @app.get("/bg-async")
    async def ep(tasks: BackgroundTasks):
        tasks.add_task(async_record, "async-bg")
        return "ok"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/bg-async")
    assert "async-bg" in executed


# ─────────────────────────────────────────────
# response_model serialization
# ─────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    name: str


class UserPrivate(BaseModel):
    id: int
    name: str
    password: str


@pytest.mark.anyio
async def test_response_model_filters_fields():
    app = Fenrir()

    @app.get("/user", response_model=UserOut)
    async def get_user():
        return UserPrivate(id=1, name="Alice", password="secret")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/user")
    assert r.status_code == 200
    data = r.json()
    assert data == {"id": 1, "name": "Alice"}
    assert "password" not in data


@pytest.mark.anyio
async def test_response_model_from_dict():
    app = Fenrir()

    @app.get("/item", response_model=UserOut)
    async def get_item():
        return {"id": 42, "name": "Bob", "extra": "ignored"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/item")
    data = r.json()
    assert data["id"] == 42
    assert "extra" not in data


@pytest.mark.anyio
async def test_response_model_exclude_unset():
    class ItemOut(BaseModel):
        name: str
        price: float = 0.0

    app = Fenrir()

    @app.get("/item", response_model=ItemOut, response_model_exclude_unset=True)
    async def ep():
        # Return as dict — only "name" key present, so price should be excluded
        return {"name": "Widget"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/item")
    data = r.json()
    assert "name" in data
    assert "price" not in data  # not set → excluded


# ─────────────────────────────────────────────
# Annotated param style
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_annotated_query_param():
    app = Fenrir()

    @app.get("/search")
    async def search(q: Annotated[str, Query()] = "default"):
        return {"q": q}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/search?q=hello")
    assert r.json() == {"q": "hello"}


@pytest.mark.anyio
async def test_annotated_header_param():
    app = Fenrir()

    @app.get("/whoami")
    async def whoami(x_user: Annotated[str, Header()] = "anon"):
        return {"user": x_user}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/whoami", headers={"x-user": "Alice"})
    assert r.json() == {"user": "Alice"}


# ─────────────────────────────────────────────
# add_middleware (ASGI-style)
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_add_middleware_asgi_style():
    app = Fenrir()

    class TimingMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            async def patched_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-timing", b"yes"))
                    message = dict(message, headers=headers)
                await send(message)
            await self.app(scope, receive, patched_send)

    app.add_middleware(TimingMiddleware)

    @app.get("/ping")
    async def ping():
        return "pong"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/ping")
    assert r.headers.get("x-timing") == "yes"


# ─────────────────────────────────────────────
# mount_wsgi (Bottle integration)
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_mount_wsgi_bottle():
    """Mount a Bottle WSGI app inside a Fenrir ASGI app."""
    app = Fenrir()

    b = bottle.Bottle()

    @b.route("/hello")
    def b_hello():
        return "hello from bottle"

    app.mount_wsgi("/legacy", b)

    @app.get("/native")
    async def native():
        return {"framework": "fenrir"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        # Native Fenrir route
        r1 = await c.get("/native")
        assert r1.json() == {"framework": "fenrir"}

        # Mounted Bottle route
        r2 = await c.get("/legacy/hello")
        assert r2.status_code == 200
        assert "hello from bottle" in r2.text


@pytest.mark.anyio
async def test_wsgi_to_asgi_adapter():
    """WsgiToAsgi adapter standalone."""
    def simple_wsgi(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"wsgi works"]

    asgi_app = WsgiToAsgi(simple_wsgi)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app), base_url="http://test") as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert r.text == "wsgi works"


# ─────────────────────────────────────────────
# install_bottle_compat
# ─────────────────────────────────────────────

def test_install_bottle_compat():
    import sys
    # Remove if previously patched by another test
    sys.modules.pop("bottle", None)
    install_bottle_compat()
    import bottle as _b
    assert _b is bottle  # noqa: F811
    # Cleanup — restore state
    sys.modules.pop("bottle", None)


# ─────────────────────────────────────────────
# Route metadata in OpenAPI
# ─────────────────────────────────────────────

def test_route_metadata_in_openapi():
    app = Fenrir(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get(
        "/items",
        tags=["items"],
        summary="List items",
        description="Returns all items.",
        deprecated=True,
        response_model=UserOut,
        responses={404: {"description": "Not found"}},
    )
    async def list_items():
        return []

    schema = app.openapi()
    op = schema["paths"]["/items"]["get"]
    assert "items" in op.get("tags", [])
    assert op["summary"] == "List items"
    assert op["description"] == "Returns all items."
    assert op.get("deprecated") is True
    assert "404" in op["responses"]
    assert "200" in op["responses"]
    # response_model should be in components
    assert "UserOut" in schema["components"]["schemas"]


def test_apirouter_metadata_forwarded():
    router = APIRouter()

    @router.get("/ep", tags=["x"], summary="My ep")
    async def ep():
        return "ok"

    assert len(router.routes) == 1
    r = router.routes[0]
    assert r.tags == ["x"]
    assert r.summary == "My ep"
