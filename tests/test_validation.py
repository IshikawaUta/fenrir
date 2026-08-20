import httpx
import pytest
from pydantic import BaseModel

from fenrir import Fenrir, Header


class Item(BaseModel):
    name: str
    price: float
    quantity: int = 1

@pytest.mark.anyio
async def test_validation():
    app = Fenrir()

    @app.post("/items")
    async def create_item(item: Item):
        return {"item": item.model_dump()}

    @app.get("/search")
    async def search(q: str, limit: int = 10):
        return {"q": q, "limit": limit}

    @app.get("/headers")
    async def get_headers(user_agent: str = Header(), api_key: str = Header(alias="x-api-key")):
        return {"user_agent": user_agent, "api_key": api_key}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Valid body
        res = await client.post("/items", json={"name": "Widget", "price": 9.99})
        assert res.status_code == 200
        assert res.json() == {"item": {"name": "Widget", "price": 9.99, "quantity": 1}}

        # 2. Invalid body (missing fields, wrong types)
        res = await client.post("/items", json={"price": "not-a-number"})
        assert res.status_code == 422
        errors = res.json()["detail"]
        assert len(errors) > 0
        assert any(e["loc"] == ["body", "name"] for e in errors)
        assert any(e["loc"] == ["body", "price"] for e in errors)

        # 3. Query params
        res = await client.get("/search?q=test&limit=5")
        assert res.status_code == 200
        assert res.json() == {"q": "test", "limit": 5}

        # Missing query param
        res = await client.get("/search?limit=5")
        assert res.status_code == 422
        assert res.json()["detail"][0]["loc"] == ["query", "q"]

        # 4. Headers
        res = await client.get("/headers", headers={"User-Agent": "Mozilla", "x-api-key": "secret"})
        assert res.status_code == 200
        assert res.json() == {"user_agent": "Mozilla", "api_key": "secret"}
