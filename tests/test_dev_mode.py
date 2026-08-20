import asyncio
import os

import pytest

from fenrir import (
    Fenrir,
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnauthorized,
    HTTPUnprocessableEntity,
)
from fenrir.response import JSONResponse
from fenrir.testing import FenrirTestClient


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure FENRIR_DEV_MODE is cleaned up after each test."""
    os.environ.pop("FENRIR_DEV_MODE", None)
    yield
    os.environ.pop("FENRIR_DEV_MODE", None)


# ── Debug Page Rendering ──────────────────────────────────────────────


class TestDevModeDebugPage:
    """Test that debug page renders correctly in dev mode."""

    def test_debug_page_renders_html(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("page not found")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "<!DOCTYPE html>" in r.text
                assert "Fenrir" in r.text
                assert "HTTPNotFound" in r.text
                assert "Not Found" in r.text
        asyncio.run(run())

    def test_debug_page_http_400(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPBadRequest("bad input")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 400
                assert "Bad Request" in r.text
                assert "bad input" in r.text
        asyncio.run(run())

    def test_debug_page_http_401(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPUnauthorized("no auth")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 401
                assert "Unauthorized" in r.text
        asyncio.run(run())

    def test_debug_page_http_403(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPForbidden("forbidden")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 403
                assert "Forbidden" in r.text
        asyncio.run(run())

    def test_debug_page_http_404(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("not found")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "Not Found" in r.text
        asyncio.run(run())

    def test_debug_page_http_500(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise ValueError("server broke")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 500
                assert "Internal Server Error" in r.text
        asyncio.run(run())

    def test_debug_page_shows_traceback(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise RuntimeError("boom")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "Traceback" in r.text
                assert "RuntimeError" in r.text
                assert "boom" in r.text
        asyncio.run(run())

    def test_debug_page_shows_request_info(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("missing")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "GET" in r.text
                assert "/error" in r.text
        asyncio.run(run())

    def test_debug_page_shows_query_string(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("missing")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error?page=1&limit=10")
                assert "page=1" in r.text
                assert "limit=10" in r.text
        asyncio.run(run())

    def test_debug_page_empty_detail(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            exc = HTTPNotFound()
            exc.detail = ""
            raise exc

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "Fenrir" in r.text
        asyncio.run(run())

    def test_debug_page_has_sidebar(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "sidebar" in r.text
                assert "Exception" in r.text
        asyncio.run(run())

    def test_debug_page_has_stack_trace_tab(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "Stack Trace" in r.text
                assert "Request" in r.text
                assert "Raw Trace" in r.text
        asyncio.run(run())

    def test_debug_page_has_collapsible_frames(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "frame-card" in r.text
                assert "toggleVendor" in r.text
                assert "collapseAll" in r.text
                assert "expandAll" in r.text
        asyncio.run(run())


# ── XSS Prevention ────────────────────────────────────────────────────


class TestDevModeXSS:
    """Test that HTML in error details is properly escaped."""

    def test_script_tag_escaped(self):
        app = Fenrir(dev_mode=True)

        @app.get("/xss")
        async def trigger():
            raise HTTPNotFound("<script>alert(1)</script>")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/xss")
                # The error detail should be escaped, not raw HTML
                assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
                # Check the detail is in the message card, not as raw HTML
                assert "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>" in r.text
        asyncio.run(run())

    def test_quotes_escaped(self):
        app = Fenrir(dev_mode=True)

        @app.get("/xss")
        async def trigger():
            raise HTTPNotFound('test"onload=alert(1)')

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/xss")
                assert 'test"onload=alert(1)' not in r.text
        asyncio.run(run())

    def test_angle_bracket_escaped(self):
        app = Fenrir(dev_mode=True)

        @app.get("/xss")
        async def trigger():
            raise HTTPNotFound('<img src=x onerror=alert(1)>')

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/xss")
                assert "<img src=x" not in r.text
                assert "&lt;img" in r.text
        asyncio.run(run())


# ── Custom Handler Override ───────────────────────────────────────────


class TestDevModeCustomHandler:
    """Test that custom exception handlers take priority over debug page."""

    def test_custom_status_handler_overrides_debug_page(self):
        app = Fenrir(dev_mode=True)

        @app.exception(404)
        async def custom_404(req, exc):
            return JSONResponse({"custom": "not found"}, status=404)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("should use debug page instead")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "<!DOCTYPE html>" in r.text
                assert "sidebar" in r.text
        asyncio.run(run())

    def test_custom_exception_handler_overrides_debug_page(self):
        app = Fenrir(dev_mode=True)

        @app.exception(HTTPForbidden)
        async def custom_forbidden(req, exc):
            return JSONResponse({"custom": "forbidden"}, status=403)

        @app.get("/error")
        async def trigger():
            raise HTTPForbidden("should use debug page instead")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 403
                assert "<!DOCTYPE html>" in r.text
                assert "sidebar" in r.text
        asyncio.run(run())

    def test_handler_reraise_shows_inner_exception(self):
        app = Fenrir(dev_mode=True)

        @app.exception(404)
        async def bad_handler(req, exc):
            raise RuntimeError("handler crashed")

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("original")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "<!DOCTYPE html>" in r.text
        asyncio.run(run())


# ── Non-Dev Mode Returns JSON ─────────────────────────────────────────


class TestNonDevMode:
    """Test that non-dev mode returns JSON responses."""

    def test_http_exception_returns_json(self):
        app = Fenrir(dev_mode=False)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("page missing")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "<!DOCTYPE html>" not in r.text
                assert '"detail"' in r.text
                assert "page missing" in r.text
        asyncio.run(run())

    def test_python_exception_returns_json(self):
        app = Fenrir(dev_mode=False)

        @app.get("/error")
        async def trigger():
            raise ValueError("something broke")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 500
                assert "<!DOCTYPE html>" not in r.text
                assert '"detail"' in r.text
        asyncio.run(run())


# ── dev_mode Parameter ────────────────────────────────────────────────


class TestDevModeParameter:
    """Test dev_mode initialization behavior."""

    def test_dev_mode_default_is_none_reads_env(self):
        """Without explicit dev_mode, reads FENRIR_DEV_MODE env var."""
        os.environ.pop("FENRIR_DEV_MODE", None)
        app = Fenrir()
        assert app.dev_mode is False

        os.environ["FENRIR_DEV_MODE"] = "1"
        import importlib

        import fenrir._app_core as core
        importlib.reload(core)
        app2 = core.FenrirCoreMixin.__new__(core.FenrirCoreMixin)
        app2._init_core()
        assert app2.dev_mode is True
        os.environ.pop("FENRIR_DEV_MODE", None)

    def test_explicit_true_overrides_missing_env(self):
        os.environ.pop("FENRIR_DEV_MODE", None)
        app = Fenrir(dev_mode=True)
        assert app.dev_mode is True

    def test_explicit_false_overrides_env_var(self):
        os.environ["FENRIR_DEV_MODE"] = "1"
        import importlib

        import fenrir._app_core as core
        importlib.reload(core)
        app = core.FenrirCoreMixin.__new__(core.FenrirCoreMixin)
        app._init_core(dev_mode=False)
        assert app.dev_mode is False
        os.environ.pop("FENRIR_DEV_MODE", None)

    def test_env_var_not_set_default_false(self):
        os.environ.pop("FENRIR_DEV_MODE", None)
        app = Fenrir()
        assert app.dev_mode is False


# ── Client Info Detection ─────────────────────────────────────────────


class TestDevModeClientInfo:
    """Test that client info is correctly extracted."""

    def test_client_info_from_scope(self):
        """ASGI scope client tuple is used when available."""
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                # httpx ASGI transport sets client in scope
                assert "unknown:unknown" not in r.text
        asyncio.run(run())

    def test_client_info_from_x_forwarded_for(self):
        """X-Forwarded-For header used as fallback."""
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error", headers={"X-Forwarded-For": "10.0.0.1, 10.0.0.2"})
                assert "10.0.0.1" in r.text
        asyncio.run(run())

    def test_client_info_from_x_real_ip(self):
        """X-Real-IP header used as fallback."""
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error", headers={"X-Real-IP": "192.168.1.100"})
                assert "192.168.1.100" in r.text
        asyncio.run(run())


# ── ASGI Middleware Errors ────────────────────────────────────────────


class TestDevModeASGIMiddlewareErrors:
    """Test that ASGI-level middleware errors also show debug page."""

    def test_asgi_middleware_error_shows_debug_page(self):
        """Exception from ASGI middleware renders debug page."""
        class BrokenMiddleware:
            def __init__(self, app):
                self.app = app
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    raise RuntimeError("asgi mw crash")
                await self.app(scope, receive, send)

        app = Fenrir(dev_mode=True)
        app.add_middleware(BrokenMiddleware)

        @app.get("/ok")
        async def ok():
            return {"ok": True}

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/ok")
                assert r.status_code == 500
                assert "<!DOCTYPE html>" in r.text
                assert "RuntimeError" in r.text
                assert "asgi mw crash" in r.text
        asyncio.run(run())

    def test_asgi_middleware_error_non_dev_returns_json(self):
        """ASGI middleware error in non-dev mode returns JSON."""
        class BrokenMiddleware:
            def __init__(self, app):
                self.app = app
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    raise RuntimeError("asgi mw crash")
                await self.app(scope, receive, send)

        app = Fenrir(dev_mode=False)
        app.add_middleware(BrokenMiddleware)

        @app.get("/ok")
        async def ok():
            return {"ok": True}

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/ok")
                assert r.status_code == 500
                assert "detail" in r.json()
        asyncio.run(run())


# ── Missing Coverage ─────────────────────────────────────────────────


class TestDevModeAdditionalCoverage:
    """Additional tests for uncovered features."""

    def test_debug_page_http_409(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPConflict("duplicate entry")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 409
                assert "<!DOCTYPE html>" in r.text
                assert "409" in r.text
                assert "HTTPConflict" in r.text
        asyncio.run(run())

    def test_debug_page_http_422(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPUnprocessableEntity("invalid data")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 422
                assert "<!DOCTYPE html>" in r.text
                assert "422" in r.text
        asyncio.run(run())

    def test_debug_page_http_500_internal(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPInternalServerError("server broke")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 500
                assert "<!DOCTYPE html>" in r.text
        asyncio.run(run())

    def test_exception_class_name_in_page(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "HTTPNotFound" in r.text
        asyncio.run(run())

    def test_raw_trace_tab_content(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise RuntimeError("raw trace test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "tab-rawtrace" in r.text
                assert "traceback-box" in r.text
                assert "RuntimeError" in r.text
        asyncio.run(run())

    def test_toggle_vendor_button(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test vendor")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "toggleVendor()" in r.text
                assert "data-vendor=" in r.text
        asyncio.run(run())

    def test_responsive_media_queries(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test responsive")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert "@media" in r.text
                assert "max-width: 768px" in r.text
                assert "max-width: 480px" in r.text
        asyncio.run(run())

    def test_client_info_host_header_fallback(self):
        app = Fenrir(dev_mode=True)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error", headers={"Host": "example.com:8080"})
                assert "example.com" in r.text
        asyncio.run(run())

    def test_custom_handler_ignored_by_status_in_dev(self):
        """Custom status handler ignored in dev mode."""
        app = Fenrir(dev_mode=True)

        @app.exception(404)
        async def custom_404(req, exc):
            return JSONResponse({"custom": True}, status=404)

        @app.get("/error")
        async def trigger():
            raise HTTPNotFound("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 404
                assert "<!DOCTYPE html>" in r.text
                assert "sidebar" in r.text
        asyncio.run(run())

    def test_custom_handler_ignored_by_class_in_dev(self):
        """Custom exception class handler ignored in dev mode."""
        app = Fenrir(dev_mode=True)

        @app.exception(HTTPForbidden)
        async def custom_forbidden(req, exc):
            return JSONResponse({"custom": True}, status=403)

        @app.get("/error")
        async def trigger():
            raise HTTPForbidden("test")

        async def run():
            async with FenrirTestClient(app) as c:
                r = await c.get("/error")
                assert r.status_code == 403
                assert "<!DOCTYPE html>" in r.text
        asyncio.run(run())
