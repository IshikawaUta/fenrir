"""Unit tests for fenrir.falcon compatibility module."""
from fenrir.falcon import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPError,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPUnauthorized,
    after,
    before,
)


def act(req, resp, resource, params):
    pass


def test_before_twice():
    def r():
        pass

    first = before(act)(r)
    assert len(first._falcon_before_hooks) == 1
    second = before(act)(first)
    assert len(second._falcon_before_hooks) == 2


def test_after_twice():
    def r():
        pass

    first = after(act)(r)
    assert len(first._falcon_after_hooks) == 1
    second = after(act)(first)
    assert len(second._falcon_after_hooks) == 2


def test_http_error_int_status():
    err = HTTPError(404, title="t", description="d")
    assert err.status_code == 404
    assert err.detail == "d"
    assert err.title == "t"
    assert err.description == "d"


def test_http_error_str_status_digit():
    err = HTTPError("500 Internal Server Error", description="oops")
    assert err.status_code == 500
    assert err.detail == "oops"


def test_http_error_str_status_non_digit():
    err = HTTPError("BAD", description="boom")
    assert err.status_code == 500
    assert err.detail == "boom"


def test_http_error_fallback_detail():
    err = HTTPError("BROKEN")
    assert err.status_code == 500
    assert err.detail == "HTTP Error"


def test_http_error_non_str_int_status():
    err = HTTPError(500.5, description="x")
    assert err.status_code == 500
    assert err.detail == "x"


def test_subclasses():
    assert HTTPBadRequest("Bad Request", "d").status_code == 400
    assert HTTPUnauthorized("Unauthorized").status_code == 401
    assert HTTPForbidden("Forbidden").status_code == 403
    assert HTTPNotFound("Not Found").status_code == 404
    assert HTTPMethodNotAllowed("Method Not Allowed").status_code == 405
    assert HTTPConflict("Conflict").status_code == 409
    assert HTTPInternalServerError("Internal Server Error").status_code == 500
