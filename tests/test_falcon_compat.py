import pytest
import httpx
import sys
from fenrir import Fenrir, Response, install_falcon_compat, falcon

# Verify that install_falcon_compat patches sys.modules
def test_falcon_global_compat():
    install_falcon_compat()
    import falcon as imported_falcon
    assert imported_falcon is falcon


@pytest.mark.anyio
async def test_falcon_request_properties():
    app = Fenrir()

    class TestResource:
        async def on_get(self, req, resp):
            # context persistence
            req.context["passed"] = True
            
            # get_header
            user_agent = req.get_header("User-Agent")
            assert user_agent == "TestClient" or "httpx" in user_agent.lower()
            assert req.get_header("X-Non-Existent", "default") == "default"

            # get_param & get_param_as_int
            page = req.get_param_as_int("page", default=1)
            limit = req.get_param_as_int("limit", required=True)
            search = req.get_param("q", default="")

            resp.media = {
                "passed": req.context.get("passed"),
                "page": page,
                "limit": limit,
                "q": search,
            }

    app.add_route("/test", TestResource())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Valid parameters
        res = await client.get("/test?limit=10&page=2&q=hello", headers={"User-Agent": "TestClient"})
        assert res.status_code == 200
        assert res.json() == {
            "passed": True,
            "page": 2,
            "limit": 10,
            "q": "hello"
        }

        # Missing required parameter
        res = await client.get("/test?page=2")
        assert res.status_code == 400
        assert "Missing query parameter" in res.json()["detail"]

        # Invalid integer conversion
        res = await client.get("/test?limit=abc")
        assert res.status_code == 400
        assert "must be an integer" in res.json()["detail"]


@pytest.mark.anyio
async def test_falcon_response_properties():
    app = Fenrir()

    class TestResource:
        async def on_get(self, req, resp):
            # status string parsing
            resp.status = falcon.HTTP_201
            
            # set_header and unset_header
            resp.set_header("X-Custom", "Value")
            resp.set_header("X-Remove-Me", "Temporary")
            resp.unset_header("X-Remove-Me")

            # text alias property
            resp.text = "Body text"

    app.add_route("/test", TestResource())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/test")
        assert res.status_code == 201
        assert res.text == "Body text"
        assert res.headers.get("x-custom") == "Value"
        assert "x-remove-me" not in res.headers


@pytest.mark.anyio
async def test_falcon_before_after_hooks():
    app = Fenrir()

    # Define hook actions
    async def add_auth_context(req, resp, resource, params):
        req.context["user"] = "Alice"

    def audit_log(req, resp, resource, params):
        # We can also modify headers or response
        resp.set_header("X-Audit", "Logged")

    class HookedResource:
        @falcon.before(add_auth_context)
        @falcon.after(audit_log)
        async def on_get(self, req, resp):
            resp.media = {"user": req.context.get("user")}

    app.add_route("/hooked", HookedResource())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/hooked")
        assert res.status_code == 200
        assert res.json() == {"user": "Alice"}
        assert res.headers.get("x-audit") == "Logged"


@pytest.mark.anyio
async def test_falcon_exceptions():
    app = Fenrir()

    class ExceptionResource:
        async def on_get(self, req, resp):
            raise falcon.HTTPForbidden(description="Access Denied")

    app.add_route("/error", ExceptionResource())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/error")
        assert res.status_code == 403
        assert res.json() == {"detail": "Access Denied"}
