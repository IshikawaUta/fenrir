class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None, headers: dict = None):
        self.status_code = status_code
        self.detail = detail or self.__class__.__name__
        self.headers = headers or {}
        super().__init__(self.detail)


class HTTPBadRequest(HTTPException):
    def __init__(self, detail: str = "Bad Request", headers: dict = None):
        super().__init__(400, detail, headers)


class HTTPUnauthorized(HTTPException):
    def __init__(self, detail: str = "Unauthorized", headers: dict = None):
        super().__init__(401, detail, headers)


class HTTPForbidden(HTTPException):
    def __init__(self, detail: str = "Forbidden", headers: dict = None):
        super().__init__(403, detail, headers)


class HTTPNotFound(HTTPException):
    def __init__(self, detail: str = "Not Found", headers: dict = None):
        super().__init__(404, detail, headers)


class HTTPMethodNotAllowed(HTTPException):
    def __init__(self, detail: str = "Method Not Allowed", headers: dict = None):
        super().__init__(405, detail, headers)


class HTTPConflict(HTTPException):
    def __init__(self, detail: str = "Conflict", headers: dict = None):
        super().__init__(409, detail, headers)


class HTTPUnprocessableEntity(HTTPException):
    def __init__(self, detail: str = "Unprocessable Entity", headers: dict = None):
        super().__init__(422, detail, headers)


class HTTPInternalServerError(HTTPException):
    def __init__(self, detail: str = "Internal Server Error", headers: dict = None):
        super().__init__(500, detail, headers)
