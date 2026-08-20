"""Unit tests for fenrir.openapi edge paths."""
import sys
from typing import Union

from pydantic import BaseModel

from fenrir.compat import Annotated
from fenrir.dependencies import Body, Cookie, Depends, Header, Path
from fenrir.openapi import _annotation_to_schema, _path_to_openapi, _resolve_annotation, get_openapi
from fenrir.routing import Route


def test_annotation_primitives():
    assert _annotation_to_schema(float) == {"type": "number"}
    assert _annotation_to_schema(bool) == {"type": "boolean"}
    assert _annotation_to_schema(bytes) == {"type": "string", "format": "binary"}
    assert _annotation_to_schema(tuple[int, str]) == {"type": "string"}
    assert _annotation_to_schema(inspect_parameter_empty()) == {"type": "string"}


def inspect_parameter_empty():
    import inspect
    return inspect.Parameter.empty


def test_union_oneof():
    schema = _annotation_to_schema(Union[int, str])
    assert schema["oneOf"][0] == {"type": "integer"}
    assert schema["oneOf"][1] == {"type": "string"}


def test_union_nullable():
    from typing import Optional

    schema = _annotation_to_schema(Optional[int])
    assert schema == {"type": "integer", "nullable": True}


def test_path_to_openapi():
    assert _path_to_openapi("/users/<int:user_id>") == "/users/{user_id}"
    assert _path_to_openapi("/x/<re:[0-9]+:num>") == "/x/{num}"
    assert _path_to_openapi("/a/<b>") == "/a/{b}"


def test_resolve_annotation():
    base, marker = _resolve_annotation(Annotated[int, Header()])
    assert base is int
    assert isinstance(marker, Header)
    base, marker = _resolve_annotation(int)
    assert base is int
    assert marker is None


def test_falcon_resource_missing_method():
    class Resource:
        def on_get(self, req, resp):
            pass

    route = Route("/r", Resource(), methods=["POST"])
    schema = get_openapi("T", "1.0.0", [route])
    assert schema["paths"]["/r"] == {}


def test_inspect_signature_error():
    route = Route("/s", 42, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    assert "get" in schema["paths"]["/s"]


def test_background_tasks_param_skipped():
    from fenrir.background import BackgroundTasks

    async def h(bg: BackgroundTasks):
        pass

    route = Route("/t", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/t"]["get"]
    assert "parameters" not in op


def test_websocket_param_skipped():
    class WebSocket:
        pass

    async def h(ws: WebSocket):
        pass

    route = Route("/w", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/w"]["get"]
    assert "parameters" not in op


def test_body_without_annotation():
    def h(payload=Body()):
        pass

    route = Route("/b", h, methods=["POST"])
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/b"]["post"]
    assert op["requestBody"]["content"]["application/json"]["schema"] == {"type": "object"}


def test_body_model_schema_error(monkeypatch):
    class M(BaseModel):
        x: int

    def _boom(cls):
        raise RuntimeError("boom")

    monkeypatch.setattr(M, "model_json_schema", classmethod(_boom))

    async def h(body: M):
        pass

    route = Route("/e", h, methods=["POST"])
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/e"]["post"]
    assert op["requestBody"]["content"]["application/json"]["schema"] == {"type": "object"}


def test_param_locations_and_aliases():
    def h(
        user_agent: str = Header(),
        token: str = Cookie(),
        pid: int = Path(),
        alias_var: str = Path(alias="aid"),
    ):
        pass

    route = Route("/u/<int:pid>/<aid>", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/u/{pid}/{aid}"]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert params["user-agent"]["in"] == "header"
    assert params["user-agent"]["required"] is False
    assert params["token"]["in"] == "cookie"
    assert params["pid"]["in"] == "path"
    assert params["pid"]["required"] is True
    assert params["aid"]["in"] == "path"
    assert params["aid"]["schema"]["type"] == "string"


def test_annotated_marker_default():
    def h(x: Annotated[int, Header()]):
        pass

    route = Route("/m", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    params = schema["paths"]["/m"]["get"]["parameters"]
    assert params[0]["in"] == "header"
    assert params[0]["required"] is False


def test_background_import_error(monkeypatch):
    import fenrir
    from fenrir.background import BackgroundTasks

    async def h(bg: BackgroundTasks):
        pass

    monkeypatch.delattr(fenrir, "background", raising=False)
    monkeypatch.setitem(sys.modules, "fenrir.background", None)
    route = Route("/t", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    assert "parameters" in schema["paths"]["/t"]["get"]


def test_depends_param_skipped():
    def dep():
        return 1

    def h(d: int = Depends(dep)):
        pass

    route = Route("/d", h, methods=["GET"])
    schema = get_openapi("T", "1.0.0", [route])
    assert "parameters" not in schema["paths"]["/d"]["get"]


def test_response_model_schema_error(monkeypatch):
    class M(BaseModel):
        x: int

    def _boom(cls):
        raise RuntimeError("boom")

    monkeypatch.setattr(M, "model_json_schema", classmethod(_boom))

    async def h():
        pass

    route = Route("/rme", h, methods=["GET"], response_model=M)
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/rme"]["get"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {"type": "object"}


def test_response_model_not_base_model():
    async def h():
        pass

    route = Route("/rm", h, methods=["GET"], response_model=int)
    schema = get_openapi("T", "1.0.0", [route])
    op = schema["paths"]["/rm"]["get"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {"type": "object"}
