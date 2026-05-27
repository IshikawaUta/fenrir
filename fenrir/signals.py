import inspect
import asyncio
from typing import Any, Callable, List, Tuple

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
        self.receivers.append((receiver, sender))
        return receiver

    def disconnect(self, receiver: Callable, sender: Any = None):
        self.receivers = [r for r in self.receivers if r[0] != receiver or r[1] != sender]

    def send(self, sender: Any = None, **kwargs: Any) -> List[Tuple[Callable, Any]]:
        results = []
        for receiver, s in self.receivers:
            if s is None or s == sender:
                if inspect.iscoroutinefunction(receiver):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(receiver(sender, **kwargs))
                    except RuntimeError:
                        asyncio.run(receiver(sender, **kwargs))
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

