import pytest


@pytest.mark.anyio
async def test_teardown_request_called_despite_errors(app):
    called = []

    @app.teardown_request
    def teardown_one(exc):
        called.append("one")
        raise RuntimeError("First teardown error")

    @app.teardown_request
    def teardown_two(exc):
        called.append("two")

    @app.get("/")
    def index():
        return "Hello"

    client = app.test_client()
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.text == "Hello"

    assert "one" in called
    assert "two" in called
