import httpx
import pytest

from fenrir import Blueprint, Fenrir, Response


@pytest.mark.anyio
async def test_global_middleware():
    app = Fenrir()

    @app.middleware("request")
    async def add_custom_request_header(request):
        request.headers["x-custom-req"] = "intercepted"

    @app.middleware("response")
    async def add_custom_response_header(request, response):
        response.headers["x-custom-res"] = "processed"

    @app.get("/test")
    async def test_endpoint(req):
        return {"header": req.headers.get("x-custom-req")}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/test")
        assert res.status_code == 200
        assert res.json() == {"header": "intercepted"}
        assert res.headers.get("x-custom-res") == "processed"


@pytest.mark.anyio
async def test_short_circuit_middleware():
    app = Fenrir()

    @app.middleware("request")
    async def block_unauthorized(request):
        if "authorization" not in request.headers:
            return Response("Unauthorized", status=401)

    @app.get("/secure")
    async def secure():
        return "Secret Area"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Blocked
        res = await client.get("/secure")
        assert res.status_code == 401
        assert res.text == "Unauthorized"

        # Allowed
        res = await client.get("/secure", headers={"Authorization": "Bearer token"})
        assert res.status_code == 200
        assert res.text == "Secret Area"


@pytest.mark.anyio
async def test_blueprint_middleware():
    app = Fenrir()
    bp = Blueprint("my_bp", url_prefix="/api")

    @bp.middleware("request")
    async def bp_req_mw(request):
        request.headers["x-bp-req"] = "bp-value"

    @bp.middleware("response")
    async def bp_res_mw(request, response):
        response.headers["x-bp-res"] = "bp-value"

    @bp.get("/info")
    async def bp_info(req):
        return {"bp_req": req.headers.get("x-bp-req")}

    @app.get("/global")
    async def global_endpoint(req):
        return {"bp_req": req.headers.get("x-bp-req")}

    app.register_blueprint(bp)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Request to blueprint route
        res = await client.get("/api/info")
        assert res.status_code == 200
        assert res.json() == {"bp_req": "bp-value"}
        assert res.headers.get("x-bp-res") == "bp-value"

        # Request to global route (blueprint middleware should NOT trigger)
        res2 = await client.get("/global")
        assert res2.status_code == 200
        assert res2.json() == {"bp_req": None}
        assert "x-bp-res" not in res2.headers
