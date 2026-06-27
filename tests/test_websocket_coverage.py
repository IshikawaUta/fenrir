"""Tests for fenrir.websocket — WebSocket class and exceptions."""
import asyncio
import pytest
from fenrir.websocket import WebSocket, WebSocketDisconnect, WebSocketTimeout
from fenrir.json import json_dumps


def _make_ws(timeout=None):
    """Create a WebSocket with mock scope/receive/send."""
    messages = []

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "websocket.disconnect", "code": 1000}

    sent = []

    async def send(msg):
        sent.append(msg)

    scope = {"type": "websocket", "path": "/ws"}
    ws = WebSocket(scope, receive, send, timeout=timeout)
    ws._test_sent = sent
    ws._test_messages = messages
    return ws


class TestWebSocketDisconnect:
    def test_default_code(self):
        exc = WebSocketDisconnect()
        assert exc.code == 1000
        assert exc.reason == ""

    def test_custom_code_and_reason(self):
        exc = WebSocketDisconnect(code=1001, reason="going away")
        assert exc.code == 1001
        assert exc.reason == "going away"

    def test_is_exception(self):
        assert issubclass(WebSocketDisconnect, Exception)


class TestWebSocketTimeout:
    def test_message(self):
        exc = WebSocketTimeout(5.0)
        assert exc.timeout == 5.0
        assert "5.0s" in str(exc)

    def test_is_exception(self):
        assert issubclass(WebSocketTimeout, Exception)


class TestWebSocketAccept:
    @pytest.mark.anyio
    async def test_accept_normal(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.connect"})
        await ws.accept()
        assert ws.client_state == "CONNECTED"
        assert ws._test_sent[0]["type"] == "websocket.accept"

    @pytest.mark.anyio
    async def test_accept_with_subprotocol(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.connect"})
        await ws.accept(subprotocol="graphql-ws")
        assert ws._test_sent[0]["subprotocol"] == "graphql-ws"

    @pytest.mark.anyio
    async def test_accept_with_headers(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.connect"})
        await ws.accept(headers=[(b"x-test", b"val")])
        assert ws._test_sent[0]["headers"] == [(b"x-test", b"val")]

    @pytest.mark.anyio
    async def test_accept_wrong_state_raises(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        with pytest.raises(RuntimeError, match="not in CONNECTING state"):
            await ws.accept()

    @pytest.mark.anyio
    async def test_accept_wrong_message_type_raises(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.send"})
        with pytest.raises(RuntimeError, match="Expected websocket.connect"):
            await ws.accept()


class TestWebSocketReceive:
    @pytest.mark.anyio
    async def test_receive_text_message(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.receive", "text": "hello"})
        msg = await ws.receive()
        assert msg["type"] == "websocket.receive"

    @pytest.mark.anyio
    async def test_receive_disconnect(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.disconnect", "code": 1001})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive()
        assert exc_info.value.code == 1001
        assert ws.client_state == "DISCONNECTED"

    @pytest.mark.anyio
    async def test_receive_text(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.receive", "text": "hello"})
        text = await ws.receive_text()
        assert text == "hello"

    @pytest.mark.anyio
    async def test_receive_text_no_text_raises(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.receive", "bytes": b"data"})
        with pytest.raises(ValueError, match="does not contain text"):
            await ws.receive_text()

    @pytest.mark.anyio
    async def test_receive_bytes(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.receive", "bytes": b"data"})
        data = await ws.receive_bytes()
        assert data == b"data"

    @pytest.mark.anyio
    async def test_receive_bytes_no_bytes_raises(self):
        ws = _make_ws()
        ws._test_messages.append({"type": "websocket.receive", "text": "hi"})
        with pytest.raises(ValueError, match="does not contain bytes"):
            await ws.receive_bytes()

    @pytest.mark.anyio
    async def test_receive_json(self):
        ws = _make_ws()
        payload = json_dumps({"key": "value"})
        ws._test_messages.append({"type": "websocket.receive", "text": payload})
        data = await ws.receive_json()
        assert data == {"key": "value"}

    @pytest.mark.anyio
    async def test_receive_with_timeout(self):
        # Create a receive coroutine that waits longer than the timeout
        async def receive():
            await asyncio.sleep(0.02)  # Wait 20ms
            return {"type": "websocket.receive", "text": "late"}
        
        async def send(msg):
            pass
            
        scope = {"type": "websocket", "path": "/ws"}
        ws = WebSocket(scope, receive, send, timeout=0.01)  # 10ms timeout
        
        with pytest.raises(WebSocketTimeout):
            await ws.receive()

    @pytest.mark.anyio
    async def test_receive_with_timeout_no_timeout(self):
        ws = _make_ws(timeout=None)
        ws._test_messages.append({"type": "websocket.receive", "text": "ok"})
        msg = await ws.receive()
        assert msg["type"] == "websocket.receive"


class TestWebSocketSend:
    @pytest.mark.anyio
    async def test_send_text(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        await ws.send_text("hello")
        assert ws._test_sent[0] == {"type": "websocket.send", "text": "hello"}

    @pytest.mark.anyio
    async def test_send_text_not_connected_raises(self):
        ws = _make_ws()
        with pytest.raises(RuntimeError, match="not connected"):
            await ws.send_text("hello")

    @pytest.mark.anyio
    async def test_send_bytes(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        await ws.send_bytes(b"data")
        assert ws._test_sent[0] == {"type": "websocket.send", "bytes": b"data"}

    @pytest.mark.anyio
    async def test_send_bytes_not_connected_raises(self):
        ws = _make_ws()
        with pytest.raises(RuntimeError, match="not connected"):
            await ws.send_bytes(b"data")

    @pytest.mark.anyio
    async def test_send_json(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        await ws.send_json({"msg": "hi"})
        assert ws._test_sent[0]["type"] == "websocket.send"
        assert "text" in ws._test_sent[0]


class TestWebSocketClose:
    @pytest.mark.anyio
    async def test_close_default(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        await ws.close()
        assert ws.client_state == "DISCONNECTED"
        assert ws._test_sent[0]["type"] == "websocket.close"
        assert ws._test_sent[0]["code"] == 1000

    @pytest.mark.anyio
    async def test_close_with_code_and_reason(self):
        ws = _make_ws()
        ws.client_state = "CONNECTED"
        await ws.close(code=1001, reason="going away")
        assert ws._test_sent[0]["code"] == 1001
        assert ws._test_sent[0]["reason"] == "going away"

    @pytest.mark.anyio
    async def test_close_already_disconnected(self):
        ws = _make_ws()
        ws.client_state = "DISCONNECTED"
        await ws.close()
        assert ws._test_sent == []
