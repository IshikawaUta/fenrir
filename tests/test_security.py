import pytest
from fenrir import Fenrir, Depends, APIKeyHeader, APIKeyCookie, APIKeyQuery, HTTPBasic, HTTPBearer, HTTPDigest, OAuth2PasswordBearer, OpenIDConnect
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
