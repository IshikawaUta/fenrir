import pytest

from demo_app import app


@pytest.mark.anyio
async def test_logo_route():
    client = app.test_client()
    resp = await client.get("/logo.png")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "image/png"
    assert len(resp.content) > 0

@pytest.mark.anyio
async def test_index_route():
    client = app.test_client()
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "logo-img" in resp.text
    assert "src=\"/logo.png\"" in resp.text

@pytest.mark.anyio
async def test_favicon_route():
    client = app.test_client()
    resp = await client.get("/favicon.ico")
    assert resp.status_code == 200
    assert len(resp.content) > 0

@pytest.mark.anyio
async def test_openapi_json_route():
    """Regression: /openapi.json must not 500 due to Ellipsis in Pydantic required fields."""
    client = app.test_client()
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "openapi" in data
    assert "paths" in data

@pytest.mark.anyio
async def test_head_requests():
    """Verify that HEAD requests to GET routes return 200 OK with an empty body."""
    client = app.test_client()
    for path in ["/", "/logo.png", "/favicon.ico"]:
        resp = await client.request("HEAD", path)
        assert resp.status_code == 200
        assert len(resp.content) == 0

