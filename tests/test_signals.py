import pytest
from fenrir import render_template
from fenrir.signals import request_started, request_finished, got_request_exception, template_rendered

@pytest.mark.anyio
async def test_signals_firing(app, tmp_path):
    events = []

    @request_started.connect
    def on_start(sender, **extra):
        events.append("started")

    @request_finished.connect
    def on_finish(sender, response, **extra):
        events.append("finished")

    @got_request_exception.connect
    def on_error(sender, exception, **extra):
        events.append("error")

    @template_rendered.connect
    def on_template(sender, template, context, **extra):
        events.append(f"template-{template}")

    @app.get("/ok")
    def ok_view():
        # Setup temporary template directory and render
        app.renderer.env.loader.searchpath.append(str(tmp_path))
        template_file = tmp_path / "hello.html"
        template_file.write_text("Hello {{ name }}")
        
        return render_template("hello.html", name="utah")

    @app.get("/error")
    def error_view():
        raise ValueError("Oops")

    client = app.test_client()

    # Test OK request
    resp = await client.get("/ok")
    assert resp.status_code == 200
    assert "started" in events
    assert "template-hello.html" in events
    assert "finished" in events

    events.clear()

    # Test Error request
    resp = await client.get("/error")
    assert resp.status_code == 500
    assert "started" in events
    assert "error" in events
