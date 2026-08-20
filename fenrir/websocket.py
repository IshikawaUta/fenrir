from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fenrir.json import json_dumps, json_loads


class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000, reason: str = ""):
        self.code = code
        self.reason = reason


class WebSocketTimeout(Exception):
    """Raised when a WebSocket receive operation times out."""
    def __init__(self, timeout: float):
        self.timeout = timeout
        super().__init__(f"WebSocket receive timed out after {timeout}s")


class WebSocket:
    def __init__(
        self,
        scope: Dict[str, Any],
        receive: Any,
        send: Any,
        timeout: Optional[float] = None,
    ):
        self.scope = scope
        self._receive = receive
        self._send = send
        self.client_state = "CONNECTING"  # CONNECTING, CONNECTED, DISCONNECTED
        self._timeout = timeout

    async def accept(self, subprotocol: str = None, headers: list = None):
        if self.client_state != "CONNECTING":
            raise RuntimeError("WebSocket is not in CONNECTING state")
        message = await self._receive()
        if message["type"] != "websocket.connect":
            raise RuntimeError(f"Expected websocket.connect, got {message['type']}")
        message_accept: Dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            message_accept["subprotocol"] = subprotocol
        if headers:
            message_accept["headers"] = headers
        await self._send(message_accept)
        self.client_state = "CONNECTED"

    async def _receive_with_timeout(self) -> Dict[str, Any]:
        if self._timeout is not None:
            try:
                return await asyncio.wait_for(self._receive(), timeout=self._timeout)
            except asyncio.TimeoutError:
                raise WebSocketTimeout(self._timeout) from None
        return await self._receive()

    async def receive(self) -> Dict[str, Any]:
        message = await self._receive_with_timeout()
        if message["type"] == "websocket.disconnect":
            self.client_state = "DISCONNECTED"
            raise WebSocketDisconnect(code=message.get("code", 1000))
        return message

    async def receive_text(self) -> str:
        message = await self.receive()
        if "text" not in message:
            raise ValueError("WebSocket message does not contain text")
        return message["text"]

    async def receive_bytes(self) -> bytes:
        message = await self.receive()
        if "bytes" not in message:
            raise ValueError("WebSocket message does not contain bytes")
        return message["bytes"]

    async def receive_json(self) -> Any:
        text = await self.receive_text()
        return json_loads(text)

    async def send_text(self, text: str):
        if self.client_state != "CONNECTED":
            raise RuntimeError("WebSocket is not connected")
        await self._send({"type": "websocket.send", "text": text})

    async def send_bytes(self, data: bytes):
        if self.client_state != "CONNECTED":
            raise RuntimeError("WebSocket is not connected")
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any):
        await self.send_text(json_dumps(data))

    async def close(self, code: int = 1000, reason: str = ""):
        if self.client_state == "DISCONNECTED":
            return
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
        self.client_state = "DISCONNECTED"
