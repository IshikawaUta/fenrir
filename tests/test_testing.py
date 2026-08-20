import pytest


@pytest.mark.anyio
async def test_client_requests(app):
    @app.get("/headers")
    def headers_view(req):
        return req.headers.get("x-custom-header", "")

    client = app.test_client()
    resp = await client.get("/headers", headers={"x-custom-header": "test-value"})
    assert resp.status_code == 200
    assert resp.text == "test-value"
