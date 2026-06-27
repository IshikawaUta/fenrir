import inspect
import re
from typing import Dict, Any, List, Tuple, Callable, Optional, Type
from fenrir.exceptions import HTTPMethodNotAllowed, HTTPNotFound

CONVERTER_PATTERNS = {
    "int": (r"\d+", int),
    "float": (r"\d+(?:\.\d+)?", float),
    "path": (r".+", str),
    "str": (r"[^/]+", str),
    "string": (r"[^/]+", str),
}

def compile_path(path_pattern: str) -> Tuple[re.Pattern, Dict[str, Callable]]:
    segment_re = re.compile(r"<([^>]+)>")
    parts = []
    converters = {}
    last_idx = 0
    
    for match in segment_re.finditer(path_pattern):
        parts.append(re.escape(path_pattern[last_idx:match.start()]))
        content = match.group(1)
        subparts = content.split(":")
        
        converter_name = "str"
        param_name = ""
        pattern = r"[^/]+"
        converter_fn = str
        
        if len(subparts) == 1:
            param_name = subparts[0]
        elif len(subparts) == 2:
            p1, p2 = subparts[0].strip(), subparts[1].strip()
            if p1 in CONVERTER_PATTERNS:
                converter_name = p1
                param_name = p2
            elif p2 in CONVERTER_PATTERNS:
                converter_name = p2
                param_name = p1
            else:
                converter_name = "str"
                param_name = p1
        elif len(subparts) == 3:
            p1, p2, p3 = subparts[0].strip(), subparts[1].strip(), subparts[2].strip()
            if p1 == "re":
                converter_name = "re"
                pattern = p2
                param_name = p3
            elif p2 == "re":
                converter_name = "re"
                pattern = p3
                param_name = p1
            else:
                param_name = p1
                converter_name = "str"
                
        if converter_name in CONVERTER_PATTERNS:
            pattern, converter_fn = CONVERTER_PATTERNS[converter_name]
        elif converter_name == "re":
            converter_fn = str
            
        parts.append(f"(?P<{param_name}>{pattern})")
        converters[param_name] = converter_fn
        last_idx = match.end()
        
    parts.append(re.escape(path_pattern[last_idx:]))
    full_regex = re.compile("^" + "".join(parts) + "$")
    return full_regex, converters


class _TrieNode:
    """Internal trie node for O(k) route matching where k = path depth."""
    __slots__ = ('children', 'param_child', 'param_name', 'param_converter', 'routes')

    def __init__(self):
        self.children: Dict[str, "_TrieNode"] = {}
        self.param_child: Optional["_TrieNode"] = None
        self.param_name: Optional[str] = None
        self.param_converter: Optional[str] = None  # 'int', 'float', 'path', 'str', etc.
        self.routes: List["Route"] = []


class RouteTrie:
    """Trie-based route index for fast prefix matching.

    Static path segments are stored as exact-match children in the trie.
    Dynamic segments (``<param>``) are stored as a single parametric child
    per trie node.  At most one regex-based converter (``<re:pattern:name>``)
    is allowed per level since regex routes cannot be indexed structurally.

    The trie only acts as a *pre-filter*: after the trie yields candidate
    routes, each candidate is validated through its compiled regex to
    extract parameters and handle converter-specific semantics.
    """

    def __init__(self):
        self.root = _TrieNode()
        self._static_routes: Dict[str, List["Route"]] = {}

    def insert(self, route: "Route") -> None:
        """Insert a route into the trie index."""
        segments = [s for s in route.path_pattern.split("/") if s]
        node = self.root
        is_static = True

        for seg in segments:
            if seg.startswith("<") and seg.endswith(">"):
                is_static = False
                inner = seg[1:-1]
                parts = inner.split(":")
                converter_name = "str"
                param_name = ""
                if parts[0] == "re":
                    param_name = parts[-1]
                elif len(parts) == 2:
                    p1, p2 = parts[0].strip(), parts[1].strip()
                    if p1 in CONVERTER_PATTERNS:
                        converter_name = p1
                        param_name = p2
                    elif p2 in CONVERTER_PATTERNS:
                        converter_name = p2
                        param_name = p1
                    else:
                        param_name = p1
                else:
                    param_name = parts[0]
                    if param_name in CONVERTER_PATTERNS:
                        converter_name = param_name
                        param_name = parts[1] if len(parts) > 1 else param_name
                if node.param_child is None:
                    node.param_child = _TrieNode()
                    node.param_child.param_name = param_name
                    node.param_child.param_converter = converter_name
                node = node.param_child
            else:
                if seg not in node.children:
                    node.children[seg] = _TrieNode()
                node = node.children[seg]

        node.routes.append(route)
        if is_static:
            self._static_routes.setdefault(route.path_pattern, []).append(route)

    def search(self, path: str) -> List["Route"]:
        """Return candidate routes matching *path*. O(k) where k = segments."""
        segments = [s for s in path.split("/") if s]
        candidates: List["Route"] = []
        self._search_node(self.root, segments, 0, candidates)
        return candidates

    def _search_node(
        self,
        node: "_TrieNode",
        segments: List[str],
        depth: int,
        candidates: List["Route"],
    ) -> None:
        if depth == len(segments):
            candidates.extend(node.routes)
            return

        seg = segments[depth]

        # Exact static match
        child = node.children.get(seg)
        if child is not None:
            self._search_node(child, segments, depth + 1, candidates)

        # Parametric match
        if node.param_child is not None:
            # 'path' converter matches all remaining segments (including slashes)
            if node.param_child.param_converter == "path":
                candidates.extend(node.param_child.routes)
                # Also recurse into children for routes with static segments after <path>.
                # <path> matches all remaining segments, so static children could appear
                # at any depth from depth+1 to len(segments).
                if node.param_child.children:
                    for child_depth in range(depth + 1, len(segments) + 1):
                        for child_node in node.param_child.children.values():
                            self._search_node(child_node, segments, child_depth, candidates)
            else:
                self._search_node(node.param_child, segments, depth + 1, candidates)


class Route:
    def __init__(
        self,
        path_pattern: str,
        handler: Any,
        methods: List[str] = None,
        *,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        status_code: int = 200,
        tags: List[str] = None,
        summary: str = None,
        description: str = None,
        deprecated: bool = False,
        responses: Dict[Any, Any] = None,
        name: str = None,
        response_models: Dict[int, Any] = None,
        ws_timeout: float = None,
    ):
        self.path_pattern = path_pattern
        self.handler = handler
        self.methods = [m.upper() for m in (methods or ["GET"])]
        self.regex, self.converters = compile_path(path_pattern)
        # Cache async status at registration time (avoids inspect.iscoroutinefunction on every call)
        self._is_async = inspect.iscoroutinefunction(handler) if handler is not None else False
        # OpenAPI / serialization metadata
        self.response_model = response_model
        self.response_model_include = response_model_include
        self.response_model_exclude = response_model_exclude
        self.response_model_exclude_unset = response_model_exclude_unset
        self.response_model_exclude_defaults = response_model_exclude_defaults
        self.status_code = status_code
        self.tags = tags or []
        self.summary = summary
        self.description = description
        self.deprecated = deprecated
        self.responses = responses or {}
        self.name = name or getattr(handler, "__name__", None)
        # Multiple response models: {status_code: model_class}
        self.response_models = response_models or {}
        # Cache Falcon resource detection
        self._is_falcon = False
        self._falcon_methods: Dict[str, Callable] = {}
        if handler is not None:
            for attr in dir(handler):
                if attr.startswith("on_") and callable(getattr(handler, attr)):
                    self._is_falcon = True
                    self._falcon_methods[attr] = getattr(handler, attr)
        # WebSocket per-route timeout (seconds)
        self.ws_timeout = ws_timeout

    def match(self, path: str) -> Optional[Dict[str, Any]]:
        m = self.regex.match(path)
        if not m:
            return None
        
        params = {}
        for name, val_str in m.groupdict().items():
            converter = self.converters.get(name, str)
            try:
                params[name] = converter(val_str)
            except ValueError:
                return None  # Conversion failed, doesn't match this route
        return params

    def is_falcon_resource(self) -> bool:
        """Check if the handler behaves like a Falcon resource class."""
        return self._is_falcon

    def get_resource_method(self, method: str) -> Optional[Callable]:
        target_name = f"on_{method.lower()}"
        return self._falcon_methods.get(target_name)


class Router:
    def __init__(self, route_class: Optional[Type[Route]] = None):
        self.routes: List[Route] = []
        self.websocket_routes: List[Route] = []
        self.route_class = route_class or Route
        self.included_routers = []
        self._trie = RouteTrie()

    def include_router(self, other: "Router", prefix: str = ""):
        if other is self:
            raise RuntimeError("Cannot include a router into itself")
        
        # Check for circular/recursive inclusion
        def check_circular(r):
            if r is self:
                raise RuntimeError("Circular router inclusion detected")
            for sub in getattr(r, "included_routers", []):
                check_circular(sub)
                
        check_circular(other)
        self.included_routers.append(other)
        
        for route in other.routes:
            self.add_route(
                prefix + route.path_pattern, route.handler, route.methods,
                response_model=route.response_model,
                response_model_include=route.response_model_include,
                response_model_exclude=route.response_model_exclude,
                response_model_exclude_unset=route.response_model_exclude_unset,
                response_model_exclude_defaults=route.response_model_exclude_defaults,
                status_code=route.status_code,
                tags=route.tags,
                summary=route.summary,
                description=route.description,
                deprecated=route.deprecated,
                responses=route.responses,
                name=route.name,
                response_models=route.response_models,
                ws_timeout=route.ws_timeout,
            )
        for route in other.websocket_routes:
            self.add_websocket_route(
                prefix + route.path_pattern, route.handler,
                ws_timeout=route.ws_timeout,
            )

    def add_route(
        self,
        path_pattern: str,
        handler: Any,
        methods: List[str] = None,
        **route_kwargs,
    ):
        if methods is None:
            if hasattr(handler, "methods") and handler.methods:
                methods = list(handler.methods)
            else:
                for attr in dir(handler):
                    if attr.startswith("on_") and callable(getattr(handler, attr)):
                        if methods is None:
                            methods = []
                        methods.append(attr[3:].upper())
        
        if not methods:
            methods = ["GET"]

        # RFC 7231: HEAD must be supported for any resource that supports GET
        if "GET" in methods and "HEAD" not in methods:
            methods = list(methods) + ["HEAD"]

        provide_automatic_options = getattr(handler, "provide_automatic_options", None)
        if provide_automatic_options is None:
            provide_automatic_options = True
        if provide_automatic_options and "OPTIONS" not in methods:
            methods = list(methods) + ["OPTIONS"]

        # Only pass kwargs that Route accepts
        _route_meta_keys = {
            "response_model", "response_model_include", "response_model_exclude",
            "response_model_exclude_unset", "response_model_exclude_defaults",
            "status_code", "tags", "summary", "description", "deprecated",
            "responses", "name", "response_models", "ws_timeout",
        }
        filtered_kwargs = {k: v for k, v in route_kwargs.items() if k in _route_meta_keys}

        # Respect custom route classes that don't accept extra kwargs
        import inspect as _inspect
        try:
            _init_sig = _inspect.signature(self.route_class.__init__)
            _init_params = set(_init_sig.parameters.keys())
            _has_var_kw = any(
                p.kind == _inspect.Parameter.VAR_KEYWORD
                for p in _init_sig.parameters.values()
            )
            if not _has_var_kw:
                filtered_kwargs = {k: v for k, v in filtered_kwargs.items() if k in _init_params}
        except (ValueError, TypeError):
            pass

        route = self.route_class(path_pattern, handler, methods, **filtered_kwargs)
        self.routes.append(route)
        self._trie.insert(route)

    def add_websocket_route(self, path_pattern: str, handler: Any, ws_timeout: float = None):
        route = self.route_class(path_pattern, handler, ["WEBSOCKET"], ws_timeout=ws_timeout)
        self.websocket_routes.append(route)

    def match(self, path: str, method: str) -> Tuple[Route, Dict[str, Any], Callable]:
        method = method.upper()
        # RFC 7231: HEAD is handled identically to GET (body stripped later)
        effective_method = "GET" if method == "HEAD" else method
        path_matched = False
        allowed_methods = set()

        # Use trie for O(k) candidate lookup instead of O(n) linear scan
        candidates = self._trie.search(path)

        for route in candidates:
            params = route.match(path)
            if params is not None:
                path_matched = True
                
                # Check methods
                if route.is_falcon_resource():
                    resource_method = route.get_resource_method(effective_method)
                    if resource_method:
                        return route, params, resource_method
                    # Also try original method for HEAD on Falcon resources
                    if method != effective_method:
                        resource_method = route.get_resource_method(method)
                        if resource_method:
                            return route, params, resource_method
                    # Find all available on_* methods for this resource
                    for attr in dir(route.handler):
                        if attr.startswith("on_") and callable(getattr(route.handler, attr)):
                            allowed_methods.add(attr[3:].upper())
                else:
                    if effective_method in route.methods or method in route.methods:
                        return route, params, route.handler
                    else:
                        allowed_methods.update(route.methods)
                        
        if path_matched:
            raise HTTPMethodNotAllowed(
                detail=f"Allowed methods: {', '.join(sorted(allowed_methods))}",
                headers={"Allow": ", ".join(sorted(allowed_methods))},
            )
        
        raise HTTPNotFound(detail="No route matches the requested path.")

    def match_websocket(self, path: str) -> Tuple[Route, Dict[str, Any], Callable]:
        for route in self.websocket_routes:
            params = route.match(path)
            if params is not None:
                return route, params, route.handler
        raise HTTPNotFound(detail="No websocket route matches the requested path.")


class APIRouter(Router):
    def route(
        self,
        path: str,
        methods: List[str] = None,
        *,
        response_model: Any = None,
        status_code: int = 200,
        tags: List[str] = None,
        summary: str = None,
        description: str = None,
        deprecated: bool = False,
        responses: Dict = None,
        **kwargs,
    ):
        def decorator(handler):
            self.add_route(
                path, handler, methods,
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                summary=summary,
                description=description,
                deprecated=deprecated,
                responses=responses or {},
                **kwargs,
            )
            return handler
        return decorator

    def get(self, path: str, **kwargs):
        return self.route(path, ["GET"], **kwargs)

    def post(self, path: str, **kwargs):
        return self.route(path, ["POST"], **kwargs)

    def put(self, path: str, **kwargs):
        return self.route(path, ["PUT"], **kwargs)

    def delete(self, path: str, **kwargs):
        return self.route(path, ["DELETE"], **kwargs)

    def patch(self, path: str, **kwargs):
        return self.route(path, ["PATCH"], **kwargs)

    def websocket(self, path: str):
        def decorator(handler):
            self.add_websocket_route(path, handler)
            return handler
        return decorator
