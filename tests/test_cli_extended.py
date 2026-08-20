"""Tests for fenrir.cli — load_app, cmd_routes, cmd_info, etc."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from fenrir.cli import cmd_info, cmd_routes, format_col, load_app

# ═══════════════════════════════════════════════════════════════════════
# format_col Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFormatCol:
    def test_no_color(self):
        result = format_col("hi", 10)
        assert result == "hi" + " " * 8

    def test_with_color(self):
        result = format_col("hi", 10, "\033[36m")
        assert "\033[36m" in result
        assert "hi" in result


# ═══════════════════════════════════════════════════════════════════════
# load_app Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLoadApp:
    def test_load_from_file(self, tmp_path):
        app_file = tmp_path / "myapp.py"
        app_file.write_text("app = {'title': 'test'}\n")
        result = load_app(str(app_file))
        assert result == {"title": "test"}

    def test_load_from_file_with_colon(self, tmp_path):
        app_file = tmp_path / "myapp.py"
        app_file.write_text("application = {'title': 'colon_test'}\n")
        result = load_app(f"{app_file}:application")
        assert result == {"title": "colon_test"}

    def test_load_fallback_attr(self, tmp_path):
        app_file = tmp_path / "myapp2.py"
        app_file.write_text("application = {'title': 'fallback'}\n")
        result = load_app(str(app_file))
        assert result == {"title": "fallback"}

    def test_load_module_not_found(self):
        with pytest.raises(ImportError, match="Could not import"):
            load_app("nonexistent_module_xyz")

    def test_load_file_not_found_spec(self):
        with pytest.raises(ImportError, match="Could not import module"):
            load_app("/nonexistent/path.py")

    def test_load_no_attr(self, tmp_path):
        app_file = tmp_path / "empty.py"
        app_file.write_text("x = 1\n")
        with pytest.raises(AttributeError, match="has no attribute"):
            load_app(str(app_file))

    def test_load_py_extension_fallback(self, tmp_path):
        app_file = tmp_path / "myapp3.py"
        app_file.write_text("app = {'title': 'ext'}\n")
        os.chdir(tmp_path)
        try:
            result = load_app("myapp3")
            assert result == {"title": "ext"}
        finally:
            os.chdir("/")


# ═══════════════════════════════════════════════════════════════════════
# cmd_routes Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCmdRoutes:
    def test_no_routes(self, capsys):
        mock_route = MagicMock()
        mock_route.path_pattern = "/test"
        mock_route.handler = MagicMock(__name__="handler")
        mock_route.methods = {"GET"}
        mock_route.is_falcon_resource.return_value = False

        app = MagicMock()
        app.title = "test"
        app.router.routes = []
        app.router.websocket_routes = []
        app._route_blueprints = {}

        args = MagicMock(target="dummy")
        with patch("fenrir.cli.load_app", return_value=app):
            cmd_routes(args)
        captured = capsys.readouterr()
        assert "No routes" in captured.out

    def test_falcon_routes(self, capsys):
        falcon_handler = MagicMock()
        falcon_handler.__class__.__name__ = "UserResource"
        falcon_handler.on_get = MagicMock()
        falcon_handler.on_post = MagicMock()

        mock_route = MagicMock()
        mock_route.path_pattern = "/users"
        mock_route.handler = falcon_handler
        mock_route.is_falcon_resource.return_value = True

        app = MagicMock()
        app.title = "test"
        app.router.routes = [mock_route]
        app.router.websocket_routes = []
        app._route_blueprints = {}

        args = MagicMock(target="dummy")
        with patch("fenrir.cli.load_app", return_value=app):
            cmd_routes(args)
        captured = capsys.readouterr()
        assert "GET" in captured.out or "POST" in captured.out

    def test_websocket_routes(self, capsys):
        ws_route = MagicMock()
        ws_route.path_pattern = "/ws"
        ws_route.handler = MagicMock(__name__="ws_handler")
        ws_route.is_falcon_resource.return_value = False

        app = MagicMock()
        app.title = "test"
        app.router.routes = []
        app.router.websocket_routes = [ws_route]
        app._route_blueprints = {}

        args = MagicMock(target="dummy")
        with patch("fenrir.cli.load_app", return_value=app):
            cmd_routes(args)
        captured = capsys.readouterr()
        assert "WEBSOCKET" in captured.out


# ═══════════════════════════════════════════════════════════════════════
# cmd_info Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCmdInfo:
    def test_no_target(self, capsys):
        args = MagicMock(target=None)
        cmd_info(args)
        captured = capsys.readouterr()
        assert "Fenrir version" in captured.out

    def test_with_target(self, capsys):
        app = MagicMock()
        app.title = "MyApp"
        app.version = "1.0.0"
        app.router.routes = [1, 2, 3]
        app.router.websocket_routes = []
        app._asgi_middlewares = []

        args = MagicMock(target="myapp")
        with patch("fenrir.cli.load_app", return_value=app):
            cmd_info(args)
        captured = capsys.readouterr()
        assert "MyApp" in captured.out
        assert "3" in captured.out  # routes count

    def test_target_load_error(self, capsys):
        args = MagicMock(target="bad")
        with patch("fenrir.cli.load_app", side_effect=ImportError("nope")):
            cmd_info(args)
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_compat_layers(self, capsys):
        app = MagicMock()
        app.title = "App"
        app.version = "1.0"
        app.router.routes = []
        app.router.websocket_routes = []
        app._asgi_middlewares = []

        args = MagicMock(target="myapp")
        sys.modules["flask"] = MagicMock()
        try:
            with patch("fenrir.cli.load_app", return_value=app):
                cmd_info(args)
            captured = capsys.readouterr()
            assert "Flask" in captured.out
        finally:
            del sys.modules["flask"]

    def test_middleware_count_fallback(self, capsys):
        app = MagicMock()
        app.title = "App"
        app.version = "1.0"
        app.router.routes = []
        app.router.websocket_routes = []
        del app.middleware_stack
        app._asgi_middlewares = [1, 2]

        args = MagicMock(target="myapp")
        with patch("fenrir.cli.load_app", return_value=app):
            cmd_info(args)
        captured = capsys.readouterr()
        assert "2" in captured.out
