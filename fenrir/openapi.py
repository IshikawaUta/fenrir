import inspect
import re
from typing import Any, Dict, List
from fenrir.compat import Annotated, get_origin, get_args
from pydantic import BaseModel
from fenrir.routing import Route
from fenrir.dependencies import ParamInfo, Header, Cookie, Query, Body, Path, Depends


def _annotation_to_schema(annotation: Any) -> Dict:
    """Convert a Python type annotation to a simple OpenAPI schema dict."""
    if annotation is int or annotation is inspect.Parameter.empty:
        return {"type": "integer"} if annotation is int else {"type": "string"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is bytes:
        return {"type": "string", "format": "binary"}
    return {"type": "string"}


def _path_to_openapi(path_pattern: str) -> str:
    """Convert <name> / <type:name> style paths to {name} OpenAPI style."""
    segment_re = re.compile(r"<([^>]+)>")
    def replace(m):
        content = m.group(1)
        parts = content.split(":")
        from fenrir.routing import CONVERTER_PATTERNS
        if len(parts) == 2:
            p0, p1 = parts[0].strip(), parts[1].strip()
            param_name = p1 if p0 in CONVERTER_PATTERNS else p0
        elif len(parts) == 3 and parts[0] == "re":
            param_name = parts[2].strip()
        else:
            param_name = parts[0].strip()
        return f"{{{param_name}}}"
    return segment_re.sub(replace, path_pattern)


def _resolve_annotation(annotation: Any):
    """Unwrap Annotated[T, marker] → (T, marker_or_None)."""
    if get_origin(annotation) is Annotated:
        inner_args = get_args(annotation)
        base = inner_args[0]
        marker = next(
            (a for a in inner_args[1:] if isinstance(a, (ParamInfo, Depends))),
            None,
        )
        return base, marker
    return annotation, None


def get_openapi(title: str, version: str, routes: List[Route]) -> Dict[str, Any]:
    openapi_schema: Dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": title, "version": version},
        "paths": {},
        "components": {"schemas": {}},
    }

    schemas: Dict[str, Any] = {}

    for route in routes:
        clean_path = _path_to_openapi(route.path_pattern)

        if clean_path not in openapi_schema["paths"]:
            openapi_schema["paths"][clean_path] = {}

        for method in route.methods:
            if method in ("OPTIONS", "WEBSOCKET"):
                continue

            m_lower = method.lower()

            # Resolve handler
            handler = route.handler
            if route.is_falcon_resource():
                handler = route.get_resource_method(method)
                if not handler:
                    continue

            try:
                sig = inspect.signature(handler)
            except (ValueError, TypeError):
                sig = None

            parameters: List[Dict] = []
            request_body = None

            if sig:
                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls", "req", "request", "resp", "response"):
                        continue

                    annotation = param.annotation
                    default = param.default

                    # Unwrap Annotated
                    annotation, annotated_marker = _resolve_annotation(annotation)
                    if annotated_marker is not None and default is inspect.Parameter.empty:
                        default = annotated_marker

                    # Skip BackgroundTasks, WebSocket, Depends
                    if annotation is not inspect.Parameter.empty:
                        try:
                            from fenrir.background import BackgroundTasks as _BT
                            if isinstance(annotation, type) and issubclass(annotation, _BT):
                                continue
                        except ImportError:
                            pass
                        if getattr(annotation, "__name__", "") == "WebSocket":
                            continue
                    if isinstance(default, Depends):
                        continue

                    # Pydantic request body
                    is_pydantic = False
                    if annotation is not inspect.Parameter.empty:
                        try:
                            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                                is_pydantic = True
                        except TypeError:
                            pass

                    if is_pydantic or isinstance(default, Body):
                        model_class = annotation if is_pydantic else None
                        if model_class:
                            model_name = model_class.__name__
                            try:
                                model_schema = model_class.model_json_schema()
                                if "$defs" in model_schema:
                                    for def_name, def_schema in model_schema["$defs"].items():
                                        schemas[def_name] = def_schema
                                    del model_schema["$defs"]
                                schemas[model_name] = model_schema
                                body_schema: Dict = {"$ref": f"#/components/schemas/{model_name}"}
                            except Exception:
                                body_schema = {"type": "object"}
                        else:
                            body_schema = {"type": "object"}

                        request_body = {
                            "content": {"application/json": {"schema": body_schema}},
                            "required": True,
                        }
                        continue

                    # Determine location
                    param_in = "query"
                    alias = None
                    has_default = default is not inspect.Parameter.empty
                    default_val = None

                    if isinstance(default, ParamInfo):
                        alias = default.alias
                        has_default = True
                        default_val = default.default
                        if isinstance(default, Header):
                            param_in = "header"
                        elif isinstance(default, Cookie):
                            param_in = "cookie"
                        elif isinstance(default, Path):
                            param_in = "path"

                    lookup_key = alias or param_name
                    if param_in == "header" and not alias:
                        lookup_key = param_name.replace("_", "-").lower()

                    # Path params override location
                    if f"{{{param_name}}}" in clean_path:
                        param_in = "path"
                        has_default = False

                    schema = _annotation_to_schema(annotation)
                    if (
                        has_default
                        and default_val is not None
                        and default_val is not ...
                        and not isinstance(default_val, ParamInfo)
                    ):
                        schema["default"] = default_val

                    parameters.append({
                        "name": lookup_key,
                        "in": param_in,
                        "required": not has_default or param_in == "path",
                        "schema": schema,
                    })

            # ---------- Response schema ----------
            success_status = str(getattr(route, "status_code", 200))

            if route.response_model is not None:
                rm = route.response_model
                try:
                    if isinstance(rm, type) and issubclass(rm, BaseModel):
                        rm_name = rm.__name__
                        rm_schema = rm.model_json_schema()
                        if "$defs" in rm_schema:
                            for d_name, d_schema in rm_schema["$defs"].items():
                                schemas[d_name] = d_schema
                            del rm_schema["$defs"]
                        schemas[rm_name] = rm_schema
                        success_resp_schema: Dict = {"$ref": f"#/components/schemas/{rm_name}"}
                    else:
                        success_resp_schema = {"type": "object"}
                except Exception:
                    success_resp_schema = {"type": "object"}
            else:
                success_resp_schema = {"type": "object"}

            responses: Dict[str, Any] = {
                success_status: {
                    "description": "Successful Response",
                    "content": {"application/json": {"schema": success_resp_schema}},
                }
            }

            # Merge extra route.responses
            for extra_code, extra_meta in getattr(route, "responses", {}).items():
                responses[str(extra_code)] = extra_meta if isinstance(extra_meta, dict) else {"description": str(extra_meta)}

            # Build operation object
            handler_name = getattr(handler, "__name__", "handler")
            op: Dict[str, Any] = {
                "summary": getattr(route, "summary", None) or handler_name.replace("_", " ").title(),
                "operationId": handler_name,
                "responses": responses,
            }

            if getattr(route, "description", None):
                op["description"] = route.description
            if getattr(route, "tags", None):
                op["tags"] = route.tags
            if getattr(route, "deprecated", False):
                op["deprecated"] = True
            if parameters:
                op["parameters"] = parameters
            if request_body:
                op["requestBody"] = request_body

            openapi_schema["paths"][clean_path][m_lower] = op

    openapi_schema["components"]["schemas"] = schemas
    return openapi_schema


def get_swagger_html(openapi_url: str = "/openapi.json", title: str = "Fenrir Swagger UI") -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <title>{title}</title>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        const ui = SwaggerUIBundle({{
            url: '{openapi_url}',
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.swaggerInterceptor
            ],
            layout: "BaseLayout"
        }});
    </script>
</body>
</html>
"""


def get_redoc_html(openapi_url: str = "/openapi.json", title: str = "Fenrir ReDoc") -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
      body {{
        margin: 0;
        padding: 0;
      }}
    </style>
</head>
<body>
    <redoc spec-url="{openapi_url}"></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"> </script>
</body>
</html>
"""
