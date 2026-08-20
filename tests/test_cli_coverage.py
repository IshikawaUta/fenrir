"""Tests for fenrir.cli — CLI subcommands coverage."""
import os
import tempfile
from unittest.mock import patch

import pytest

from fenrir.cli import (
    _update_env_var,
    format_col,
    load_app,
    main,
    print_banner,
)


class TestPrintBanner:
    def test_prints_without_error(self, capsys):
        print_banner("TestApp")
        captured = capsys.readouterr()
        assert "TestApp" in captured.out or "FENRIR" in captured.out

    def test_prints_empty_title(self, capsys):
        print_banner("")
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestFormatCol:
    def test_basic_col(self):
        result = format_col("hello", 20)
        assert len(result) == 20
        assert result.strip() == "hello"

    def test_col_with_color(self):
        # color_code should be ANSI escape code like "\033[31m" for red
        result = format_col("test", 10, color_code="\033[31m")
        # Should start with the color code and end with reset
        assert result.startswith("\033[31m")
        assert result.endswith("\033[0m")
        # Content should be padded to width
        assert len(result) >= 10


class TestLoadApp:
    def test_load_app_invalid_format(self):
        # No colon - treated as module path
        with pytest.raises((ImportError, ModuleNotFoundError)):
            load_app("this_module_definitely_does_not_exist_12345")

    def test_load_app_nonexistent_module(self):
        # Has colon - tries to import module part
        with pytest.raises((ImportError, ModuleNotFoundError)):
            load_app("nonexistent_module_xyz:app")

    def test_load_app_attr_not_found(self):
        # Module exists but attribute doesn't
        with pytest.raises(AttributeError):
            load_app("os:nonexistent_attribute_12345")


class TestUpdateEnvVar:
    def test_creates_env_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                _update_env_var("MY_KEY", "my_value")
                env_path = os.path.join(tmpdir, ".env")
                with open(env_path) as f:
                    content = f.read()
                assert "MY_KEY=my_value" in content
            finally:
                os.chdir(old_cwd)

    def test_updates_existing_var(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                _update_env_var("KEY", "old")
                _update_env_var("KEY", "new")
                env_path = os.path.join(tmpdir, ".env")
                with open(env_path) as f:
                    content = f.read()
                assert "KEY=new" in content
                assert "KEY=old" not in content
            finally:
                os.chdir(old_cwd)

    def test_preserves_other_vars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                _update_env_var("A", "1")
                _update_env_var("B", "2")
                env_path = os.path.join(tmpdir, ".env")
                with open(env_path) as f:
                    content = f.read()
                assert "A=1" in content
                assert "B=2" in content
            finally:
                os.chdir(old_cwd)


class TestMain:
    def test_main_help(self, capsys, monkeypatch):
        with patch('sys.argv', ["fenrir", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

    def test_main_version(self, capsys, monkeypatch):
        with patch('sys.argv', ["fenrir", "--version"]):
            with pytest.raises(SystemExit):
                main()

    def test_routes_no_app(self):
        with patch('fenrir.cli.load_app') as mock_load_app:
            mock_app = type('MockApp', (), {
                'title': 'TestApp',
                'version': '1.0.0',
                '_route_blueprints': {},
                'router': type('Router', (), {
                    'routes': [],
                    'websocket_routes': []
                })()
            })()
            mock_load_app.return_value = mock_app

            from fenrir.cli import cmd_routes
            # Mock sys.argv for cmd_routes
            with patch('sys.argv', ["fenrir", "routes", "mock:app"]):
                # cmd_routes doesn't return, so we just call it
                args = type('Args', (), {'target': 'mock:app'})()
                cmd_routes(args)
