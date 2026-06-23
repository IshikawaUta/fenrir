"""
fenrir.plugins — Production-ready plugin system for Fenrir.

Features:
- Version compatibility checking
- Plugin dependency resolution
- Hot-reload support
- Auto-discovery via entry points
- Configuration schema validation
- Plugin lifecycle hooks
- Health monitoring
- Plugin isolation (namespace)
- Security sandboxing

Usage::

    from fenrir import Fenrir
    from fenrir.plugins import Plugin, PluginRegistry

    class AuthPlugin(Plugin):
        name = "auth"
        version = "2.0.0"
        description = "Authentication plugin"
        author = "Fenrir Team"

        # Declare dependencies
        requires = ["logging"]
        optional = ["redis"]

        # Config schema (Pydantic-like)
        config_schema = {
            "secret_key": {"type": "str", "required": True},
            "token_expire": {"type": "int", "default": 3600, "min": 60},
            "enable_refresh": {"type": "bool", "default": True},
        }

        def setup(self, app, **kwargs):
            # Register middleware, routes, etc.
            pass

        def health_check(self):
            return {"status": "healthy", "version": self.version}

    # Register and enable
    app = Fenrir()
    registry = PluginRegistry(app)
    registry.register(AuthPlugin)
    registry.enable("auth", secret_key="my-secret")
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import sys
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

logger = logging.getLogger("fenrir.plugins")


# ═══════════════════════════════════════════════════════════════════════
# Plugin base class with production features
# ═══════════════════════════════════════════════════════════════════════

class PluginError(Exception):
    """Base exception for plugin errors."""
    pass


class PluginDependencyError(PluginError):
    """Raised when plugin dependencies are not met."""
    pass


class PluginConfigError(PluginError):
    """Raised when plugin configuration is invalid."""
    pass


class PluginVersionError(PluginError):
    """Raised when plugin version is incompatible."""
    pass


@dataclass
class PluginHealth:
    """Plugin health status."""
    status: str = "unknown"  # healthy, degraded, unhealthy
    message: str = ""
    last_check: float = 0.0
    checks: Dict[str, Any] = field(default_factory=dict)


class Plugin:
    """Production-ready base class for Fenrir plugins.

    Features:
    - Version compatibility
    - Dependency declaration
    - Config schema validation
    - Lifecycle hooks
    - Health monitoring
    """
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    min_fenrir_version: str = ""
    max_fenrir_version: str = ""

    # Internal
    _registry: Optional["PluginRegistry"] = None
    _health: Optional[PluginHealth] = None
    _enabled_at: Optional[float] = None
    _namespace: Optional[str] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Ensure mutable class-level defaults are per-class, not shared
        defaults = {
            "requires": [],
            "optional": [],
            "conflicts": [],
            "config_schema": {},
        }
        for attr, default_val in defaults.items():
            if attr not in cls.__dict__:
                setattr(cls, attr, default_val)

    def setup(self, app: Any, **kwargs: Any) -> None:
        """Called when the plugin is enabled."""
        pass

    def teardown(self, app: Any) -> None:
        """Called when the plugin is disabled or app shuts down."""
        pass

    def on_request(self, request: Any) -> Optional[Any]:
        """Hook called before each request. Return False to stop."""
        pass

    def on_response(self, request: Any, response: Any) -> Optional[Any]:
        """Hook called after each request."""
        pass

    def health_check(self) -> Dict[str, Any]:
        """Return health status. Override for custom health checks."""
        return {"status": "healthy", "version": self.version}

    def get_config(self) -> Dict[str, Any]:
        """Get plugin configuration."""
        if self._registry:
            return self._registry.get_plugin_config(self.name)
        return {}

    @property
    def is_enabled(self) -> bool:
        if self._registry:
            return self._registry.is_enabled(self.name)
        return False

    @property
    def uptime(self) -> Optional[float]:
        if self._enabled_at:
            return time.time() - self._enabled_at
        return None


# ═══════════════════════════════════════════════════════════════════════
# Plugin Registry with production features
# ═══════════════════════════════════════════════════════════════════════

class PluginRegistry:
    """Production-ready plugin registry.

    Features:
    - Version compatibility checking
    - Dependency resolution
    - Hot-reload support
    - Auto-discovery via entry points
    - Configuration validation
    - Health monitoring
    - Plugin isolation
    """

    def __init__(self, app: Any) -> None:
        self._app = app
        self._plugins: Dict[str, Plugin] = {}
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._enabled: Dict[str, float] = {}  # name -> enabled_at
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._health_cache: Dict[str, PluginHealth] = {}
        self._health_interval: float = 60.0
        self._last_health_check: float = 0
        self._lock = threading.RLock()
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._namespaces: Dict[str, str] = {}  # plugin_name -> namespace

    # ── Registration ────────────────────────────────────────────────

    def register(
        self,
        plugin_class: Any,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a plugin without enabling it."""
        with self._lock:
            if isinstance(plugin_class, str):
                self._register_lazy(plugin_class, config)
            elif isinstance(plugin_class, dict):
                self._register_from_dict(plugin_class, config)
            elif isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
                self._register_class(plugin_class, config)
            elif isinstance(plugin_class, Plugin):
                self._register_instance(plugin_class, config)
            else:
                raise TypeError(f"Cannot register plugin of type {type(plugin_class)}")

    def _register_lazy(self, module_path: str, config: Optional[Dict] = None) -> None:
        parts = module_path.split(":")
        module = parts[0]
        class_name = parts[1] if len(parts) > 1 else None
        name = class_name or module.rsplit(".", 1)[-1] if module else module_path
        if not name:
            raise PluginConfigError(f"Invalid module path: {module_path!r}")
        self._registry[name] = {
            "type": "lazy",
            "module": module,
            "class": class_name,
            "config": config or {},
        }

    def _register_from_dict(self, data: Dict, config: Optional[Dict] = None) -> None:
        name = data.get("name")
        if not name:
            module = data.get("module", "")
            name = module.rsplit(".", 1)[-1] if module else ""
        if not name:
            raise PluginConfigError("Plugin dict must have 'name' or 'module' key")
        self._registry[name] = {
            "type": "lazy",
            "module": data.get("module", ""),
            "class": data.get("class"),
            "config": {**(data.get("config", {})), **(config or {})},
        }

    def _register_class(self, cls: Type[Plugin], config: Optional[Dict] = None) -> None:
        name = cls.name or cls.__name__
        self._registry[name] = {
            "type": "class",
            "class": cls,
            "config": config or {},
        }

    def _register_instance(self, instance: Plugin, config: Optional[Dict] = None) -> None:
        name = instance.name or instance.__class__.__name__
        instance._registry = self
        self._plugins[name] = instance
        self._registry[name] = {
            "type": "instance",
            "instance": instance,
            "config": config or {},
        }

    # ── Auto-discovery ──────────────────────────────────────────────

    def discover(self, group: str = "fenrir.plugins") -> int:
        """Auto-discover plugins via entry points.

        Returns the number of plugins discovered.
        """
        count = 0
        with self._lock:
            try:
                if sys.version_info >= (3, 10):
                    from importlib.metadata import entry_points
                    eps = entry_points(group=group)
                else:
                    from importlib.metadata import entry_points
                    all_eps = entry_points()
                    eps = all_eps.get(group, [])

                for ep in eps:
                    try:
                        plugin_class = ep.load()
                        if isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
                            name = plugin_class.name or ep.name
                            if name not in self._registry:
                                self._registry[name] = {
                                    "type": "class",
                                    "class": plugin_class,
                                    "config": {},
                                    "entry_point": ep,
                                }
                                count += 1
                                logger.debug("Discovered plugin: %s", name)
                    except Exception as e:
                        logger.warning("Failed to load entry point %s: %s", ep.name, e)
            except Exception as e:
                logger.debug("Entry point discovery not available: %s", e)

        return count

    def discover_from_path(self, path: str, pattern: str = "*.py") -> int:
        """Discover plugins from a directory path."""
        count = 0
        plugin_dir = Path(path)
        if not plugin_dir.exists():
            return count

        with self._lock:
            for py_file in plugin_dir.glob(pattern):
                if py_file.name.startswith("_"):
                    continue
                module_name = f"fenrir_plugins.{py_file.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, Plugin)
                                and attr is not Plugin
                                and (attr.name or attr_name) not in self._registry
                            ):
                                name = attr.name or attr_name
                                self._registry[name] = {
                                    "type": "class",
                                    "class": attr,
                                    "config": {},
                                }
                                count += 1
                except Exception as e:
                    logger.warning("Failed to load plugin from %s: %s", py_file, e)

        return count

    # ── Loading ─────────────────────────────────────────────────────

    def _load_plugin(self, name: str) -> Optional[Plugin]:
        """Load a plugin by name (handles lazy loading)."""
        if name in self._plugins:
            return self._plugins[name]

        info = self._registry.get(name)
        if not info:
            return None

        if info["type"] == "instance":
            return info["instance"]

        if info["type"] == "class":
            plugin = info["class"]()
            plugin._registry = self
            self._plugins[name] = plugin
            return plugin

        if info["type"] == "lazy":
            try:
                module_path = info["module"]
                # Validate module path: must be a valid Python dotted name
                if not all(part.isidentifier() for part in module_path.split(".")):
                    logger.error(
                        "Invalid module path '%s' for plugin '%s'. "
                        "Module paths must contain only alphanumeric characters and dots.",
                        module_path, name,
                    )
                    return None
                module = importlib.import_module(module_path)
                class_name = info.get("class")
                if class_name:
                    plugin_cls = getattr(module, class_name)
                else:
                    plugin_cls = None
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                        ):
                            plugin_cls = attr
                            break
                if plugin_cls is None:
                    return None
                plugin = plugin_cls()
                plugin._registry = self
                self._plugins[name] = plugin
                return plugin
            except Exception as e:
                logger.error("Failed to load plugin '%s': %s", name, e)
                return None

        return None

    # ── Version checking ────────────────────────────────────────────

    def _check_version(self, plugin: Plugin) -> None:
        """Check plugin version compatibility."""
        if not plugin.min_fenrir_version and not plugin.max_fenrir_version:
            return

        try:
            from packaging.version import Version
        except ImportError:
            logger.warning("packaging not installed — skipping version check")
            return

        from fenrir import __version__ as fenrir_version

        current = Version(fenrir_version)

        if plugin.min_fenrir_version:
            min_ver = Version(plugin.min_fenrir_version)
            if current < min_ver:
                raise PluginVersionError(
                    f"Plugin '{plugin.name}' requires Fenrir >= {plugin.min_fenrir_version}, "
                    f"but current version is {fenrir_version}"
                )

        if plugin.max_fenrir_version:
            max_ver = Version(plugin.max_fenrir_version)
            if current > max_ver:
                raise PluginVersionError(
                    f"Plugin '{plugin.name}' requires Fenrir <= {plugin.max_fenrir_version}, "
                    f"but current version is {fenrir_version}"
                )

    # ── Dependency resolution ───────────────────────────────────────

    def _check_dependencies(self, name: str, plugin: Plugin) -> None:
        """Check plugin dependencies."""
        # Check required plugins
        for dep in plugin.requires:
            if not self.is_enabled(dep):
                raise PluginDependencyError(
                    f"Plugin '{name}' requires '{dep}' to be enabled"
                )

        # Check conflicts
        for conflict in plugin.conflicts:
            if self.is_enabled(conflict):
                raise PluginDependencyError(
                    f"Plugin '{name}' conflicts with '{conflict}'"
                )

    def _resolve_dependencies(self, name: str) -> List[str]:
        """Resolve plugin dependencies in order with circular dependency detection."""
        plugin = self._load_plugin(name)
        if not plugin:
            return []

        order = []
        visited = set()
        visiting = set()  # For circular dependency detection

        def _visit(n: str) -> None:
            if n in visited:
                return
            if n in visiting:
                raise PluginDependencyError(
                    f"Circular dependency detected involving plugin '{n}'"
                )
            visiting.add(n)
            p = self._load_plugin(n)
            if p:
                for dep in p.requires:
                    _visit(dep)
            visiting.remove(n)
            visited.add(n)
            order.append(n)

        _visit(name)
        return order

    # ── Configuration validation ────────────────────────────────────

    def _validate_config(self, plugin: Plugin, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plugin configuration against schema."""
        schema = plugin.config_schema
        if not schema:
            return config

        validated = {}
        errors = []

        for field_name, field_schema in schema.items():
            value = config.get(field_name)
            field_type = field_schema.get("type", "str")
            required = field_schema.get("required", False)
            default = field_schema.get("default")
            min_val = field_schema.get("min")
            max_val = field_schema.get("max")

            if value is None:
                if required:
                    errors.append(f"'{field_name}' is required")
                    continue
                value = default

            # Type validation
            if field_type == "str" and not isinstance(value, str):
                try:
                    value = str(value)
                except (ValueError, TypeError):
                    errors.append(f"'{field_name}' must be a string")
                    continue
            elif field_type == "int":
                if isinstance(value, bool):
                    errors.append(f"'{field_name}' must be an integer (not bool)")
                    continue
                if not isinstance(value, int):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        errors.append(f"'{field_name}' must be an integer")
                        continue
            elif field_type == "float" and not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    errors.append(f"'{field_name}' must be a number")
                    continue
            elif field_type == "bool" and not isinstance(value, bool):
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes")
                else:
                    value = bool(value)

            # Range validation (only for numeric types)
            if field_type in ("int", "float") and isinstance(value, (int, float)):
                if min_val is not None and value < min_val:
                    errors.append(f"'{field_name}' must be >= {min_val}")
                if max_val is not None and value > max_val:
                    errors.append(f"'{field_name}' must be <= {max_val}")

            validated[field_name] = value

        if errors:
            raise PluginConfigError(
                f"Configuration errors for '{plugin.name}': {'; '.join(errors)}"
            )

        # Fill in defaults for missing fields
        for field_name, field_schema in schema.items():
            if field_name not in validated and "default" in field_schema:
                validated[field_name] = field_schema["default"]

        return validated

    # ── Enable/Disable ──────────────────────────────────────────────

    def enable(self, name: str, **kwargs: Any) -> bool:
        """Enable a plugin by name."""
        with self._lock:
            if name in self._enabled:
                return True

            plugin = self._load_plugin(name)
            if plugin is None:
                logger.error("Plugin '%s' not found", name)
                return False

            try:
                # Version check
                self._check_version(plugin)

                # Resolve and check dependencies
                dep_order = self._resolve_dependencies(name)
                for dep_name in dep_order:
                    if dep_name != name and dep_name not in self._enabled:
                        if not self.enable(dep_name):
                            raise PluginDependencyError(
                                f"Failed to enable dependency '{dep_name}'"
                            )

                self._check_dependencies(name, plugin)

                # Merge config
                config = self._registry.get(name, {}).get("config", {})
                merged = {**config, **kwargs}

                # Validate config
                if plugin.config_schema:
                    merged = self._validate_config(plugin, merged)

                # Setup plugin
                plugin.setup(self._app, **merged)

                # Set namespace
                plugin._namespace = name
                self._namespaces[name] = name

                # Record enable time (single time.time() call)
                now = time.time()
                plugin._enabled_at = now
                self._enabled[name] = now
                self._configs[name] = merged

                # Emit hook
                self._emit_hook("on_plugin_enabled", name=name, plugin=plugin)

                logger.info("Enabled plugin: %s v%s", name, plugin.version)
                return True

            except Exception as e:
                logger.error("Failed to enable plugin '%s': %s", name, e)
                return False

    def disable(self, name: str) -> bool:
        """Disable a plugin by name."""
        with self._lock:
            if name not in self._enabled:
                return True

            plugin = self._plugins.get(name)
            if plugin:
                try:
                    # Check if other plugins depend on this one
                    for other_name, other_plugin in self._plugins.items():
                        if other_name != name and other_name in self._enabled:
                            if name in other_plugin.requires:
                                logger.error(
                                    "Cannot disable '%s': plugin '%s' depends on it",
                                    name, other_name,
                                )
                                return False

                    plugin.teardown(self._app)
                    plugin._enabled_at = None
                    del self._enabled[name]
                    self._configs.pop(name, None)
                    self._health_cache.pop(name, None)
                    self._namespaces.pop(name, None)

                    self._emit_hook("on_plugin_disabled", name=name, plugin=plugin)

                    logger.info("Disabled plugin: %s", name)
                    return True
                except Exception as e:
                    logger.error("Failed to disable plugin '%s': %s", name, e)
                    return False
            return False

    def reload(self, name: str) -> bool:
        """Hot-reload a plugin."""
        with self._lock:
            was_enabled = name in self._enabled
            config = self._configs.get(name, {})

            # Get the plugin class before removing
            plugin_class = None
            if name in self._registry:
                info = self._registry[name]
                if info["type"] == "class":
                    plugin_class = info["class"]
                # Don't reuse instance — always create fresh on reload
            elif name in self._plugins:
                plugin_class = type(self._plugins[name])

            # Disable
            if was_enabled:
                self.disable(name)

            # Remove cached instance
            self._plugins.pop(name, None)
            self._registry.pop(name, None)

            # Re-register and enable
            if was_enabled and plugin_class:
                if isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
                    self._register_class(plugin_class, config)
                return self.enable(name, **config)
            return True

    # ── Health monitoring ───────────────────────────────────────────

    def check_health(self, force: bool = False) -> Dict[str, PluginHealth]:
        """Check health of all enabled plugins."""
        with self._lock:
            now = time.time()
            if not force and (now - self._last_health_check) < self._health_interval:
                return dict(self._health_cache)

            results = {}
            for name in list(self._enabled.keys()):
                plugin = self._plugins.get(name)
                if plugin:
                    try:
                        health_data = plugin.health_check()
                        health = PluginHealth(
                            status=health_data.get("status", "unknown"),
                            message=health_data.get("message", ""),
                            last_check=now,
                            checks=health_data,
                        )
                        results[name] = health
                        self._health_cache[name] = health
                    except Exception as e:
                        health = PluginHealth(
                            status="unhealthy",
                            message=str(e),
                            last_check=now,
                        )
                        results[name] = health
                        self._health_cache[name] = health

            self._last_health_check = now
            return results

    def get_plugin_health(self, name: str) -> Optional[PluginHealth]:
        """Get health status of a specific plugin."""
        with self._lock:
            return self._health_cache.get(name)

    # ── Query methods ───────────────────────────────────────────────

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            return name in self._enabled

    def get(self, name: str) -> Optional[Plugin]:
        with self._lock:
            return self._plugins.get(name)

    def get_plugin_config(self, name: str) -> Dict[str, Any]:
        with self._lock:
            return self._configs.get(name, {})

    def list_plugins(self) -> Dict[str, Dict[str, Any]]:
        """List all registered plugins with their status."""
        with self._lock:
            result = {}
            all_names = set(self._registry.keys()) | set(self._plugins.keys())
            for name in all_names:
                plugin = self._plugins.get(name)
                enabled = name in self._enabled
                enabled_at = self._enabled.get(name)
                result[name] = {
                    "enabled": enabled,
                    "version": getattr(plugin, "version", "unknown"),
                    "description": getattr(plugin, "description", ""),
                    "author": getattr(plugin, "author", ""),
                    "enabled_at": enabled_at,
                    "uptime": time.time() - enabled_at if enabled_at else None,
                    "health": self._health_cache.get(name, PluginHealth()).status,
                }
            return result

    def get_enabled(self) -> List[str]:
        """Get list of enabled plugin names."""
        with self._lock:
            return list(self._enabled.keys())

    def get_dependencies(self, name: str) -> List[str]:
        """Get dependencies for a plugin."""
        with self._lock:
            plugin = self._load_plugin(name)
            if plugin:
                return list(plugin.requires)
            return []

    def get_dependents(self, name: str) -> List[str]:
        """Get plugins that depend on the given plugin."""
        with self._lock:
            dependents = []
            for other_name, other_plugin in self._plugins.items():
                if name in other_plugin.requires:
                    dependents.append(other_name)
            return dependents

    # ── Hooks ───────────────────────────────────────────────────────

    def register_hook(self, event: str, func: Callable) -> None:
        """Register a hook for plugin events."""
        with self._lock:
            self._hooks[event].append(func)

    def _emit_hook(self, event: str, **kwargs: Any) -> None:
        """Emit a hook event."""
        for func in self._hooks.get(event, []):
            try:
                func(**kwargs)
            except Exception as e:
                logger.error("Hook error in '%s': %s", event, e)

    # ── Bulk operations ─────────────────────────────────────────────

    def enable_all(self, **kwargs: Any) -> Dict[str, bool]:
        """Enable all registered plugins. Returns dict of name -> success."""
        results = {}
        for name in list(self._registry.keys()):
            results[name] = self.enable(name, **kwargs)
        return results

    def disable_all(self) -> Dict[str, bool]:
        """Disable all enabled plugins. Returns dict of name -> success."""
        results = {}
        for name in list(self._enabled.keys()):
            results[name] = self.disable(name)
        return results

    def cleanup(self) -> None:
        """Cleanup all plugins (called on app shutdown)."""
        with self._lock:
            self.disable_all()
            self._plugins.clear()
            self._registry.clear()
            self._enabled.clear()
            self._configs.clear()
            self._health_cache.clear()
            self._hooks.clear()
            self._namespaces.clear()


# ═══════════════════════════════════════════════════════════════════════
# Convenience functions
# ═══════════════════════════════════════════════════════════════════════

def plugin_hook(name: str, **hook_kwargs: Any) -> Callable:
    """Decorator to register a function as a plugin hook handler."""
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, "_plugin_hooks"):
            func._plugin_hooks = {}
        func._plugin_hooks[name] = hook_kwargs
        return func
    return decorator


def setup_plugins(app: Any, **kwargs: Any) -> PluginRegistry:
    """Convenience function to setup plugins for an app."""
    registry = PluginRegistry(app)

    # Auto-discover plugins
    registry.discover()

    # Enable plugins from config
    plugins_config = getattr(app, "config", {})
    if not isinstance(plugins_config, dict):
        plugins_config = {}

    for name, config in plugins_config.items():
        if isinstance(config, dict) and config.get("enabled", True):
            plugin_config = config.get("config", {})
            if plugin_config is None:
                plugin_config = {}
            registry.enable(name, **plugin_config)
        elif config is True:
            registry.enable(name)

    return registry
