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

import httpx
import pytest
from pydantic import BaseModel

from fenrir import (
    Annotated,
    APIRouter,
    BackgroundTasks,
    Fenrir,
    FileResponse,
    Header,
    PlainTextResponse,
    Query,
    StreamingResponse,
    WsgiToAsgi,
    bottle,
    install_bottle_compat,
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


# ── OpenAPI XSS Prevention ──────────────────────────────────────


def test_swagger_html_escapes_xss_in_url():
    from fenrir.openapi import get_swagger_html
    html = get_swagger_html(openapi_url="http://x.com/'+alert(1)+'")
    # The single quotes should be escaped, preventing JS breakout
    assert "'+alert(1)+'" not in html
    # html.escape converts ' to &#x27; or similar
    assert "alert" not in html or "&" in html


def test_redoc_html_escapes_xss_in_url():
    from fenrir.openapi import get_redoc_html
    html = get_redoc_html(openapi_url='http://x.com/" onmouseover="alert(1)')
    # The double quotes should be escaped, preventing attribute breakout
    assert 'onmouseover="alert(1)"' not in html


def test_swagger_html_escapes_xss_in_title():
    from fenrir.openapi import get_swagger_html
    html = get_swagger_html(title="<img onerror=alert(1)>")
    # HTML tags should be escaped
    assert "<img" not in html
    assert "&lt;" in html


def test_swagger_html_normal_url_passthrough():
    from fenrir.openapi import get_swagger_html
    html = get_swagger_html(openapi_url="/openapi.json")
    assert "url: '/openapi.json'" in html


# ── Content-Disposition Sanitization ─────────────────────────────


def test_file_response_sanitizes_quote_in_filename(tmp_path):
    f = tmp_path / 'file"name.txt'
    f.write_text("content")
    resp = FileResponse(str(f), filename='file"name.txt')
    assert 'file"name.txt' not in resp.headers.get("content-disposition", "")
    assert 'filename="filename.txt"' in resp.headers.get("content-disposition", "")


def test_file_response_sanitizes_crlf_in_filename(tmp_path):
    f = tmp_path / "normal.txt"
    f.write_text("content")
    resp = FileResponse(str(f), filename="a\r\nb.txt")
    assert "\r" not in resp.headers.get("content-disposition", "")
    assert "\n" not in resp.headers.get("content-disposition", "")


def test_send_file_attachment_sanitizes_filename(tmp_path):
    from fenrir.helpers import send_file
    f = tmp_path / "normal.txt"
    f.write_text("content")
    resp = send_file(str(f), as_attachment=True, download_name='file"name.txt')
    assert 'file"name.txt' not in resp.headers.get("content-disposition", "")


# ── JSONResponse Outside Request Context ─────────────────────────


def test_json_response_outside_request_context():
    from fenrir.response import JSONResponse
    resp = JSONResponse({"key": "value", "number": 42})
    assert resp.status == 200
    body = resp.body if isinstance(resp.body, str) else resp.body.decode()
    # orjson produces compact JSON without spaces
    assert '"key"' in body
    assert '"value"' in body
    assert '"number"' in body
    assert '42' in body


# ── Session Modified Flag ────────────────────────────────────────


def test_session_pop_existing_key_sets_modified():
    from fenrir.sessions import SessionMixin
    s = SessionMixin({"a": 1})
    s.modified = False
    s.pop("a")
    assert s.modified is True


def test_session_pop_missing_key_no_modified():
    from fenrir.sessions import SessionMixin
    s = SessionMixin({"a": 1})
    s.modified = False
    s.pop("b")
    assert s.modified is False


def test_session_mixin_all_modified_flags():
    from fenrir.sessions import SessionMixin
    s = SessionMixin()

    s.modified = False
    s["x"] = 1
    assert s.modified is True

    s.modified = False
    del s["x"]
    assert s.modified is True

    s.modified = False
    s.clear()
    assert s.modified is True

    s.modified = False
    s.update({"y": 2})
    assert s.modified is True


# ── send_file Edge Cases ─────────────────────────────────────────


def test_send_file_as_attachment_returns_file_response(tmp_path):
    from fenrir.helpers import send_file
    f = tmp_path / "test.txt"
    f.write_text("hello")
    resp = send_file(str(f), as_attachment=True)
    assert isinstance(resp, FileResponse)


def test_send_file_filelike_object():
    import io

    from fenrir.helpers import send_file
    data = io.BytesIO(b"hello world")
    resp = send_file(data)
    assert resp.status == 200


def test_send_file_missing_raises_404():
    from fenrir.exceptions import HTTPNotFound
    from fenrir.helpers import send_file
    with pytest.raises(HTTPNotFound):
        send_file("/nonexistent/path/file.txt")
