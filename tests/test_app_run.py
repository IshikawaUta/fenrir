"""Coverage tests for fenrir.app — Fenrir.run() and _get_active_app()."""

import pytest

from fenrir import Fenrir
from fenrir.app import _get_active_app


class _FakeArbiter:
    kwargs = {}

    def __init__(self, **kwargs):
        _FakeArbiter.kwargs = kwargs

    def start(self):
        raise KeyboardInterrupt


@pytest.fixture
def fake_arbiter(monkeypatch):
    monkeypatch.setattr("asteri.arbiter.Arbiter", _FakeArbiter)
    return _FakeArbiter


def test_get_active_app_outside_request_context(monkeypatch):
    class _Unset:
        def get(self):
            raise LookupError("unset")
    monkeypatch.setattr("fenrir.context._app_ctx_var", _Unset())
    assert _get_active_app() is None


def test_get_active_app_in_context():
    from fenrir.context import _app_ctx_var
    app = Fenrir()
    token = _app_ctx_var.set(app)
    try:
        assert _get_active_app() is app
    finally:
        _app_ctx_var.reset(token)


def test_run_explicit_app_path(fake_arbiter):
    app = Fenrir()
    # KeyboardInterrupt from start() is swallowed -> no exception
    app.run(host="0.0.0.0", port=9999, workers=2, app_path="myapp:app", timeout=30)
    arb = fake_arbiter.kwargs
    assert arb["app_path"] == "myapp:app"
    assert arb["binds"] == ["0.0.0.0:9999"]
    assert arb["num_workers"] == 2
    assert arb["timeout"] == 30


def test_run_auto_detect_app_path(fake_arbiter):
    app = Fenrir()
    mod_name = "tests.test_app_run"
    globs = {"__name__": mod_name, "__file__": __file__, "app": app}
    exec("app.run(app_path=None)", globs)
    assert "app_path" in _FakeArbiter.kwargs


def test_run_auto_detect_main_module(fake_arbiter):
    app = Fenrir()
    globs = {"__name__": "__main__", "__file__": "/tmp/somewhere/app.py", "app": app}
    exec("app.run()", globs)
    assert "app_path" in fake_arbiter.kwargs


def test_run_raises_without_app_path():
    app = Fenrir()
    with pytest.raises(RuntimeError, match="Could not auto-detect app_path"):
        # namespace without __file__ -> auto-detection impossible
        exec("app.run()", {"app": app})
