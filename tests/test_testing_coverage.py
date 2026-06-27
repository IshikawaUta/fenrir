"""Tests for fenrir.testing — FenrirTestClient."""
import pytest
from fenrir import Fenrir
from fenrir.testing import FenrirTestClient, TestClient


class TestFenrirTestClient:
    def test_alias(self):
        assert TestClient is FenrirTestClient

    @pytest.mark.anyio
    async def test_context_manager(self):
        app = Fenrir()

        @app.route("/ping")
        async def ping():
            return "pong"

        async with FenrirTestClient(app) as client:
            resp = await client.get("/ping")
            assert resp.status_code == 200
            assert resp.text == "pong"

    @pytest.mark.anyio
    async def test_get_request(self):
        app = Fenrir()

        @app.route("/hello")
        async def hello():
            return "world"

        async with FenrirTestClient(app) as client:
            resp = await client.get("/hello")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_post_request(self):
        app = Fenrir()

        @app.route("/echo", methods=["POST"])
        async def echo(request):
            body = request.body  # body is a property, returns bytes
            return body

        async with FenrirTestClient(app) as client:
            resp = await client.post("/echo", content=b"test")
            assert resp.status_code == 200
            assert resp.content == b"test"

    @pytest.mark.anyio
    async def test_put_request(self):
        app = Fenrir()

        @app.route("/update", methods=["PUT"])
        async def update():
            return "updated"

        async with FenrirTestClient(app) as client:
            resp = await client.put("/update")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_delete_request(self):
        app = Fenrir()

        @app.route("/remove", methods=["DELETE"])
        async def remove():
            return "deleted"

        async with FenrirTestClient(app) as client:
            resp = await client.delete("/remove")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_patch_request(self):
        app = Fenrir()

        @app.route("/modify", methods=["PATCH"])
        async def modify():
            return "modified"

        async with FenrirTestClient(app) as client:
            resp = await client.patch("/modify")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_options_request(self):
        app = Fenrir()

        @app.route("/resource")
        async def resource():
            return "ok"

        async with FenrirTestClient(app) as client:
            resp = await client.options("/resource")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_head_request(self):
        app = Fenrir()

        @app.route("/check")
        async def check():
            return "ok"

        async with FenrirTestClient(app) as client:
            resp = await client.head("/check")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_follow_redirects(self):
        app = Fenrir()

        @app.route("/redirect")
        async def do_redirect():
            from fenrir.helpers import redirect
            return redirect("/target")

        @app.route("/target")
        async def target():
            return "arrived"

        async with FenrirTestClient(app, follow_redirects=True) as client:
            resp = await client.get("/redirect")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_generic_request_method(self):
        app = Fenrir()

        @app.route("/info")
        async def info():
            return "info"

        async with FenrirTestClient(app) as client:
            resp = await client.request("GET", "/info")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_404_response(self):
        app = Fenrir()

        async with FenrirTestClient(app) as client:
            resp = await client.get("/nonexistent")
            assert resp.status_code == 404
