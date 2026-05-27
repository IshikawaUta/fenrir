from typing import Any, Dict

class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000, reason: str = ""):
        self.code = code
        self.reason = reason


class WebSocket:
    def __init__(self, scope: Dict[str, Any], receive: Any, send: Any):
        self.scope = scope
        self._receive = receive
        self._send = send
        self.client_state = "CONNECTING"  # CONNECTING, CONNECTED, DISCONNECTED

    async def accept(self, subprotocol: str = None, headers: list = None):
        if self.client_state != "CONNECTING":
            raise RuntimeError("WebSocket is not in CONNECTING state")
        message = await self._receive()
        if message["type"] != "websocket.connect":
            raise RuntimeError(f"Expected websocket.connect, got {message['type']}")
        message_accept = {"type": "websocket.accept"}
        if subprotocol:
            message_accept["subprotocol"] = subprotocol
        if headers:
            message_accept["headers"] = headers
        await self._send(message_accept)
        self.client_state = "CONNECTED"

    async def receive(self) -> Dict[str, Any]:
        message = await self._receive()
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
        import json
        text = await self.receive_text()
        return json.loads(text)

    async def send_text(self, text: str):
        if self.client_state != "CONNECTED":
            raise RuntimeError("WebSocket is not connected")
        await self._send({"type": "websocket.send", "text": text})

    async def send_bytes(self, data: bytes):
        if self.client_state != "CONNECTED":
            raise RuntimeError("WebSocket is not connected")
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any):
        import json
        await self.send_text(json.dumps(data))

    async def close(self, code: int = 1000, reason: str = ""):
        if self.client_state == "DISCONNECTED":
            return
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
        self.client_state = "DISCONNECTED"
