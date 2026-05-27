import pytest
import httpx
from fenrir import Fenrir, Depends

@pytest.mark.anyio
async def test_circular_dependency():
    app = Fenrir()

    # Define circular dependency chain:
    # dep_a -> dep_b -> dep_a
    def dep_a(val: int = Depends(lambda: dep_b)):
        return val + 1

    def dep_b(val: int = Depends(lambda: dep_a)):
        return val + 2

    # Handler relying on circular dependency
    @app.get("/circular")
    async def get_circular(res: int = Depends(dep_a)):
        return {"result": res}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # A circular dependency error should result in an unhandled exception or 500
        # In our implementation we raise RuntimeError in resolve_parameters which gets converted to a 500 error by default exception handling
        res = await client.get("/circular")
        assert res.status_code == 500
        # Let's verify that running the resolver manually raises the RuntimeError
        from fenrir.dependencies import resolve_parameters
        from fenrir.request import Request
        from fenrir.response import Response
        
        req = Request({"type": "http", "method": "GET", "path": "/circular"})
        resp = Response()
        
        with pytest.raises(RuntimeError, match="Circular dependency detected"):
            await resolve_parameters(get_circular, {}, req, resp)
