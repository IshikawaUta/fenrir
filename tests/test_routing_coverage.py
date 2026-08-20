"""Unit tests for fenrir.routing edge paths."""
import pytest

from fenrir.exceptions import HTTPMethodNotAllowed, HTTPNotFound
from fenrir.routing import APIRouter, Route, Router, RouteTrie, compile_path


def handler():
    pass


def test_compile_path_converter_second():
    regex, converters = compile_path("/u/<user_id:int>")
    assert converters == {"user_id": int}
    assert regex.match("/u/42")


def test_compile_path_re_middle():
    regex, converters = compile_path("/x/<uid:re:[0-9]+>")
    assert regex.match("/x/123")
    assert not regex.match("/x/abc")


def test_compile_path_three_plain():
    regex, converters = compile_path("/t/<a:b:c>")
    assert regex.match("/t/anything")
    assert converters == {"a": str}


def test_compile_path_two_plain():
    regex, converters = compile_path("/t2/<a:b>")
    assert regex.match("/t2/anything")
    assert converters == {"a": str}


def test_trie_insert_two_plain():
    trie = RouteTrie()
    trie.insert(Route("/x/<a:b>", handler))
    assert trie.root.children["x"].param_child.param_name == "a"


def test_route_match_converter_value_error():
    import re

    route = Route.__new__(Route)
    route.regex = re.compile("^(?P<x>.*)$")
    route.converters = {"x": int}
    assert route.match("/abc") is None


def test_trie_insert_three_parts():
    trie = RouteTrie()
    trie.insert(Route("/x/<a:b:c>", handler))
    assert trie.root.children["x"].param_child.param_name == "a"


def test_trie_insert_converter_three_parts():
    trie = RouteTrie()
    trie.insert(Route("/y/<int:a:b>", handler))
    node = trie.root.children["y"].param_child
    assert node.param_converter == "int"


def test_trie_reuses_param_child():
    trie = RouteTrie()
    trie.insert(Route("/p/<id>", handler))
    trie.insert(Route("/p/<name>", handler))
    node = trie.root.children["p"].param_child
    assert node.param_name == "id"
    assert len(node.routes) == 2


def test_route_none_handler():
    route = Route("/n", None)
    assert route.handler is None
    assert route._is_async is False


def test_route_match_conversion_error():
    route = Route("/u/<int:user_id>", handler)
    assert route.match("/u/abc") is None


def test_router_signature_error():
    class Weird:
        __init__ = 42

    router = Router(route_class=Weird)
    assert router.routes == []


def test_include_router_with_websocket():
    sub = Router()
    sub.add_route("/a", handler, methods=["GET"])
    sub.add_websocket_route("/ws", handler)

    main = Router()
    main.include_router(sub, prefix="/v")
    assert any(r.path_pattern == "/v/a" for r in main.routes)
    assert any(r.path_pattern == "/v/ws" for r in main.websocket_routes)


def test_add_route_automatic_options_disabled():
    class H:
        provide_automatic_options = False

        def __call__(self):
            pass

    router = Router()
    router.add_route("/no", H())
    assert "OPTIONS" not in router.routes[0].methods


def test_add_route_automatic_options_enabled():
    class H:
        provide_automatic_options = True

        def __call__(self):
            pass

    router = Router()
    router.add_route("/yes", H())
    assert "OPTIONS" in router.routes[0].methods


def test_add_route_custom_class_minimal():
    class MinimalRoute:
        def __init__(self, path, h, methods):
            self.path_pattern = path
            self.handler = h
            self.methods = methods

    router = Router(route_class=MinimalRoute)
    router.add_route("/x", handler, status_code=201)
    assert router.routes[0].handler is handler


def test_path_converter_with_static_child():
    router = Router()
    router.add_route("/a/<path:x>/b", handler)
    route, params, h = router.match("/a/foo/b", "GET")
    assert params == {"x": "foo"}


def test_path_converter_no_children():
    router = Router()
    router.add_route("/pa/<path:x>", handler)
    route, params, h = router.match("/pa/foo", "GET")
    assert params == {"x": "foo"}


def test_include_router_self():
    router = Router()
    with pytest.raises(RuntimeError):
        router.include_router(router)


def test_include_router_circular():
    a = Router()
    b = Router()
    a.include_router(b)
    with pytest.raises(RuntimeError):
        b.include_router(a)


def test_add_route_handler_methods_attr():
    def h():
        pass

    h.methods = ["GET", "PUT"]
    router = Router()
    router.add_route("/m", h)
    assert router.routes[0].methods == ["GET", "PUT", "HEAD", "OPTIONS"]


def test_add_route_falcon_auto_methods():
    class Resource:
        def on_get(self, req, resp):
            pass

        def on_post(self, req, resp):
            pass

    router = Router()
    router.add_route("/r", Resource())
    assert "GET" in router.routes[0].methods
    assert "POST" in router.routes[0].methods


def test_add_route_custom_class_var_kwargs():
    class KwargRoute:
        def __init__(self, path, h, methods, **kwargs):
            self.path_pattern = path
            self.handler = h
            self.methods = methods

    router = Router(route_class=KwargRoute)
    router.add_route("/k", handler, status_code=201)
    assert router.routes[0].handler is handler


def test_static_falcon_head_get():
    class Resource:
        def on_get(self, req, resp):
            pass

    router = Router()
    router.add_route("/g", Resource())
    route, params, h = router.match("/g", "HEAD")
    assert callable(h)


def test_static_falcon_head_fallback():
    class Resource:
        def on_head(self, req, resp):
            pass

    router = Router()
    router.add_route("/s", Resource())
    route, params, h = router.match("/s", "HEAD")
    assert h is Resource().on_head or callable(h)


def test_static_falcon_head_missing_method():
    class Resource:
        def on_post(self, req, resp):
            pass

    router = Router()
    router.add_route("/h", Resource())
    with pytest.raises(HTTPMethodNotAllowed) as exc:
        router.match("/h", "HEAD")
    assert "POST" in exc.value.headers["Allow"]


def test_static_non_falcon_method_not_allowed():
    router = Router()
    router.add_route("/n", handler, methods=["GET"])
    with pytest.raises(HTTPMethodNotAllowed):
        router.match("/n", "POST")


def test_trie_falcon_head_get():
    class Resource:
        def on_get(self, req, resp):
            pass

    router = Router()
    router.add_route("/tg/<int:uid>", Resource())
    route, params, h = router.match("/tg/1", "HEAD")
    assert params == {"uid": 1}


def test_trie_falcon_head_fallback():
    class Resource:
        def on_head(self, req, resp):
            pass

    router = Router()
    router.add_route("/f/<int:uid>", Resource())
    route, params, h = router.match("/f/1", "HEAD")
    assert params == {"uid": 1}


def test_trie_falcon_head_missing_method():
    class Resource:
        def on_post(self, req, resp):
            pass

    router = Router()
    router.add_route("/tm/<int:uid>", Resource())
    with pytest.raises(HTTPMethodNotAllowed):
        router.match("/tm/1", "HEAD")


def test_trie_non_falcon_method_not_allowed():
    router = Router()
    router.add_route("/tn/<id>", handler, methods=["GET"])
    with pytest.raises(HTTPMethodNotAllowed):
        router.match("/tn/1", "POST")


def test_static_falcon_method_not_allowed():
    class Resource:
        def on_get(self, req, resp):
            pass

    router = Router()
    router.add_route("/s", Resource())
    with pytest.raises(HTTPMethodNotAllowed) as exc:
        router.match("/s", "POST")
    assert "GET" in exc.value.headers["Allow"]


def test_match_websocket_success():
    router = Router()
    router.add_websocket_route("/ws/<x>", handler)
    route, params, h = router.match_websocket("/ws/1")
    assert params == {"x": "1"}


def test_match_websocket_not_found():
    router = Router()
    router.add_websocket_route("/ws", handler)
    with pytest.raises(HTTPNotFound):
        router.match_websocket("/other")


def test_apirouter_shortcuts():
    router = APIRouter()

    @router.get("/g")
    def g():
        pass

    @router.post("/p")
    def p():
        pass

    @router.put("/u")
    def u():
        pass

    @router.delete("/d")
    def d():
        pass

    @router.patch("/pa")
    def pa():
        pass

    @router.websocket("/w")
    def ws():
        pass

    paths = [r.path_pattern for r in router.routes]
    methods = dict(zip(paths, router.routes))
    assert "GET" in methods["/g"].methods
    assert "POST" in methods["/p"].methods
    assert "PUT" in methods["/u"].methods
    assert "DELETE" in methods["/d"].methods
    assert "PATCH" in methods["/pa"].methods
    assert router.websocket_routes[0].path_pattern == "/w"
