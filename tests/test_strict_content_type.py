import pytest
from pydantic import BaseModel

from fenrir import Fenrir
from fenrir.testing import TestClient


class Item(BaseModel):
    name: str

@pytest.mark.anyio
async def test_strict_content_type_enabled():
    app = Fenrir(strict_content_type=True)

    @app.post("/item")
    async def create_item(item: Item):
        return {"name": item.name}

    client = TestClient(app)

    # Valid JSON request with correct Content-Type -> 200
    resp = await client.post("/item", json={"name": "book"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "book"}

    # Request with missing or invalid Content-Type -> 400
    resp = await client.post(
        "/item",
        content=b'{"name": "book"}',
        headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Strict content-type check failed"


@pytest.mark.anyio
async def test_strict_content_type_disabled():
    app = Fenrir(strict_content_type=False)

    @app.post("/item")
    async def create_item(item: Item):
        return {"name": item.name}

    client = TestClient(app)

    # When disabled, text/plain Content-Type is accepted as long as it contains valid JSON
    resp = await client.post(
        "/item",
        content=b'{"name": "book"}',
        headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"name": "book"}
