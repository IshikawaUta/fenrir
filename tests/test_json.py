import datetime
import sys
import uuid

import pytest

from fenrir.json import (
    DefaultJSONProvider,
    JSONProvider,
    TaggedJSONSerializer,
    json_dumps,
    json_dumps_bytes,
    json_loads,
)


class CustomJSONProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return '{"custom": true}'
    def loads(self, s, **kwargs):
        return {"custom": True}

@pytest.mark.anyio
async def test_custom_json_provider(app):
    app.json = CustomJSONProvider(app)

    @app.get("/json")
    def get_json():
        return {"hello": "world"}

    client = app.test_client()
    resp = await client.get("/json")
    assert resp.status_code == 200
    assert resp.text == '{"custom": true}'

def test_default_json_provider_date_datetime(app):
    dt = datetime.datetime(2026, 5, 20, 15, 0, 0)
    d = datetime.date(2026, 5, 20)

    serialized_dt = app.json.dumps(dt)
    serialized_d = app.json.dumps(d)

    assert "2026-05-20T15:00:00" in serialized_dt
    assert "2026-05-20" in serialized_d


@pytest.fixture
def no_orjson(monkeypatch):
    import fenrir.json as j
    monkeypatch.setattr(j, "_HAS_ORJSON", False)
    monkeypatch.setattr(j, "_orjson", None)
    return j


def test_stdlib_dumps_default_types(no_orjson):
    prov = DefaultJSONProvider(None)
    dt = datetime.datetime(2026, 5, 20, 15, 0, 0)
    d = datetime.date(2026, 5, 20)
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert "2026-05-20T15:00:00" in prov.dumps(dt)
    assert '"2026-05-20"' in prov.dumps(d)
    assert '"12345678-1234-5678-1234-567812345678"' in prov.dumps(u)
    with pytest.raises(TypeError, match="not JSON serializable"):
        prov.dumps(object())


def test_stdlib_loads(no_orjson):
    prov = DefaultJSONProvider(None)
    assert prov.loads('{"a": 1}') == {"a": 1}


def test_tagged_json_stdlib_roundtrip(no_orjson):
    ser = TaggedJSONSerializer()
    dt = datetime.datetime(2026, 5, 20, 15, 0, 0)
    d = datetime.date(2026, 5, 20)
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    obj = {"dt": dt, "d": d, "u": u, "b": b"\x00\x01", "t": (1, 2), "lst": [dt], "nested": {"x": dt}}
    out = ser.loads(ser.dumps(obj))
    assert out["dt"] == dt
    assert out["d"] == d
    assert out["u"] == u
    assert out["b"] == b"\x00\x01"
    assert out["t"] == (1, 2)
    assert out["lst"] == [dt]
    assert out["nested"]["x"] == dt


def test_tagged_json_unknown_tag(no_orjson):
    ser = TaggedJSONSerializer()
    assert ser.loads('{"__t__": "zz", "__v__": 1}') == {"__t__": "zz", "__v__": 1}


def test_json_helpers_stdlib(no_orjson):
    assert json_dumps({"a": 1}) == '{"a": 1}'
    assert json_loads(b'{"a": 1}') == {"a": 1}
    assert json_dumps_bytes({"a": 1}) == b'{"a": 1}'


def test_json_fallback_import_without_orjson(monkeypatch):
    import importlib

    import orjson as real_orjson

    import fenrir.json as j

    monkeypatch.setitem(sys.modules, "orjson", None)
    importlib.reload(j)
    assert j._HAS_ORJSON is False
    assert j.json_dumps({"a": 1}) == '{"a": 1}'

    monkeypatch.setitem(sys.modules, "orjson", real_orjson)
    importlib.reload(j)
    assert j._HAS_ORJSON is True
