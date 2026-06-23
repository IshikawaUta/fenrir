"""Tests for fenrir.signals module."""
import asyncio
import pytest
from fenrir.signals import (
    Namespace, Signal, _handle_signal_error,
    request_started, request_finished, got_request_exception, template_rendered,
    signal_bus, signal,
)


# ═══════════════════════════════════════════════════════════════════════
# Namespace Tests
# ═══════════════════════════════════════════════════════════════════════

class TestNamespace:
    def test_signal_creates(self):
        ns = Namespace()
        sig = ns.signal("test-signal")
        assert isinstance(sig, Signal)
        assert sig.name == "test-signal"
        assert "test-signal" in ns

    def test_signal_returns_existing(self):
        ns = Namespace()
        sig1 = ns.signal("my-signal")
        sig2 = ns.signal("my-signal")
        assert sig1 is sig2

    def test_signal_with_doc(self):
        ns = Namespace()
        sig = ns.signal("documented", doc="A documented signal")
        assert sig.doc == "A documented signal"


# ═══════════════════════════════════════════════════════════════════════
# Signal Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSignal:
    def test_init(self):
        sig = Signal("test")
        assert sig.name == "test"
        assert sig.doc is None
        assert sig.receivers == []

    def test_connect(self):
        sig = Signal("test")
        def handler(sender, **kwargs):
            pass
        sig.connect(handler)
        assert len(sig.receivers) == 1
        assert sig.receivers[0] == (handler, None)

    def test_connect_with_sender(self):
        sig = Signal("test")
        def handler(sender, **kwargs):
            pass
        sig.connect(handler, sender="mysender")
        assert sig.receivers[0] == (handler, "mysender")

    def test_connect_returns_receiver(self):
        sig = Signal("test")
        def handler(sender, **kwargs):
            pass
        result = sig.connect(handler)
        assert result is handler

    def test_disconnect(self):
        sig = Signal("test")
        def handler(sender, **kwargs):
            pass
        sig.connect(handler)
        assert len(sig.receivers) == 1
        sig.disconnect(handler)
        assert len(sig.receivers) == 0

    def test_disconnect_with_sender(self):
        sig = Signal("test")
        def handler(sender, **kwargs):
            pass
        sig.connect(handler, sender="a")
        sig.connect(handler, sender="b")
        sig.disconnect(handler, sender="a")
        assert len(sig.receivers) == 1
        assert sig.receivers[0][1] == "b"

    def test_send_sync_receiver(self):
        sig = Signal("test")
        results = []
        def handler(sender, **kwargs):
            results.append(("called", sender, kwargs))
        sig.connect(handler)
        ret = sig.send("mysender", key="value")
        assert len(ret) == 1
        assert results[0] == ("called", "mysender", {"key": "value"})

    def test_send_filters_by_sender(self):
        sig = Signal("test")
        results = []
        def handler_a(sender, **kwargs):
            results.append("a")
        def handler_b(sender, **kwargs):
            results.append("b")
        sig.connect(handler_a, sender="a")
        sig.connect(handler_b, sender="b")
        sig.send("a")
        assert results == ["a"]

    def test_send_no_sender_matches_all(self):
        sig = Signal("test")
        results = []
        def handler(sender, **kwargs):
            results.append(1)
        sig.connect(handler)  # no sender filter
        sig.send("anyone")
        assert results == [1]

    def test_send_no_receivers(self):
        sig = Signal("test")
        ret = sig.send("sender")
        assert ret == []


# ═══════════════════════════════════════════════════════════════════════
# Async Signal Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSignalAsync:
    @pytest.mark.anyio
    async def test_send_async_receiver(self):
        sig = Signal("test")
        results = []
        async def handler(sender, **kwargs):
            results.append(("async", sender, kwargs))
        sig.connect(handler)
        ret = sig.send("sender", key="val")
        assert len(ret) == 1
        # Wait for the task to complete
        task = ret[0][1]
        await asyncio.sleep(0.01)
        assert results == [("async", "sender", {"key": "val"})]

    @pytest.mark.anyio
    async def test_async_receiver_error(self):
        sig = Signal("test")
        async def bad_handler(sender, **kwargs):
            raise RuntimeError("boom")
        sig.connect(bad_handler)
        ret = sig.send("sender")
        task = ret[0][1]
        await asyncio.sleep(0.01)
        # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# _handle_signal_error Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHandleSignalError:
    @pytest.mark.anyio
    async def test_handle_result(self):
        task = asyncio.create_task(asyncio.sleep(0))
        await asyncio.sleep(0)
        _handle_signal_error(task)  # Should not raise

    @pytest.mark.anyio
    async def test_handle_cancelled(self):
        task = asyncio.create_task(asyncio.sleep(10))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        _handle_signal_error(task)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# Global Signals Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGlobalSignals:
    def test_request_started_is_signal(self):
        assert isinstance(request_started, Signal)
        assert request_started.name == "request-started"

    def test_request_finished_is_signal(self):
        assert isinstance(request_finished, Signal)
        assert request_finished.name == "request-finished"

    def test_got_request_exception_is_signal(self):
        assert isinstance(got_request_exception, Signal)
        assert got_request_exception.name == "got-request-exception"

    def test_template_rendered_is_signal(self):
        assert isinstance(template_rendered, Signal)
        assert template_rendered.name == "template-rendered"

    def test_signal_bus_is_namespace(self):
        assert isinstance(signal_bus, Namespace)

    def test_signal_function(self):
        sig = signal("custom-signal")
        assert isinstance(sig, Signal)
        assert sig.name == "custom-signal"

    def test_signal_function_returns_same(self):
        sig1 = signal("my-signal")
        sig2 = signal("my-signal")
        assert sig1 is sig2
