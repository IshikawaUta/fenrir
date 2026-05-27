import pytest
from fenrir import session

@pytest.mark.anyio
async def test_session_cookie_persistence(app):
    app.config["SECRET_KEY"] = "super-secret"

    @app.get("/set")
    def set_val():
        session["user"] = "utah"
        return "set"

    @app.get("/get")
    def get_val():
        return f"Hello {session.get('user')}"

    client = app.test_client()
    
    resp_set = await client.get("/set")
    assert resp_set.status_code == 200
    assert "session" in resp_set.cookies

    # Use the session cookie in the next request
    client.client.cookies.update(resp_set.cookies)
    resp_get = await client.get("/get")
    assert resp_get.status_code == 200
    assert resp_get.text == "Hello utah"
