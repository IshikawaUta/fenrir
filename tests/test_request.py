import pytest


@pytest.mark.anyio
async def test_trusted_hosts(app):
    app.config["TRUSTED_HOSTS"] = ["localhost", "*.example.com"]

    @app.get("/")
    def index():
        return "OK"

    client = app.test_client()

    # Valid hosts
    resp = await client.get("/", headers={"Host": "localhost"})
    assert resp.status_code == 200

    resp = await client.get("/", headers={"Host": "sub.example.com"})
    assert resp.status_code == 200

    # Invalid host
    resp = await client.get("/", headers={"Host": "attacker.com"})
    assert resp.status_code == 400
    assert "Invalid Host header" in resp.text
