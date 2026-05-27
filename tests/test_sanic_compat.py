import asyncio
import pytest
import httpx
from fenrir import Fenrir, install_sanic_compat, sanic


# --- Patch sys.modules ---
def test_sanic_global_compat():
    install_sanic_compat()
    import sanic as imported_sanic
    assert imported_sanic is sanic


# --- Response helpers ---
@pytest.mark.anyio
async def test_sanic_response_json():
    app = Fenrir()

    @app.get("/json")
    async def handler(request):
        return sanic.response.json({"hello": "world"}, status=200)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/json")
        assert res.status_code == 200
        assert res.json() == {"hello": "world"}


@pytest.mark.anyio
async def test_sanic_response_text():
    app = Fenrir()

    @app.get("/text")
    async def handler(request):
        return sanic.response.text("Hello, World!", status=200)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/text")
        assert res.status_code == 200
        assert res.text == "Hello, World!"


@pytest.mark.anyio
async def test_sanic_response_html():
    app = Fenrir()

    @app.get("/html")
    async def handler(request):
        return sanic.response.html("<h1>Fenrir</h1>", status=201)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/html")
        assert res.status_code == 201
        assert "<h1>Fenrir</h1>" in res.text


@pytest.mark.anyio
async def test_sanic_response_raw():
    app = Fenrir()

    @app.get("/raw")
    async def handler(request):
        return sanic.response.raw(b"\x00\x01\x02", content_type="application/octet-stream")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/raw")
        assert res.status_code == 200
        assert res.content == b"\x00\x01\x02"


@pytest.mark.anyio
async def test_sanic_response_redirect():
    app = Fenrir()

    @app.get("/redirect")
    async def handler(request):
        return sanic.response.redirect("/destination", status=302)

    @app.get("/destination")
    async def dest(request):
        return sanic.response.text("arrived")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True
    ) as client:
        res = await client.get("/redirect")
        assert res.status_code == 200
        assert res.text == "arrived"


# --- Exception mapping ---
@pytest.mark.anyio
async def test_sanic_exceptions():
    app = Fenrir()

    @app.get("/not-found")
    async def handler(request):
        raise sanic.exceptions.NotFound("Not here")

    @app.get("/forbidden")
    async def handler2(request):
        raise sanic.exceptions.Forbidden("Go away")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/not-found")
        assert res.status_code == 404

        res = await client.get("/forbidden")
        assert res.status_code == 403


# --- Listeners (Sanic lifecycle hooks) ---
@pytest.mark.anyio
async def test_sanic_listeners():
    app = Fenrir()
    boot_log = []

    @app.listener("before_server_start")
    async def setup(app_ref):
        boot_log.append("started")

    @app.get("/ping")
    async def ping(request):
        return sanic.response.text("pong")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Manually trigger listeners to simulate server start
        await app._trigger_listeners("before_server_start")
        res = await client.get("/ping")

    assert res.status_code == 200
    assert "started" in boot_log


# --- Blueprint (Sanic-style Blueprint with url_prefix) ---
@pytest.mark.anyio
async def test_sanic_blueprint():
    from fenrir import Blueprint

    app = Fenrir()
    bp = Blueprint("v1", url_prefix="/v1")

    @bp.get("/greet")
    async def greet(request):
        return sanic.response.json({"greeting": "hello"})

    app.register_blueprint(bp)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/v1/greet")
        assert res.status_code == 200
        assert res.json() == {"greeting": "hello"}


# --- add_task (background coroutine scheduling) ---
@pytest.mark.anyio
async def test_sanic_add_task():
    app = Fenrir()
    results = []

    @app.get("/trigger")
    async def trigger(request):
        async def background():
            await asyncio.sleep(0.01)
            results.append("done")

        app.add_task(background)
        return sanic.response.text("ok")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/trigger")
        assert res.status_code == 200

    # Wait briefly for the background task
    await asyncio.sleep(0.05)
    assert "done" in results
