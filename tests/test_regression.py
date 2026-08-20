import pytest

from fenrir import redirect


@pytest.mark.anyio
async def test_relative_redirect(app):
    @app.get("/nested/page")
    def page():
        return redirect("target")  # Relative redirect

    client = app.test_client()
    resp = await client.get("/nested/page")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/nested/target"
