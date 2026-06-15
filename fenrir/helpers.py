import os
import mimetypes
import urllib.parse
from typing import Any, Dict, Optional
from fenrir.exceptions import HTTPNotFound
from fenrir.response import Response, RedirectResponse

def redirect(location: str, code: int = 302) -> RedirectResponse:
    from fenrir.context import request
    try:
        if not (location.startswith("/") or location.startswith("http://") or location.startswith("https://")):
            req_path = request.path
            base_dir = req_path.rsplit("/", 1)[0]
            location = f"{base_dir}/{location}"
    except RuntimeError:
        pass
    return RedirectResponse(url=location, status=code)


def _build_url_path(path_pattern: str, values: Dict[str, Any]) -> str:
    segments = path_pattern.split("/")
    new_segments = []
    for seg in segments:
        if seg.startswith("<") and seg.endswith(">"):
            inner = seg[1:-1]
            if inner.startswith("re:"):
                # <re:pattern:name>
                param_name = inner.split(":")[-1]
            elif ":" in inner:
                parts = inner.split(":")
                types = {"int", "float", "string", "path", "re"}
                if parts[0] in types:
                    param_name = parts[1]
                else:
                    param_name = parts[0]
            else:
                param_name = inner
            
            if param_name not in values:
                raise ValueError(f"Missing parameter {param_name!r} to build URL")
            new_segments.append(str(values.pop(param_name)))
        else:
            new_segments.append(seg)
    return "/".join(new_segments)


def url_for(endpoint: str, **values: Any) -> str:
    from fenrir.context import current_app
    try:
        app = current_app._get_current_object()
    except RuntimeError:
        from fenrir.app import _active_app
        app = _active_app

    if app is None:
        raise RuntimeError("Attempted to generate a URL without an active application context.")

    # Determine blueprint and handler name
    target_bp = None
    target_handler = endpoint
    if "." in endpoint:
        target_bp, target_handler = endpoint.split(".", 1)

    matched_route = None
    
    # 1. Search HTTP routes
    for route in app.router.routes:
        bp = app._route_blueprints.get(route)
        bp_name = bp.name if bp else None
        
        # Check matching blueprint and handler name
        if bp_name == target_bp:
            handler_name = getattr(route.handler, "__name__", None)
            # Support class-based view handlers via __name__ or __class__.__name__
            if not handler_name and hasattr(route.handler, "__class__"):
                handler_name = route.handler.__class__.__name__
            if handler_name == target_handler:
                matched_route = route
                break

    # 2. Search WebSocket routes if not found
    if not matched_route:
        websocket_routes = getattr(app.router, "websocket_routes", [])
        for route in websocket_routes:
            bp = app._route_blueprints.get(route)
            bp_name = bp.name if bp else None
            if bp_name == target_bp:
                handler_name = getattr(route.handler, "__name__", None)
                if handler_name == target_handler:
                    matched_route = route
                    break

    if not matched_route:
        raise ValueError(f"Could not build url for endpoint {endpoint!r}.")

    path = _build_url_path(matched_route.path_pattern, values)
    if values:
        query_string = urllib.parse.urlencode(values)
        path = f"{path}?{query_string}"
    return path


def send_file(
    path_or_file: Any,
    mimetype: Optional[str] = None,
    as_attachment: bool = False,
    download_name: Optional[str] = None,
) -> Response:
    if isinstance(path_or_file, (str, bytes)):
        filepath = os.path.abspath(path_or_file)
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            raise HTTPNotFound(detail="File not found")
        if mimetype is None:
            mimetype, _ = mimetypes.guess_type(filepath)
            if mimetype is None:
                mimetype = "application/octet-stream"
        name = download_name or os.path.basename(filepath)
        if as_attachment:
            from fenrir.response import FileResponse
            return FileResponse(
                filepath,
                media_type=mimetype,
                filename=name,
            )
        with open(filepath, "rb") as f:
            data = f.read()
    else:
        # File-like object
        data = path_or_file.read()
        if mimetype is None:
            mimetype = "application/octet-stream"
        name = download_name or "file"

    headers = {}
    if as_attachment:
        safe_name = name.replace('"', '').replace('\r', '').replace('\n', '')
        headers["content-disposition"] = f'attachment; filename="{safe_name}"'
    return Response(body=data, content_type=mimetype, headers=headers)


def send_from_directory(directory: str, path: str, **kwargs: Any) -> Response:
    directory = os.path.abspath(directory)
    filepath = os.path.abspath(os.path.join(directory, path))
    if not filepath.startswith(directory):
        raise HTTPNotFound(detail="File not found or access denied")
    return send_file(filepath, **kwargs)
