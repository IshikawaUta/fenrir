"""Tests for fenrir.plugins — extended coverage."""
from unittest.mock import MagicMock, patch

import pytest

from fenrir.plugins import (
    Plugin,
    PluginConfigError,
    PluginRegistry,
    PluginVersionError,
    plugin_hook,
    setup_plugins,
)


class SimplePlugin(Plugin):
    name = "simple"
    version = "1.0.0"
    description = "A simple plugin"

    def setup(self, app, **kwargs):
        self._setup_called = True

    def teardown(self, app):
        self._teardown_called = True


class DepPlugin(Plugin):
    name = "depp"
    version = "1.0.0"
    requires = ["simple"]

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        pass


class ConflictPlugin(Plugin):
    name = "conflict"
    version = "1.0.0"
    conflicts = ["simple"]

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        pass


class SchemaPlugin(Plugin):
    name = "schema"
    version = "1.0.0"
    config_schema = {
        "host": {"type": "str", "default": "localhost"},
        "port": {"type": "int", "default": 8080, "min": 1, "max": 65535},
        "debug": {"type": "bool", "default": False},
        "rate": {"type": "float", "default": 1.0},
    }

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        pass


class HealthPlugin(Plugin):
    name = "health"
    version = "1.0.0"

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        pass

    def health_check(self):
        return {"status": "healthy", "message": "ok"}


class BadHealthPlugin(Plugin):
    name = "bad_health"
    version = "1.0.0"

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        pass

    def health_check(self):
        raise RuntimeError("check failed")


class TeardownFailPlugin(Plugin):
    name = "teardown_fail"
    version = "1.0.0"

    def setup(self, app, **kwargs):
        pass

    def teardown(self, app):
        raise RuntimeError("teardown error")


# ═══════════════════════════════════════════════════════════════════════
# PluginRegistry Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPluginRegistry:
    def test_register_class(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        assert "simple" in reg._registry

    def test_register_instance(self):
        p = SimplePlugin()
        reg = PluginRegistry(MagicMock())
        reg.register(p)
        assert "simple" in reg._registry
        assert reg._registry["simple"]["type"] == "instance"

    def test_register_lazy(self):
        reg = PluginRegistry(MagicMock())
        reg._register_lazy("some.module:MyPlugin")
        assert "MyPlugin" in reg._registry

    def test_enable_disable(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        assert reg.enable("simple") is True
        assert reg.is_enabled("simple") is True
        assert reg.disable("simple") is True
        assert reg.is_enabled("simple") is False

    def test_enable_already_enabled(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple")
        assert reg.enable("simple") is True

    def test_disable_not_enabled(self):
        reg = PluginRegistry(MagicMock())
        assert reg.disable("nonexistent") is True

    def test_enable_not_found(self):
        reg = PluginRegistry(MagicMock())
        assert reg.enable("nonexistent") is False

    def test_enable_with_dependencies(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(DepPlugin)
        assert reg.enable("depp") is True
        assert reg.is_enabled("simple") is True
        assert reg.is_enabled("depp") is True

    def test_enable_conflict(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(ConflictPlugin)
        reg.enable("simple")
        assert reg.enable("conflict") is False

    def test_disable_with_dependent(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(DepPlugin)
        reg.enable("depp")
        assert reg.disable("simple") is False

    def test_disable_teardown_fails(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(TeardownFailPlugin)
        reg.enable("teardown_fail")
        assert reg.disable("teardown_fail") is False

    def test_enable_fails_setup(self):
        class FailSetupPlugin(Plugin):
            name = "fail_setup"
            version = "1.0.0"
            def setup(self, app, **kwargs):
                raise RuntimeError("setup error")
            def teardown(self, app):
                pass

        reg = PluginRegistry(MagicMock())
        reg._register_class(FailSetupPlugin)
        assert reg.enable("fail_setup") is False

    def test_reload(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple")
        assert reg.reload("simple") is True
        assert reg.is_enabled("simple") is True

    def test_get(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple")
        assert reg.get("simple") is not None

    def test_list_plugins(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        result = reg.list_plugins()
        assert "simple" in result

    def test_get_enabled(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple")
        assert "simple" in reg.get_enabled()

    def test_get_plugin_config(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple", host="0.0.0.0")
        config = reg.get_plugin_config("simple")
        assert config.get("host") == "0.0.0.0"

    def test_get_dependencies(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(DepPlugin)
        deps = reg.get_dependencies("depp")
        assert "simple" in deps

    def test_get_dependents(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(DepPlugin)
        reg.enable("depp")
        dependents = reg.get_dependents("simple")
        assert "depp" in dependents

    def test_enable_all_disable_all(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg._register_class(HealthPlugin)
        results = reg.enable_all()
        assert results["simple"] is True
        results = reg.disable_all()
        assert results["simple"] is True

    def test_cleanup(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(SimplePlugin)
        reg.enable("simple")
        reg.cleanup()
        assert len(reg._plugins) == 0
        assert len(reg._registry) == 0


# ═══════════════════════════════════════════════════════════════════════
# Config Validation Tests
# ═══════════════════════════════════════════════════════════════════════

class TestConfigValidation:
    def test_validate_config(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        config = {"host": "0.0.0.0", "port": 9000, "debug": True, "rate": 2.0}
        result = reg._validate_config(plugin, config)
        assert result["host"] == "0.0.0.0"
        assert result["port"] == 9000
        assert result["debug"] is True

    def test_validate_config_defaults(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        result = reg._validate_config(plugin, {})
        assert result["host"] == "localhost"
        assert result["port"] == 8080

    def test_validate_config_required_missing(self):
        reg = PluginRegistry(MagicMock())
        plugin = Plugin()
        plugin.config_schema = {"name": {"type": "str", "required": True}}
        with pytest.raises(PluginConfigError, match="required"):
            reg._validate_config(plugin, {})

    def test_validate_config_type_str(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        result = reg._validate_config(plugin, {"host": 123})
        assert result["host"] == "123"

    def test_validate_config_type_int(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        result = reg._validate_config(plugin, {"port": "9000"})
        assert result["port"] == 9000

    def test_validate_config_type_int_bool_rejected(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        with pytest.raises(PluginConfigError, match="not bool"):
            reg._validate_config(plugin, {"port": True})

    def test_validate_config_type_float(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        result = reg._validate_config(plugin, {"rate": "2.5"})
        assert result["rate"] == 2.5

    def test_validate_config_type_bool_from_str(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        result = reg._validate_config(plugin, {"debug": "true"})
        assert result["debug"] is True

    def test_validate_config_range_min(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        with pytest.raises(PluginConfigError, match=">="):
            reg._validate_config(plugin, {"port": 0})

    def test_validate_config_range_max(self):
        reg = PluginRegistry(MagicMock())
        plugin = SchemaPlugin()
        with pytest.raises(PluginConfigError, match="<="):
            reg._validate_config(plugin, {"port": 99999})

    def test_validate_config_no_schema(self):
        reg = PluginRegistry(MagicMock())
        plugin = SimplePlugin()
        result = reg._validate_config(plugin, {"anything": "goes"})
        assert result == {"anything": "goes"}


# ═══════════════════════════════════════════════════════════════════════
# Version Check Tests
# ═══════════════════════════════════════════════════════════════════════

class TestVersionCheck:
    def test_check_version_no_requirements(self):
        reg = PluginRegistry(MagicMock())
        plugin = SimplePlugin()
        reg._check_version(plugin)  # Should not raise

    def test_check_version_min_fails(self):
        reg = PluginRegistry(MagicMock())
        plugin = SimplePlugin()
        plugin.min_fenrir_version = "999.0.0"
        with pytest.raises(PluginVersionError):
            reg._check_version(plugin)

    def test_check_version_max_fails(self):
        reg = PluginRegistry(MagicMock())
        plugin = SimplePlugin()
        plugin.max_fenrir_version = "0.0.1"
        with pytest.raises(PluginVersionError):
            reg._check_version(plugin)

    def test_check_version_packaging_missing(self):
        reg = PluginRegistry(MagicMock())
        plugin = SimplePlugin()
        plugin.min_fenrir_version = "0.0.1"
        with patch.dict("sys.modules", {"packaging": None}):
            reg._check_version(plugin)  # Should warn and return


# ═══════════════════════════════════════════════════════════════════════
# Dependency Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDependencies:
    def test_circular_dependency(self):
        class A(Plugin):
            name = "a"
            version = "1.0.0"
            requires = ["b"]
            def setup(self, app, **kwargs): pass
            def teardown(self, app): pass

        class B(Plugin):
            name = "b"
            version = "1.0.0"
            requires = ["a"]
            def setup(self, app, **kwargs): pass
            def teardown(self, app): pass

        reg = PluginRegistry(MagicMock())
        reg._register_class(A)
        reg._register_class(B)
        # Circular dependency will cause enable to return False (caught by enable())
        result = reg.enable("a")
        assert result is False

    def test_resolve_missing_plugin(self):
        reg = PluginRegistry(MagicMock())
        result = reg._resolve_dependencies("nonexistent")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Health Check Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    def test_check_health(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(HealthPlugin)
        reg.enable("health")
        results = reg.check_health(force=True)
        assert results["health"].status == "healthy"

    def test_check_health_bad_plugin(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(BadHealthPlugin)
        reg.enable("bad_health")
        results = reg.check_health(force=True)
        assert results["bad_health"].status == "unhealthy"

    def test_check_health_cached(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(HealthPlugin)
        reg.enable("health")
        r1 = reg.check_health(force=True)
        r2 = reg.check_health(force=False)  # uses cache
        assert r2["health"].last_check == r1["health"].last_check

    def test_get_plugin_health(self):
        reg = PluginRegistry(MagicMock())
        reg._register_class(HealthPlugin)
        reg.enable("health")
        reg.check_health(force=True)
        h = reg.get_plugin_health("health")
        assert h is not None

    def test_get_plugin_health_not_found(self):
        reg = PluginRegistry(MagicMock())
        assert reg.get_plugin_health("nope") is None


# ═══════════════════════════════════════════════════════════════════════
# Hook Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHooks:
    def test_register_hook(self):
        reg = PluginRegistry(MagicMock())
        reg.register_hook("on_test", lambda **kw: None)
        assert "on_test" in reg._hooks

    def test_emit_hook(self):
        reg = PluginRegistry(MagicMock())
        results = []
        reg.register_hook("on_event", lambda name: results.append(name))
        reg._emit_hook("on_event", name="test")
        assert results == ["test"]

    def test_emit_hook_exception(self):
        reg = PluginRegistry(MagicMock())
        reg.register_hook("on_event", lambda **kw: 1 / 0)
        reg._emit_hook("on_event")  # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# Discover from path Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDiscoverFromPath:
    def test_discover_from_path_nonexistent(self):
        reg = PluginRegistry(MagicMock())
        count = reg.discover_from_path("/nonexistent/path")
        assert count == 0

    def test_discover_from_path(self, tmp_path):
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("""
from fenrir.plugins import Plugin

class TestPlugin(Plugin):
    name = "from_path"
    version = "1.0.0"
    def setup(self, app, **kwargs): pass
    def teardown(self, app): pass
""")
        reg = PluginRegistry(MagicMock())
        count = reg.discover_from_path(str(tmp_path))
        assert count == 1
        assert "from_path" in reg._registry

    def test_discover_from_path_skip_underscore(self, tmp_path):
        plugin_file = tmp_path / "_hidden.py"
        plugin_file.write_text("x = 1")
        reg = PluginRegistry(MagicMock())
        count = reg.discover_from_path(str(tmp_path))
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════
# Lazy Loading Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLazyLoading:
    def test_load_lazy_invalid_path(self):
        reg = PluginRegistry(MagicMock())
        reg._register_lazy("not a valid path!!!")
        result = reg._load_plugin("not a valid path!!!")
        assert result is None

    def test_load_lazy_import_error(self):
        reg = PluginRegistry(MagicMock())
        reg._register_lazy("nonexistent.module.xyz:Cls")
        result = reg._load_plugin("Cls")
        assert result is None

    def test_load_plugin_not_found(self):
        reg = PluginRegistry(MagicMock())
        result = reg._load_plugin("nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# plugin_hook decorator Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPluginHookDecorator:
    def test_plugin_hook(self):
        @plugin_hook("my_hook", priority=1)
        def handler():
            pass
        assert hasattr(handler, "_plugin_hooks")
        assert handler._plugin_hooks["my_hook"] == {"priority": 1}


# ═══════════════════════════════════════════════════════════════════════
# setup_plugins Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSetupPlugins:
    def test_setup_plugins_with_config(self):
        app = MagicMock()
        app.config = {"simple": {"enabled": True, "config": {"host": "0.0.0.0"}}}
        with patch.object(PluginRegistry, "_register_class"):
            with patch.object(PluginRegistry, "discover"):
                registry = setup_plugins(app)
                assert isinstance(registry, PluginRegistry)

    def test_setup_plugins_bare_true(self):
        app = MagicMock()
        app.config = {"simple": True}
        with patch.object(PluginRegistry, "_register_class"):
            with patch.object(PluginRegistry, "discover"):
                registry = setup_plugins(app)
                assert isinstance(registry, PluginRegistry)

    def test_setup_plugins_non_dict_config(self):
        app = MagicMock()
        app.config = "not a dict"
        with patch.object(PluginRegistry, "_register_class"):
            with patch.object(PluginRegistry, "discover"):
                registry = setup_plugins(app)
                assert isinstance(registry, PluginRegistry)

    def test_setup_plugins_none_config(self):
        app = MagicMock()
        app.config = {"simple": {"enabled": True, "config": None}}
        with patch.object(PluginRegistry, "_register_class"):
            with patch.object(PluginRegistry, "discover"):
                registry = setup_plugins(app)
                assert isinstance(registry, PluginRegistry)
