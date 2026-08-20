import asyncio
import inspect

import pytest

from fenrir import MethodView, View


@pytest.mark.anyio
async def test_pluggable_views(app):
    class ItemView(MethodView):
        async def get(self):
            return "item get"
        async def post(self):
            return "item post"

    app.add_route("/item", ItemView.as_view("item_view"))
    client = app.test_client()

    resp = await client.get("/item")
    assert resp.status_code == 200
    assert resp.text == "item get"

    resp = await client.post("/item")
    assert resp.status_code == 200
    assert resp.text == "item post"

    # Test automatic OPTIONS response
    resp = await client.request("OPTIONS", "/item")
    assert resp.status_code == 200
    assert "GET" in resp.headers["allow"]
    assert "POST" in resp.headers["allow"]


def test_view_as_view_sync_dispatch():
    class V(View):
        methods = ["GET"]

        def dispatch_request(self, *args, **kwargs):
            return "sync result"

    view = V.as_view("v")
    assert inspect.iscoroutinefunction(view)
    assert asyncio.run(view()) == "sync result"
    assert view.methods == ["GET"]


def test_view_default_methods_get():
    class V(View):
        pass

    view = V.as_view("v2")
    assert view.methods == ["GET"]


@pytest.mark.anyio
async def test_method_view_without_request_context():
    class M(MethodView):
        async def get(self):
            return "no-ctx"

    res = await M().dispatch_request()
    assert res == "no-ctx"


@pytest.mark.anyio
async def test_method_view_sync_result():
    class M(MethodView):
        def get(self):
            return "sync"

    res = await M().dispatch_request()
    assert res == "sync"


@pytest.mark.anyio
async def test_method_view_head_fallback(app):
    class M(MethodView):
        async def get(self):
            return "g"

    app.add_route("/h", M.as_view("h"))
    resp = await app.test_client().head("/h")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_method_view_not_allowed(app):
    class M(MethodView):
        async def get(self):
            return "g"

    app.add_route("/n", M.as_view("n"))
    resp = await app.test_client().post("/n")
    assert resp.status_code == 405


@pytest.mark.anyio
async def test_method_view_options_only_get(app):
    class M(MethodView):
        async def get(self):
            return "g"

    app.add_route("/o", M.as_view("o"))
    resp = await app.test_client().request("OPTIONS", "/o")
    allow = resp.headers["allow"]
    assert "GET" in allow
    assert "HEAD" in allow
    assert "OPTIONS" in allow
