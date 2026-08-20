"""Tests for fenrir.json module."""
import json
import uuid
from datetime import date, datetime

import pytest

from fenrir.json import (
    DefaultJSONProvider,
    JSONProvider,
    JSONTag,
    TagBytes,
    TagDate,
    TagDateTime,
    TaggedJSONSerializer,
    TagTuple,
    TagUUID,
    json_dumps,
    json_dumps_bytes,
    json_loads,
)

# ═══════════════════════════════════════════════════════════════════════
# JSONProvider Base Tests
# ═══════════════════════════════════════════════════════════════════════

class TestJSONProvider:
    def test_base_dumps_raises(self):
        provider = JSONProvider(None)
        with pytest.raises(NotImplementedError):
            provider.dumps({})

    def test_base_loads_raises(self):
        provider = JSONProvider(None)
        with pytest.raises(NotImplementedError):
            provider.loads("{}")


# ═══════════════════════════════════════════════════════════════════════
# DefaultJSONProvider Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDefaultJSONProvider:
    def test_dumps_basic(self):
        provider = DefaultJSONProvider(None)
        result = provider.dumps({"key": "value", "num": 42})
        parsed = json.loads(result)
        assert parsed == {"key": "value", "num": 42}

    def test_loads_basic(self):
        provider = DefaultJSONProvider(None)
        result = provider.loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_dumps_unicode(self):
        provider = DefaultJSONProvider(None)
        result = provider.dumps({"text": "日本語"})
        parsed = json.loads(result)
        assert parsed["text"] == "日本語"

    def test_dumps_datetime(self):
        provider = DefaultJSONProvider(None)
        dt = datetime(2024, 1, 15, 12, 30, 0)
        result = provider.dumps({"ts": dt})
        parsed = json.loads(result)
        assert "2024-01-15" in parsed["ts"]

    def test_dumps_date(self):
        provider = DefaultJSONProvider(None)
        d = date(2024, 1, 15)
        result = provider.dumps({"day": d})
        parsed = json.loads(result)
        assert parsed["day"] == "2024-01-15"

    def test_dumps_uuid(self):
        provider = DefaultJSONProvider(None)
        u = uuid.uuid4()
        result = provider.dumps({"id": u})
        parsed = json.loads(result)
        assert parsed["id"] == str(u)

    def test_dumps_non_serializable_raises(self):
        provider = DefaultJSONProvider(None)
        with pytest.raises(TypeError, match="not JSON serializable"):
            provider.dumps({"obj": object()})


# ═══════════════════════════════════════════════════════════════════════
# JSONTag Tests
# ═══════════════════════════════════════════════════════════════════════

class TestJSONTag:
    def test_base_check_raises(self):
        with pytest.raises(NotImplementedError):
            JSONTag().check("value")

    def test_base_to_json_raises(self):
        with pytest.raises(NotImplementedError):
            JSONTag().to_json("value")

    def test_base_to_python_raises(self):
        with pytest.raises(NotImplementedError):
            JSONTag().to_python("value")


# ═══════════════════════════════════════════════════════════════════════
# TagDateTime Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTagDateTime:
    def test_check_true(self):
        assert TagDateTime().check(datetime.now()) is True

    def test_check_false(self):
        assert TagDateTime().check("not a datetime") is False

    def test_to_json(self):
        dt = datetime(2024, 1, 15, 12, 0)
        result = TagDateTime().to_json(dt)
        assert result == {"__t__": "dt", "__v__": "2024-01-15T12:00:00"}

    def test_to_python(self):
        result = TagDateTime().to_python("2024-01-15T12:00:00")
        assert result == datetime(2024, 1, 15, 12, 0)


# ═══════════════════════════════════════════════════════════════════════
# TagDate Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTagDate:
    def test_check_true(self):
        assert TagDate().check(date(2024, 1, 15)) is True

    def test_check_datetime_is_false(self):
        assert TagDate().check(datetime(2024, 1, 15)) is False

    def test_check_false(self):
        assert TagDate().check("not a date") is False

    def test_to_json(self):
        result = TagDate().to_json(date(2024, 1, 15))
        assert result == {"__t__": "d", "__v__": "2024-01-15"}

    def test_to_python(self):
        result = TagDate().to_python("2024-01-15")
        assert result == date(2024, 1, 15)


# ═══════════════════════════════════════════════════════════════════════
# TagUUID Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTagUUID:
    def test_check_true(self):
        assert TagUUID().check(uuid.uuid4()) is True

    def test_check_false(self):
        assert TagUUID().check("not a uuid") is False

    def test_to_json(self):
        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = TagUUID().to_json(u)
        assert result["__t__"] == "u"
        assert result["__v__"] == u.hex

    def test_to_python(self):
        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = TagUUID().to_python(u.hex)
        assert result == u


# ═══════════════════════════════════════════════════════════════════════
# TagBytes Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTagBytes:
    def test_check_true(self):
        assert TagBytes().check(b"data") is True

    def test_check_false(self):
        assert TagBytes().check("not bytes") is False

    def test_to_json(self):
        result = TagBytes().to_json(b"hello")
        assert result["__t__"] == "b"

    def test_to_python(self):
        import base64
        encoded = base64.b64encode(b"hello").decode()
        result = TagBytes().to_python(encoded)
        assert result == b"hello"


# ═══════════════════════════════════════════════════════════════════════
# TagTuple Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTagTuple:
    def test_check_true(self):
        assert TagTuple().check((1, 2, 3)) is True

    def test_check_false(self):
        assert TagTuple().check([1, 2, 3]) is False

    def test_to_json(self):
        result = TagTuple().to_json((1, 2))
        assert result == {"__t__": "t", "__v__": [1, 2]}

    def test_to_python(self):
        result = TagTuple().to_python([1, 2])
        assert result == (1, 2)


# ═══════════════════════════════════════════════════════════════════════
# TaggedJSONSerializer Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTaggedJSONSerializer:
    def test_roundtrip_dict(self):
        s = TaggedJSONSerializer()
        data = {"key": "value", "num": 42}
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded == data

    def test_roundtrip_datetime(self):
        s = TaggedJSONSerializer()
        dt = datetime(2024, 1, 15, 12, 0)
        data = {"ts": dt}
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded["ts"] == dt

    def test_roundtrip_uuid(self):
        s = TaggedJSONSerializer()
        u = uuid.uuid4()
        data = {"id": u}
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded["id"] == u

    def test_roundtrip_bytes(self):
        s = TaggedJSONSerializer()
        data = {"data": b"binary"}
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded["data"] == b"binary"

    def test_roundtrip_tuple(self):
        s = TaggedJSONSerializer()
        data = {"items": (1, 2, 3)}
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded["items"] == (1, 2, 3)

    def test_roundtrip_nested(self):
        s = TaggedJSONSerializer()
        data = {
            "name": "test",
            "ts": datetime(2024, 1, 15),
            "tags": ["a", "b"],
            "meta": {"nested": True}
        }
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded["name"] == "test"
        assert loaded["ts"] == datetime(2024, 1, 15)
        assert loaded["tags"] == ["a", "b"]
        assert loaded["meta"] == {"nested": True}

    def test_roundtrip_list(self):
        s = TaggedJSONSerializer()
        data = [datetime(2024, 1, 15), "text", 42]
        dumped = s.dumps(data)
        loaded = s.loads(dumped)
        assert loaded[0] == datetime(2024, 1, 15)
        assert loaded[1] == "text"
        assert loaded[2] == 42


# ═══════════════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelperFunctions:
    def test_json_dumps(self):
        result = json_dumps({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_json_loads(self):
        result = json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_loads_bytes(self):
        result = json_loads(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_dumps_bytes(self):
        result = json_dumps_bytes({"key": "value"})
        assert isinstance(result, bytes)
        assert b"key" in result

    def test_json_dumps_orjson_path(self):
        """Test the orjson path if available."""
        result = json_dumps([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_json_loads_orjson_path(self):
        """Test the orjson path if available."""
        result = json_loads("[1, 2, 3]")
        assert result == [1, 2, 3]
