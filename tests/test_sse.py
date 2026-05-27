import pytest
from fenrir import Fenrir, EventSourceResponse
from fenrir.testing import TestClient
import asyncio

@pytest.mark.anyio
async def test_sse_async_gen():
    app = Fenrir()

    async def event_generator():
        yield "hello"
        yield {"event": "ping", "data": "pong"}
        yield {"id": "123", "data": "multiline\ndata"}

    @app.get("/sse")
    async def sse_endpoint():
        return EventSourceResponse(event_generator())

    client = TestClient(app)
    resp = await client.get("/sse")
    
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream"
    
    expected = (
        "data: hello\n\n"
        "event: ping\n"
        "data: pong\n\n"
        "id: 123\n"
        "data: multiline\n"
        "data: data\n\n"
    )
    assert resp.text == expected


@pytest.mark.anyio
async def test_sse_list():
    app = Fenrir()

    @app.get("/sse-list")
    async def sse_list_endpoint():
        return EventSourceResponse(["first", "second"])

    client = TestClient(app)
    resp = await client.get("/sse-list")
    
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream"
    
    expected = (
        "data: first\n\n"
        "data: second\n\n"
    )
    assert resp.text == expected
