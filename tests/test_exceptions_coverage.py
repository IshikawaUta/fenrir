"""Tests for fenrir.exceptions — HTTP exception hierarchy."""
import pytest
from fenrir.exceptions import (
    HTTPException,
    HTTPBadRequest,
    HTTPUnauthorized,
    HTTPForbidden,
    HTTPNotFound,
    HTTPMethodNotAllowed,
    HTTPConflict,
    HTTPUnprocessableEntity,
    HTTPInternalServerError,
)


class TestHTTPExceptionBase:
    def test_base_status_code(self):
        exc = HTTPException(418)
        assert exc.status_code == 418

    def test_base_detail(self):
        exc = HTTPException(500, detail="custom error")
        assert exc.detail == "custom error"

    def test_base_default_detail(self):
        exc = HTTPException(500)
        assert exc.detail == "HTTPException"

    def test_base_headers(self):
        exc = HTTPException(500, headers={"X-Custom": "val"})
        assert exc.headers == {"X-Custom": "val"}

    def test_base_default_headers(self):
        exc = HTTPException(500)
        assert exc.headers == {}

    def test_is_exception(self):
        assert issubclass(HTTPException, Exception)

    def test_str_representation(self):
        exc = HTTPException(400, detail="bad")
        assert str(exc) == "bad"

    def test_can_be_raised_and_caught(self):
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(400, detail="oops")
        assert exc_info.value.status_code == 400


class TestHTTPBadRequest:
    def test_status_code(self):
        assert HTTPBadRequest().status_code == 400

    def test_default_detail(self):
        assert HTTPBadRequest().detail == "Bad Request"

    def test_custom_detail(self):
        assert HTTPBadRequest(detail="invalid input").detail == "invalid input"


class TestHTTPUnauthorized:
    def test_status_code(self):
        assert HTTPUnauthorized().status_code == 401

    def test_default_detail(self):
        assert HTTPUnauthorized().detail == "Unauthorized"


class TestHTTPForbidden:
    def test_status_code(self):
        assert HTTPForbidden().status_code == 403

    def test_default_detail(self):
        assert HTTPForbidden().detail == "Forbidden"


class TestHTTPNotFound:
    def test_status_code(self):
        assert HTTPNotFound().status_code == 404

    def test_default_detail(self):
        assert HTTPNotFound().detail == "Not Found"


class TestHTTPMethodNotAllowed:
    def test_status_code(self):
        assert HTTPMethodNotAllowed().status_code == 405

    def test_default_detail(self):
        assert HTTPMethodNotAllowed().detail == "Method Not Allowed"


class TestHTTPConflict:
    def test_status_code(self):
        assert HTTPConflict().status_code == 409

    def test_default_detail(self):
        assert HTTPConflict().detail == "Conflict"


class TestHTTPUnprocessableEntity:
    def test_status_code(self):
        assert HTTPUnprocessableEntity().status_code == 422

    def test_default_detail(self):
        assert HTTPUnprocessableEntity().detail == "Unprocessable Entity"


class TestHTTPInternalServerError:
    def test_status_code(self):
        assert HTTPInternalServerError().status_code == 500

    def test_default_detail(self):
        assert HTTPInternalServerError().detail == "Internal Server Error"


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        classes = [
            HTTPBadRequest, HTTPUnauthorized, HTTPForbidden,
            HTTPNotFound, HTTPMethodNotAllowed, HTTPConflict,
            HTTPUnprocessableEntity, HTTPInternalServerError,
        ]
        for cls in classes:
            assert issubclass(cls, HTTPException)

    def test_all_catchable_as_http_exception(self):
        exceptions = [
            HTTPBadRequest(), HTTPUnauthorized(), HTTPForbidden(),
            HTTPNotFound(), HTTPMethodNotAllowed(), HTTPConflict(),
            HTTPUnprocessableEntity(), HTTPInternalServerError(),
        ]
        for exc in exceptions:
            with pytest.raises(HTTPException):
                raise exc

    def test_headers_propagation(self):
        exc = HTTPNotFound(headers={"X-Request-ID": "123"})
        assert exc.headers == {"X-Request-ID": "123"}
        assert exc.status_code == 404
