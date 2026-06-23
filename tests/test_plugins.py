"""Tests for fenrir.plugins — Production-ready plugin system."""
import pytest
from fenrir import Plugin, PluginRegistry, PluginHealth
from fenrir.plugins import (
    PluginError,
    PluginDependencyError,
    PluginConfigError,
    PluginVersionError,
    setup_plugins,
)


class MockApp:
    def __init__(self):
        self.config = {}
        self._routes = []
        self._middlewares = []

    def get(self, path):
        def decorator(f):
            self._routes.append(("GET", path, f))
            return f
        return decorator

    def post(self, path):
        def decorator(f):
            self._routes.append(("POST", path, f))
            return f
        return decorator

    def add_middleware(self, mw, **kwargs):
        self._middlewares.append((mw, kwargs))


class SimplePlugin(Plugin):
    name = "simple"
    version = "1.0.0"
    description = "Simple test plugin"
    author = "Test"

    def setup(self, app, **kwargs):
        self._setup_called = True
        self._kwargs = kwargs

    def teardown(self, app):
        self._teardown_called = True

    def health_check(self):
        return {"status": "healthy", "version": self.version}


class DependentPlugin(Plugin):
    name = "dependent"
    version = "1.0.0"
    requires = ["simple"]
    optional = ["missing_optional"]
    conflicts = []

    def setup(self, app, **kwargs):
        pass


class ConflictPlugin(Plugin):
    name = "conflict"
    version = "1.0.0"
    conflicts = ["simple"]

    def setup(self, app, **kwargs):
        pass


class ConfigPlugin(Plugin):
    name = "configurable"
    version = "1.0.0"
    config_schema = {
        "api_key": {"type": "str", "required": True},
        "timeout": {"type": "int", "default": 30, "min": 1, "max": 300},
        "debug": {"type": "bool", "default": False},
    }

    def setup(self, app, **kwargs):
        self._config = kwargs


class VersionPlugin(Plugin):
    name = "versioned"
    version = "1.0.0"
    min_fenrir_version = "999.0.0"  # Will fail version check

    def setup(self, app, **kwargs):
        pass


# ═══════════════════════════════════════════════════════════════════════
# Plugin Base Class Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPluginBase:
    def test_plugin_attributes(self):
        plugin = SimplePlugin()
        assert plugin.name == "simple"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Simple test plugin"
        assert plugin.author == "Test"

    def test_plugin_setup(self):
        app = MockApp()
        plugin = SimplePlugin()
        plugin.setup(app, key="value")
        assert plugin._setup_called is True
        assert plugin._kwargs == {"key": "value"}

    def test_plugin_teardown(self):
        app = MockApp()
        plugin = SimplePlugin()
        plugin.teardown(app)
        assert plugin._teardown_called is True

    def test_plugin_health_check(self):
        plugin = SimplePlugin()
        health = plugin.health_check()
        assert health["status"] == "healthy"
        assert health["version"] == "1.0.0"

    def test_plugin_is_enabled(self):
        plugin = SimplePlugin()
        assert plugin.is_enabled is False

    def test_plugin_uptime(self):
        plugin = SimplePlugin()
        assert plugin.uptime is None


# ═══════════════════════════════════════════════════════════════════════
# PluginRegistry Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPluginRegistry:
    def test_register_class(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        assert "simple" in registry._registry

    def test_register_instance(self):
        app = MockApp()
        registry = PluginRegistry(app)
        plugin = SimplePlugin()
        registry.register(plugin)
        assert "simple" in registry._plugins

    def test_register_string(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register("fenrir.plugins:Plugin")
        assert "Plugin" in registry._registry

    def test_register_dict(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register({
            "name": "test_dict",
            "module": "fenrir.plugins",
            "class": "Plugin",
        })
        assert "test_dict" in registry._registry

    def test_enable_plugin(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        result = registry.enable("simple")
        assert result is True
        assert registry.is_enabled("simple")

    def test_disable_plugin(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        result = registry.disable("simple")
        assert result is True
        assert not registry.is_enabled("simple")

    def test_enable_nonexistent_plugin(self):
        app = MockApp()
        registry = PluginRegistry(app)
        result = registry.enable("nonexistent")
        assert result is False

    def test_list_plugins(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        # Enable to load the plugin
        registry.enable("simple")
        plugins = registry.list_plugins()
        assert "simple" in plugins
        assert plugins["simple"]["version"] == "1.0.0"

    def test_get_plugin_after_enable(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        plugin = registry.get("simple")
        assert plugin is not None
        assert plugin.name == "simple"

    def test_cleanup(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        registry.cleanup()
        assert len(registry._plugins) == 0
        assert len(registry._enabled) == 0

    def test_list_plugins_after_enable(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        plugins = registry.list_plugins()
        assert "simple" in plugins
        assert plugins["simple"]["enabled"] is True
        assert plugins["simple"]["version"] == "1.0.0"


# ═══════════════════════════════════════════════════════════════════════
# Dependency Resolution Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDependencies:
    def test_enable_with_dependency(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.register(DependentPlugin)
        
        # Enable dependent (should auto-enable simple)
        result = registry.enable("dependent")
        assert result is True
        assert registry.is_enabled("simple")
        assert registry.is_enabled("dependent")

    def test_conflict_detection(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.register(ConflictPlugin)
        
        registry.enable("simple")
        result = registry.enable("conflict")
        assert result is False

    def test_get_dependencies(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(DependentPlugin)
        deps = registry.get_dependencies("dependent")
        assert "simple" in deps

    def test_get_dependents(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.register(DependentPlugin)
        # Need to load the dependent plugin first
        registry.enable("dependent")
        dependents = registry.get_dependents("simple")
        assert "dependent" in dependents


# ═══════════════════════════════════════════════════════════════════════
# Config Validation Tests
# ═══════════════════════════════════════════════════════════════════════

class TestConfigValidation:
    def test_enable_with_valid_config(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(ConfigPlugin)
        result = registry.enable("configurable", api_key="test-key", timeout=60)
        assert result is True

    def test_enable_without_required_config(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(ConfigPlugin)
        result = registry.enable("configurable")
        assert result is False

    def test_config_with_defaults(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(ConfigPlugin)
        registry.enable("configurable", api_key="test-key")
        config = registry.get_plugin_config("configurable")
        assert config["api_key"] == "test-key"
        assert config["timeout"] == 30
        assert config["debug"] is False


# ═══════════════════════════════════════════════════════════════════════
# Health Monitoring Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHealthMonitoring:
    def test_health_check(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        
        health = registry.check_health(force=True)
        assert "simple" in health
        assert health["simple"].status == "healthy"

    def test_plugin_uptime(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        
        plugin = registry.get("simple")
        assert plugin.uptime is not None
        assert plugin.uptime >= 0


# ═══════════════════════════════════════════════════════════════════════
# Hot-Reload Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHotReload:
    def test_reload_plugin(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        
        # Get the plugin before reload
        plugin_before = registry.get("simple")
        assert plugin_before is not None
        
        # Reload
        result = registry.reload("simple")
        assert result is True
        
        # Check that plugin is still available
        plugin_after = registry.get("simple")
        assert plugin_after is not None
        assert plugin_after.name == "simple"


# ═══════════════════════════════════════════════════════════════════════
# Exception Tests
# ═══════════════════════════════════════════════════════════════════════

class TestExceptions:
    def test_plugin_error(self):
        with pytest.raises(PluginError):
            raise PluginError("test")

    def test_dependency_error(self):
        with pytest.raises(PluginDependencyError):
            raise PluginDependencyError("test")

    def test_config_error(self):
        with pytest.raises(PluginConfigError):
            raise PluginConfigError("test")

    def test_version_error(self):
        with pytest.raises(PluginVersionError):
            raise PluginVersionError("test")


# ═══════════════════════════════════════════════════════════════════════
# Extended PluginRegistry Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPluginRegistryExtended:
    def test_disable_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        result = registry.disable("nonexistent")
        assert result is True  # disable returns True for nonexistent (idempotent)

    def test_get_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        plugin = registry.get("nonexistent")
        assert plugin is None

    def test_is_enabled_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        assert registry.is_enabled("nonexistent") is False

    def test_reload_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        result = registry.reload("nonexistent")
        assert result is True  # reload returns True for nonexistent (no-op)

    def test_get_plugin_config_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        config = registry.get_plugin_config("nonexistent")
        assert config == {}

    def test_enable_disable_enable(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.enable("simple")
        registry.disable("simple")
        registry.enable("simple")
        assert registry.is_enabled("simple")

    def test_register_duplicate(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        registry.register(SimplePlugin)  # Should not raise
        assert "simple" in registry._registry

    def test_cleanup_empty(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.cleanup()  # Should not raise

    def test_health_check_disabled(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(SimplePlugin)
        # Don't enable - health check should handle gracefully
        health = registry.check_health(force=True)
        assert "simple" not in health or health.get("simple") is None

    def test_get_dependencies_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        deps = registry.get_dependencies("nonexistent")
        assert deps == []

    def test_get_dependents_nonexistent(self):
        app = MockApp()
        registry = PluginRegistry(app)
        dependents = registry.get_dependents("nonexistent")
        assert dependents == []

    def test_list_plugins_empty(self):
        app = MockApp()
        registry = PluginRegistry(app)
        plugins = registry.list_plugins()
        assert plugins == {}


# ═══════════════════════════════════════════════════════════════════════
# Plugin with version check
# ═══════════════════════════════════════════════════════════════════════

class TestVersionCheck:
    def test_version_check_fails(self):
        app = MockApp()
        registry = PluginRegistry(app)
        registry.register(VersionPlugin)
        result = registry.enable("versioned")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# setup_plugins function
# ═══════════════════════════════════════════════════════════════════════

class TestSetupPlugins:
    def test_setup_plugins(self):
        app = MockApp()
        app.config["PLUGINS"] = []
        setup_plugins(app)
        # Should not raise even with no plugins configured
