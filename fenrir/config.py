import os
import types
from typing import Any, Mapping, Union

class Config(dict):
    def __init__(self, root_path: str, defaults: dict = None):
        super().__init__(defaults or {})
        self.root_path = root_path

    def from_object(self, obj: Union[object, str]):
        if isinstance(obj, str):
            import importlib
            obj = importlib.import_module(obj)
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)

    def from_mapping(self, mapping: Mapping[str, Any]):
        for key, value in mapping.items():
            if key.isupper():
                self[key] = value

    def from_pyfile(self, filename: str, silent: bool = False) -> bool:
        filepath = os.path.join(self.root_path, filename)
        d = types.ModuleType("config")
        d.__file__ = filepath
        try:
            with open(filepath, mode="rb") as config_file:
                exec(compile(config_file.read(), filepath, "exec"), d.__dict__)
        except OSError:
            if silent:
                return False
            raise
        self.from_object(d)
        return True

    def from_envvar(self, variable_name: str, silent: bool = False) -> bool:
        rv = os.environ.get(variable_name)
        if not rv:
            if silent:
                return False
            raise RuntimeError(
                f"The environment variable {variable_name!r} is not set "
                "and as such configuration could not be loaded."
            )
        return self.from_pyfile(rv, silent=silent)
