"""Tests for GZipMiddleware streaming fix."""
import gzip
import zlib

import pytest
import httpx

from fenrir import Fenrir, Response, StreamingResponse, FileResponse
from fenrir.middleware import GZipMiddleware


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _raw_asgi_gzip_test(app, path="/stream"):
    """Run a raw ASGI test to capture the exact wire bytes (no auto-decompress)."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"accept-encoding", b"gzip, deflate, br"),
        ],
        "server": ("test", 80),
        "scheme": "http",
    }
    received = []
    response_started = False
    body_started = False
    raw_bytes = b""

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal response_started, body_started, raw_bytes
        if message["type"] == "http.response.start":
            response_started = True
        elif message["type"] == "http.response.body":
            raw_bytes += message.get("body", b"")

    await app(scope, receive, send)
    return raw_bytes


@pytest.mark.anyio
async def test_gzip_streaming_response():
    """Streaming response with GZip middleware produces valid gzip."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware, minimum_size=0)

    async def generate():
        for i in range(10):
            yield f"chunk-{i}\n"

    @app.get("/stream")
    async def stream():
        return StreamingResponse(generate(), media_type="text/plain")

    raw = await _raw_asgi_gzip_test(app)
    # Must be valid gzip
    body = gzip.decompress(raw)
    assert b"chunk-0" in body
    assert b"chunk-9" in body


@pytest.mark.anyio
async def test_gzip_streaming_valid_single_gzip_stream():
    """Multiple chunks compressed as streaming gzip must decompress as one stream."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware, minimum_size=0)

    async def generate():
        for i in range(20):
            yield "x" * 1000

    @app.get("/stream")
    async def stream():
        return StreamingResponse(generate(), media_type="text/plain")

    raw = await _raw_asgi_gzip_test(app)
    # This MUST NOT raise — proves it's a single valid gzip stream
    body = gzip.decompress(raw)
    assert len(body) == 20 * 1000


@pytest.mark.anyio
async def test_gzip_non_streaming_response():
    """Non-streaming Response still works with GZip."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware, minimum_size=10)

    @app.get("/json")
    async def json_endpoint():
        return {"message": "hello world " * 20}

    raw = await _raw_asgi_gzip_test(app, "/json")
    body = gzip.decompress(raw)
    assert b"hello world" in body


@pytest.mark.anyio
async def test_gzip_bypass_no_accept_encoding():
    """Requests without gzip in Accept-Encoding bypass compression."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware)

    @app.get("/data")
    async def data():
        return {"message": "hello world " * 20}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/data", headers={"Accept-Encoding": "identity"})
        assert res.status_code == 200
        assert res.headers.get("content-encoding") is None


@pytest.mark.anyio
async def test_gzip_bypass_non_compressible():
    """Non-compressible content types bypass GZip."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware)

    @app.get("/image")
    async def image():
        return Response(body=b"\x89PNG\r\n", content_type="image/png")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/image")
        assert res.status_code == 200
        assert res.headers.get("content-encoding") is None


@pytest.mark.anyio
async def test_gzip_bypass_status_204():
    """204 responses bypass GZip."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware)

    @app.get("/empty")
    async def empty():
        return Response(body=b"", status=204)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/empty")
        assert res.status_code == 204
        assert res.headers.get("content-encoding") is None


@pytest.mark.anyio
async def test_gzip_file_response(tmp_path):
    """FileResponse streaming with GZip produces valid gzip."""
    test_file = tmp_path / "test.txt"
    content = "Hello World! " * 1000
    test_file.write_text(content)

    app = Fenrir()
    app.add_middleware(GZipMiddleware, minimum_size=0)

    @app.get("/file")
    async def serve_file():
        return FileResponse(str(test_file), media_type="text/plain")

    raw = await _raw_asgi_gzip_test(app, "/file")
    body = gzip.decompress(raw)
    assert body == content.encode("utf-8")


@pytest.mark.anyio
async def test_gzip_streaming_small_chunks():
    """Small chunks (< minimum_size) in streaming mode still produce valid gzip."""
    app = Fenrir()
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    async def generate():
        for i in range(5):
            yield "tiny"

    @app.get("/stream")
    async def stream():
        return StreamingResponse(generate(), media_type="text/plain")

    raw = await _raw_asgi_gzip_test(app)
    assert raw[:2] == b"\x1f\x8b"  # gzip magic bytes
    body = gzip.decompress(raw)
    assert body == b"tinytinytinytinytiny"
