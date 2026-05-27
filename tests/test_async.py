import pytest

@pytest.mark.anyio
async def test_async_handler(app):
    @app.get("/async")
    async def async_view():
        return "Async View Working"

    @app.get("/sync")
    def sync_view():
        return "Sync View Working"

    client = app.test_client()
    
    r = await client.get("/async")
    assert r.status_code == 200
    assert r.text == "Async View Working"

    r = await client.get("/sync")
    assert r.status_code == 200
    assert r.text == "Sync View Working"
