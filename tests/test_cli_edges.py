"""Edge-case coverage tests for fenrir.cli."""
import os
import re
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import fenrir.cli as _cli
from fenrir.cli import (
    cmd_info,
    cmd_monitoring,
    cmd_new,
    cmd_routes,
    cmd_run,
    load_app,
    run_benchmark,
    run_with_reloader,
)


def _os_proxy():
    import os as _real_os

    proxy = type(sys)("fenrir_test_os")
    for _name in dir(_real_os):
        setattr(proxy, _name, getattr(_real_os, _name))
    return proxy


class TestLoadAppEdges:
    def test_file_spec_none(self, tmp_path):
        app_file = tmp_path / "bad.py"
        app_file.write_text("app = 1\n")
        with patch("importlib.util.spec_from_file_location", return_value=None):
            with pytest.raises(ImportError, match="Could not load spec"):
                load_app(str(app_file))

    def test_module_import_fails_py_file_fallback(self, tmp_path):
        app_file = tmp_path / "fallbackmod.py"
        app_file.write_text("app = {'title': 'fb'}\n")
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("importlib.import_module", side_effect=ImportError("boom")):
                result = load_app("fallbackmod")
            assert result == {"title": "fb"}
        finally:
            os.chdir(old_cwd)

    def test_fallback_spec_none(self, tmp_path):
        app_file = tmp_path / "fallbackmod2.py"
        app_file.write_text("app = 1\n")
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("importlib.util.spec_from_file_location", return_value=None), \
                 patch("importlib.import_module", side_effect=ImportError("boom")):
                with pytest.raises(ImportError, match="Could not load spec"):
                    load_app("fallbackmod2")
        finally:
            os.chdir(old_cwd)


class TestRunWithReloader:
    def test_reloads_on_change_then_keyboard_interrupt(self):
        processes = []

        def fake_process(*a, **k):
            pm = MagicMock()
            processes.append(pm)
            return pm

        proxy = _os_proxy()
        proxy.walk = MagicMock(side_effect=[
            [(".", ["s"], ["a.py", "b.py"])],
            [(".", ["s"], ["a.py", "b.py"])],
            [(".", ["s"], ["a.py", "b.py"])],
            [(".", ["s"], ["a.py", "b.py"])],
        ])
        proxy.stat = MagicMock(side_effect=[
            SimpleNamespace(st_mtime=1.0), SimpleNamespace(st_mtime=2.0),
            SimpleNamespace(st_mtime=1.0), SimpleNamespace(st_mtime=2.0),
            SimpleNamespace(st_mtime=9.0), SimpleNamespace(st_mtime=2.0),
        ])
        with patch("multiprocessing.Process", side_effect=fake_process), \
             patch("fenrir.cli.time.sleep",
                   side_effect=[None, None, KeyboardInterrupt()]), \
             patch.object(_cli, "os", proxy):
            run_with_reloader(lambda: None)

        assert len(processes) == 2
        processes[0].terminate.assert_called_once()
        processes[1].start.assert_called_once()
        processes[1].terminate.assert_called_once()

    def test_file_set_change_detected(self):
        processes = []

        def fake_process(*a, **k):
            pm = MagicMock()
            processes.append(pm)
            return pm

        proxy = _os_proxy()
        proxy.walk = MagicMock(side_effect=[
            [(".", ["s"], ["a.py"])],
            [(".", ["s"], ["a.py", "c.py"])],
            [(".", ["s"], ["a.py", "c.py"])],
        ])
        proxy.stat = MagicMock(side_effect=[
            SimpleNamespace(st_mtime=1.0),
            SimpleNamespace(st_mtime=1.0), SimpleNamespace(st_mtime=1.0),
            SimpleNamespace(st_mtime=1.0), SimpleNamespace(st_mtime=1.0),
        ])
        with patch("multiprocessing.Process", side_effect=fake_process), \
             patch("fenrir.cli.time.sleep",
                   side_effect=[None, None, KeyboardInterrupt()]), \
             patch.object(_cli, "os", proxy):
            run_with_reloader(lambda: None)

        assert len(processes) == 2
        processes[0].terminate.assert_called_once()
        processes[1].start.assert_called_once()

    def test_no_py_files_found(self):
        processes = []

        def fake_process(*a, **k):
            pm = MagicMock()
            processes.append(pm)
            return pm

        proxy = _os_proxy()
        proxy.walk = MagicMock(side_effect=[
            [(".", ["s"], ["readme.txt"])],
            [(".", ["s"], ["readme.txt"])],
        ])
        proxy.stat = MagicMock(return_value=SimpleNamespace(st_mtime=1.0))
        with patch("multiprocessing.Process", side_effect=fake_process), \
             patch("fenrir.cli.time.sleep",
                   side_effect=[None, KeyboardInterrupt()]), \
             patch.object(_cli, "os", proxy):
            run_with_reloader(lambda: None)

        processes[0].terminate.assert_called_once()

    def test_stat_oserror_skipped(self):
        processes = []

        def fake_process(*a, **k):
            pm = MagicMock()
            processes.append(pm)
            return pm

        def fake_stat(path):
            if path.endswith("b.py"):
                raise OSError("gone")
            return SimpleNamespace(st_mtime=1.0)

        proxy = _os_proxy()
        proxy.walk = MagicMock(side_effect=[
            [(".", ["s"], ["a.py", "b.py"])],
            [(".", ["s"], ["a.py", "b.py"])],
        ])
        proxy.stat = MagicMock(side_effect=fake_stat)
        with patch("multiprocessing.Process", side_effect=fake_process), \
             patch("fenrir.cli.time.sleep",
                   side_effect=[None, KeyboardInterrupt()]), \
             patch.object(_cli, "os", proxy):
            run_with_reloader(lambda: None)

        processes[0].terminate.assert_called_once()


class TestCmdRun:
    def _args(self, dev=False, reload=False):
        return SimpleNamespace(
            dev=dev, reload=reload, target="x:app", workers=1,
            host="127.0.0.1", port=8000, disable_dashboard=False,
        )

    def test_dev_sets_debug_config(self):
        app = SimpleNamespace(title="t", version="1", dev_mode=False)
        app.config = {"DEBUG": False}
        with patch("fenrir.cli.load_app", return_value=app), \
             patch("asteri.arbiter.Arbiter", return_value=MagicMock()):
            cmd_run(self._args(dev=True))
        assert app.config["DEBUG"] is True
        assert os.environ.get("FENRIR_DEV_MODE") == "1"
        os.environ.pop("FENRIR_DEV_MODE", None)

    def test_asteri_missing_exits(self):
        app = SimpleNamespace(title="t", version="1", config=None, dev_mode=False)
        with patch("fenrir.cli.load_app", return_value=app), \
             patch.dict(sys.modules, {"asteri": None, "asteri.arbiter": None,
                                      "asteri.workers.asgi": None}), \
             pytest.raises(SystemExit) as e:
            cmd_run(self._args())
        assert e.value.code == 1

    def test_asteri_keyboard_interrupt(self):
        arbiter = MagicMock()
        arbiter.start.side_effect = KeyboardInterrupt
        app = SimpleNamespace(title="t", version="1", config=None, dev_mode=False)
        with patch("fenrir.cli.load_app", return_value=app), \
             patch("asteri.arbiter.Arbiter", return_value=arbiter):
            cmd_run(self._args())


@pytest.mark.anyio
class TestRunBenchmark:
    async def test_missing_httpx(self):
        with patch("importlib.util.find_spec", return_value=None), \
             pytest.raises(SystemExit) as e:
            await run_benchmark(SimpleNamespace(), "/", "GET", 1, 1)
        assert e.value.code == 1


class TestCmdNew:
    def test_dir_exists_exits(self, tmp_path):
        target = tmp_path / "exists"
        target.mkdir()
        with pytest.raises(SystemExit) as e:
            cmd_new(SimpleNamespace(name=str(target)))
        assert e.value.code == 1

    def test_logo_fallbacks(self, tmp_path):
        target = tmp_path / "proj"
        real_exists = os.path.exists

        def exists_no_logo(path):
            if str(path).endswith(("logo.png", "logo.jpg")):
                return False
            return real_exists(path)

        with patch("fenrir.cli.os.path.exists", side_effect=exists_no_logo):
            cmd_new(SimpleNamespace(name=str(target)))
        assert (target / "app.py").exists()

    def test_scaffold_error_exits(self, tmp_path):
        target = tmp_path / "errproj"
        with patch("fenrir.cli.os.makedirs", side_effect=OSError("boom")), \
             pytest.raises(SystemExit) as e:
            cmd_new(SimpleNamespace(name=str(target)))
        assert e.value.code == 1

    def test_favicon_from_logo_when_jpg_missing(self, tmp_path):
        target = tmp_path / "proj2"
        real_exists = os.path.exists

        def exists_no_jpg(path):
            if str(path).endswith("logo.jpg"):
                return False
            return real_exists(path)

        with patch("fenrir.cli.os.path.exists", side_effect=exists_no_jpg):
            cmd_new(SimpleNamespace(name=str(target)))
        assert (target / "favicon.ico").exists()


class TestCmdMonitoring:
    def _call(self, action):
        cmd_monitoring(SimpleNamespace(monitoring_action=action))

    def test_enable(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._call("enable")
        assert "enabled" in capsys.readouterr().out
        content = (tmp_path / ".env").read_text()
        assert "MONITORING_ENABLED=true" in content

    def test_disable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._call("disable")
        content = (tmp_path / ".env").read_text()
        assert "MONITORING_ENABLED=false" in content

    def test_status(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("dotenv.load_dotenv", return_value=False), \
             patch.dict(os.environ, {
                 "MONITORING_ENABLED": "true",
                 "MONITORING_USER": "bob",
                 "MONITORING_SITES": "http://x.test",
             }, clear=True):
            self._call("status")
        out = capsys.readouterr().out
        assert "ENABLED" in out
        assert "bob" in out
        assert "http://x.test" in out

    def test_status_disabled(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("dotenv.load_dotenv", return_value=False), \
             patch.dict(os.environ, {"MONITORING_ENABLED": "false"}, clear=True):
            self._call("status")
        assert "DISABLED" in capsys.readouterr().out

    def test_status_no_dotenv(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch.dict(sys.modules, {"dotenv": None}), \
             patch.dict(os.environ, {}, clear=True):
            self._call("status")
        assert "DISABLED" in capsys.readouterr().out

    def test_set_password(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("getpass.getpass", return_value="newpass"), \
             patch("secrets.token_hex", return_value="deadbeef"):
            self._call("set-password")
        content = (tmp_path / ".env").read_text()
        assert "MONITORING_PASSWORD=newpass" in content
        assert "MONITORING_SECRET_KEY=deadbeef" in content

    def test_set_password_empty(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("getpass.getpass", return_value=""):
            self._call("set-password")
        assert "empty" in capsys.readouterr().out

    def test_unknown_action(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._call("bogus-action")
        assert capsys.readouterr().out


class TestCmdRoutesEdges:
    def test_routes_with_blueprint(self, capsys):
        route = MagicMock()
        route.path_pattern = "/bp"
        route.methods = {"GET"}
        route.handler = MagicMock(__name__="bp_handler")
        route.is_falcon_resource.return_value = False

        bp = MagicMock()
        bp.name = "admin"

        app = MagicMock()
        app.title = "t"
        app.router.routes = [route]
        app.router.websocket_routes = []
        app._route_blueprints = {route: bp}

        with patch("fenrir.cli.load_app", return_value=app):
            cmd_routes(SimpleNamespace(target="x"))
        assert "admin" in capsys.readouterr().out

    def test_websocket_with_blueprint(self, capsys):
        ws_route = MagicMock()
        ws_route.path_pattern = "/wsp"
        ws_route.handler = MagicMock(__name__="ws_handler")

        bp = MagicMock()
        bp.name = "wsbp"

        app = MagicMock()
        app.title = "t"
        app.router.routes = []
        app.router.websocket_routes = [ws_route]
        app._route_blueprints = {ws_route: bp}

        with patch("fenrir.cli.load_app", return_value=app):
            cmd_routes(SimpleNamespace(target="x"))
        assert "wsbp" in capsys.readouterr().out


def _info_app():
    app = MagicMock()
    app.title = "App"
    app.version = "1.0"
    app.router.routes = []
    app.router.websocket_routes = []
    app._asgi_middlewares = []
    return app


class TestCmdInfoEdges:
    def test_pydantic_version_fallback(self, capsys):
        import pydantic
        saved = pydantic.__version__
        del pydantic.__version__
        try:
            cmd_info(SimpleNamespace(target=None))
        finally:
            pydantic.__version__ = saved
        out = capsys.readouterr().out
        assert "Pydantic" in out

    def test_pydantic_import_error(self, capsys):
        with patch.dict(sys.modules, {"pydantic": None}):
            cmd_info(SimpleNamespace(target=None))
        out = capsys.readouterr().out
        assert "No" in out

    def test_pydantic_no_version_attrs(self, capsys):
        import pydantic
        saved_v, saved_V = pydantic.__version__, pydantic.VERSION
        del pydantic.__version__
        del pydantic.VERSION
        try:
            cmd_info(SimpleNamespace(target=None))
        finally:
            pydantic.__version__ = saved_v
            pydantic.VERSION = saved_V
        out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
        assert "Pydantic installed:  Yes" in out

    def test_asteri_version_branch(self, capsys):
        import asteri
        with patch.object(asteri, "__version__", "3.0.0", create=True):
            cmd_info(SimpleNamespace(target=None))
        out = capsys.readouterr().out
        assert "(v3.0.0)" in out

    def test_asteri_version_fallback(self, capsys):
        import asteri
        with patch.object(asteri, "VERSION", "3.0.0", create=True):
            cmd_info(SimpleNamespace(target=None))
        out = capsys.readouterr().out
        assert "(v3.0.0)" in out

    def test_asteri_import_error(self, capsys):
        with patch.dict(sys.modules, {"asteri": None}):
            cmd_info(SimpleNamespace(target=None))
        out = capsys.readouterr().out
        assert "Asteri" in out

    def test_compat_layers_all(self, capsys):
        mods = {name: MagicMock() for name in ("fastapi", "bottle", "falcon", "sanic")}
        for name in mods:
            sys.modules[name] = mods[name]
        try:
            with patch("fenrir.cli.load_app", return_value=_info_app()):
                cmd_info(SimpleNamespace(target="x"))
        finally:
            for name in mods:
                sys.modules.pop(name, None)
        out = capsys.readouterr().out
        for name in ("FastAPI", "Bottle", "Falcon", "Sanic"):
            assert name in out
