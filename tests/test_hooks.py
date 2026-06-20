"""Tests for fenrir.hooks — Extension points / hook system."""
import asyncio
import pytest
from fenrir.hooks import HookRegistry, get_hooks, HookEntry


class MockApp:
    def __init__(self):
        self._middlewares = {"request": [], "response": []}
        self._listeners = []

    def middleware(self, type_):
        def decorator(f):
            self._middlewares[type_].append(f)
            return f
        return decorator

    def listener(self, name):
        def decorator(f):
            self._listeners.append((name, f))
            return f
        return decorator


# ═══════════════════════════════════════════════════════════════════════
# HookRegistry Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHookRegistry:
    def test_register_hook(self):
        hooks = HookRegistry()
        
        @hooks.register("test_event")
        def handler():
            pass
        
        assert hooks.has_hooks("test_event")

    def test_register_with_priority(self):
        hooks = HookRegistry()
        
        @hooks.register("test_event", priority=10)
        def high_priority():
            pass
        
        @hooks.register("test_event", priority=100)
        def low_priority():
            pass
        
        assert len(hooks._hooks["test_event"]) == 2

    def test_register_once(self):
        hooks = HookRegistry()
        call_count = 0
        
        @hooks.register("test_event", once=True)
        def handler():
            nonlocal call_count
            call_count += 1
        
        asyncio.run(hooks.emit("test_event"))
        asyncio.run(hooks.emit("test_event"))
        
        assert call_count == 1

    def test_unregister_hook(self):
        hooks = HookRegistry()
        
        @hooks.register("test_event")
        def handler():
            pass
        
        assert hooks.has_hooks("test_event")
        hooks.unregister("test_event", handler)
        assert not hooks.has_hooks("test_event")

    def test_clear_hooks(self):
        hooks = HookRegistry()
        
        @hooks.register("event1")
        def handler1():
            pass
        
        @hooks.register("event2")
        def handler2():
            pass
        
        hooks.clear("event1")
        assert not hooks.has_hooks("event1")
        assert hooks.has_hooks("event2")

    def test_clear_all_hooks(self):
        hooks = HookRegistry()
        
        @hooks.register("event1")
        def handler1():
            pass
        
        hooks.clear()
        assert not hooks.has_hooks("event1")

    def test_list_events(self):
        hooks = HookRegistry()
        
        @hooks.register("event1")
        def handler1():
            pass
        
        @hooks.register("event2")
        def handler2():
            pass
        
        events = hooks.list_events()
        assert "event1" in events
        assert "event2" in events


# ═══════════════════════════════════════════════════════════════════════
# Async Hook Emission Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAsyncHooks:
    @pytest.mark.anyio
    async def test_emit_async_hook(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event")
        async def handler(data):
            results.append(data)
        
        await hooks.emit("test_event", data="test")
        assert "test" in results

    @pytest.mark.anyio
    async def test_emit_sync_hook(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event")
        def handler(data):
            results.append(data)
        
        await hooks.emit("test_event", data="test")
        assert "test" in results

    @pytest.mark.anyio
    async def test_hook_priority_order(self):
        hooks = HookRegistry()
        order = []
        
        @hooks.register("test_event", priority=100)
        def low_priority():
            order.append("low")
        
        @hooks.register("test_event", priority=10)
        def high_priority():
            order.append("high")
        
        await hooks.emit("test_event")
        assert order == ["high", "low"]

    @pytest.mark.anyio
    async def test_hook_cancellation(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event", priority=10)
        def canceller():
            return False
        
        @hooks.register("test_event", priority=100)
        def handler():
            results.append("called")
        
        await hooks.emit("test_event")
        assert "called" not in results

    @pytest.mark.anyio
    async def test_wildcard_hook(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("*")
        def wildcard_handler(**kwargs):
            results.append("wildcard")
        
        await hooks.emit("event1", data="test")
        await hooks.emit("event2", data="test")
        
        assert "wildcard" in results

    @pytest.mark.anyio
    async def test_hook_error_handling(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event", priority=10)
        def bad_handler():
            raise ValueError("test error")
        
        @hooks.register("test_event", priority=100)
        def good_handler():
            results.append("ok")
        
        await hooks.emit("test_event")
        assert "ok" in results


# ═══════════════════════════════════════════════════════════════════════
# Sync Hook Emission Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSyncHooks:
    def test_emit_sync(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event")
        def handler(data):
            results.append(data)
        
        hooks.emit_sync("test_event", data="test")
        assert "test" in results

    def test_sync_skips_async_handlers(self):
        hooks = HookRegistry()
        results = []
        
        @hooks.register("test_event")
        async def async_handler():
            results.append("async")
        
        @hooks.register("test_event")
        def sync_handler():
            results.append("sync")
        
        hooks.emit_sync("test_event")
        assert "sync" in results
        assert "async" not in results


# ═══════════════════════════════════════════════════════════════════════
# Middleware Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMiddlewareIntegration:
    def test_apply_hooks_to_app(self):
        hooks = HookRegistry()
        app = MockApp()
        
        @hooks.register("on_request")
        async def request_hook():
            pass
        
        @hooks.register("on_response")
        async def response_hook():
            pass
        
        hooks.apply(app)
        
        assert len(app._middlewares["request"]) > 0
        assert len(app._middlewares["response"]) > 0


# ═══════════════════════════════════════════════════════════════════════
# Default Registry Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDefaultRegistry:
    def test_get_hooks(self):
        hooks = get_hooks()
        assert isinstance(hooks, HookRegistry)

    def test_singleton(self):
        hooks1 = get_hooks()
        hooks2 = get_hooks()
        assert hooks1 is hooks2
