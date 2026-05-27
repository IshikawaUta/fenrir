import os
import pytest
from fenrir import Fenrir

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
