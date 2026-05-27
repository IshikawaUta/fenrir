import pytest
from fenrir import Fenrir, current_app

def test_app_context_push(app):
    with app.app_context():
        assert current_app.title == "TestApp"

def test_teardown_callbacks_called_despite_errors(app):
    called = []

    @app.teardown_appcontext
    def callback_one(exc):
        called.append("one")
        raise RuntimeError("First error")

    @app.teardown_appcontext
    def callback_two(exc):
        called.append("two")

    with app.app_context():
        pass

    assert "one" in called
    assert "two" in called
