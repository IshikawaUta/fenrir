import httpx
import pytest

from fenrir import Depends, Fenrir


# Dependencies
async def get_token():
    return "secret-token"

def get_db(token: str = Depends(get_token)):
    # Dependency can depend on another dependency
    return f"db-conn-{token}"

@pytest.mark.anyio
async def test_dependency_injection():
    app = Fenrir()

    @app.get("/items")
    async def list_items(db: str = Depends(get_db)):
        return {"db": db}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/items")
        assert res.status_code == 200
        assert res.json() == {"db": "db-conn-secret-token"}
