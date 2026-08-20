import asyncio
import contextvars
import types

import httpx
import pytest

from fenrir import Fenrir, g, request
from fenrir.context import (
    AppContext,
    LocalProxy,
    RequestContext,
    current_app,
    session,
)


@pytest.mark.anyio
async def test_context_concurrency():
    app = Fenrir()

    @app.get("/delay/<delay_val:float>/<request_id:int>")
    async def delayed_route(delay_val: float, request_id: int):
        g.request_id = request_id
        g.other_val = f"val-{request_id}"

        # Pause to let other requests run and potentially overwrite context
        await asyncio.sleep(delay_val)

        # Verify context is still isolated
        assert g.request_id == request_id
        assert g.other_val == f"val-{request_id}"
        assert request.path == f"/delay/{delay_val}/{request_id}"

        return {"id": g.request_id, "path": request.path}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Run two requests concurrently
        t1 = client.get("/delay/0.2/1")
        t2 = client.get("/delay/0.05/2")

        r1, r2 = await asyncio.gather(t1, t2)

        assert r1.status_code == 200
        assert r1.json() == {"id": 1, "path": "/delay/0.2/1"}

        assert r2.status_code == 200
        assert r2.json() == {"id": 2, "path": "/delay/0.05/2"}


class _DunderRequest:
    def __init__(self):
        object.__setattr__(self, "data", {})
        object.__setattr__(self, "session", types.SimpleNamespace(x=1))

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def __delitem__(self, k):
        del self.data[k]

    def __contains__(self, k):
        return k in self.data

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)


def test_local_proxy_callable_target():
    proxy = LocalProxy(lambda: {"x": 1})
    assert proxy["x"] == 1


def test_local_proxy_unrecognized_target():
    proxy = LocalProxy("bogus")
    with pytest.raises(RuntimeError, match="Unrecognized proxy target."):
        proxy.anything  # noqa: B018 - intentional attribute access raising


def test_local_proxy_repr_unbound():
    assert repr(LocalProxy("bogus")) == "<LocalProxy unbound>"


def test_current_app_unbound(monkeypatch):
    monkeypatch.setattr("fenrir.context._app_ctx_var", contextvars.ContextVar("app_ctx_t"))
    with pytest.raises(RuntimeError, match="application context"):
        current_app.config  # noqa: B018 - intentional attribute access raising


def test_session_unbound(monkeypatch):
    monkeypatch.setattr("fenrir.context._request_ctx_var", contextvars.ContextVar("req_ctx_t"))
    with pytest.raises(RuntimeError, match="request context"):
        session.value  # noqa: B018 - intentional attribute access raising


def test_local_proxy_dunder_operations():
    app = object()
    req = _DunderRequest()
    with RequestContext(app, req) as rc:
        assert rc.app is app
        request["k"] = 1
        assert request["k"] == 1
        assert "k" in request
        assert len(request) == 1
        assert list(request) == ["k"]
        del request["k"]
        request.attr = 5
        del request.attr
        assert session.x == 1
        assert repr(g) == "<g {}>"


def test_request_context_enter_rollback(monkeypatch):
    class _BoomVar:
        def set(self, value):
            raise RuntimeError("boom")

    monkeypatch.setattr("fenrir.context._request_ctx_var", _BoomVar())
    with pytest.raises(RuntimeError, match="boom"):
        with RequestContext(object(), _DunderRequest()):
            pass


class _TeardownApp:
    def __init__(self):
        self.calls = []

    def do_teardown_request(self, exc):
        self.calls.append(("req", exc))

    def do_teardown_appcontext(self, exc):
        self.calls.append(("app", exc))


def test_request_context_teardown_hooks():
    app = _TeardownApp()
    with RequestContext(app, _DunderRequest()):
        pass
    kinds = [c[0] for c in app.calls]
    assert kinds == ["req", "app"]


def test_app_context_teardown_hook():
    app = _TeardownApp()
    with AppContext(app):
        pass
    assert app.calls == [("app", None)]
