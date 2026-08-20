"""Unit tests for fenrir.security dependency classes."""
import types

import pytest

from fenrir.exceptions import HTTPException
from fenrir.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPBasic,
    HTTPBearer,
    HTTPDigest,
    OAuth2,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordBearer,
    OpenIDConnect,
    WebSocketTokenAuth,
)


def make_request(headers=None, args=None, cookies=None):
    return types.SimpleNamespace(
        headers=headers or {},
        args=args or {},
        cookies=cookies or {},
    )


def make_ws(scope):
    return types.SimpleNamespace(scope=scope)


@pytest.mark.anyio
async def test_api_key_cookie_no_error():
    dep = APIKeyCookie("sid", auto_error=False)
    assert await dep(make_request(cookies={})) is None


@pytest.mark.anyio
async def test_api_key_header_no_error():
    dep = APIKeyHeader("X-Key", auto_error=False)
    assert await dep(make_request(headers={})) is None


@pytest.mark.anyio
async def test_api_key_query_no_error():
    dep = APIKeyQuery("apikey", auto_error=False)
    assert await dep(make_request(args={})) is None


@pytest.mark.anyio
async def test_ws_token_auth_no_websocket():
    dep = WebSocketTokenAuth(auto_error=False)
    assert await dep(websocket=None) is None

    dep2 = WebSocketTokenAuth(auto_error=True)
    with pytest.raises(HTTPException):
        await dep2(websocket=None)


@pytest.mark.anyio
async def test_ws_token_auth_from_header():
    dep = WebSocketTokenAuth()
    ws = make_ws({"headers": [(b"authorization", b"Bearer abc123")], "query_string": b""})
    assert await dep(ws) == "abc123"


@pytest.mark.anyio
async def test_ws_token_auth_plain_header_value():
    dep = WebSocketTokenAuth()
    ws = make_ws({"headers": [(b"authorization", b"rawtoken")], "query_string": b""})
    assert await dep(ws) == "rawtoken"


@pytest.mark.anyio
async def test_ws_token_auth_query_fallback():
    dep = WebSocketTokenAuth(query_param="token")
    ws = make_ws({"headers": [], "query_string": b"token=qsecret"})
    assert await dep(ws) == "qsecret"


@pytest.mark.anyio
async def test_ws_token_auth_no_token():
    dep = WebSocketTokenAuth(auto_error=False)
    ws = make_ws({"headers": [], "query_string": b""})
    assert await dep(ws) is None

    dep2 = WebSocketTokenAuth(auto_error=True)
    with pytest.raises(HTTPException):
        await dep2(ws)


@pytest.mark.anyio
async def test_http_basic_missing_auth():
    dep = HTTPBasic(auto_error=False)
    assert await dep(make_request(headers={})) is None

    dep2 = HTTPBasic(realm="Protected")
    with pytest.raises(HTTPException) as exc:
        await dep2(make_request(headers={}))
    assert "Basic realm=\"Protected\"" in exc.value.headers.get("WWW-Authenticate", "")

    dep3 = HTTPBasic(auto_error=True)
    with pytest.raises(HTTPException) as exc:
        await dep3(make_request(headers={}))
    assert exc.value.headers.get("WWW-Authenticate") == "Basic"


@pytest.mark.anyio
async def test_http_basic_malformed():
    dep = HTTPBasic(auto_error=False)
    assert await dep(make_request(headers={"authorization": "Basic !!!"})) is None
    assert await dep(make_request(headers={"authorization": "singleword"})) is None

    dep2 = HTTPBasic()
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep2(make_request(headers={"authorization": "Basic !!!"}))
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep2(make_request(headers={"authorization": "singleword"}))


@pytest.mark.anyio
async def test_http_basic_valid():
    import base64
    dep = HTTPBasic()
    token = base64.b64encode(b"user:pass").decode()
    assert await dep(make_request(headers={"authorization": f"Basic {token}"})) == ("user", "pass")


@pytest.mark.anyio
async def test_http_bearer_format_and_errors():
    dep = HTTPBearer(bearerFormat="JWT")
    assert dep.model["bearerFormat"] == "JWT"

    dep2 = HTTPBearer(auto_error=False)
    assert await dep2(make_request(headers={})) is None
    assert await dep2(make_request(headers={"authorization": "Basic xyz"})) is None

    dep3 = HTTPBearer(auto_error=True)
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep3(make_request(headers={"authorization": "Basic xyz"}))
    assert await dep3(make_request(headers={"authorization": "Bearer tok"})) == "tok"


@pytest.mark.anyio
async def test_http_digest():
    dep = HTTPDigest(auto_error=False)
    assert await dep(make_request(headers={})) is None
    assert await dep(make_request(headers={"authorization": "Basic x"})) is None

    dep2 = HTTPDigest(auto_error=True)
    with pytest.raises(HTTPException):
        await dep2(make_request(headers={}))
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep2(make_request(headers={"authorization": "Basic x"}))

    result = await dep2(make_request(headers={
        "authorization": 'Digest username="u", realm="r", nonce="n"'
    }))
    assert result == {"username": "u", "realm": "r", "nonce": "n"}


@pytest.mark.anyio
async def test_oauth2_errors():
    dep = OAuth2(flows={}, auto_error=False)
    assert await dep(make_request(headers={})) is None
    assert await dep(make_request(headers={"authorization": "Basic x"})) is None

    dep2 = OAuth2(flows={}, auto_error=True)
    with pytest.raises(HTTPException):
        await dep2(make_request(headers={}))
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep2(make_request(headers={"authorization": "Basic x"}))
    assert await dep2(make_request(headers={"authorization": "Bearer tok"})) == "tok"


@pytest.mark.anyio
async def test_openid_connect_errors():
    dep = OpenIDConnect("https://example.com/.well-known/openid-configuration", auto_error=False)
    assert await dep(make_request(headers={})) is None
    assert await dep(make_request(headers={"authorization": "Basic x"})) is None
    assert await dep(make_request(headers={"authorization": "Bearer tok"})) == "tok"

    dep2 = OpenIDConnect("https://example.com/.well-known/openid-configuration", auto_error=True)
    with pytest.raises(HTTPException):
        await dep2(make_request(headers={}))
    with pytest.raises(HTTPException, match="Invalid credentials"):
        await dep2(make_request(headers={"authorization": "Basic x"}))


def test_oauth2_subclasses_models():
    pb = OAuth2PasswordBearer(tokenUrl="/token")
    assert pb.model["type"] == "oauth2"
    assert "password" in pb.model["flows"]

    ac = OAuth2AuthorizationCodeBearer(authorizationUrl="/auth", tokenUrl="/token")
    assert "authorizationCode" in ac.model["flows"]
    assert ac.model["flows"]["authorizationCode"]["authorizationUrl"] == "/auth"
