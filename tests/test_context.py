import pytest
import asyncio
import httpx
from fenrir import Fenrir, request, g

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
