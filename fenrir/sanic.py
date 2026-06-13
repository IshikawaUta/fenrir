from fenrir.app import Fenrir as Sanic
from fenrir.exceptions import (
    HTTPException as SanicException,
    HTTPBadRequest as BadRequest,
    HTTPUnauthorized as Unauthorized,
    HTTPForbidden as Forbidden,
    HTTPNotFound as NotFound,
    HTTPInternalServerError as ServerError,
)
from fenrir.response import JSONResponse, TextResponse, HTMLResponse, Response, RedirectResponse
from typing import Any, Dict, Optional, Union

# response helpers matching sanic.response.*
class response:
    @staticmethod
    def json(body: Any, status: int = 200, headers: Optional[Dict[str, str]] = None, **kwargs) -> JSONResponse:
        return JSONResponse(body, status=status, headers=headers)

    @staticmethod
    def text(body: str, status: int = 200, headers: Optional[Dict[str, str]] = None, **kwargs) -> TextResponse:
        return TextResponse(body, status=status, headers=headers)

    @staticmethod
    def html(body: str, status: int = 200, headers: Optional[Dict[str, str]] = None, **kwargs) -> HTMLResponse:
        return HTMLResponse(body, status=status, headers=headers)

    @staticmethod
    def raw(
        body: Union[str, bytes],
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
        content_type: str = "application/octet-stream",
        **kwargs
    ) -> Response:
        return Response(body=body, status=status, headers=headers, content_type=content_type)

    @staticmethod
    def redirect(to: str, status: int = 302, headers: Optional[Dict[str, str]] = None) -> RedirectResponse:
        return RedirectResponse(url=to, status=status, headers=headers)


# exception definitions matching sanic.exceptions.*
class exceptions:
    SanicException = SanicException
    BadRequest = BadRequest
    Unauthorized = Unauthorized
    Forbidden = Forbidden
    NotFound = NotFound
    ServerError = ServerError
