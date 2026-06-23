"""
fenrir.json — JSON serialization using orjson.

Provides fast JSON serialization with orjson (fallback to stdlib json).
"""
from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from typing import Any, Callable, Dict, Type

# Try to import orjson, fallback to stdlib json
try:
    import orjson as _orjson
    _HAS_ORJSON = True
except ImportError:
    _orjson = None  # type: ignore
    _HAS_ORJSON = False

import json as _stdlib_json


class JSONProvider:
    def __init__(self, app: Any):
        self._app = app

    def dumps(self, obj: Any, **kwargs: Any) -> str:
        raise NotImplementedError()

    def loads(self, s: str, **kwargs: Any) -> Any:
        raise NotImplementedError()


class DefaultJSONProvider(JSONProvider):
    def dumps(self, obj: Any, **kwargs: Any) -> str:
        if _HAS_ORJSON:
            # orjson doesn't accept ensure_ascii or default kwargs
            # It handles most types natively, use default fallback for others
            result = _orjson.dumps(obj)
            return result.decode("utf-8") if isinstance(result, bytes) else result
        
        kwargs.setdefault("ensure_ascii", False)
        
        def default(o: Any) -> Any:
            if isinstance(o, datetime):
                return o.isoformat()
            if isinstance(o, date):
                return o.isoformat()
            if isinstance(o, uuid.UUID):
                return str(o)
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
        
        kwargs.setdefault("default", default)
        return _stdlib_json.dumps(obj, **kwargs)

    def loads(self, s: str, **kwargs: Any) -> Any:
        if _HAS_ORJSON:
            # orjson accepts both str and bytes
            return _orjson.loads(s)
        return _stdlib_json.loads(s, **kwargs)


class JSONTag:
    def check(self, value: Any) -> bool:
        raise NotImplementedError()

    def to_json(self, value: Any) -> Any:
        raise NotImplementedError()

    def to_python(self, value: Any) -> Any:
        raise NotImplementedError()


class TagDateTime(JSONTag):
    def check(self, value: Any) -> bool:
        return isinstance(value, datetime)

    def to_json(self, value: Any) -> Any:
        return {"__t__": "dt", "__v__": value.isoformat()}

    def to_python(self, value: Any) -> Any:
        return datetime.fromisoformat(value)


class TagDate(JSONTag):
    def check(self, value: Any) -> bool:
        return isinstance(value, date) and not isinstance(value, datetime)

    def to_json(self, value: Any) -> Any:
        return {"__t__": "d", "__v__": value.isoformat()}

    def to_python(self, value: Any) -> Any:
        return date.fromisoformat(value)


class TagUUID(JSONTag):
    def check(self, value: Any) -> bool:
        return isinstance(value, uuid.UUID)

    def to_json(self, value: Any) -> Any:
        return {"__t__": "u", "__v__": value.hex}

    def to_python(self, value: Any) -> Any:
        return uuid.UUID(value)


class TagBytes(JSONTag):
    def check(self, value: Any) -> bool:
        return isinstance(value, bytes)

    def to_json(self, value: Any) -> Any:
        return {"__t__": "b", "__v__": base64.b64encode(value).decode("utf-8")}

    def to_python(self, value: Any) -> Any:
        return base64.b64decode(value.encode("utf-8"))


class TagTuple(JSONTag):
    def check(self, value: Any) -> bool:
        return isinstance(value, tuple)

    def to_json(self, value: Any) -> Any:
        return {"__t__": "t", "__v__": list(value)}

    def to_python(self, value: Any) -> Any:
        return tuple(value)


class TaggedJSONSerializer:
    tags: Dict[str, JSONTag] = {
        "dt": TagDateTime(),
        "d": TagDate(),
        "u": TagUUID(),
        "b": TagBytes(),
        "t": TagTuple(),
    }

    def dumps(self, obj: Any) -> str:
        def tag(o: Any) -> Any:
            for tag_name, tag_obj in self.tags.items():
                if tag_obj.check(o):
                    return tag_obj.to_json(o)
            if isinstance(o, dict):
                return {k: tag(v) for k, v in o.items()}
            if isinstance(o, list):
                return [tag(item) for item in o]
            return o

        tagged = tag(obj)
        if _HAS_ORJSON:
            result = _orjson.dumps(tagged)
            return result.decode("utf-8") if isinstance(result, bytes) else result
        return _stdlib_json.dumps(tagged)

    def loads(self, s: str) -> Any:
        def untag(o: Any) -> Any:
            if isinstance(o, dict):
                if "__t__" in o and "__v__" in o:
                    tag_name = o["__t__"]
                    if tag_name in self.tags:
                        return self.tags[tag_name].to_python(o["__v__"])
                return {k: untag(v) for k, v in o.items()}
            if isinstance(o, list):
                return [untag(v) for v in o]
            return o

        if _HAS_ORJSON:
            data = _orjson.loads(s)
        else:
            data = _stdlib_json.loads(s)
        return untag(data)


# ═══════════════════════════════════════════════════════════════════════
# Centralized JSON helpers — use these instead of importing json directly
# ═══════════════════════════════════════════════════════════════════════

def json_dumps(obj: Any) -> str:
    """Serialize to JSON string using orjson when available."""
    if _HAS_ORJSON:
        result = _orjson.dumps(obj)
        return result.decode("utf-8") if isinstance(result, bytes) else result
    return _stdlib_json.dumps(obj)


def json_loads(s: Any) -> Any:
    """Deserialize from JSON string/bytes using orjson when available."""
    if _HAS_ORJSON:
        return _orjson.loads(s)
    if isinstance(s, bytes):
        s = s.decode("utf-8")
    return _stdlib_json.loads(s)


def json_dumps_bytes(obj: Any) -> bytes:
    """Serialize to JSON bytes using orjson when available."""
    if _HAS_ORJSON:
        result = _orjson.dumps(obj)
        return result if isinstance(result, bytes) else result.encode("utf-8")
    return _stdlib_json.dumps(obj).encode("utf-8")
