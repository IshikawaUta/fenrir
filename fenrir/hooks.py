"""
fenrir.hooks — Extension points / hook system for Fenrir.

Provides a lightweight event system that plugins and extensions can use
to hook into the request/response lifecycle without modifying core code.

Built-in hooks:
    - on_startup / on_shutdown
    - on_request / on_response
    - on_before_handler / on_after_handler
    - on_exception
    - on_blueprint_register

Usage::

    from fenrir.hooks import HookRegistry

    hooks = HookRegistry()

    # Register a hook
    @hooks.register("on_request")
    async def log_request(request):
        print(f"Request: {request.method} {request.path}")

    # Register with priority (lower = runs first)
    @hooks.register("on_response", priority=10)
    async def add_header(response):
        response.headers["X-Custom"] = "value"

    # Emit a hook
    await hooks.emit("on_request", request=req)

    # As middleware integration
    hooks.apply(app)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("fenrir.hooks")


class HookEntry:
    """A registered hook handler with priority."""
    __slots__ = ("func", "priority", "is_async", "once")

    def __init__(self, func: Callable, priority: int = 100, once: bool = False) -> None:
        if not callable(func):
            raise TypeError(f"Hook handler must be callable, got {type(func)}")
        self.func = func
        self.priority = priority
        self.is_async = asyncio.iscoroutinefunction(func)
        self.once = once


class HookRegistry:
    """Registry for lifecycle hooks.

    Supports:
    - Synchronous and async hook handlers
    - Priority ordering (lower = runs first)
    - One-time hooks (auto-unregister after first call)
    - Hook cancellation (handler can return False to stop chain)
    - Wildcard hooks (registered with '*' to listen to all events)

    Usage::

        hooks = HookRegistry()

        @hooks.register("on_request")
        async def my_hook(ctx):
            print(ctx)

        await hooks.emit("on_request", ctx={"request": req})
    """

    def __init__(self) -> None:
        self._hooks: Dict[str, List[HookEntry]] = defaultdict(list)
        self._sorted: Dict[str, bool] = {}
        self._has_applied = False

    def register(
        self,
        event: str,
        func: Optional[Callable] = None,
        priority: int = 100,
        once: bool = False,
    ) -> Callable:
        """Register a hook handler.

        Can be used as a decorator::

            @hooks.register("on_request")
            async def handler(ctx):
                ...

        Or called directly::

            hooks.register("on_request", handler, priority=50)
        """
        def _register(fn: Callable) -> Callable:
            entry = HookEntry(fn, priority=priority, once=once)
            self._hooks[event].append(entry)
            self._sorted[event] = False
            return fn

        if func is not None:
            _register(func)
            return func

        return _register

    def unregister(self, event: str, func: Callable) -> bool:
        """Remove a hook handler."""
        if event not in self._hooks:
            return False
        before = len(self._hooks[event])
        self._hooks[event] = [e for e in self._hooks[event] if e.func is not func]
        return len(self._hooks[event]) < before

    def _ensure_sorted(self, event: str) -> None:
        if not self._sorted.get(event, True):
            self._hooks[event].sort(key=lambda e: e.priority)
            self._sorted[event] = True

    def _ensure_wildcard_sorted(self) -> None:
        if not self._sorted.get("*", True):
            self._hooks["*"].sort(key=lambda e: e.priority)
            self._sorted["*"] = True

    async def emit(self, event: str, **kwargs: Any) -> List[Any]:
        """Emit a hook event, calling all registered handlers.

        Returns a list of return values from handlers.
        If a handler returns ``False``, the chain is stopped.
        """
        results = []

        # Handle specific event hooks
        entries = self._hooks.get(event, [])

        # Handle wildcard hooks
        wildcard_entries = self._hooks.get("*", [])

        all_entries = entries + wildcard_entries
        if not all_entries:
            return results

        self._ensure_sorted(event)
        self._ensure_wildcard_sorted()

        # Sort combined entries by priority
        all_entries.sort(key=lambda e: e.priority)

        to_remove: List[Tuple[str, HookEntry]] = []

        for entry in all_entries:
            try:
                if entry.is_async:
                    result = await entry.func(**kwargs)
                else:
                    result = entry.func(**kwargs)
                results.append(result)
                if entry.once:
                    # Determine which list this entry came from
                    if entry in entries:
                        to_remove.append((event, entry))
                    else:
                        to_remove.append(("*", entry))
                if result is False:
                    break
            except Exception as e:
                logger.exception("Error in hook '%s' handler %r: %s", event, entry.func, e)
                if entry.once:
                    if entry in entries:
                        to_remove.append((event, entry))
                    else:
                        to_remove.append(("*", entry))

        # Remove one-time hooks
        for evt, entry in to_remove:
            if entry in self._hooks.get(evt, []):
                self._hooks[evt].remove(entry)

        return results

    def emit_sync(self, event: str, **kwargs: Any) -> List[Any]:
        """Emit a hook synchronously (for sync contexts)."""
        results = []
        entries = self._hooks.get(event, [])
        wildcard_entries = self._hooks.get("*", [])
        all_entries = entries + wildcard_entries

        if not all_entries:
            return results

        self._ensure_sorted(event)
        self._ensure_wildcard_sorted()

        # Sort combined entries by priority
        all_entries.sort(key=lambda e: e.priority)

        to_remove: List[Tuple[str, HookEntry]] = []

        for entry in all_entries:
            try:
                if entry.is_async:
                    logger.warning(
                        "Async hook '%s' handler %r called in sync context, skipping",
                        event, entry.func
                    )
                    continue
                result = entry.func(**kwargs)
                results.append(result)
                if entry.once:
                    if entry in entries:
                        to_remove.append((event, entry))
                    else:
                        to_remove.append(("*", entry))
                if result is False:
                    break
            except Exception as e:
                logger.exception("Error in hook '%s' handler %r: %s", event, entry.func, e)
                if entry.once:
                    if entry in entries:
                        to_remove.append((event, entry))
                    else:
                        to_remove.append(("*", entry))

        for evt, entry in to_remove:
            if entry in self._hooks.get(evt, []):
                self._hooks[evt].remove(entry)

        return results

    def clear(self, event: Optional[str] = None) -> None:
        """Clear hooks for a specific event or all events."""
        if event:
            self._hooks.pop(event, None)
            self._sorted.pop(event, None)
        else:
            self._hooks.clear()
            self._sorted.clear()

    def has_hooks(self, event: str) -> bool:
        """Check if any handlers are registered for an event."""
        return bool(self._hooks.get(event)) or bool(self._hooks.get("*"))

    def list_events(self) -> List[str]:
        """List all events with registered handlers."""
        return list(self._hooks.keys())

    def apply(self, app: Any) -> None:
        """Apply hooks to a Fenrir app by registering them as middleware/listeners.

        This integrates the hook system with the app's lifecycle.
        """
        if self._has_applied:
            logger.warning("HookRegistry.apply() called multiple times")
            return
        self._has_applied = True

        if self.has_hooks("on_startup"):
            @app.listener("before_server_start")
            async def _hooks_startup(app_instance):
                await self.emit("on_startup", app=app_instance)

        if self.has_hooks("on_shutdown"):
            @app.listener("after_server_stop")
            async def _hooks_shutdown(app_instance):
                await self.emit("on_shutdown", app=app_instance)

        if self.has_hooks("on_request") or self.has_hooks("on_response"):
            @app.middleware("request")
            async def _hooks_before_request(req):
                ctx = {"request": req, "app": app}
                await self.emit("on_request", **ctx)

            @app.middleware("response")
            async def _hooks_after_response(req, resp):
                ctx = {"request": req, "response": resp, "app": app}
                await self.emit("on_response", **ctx)


# Singleton for convenience
_default_registry: Optional[HookRegistry] = None
_singleton_lock = threading.Lock()


def get_hooks() -> HookRegistry:
    """Get or create the default hook registry."""
    global _default_registry
    if _default_registry is None:
        with _singleton_lock:
            if _default_registry is None:
                _default_registry = HookRegistry()
    return _default_registry
