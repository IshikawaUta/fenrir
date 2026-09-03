import inspect
from typing import Any, Callable, Dict, Optional, cast

from fenrir.compat import Annotated, get_args, get_origin, to_thread
from fenrir.exceptions import HTTPUnprocessableEntity
from fenrir.request import Request
from fenrir.response import Response

# Lazy imports for types used in hot path
_BackgroundTasks = None
_UploadFile = None
_current_app = None
_BaseModel = None
_TypeAdapter = None
_ValidationError = None

# Cache for dependency async status (avoids inspect.iscoroutinefunction on every call)
# Bounded to prevent memory leak — evicts oldest entries when full
_dep_is_async_cache: Dict[int, bool] = {}
_DEP_CACHE_MAX = 1024


def _is_async_dep(dep_func):
    """Check if a dependency function is async, with caching."""
    dep_id = id(dep_func)
    result = _dep_is_async_cache.get(dep_id)
    if result is not None:
        return result
    result = inspect.iscoroutinefunction(dep_func) or (
        callable(dep_func) and inspect.iscoroutinefunction(dep_func.__call__)
    )
    if len(_dep_is_async_cache) >= _DEP_CACHE_MAX:
        _dep_is_async_cache.pop(next(iter(_dep_is_async_cache)))
    _dep_is_async_cache[dep_id] = result
    return result


def _get_background_tasks_class():
    global _BackgroundTasks
    if _BackgroundTasks is None:
        from fenrir.background import BackgroundTasks
        _BackgroundTasks = BackgroundTasks
    return _BackgroundTasks


def _get_upload_file_class():
    global _UploadFile
    if _UploadFile is None:
        from fenrir.upload import UploadFile
        _UploadFile = UploadFile
    return _UploadFile


def _get_current_app():
    global _current_app
    if _current_app is None:
        from fenrir.context import current_app
        _current_app = current_app
    return _current_app


def _get_base_model():
    global _BaseModel
    if _BaseModel is None:
        from pydantic import BaseModel
        _BaseModel = BaseModel
    return _BaseModel


def _get_type_adapter():
    global _TypeAdapter
    if _TypeAdapter is None:
        from pydantic import TypeAdapter
        _TypeAdapter = TypeAdapter
    return _TypeAdapter


def _get_validation_error():
    global _ValidationError
    if _ValidationError is None:
        from pydantic import ValidationError
        _ValidationError = ValidationError
    return _ValidationError

# Module-level cache for inspect.signature() results — avoids repeated
# signature introspection on every request for every handler/dependency.
_signature_cache: Dict[Callable, inspect.Signature] = {}
_SIGNATURE_CACHE_MAX = 2048

# Module-level cache for pydantic TypeAdapter — avoids recompilation on every request.
_type_adapter_cache: Dict[Any, Any] = {}
_TYPE_ADAPTER_CACHE_MAX = 2048


def _evict_if_needed(cache: dict, max_size: int) -> None:
    """Evict oldest entry if cache exceeds max size."""
    if len(cache) >= max_size:
        cache.pop(next(iter(cache)))


def _get_cached_type_adapter(annotation: type) -> Any:
    """Return a cached TypeAdapter for the given annotation."""
    try:
        return _type_adapter_cache[annotation]
    except (KeyError, TypeError):
        adapter = _get_type_adapter()(annotation)
        try:
            _evict_if_needed(_type_adapter_cache, _TYPE_ADAPTER_CACHE_MAX)
            _type_adapter_cache[annotation] = adapter
        except TypeError:
            pass  # unhashable type, skip caching
        return adapter


def _get_cached_signature(func: Callable) -> inspect.Signature:
    """Return a cached inspect.Signature for *func*."""
    try:
        return _signature_cache[func]
    except (KeyError, TypeError):
        # TypeError: func is not hashable (e.g. a lambda bound to a local)
        pass
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        raise
    try:
        _evict_if_needed(_signature_cache, _SIGNATURE_CACHE_MAX)
        _signature_cache[func] = sig
    except TypeError:
        pass  # unhashable func — don't cache
    return sig

class ParamInfo:
    def __init__(self, default: Any = None, alias: str = None):
        self.default = default
        self.alias = alias


class Query(ParamInfo):
    pass


class Header(ParamInfo):
    pass


class Cookie(ParamInfo):
    pass


class Body(ParamInfo):
    pass


class Path(ParamInfo):
    pass


class FormParam(ParamInfo):
    pass


class FileParam(ParamInfo):
    pass


def Form(default: Any = ..., alias: str = None) -> Any:
    return FormParam(default=default, alias=alias)


def File(default: Any = ..., alias: str = None) -> Any:
    return FileParam(default=default, alias=alias)


class Depends:
    def __init__(self, dependency: Optional[Callable] = None, use_cache: bool = True):
        self.dependency = dependency
        self.use_cache = use_cache

    def __hash__(self):
        return hash((self.dependency, self.use_cache))

    def __eq__(self, other):
        return isinstance(other, Depends) and self.dependency == other.dependency and self.use_cache == other.use_cache


async def resolve_parameters(
    func: Callable,
    path_params: Dict[str, Any],
    req_obj: Request,
    resp_obj: Response,
    ws: Any = None,
    resolving_set: set = None,
) -> Dict[str, Any]:
    sig = _get_cached_signature(func)
    resolved = {}

    if resolving_set is None:
        resolving_set = set()

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls") or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = param.annotation
        default = param.default

        # ------------------------------------------------------------------ #
        # Unwrap Annotated[T, ParamInfo(...)] → extract inner type + marker   #
        # e.g. Annotated[str, Query()] or Annotated[UserModel, Body()]        #
        # ------------------------------------------------------------------ #
        _annotated_default_val = inspect.Parameter.empty  # original func default
        if get_origin(annotation) is Annotated:
            inner_args = get_args(annotation)
            annotation = inner_args[0]  # real type
            # Pick first ParamInfo/Depends marker
            for extra in inner_args[1:]:
                if isinstance(extra, (ParamInfo, Depends)):
                    # Always apply the marker as the param descriptor.
                    # If the function already has a default value (e.g. = "anon"),
                    # carry it over into the marker if the marker doesn't have one.
                    if isinstance(extra, ParamInfo) and extra.default is ...:
                        if default is not inspect.Parameter.empty:
                            # Build a copy with the actual default value
                            marker_copy = extra.__class__(default=default, alias=extra.alias)
                            _annotated_default_val = default
                            default = marker_copy
                        else:
                            default = extra
                    else:
                        default = extra
                    break

        # ------------------------------------------------------------------ #
        # BackgroundTasks auto-injection                                       #
        # ------------------------------------------------------------------ #
        if annotation is not inspect.Parameter.empty:
            _BT = _get_background_tasks_class()
            if annotation is _BT or (isinstance(annotation, type) and issubclass(annotation, _BT)):
                if not hasattr(req_obj, "_background_tasks"):
                    req_obj._background_tasks = _BT()  # type: ignore[attr-defined]
                resolved[param_name] = req_obj._background_tasks  # type: ignore[attr-defined]
                continue

        # Handle WebSocket injection
        if param_name in ("websocket", "ws") or (annotation != inspect.Parameter.empty and getattr(annotation, "__name__", "") == "WebSocket"):
            resolved[param_name] = ws
            continue

        # Handle explicit req/resp parameters
        if param_name in ("req", "request"):
            resolved[param_name] = req_obj
            continue
        if param_name in ("resp", "response"):
            resolved[param_name] = resp_obj
            continue

        # 1. Dependency Injection (Depends)
        if isinstance(default, Depends):
            dep_func = default.dependency
            if dep_func is None:
                if annotation != inspect.Parameter.empty and callable(annotation):
                    dep_func = annotation
                else:
                    raise ValueError(f"Dependency for parameter '{param_name}' could not be resolved.")

            # Unwrap lazy lambda dependencies
            if getattr(dep_func, "__name__", "") == "<lambda>":
                real_dep = dep_func()
                if callable(real_dep):
                    dep_func = real_dep

            # Apply dependency overrides if present
            current_app = _get_current_app()
            try:
                if hasattr(current_app, "dependency_overrides") and current_app.dependency_overrides:
                    if dep_func in current_app.dependency_overrides:
                        dep_func = current_app.dependency_overrides[dep_func]
            except Exception:
                pass

            # Check dependency cache
            if not hasattr(req_obj, "_dependency_cache"):
                req_obj._dependency_cache = {}  # type: ignore[attr-defined]

            use_cache = getattr(default, "use_cache", True)
            if use_cache and dep_func in req_obj._dependency_cache:  # type: ignore[attr-defined]
                resolved[param_name] = req_obj._dependency_cache[dep_func]  # type: ignore[attr-defined]
                continue

            # Detect circular dependencies
            if dep_func in resolving_set:
                dep_name = getattr(dep_func, "__name__", getattr(dep_func.__class__, "__name__", "dependency"))
                raise RuntimeError(f"Circular dependency detected for '{dep_name}'")

            resolving_set.add(dep_func)
            try:
                dep_kwargs = await resolve_parameters(dep_func, path_params, req_obj, resp_obj, ws, resolving_set)

                is_async_gen = inspect.isasyncgenfunction(dep_func) or (callable(dep_func) and inspect.isasyncgenfunction(dep_func.__call__))  # type: ignore[operator]
                is_sync_gen = inspect.isgeneratorfunction(dep_func) or (callable(dep_func) and inspect.isgeneratorfunction(dep_func.__call__))  # type: ignore[operator]

                if is_async_gen or is_sync_gen:
                    if is_async_gen:
                        gen = dep_func(**dep_kwargs)
                        dep_val = await gen.__anext__()
                        async def async_cleanup(_gen=gen):
                            try:
                                await _gen.__anext__()
                            except StopAsyncIteration:
                                pass
                        if not hasattr(req_obj, "_yield_cleanups"):
                            req_obj._yield_cleanups = []  # type: ignore[attr-defined]
                        req_obj._yield_cleanups.append(async_cleanup)  # type: ignore[attr-defined]
                    else:
                        gen = dep_func(**dep_kwargs)
                        dep_val = next(gen)
                        def sync_cleanup(_gen=gen):
                            try:
                                next(_gen)
                            except StopIteration:
                                pass
                        if not hasattr(req_obj, "_yield_cleanups"):
                            req_obj._yield_cleanups = []  # type: ignore[attr-defined]
                        req_obj._yield_cleanups.append(sync_cleanup)  # type: ignore[attr-defined]
                else:
                    is_coroutine_fn = _is_async_dep(dep_func)
                    if is_coroutine_fn:
                        dep_val = await cast(Any, dep_func(**dep_kwargs))
                    else:
                        dep_val = await to_thread(dep_func, **dep_kwargs)

                if use_cache:
                    req_obj._dependency_cache[dep_func] = dep_val  # type: ignore[attr-defined]
                resolved[param_name] = dep_val
            finally:
                resolving_set.remove(dep_func)
            continue

        # 2. Path parameter
        if param_name in path_params:
            val = path_params[param_name]
            if annotation != inspect.Parameter.empty:
                try:
                    val = _get_cached_type_adapter(annotation).validate_python(val)
                except Exception as e:
                    raise HTTPUnprocessableEntity(
                        detail=[
                            {
                                "loc": ["path", param_name],
                                "msg": str(e),
                                "type": "type_error"
                            }
                        ]
                    ) from e
            resolved[param_name] = val
            continue

        # 3. Form or File parameters
        is_file = False
        is_form = False

        if isinstance(default, FileParam):
            is_file = True
        elif annotation != inspect.Parameter.empty:
            # Check if annotation is UploadFile or lists/unions containing it
            UploadFile = _get_upload_file_class()
            if annotation is UploadFile or getattr(annotation, "__name__", "") == "UploadFile":
                is_file = True
            elif hasattr(annotation, "__origin__"):
                args = getattr(annotation, "__args__", ())
                if UploadFile in args or any(getattr(a, "__name__", "") == "UploadFile" for a in args):
                    is_file = True

        if isinstance(default, FormParam):
            is_form = True

        if is_form or is_file:
            form_data = await req_obj.form()
            lookup_key = (isinstance(default, ParamInfo) and default.alias) or param_name
            raw_val = form_data.get(lookup_key)

            if raw_val is None:
                has_default = False
                default_val = None
                if default != inspect.Parameter.empty:
                    if isinstance(default, ParamInfo):
                        if default.default is not ...:
                            has_default = True
                            default_val = default.default
                    else:
                        has_default = True
                        default_val = default

                if has_default:
                    val = default_val
                else:
                    raise HTTPUnprocessableEntity(
                        detail=[
                            {
                                "loc": ["body", lookup_key],
                                "msg": "field required",
                                "type": "value_error.missing"
                            }
                        ]
                    )
            else:
                if is_file:
                    val = raw_val
                else:
                    if annotation != inspect.Parameter.empty:
                        try:
                            val = _get_cached_type_adapter(annotation).validate_python(raw_val)
                        except Exception as e:
                            raise HTTPUnprocessableEntity(
                                detail=[
                                    {
                                        "loc": ["query", param_name],
                                        "msg": str(e),
                                        "type": "type_error"
                                    }
                                ]
                            ) from e
                    else:
                        val = raw_val
            resolved[param_name] = val
            continue

        # 4. Request Body (Pydantic model or explicit Body)
        is_pydantic = False
        if annotation != inspect.Parameter.empty:
            try:
                if issubclass(annotation, _get_base_model()):
                    is_pydantic = True
            except TypeError:
                pass

        if is_pydantic or isinstance(default, Body):
            current_app = _get_current_app()
            strict = False
            try:
                if hasattr(current_app, "strict_content_type"):
                    strict = current_app.strict_content_type
            except Exception:
                pass

            if strict:
                ct = req_obj.headers.get("content-type", "")
                if "application/json" not in ct.lower():
                    from fenrir.exceptions import HTTPException
                    raise HTTPException(status_code=400, detail="Strict content-type check failed")

            body_json = req_obj.json
            if is_pydantic:
                try:
                    resolved[param_name] = annotation.model_validate(body_json)
                except _get_validation_error() as e:
                    errors = e.errors()
                    for err in errors:
                        loc = err.get("loc", ())
                        err["loc"] = ("body",) + loc
                    raise HTTPUnprocessableEntity(detail=errors) from e
            else:
                resolved[param_name] = body_json
            continue

        # 5. Query, Header, Cookie parameters
        source = "query"
        alias = None
        has_default = param.default != inspect.Parameter.empty
        default_val = None

        if isinstance(default, ParamInfo):
            alias = default.alias
            has_default = True
            default_val = default.default
            if isinstance(default, Header):
                source = "header"
            elif isinstance(default, Cookie):
                source = "cookie"
            elif isinstance(default, Query):
                source = "query"
        elif default is not inspect.Parameter.empty:
            default_val = default

        lookup_key = alias or param_name
        if source == "header" and not alias:
            lookup_key = param_name.replace("_", "-").lower()

        raw_val = None
        if source == "query":
            raw_val = req_obj.args.get(lookup_key)
        elif source == "header":
            raw_val = req_obj.headers.get(lookup_key.lower())
        elif source == "cookie":  # pragma: no branch
            raw_val = req_obj.cookies.get(lookup_key)

        if raw_val is None:
            if has_default:
                val = default_val
            else:
                raise HTTPUnprocessableEntity(
                    detail=[
                        {
                            "loc": [source, lookup_key],
                            "msg": "field required",
                            "type": "value_error.missing"
                        }
                    ]
                )
        else:
            if annotation != inspect.Parameter.empty:
                try:
                    val = _get_cached_type_adapter(annotation).validate_python(raw_val)
                except Exception as e:
                    raise HTTPUnprocessableEntity(
                        detail=[
                            {
                                "loc": [source, lookup_key],
                                "msg": str(e),
                                "type": "type_error"
                            }
                        ]
                    ) from e
            else:
                val = raw_val

        resolved[param_name] = val

    return resolved
