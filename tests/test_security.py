import pytest

from fenrir import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    Depends,
    Fenrir,
    HTTPBasic,
    HTTPBearer,
    OAuth2PasswordBearer,
    SecurityHeadersMiddleware,
)
from fenrir.testing import TestClient


@pytest.mark.anyio
async def test_api_key_header():
    app = Fenrir()
    header_scheme = APIKeyHeader(name="X-API-Key")

    @app.get("/header")
    async def get_header(key: str = Depends(header_scheme)):
        return {"key": key}

    client = TestClient(app)

    # Success
    resp = await client.get("/header", headers={"X-API-Key": "mysecret"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "mysecret"}

    # Unauthorized (auto_error)
    resp = await client.get("/header")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


@pytest.mark.anyio
async def test_api_key_cookie():
    app = Fenrir()
    cookie_scheme = APIKeyCookie(name="session_key")

    @app.get("/cookie")
    async def get_cookie(key: str = Depends(cookie_scheme)):
        return {"key": key}

    client = TestClient(app)

    # Success
    client.client.cookies.update({"session_key": "cookieval"})
    resp = await client.get("/cookie")
    assert resp.status_code == 200
    assert resp.json() == {"key": "cookieval"}

    # Unauthorized
    client.client.cookies.clear()
    resp = await client.get("/cookie")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_api_key_query():
    app = Fenrir()
    query_scheme = APIKeyQuery(name="api_key")

    @app.get("/query")
    async def get_query(key: str = Depends(query_scheme)):
        return {"key": key}

    client = TestClient(app)

    # Success
    resp = await client.get("/query?api_key=queryval")
    assert resp.status_code == 200
    assert resp.json() == {"key": "queryval"}

    # Unauthorized
    resp = await client.get("/query")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_http_basic():
    app = Fenrir()
    basic_scheme = HTTPBasic(realm="Secured Area")

    @app.get("/basic")
    async def get_basic(creds = Depends(basic_scheme)):
        return {"username": creds[0], "password": creds[1]}

    client = TestClient(app)

    # Success (testadmin:password123 -> dGVzdGFkbWluOnBhc3N3b3JkMTIz)
    resp = await client.get("/basic", headers={"Authorization": "Basic dGVzdGFkbWluOnBhc3N3b3JkMTIz"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "testadmin", "password": "password123"}

    # No credentials (WWW-Authenticate header presence)
    resp = await client.get("/basic")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == 'Basic realm="Secured Area"'


@pytest.mark.anyio
async def test_http_bearer():
    app = Fenrir()
    bearer_scheme = HTTPBearer()

    @app.get("/bearer")
    async def get_bearer(token: str = Depends(bearer_scheme)):
        return {"token": token}

    client = TestClient(app)

    # Success
    resp = await client.get("/bearer", headers={"Authorization": "Bearer tok123"})
    assert resp.status_code == 200
    assert resp.json() == {"token": "tok123"}

    # Missing
    resp = await client.get("/bearer")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_oauth2_password():
    app = Fenrir()
    oauth_scheme = OAuth2PasswordBearer(tokenUrl="token")

    @app.get("/oauth2")
    async def get_oauth2(token: str = Depends(oauth_scheme)):
        return {"token": token}

    client = TestClient(app)

    # Success
    resp = await client.get("/oauth2", headers={"Authorization": "Bearer abc"})
    assert resp.status_code == 200
    assert resp.json() == {"token": "abc"}


@pytest.mark.anyio
async def test_security_headers_middleware():
    app = Fenrir()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def index():
        return {"ok": True}

    client = TestClient(app)
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"


@pytest.mark.anyio
async def test_security_headers_never_overwrite_existing():
    app = Fenrir()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def index():
        return {"ok": True}

    client = TestClient(app)
    resp = await client.get("/", headers={"X-Frame-Options": "SAMEORIGIN"})
    # Request header must not clobber the middleware's DENY default, and an
    # existing app-set response header must be preserved.
    assert resp.headers["x-frame-options"] == "DENY"


@pytest.mark.anyio
async def test_security_headers_csp():
    app = Fenrir()
    app.add_middleware(SecurityHeadersMiddleware, csp="default-src 'self'")

    @app.get("/")
    async def index():
        return {"ok": True}

    client = TestClient(app)
    resp = await client.get("/")
    assert resp.headers["content-security-policy"] == "default-src 'self'"


@pytest.mark.anyio
async def test_docs_disabled_in_production_by_default():
    app = Fenrir()
    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None

    client = TestClient(app)
    resp = await client.get("/openapi.json")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_docs_enabled_in_dev_mode_and_via_flag():
    assert Fenrir(dev_mode=True).docs_url == "/docs"
    assert Fenrir(dev_mode=True).openapi_url == "/openapi.json"
    assert Fenrir(docs_enabled=True).docs_url == "/docs"

    client = TestClient(Fenrir(docs_enabled=True))
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_max_content_length_config():
    app = Fenrir()
    app.config["MAX_CONTENT_LENGTH"] = 10

    @app.post("/")
    async def echo():
        return {"ok": True}

    client = TestClient(app)
    big = await client.post("/", json={"data": "this is definitely longer than ten bytes"})
    assert big.status_code == 413
    small = await client.post("/", json={"ok": 1})
    assert small.status_code == 200


@pytest.mark.anyio
async def test_rate_limit_config():
    app = Fenrir()
    app.config["RATE_LIMIT_MAX_REQUESTS"] = 2

    @app.get("/")
    async def index():
        return {"ok": True}

    client = TestClient(app)
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/")).status_code == 429
