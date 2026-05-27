import pytest
from fenrir import render_template

@pytest.mark.anyio
async def test_rendering(app, tmp_path):
    # Register template path
    app.renderer.env.loader.searchpath.append(str(tmp_path))
    template_file = tmp_path / "test_template_render.html"
    template_file.write_text("Hello {{ user }}!")

    @app.get("/")
    def index():
        return render_template("test_template_render.html", user="Wuta")

    client = app.test_client()
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.text == "Hello Wuta!"
