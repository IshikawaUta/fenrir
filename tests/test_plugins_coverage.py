"""Targeted coverage tests for fenrir.plugins internals."""
import sys
import types

import pytest

from fenrir.plugins import (
    Plugin,
    PluginConfigError,
    PluginDependencyError,
    PluginError,
    PluginHealth,
    PluginRegistry,
    PluginVersionError,
    plugin_hook,
    setup_plugins,
)


class SamplePlugin(Plugin):
    name = "sample"
    version = "1.0.0"
    description = "desc"
    author = "me"
    requires = []
    optional = []
    conflicts = []
    config_schema = {
        "mode": {"type": "str", "required": True},
        "level": {"type": "int", "default": 5},
        "ratio": {"type": "float", "default": 1.5},
        "flag": {"type": "bool", "default": True},
    }

    def __init__(self):
        self.setup_called = 0
        self.teardown_called = 0

    def setup(self, app, **kwargs):
        self.setup_called += 1
        self._last_kwargs = kwargs

    def teardown(self, app):
        self.teardown_called += 1

    def health_check(self):
        return {"status": "healthy", "message": "ok", "version": self.version}


class TestPluginBase:
    def test_base_methods(self):
        p = Plugin()
        p.setup(object())
        p.teardown(object())
        p.on_request(object())
        p.on_response(object(), object())
        assert p.health_check()["status"] == "healthy"
        p = SamplePlugin()
        assert p.setup(object()) is None
        assert p.teardown(object()) is None
        assert p.on_request(object()) is None
        assert p.on_response(object(), object()) is None
        assert p.health_check()["status"] == "healthy"
        assert p.get_config() == {}
        assert p.is_enabled is False
        assert p.uptime is None

    def test_plugin_with_registry(self):
        app = object()
        reg = PluginRegistry(app)
        p = SamplePlugin()
        reg._register_instance(p)
        reg._configs["sample"] = {"mode": "x"}
        reg._enabled["sample"] = 0.0
        p._registry = reg
        assert p.get_config() == {"mode": "x"}
        assert p.is_enabled is True

    def test_plugin_uptime(self):
        import time

        p = SamplePlugin()
        p._enabled_at = time.time() - 10
        assert p.uptime is not None

    def test_subclass_defaults(self):
        class Custom(Plugin):
            name = "custom"

        assert Custom.requires == []
        assert Custom.config_schema == {}


class TestRegistration:
    def test_register_invalid_type(self):
        reg = PluginRegistry(object())
        with pytest.raises(TypeError):
            reg.register(12345)

    def test_register_lazy_empty_name(self):
        reg = PluginRegistry(object())
        with pytest.raises(PluginConfigError):
            reg._register_lazy("")

    def test_register_from_dict_module(self):
        reg = PluginRegistry(object())
        reg._register_from_dict({"module": "fenrir.plugins"})
        assert "plugins" in reg._registry
        with pytest.raises(PluginConfigError):
            reg._register_from_dict({})

    def test_register_from_dict_no_name(self):
        reg = PluginRegistry(object())
        with pytest.raises(PluginConfigError):
            reg._register_from_dict({"module": ""})

    def test_load_instance_via_registry(self):
        reg = PluginRegistry(object())
        reg._register_lazy("fenrir.plugins", {})
        info = reg._registry["plugins"]
        info["type"] = "instance"
        inst = SamplePlugin()
        info["instance"] = inst
        assert reg._load_plugin("plugins") is inst


class TestDiscover:
    def test_discover_entry_points(self, monkeypatch, tmp_path):
        import importlib.metadata

        class FakeEP:
            def __init__(self, name, result, error=False):
                self.name = name
                self._result = result
                self._error = error

            def load(self):
                if self._error:
                    raise RuntimeError("boom")
                return self._result

        class NonPlugin:
            pass

        eps = [
            FakeEP("sample", SamplePlugin),
            FakeEP("dup", SamplePlugin),
            FakeEP("non", NonPlugin),
            FakeEP("bad", None, error=True),
        ]
        monkeypatch.setattr(importlib.metadata, "entry_points", lambda group=None: eps)
        reg = PluginRegistry(object())
        count = reg.discover()
        assert count == 1
        assert "sample" in reg._registry

    def test_discover_entry_points_error(self, monkeypatch):
        import importlib.metadata

        def boom(group=None):
            raise RuntimeError("no entry points available")

        monkeypatch.setattr(importlib.metadata, "entry_points", boom)
        reg = PluginRegistry(object())
        assert reg.discover() == 0

    def test_discover_from_path(self, tmp_path):
        (tmp_path / "_private.py").write_text("x = 1")
        (tmp_path / "good_plugin.py").write_text(
            "from fenrir.plugins import Plugin\n"
            "class GoodPlugin(Plugin):\n"
            "    name = 'good_plugin'\n"
        )
        (tmp_path / "non_plugin.py").write_text("class NotAPlugin:\n    pass\n")
        (tmp_path / "1badname.py").write_text("x = 1")
        (tmp_path / "broken_plugin.py").write_text("raise RuntimeError('boom')\n")

        reg = PluginRegistry(object())
        count = reg.discover_from_path(str(tmp_path))
        assert count == 1
        assert "good_plugin" in reg._registry

    def test_discover_from_path_missing(self):
        reg = PluginRegistry(object())
        assert reg.discover_from_path("/nonexistent/xyz") == 0


class TestLazyLoad:
    def test_lazy_with_class(self):
        mod = types.ModuleType("fenrir._testplug")
        mod.SamplePlugin = SamplePlugin
        sys.modules["fenrir._testplug"] = mod
        try:
            reg = PluginRegistry(object())
            reg._register_lazy("fenrir._testplug:SamplePlugin")
            plugin = reg._load_plugin("SamplePlugin")
            assert plugin is not None
            assert isinstance(plugin, SamplePlugin)
        finally:
            sys.modules.pop("fenrir._testplug", None)

    def test_lazy_find_plugin_class(self):
        mod = types.ModuleType("fenrir._testplug")
        mod.D = 1
        mod.SamplePlugin = SamplePlugin
        sys.modules["fenrir._testplug"] = mod
        try:
            reg = PluginRegistry(object())
            reg._register_lazy("fenrir._testplug")
            plugin = reg._load_plugin("_testplug")
            assert plugin is not None
            assert isinstance(plugin, SamplePlugin)
        finally:
            sys.modules.pop("fenrir._testplug", None)

    def test_lazy_no_plugin_class(self):
        mod = types.ModuleType("fenrir._testplain")
        sys.modules["fenrir._testplain"] = mod
        try:
            reg = PluginRegistry(object())
            reg._register_lazy("fenrir._testplain")
            assert reg._load_plugin("_testplain") is None
        finally:
            sys.modules.pop("fenrir._testplain", None)

    def test_lazy_invalid_module_path(self):
        reg = PluginRegistry(object())
        reg._register_lazy("not valid!")
        assert reg._load_plugin("not valid!") is None

    def test_lazy_import_error(self):
        reg = PluginRegistry(object())
        reg._register_lazy("nonexistent.module.xyz")
        assert reg._load_plugin("xyz") is None

    def test_load_unknown(self):
        reg = PluginRegistry(object())
        assert reg._load_plugin("missing") is None


class TestVersion:
    def test_version_ok(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "v"
            min_fenrir_version = "0.1.0"
            max_fenrir_version = "99.0.0"

        reg._check_version(P())

    def test_version_min_fail(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "v"
            min_fenrir_version = "99.0.0"

        with pytest.raises(PluginVersionError):
            reg._check_version(P())

    def test_version_max_fail(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "v"
            max_fenrir_version = "0.0.1"

        with pytest.raises(PluginVersionError):
            reg._check_version(P())

    def test_version_max_absent(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "v"
            min_fenrir_version = "0.1.0"

        reg._check_version(P())

    def test_version_no_limits(self):
        reg = PluginRegistry(object())
        reg._check_version(Plugin())

    def test_version_packaging_missing(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "packaging" or name.startswith("packaging."):
                raise ImportError("no packaging")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "v"
            min_fenrir_version = "99.0.0"

        reg._check_version(P())  # should skip, no raise


class TestDependencies:
    def test_missing_required(self):
        app = object()
        reg = PluginRegistry(app)

        class P(Plugin):
            name = "p"
            requires = ["missing_dep"]

        with pytest.raises(PluginDependencyError):
            reg._check_dependencies("p", P())

    def test_conflict_enabled(self):
        reg = PluginRegistry(app := object())

        class P(Plugin):
            name = "p"
            conflicts = ["conf"]

        reg._enabled["conf"] = 0.0
        with pytest.raises(PluginDependencyError):
            reg._check_dependencies("p", P())

    def test_circular_dependency(self):
        reg = PluginRegistry(object())

        class A(Plugin):
            name = "a"
            requires = ["b"]

        class B(Plugin):
            name = "b"
            requires = ["a"]

        reg._register_class(A)
        reg._register_class(B)
        with pytest.raises(PluginDependencyError):
            reg._resolve_dependencies("a")

    def test_resolve_order(self):
        reg = PluginRegistry(object())

        class A(Plugin):
            name = "a"
            requires = ["b"]

        class B(Plugin):
            name = "b"

        reg._register_class(A)
        reg._register_class(B)
        order = reg._resolve_dependencies("a")
        assert order == ["b", "a"]

    def test_conflict_not_enabled(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "p"
            conflicts = ["not_enabled_conflict"]

        reg._check_dependencies("p", P())  # no raise

    def test_resolve_skip_visited(self):
        reg = PluginRegistry(object())

        class A(Plugin):
            name = "a"
            requires = ["b", "c"]

        class B(Plugin):
            name = "b"

        class C(Plugin):
            name = "c"
            requires = ["b"]

        reg._register_class(A)
        reg._register_class(B)
        reg._register_class(C)
        order = reg._resolve_dependencies("a")
        assert order == ["b", "c", "a"]

    def test_resolve_missing(self):
        reg = PluginRegistry(object())
        assert reg._resolve_dependencies("nope") == []

    def test_resolve_missing_dependency(self):
        reg = PluginRegistry(object())

        class A(Plugin):
            name = "a"
            requires = ["ghost"]

        reg._register_class(A)
        order = reg._resolve_dependencies("a")
        assert "ghost" in order


class TestConfigValidation:
    def make_plugin(self):
        class P(Plugin):
            name = "cfg"
            config_schema = {
                "s": {"type": "str"},
                "i": {"type": "int"},
                "f": {"type": "float"},
                "b": {"type": "bool"},
                "num": {"type": "int", "min": 10, "max": 100},
            }

        return P()

    def test_validation_conversions(self):
        reg = PluginRegistry(object())
        p = self.make_plugin()
        validated = reg._validate_config(p, {"s": 5, "i": "42", "f": "1.5", "b": "yes", "num": 50})
        assert validated["s"] == "5"
        assert validated["i"] == 42
        assert validated["f"] == 1.5
        assert validated["b"] is True
        assert validated["num"] == 50

    def test_validation_defaults(self):
        class P(Plugin):
            name = "cfg2"
            config_schema = {"s": {"type": "str"}, "i": {"type": "int", "default": 7}}

        reg = PluginRegistry(object())
        validated = reg._validate_config(P(), {"s": "x"})
        assert validated["s"] == "x"
        assert validated["i"] == 7

    def test_validation_str_error(self):
        class BadStr:
            def __str__(self):
                raise TypeError("cannot convert")

        reg = PluginRegistry(object())
        p = self.make_plugin()
        with pytest.raises(PluginConfigError):
            reg._validate_config(p, {"s": BadStr()})

    def test_validation_range_error(self):
        reg = PluginRegistry(object())
        p = self.make_plugin()
        with pytest.raises(PluginConfigError):
            reg._validate_config(p, {"num": 5})
        with pytest.raises(PluginConfigError):
            reg._validate_config(p, {"num": 150})

    def test_validation_type_error(self):
        reg = PluginRegistry(object())
        p = self.make_plugin()

        class BadBool:
            pass

        with pytest.raises(PluginConfigError):
            reg._validate_config(p, {"i": True})

    def test_validation_no_schema(self):
        reg = PluginRegistry(object())
        p = Plugin()
        assert reg._validate_config(p, {"x": 1}) == {"x": 1}


class TestLifecycle:
    def test_enable_flow(self):
        app = object()
        reg = PluginRegistry(app)
        reg.register(SamplePlugin)
        assert reg.enable("sample", mode="x", level="3") is True
        p = reg.get("sample")
        assert p._last_kwargs["mode"] == "x"
        assert p._last_kwargs["level"] == 3
        assert reg.is_enabled("sample")
        assert reg.enable("sample") is True  # already enabled

    def test_enable_not_found(self):
        reg = PluginRegistry(object())
        assert reg.enable("missing") is False

    def test_enable_dependency_failure(self):
        reg = PluginRegistry(object())

        class P(Plugin):
            name = "p"
            requires = ["dep"]

        class Dep(Plugin):
            name = "dep"
            config_schema = {"x": {"type": "str", "required": True}}

        reg._register_class(P)
        reg._register_class(Dep)
        assert reg.enable("p") is False

    def test_enable_setup_error(self):
        reg = PluginRegistry(object())

        class Bad(Plugin):
            name = "bad"

            def setup(self, app, **kwargs):
                raise RuntimeError("setup failed")

        reg._register_class(Bad)
        assert reg.enable("bad") is False

    def test_disable_not_enabled(self):
        reg = PluginRegistry(object())
        assert reg.disable("nothing") is True

    def test_disable_with_dependent(self):
        reg = PluginRegistry(object())

        class Dep(Plugin):
            name = "dep"

        class User(Plugin):
            name = "user"
            requires = ["dep"]

        reg._register_class(Dep)
        reg._register_class(User)
        assert reg.enable("dep") is True
        assert reg.enable("user") is True
        assert reg.disable("dep") is False  # still used

    def test_disable_independent_plugin(self):
        reg = PluginRegistry(object())

        class A(Plugin):
            name = "a"

        class B(Plugin):
            name = "b"

        reg._register_class(A)
        reg._register_class(B)
        assert reg.enable("a") is True
        assert reg.enable("b") is True
        assert reg.disable("a") is True
        assert reg.is_enabled("b")

    def test_disable_teardown_error(self):
        reg = PluginRegistry(object())

        class Bad(Plugin):
            name = "bad"

            def teardown(self, app):
                raise RuntimeError("teardown failed")

        reg._register_class(Bad)
        assert reg.enable("bad") is True
        assert reg.disable("bad") is False

    def test_disable_plugin_not_in_plugins(self):
        reg = PluginRegistry(object())
        reg._enabled["ghost"] = 0.0
        assert reg.disable("ghost") is False

    def test_reload_disabled(self):
        reg = PluginRegistry(object())
        assert reg.reload("missing") is True

    def test_reload_class_type(self):
        reg = PluginRegistry(object())
        reg.register(SamplePlugin)
        assert reg.enable("sample", mode="x") is True
        assert reg.reload("sample") is True

    def test_reload_non_plugin_class(self):
        reg = PluginRegistry(object())
        reg._registry["weird"] = {"type": "class", "class": list, "config": {}}
        reg._enabled["weird"] = 0.0
        assert reg.reload("weird") is True

    def test_reload_from_plugins_only(self):
        reg = PluginRegistry(object())
        inst = SamplePlugin()
        reg._plugins["sample"] = inst
        assert reg.reload("sample") is True

    def test_reload_from_instance(self):
        reg = PluginRegistry(object())
        inst = SamplePlugin()
        reg._register_instance(inst)
        reg._enabled["sample"] = 0.0
        assert reg.reload("sample") is True

    def test_emit_hook_error(self):
        reg = PluginRegistry(object())

        def bad_hook(**kwargs):
            raise RuntimeError("hook error")

        reg.register_hook("on_plugin_enabled", bad_hook)
        reg._emit_hook("on_plugin_enabled", x=1)


class TestHealth:
    def test_health_cached(self):
        import time

        reg = PluginRegistry(object())
        reg._health_cache["sample"] = PluginHealth(status="healthy")
        reg._last_health_check = time.time()
        reg._health_interval = 60.0

        results = reg.check_health()
        assert results == {"sample": reg._health_cache["sample"]}

    def test_health_force(self):
        reg = PluginRegistry(object())
        inst = SamplePlugin()
        reg._register_instance(inst)
        reg._enabled["sample"] = 0.0
        reg._last_health_check = 0.0
        results = reg.check_health(force=True)
        assert results["sample"].status == "healthy"

    def test_health_exception(self):
        reg = PluginRegistry(object())

        class Bad(Plugin):
            name = "bad"

            def health_check(self):
                raise RuntimeError("health failed")

        inst = Bad()
        reg._register_instance(inst)
        reg._enabled["bad"] = 0.0
        results = reg.check_health(force=True)
        assert results["bad"].status == "unhealthy"

    def test_health_plugin_missing(self):

        reg = PluginRegistry(object())
        reg._enabled["ghost"] = 0.0
        reg._last_health_check = 0.0
        results = reg.check_health(force=True)
        assert results == {}

    def test_get_plugin_health(self):
        reg = PluginRegistry(object())
        assert reg.get_plugin_health("none") is None
        h = PluginHealth(status="healthy")
        reg._health_cache["x"] = h
        assert reg.get_plugin_health("x") is h


class TestBulk:
    def test_enable_all_and_disable_all(self):
        app = object()
        reg = PluginRegistry(app)
        reg.register(SamplePlugin)
        results = reg.enable_all(mode="x")
        assert results["sample"] is True
        results2 = reg.disable_all()
        assert results2["sample"] is True
        assert reg.get_enabled() == []

    def test_cleanup(self):
        reg = PluginRegistry(object())
        inst = SamplePlugin()
        reg._register_instance(inst)
        reg._enabled["sample"] = 0.0
        reg.cleanup()
        assert reg._plugins == {}


class TestConvenience:
    def test_plugin_hook(self):
        called = []

        @plugin_hook("custom", a=1)
        def handler():
            called.append(1)

        @plugin_hook("custom", b=2)
        def handler2():
            called.append(2)

        assert handler._plugin_hooks["custom"] == {"a": 1}
        assert handler2._plugin_hooks["custom"] == {"b": 2}

        decorated_twice = plugin_hook("custom2", c=3)(handler)
        assert decorated_twice is handler
        assert handler._plugin_hooks["custom2"] == {"c": 3}

    def test_setup_plugins(self):
        from fenrir import Fenrir

        app = Fenrir()
        reg = setup_plugins(app)
        assert isinstance(reg, PluginRegistry)
        assert reg.get_enabled() == []

    def test_setup_plugins_with_config(self, tmp_path, monkeypatch):
        class FakeApp:
            pass

        calls = []
        monkeypatch.setattr(
            PluginRegistry, "enable",
            lambda self, name, **kw: calls.append((name, kw)) or True,
        )
        monkeypatch.setattr(PluginRegistry, "discover", lambda self, group=None: 0)

        app = FakeApp()
        app.config = {"sample": {"enabled": True, "config": None}}
        setup_plugins(app)
        assert ("sample", {}) in calls

        app2 = FakeApp()
        app2.config = {"sample": True}
        setup_plugins(app2)
        assert ("sample", {}) in calls

        app3 = FakeApp()
        app3.config = {"sample": {"enabled": False}}
        setup_plugins(app3)
        assert calls.count(("sample", {})) == 2

        app4 = FakeApp()
        app4.config = "not-a-dict"
        setup_plugins(app4)
        assert len(calls) == 2

        app5 = FakeApp()
        app5.config = {"sample": {"enabled": True, "config": {"mode": "x"}}}
        setup_plugins(app5)
        assert ("sample", {"mode": "x"}) in calls

    def test_exception_hierarchy(self):
        assert issubclass(PluginDependencyError, PluginError)
        assert issubclass(PluginConfigError, PluginError)
        assert issubclass(PluginVersionError, PluginError)
