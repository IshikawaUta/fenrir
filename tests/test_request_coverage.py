"""Unit tests for fenrir.request edge paths."""
import pytest

from fenrir.request import Request


def make_request(query_string=b"", headers=None, path="/"):
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
    })


def test_cookies_ignore_malformed():
    req = make_request(headers=[(b"cookie", b"a=1; justgarbage")])
    assert req.cookies == {"a": "1"}


def test_args_list():
    req = make_request(query_string=b"a=1&a=2&b=x")
    assert req.args_list == {"a": ["1", "2"], "b": ["x"]}
    assert req.args == {"a": "1", "b": "x"}


def test_host_cached_outside_context():
    req = make_request(headers=[(b"host", b"example.com")])
    assert req.host == "example.com"
    assert req.host == "example.com"


@pytest.mark.anyio
async def test_body_json_async():
    req = make_request()
    assert await req.body_async() == b""
    assert await req.json_async() is None


@pytest.mark.anyio
async def test_read_body_already_parsed():
    req = make_request()
    req._parsed = True
    req._body = b"x"
    await req._read_body(None)
    assert req._body == b"x"


@pytest.mark.anyio
async def test_read_body_chunks():
    req = make_request()
    messages = iter([
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ])

    async def receive():
        return next(messages)

    await req._read_body(receive)
    assert req._body == b"abcdef"
    assert req._parsed is True


@pytest.mark.anyio
async def test_read_body_disconnect():
    req = make_request()

    async def receive():
        return {"type": "http.disconnect"}

    await req._read_body(receive)
    assert req._body == b""


@pytest.mark.anyio
async def test_stream_body_unparsed():
    req = make_request()
    messages = iter([
        {"type": "http.request", "body": b"chunk1", "more_body": True},
        {"type": "http.request", "body": b"chunk2", "more_body": False},
    ])

    async def receive():
        return next(messages)

    req._receive = receive
    chunks = [c async for c in req.stream_body()]
    assert chunks == [b"chunk1", b"chunk2"]


@pytest.mark.anyio
async def test_stream_body_disconnect():
    req = make_request()

    async def receive():
        return {"type": "http.disconnect"}

    req._receive = receive
    assert [c async for c in req.stream_body()] == []


@pytest.mark.anyio
async def test_form_empty_body():
    req = make_request()
    assert await req.form() == {}


@pytest.mark.anyio
async def test_form_unhandled_content_type():
    req = make_request(headers=[(b"content-type", b"text/plain")])
    req._body = b"raw"
    assert await req.form() == {}


@pytest.mark.anyio
async def test_form_urlencoded_list():
    req = make_request(headers=[(b"content-type", b"application/x-www-form-urlencoded")])
    req._body = b"k=a&k=b&single=c"
    assert await req.form() == {"k": ["a", "b"], "single": "c"}


def test_args_empty_query():
    req = make_request()
    assert req.args == {}


def test_args_list_and_cookies_recall():
    req = make_request(query_string=b"a=1")
    assert req.args_list == {"a": ["1"]}
    assert req.args_list == {"a": ["1"]}
    assert req.cookies == {}
    assert req.cookies == {}


@pytest.mark.anyio
async def test_read_body_unknown_message_type():
    req = make_request()
    messages = iter([
        {"type": "custom", "body": b"x"},
        {"type": "http.request", "body": b"y", "more_body": False},
    ])

    async def receive():
        return next(messages)

    await req._read_body(receive)
    assert req._body == b"y"


@pytest.mark.anyio
async def test_stream_body_no_receive():
    req = make_request()
    assert [c async for c in req.stream_body()] == []


@pytest.mark.anyio
async def test_stream_body_empty_chunk_skipped():
    req = make_request()
    messages = iter([
        {"type": "http.request", "body": b"", "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": False},
    ])

    async def receive():
        return next(messages)

    req._receive = receive
    assert [c async for c in req.stream_body()] == [b"x"]


@pytest.mark.anyio
async def test_stream_body_unknown_message_type():
    req = make_request()
    messages = iter([
        {"type": "custom", "body": b"x"},
        {"type": "http.request", "body": b"y", "more_body": False},
    ])

    async def receive():
        return next(messages)

    req._receive = receive
    assert [c async for c in req.stream_body()] == [b"y"]


@pytest.mark.anyio
async def test_json_invalid_body():
    req = make_request()
    req._body = b"not-json"
    assert req.json is None


@pytest.mark.anyio
async def test_multipart_parser_without_parser_attr(monkeypatch):
    import python_multipart as mp

    class FakeParser:
        def write(self, chunk):
            pass

        def finalize(self):
            pass

    monkeypatch.setattr(mp, "create_form_parser", lambda *a, **k: FakeParser())
    req = make_request(headers=[(b"content-type", b"multipart/form-data; boundary=b")])
    req._body = b"x"
    assert await req.form() == {}


@pytest.mark.anyio
async def test_multipart_parser_callbacks_without_orig(monkeypatch):
    import python_multipart as mp

    class FakeInner:
        def __init__(self):
            self.callbacks = {}

    class FakeParser:
        def __init__(self):
            self.parser = FakeInner()

        def write(self, chunk):
            cb = self.parser.callbacks
            if "on_header_field" in cb:
                cb["on_header_field"](b"content-type", 0, 1)
            if "on_header_value" in cb:
                cb["on_header_value"](b"text/plain", 0, 1)
            if "on_header_end" in cb:
                cb["on_header_end"]()
            if "on_headers_finished" in cb:
                cb["on_headers_finished"]()

        def finalize(self):
            pass

    monkeypatch.setattr(mp, "create_form_parser", lambda *a, **k: FakeParser())
    req = make_request(headers=[(b"content-type", b"multipart/form-data; boundary=b")])
    req._body = b"x"
    assert await req.form() == {}
