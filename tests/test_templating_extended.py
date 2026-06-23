"""Tests for fenrir.templating module."""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from fenrir.templating import BaseTemplateRenderer, Jinja2Renderer, render_template
from fenrir.exceptions import HTTPInternalServerError


# ═══════════════════════════════════════════════════════════════════════
# BaseTemplateRenderer Tests
# ═══════════════════════════════════════════════════════════════════════

class TestBaseTemplateRenderer:
    def test_render_raises_not_implemented(self):
        renderer = BaseTemplateRenderer()
        with pytest.raises(NotImplementedError, match="Renderer must implement render"):
            renderer.render("test.html")


# ═══════════════════════════════════════════════════════════════════════
# Jinja2Renderer Tests
# ═══════════════════════════════════════════════════════════════════════

class TestJinja2Renderer:
    def test_init_without_jinja2(self):
        with patch.dict("sys.modules", {"jinja2": None}):
            with pytest.raises(ImportError, match="Jinja2 is required"):
                Jinja2Renderer("templates")

    def test_render(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "hello.html"), "w") as f:
                f.write("Hello {{ name }}!")
            renderer = Jinja2Renderer(tmpdir)
            result = renderer.render("hello.html", name="World")
            assert result == "Hello World!"

    def test_render_with_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "item.html"), "w") as f:
                f.write("Item: {{ item }} - Price: {{ price }}")
            renderer = Jinja2Renderer(tmpdir)
            result = renderer.render("item.html", item="Widget", price=9.99)
            assert "Item: Widget" in result
            assert "9.99" in result

    def test_render_autoescape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "safe.html"), "w") as f:
                f.write("{{ content }}")
            renderer = Jinja2Renderer(tmpdir)
            result = renderer.render("safe.html", content="<script>alert('x')</script>")
            assert "<script>" not in result
            assert "&lt;" in result

    def test_render_missing_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = Jinja2Renderer(tmpdir)
            with pytest.raises(Exception):
                renderer.render("nonexistent.html")

    def test_relative_path_converted_to_absolute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.html"), "w") as f:
                f.write("test")
            renderer = Jinja2Renderer(tmpdir)
            assert os.path.isabs(renderer.env.loader.searchpath[0])


# ═══════════════════════════════════════════════════════════════════════
# render_template Tests
# ═══════════════════════════════════════════════════════════════════════

class TestRenderTemplate:
    def test_render_with_active_app_renderer(self):
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = "<html>rendered</html>"
        mock_app = MagicMock()
        mock_app.renderer = mock_renderer

        with patch("fenrir.app._active_app", mock_app):
            result = render_template("test.html", name="test")

        assert result == "<html>rendered</html>"
        mock_renderer.render.assert_called_once_with("test.html", name="test")

    def test_render_with_active_app_renderer_error(self):
        mock_renderer = MagicMock()
        mock_renderer.render.side_effect = RuntimeError("template error")
        mock_app = MagicMock()
        mock_app.renderer = mock_renderer

        with patch("fenrir.app._active_app", mock_app):
            with pytest.raises(HTTPInternalServerError, match="Template rendering failed"):
                render_template("bad.html")

    def test_render_without_active_app(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpl_dir = os.path.join(tmpdir, "templates")
            os.makedirs(tmpl_dir)
            with open(os.path.join(tmpl_dir, "fallback.html"), "w") as f:
                f.write("Fallback {{ value }}")

            with patch("fenrir.app._active_app", None):
                os.chdir(tmpdir)
                try:
                    result = render_template("fallback.html", value="test")
                    assert "Fallback test" in result
                finally:
                    os.chdir("/")

    def test_render_fallback_error(self):
        with patch("fenrir.app._active_app", None):
            with pytest.raises(HTTPInternalServerError, match="Template rendering failed"):
                render_template("nonexistent.html")

    def test_render_with_no_renderer(self):
        mock_app = MagicMock(spec=[])  # no renderer attribute
        with patch("fenrir.app._active_app", mock_app):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpl_dir = os.path.join(tmpdir, "templates")
                os.makedirs(tmpl_dir)
                with open(os.path.join(tmpl_dir, "tmpl.html"), "w") as f:
                    f.write("Hello!")
                os.chdir(tmpdir)
                try:
                    result = render_template("tmpl.html")
                    assert result == "Hello!"
                finally:
                    os.chdir("/")
