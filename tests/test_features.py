"""Tests for fenrir.features module."""
import os
from unittest.mock import patch

import pytest

from fenrir.features import init_fenrir_monitoring


@pytest.mark.anyio
class TestInitFenrirMonitoring:
    async def test_does_nothing_when_disabled(self, app):
        with patch.dict(os.environ, {"MONITORING_ENABLED": "false"}):
            init_fenrir_monitoring(app)
        # No monitoring routes should be registered
        routes = [r.path_pattern for r in app.router.routes]
        assert not any("/monitoring" in r for r in routes)

    async def test_enables_when_env_true(self, app):
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_fenrir_monitoring(app)
        routes = [r.path_pattern for r in app.router.routes]
        assert any("/monitoring" in r for r in routes)

    async def test_enables_when_kwarg_true(self, app):
        with patch.dict(os.environ, {"MONITORING_ENABLED": "false", "MONITORING_PASSWORD": "testpass"}):
            init_fenrir_monitoring(app, enabled=True)
        routes = [r.path_pattern for r in app.router.routes]
        assert any("/monitoring" in r for r in routes)

    async def test_sets_config_values(self, app):
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "testuser",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "secret",
        }):
            init_fenrir_monitoring(app)
        assert app.config["MONITORING_USER"] == "testuser"

    async def test_dotenv_missing(self, app):
        with patch.dict("sys.modules", {"dotenv": None}):
            with patch.dict(os.environ, {"MONITORING_ENABLED": "false"}):
                init_fenrir_monitoring(app)
        routes = [r.path_pattern for r in app.router.routes]
        assert not any("/monitoring" in r for r in routes)

    async def test_enabled_false_kwarg(self, app):
        with patch.dict(os.environ, {"MONITORING_ENABLED": "false"}):
            init_fenrir_monitoring(app, enabled=False)
        assert app.config.get("MONITORING_ENABLED") is False
