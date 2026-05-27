import pytest
import asyncio
from fenrir import Fenrir
from fenrir.websocket import WebSocket, WebSocketDisconnect

@pytest.mark.anyio
async def test_websocket_routing_and_echo():
    app = Fenrir()

    @app.websocket("/ws/echo")
    async def echo_handler(ws: WebSocket):
        await ws.accept()
        while True:
            try:
                msg = await ws.receive_text()
                await ws.send_text(f"echo: {msg}")
            except WebSocketDisconnect:
                break

    scope = {
        "type": "websocket",
        "path": "/ws/echo",
        "headers": [],
    }

    receive_queue = asyncio.Queue()
    send_queue = asyncio.Queue()

    async def receive():
        return await receive_queue.get()

    async def send(msg):
        await send_queue.put(msg)

    # Simulate WebSocket handshakes and message exchange
    await receive_queue.put({"type": "websocket.connect"})
    
    task = asyncio.create_task(app(scope, receive, send))

    # Expect accept
    accept_msg = await send_queue.get()
    assert accept_msg["type"] == "websocket.accept"

    # Send text
    await receive_queue.put({"type": "websocket.receive", "text": "Hello Fenrir"})
    echo_msg = await send_queue.get()
    assert echo_msg["type"] == "websocket.send"
    assert echo_msg["text"] == "echo: Hello Fenrir"

    # Send disconnect
    await receive_queue.put({"type": "websocket.disconnect", "code": 1000})
    await task


@pytest.mark.anyio
async def test_websocket_json():
    app = Fenrir()

    @app.websocket("/ws/json")
    async def json_handler(ws):
        await ws.accept()
        data = await ws.receive_json()
        await ws.send_json({"response": data["request"] * 2})
        await ws.close()

    scope = {
        "type": "websocket",
        "path": "/ws/json",
        "headers": [],
    }

    receive_queue = asyncio.Queue()
    send_queue = asyncio.Queue()

    async def receive():
        return await receive_queue.get()

    async def send(msg):
        await send_queue.put(msg)

    await receive_queue.put({"type": "websocket.connect"})
    task = asyncio.create_task(app(scope, receive, send))

    # Accept
    assert (await send_queue.get())["type"] == "websocket.accept"

    # Send JSON
    await receive_queue.put({"type": "websocket.receive", "text": '{"request": 5}'})
    
    resp_msg = await send_queue.get()
    assert resp_msg["type"] == "websocket.send"
    import json
    parsed = json.loads(resp_msg["text"])
    assert parsed == {"response": 10}

    # Close
    close_msg = await send_queue.get()
    assert close_msg["type"] == "websocket.close"
    
    await task


@pytest.mark.anyio
async def test_websocket_close_reason():
    app = Fenrir()

    @app.websocket("/ws/close")
    async def close_handler(ws):
        await ws.accept()
        await ws.close(code=1008, reason="Policy Violation")

    scope = {
        "type": "websocket",
        "path": "/ws/close",
        "headers": [],
    }

    receive_queue = asyncio.Queue()
    send_queue = asyncio.Queue()

    async def receive():
        return await receive_queue.get()

    async def send(msg):
        await send_queue.put(msg)

    await receive_queue.put({"type": "websocket.connect"})
    task = asyncio.create_task(app(scope, receive, send))

    # Accept
    assert (await send_queue.get())["type"] == "websocket.accept"

    # Close with reason
    close_msg = await send_queue.get()
    assert close_msg["type"] == "websocket.close"
    assert close_msg["code"] == 1008
    assert close_msg["reason"] == "Policy Violation"
    
    await task

