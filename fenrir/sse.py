import asyncio
import logging
import queue as _queue
import threading
from typing import Any, AsyncIterable, Dict, Optional, Union

from fenrir.compat import _thread_pool
from fenrir.response import Response

logger = logging.getLogger("fenrir.sse")

class EventSourceResponse(Response):
    def __init__(
        self,
        generator: Union[AsyncIterable[Any], Any],
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        headers_dict = dict(headers) if headers else {}
        headers_dict.setdefault("Content-Type", "text/event-stream")
        headers_dict.setdefault("Cache-Control", "no-cache")
        headers_dict.setdefault("Connection", "keep-alive")
        headers_dict.setdefault("X-Accel-Buffering", "no")
        super().__init__(body=b"", status=status, headers=headers_dict)
        self.generator = generator

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any):
        # Send HTTP headers
        await send({
            "type": "http.response.start",
            "status": self.status,
            "headers": [
                (k.lower().encode("utf-8"), v.encode("utf-8"))
                for k, v in self.headers.items()
            ],
        })

        async def send_chunk(text: str):
            await send({
                "type": "http.response.body",
                "body": text.encode("utf-8"),
                "more_body": True,
            })

        try:
            if hasattr(self.generator, "__aiter__"):
                async for item in self.generator:
                    formatted = self._format_event(item)
                    await send_chunk(formatted)
            else:
                # Run sync generator in a thread to avoid blocking the event loop
                loop = asyncio.get_running_loop()
                q: _queue.Queue = _queue.Queue()

                def _produce():
                    try:
                        for item in self.generator:
                            q.put(item)
                    finally:
                        q.put(None)

                t = threading.Thread(target=_produce, daemon=True)
                t.start()

                while True:
                    item = await loop.run_in_executor(_thread_pool, q.get)
                    if item is None:
                        break
                    formatted = self._format_event(item)
                    await send_chunk(formatted)
        except Exception as e:
            logger.exception("SSE generator error: %s", e)
        finally:
            # End stream
            await send({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })

    def _format_event(self, item: Any) -> str:
        if isinstance(item, dict):
            out = []
            if "id" in item:
                out.append(f"id: {item['id']}")
            if "event" in item:
                out.append(f"event: {item['event']}")
            if "data" in item:
                data_val = str(item["data"])
                for line in data_val.split("\n"):
                    out.append(f"data: {line}")
            if "retry" in item:
                out.append(f"retry: {item['retry']}")
            return "\n".join(out) + "\n\n"
        else:
            data_val = str(item)
            out = []
            for line in data_val.split("\n"):
                out.append(f"data: {line}")
            return "\n".join(out) + "\n\n"
