import httpx
import pytest

from fenrir import Fenrir


class UserResource:
    async def on_get(self, req, resp, user_id: int):
        resp.status = 200
        resp.media = {"user_id": user_id, "source": "resource"}

    async def on_post(self, req, resp):
        data = req.json
        resp.status = 201
        resp.media = {"status": "created", "data": data}

@pytest.mark.anyio
async def test_resources():
    app = Fenrir()
    app.add_route("/users/<user_id:int>", UserResource())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # GET request
        res = await client.get("/users/789")
        assert res.status_code == 200
        assert res.json() == {"user_id": 789, "source": "resource"}

        # POST request
        res = await client.post("/users/789", json={"name": "Alice"})
        assert res.status_code == 201
        assert res.json() == {"status": "created", "data": {"name": "Alice"}}

        # Method Not Allowed
        res = await client.put("/users/789")
        assert res.status_code == 405
