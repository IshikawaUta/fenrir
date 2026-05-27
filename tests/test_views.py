import pytest
from fenrir import View, MethodView

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
