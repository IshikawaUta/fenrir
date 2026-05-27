import pytest
from fenrir import Fenrir, Depends
from fenrir.testing import TestClient

def original_dependency():
    return "original"

def override_dependency():
    return "overridden"

@pytest.mark.anyio
async def test_dependency_overrides():
    app = Fenrir()

    @app.get("/override")
    async def get_override(value: str = Depends(original_dependency)):
        return {"value": value}

    client = TestClient(app)
    
    # Before override
    resp = await client.get("/override")
    assert resp.status_code == 200
    assert resp.json() == {"value": "original"}

    # Apply override
    app.dependency_overrides[original_dependency] = override_dependency
    
    resp = await client.get("/override")
    assert resp.status_code == 200
    assert resp.json() == {"value": "overridden"}

    # Clear override
    app.dependency_overrides.clear()
    
    resp = await client.get("/override")
    assert resp.status_code == 200
    assert resp.json() == {"value": "original"}
