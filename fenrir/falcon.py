from typing import Any, Callable, Dict, Optional, Union

from fenrir.exceptions import HTTPException

# HTTP Status Constants
HTTP_200 = "200 OK"
HTTP_201 = "201 Created"
HTTP_202 = "202 Accepted"
HTTP_204 = "204 No Content"
HTTP_301 = "301 Moved Permanently"
HTTP_302 = "302 Found"
HTTP_400 = "400 Bad Request"
HTTP_401 = "401 Unauthorized"
HTTP_403 = "403 Forbidden"
HTTP_404 = "404 Not Found"
HTTP_405 = "405 Method Not Allowed"
HTTP_409 = "409 Conflict"
HTTP_500 = "500 Internal Server Error"

# Hook Decorators
def before(action: Callable[[Any, Any, Any, Dict[str, Any]], Any]) -> Callable[[Callable], Callable]:
    """Execute action(req, resp, resource, params) before the responder."""
    def decorator(responder: Callable) -> Callable:
        if not hasattr(responder, "_falcon_before_hooks"):
            responder._falcon_before_hooks = []  # type: ignore[attr-defined]
        responder._falcon_before_hooks.append(action)  # type: ignore[attr-defined]
        return responder
    return decorator


def after(action: Callable[[Any, Any, Any, Dict[str, Any]], Any]) -> Callable[[Callable], Callable]:
    """Execute action(req, resp, resource, params) after the responder."""
    def decorator(responder: Callable) -> Callable:
        if not hasattr(responder, "_falcon_after_hooks"):
            responder._falcon_after_hooks = []  # type: ignore[attr-defined]
        # In Falcon, hooks executed by @after run in reverse order of decoration,
        # but to keep it simple we just append them.
        responder._falcon_after_hooks.append(action)  # type: ignore[attr-defined]
        return responder
    return decorator


# HTTP Exception Classes
class HTTPError(HTTPException):
    def __init__(
        self,
        status: Union[str, int],
        title: Optional[str] = None,
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> None:
        status_code = 500
        if isinstance(status, int):
            status_code = status
        elif isinstance(status, str):
            parts = status.split(" ", 1)
            if parts[0].isdigit():
                status_code = int(parts[0])

        detail = description or title or "HTTP Error"
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.title = title
        self.description = description


class HTTPBadRequest(HTTPError):
    def __init__(self, title: Optional[str] = "Bad Request", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_400, title, description, **kwargs)


class HTTPUnauthorized(HTTPError):
    def __init__(self, title: Optional[str] = "Unauthorized", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_401, title, description, **kwargs)


class HTTPForbidden(HTTPError):
    def __init__(self, title: Optional[str] = "Forbidden", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_403, title, description, **kwargs)


class HTTPNotFound(HTTPError):
    def __init__(self, title: Optional[str] = "Not Found", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_404, title, description, **kwargs)


class HTTPMethodNotAllowed(HTTPError):
    def __init__(self, title: Optional[str] = "Method Not Allowed", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_405, title, description, **kwargs)


class HTTPConflict(HTTPError):
    def __init__(self, title: Optional[str] = "Conflict", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_409, title, description, **kwargs)


class HTTPInternalServerError(HTTPError):
    def __init__(self, title: Optional[str] = "Internal Server Error", description: Optional[str] = None, **kwargs) -> None:
        super().__init__(HTTP_500, title, description, **kwargs)
