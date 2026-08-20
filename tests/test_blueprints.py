import pytest

from fenrir import Blueprint


@pytest.mark.anyio
async def test_blueprint_lifecycle(app):
    bp = Blueprint("api", url_prefix="/api")
    called = []

    @bp.before_request
    def before():
        called.append("before")

    @bp.after_request
    def after(req, resp):
        called.append("after")
        return resp

    @bp.teardown_request
    def teardown(exc):
        called.append("teardown")

    @bp.get("/info")
    def info():
        return "api info"

    app.register_blueprint(bp)
    client = app.test_client()
    resp = await client.get("/api/info")
    assert resp.status_code == 200
    assert resp.text == "api info"

    assert "before" in called
    assert "after" in called
    assert "teardown" in called
