"""Unit tests for fenrir.http2 edge paths."""
import pytest

from fenrir.http2 import HTTP2Push
from fenrir.response import HTMLResponse, JSONResponse, Response


def test_push_existing_link_header():
    push = HTTP2Push()
    resp = HTMLResponse("<html></html>")
    resp.headers["link"] = "<http://cdn/x.js>; rel=preload"
    out = push.push(resp, push_paths=["/style.css"])
    assert "<http://cdn/x.js>" in out.headers["link"]
    assert "/style.css" in out.headers["link"]
    assert out.headers["x-http2-push"] == "true"


def test_wrap_response_types():
    push = HTTP2Push()
    resp = Response(b"raw")
    assert push.push(resp, push_paths=["/a.css"]) is resp

    json_resp = push.push({"a": 1}, push_paths=["/b.css"])
    assert isinstance(json_resp, JSONResponse)

    raw_resp = push.push(123, push_paths=["/c.css"])
    assert raw_resp.body == b"123"


def test_guess_as_fallback():
    assert HTTP2Push._guess_as("/file.txt") == "fetch"
    assert HTTP2Push._guess_as("/noext") == "fetch"


@pytest.mark.anyio
async def test_auto_push_without_paths():
    push = HTTP2Push()

    @push.auto_push(static_url="/static")
    async def index():
        return "<html></html>"

    resp = await index()
    assert resp.headers.get("x-http2-push") is None
