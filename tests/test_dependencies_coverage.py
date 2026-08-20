"""Targeted coverage tests for fenrir.dependencies internals."""
from typing import List

import pytest
from pydantic import BaseModel

import fenrir.dependencies as d
from fenrir.compat import Annotated
from fenrir.dependencies import (
    Body,
    Cookie,
    Depends,
    Form,
    Header,
    Path,
    Query,
    _get_cached_signature,
    _get_cached_type_adapter,
    _is_async_dep,
    resolve_parameters,
)
from fenrir.exceptions import HTTPException, HTTPUnprocessableEntity
from fenrir.response import Response


class StubReq:
    def __init__(self, args=None, headers=None, cookies=None, json=None, form=None):
        self.args = args or {}
        self.headers = headers or {}
        self.cookies = cookies or {}
        self._json = json
        self._form = form or {}

    @property
    def json(self):
        return self._json

    async def form(self):
        return self._form


class TestCaches:
    def test_dep_is_async_cache_eviction(self, monkeypatch):
        monkeypatch.setattr(d, "_DEP_CACHE_MAX", 1)

        def dep():
            return 1

        def dep2():
            return 2

        assert _is_async_dep(dep) is False
        assert _is_async_dep(dep2) is False

    def test_dep_is_async_callable(self):
        class AsyncCall:
            async def __call__(self):
                return 1

        assert _is_async_dep(AsyncCall()) is True

    def test_type_adapter_unhashable(self):
        adapter = _get_cached_type_adapter(list)
        assert adapter.validate_python([1]) == [1]

    def test_type_adapter_cache_set_error(self, monkeypatch):
        class Boom:
            def __getitem__(self, k):
                raise TypeError("unhashable")

            def __setitem__(self, k, v):
                raise TypeError("unhashable")

        monkeypatch.setattr(d, "_type_adapter_cache", Boom())
        adapter = _get_cached_type_adapter(int)
        assert adapter is not None

    def test_signature_cache_unhashable(self):
        class NoHash:
            __hash__ = None

            def __call__(self, x: int) -> str:
                ...

        sig = _get_cached_signature(NoHash())
        assert "x" in sig.parameters

    def test_signature_invalid(self):
        with pytest.raises((ValueError, TypeError)):
            _get_cached_signature(None)


class TestDepends:
    def test_hash_and_eq(self):
        def f():
            return 1

        a = Depends(f)
        b = Depends(f)
        assert hash(a) == hash(b)
        assert a == b
        assert (a == Depends(f, use_cache=False)) is False
        assert (a == object()) is False
        assert Depends() == Depends()
        mapping = {Depends(f): "v"}
        assert mapping[Depends(f)] == "v"


class TestParamKinds:
    @pytest.mark.anyio
    async def test_skip_var_params(self):
        async def h(a="x", *args, **kwargs):
            ...

        assert await resolve_parameters(h, {}, StubReq(), Response()) == {"a": "x"}

    @pytest.mark.anyio
    async def test_req_resp_params(self):
        async def h(req, resp):
            ...

        req = StubReq()
        resp = Response()
        resolved = await resolve_parameters(h, {}, req, resp)
        assert resolved == {"req": req, "resp": resp}

    @pytest.mark.anyio
    async def test_ws_param_name(self):
        async def h(ws):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response(), ws="WS")
        assert resolved["ws"] == "WS"

    @pytest.mark.anyio
    async def test_ws_annotation(self):
        class WebSocket:
            pass

        async def h(c: WebSocket):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response(), ws="SOCK")
        assert resolved["c"] == "SOCK"

    @pytest.mark.anyio
    async def test_background_tasks_injection(self):
        from fenrir.background import BackgroundTasks

        async def h(bt: BackgroundTasks):
            ...

        req = StubReq()
        resolved = await resolve_parameters(h, {}, req, Response())
        assert isinstance(resolved["bt"], BackgroundTasks)

    @pytest.mark.anyio
    async def test_background_tasks_subclass(self):
        from fenrir.background import BackgroundTasks

        class MyBT(BackgroundTasks):
            pass

        async def h(bt: MyBT):
            ...

        req = StubReq()
        resolved = await resolve_parameters(h, {}, req, Response())
        assert isinstance(resolved["bt"], BackgroundTasks)

    @pytest.mark.anyio
    async def test_background_tasks_existing(self):
        from fenrir.background import BackgroundTasks

        async def h(bt: BackgroundTasks):
            ...

        req = StubReq()
        req._background_tasks = BackgroundTasks()
        resolved = await resolve_parameters(h, {}, req, Response())
        assert resolved["bt"] is req._background_tasks


class TestAnnotated:
    @pytest.mark.anyio
    async def test_annotated_no_marker(self):
        async def h(x: Annotated[int, None]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(args={"x": "5"}), Response())
        assert resolved["x"] == 5

    @pytest.mark.anyio
    async def test_annotated_second_marker(self):
        async def h(x: Annotated[int, None, Query()]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(args={"x": "7"}), Response())
        assert resolved["x"] == 7

    @pytest.mark.anyio
    async def test_annotated_marker_with_default(self):
        async def h(x: Annotated[int, Form()] = 5):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == 5

    @pytest.mark.anyio
    async def test_annotated_marker_no_func_default(self):
        async def h(x: Annotated[str, Query()]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(args={"x": "v"}), Response())
        assert resolved["x"] == "v"

    @pytest.mark.anyio
    async def test_annotated_form_no_func_default(self):
        async def h(x: Annotated[int, Form()]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={"x": "3"}), Response())
        assert resolved["x"] == 3


class TestDependencies:
    def real_dep(self):
        return "R"

    @pytest.mark.anyio
    async def test_depends_unresolvable(self):
        async def h(x: "NotCallable" = Depends()):  # noqa: F821 - intentional unresolved forward ref
            ...

        with pytest.raises(ValueError):
            await resolve_parameters(h, {}, StubReq(), Response())

    @pytest.mark.anyio
    async def test_depends_callable_annotation(self):
        def fn():
            return "C"

        async def h(x: fn = Depends()):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == "C"

    @pytest.mark.anyio
    async def test_lambda_dep_callable(self):
        async def h(x: str = Depends(lambda: self.real_dep)):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == "R"

    @pytest.mark.anyio
    async def test_lambda_dep_noncallable(self):
        async def h(x: str = Depends(lambda: "plain")):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == "plain"

    @pytest.mark.anyio
    async def test_override_not_matched(self, monkeypatch):
        other = lambda: "other"
        override = lambda: "override"
        class FakeApp:
            dependency_overrides = {other: override}
        monkeypatch.setattr(d, "_current_app", FakeApp())
        async def h(x: str = Depends(self.real_dep)):
            ...
        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == "R"

    @pytest.mark.anyio
    async def test_override_access_exception(self, monkeypatch):
        class Boom:
            def __len__(self):
                return 1

            def __contains__(self, k):
                raise RuntimeError("boom")

        class FakeApp:
            dependency_overrides = Boom()
        monkeypatch.setattr(d, "_current_app", FakeApp())
        async def h(x: str = Depends(self.real_dep)):
            ...
        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == "R"

    @pytest.mark.anyio
    async def test_yield_cleanup_existing(self):
        async def gen_dep():
            yield "Y"

        async def h(x: str = Depends(gen_dep)):
            ...

        req = StubReq()
        req._yield_cleanups = []
        resolved = await resolve_parameters(h, {}, req, Response())
        assert resolved["x"] == "Y"
        assert len(req._yield_cleanups) == 1

        def sync_gen_dep():
            yield "S"

        async def h2(x: str = Depends(sync_gen_dep)):
            ...

        resolved = await resolve_parameters(h2, {}, req, Response())
        assert resolved["x"] == "S"
        assert len(req._yield_cleanups) == 2


class TestPath:
    @pytest.mark.anyio
    async def test_path_validation_error(self):
        async def h(item_id: int):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {"item_id": "abc"}, StubReq(), Response())

    @pytest.mark.anyio
    async def test_path_validation_ok(self):
        async def h(item_id: int):
            ...

        resolved = await resolve_parameters(h, {"item_id": "42"}, StubReq(), Response())
        assert resolved["item_id"] == 42

    @pytest.mark.anyio
    async def test_path_unannotated(self):
        async def h(item_id):
            ...

        resolved = await resolve_parameters(h, {"item_id": "x"}, StubReq(), Response())
        assert resolved["item_id"] == "x"

    @pytest.mark.anyio
    async def test_path_marker(self):
        async def h(x: int = Path(9)):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == 9


class TestFormFile:
    @pytest.mark.anyio
    async def test_upload_annotation(self):
        from fenrir.upload import UploadFile

        async def h(f: UploadFile):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={"f": "data"}), Response())
        assert resolved["f"] == "data"

    @pytest.mark.anyio
    async def test_upload_list_annotation(self):
        from fenrir.upload import UploadFile

        async def h(fs: List[UploadFile]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={"fs": "data"}), Response())
        assert resolved["fs"] == "data"

    @pytest.mark.anyio
    async def test_upload_named_annotation(self):
        class NamedUpload:
            pass

        NamedUpload.__name__ = "UploadFile"

        async def h(fs: List[NamedUpload]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={"fs": "data"}), Response())
        assert resolved["fs"] == "data"

    @pytest.mark.anyio
    async def test_list_no_upload_annotation(self):
        from typing import Optional

        async def h(fs: Optional[int]):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(args={"fs": "5"}), Response())
        assert resolved["fs"] == 5

    @pytest.mark.anyio
    async def test_upload_no_default(self):
        from fenrir.upload import UploadFile

        async def h(f: UploadFile):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {}, StubReq(form={}), Response())

    @pytest.mark.anyio
    async def test_form_default_paraminfo(self):
        async def h(x: str = Form(default="D")):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={}), Response())
        assert resolved["x"] == "D"

    @pytest.mark.anyio
    async def test_form_default_plain(self):
        from fenrir.upload import UploadFile

        async def h(x: UploadFile = None):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(form={}), Response())
        assert resolved["x"] is None

    @pytest.mark.anyio
    async def test_form_required_missing(self):
        async def h(x: str = Form()):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {}, StubReq(form={}), Response())

    @pytest.mark.anyio
    async def test_form_validation_error(self):
        async def h(x: int = Form()):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {}, StubReq(form={"x": "abc"}), Response())


class TestBody:
    @pytest.mark.anyio
    async def test_issubclass_typeerror(self):
        async def h(x: "ForwardRef" = Query(5)):  # noqa: F821 - intentional unresolved forward ref
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == 5

    @pytest.mark.anyio
    async def test_strict_content_type_reject(self, monkeypatch):
        class Item(BaseModel):
            name: str

        class FakeApp:
            strict_content_type = True
        monkeypatch.setattr(d, "_current_app", FakeApp())
        async def h(item: Item = Body()):
            ...
        with pytest.raises(HTTPException):
            await resolve_parameters(
                h, {}, StubReq(json={"name": "x"}, headers={"content-type": "text/plain"}), Response()
            )

    @pytest.mark.anyio
    async def test_strict_content_type_ok(self, monkeypatch):
        class Item(BaseModel):
            name: str

        class FakeApp:
            strict_content_type = True
        monkeypatch.setattr(d, "_current_app", FakeApp())
        async def h(item: Item = Body()):
            ...
        resolved = await resolve_parameters(
            h, {}, StubReq(json={"name": "x"}, headers={"content-type": "application/json"}), Response()
        )
        assert resolved["item"].name == "x"

    @pytest.mark.anyio
    async def test_strict_attr_exception(self, monkeypatch):
        class Item(BaseModel):
            name: str

        class Boom:
            @property
            def strict_content_type(self):
                raise RuntimeError("boom")
        monkeypatch.setattr(d, "_current_app", Boom())
        async def h(item: Item = Body()):
            ...
        resolved = await resolve_parameters(h, {}, StubReq(json={"name": "x"}), Response())
        assert resolved["item"].name == "x"

    @pytest.mark.anyio
    async def test_strict_attr_absent(self, monkeypatch):
        class Item(BaseModel):
            name: str

        class FakeApp:
            pass
        monkeypatch.setattr(d, "_current_app", FakeApp())
        async def h(item: Item = Body()):
            ...
        resolved = await resolve_parameters(h, {}, StubReq(json={"name": "x"}), Response())
        assert resolved["item"].name == "x"

    @pytest.mark.anyio
    async def test_body_dict(self):
        async def h(x: dict = Body()):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(json={"a": 1}), Response())
        assert resolved["x"] == {"a": 1}


class TestQueryHeaderCookie:
    @pytest.mark.anyio
    async def test_query_validation_error(self):
        async def h(x: int):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {}, StubReq(args={"x": "abc"}), Response())

    @pytest.mark.anyio
    async def test_header_validation_error(self):
        async def h(x: int = Header()):
            ...

        with pytest.raises(HTTPUnprocessableEntity):
            await resolve_parameters(h, {}, StubReq(headers={"x": "abc"}), Response())

    @pytest.mark.anyio
    async def test_header_dash_lookup(self):
        async def h(x_api_key: str = Header()):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(headers={"x-api-key": "k"}), Response())
        assert resolved["x_api_key"] == "k"

    @pytest.mark.anyio
    async def test_cookie_alias(self):
        async def h(sid: str = Cookie(alias="sid")):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(cookies={"sid": "abc"}), Response())
        assert resolved["sid"] == "abc"

    @pytest.mark.anyio
    async def test_cookie_default(self):
        async def h(sid: str = Cookie("def")):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["sid"] == "def"

    @pytest.mark.anyio
    async def test_query_plain_default(self):
        async def h(x: int = 7):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(), Response())
        assert resolved["x"] == 7

    @pytest.mark.anyio
    async def test_query_unannotated(self):
        async def h(x):
            ...

        resolved = await resolve_parameters(h, {}, StubReq(args={"x": "v"}), Response())
        assert resolved["x"] == "v"
