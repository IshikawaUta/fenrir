import pytest
from fenrir import HTTPForbidden

class CustomAppException(Exception):
    pass

@pytest.mark.anyio
async def test_error_handlers(app):
    @app.exception(CustomAppException)
    def handle_custom(req, exc):
        return "Handled Custom Exception", 400

    @app.exception(403)
    def handle_forbidden(req, exc):
        return "Handled Forbidden", 403

    @app.get("/trigger-exc")
    def trigger_exc():
        raise CustomAppException()

    @app.get("/trigger-forbidden")
    def trigger_forbidden():
        raise HTTPForbidden(detail="forbidden access")

    # Validate incorrect registration raises ValueError
    with pytest.raises(ValueError):
        app.register_error_handler("not-an-exception-or-code", lambda r, e: "error")

    client = app.test_client()

    resp = await client.get("/trigger-exc")
    assert resp.status_code == 400
    assert resp.text == "Handled Custom Exception"

    resp = await client.get("/trigger-forbidden")
    assert resp.status_code == 403
    assert resp.text == "Handled Forbidden"
