import pytest
from fenrir import Fenrir

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def app():
    app = Fenrir(title="TestApp")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["SESSION_COOKIE_SECURE"] = False
    return app

@pytest.fixture
async def client(app):
    async with app.test_client() as c:
        yield c
