import inspect
import asyncio
import logging
from typing import Any, Callable, List, Tuple

logger = logging.getLogger("fenrir.signals")

# Cache for receiver async status (avoids inspect.iscoroutinefunction on every signal send)
# Bounded to prevent memory leak — evicts oldest entries when full
_receiver_is_async_cache: dict = {}
_RECEIVER_CACHE_MAX = 1024


def _handle_signal_error(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Unhandled exception in async signal receiver")

class Namespace(dict):
    def signal(self, name: str, doc: str = None) -> "Signal":
        try:
            return self[name]
        except KeyError:
            return self.setdefault(name, Signal(name, doc))


class Signal:
    def __init__(self, name: str, doc: str = None):
        self.name = name
        self.doc = doc
        self.receivers: List[Tuple[Callable, Any]] = []

    def connect(self, receiver: Callable, sender: Any = None, weak: bool = True):
        # Note: weak reference support is not implemented; receivers are always strong references
        self.receivers.append((receiver, sender))
        return receiver

    def disconnect(self, receiver: Callable, sender: Any = None):
        self.receivers = [r for r in self.receivers if r[0] != receiver or r[1] != sender]

    def send(self, sender: Any = None, **kwargs: Any) -> List[Tuple[Callable, Any]]:
        results = []
        # Copy list to avoid mutation during iteration
        for receiver, s in list(self.receivers):
            if s is None or s == sender:
                # Use cached async status (bounded cache)
                receiver_id = id(receiver)
                is_async = _receiver_is_async_cache.get(receiver_id)
                if is_async is None:
                    is_async = inspect.iscoroutinefunction(receiver)
                    if len(_receiver_is_async_cache) >= _RECEIVER_CACHE_MAX:
                        _receiver_is_async_cache.pop(next(iter(_receiver_is_async_cache)))
                    _receiver_is_async_cache[receiver_id] = is_async
                if is_async:
                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(receiver(sender, **kwargs))
                        task.add_done_callback(_handle_signal_error)
                        results.append((receiver, task))
                    except RuntimeError:
                        # No running loop — schedule for later
                        logger.debug("No event loop running; async signal receiver '%s' skipped.", getattr(receiver, '__name__', receiver))
                else:
                    res = receiver(sender, **kwargs)
                    results.append((receiver, res))
        return results


_signals = Namespace()

request_started = _signals.signal("request-started")
request_finished = _signals.signal("request-finished")
got_request_exception = _signals.signal("got-request-exception")
template_rendered = _signals.signal("template-rendered")

# Alias for convenience (Sanic/Blinker-style)
signal_bus = _signals

def signal(name: str, doc: str = None) -> Signal:
    """Get or create a named signal on the global signal bus."""
    return _signals.signal(name, doc)

