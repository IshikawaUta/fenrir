import pytest
from fenrir import session
from fenrir.routing import CONVERTER_PATTERNS

# Define a custom converter that checks session
def custom_converter(val):
    # Retrieve from session to verify access
    prefix = session.get("prefix", "default")
    return f"{prefix}-{val}"

# Register the custom converter
CONVERTER_PATTERNS["custom"] = (r"[a-z]+", custom_converter)

@pytest.mark.anyio
async def test_converter_access_session(app):
    @app.get("/convert/<custom:val>")
    def convert_view(val):
        return f"Result: {val}"

    client = app.test_client()

    # Pre-populate session using a route
    @app.get("/set-session")
    def set_session():
        session["prefix"] = "hello"
        return "ok"

    await client.get("/set-session")
    resp = await client.get("/convert/world")
    assert resp.status_code == 200
    assert resp.text == "Result: hello-world"
