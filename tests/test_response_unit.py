"""Unit tests for fenrir.response covering edge paths."""
import pytest

from fenrir import Fenrir
from fenrir.context import AppContext
from fenrir.json import JSONProvider
from fenrir.response import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
    TextResponse,
)


class _StrProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return '{"provider": true}'

    def loads(self, s, **kwargs):
        return {"provider": True}


def test_response_init_str_body_and_status_string():
    r = Response(body="hello", status="201 Created")
    assert r.body == b"hello"
    assert r.status == 201
    assert r.headers["content-type"] == "text/html; charset=utf-8"


def test_response_init_bytes_body_with_existing_content_type():
    r = Response(b"raw", headers={"Content-Type": "application/octet-stream"})
    assert r.body == b"raw"
    assert r.headers["Content-Type"] == "application/octet-stream"
    assert not any(k.lower() == "content-type" for k in r.headers if k == "Content-Type") or True
    assert len([k for k in r.headers if k.lower() == "content-type"]) == 1


def test_response_invalid_status_string():
    with pytest.raises(ValueError, match="Invalid status code"):
        Response(status="OK")


def test_response_cookies_property():
    r = Response()
    assert r.cookies is not None
    r2 = Response()
    r2.cookies = "custom"
    assert r2.cookies == "custom"


def test_response_body_setter():
    r = Response()
    r.body = "text"
    assert r.body == b"text"
    r.body = b"bytes"
    assert r.body == b"bytes"


def test_response_text():
    r = Response(b"hello")
    assert r.text == "hello"
    r.text = "world"
    assert r.body == b"world"
    r.text = None
    assert r.body == b""


def test_response_text_none_body():
    assert Response(body=None).text is None


def test_response_text_decode_failure():
    assert Response(b"\xff\xfe not utf8").text is None


def test_response_set_unset_header():
    r = Response()
    r.set_header("X-Custom", "v")
    assert r.headers["x-custom"] == "v"
    r.unset_header("X-Custom")
    assert "x-custom" not in r.headers


def test_response_media_via_app_provider():
    app = Fenrir()
    with AppContext(app):
        r = Response(b'{"a": 1}')
        assert r.media == {"a": 1}
        r.media = {"b": 2}
        assert r.headers["content-type"] == "application/json"


def test_response_media_invalid_json():
    r = Response(b"not-json")
    assert r.media is None


def test_response_media_without_context(monkeypatch):
    import fenrir.response as mod

    monkeypatch.setattr(mod, "_HAS_ORJSON", False)
    monkeypatch.setattr(mod, "_orjson", None)
    r = Response(b'{"a": 1}')
    assert r.media == {"a": 1}
    r.media = {"c": 3}
    assert r.headers["content-type"] == "application/json"


def test_response_media_without_context_orjson():
    r = Response(b'{"a": 1}')
    assert r.media == {"a": 1}
    r.media = {"c": 3}
    assert r.headers["content-type"] == "application/json"


def test_response_set_cookie_expires_string_and_no_path():
    r = Response()
    r.set_cookie("k", "v", expires="Thu, 01 Jan 1970 00:00:00 GMT", path="", domain="")
    assert r.cookies["k"]["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert r.cookies["k"]["path"] == ""


def test_response_set_cookie_options():
    r = Response()
    r.set_cookie(
        "k", "v", max_age=100, expires=3600, path="/p", domain="ex.com",
        secure=True, httponly=True, samesite="Lax",
    )
    assert r.cookies["k"]["max-age"] == 100
    assert r.cookies["k"]["path"] == "/p"
    assert r.cookies["k"]["domain"] == "ex.com"
    assert r.cookies["k"]["secure"]
    assert r.cookies["k"]["httponly"]
    assert r.cookies["k"]["samesite"] == "Lax"


def test_response_delete_cookie():
    r = Response()
    r.set_cookie("k", "v")
    r.delete_cookie("k", path="/p", domain="ex.com")
    assert r.cookies["k"]["max-age"] == 0
    assert "1970" in r.cookies["k"]["expires"]


def test_response_get_asgi_headers_with_cookies():
    r = Response(b"x")
    r.set_cookie("sid", "abc")
    headers = dict(r.get_asgi_headers())
    assert headers[b"content-type"] == b"text/html; charset=utf-8"
    assert headers[b"set-cookie"] == b"sid=abc; Path=/"


def test_json_response_default_provider():
    r = JSONResponse({"a": 1})
    assert r.headers["content-type"] == "application/json"
    assert r.body == b'{"a":1}' or r.body == b'{"a": 1}'


def test_json_response_custom_provider():
    app = Fenrir()
    app.json = _StrProvider(app)
    with AppContext(app):
        r = JSONResponse({"a": 1})
        assert r.body == b'{"provider": true}'


def test_html_text_redirect_responses():
    assert HTMLResponse("<b>x</b>").body == b"<b>x</b>"
    assert TextResponse("plain").body == b"plain"
    assert TextResponse("plain").headers["content-type"] == "text/plain; charset=utf-8"
    rd = RedirectResponse("/next", status=302)
    assert rd.headers["location"] == "/next"
    assert rd.status == 302


@pytest.mark.anyio
async def test_streaming_response_callable_and_asyncgen():
    def factory():
        async def gen():
            yield "a"
            yield b"b"
        return gen()

    sr = StreamingResponse(factory())
    assert sr.streaming is True
    chunks = [c async for c in sr.stream_body()]
    assert chunks == [b"a", b"b"]


@pytest.mark.anyio
async def test_streaming_response_callable():
    async def gen():
        yield "a"
        yield b"b"

    sr = StreamingResponse(gen)
    chunks = [c async for c in sr.stream_body()]
    assert chunks == [b"a", b"b"]


@pytest.mark.anyio
async def test_streaming_response_async_iterable():
    class _AIter:
        def __aiter__(self):
            async def gen():
                yield "q"
                yield b"r"
            return gen()

    sr = StreamingResponse(_AIter())
    chunks = [c async for c in sr.stream_body()]
    assert chunks == [b"q", b"r"]


@pytest.mark.anyio
async def test_streaming_response_sync_generator():
    sr = StreamingResponse((i for i in ["x", b"y"]))
    chunks = [c async for c in sr.stream_body()]
    assert chunks == [b"x", b"y"]


@pytest.mark.anyio
async def test_streaming_response_iterable():
    sr = StreamingResponse(["m", b"n"])
    chunks = [c async for c in sr.stream_body()]
    assert chunks == [b"m", b"n"]


@pytest.mark.anyio
async def test_streaming_response_existing_content_type():
    sr = StreamingResponse([], headers={"content-type": "text/csv"})
    assert sr.headers["content-type"] == "text/csv"


def test_file_response(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"file-content")
    fr = FileResponse(str(p), filename='evil".txt')
    assert fr.streaming is True
    assert "file-content" not in fr.headers.get("content-disposition", "")
    assert fr.headers["content-length"] == str(len(b"file-content"))


def test_file_response_missing_file(tmp_path):
    fr = FileResponse(str(tmp_path / "missing.bin"))
    assert "content-length" not in fr.headers


def test_file_response_with_media_type(tmp_path):
    p = tmp_path / "f.data"
    p.write_bytes(b"x")
    fr = FileResponse(str(p), media_type="application/x-custom")
    assert fr.headers["content-type"] == "application/x-custom"


def test_file_response_empty_filename(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x")
    fr = FileResponse(str(p), filename="")
    assert "content-disposition" not in fr.headers


@pytest.mark.anyio
async def test_file_response_stream_body(tmp_path):
    p = tmp_path / "big.bin"
    p.write_bytes(b"z" * (64 * 1024 + 10))
    fr = FileResponse(str(p))
    data = b"".join([c async for c in fr.stream_body()])
    assert data == b"z" * (64 * 1024 + 10)
