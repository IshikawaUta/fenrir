import json
import base64
import uuid
from datetime import date, datetime
from typing import Any, Callable, Dict, Type

class JSONProvider:
    def __init__(self, app: Any):
        self._app = app

    def dumps(self, obj: Any, **kwargs: Any) -> str:
        raise NotImplementedError()

    def loads(self, s: str, **kwargs: Any) -> Any:
        raise NotImplementedError()


class DefaultJSONProvider(JSONProvider):
    def dumps(self, obj: Any, **kwargs: Any) -> str:
        # Default options
        kwargs.setdefault("ensure_ascii", False)
        # Custom default serializer for datetime / UUID
        def default(o: Any) -> Any:
            if isinstance(o, datetime):
                return o.isoformat()
            if isinstance(o, date):
                return o.isoformat()
            if isinstance(o, uuid.UUID):
                return str(o)
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
        
        kwargs.setdefault("default", default)
        return json.dumps(obj, **kwargs)

    def loads(self, s: str, **kwargs: Any) -> Any:
        return json.loads(s, **kwargs)


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
                return [tag(v) for o_item in o for v in (o_item,)]  # safe iteration
            return o

        return json.dumps(tag(obj))

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

        return untag(json.loads(s))
