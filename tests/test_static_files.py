"""Tests for StaticFiles ASGI application."""

import httpx
import pytest

from fenrir import Fenrir
from fenrir.static import StaticFiles


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def static_dir(tmp_path):
    """Create a temporary directory with test files."""
    (tmp_path / "hello.txt").write_text("Hello, World!")
    (tmp_path / "data.json").write_text('{"key": "value"}')
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    # Create subdirectory
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("Nested file")
    return tmp_path


@pytest.mark.anyio
async def test_serve_file(static_dir):
    """StaticFiles serves files from directory."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/hello.txt")
        assert res.status_code == 200
        assert res.text == "Hello, World!"
        assert res.headers["content-type"] == "text/plain"


@pytest.mark.anyio
async def test_404_for_missing_file(static_dir):
    """Returns 404 for files that don't exist."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/notfound.txt")
        assert res.status_code == 404


@pytest.mark.anyio
async def test_directory_traversal_blocked(static_dir):
    """Blocks directory traversal attacks."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Basic traversal
        res = await client.get("/static/../../etc/passwd")
        assert res.status_code == 404


@pytest.mark.anyio
async def test_directory_prefix_attack_blocked(tmp_path):
    """Blocks prefix attacks: /tmp/a should NOT match /tmp/ab."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "secret.txt").write_text("secret-a")

    dir_ab = tmp_path / "ab"
    dir_ab.mkdir()
    (dir_ab / "secret.txt").write_text("secret-ab")

    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(dir_a)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Should serve from /a
        res = await client.get("/static/secret.txt")
        assert res.status_code == 200
        assert res.text == "secret-a"

        # Should NOT be able to access /ab via prefix attack
        res = await client.get("/static/../ab/secret.txt")
        assert res.status_code == 404


@pytest.mark.anyio
async def test_etag_304(static_dir):
    """Returns 304 when ETag matches."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Get ETag
        res = await client.get("/static/hello.txt")
        assert res.status_code == 200
        etag = res.headers.get("etag")
        assert etag

        # Conditional request
        res2 = await client.get("/static/hello.txt", headers={"If-None-Match": etag})
        assert res2.status_code == 304


@pytest.mark.anyio
async def test_modified_since_304(static_dir):
    """Returns 304 when If-Modified-Since is valid."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Get Last-Modified
        res = await client.get("/static/hello.txt")
        assert res.status_code == 200
        last_modified = res.headers.get("last-modified")
        assert last_modified

        # Conditional request (use same time → should be 304)
        res2 = await client.get("/static/hello.txt", headers={"If-Modified-Since": last_modified})
        assert res2.status_code == 304


@pytest.mark.anyio
async def test_mime_type_detection(static_dir):
    """Detects MIME types correctly."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/data.json")
        assert res.headers["content-type"] == "application/json"

        res = await client.get("/static/image.png")
        assert res.headers["content-type"] == "image/png"


@pytest.mark.anyio
async def test_html_index(static_dir):
    """html=True serves index.html for directory paths."""
    (static_dir / "index.html").write_text("<h1>Index</h1>")
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/")
        assert res.status_code == 200
        assert res.text == "<h1>Index</h1>"


@pytest.mark.anyio
async def test_nested_file(static_dir):
    """Serves files from subdirectories."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/subdir/nested.txt")
        assert res.status_code == 200
        assert res.text == "Nested file"


@pytest.mark.anyio
async def test_content_length(static_dir):
    """Response includes correct Content-Length."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/static/hello.txt")
        assert res.status_code == 200
        assert res.headers["content-length"] == str(len(b"Hello, World!"))


@pytest.mark.anyio
async def test_integration_with_gzip(static_dir):
    """StaticFiles works with GZipMiddleware."""
    import gzip

    from fenrir.middleware import GZipMiddleware

    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))
    app.add_middleware(GZipMiddleware, minimum_size=0)

    # Use raw ASGI to avoid httpx auto-decompression
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/static/hello.txt",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"accept-encoding", b"gzip, deflate, br"),
        ],
        "server": ("test", 80),
        "scheme": "http",
    }
    raw_bytes = b""

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal raw_bytes
        if message["type"] == "http.response.body":
            raw_bytes += message.get("body", b"")

    await app(scope, receive, send)
    body = gzip.decompress(raw_bytes)
    assert body == b"Hello, World!"


@pytest.mark.anyio
async def test_nonexistent_directory():
    """Raises RuntimeError for nonexistent directory."""
    with pytest.raises(RuntimeError):
        StaticFiles(directory="/nonexistent/path/that/does/not/exist")


@pytest.mark.anyio
async def test_head_request_no_body(static_dir):
    """HEAD requests return headers but no body."""
    app = Fenrir()
    app.mount("/static", StaticFiles(directory=str(static_dir)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.head("/static/hello.txt")
        assert res.status_code == 200
        assert res.headers.get("content-length") == str(len(b"Hello, World!"))
        # httpx auto-decompresses, but body should be empty for HEAD
        assert res.text == ""


async def _call_static(files, scope):
    messages = []

    async def send(msg):
        messages.append(msg)

    await files(scope, None, send)
    return messages


@pytest.mark.anyio
async def test_non_http_scope(static_dir):
    files = StaticFiles(directory=str(static_dir))
    await files({"type": "websocket", "path": "/x"}, None, None)  # returns silently


@pytest.mark.anyio
async def test_traversal_direct(static_dir):
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/../../etc/passwd", "headers": [],
    })
    assert messages[0]["status"] == 404


@pytest.mark.anyio
async def test_html_index_subdir(static_dir):
    (static_dir / "subdir" / "index.html").write_text("sub-index")
    files = StaticFiles(directory=str(static_dir), html=True)
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/subdir", "headers": [],
    })
    assert messages[0]["status"] == 200


@pytest.mark.anyio
async def test_stat_oserror(static_dir, monkeypatch):
    import os

    import fenrir.static as smod

    real_to_thread = smod.to_thread

    async def fake_to_thread(func, *args, **kwargs):
        if func is os.stat:
            raise OSError("gone")
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(smod, "to_thread", fake_to_thread)
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt", "headers": [],
    })
    assert messages[0]["status"] == 404


@pytest.mark.anyio
async def test_directory_403(static_dir, monkeypatch):
    import fenrir.static as smod

    monkeypatch.setattr(smod.stat, "S_ISDIR", lambda mode: True)
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt", "headers": [],
    })
    assert messages[0]["status"] == 403


@pytest.mark.anyio
async def test_unknown_content_type(static_dir):
    (static_dir / "blob.zzunknown").write_bytes(b"x")
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/blob.zzunknown", "headers": [],
    })
    headers = dict(messages[0]["headers"])
    assert headers[b"content-type"] == b"application/octet-stream"


@pytest.mark.anyio
async def test_invalid_modified_since(static_dir):
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt",
        "headers": [(b"if-modified-since", b"not-a-date")],
    })
    assert messages[0]["status"] == 200


@pytest.mark.anyio
async def test_file_read_oserror(static_dir, monkeypatch):
    import builtins

    def _raise(*args, **kwargs):
        raise OSError("deleted")

    monkeypatch.setattr(builtins, "open", _raise)
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt", "headers": [],
    })
    assert messages[-1]["more_body"] is False


@pytest.mark.anyio
async def test_cache_control_default(static_dir):
    files = StaticFiles(directory=str(static_dir))
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt", "headers": [],
    })
    headers = dict(messages[0]["headers"])
    assert headers[b"cache-control"] == b"public, max-age=0"


@pytest.mark.anyio
async def test_cache_control_custom(static_dir):
    files = StaticFiles(directory=str(static_dir), cache_control="public, max-age=31536000, immutable")
    messages = await _call_static(files, {
        "type": "http", "method": "GET", "path": "/hello.txt", "headers": [],
    })
    headers = dict(messages[0]["headers"])
    assert headers[b"cache-control"] == b"public, max-age=31536000, immutable"
