
import pytest

from fenrir.config import Config


class DummyConfigObject:
    DEBUG = True
    TESTING = True
    secret_value = "should-be-ignored"

def test_config_from_object(app):
    app.config.from_object(DummyConfigObject)
    assert app.config["DEBUG"] is True
    assert app.config["TESTING"] is True
    assert "secret_value" not in app.config

def test_config_from_mapping(app):
    app.config.from_mapping({"DEBUG": False, "TESTING": False, "ignored": 123})
    assert app.config["DEBUG"] is False
    assert app.config["TESTING"] is False
    assert "ignored" not in app.config

def test_config_from_pyfile(app, tmp_path):
    config_file = tmp_path / "config.py"
    config_file.write_text("DEBUG = True\nPORT = 8080\nlower_ignored = 'ignore'\n")
    app.config.from_pyfile(str(config_file))
    assert app.config["DEBUG"] is True
    assert app.config["PORT"] == 8080
    assert "lower_ignored" not in app.config

def test_config_from_envvar(app, tmp_path, monkeypatch):
    config_file = tmp_path / "config.py"
    config_file.write_text("SECRET_KEY = 'env-secret'\n")
    monkeypatch.setenv("FENRIR_SETTINGS", str(config_file))
    app.config.from_envvar("FENRIR_SETTINGS")
    assert app.config["SECRET_KEY"] == "env-secret"


def test_config_from_object_string(app, tmp_path, monkeypatch):
    (tmp_path / "confmod.py").write_text("APP_STRING_CONFIG = 42\nlower_ignored = 'x'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    app.config.from_object("confmod")
    assert app.config["APP_STRING_CONFIG"] == 42
    assert "lower_ignored" not in app.config


def test_config_from_pyfile_outside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.py").write_text("X = 1\n")
    cfg = Config(str(root))
    with pytest.raises(ValueError, match="outside the application root"):
        cfg.from_pyfile("../outside.py")


def test_config_from_pyfile_missing(tmp_path):
    cfg = Config(str(tmp_path))
    assert cfg.from_pyfile("nope.py", silent=True) is False
    with pytest.raises(OSError):
        cfg.from_pyfile("nope.py")


def test_config_from_envvar_unset(app, monkeypatch):
    monkeypatch.delenv("FENRIR_MISSING_CONFIG", raising=False)
    assert app.config.from_envvar("FENRIR_MISSING_CONFIG", silent=True) is False
    with pytest.raises(RuntimeError, match="not set"):
        app.config.from_envvar("FENRIR_MISSING_CONFIG")
