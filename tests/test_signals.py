import pytest

from fenrir import render_template
from fenrir.signals import (
    Signal,
    got_request_exception,
    request_finished,
    request_started,
    template_rendered,
)


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


def test_signals_send_async_receiver_without_loop():
    s = Signal("x")

    @s.connect
    async def receiver(sender, **extra):
        pass

    assert s.send("sender") == []


@pytest.mark.anyio
async def test_signals_async_cache_eviction(monkeypatch):
    import asyncio

    import fenrir.signals as sig

    monkeypatch.setattr(sig, "_RECEIVER_CACHE_MAX", 2)
    sig._receiver_is_async_cache.clear()
    s = Signal("x")

    def make():
        async def receiver(sender, **extra):
            pass
        return receiver

    for r in (make(), make(), make()):
        s.connect(r)
        s.send("sender")
        await asyncio.sleep(0)

    assert len(sig._receiver_is_async_cache) == 2
